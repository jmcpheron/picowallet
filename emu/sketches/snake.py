# snake: the flip-phone classic for the Pico wallet. Joystick steers, A starts, B or the joystick
# press pauses, X quits (into the mock wallet, see EXIT_TO). Walls kill. Every 5th food a bonus bug
# appears for a while with a countdown top right, worth countdown x 10. High score lives in snake.hi.
# Emulator: tools/emu run snake     Pico: tools/emu ship snake   (or mpremote cp + exec 'import snake')
# Runs from a 30 ms Timer so the REPL stays free. Testing over the REPL: snake.inject("left"),
# snake.snap() writes the screen to shot.bin.
import time, random, gc
from machine import Timer
from lcd import LCD, Keys, color

lcd = LCD()
keys = Keys()
timer = None

BG = color(196, 232, 200)     # the backlit green of the old Nokia panel
INK = color(40, 56, 40)       # its pixels
CELL = 10
COLS, ROWS = 22, 20           # 220 x 200 field
OX, OY = 10, 30               # field origin on the screen
HI_FILE = "snake.hi"
START_MS, MIN_MS, STEP_MS = 200, 80, 8
BONUS_EVERY, BONUS_MOVES = 5, 30
EXIT_TO = "mock"              # module to start when X quits; None for a blank screen

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
ms = START_MS
next_t = 0
blink = 0
fake = []                     # key names pushed by inject(), read by tick like real presses


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


def free_cell(width=1):
    """A random empty cell; with width 2 the cell to its right is empty too."""
    for _ in range(500):
        r = random.randrange(ROWS)
        c = random.randrange(COLS - width + 1)
        i = r * COLS + c
        if not taken(i) and (width == 1 or not taken(i + 1)):
            return i
    return -1


def reset():
    global body, heading, queue, food, bonus, bonus_left, eaten, score, ms, next_t
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
    food = free_cell()
    eaten = 0
    score = 0
    ms = START_MS
    next_t = time.ticks_add(time.ticks_ms(), ms)


def turn(k):
    d = DIRS[k]
    last = queue[-1] if queue else heading
    if d == last or (d[0] == -last[0] and d[1] == -last[1]):
        return
    if len(queue) < 2:
        queue.append(d)


def die():
    global state, blink, next_t
    state = "dead"
    blink = 6
    next_t = time.ticks_add(time.ticks_ms(), 120)
    save_hi()


def move():
    global heading, food, bonus, bonus_left, eaten, score, ms, hi
    if queue:
        heading = queue.pop(0)
    head = body[-1]
    c = head % COLS + heading[0]
    r = head // COLS + heading[1]
    if c < 0 or c >= COLS or r < 0 or r >= ROWS:
        return die()
    i = r * COLS + c
    ate = i == food
    got = bonus >= 0 and (i == bonus or i == bonus + 1)
    if not ate and not got:
        grid[body.pop(0)] = 0           # tail moves first, so chasing it is allowed
    if grid[i]:
        return die()
    body.append(i)
    grid[i] = 1
    if ate:
        eaten += 1
        score += 10
        food = -1
        food = free_cell()
        ms = max(MIN_MS, ms - STEP_MS)
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


def cell_xy(i):
    return OX + (i % COLS) * CELL, OY + (i // COLS) * CELL


def draw_border():
    lcd.rect(OX - 2, OY - 2, COLS * CELL + 4, ROWS * CELL + 4, INK)
    lcd.rect(OX - 1, OY - 1, COLS * CELL + 2, ROWS * CELL + 2, INK)


def draw_snake(cells, head_dir):
    for i in cells:
        x, y = cell_xy(i)
        lcd.fill_rect(x + 1, y + 1, CELL - 2, CELL - 2, INK)
    x, y = cell_xy(cells[-1])
    lcd.fill_rect(x, y, CELL, CELL, INK)
    dx, dy = head_dir
    if dx:
        ex = x + (6 if dx > 0 else 2)
        lcd.fill_rect(ex, y + 2, 2, 2, BG)
        lcd.fill_rect(ex, y + 6, 2, 2, BG)
    else:
        ey = y + (6 if dy > 0 else 2)
        lcd.fill_rect(x + 2, ey, 2, 2, BG)
        lcd.fill_rect(x + 6, ey, 2, 2, BG)


def draw_field(show_snake=True):
    lcd.fill(BG)
    lcd.big_text("%04d" % score, OX, 7, INK, 2)
    if bonus >= 0:
        lcd.big_text("%02d" % bonus_left, 198, 7, INK, 2)
    else:
        lcd.text("HI %04d" % hi, 174, 11, INK)
    draw_border()
    if food >= 0:
        x, y = cell_xy(food)
        lcd.rect(x + 2, y + 2, 6, 6, INK)
        lcd.fill_rect(x + 4, y + 4, 2, 2, INK)
    if bonus >= 0:
        x, y = cell_xy(bonus)
        lcd.ellipse(x + 10, y + 5, 6, 3, INK, True)
        for lx in (x + 3, x + 15):
            lcd.fill_rect(lx, y + 1, 2, 2, INK)
            lcd.fill_rect(lx, y + 7, 2, 2, INK)
    if show_snake and body:
        draw_snake(body, heading)


def box(w, h):
    x, y = (240 - w) // 2, (240 - h) // 2
    lcd.fill_rect(x, y, w, h, BG)
    lcd.rect(x, y, w, h, INK)
    lcd.rect(x + 2, y + 2, w - 4, h - 4, INK)
    return y


def draw_title():
    lcd.fill(BG)
    draw_border()
    lcd.center_text("SNAKE", 56, INK, 4)
    r = 11
    draw_snake([r * COLS + c for c in range(5, 12)], (1, 0))
    x, y = cell_xy(r * COLS + 15)
    lcd.rect(x + 2, y + 2, 6, 6, INK)
    lcd.fill_rect(x + 4, y + 4, 2, 2, INK)
    lcd.center_text("A  start", 166, INK)
    lcd.center_text("HI %04d" % hi, 184, INK)
    lcd.center_text("stick steer B pause X quit", 210, INK)


def draw():
    if state == "title":
        draw_title()
    elif state == "play":
        draw_field()
    elif state == "pause":
        draw_field()
        y = box(120, 40)
        lcd.center_text("PAUSED", y + 12, INK, 2)
    elif state == "dead":
        draw_field(blink % 2 == 0)
    else:
        draw_field()
        y = box(180, 96)
        lcd.center_text("GAME OVER", y + 12, INK, 2)
        lcd.center_text("SCORE %04d" % score, y + 44, INK)
        lcd.center_text("HI %04d" % hi, y + 58, INK)
        lcd.center_text("A again   X quit", y + 78, INK)
    lcd.show()


def tick(_):
    global state, blink, next_t
    ks = keys.pressed()
    if fake:
        ks = ks + fake
        del fake[:]
    for k in ks:
        if k == "X":
            stop()
            return
        if state in ("title", "over"):
            if k == "A" or k in DIRS:
                reset()
                state = "play"
                if k in DIRS:
                    turn(k)
                draw()
        elif state == "play":
            if k in DIRS:
                turn(k)
            elif k in ("B", "press"):
                state = "pause"
                draw()
        elif state == "pause":
            if k in ("B", "press", "A"):
                state = "play"
                next_t = time.ticks_add(time.ticks_ms(), ms)
                draw()
    now = time.ticks_ms()
    if state == "play" and time.ticks_diff(now, next_t) >= 0:
        move()
        next_t = time.ticks_add(now, ms)
        draw()
    elif state == "dead" and time.ticks_diff(now, next_t) >= 0:
        blink -= 1
        if blink <= 0:
            state = "over"
        else:
            next_t = time.ticks_add(now, 120)
        draw()


def inject(*names):
    """Queue key presses for the next tick, e.g. snake.inject("A", "up")."""
    fake.extend(names)


def snap(path="shot.bin"):
    """Save the framebuffer to flash so the Mac can pull it."""
    with open(path, "wb") as f:
        f.write(lcd.buffer)


def start():
    global timer, hi, saved_hi, state
    hi = saved_hi = load_hi()
    random.seed(time.ticks_us())
    state = "title"
    draw()
    timer = Timer(period=30, mode=Timer.PERIODIC, callback=tick)
    print("snake: A starts, joystick steers, B pauses, X quits")


def stop():
    global state
    if timer:
        timer.deinit()
    state = "title"
    print("snake stopped")
    if not EXIT_TO:
        lcd.fill(BG)
        lcd.show()
        return
    try:
        import sys
        gc.collect()
        m = sys.modules.get(EXIT_TO)
        if m:
            m.start()
        else:
            __import__(EXIT_TO)
    except Exception as e:
        print("could not start", EXIT_TO, e)
        lcd.fill(BG)
        lcd.show()


start()
