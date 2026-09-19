# PLAY SNAKE, in the LAB: the flip-phone classic, and a small honest lesson about randomness.
# Every press you make while the game is open goes into a pool (which key, how many 50 ms ticks
# since the last press, the microsecond clock). Every apple after the first is placed from a
# SHA-256 of that pool, so the game visibly runs on your own randomness. When a game ends, A
# shows the report on the LAB's answer screen: how many bits the presses were worth (NIST SP
# 800-90B's most common value rule on the gaps, with its small-sample bound), the pool digest,
# and how the chip's own Random compares. Nothing here becomes a key.
#
# A view of the chip UI (slots.py): draw(ui) and tick(ui, pressed) on the wallet's 50 ms timer,
# ui.n as the only clock, ui.d as the screen. During play the whole screen is the green panel.
# Keys: stick steers, A starts (and opens the report after a game), B or the stick press pauses,
# Y quits to the LAB. B and Y reach this view on press, not on release (slots.py skips arm_tick).
# The standalone version with its own Timer is emu/sketches/snake.py.
import time, math, hashlib
import lcd as L
import chipmap as C

BG = L.color(196, 232, 200)   # the backlit green of the old Nokia panel
INK = L.color(40, 56, 40)     # its pixels
CELL = 10
COLS, ROWS = 22, 20           # 220 x 200 field
OX, OY = 10, 30               # field origin on the screen
HI_FILE = "snake.hi"
START_TICKS, MIN_TICKS = 4, 2 # a move every 200 ms at first, 100 ms at most; one tick is 50 ms
BONUS_EVERY, BONUS_MOVES = 5, 30
FIRST_FOOD = 6 * COLS + 15    # before any press there is nothing to draw from
FIXED = bytes([0xFF, 0xFF, 0x00, 0x00]) * 8   # what Random answers while the rules are open
KEYCODE = {"up": 1, "down": 2, "left": 3, "right": 4, "A": 5, "B": 6, "press": 7}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

state = "title"               # title, play, pause, dead, over
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
saved_hi = 0
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
def load_hi():
    try:
        with open(HI_FILE) as f:
            return int(f.read())
    except Exception:
        return 0


def save_hi():
    global saved_hi
    if hi <= saved_hi:
        return
    try:
        with open(HI_FILE, "w") as f:
            f.write(str(hi))
        saved_hi = hi
    except Exception:
        pass


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
    save_hi()


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
    d.center_text("HI %04d" % hi, 198, INK)
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
    else:
        draw_field(d)
        y = box(d, 180, 96)
        d.center_text("GAME OVER", y + 12, INK, 2)
        d.center_text("SCORE %04d  HI %04d" % (score, hi), y + 40, INK)
        d.center_text("A report   B again", y + 60, INK)
        d.center_text("Y quit", y + 76, INK)


# ----------------------------------------------------------------------------- input
def open(ui):
    """The LAB row: a fresh pool, the high score from flash, the title screen."""
    global state, hi, saved_hi
    reset_pool()
    hi = saved_hi = load_hi()
    state = "title"
    ui.armhold = None
    ui.pend.clear()
    ui.go("snake")


def tick(ui, pressed):
    global state, blink, next_n, play_ticks
    n = ui.n
    ks = list(pressed)
    if fake:
        ks += fake
        del fake[:]
    for k in ks:
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
            state = "over"
        else:
            next_n = n + 2
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
