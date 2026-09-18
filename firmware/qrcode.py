# A small QR code encoder for the Pico: versions 1 to 6 (21 to 41 modules), error correction L or M,
# alphanumeric or byte mode, Reed-Solomon over GF(256), all eight masks scored as the spec asks.
# Pure Python so the same file runs on the laptop for tests. encode(text) returns (n, rows) in the
# form wallet.draw_qr and slots draw: n modules a side, rows[r] an int whose bit c is the dark module
# at column c. A 130-character uppercase hex key fits version 5 (37 modules) at level L.
ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
# per version: total codewords, then per level: (ec codewords per block, number of blocks)
TOTAL = (0, 26, 44, 70, 100, 134, 172)
BLOCKS = {"L": (None, (7, 1), (10, 1), (15, 1), (20, 1), (26, 1), (18, 2)),
          "M": (None, (10, 1), (16, 1), (26, 1), (18, 2), (24, 2), (16, 4))}
LEVEL_BITS = {"L": 1, "M": 0}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs(data, nec):
    """Reed-Solomon error-correction codewords for one block."""
    gen = [1]                       # coefficients, highest degree first; times (x + a^i) each round
    for i in range(nec):
        gen = [g ^ (_mul(gen[j - 1], _EXP[i]) if j else 0) for j, g in enumerate(gen + [0])]
    rem = [0] * nec
    for d in data:
        f = d ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for j in range(nec):
                rem[j] ^= _mul(gen[j + 1], f)
    return rem


def _bits(text, version, level):
    """Mode, count, data, terminator, padding: the data codewords, or None if it does not fit."""
    nec, nb = BLOCKS[level][version]
    cap = TOTAL[version] - nec * nb
    out = []
    alnum = all(c in ALNUM for c in text)
    if alnum:
        out.append((2, 4)); out.append((len(text), 9))
        for i in range(0, len(text) - 1, 2):
            out.append((ALNUM.index(text[i]) * 45 + ALNUM.index(text[i + 1]), 11))
        if len(text) % 2:
            out.append((ALNUM.index(text[-1]), 6))
    else:
        b = text.encode()
        out.append((4, 4)); out.append((len(b), 8))
        for c in b:
            out.append((c, 8))
    n = sum(w for _, w in out)
    if n > cap * 8:
        return None
    out.append((0, min(4, cap * 8 - n)))
    acc, nacc, cw = 0, 0, []
    for v, w in out:
        acc = (acc << w) | v
        nacc += w
        while nacc >= 8:
            cw.append((acc >> (nacc - 8)) & 0xFF)
            nacc -= 8
    if nacc:
        cw.append((acc << (8 - nacc)) & 0xFF)
    pad = (0xEC, 0x11)
    while len(cw) < cap:
        cw.append(pad[len(cw) % 2])
    return cw


def _codewords(data, version, level):
    """Split into blocks, add EC, interleave."""
    nec, nb = BLOCKS[level][version]
    short = len(data) // nb
    blocks, k = [], 0
    for i in range(nb):
        size = short + (1 if i >= nb - len(data) % nb else 0) if len(data) % nb else short
        blocks.append(data[k:k + size]); k += size
    ecs = [_rs(b, nec) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(nec):
        for e in ecs:
            out.append(e[i])
    return out


def _matrix(version):
    """Function patterns and a mask of reserved modules. Returns (grid, reserved)."""
    n = 17 + 4 * version
    g = [[0] * n for _ in range(n)]
    r = [[0] * n for _ in range(n)]

    def finder(x, y):
        for i in range(-1, 8):
            for j in range(-1, 8):
                if 0 <= x + i < n and 0 <= y + j < n:
                    v = 1 if (0 <= i <= 6 and 0 <= j <= 6 and (i in (0, 6) or j in (0, 6) or (2 <= i <= 4 and 2 <= j <= 4))) else 0
                    g[y + j][x + i] = v
                    r[y + j][x + i] = 1
    finder(0, 0); finder(n - 7, 0); finder(0, n - 7)
    for i in range(8, n - 8):
        g[6][i] = g[i][6] = 1 - i % 2
        r[6][i] = r[i][6] = 1
    if version >= 2:
        c = 4 * version + 10
        for i in range(-2, 3):
            for j in range(-2, 3):
                g[c + j][c + i] = 1 if (abs(i) == 2 or abs(j) == 2 or (i == 0 and j == 0)) else 0
                r[c + j][c + i] = 1
    g[4 * version + 9][8] = 1
    r[4 * version + 9][8] = 1
    for i in range(9):          # format info around the top-left finder
        if i != 6:
            r[8][i] = r[i][8] = 1
    for i in range(8):          # its second copy: row 8 on the right, column 8 at the bottom
        r[8][n - 1 - i] = 1
        r[n - 1 - i][8] = 1
    return g, r


def _place(g, r, cw):
    n = len(g)
    bits = []
    for c in cw:
        for k in range(7, -1, -1):
            bits.append((c >> k) & 1)
    i, up, col = 0, True, n - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if up else range(n)
        for row in rows:
            for dx in (0, 1):
                x = col - dx
                if not r[row][x]:
                    g[row][x] = bits[i] if i < len(bits) else 0
                    i += 1
        up = not up
        col -= 2


def _mask(g, r, m):
    n = len(g)
    out = [row[:] for row in g]
    for i in range(n):
        for j in range(n):
            if r[i][j]:
                continue
            if m == 0: f = (i + j) % 2 == 0
            elif m == 1: f = i % 2 == 0
            elif m == 2: f = j % 3 == 0
            elif m == 3: f = (i + j) % 3 == 0
            elif m == 4: f = (i // 2 + j // 3) % 2 == 0
            elif m == 5: f = (i * j) % 2 + (i * j) % 3 == 0
            elif m == 6: f = ((i * j) % 2 + (i * j) % 3) % 2 == 0
            else: f = ((i + j) % 2 + (i * j) % 3) % 2 == 0
            if f:
                out[i][j] ^= 1
    return out


def _format(g, level, m):
    n = len(g)
    v = (LEVEL_BITS[level] << 3) | m
    f = v << 10
    for i in range(14, 9, -1):
        if f >> i & 1:
            f ^= 0x537 << (i - 10)
    f = ((v << 10) | f) ^ 0x5412
    bits = [(f >> i) & 1 for i in range(14, -1, -1)]
    # around the top-left finder
    pos = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8), (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for (row, col), b in zip(pos, bits):
        g[row][col] = b
    # split copy: bottom-left column 8 and top-right row 8
    for k in range(7):
        g[n - 1 - k][8] = bits[k]
    for k in range(7, 15):
        g[8][n - 15 + k] = bits[k]


def _penalty(g):
    n = len(g)
    p = 0
    for lines in (g, [[g[i][j] for i in range(n)] for j in range(n)]):
        for line in lines:
            run, prev = 0, -1
            for v in line:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prev = 1, v
            if run >= 5:
                p += run - 2
            s = "".join("1" if v else "0" for v in line)
            p += 40 * (s.count("10111010000") + s.count("00001011101"))
    for i in range(n - 1):
        for j in range(n - 1):
            if g[i][j] == g[i][j + 1] == g[i + 1][j] == g[i + 1][j + 1]:
                p += 3
    dark = sum(sum(row) for row in g)
    k = abs(dark * 100 // (n * n) - 50) // 5
    return p + 10 * k


def encode(text, level="L", max_version=6, mask=None):
    """(n, rows) for the smallest version that fits, best mask by penalty (or `mask`, for tests)."""
    for version in range(1, max_version + 1):
        data = _bits(text, version, level)
        if data is not None:
            break
    else:
        raise ValueError("too long for version %d" % max_version)
    cw = _codewords(data, version, level)
    base, reserved = _matrix(version)
    _place(base, reserved, cw)
    best, best_p = None, None
    for m in (range(8) if mask is None else (mask,)):
        g = _mask(base, reserved, m)
        _format(g, level, m)
        p = _penalty(g)
        if best_p is None or p < best_p:
            best, best_p = g, p
    n = len(best)
    rows = []
    for row in best:
        bits = 0
        for c, v in enumerate(row):
            if v:
                bits |= 1 << c
        rows.append(bits)
    return n, rows
