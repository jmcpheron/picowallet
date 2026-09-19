# PLAY SNAKE, in the LAB: the flip-phone classic, and a small honest lesson about randomness.
# Every press you make while the game is open goes into a pool (which key, how many 50 ms ticks
# since the last press, the microsecond clock). Every apple after the first is placed from a
# SHA-256 of that pool, so the game visibly runs on your own randomness. When a game ends, A
# shows the report on the LAB's answer screen: how many bits the presses were worth (NIST SP
# 800-90B's most common value rule on the gaps, with its small-sample bound), the pool digest,
# and how the chip's own Random compares. Nothing here becomes a key.
#
# High scores: a top-10 table with three-letter initials, kept in snake.top on the Pico and written
# into DATA slot 13 of the chip (72 bytes, the free clear slot under the wallet config; 12 is the
# note's). While the data zone is open the chip takes the table but refuses to read it back; after
# the data lock the chip's copy is read first and becomes the working copy. A chip write is a
# REVERSIBLE change and the initials box says so before A confirms it.
#
# A view of the chip UI (slots.py): draw(ui) and tick(ui, pressed) on the wallet's 50 ms timer,
# ui.n as the only clock, ui.d as the screen. During play the whole screen is the green panel.
# Keys: stick steers, A starts (and opens the report after a game), B or the stick press pauses,
# Y quits to the LAB. B and Y reach this view on press, not on release (slots.py skips arm_tick).
# The standalone version with its own Timer is emu/sketches/snake.py.
import time, math, hashlib, json
import lcd as L
import chipmap as C
import atecc

BG = L.color(196, 232, 200)   # the backlit green of the old Nokia panel
INK = L.color(40, 56, 40)     # its pixels
CELL = 10
COLS, ROWS = 22, 20           # 220 x 200 field
OX, OY = 10, 30               # field origin on the screen
HI_FILE = "snake.hi"          # the old single number; read once to seed the table
TOP_FILE = "snake.top"        # the table, JSON [[initials, score], ...] best first
TOP_N = 10
SLOT = 13                     # the chip's clear DATA slot the table goes into
MAGIC = b"SNK1"               # 4 + 10 x 6 = 64 bytes: two 32-byte blocks
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ-"
START_TICKS, MIN_TICKS = 4, 2 # a move every 200 ms at first, 100 ms at most; one tick is 50 ms
BONUS_EVERY, BONUS_MOVES = 5, 30
FIRST_FOOD = 6 * COLS + 15    # before any press there is nothing to draw from
FIXED = bytes([0xFF, 0xFF, 0x00, 0x00]) * 8   # what Random answers while the rules are open
KEYCODE = {"up": 1, "down": 2, "left": 3, "right": 4, "A": 5, "B": 6, "press": 7}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

state = "title"               # title, play, pause, dead, name, over, scores
body = []                     # cells as col + row * COLS, head last
grid = bytearray(COLS * ROWS)
heading = (1, 0)
queue = []                    # pending turns, at most 2
food = -1
bonus = -1                    # left cell of the bonus bug, -1 when none
bonus_left = 0
eaten = 0
score = 0
hi = 0
top = []                      # [[initials, score], ...] best first, at most TOP_N
initials = "AAA"              # the letters being entered (start from the last ones)
cursor = 0                    # which letter
rank = 0                      # the place the score is going into, 1-based
chip_note = ""                # what the chip did with the table, for the SCORES screen
chip_ok = None                # True written/read, False refused, None no chip or not tried
prev = "title"                # where the SCORES screen goes back to
_ui = None                    # the SlotsUI, for the chip and the slot table
next_n = 0                    # ui.n of the next move (or blink step)
blink = 0
play_ticks = 0                # ticks spent in play since the LAB row was opened
fake = []                     # key names pushed by inject(), read by tick like real presses

# the pool, since the LAB row was opened
pool = bytearray()
hist = [0] * 64               # how often each gap (in ticks, 63 = 3 s or more) came up
N = 0                         # gaps in the histogram: presses minus the first, which has none
presses = 0
last_n = 0


# ----------------------------------------------------------------------------- the pool
def sample(k, n):
    """One press: 7 bytes into the pool, one count into the gap histogram. No hashing here."""
    global N, presses, last_n, pool
    gap = n - last_n if last_n else 0
    if last_n:
        hist[min(gap, 63)] += 1     # the first press has nothing to be a gap from
        N += 1
    last_n = n
    presses += 1
    pool.append(KEYCODE[k])
    pool.append(gap >> 8 & 0xFF)
    pool.append(gap & 0xFF)
    pool.extend((time.ticks_us() & 0xFFFFFFFF).to_bytes(4, "little"))
    if len(pool) > 2048:
        pool = bytearray(hashlib.sha256(pool).digest())   # fold; N and hist keep counting


def digest():
    return hashlib.sha256(pool).digest()


def estimate():
    """Bits a press and in all, by the most common gap: (per, total, mode_gap, mode_count).
    NIST SP 800-90B most common value: -log2 of the 99% upper bound on the likeliest gap's share."""
    if N < 2:
        return 0.0, 0.0, (hist.index(1) if N else 0), N
    m = max(hist)
    g = hist.index(m)
    p = m / N
    pu = min(1.0, p + 2.576 * math.sqrt(p * (1 - p) / (N - 1)))
    per = 0.0 if pu >= 1.0 else -math.log(pu) / math.log(2)
    return per, min(256.0, per * N), g, m


def numbers():
    """For the REPL and the emulator: (presses, gaps, mode_gap, mode_count, bits_per_press, total_bits, digest_hex)."""
    per, total, g, m = estimate()
    return (presses, N, g, m, per, total, "".join("%02x" % b for b in digest()))


def reset_pool():
    global pool, N, presses, last_n, play_ticks
    pool = bytearray()
    for i in range(64):
        hist[i] = 0
    N = 0
    presses = 0
    last_n = 0
    play_ticks = 0


# ----------------------------------------------------------------------------- the game
# ----------------------------------------------------------------------------- the table
def load_top():
    """snake.top from flash; an old snake.hi seeds it once as '---'. hi is the top score."""
    global top, hi
    top = []
    try:
        top = [[str(a)[:3], int(b)] for a, b in json.load(open(TOP_FILE))][:TOP_N]
    except Exception:
        try:
            h = int(open(HI_FILE).read())
            if h > 0:
                top = [["---", h]]
        except Exception:
            pass
    hi = top[0][1] if top else 0


def save_top():
    global hi
    hi = top[0][1] if top else 0
    try:
        with open(TOP_FILE, "w") as f:
            json.dump(top, f)
    except Exception:
        pass


def pack_top(t):
    """The table as the 64 bytes slot 13 holds: MAGIC, then 6 bytes an entry (3 letters, score, pad)."""
    b = bytearray(MAGIC)
    for name, score in t[:TOP_N]:
        b += (name + "---")[:3].encode() + min(int(score), 65535).to_bytes(2, "little") + b"\x00"
    return bytes(b) + bytes(64 - len(b))


def unpack_top(b):
    """The table back from those bytes, or None when they are not a table."""
    b = bytes(b)
    if len(b) < 10 or b[:4] != MAGIC:
        return None
    t = []
    for i in range(4, len(b) - 5, 6):
        name, score = b[i:i + 3], b[i + 3] | b[i + 4] << 8
        if score == 0:
            break
        try:
            t.append([name.decode(), score])
        except Exception:
            return None
    return t


def qualifies(score):
    return score > 0 and (len(top) < TOP_N or score > top[-1][1])


def place(score):
    """1-based rank a score would take: after every entry that ties or beats it."""
    n = 0
    for _, s in top:
        if s >= score:
            n += 1
    return n + 1


def chip_slot(ui):
    """The chip, if the table can go there: config locked, slot 13's rules say clear and not secret."""
    chip = getattr(ui.sig, "chip", None)
    if chip is None or not ui.st.get("configLocked"):
        return None
    s = ui.row(SLOT)
    if s.get("clearWrite") != "clear" or s.get("isSecret"):
        return None
    return chip


def refused(ui, e):
    status = getattr(e, "status", None)
    if status is None:
        return "chip: %s" % e
    return "chip refused (0x%02X): %s" % (status, atecc.explain(status))


def chip_save(ui):
    """The table into slot 13, two 32-byte blocks. What happened goes to chip_note for the SCORES screen."""
    global chip_note, chip_ok
    chip = chip_slot(ui)
    if chip is None:
        chip_note, chip_ok = "kept on the Pico only: no clear data slot on the bus", None
        return
    b = pack_top(top)
    try:
        chip.write_data(SLOT, 0, b[:32])
        chip.write_data(SLOT, 1, b[32:])
        chip_ok = True
        if ui.st.get("dataLocked"):
            chip_note = "chip slot %d holds it: 64 bytes, written in clear" % SLOT
        else:
            chip_note = "chip slot %d holds it; it reads back after the data lock" % SLOT
    except Exception as e:
        chip_ok = False
        chip_note = refused(ui, e)


def chip_load(ui):
    """After the data lock the chip's copy is the working copy; before it the chip cannot answer."""
    global top, chip_note, chip_ok
    chip = chip_slot(ui)
    if chip is None:
        chip_note, chip_ok = "kept on the Pico only: no clear data slot on the bus", None
        return
    if not ui.st.get("dataLocked"):
        chip_note, chip_ok = "chip slot %d: written on each new score, read back after the data lock" % SLOT, None
        return
    try:
        t = unpack_top(chip.read_data(SLOT, 0) + chip.read_data(SLOT, 1))
    except Exception as e:
        chip_note, chip_ok = refused(ui, e), False
        return
    if t is None:
        chip_note, chip_ok = "chip slot %d holds no table yet; the next score writes one" % SLOT, None
    elif t == top:
        chip_note, chip_ok = "chip slot %d holds this table, read back in clear" % SLOT, True
    else:
        top = t[:TOP_N]
        save_top()
        chip_note, chip_ok = "chip slot %d held a different table; the chip's copy wins" % SLOT, True


def commit(ui, name):
    """A finished entry: into the table, to flash, to the chip."""
    global initials, state
    initials = name
    top.insert(place(score) - 1, [name, score])
    del top[TOP_N:]
    save_top()
    chip_save(ui)
    state = "over"


def taken(i):
    return grid[i] or i == food or (bonus >= 0 and (i == bonus or i == bonus + 1))


def fits(i, width):
    if width == 2 and i % COLS == COLS - 1:
        return False
    return not taken(i) and (width == 1 or not taken(i + 1))


def free_cell(width=1):
    """An empty cell drawn from the pool; with width 2 the cell to its right is empty too."""
    if N == 0 and eaten == 0:
        return FIRST_FOOD
    h = hashlib.sha256(pool + bytes([eaten & 0xFF, width])).digest()
    n = ROWS * COLS
    for j in range(0, 32, 2):
        i = (h[j] << 8 | h[j + 1]) % n
        if fits(i, width):
            return i
    i = (h[0] << 8 | h[1]) % n
    for _ in range(n):
        i = (i + 1) % n
        if fits(i, width):
            return i
    return -1


def period():
    return max(MIN_TICKS, START_TICKS - eaten // 5)


def reset(n):
    global body, heading, queue, food, bonus, bonus_left, eaten, score, next_n
    for i in range(len(grid)):
        grid[i] = 0
    r = ROWS // 2
    body = [r * COLS + c for c in range(8, 12)]   # 4 long, heading right
    for i in body:
        grid[i] = 1
    heading = (1, 0)
    queue = []
    food = -1
    bonus = -1
    bonus_left = 0
    eaten = 0
    score = 0
    food = free_cell()
    next_n = n + period()


def turn(k):
    d = DIRS[k]
    last = queue[-1] if queue else heading
    if d == last or (d[0] == -last[0] and d[1] == -last[1]):
        return
    if len(queue) < 2:
        queue.append(d)


def die(n):
    global state, blink, next_n
    state = "dead"
    blink = 6
    next_n = n + 2


def move(n):
    global heading, food, bonus, bonus_left, eaten, score, hi
    if queue:
        heading = queue.pop(0)
    head = body[-1]
    c = head % COLS + heading[0]
    r = head // COLS + heading[1]
    if c < 0 or c >= COLS or r < 0 or r >= ROWS:
        return die(n)
    i = r * COLS + c
    ate = i == food
    got = bonus >= 0 and (i == bonus or i == bonus + 1)
    if not ate and not got:
        grid[body.pop(0)] = 0           # tail moves first, so chasing it is allowed
    if grid[i]:
        return die(n)
    body.append(i)
    grid[i] = 1
    if ate:
        eaten += 1
        score += 10
        food = -1
        food = free_cell()
        if eaten % BONUS_EVERY == 0 and bonus < 0:
            bonus = free_cell(2)
            bonus_left = BONUS_MOVES
    if got:
        score += bonus_left * 10
        bonus = -1
    elif bonus >= 0:
        bonus_left -= 1
        if bonus_left <= 0:
            bonus = -1
    if score > hi:
        hi = score


# ----------------------------------------------------------------------------- drawing
def cell_xy(i):
    return OX + (i % COLS) * CELL, OY + (i // COLS) * CELL


def draw_border(d):
    d.rect(OX - 2, OY - 2, COLS * CELL + 4, ROWS * CELL + 4, INK)
    d.rect(OX - 1, OY - 1, COLS * CELL + 2, ROWS * CELL + 2, INK)


def draw_snake(d, cells, head_dir):
    for i in cells:
        x, y = cell_xy(i)
        d.fill_rect(x + 1, y + 1, CELL - 2, CELL - 2, INK)
    x, y = cell_xy(cells[-1])
    d.fill_rect(x, y, CELL, CELL, INK)
    dx, dy = head_dir
    if dx:
        ex = x + (6 if dx > 0 else 2)
        d.fill_rect(ex, y + 2, 2, 2, BG)
        d.fill_rect(ex, y + 6, 2, 2, BG)
    else:
        ey = y + (6 if dy > 0 else 2)
        d.fill_rect(x + 2, ey, 2, 2, BG)
        d.fill_rect(x + 6, ey, 2, 2, BG)


def draw_field(d, show_snake=True):
    d.fill(BG)
    d.big_text("%04d" % score, OX, 7, INK, 2)
    if bonus >= 0:
        d.big_text("%02d" % bonus_left, 198, 7, INK, 2)
    else:
        d.text("HI %04d" % hi, 174, 11, INK)
    draw_border(d)
    if food >= 0:
        x, y = cell_xy(food)
        d.rect(x + 2, y + 2, 6, 6, INK)
        d.fill_rect(x + 4, y + 4, 2, 2, INK)
    if bonus >= 0:
        x, y = cell_xy(bonus)
        d.ellipse(x + 10, y + 5, 6, 3, INK, True)
        for lx in (x + 3, x + 15):
            d.fill_rect(lx, y + 1, 2, 2, INK)
            d.fill_rect(lx, y + 7, 2, 2, INK)
    if show_snake and body:
        draw_snake(d, body, heading)


def box(d, w, h):
    x, y = (240 - w) // 2, (240 - h) // 2
    d.fill_rect(x, y, w, h, BG)
    d.rect(x, y, w, h, INK)
    d.rect(x + 2, y + 2, w - 4, h - 4, INK)
    return y


def draw_title(d):
    d.fill(BG)
    draw_border(d)
    d.center_text("SNAKE", 50, INK, 4)
    r = 10
    draw_snake(d, [r * COLS + c for c in range(5, 12)], (1, 0))
    x, y = cell_xy(r * COLS + 15)
    d.rect(x + 2, y + 2, 6, 6, INK)
    d.fill_rect(x + 4, y + 4, 2, 2, INK)
    d.center_text("every press feeds a pool", 150, INK)
    d.center_text("the apples come from it", 162, INK)
    d.center_text("A  start", 184, INK)
    d.center_text(("HI %04d %s     X scores" % (hi, top[0][0])) if top else "no scores yet    X scores", 198, INK)
    d.center_text("stick steer  B pause  Y quit", 214, INK)


def draw(ui):
    d = ui.d
    if state == "title":
        draw_title(d)
    elif state == "play":
        draw_field(d)
    elif state == "pause":
        draw_field(d)
        y = box(d, 120, 40)
        d.center_text("PAUSED", y + 12, INK, 2)
    elif state == "dead":
        draw_field(d, blink % 2 == 0)
    elif state == "name":
        draw_field(d)
        draw_name(d, ui)
    elif state == "scores":
        draw_scores(d)
    else:
        draw_field(d)
        y = box(d, 180, 96)
        d.center_text("GAME OVER", y + 12, INK, 2)
        d.center_text("SCORE %04d  HI %04d" % (score, hi), y + 40, INK)
        d.center_text("A report   B again", y + 60, INK)
        d.center_text("X scores   Y quit", y + 76, INK)


def draw_name(d, ui):
    """The arcade box: rank, score, three big letters with the cursor under one, and the class of
    what A will do (a chip write is a REVERSIBLE change; it says so before it happens)."""
    y = box(d, 220, 150)
    d.center_text("NEW HIGH SCORE  #%d" % rank, y + 10, INK)
    d.center_text("%04d" % score, y + 24, INK, 2)
    x0 = 120 - 66
    for i in range(3):
        x = x0 + i * 44 + 6
        d.big_text(initials[i], x, y + 50, INK, 4)
        if i == cursor:
            d.fill_rect(x, y + 86, 32, 3, INK)
    if chip_slot(ui):
        C.badge(d, "rev", 18, y + 100)
        d.text("REVERSIBLE: chip slot %d" % SLOT, 32, y + 100, INK)
        d.text("and the Pico's flash", 32, y + 112, INK)
    else:
        C.badge(d, "safe", 18, y + 100)
        d.text("kept on the Pico only", 32, y + 100, INK)
    d.center_text("up/dn  A next  Y skip", y + 132, INK)


def draw_scores(d):
    d.fill(BG)
    draw_border(d)
    d.center_text("HIGH SCORES", 30, INK, 2)
    y = 52
    for i in range(TOP_N):
        if i < len(top):
            d.text("#%2d  %s  %04d" % (i + 1, top[i][0], top[i][1]), 56, y, INK)
        else:
            d.text("#%2d  ---  ----" % (i + 1), 56, y, INK)
        y += 12
    y += 6
    for line in C.wrap(chip_note, 27)[:3]:
        d.text(line, 16, y, INK); y += 11
    d.center_text("Y back", 216, INK)


# ----------------------------------------------------------------------------- input
def enter(ui):
    """The LAB row: a fresh pool, the table from flash and the chip, the title screen. (Not named
    open: that would shadow the builtin this module reads its files with.)"""
    global state, _ui
    _ui = ui
    reset_pool()
    load_top()
    chip_load(ui)
    state = "title"
    ui.armhold = None
    ui.pend.clear()
    ui.go("snake")


def tick(ui, pressed):
    global state, blink, next_n, play_ticks, prev, cursor, rank
    n = ui.n
    ks = list(pressed)
    if fake:
        ks += fake
        del fake[:]
    for k in ks:
        if state == "scores":
            if k in ("Y", "X", "A", "B"):
                state = prev
                ui.dirty = True
            continue
        if k == "X" and state in ("title", "over"):
            prev, state = state, "scores"
            ui.dirty = True
            continue
        if state == "name":
            if k in KEYCODE:
                sample(k, n)
            name_key(ui, k)
            continue
        if k == "Y":
            ui.back()
            return
        if k not in KEYCODE:
            continue
        sample(k, n)
        if state == "title" or state == "over":
            if k == "A" or k in DIRS or (k == "B" and state == "over"):
                if k == "A" and state == "over":
                    report(ui)
                    return
                reset(n)
                state = "play"
                if k in DIRS:
                    turn(k)
                ui.dirty = True
        elif state == "play":
            if k in DIRS:
                turn(k)
            elif k == "B" or k == "press":
                state = "pause"
                ui.dirty = True
        elif state == "pause":
            if k in ("B", "press", "A"):
                state = "play"
                next_n = n + period()
                ui.dirty = True
    if state == "play":
        play_ticks += 1
        if n >= next_n:
            move(n)
            if state == "play":
                next_n = n + period()
            ui.dirty = True
    elif state == "dead" and n >= next_n:
        blink -= 1
        if blink <= 0:
            if qualifies(score):
                state, cursor, rank = "name", 0, place(score)
            else:
                state = "over"
        else:
            next_n = n + 2
        ui.dirty = True


def name_key(ui, k):
    """The initials box: up/down cycle the letter, left/right move, A next (the third A commits),
    Y skips and files the score as ---."""
    global initials, cursor
    if k == "up" or k == "down":
        i = LETTERS.index(initials[cursor]) if initials[cursor] in LETTERS else 0
        i = (i + (1 if k == "down" else -1)) % len(LETTERS)
        initials = initials[:cursor] + LETTERS[i] + initials[cursor + 1:]
    elif k == "left":
        cursor = max(0, cursor - 1)
    elif k == "right":
        cursor = min(2, cursor + 1)
    elif k == "A" or k == "press":
        if cursor < 2:
            cursor += 1
        else:
            commit(ui, initials)
    elif k == "Y":
        commit(ui, "---")
    ui.dirty = True


def inject(*names):
    """Queue key presses for the next tick, e.g. snakelab.inject("A", "up") from the REPL."""
    fake.extend(names)


# ----------------------------------------------------------------------------- the report
def report(ui):
    """The pool as a LAB answer: the count in words, the digest as the bytes, the method as WHY."""
    global state
    per, total, g, m = estimate()
    raw_total = per * N
    secs = play_ticks * 50 // 1000
    text = "%d presses in %d s. What you control is the gap between them: %d ticks came up %d of %d times, so about %.1f bits a press. " % (presses, secs, g, m, N, per)
    if N < 20:
        text += "Too few presses to trust the count."
    elif raw_total > 256:
        text += "Total ~%d bits, capped at 256 here." % raw_total
    elif total < 128:
        text += "~%d bits: not a key yet. Play longer." % total
    else:
        text += "~%d bits in all." % total
    chip = getattr(ui.sig, "chip", None)
    trace = None
    if chip is None:
        cmp = "There is no chip on the bus to compare with."
    else:
        try:
            r = chip.random()
            trace = chip.trace
            ms = trace["ms"] if trace else 25
            if r == FIXED:
                cmp = "The chip's Random took %d ms for 32 bytes: ffff0000 repeated, the test pattern of a chip whose rules are still open." % ms
            else:
                cmp = "The chip's Random took %d ms for 32 real bytes; you took %d s for about %d." % (ms, secs, total)
        except Exception as e:
            cmp = "The chip refused Random: %s." % e
    gaps = sorted(((hist[i], i) for i in range(64) if hist[i]), reverse=True)[:6]
    why = ("Smaller than it looks. Every press put 7 bytes in the pool: which key, how many 50 ms ticks since the last press, "
           "and the microsecond clock. Only the gap is counted. The key is what the game made you press; the clock is the "
           "wallet's timer, not you. Gaps are whole ticks, so there are at most 64 sizes: 6 bits a press is the ceiling and "
           "a person lands near 2. NIST SP 800-90B's most common value rule: if the likeliest gap has share p, a press is "
           "worth at most -log2(p) bits, and with few presses p is pushed up first (a 99%% bound). Here: gaps %s. "
           "%d gaps x %.1f = ~%d bits; SHA-256 keeps 256 at most. %s The first apple is always in the same place: "
           "you had not pressed anything yet. Every apple after it came from the hash of your presses so far, so no two "
           "games look alike. Nothing here becomes a key. A wallet key comes from the chip's generator, never from a game."
           % (" ".join("%dx%d" % (i, c) for c, i in gaps) or "none", N, per, raw_total, cmp))
    ui.lab = {"q": "PLAY SNAKE", "cmd": "make randomness yourself", "text": text, "raw": digest(), "why": why,
              "trace": trace, "icon": "snake", "whylabel": "HOW IT WAS COUNTED >"}
    state = "title"
    ui.ret, ui.view, ui.act2, ui.dirty = "snake", "labres", 0, True
