# Boot screen: a navy gradient, a chip die whose legs chase through the zone colours while a step
# waits, the name with an underline that fills as the four steps complete, and a checklist with an
# icon per step (screen, wifi, chip, app). boot.py starts it before WiFi so the join is visible;
# wallet.start() keeps the same LCD, adds the chip and app rows, shows it a moment longer, then
# hands over to the home screen. Same API as before: begin, step, spin, wifi_row, draw.
import time
import lcd as L
import theme as T
import icons as I

lcd = None
rows = []           # [key, text, color], drawn in ORDER
ORDER = ("screen", "wifi", "chip", "app")
ICON = {"screen": "screen", "wifi": "wifi", "chip": "chip", "app": "app"}
_t0 = 0
_frame = 0
_last = 0
_waiting = None     # the row that is spinning, if any


def begin():
    """The LCD, created once. Safe to call again: returns the same one."""
    global lcd, _t0
    if lcd is None:
        lcd = L.LCD()
        _t0 = time.ticks_ms()
        step("screen", "ok", L.GREEN)
    return lcd


def step(key, text, color=L.WHITE):
    """Set a row (rows appear in ORDER as they are first set) and redraw."""
    global _waiting
    for r in rows:
        if r[0] == key:
            r[1], r[2] = text, color
            break
    else:
        rows.append([key, text, color])
        rows.sort(key=lambda r: ORDER.index(r[0]) if r[0] in ORDER else 9)
    if _waiting == key and color != L.GREY:
        _waiting = None
    draw()


def spin(key, text):
    """A row that is waiting: call it as often as you like, it redraws at most ~8 times a second."""
    global _last, _waiting
    now = time.ticks_ms()
    if time.ticks_diff(now, _last) < 120:
        return
    _last = now
    _waiting = key
    step(key, text, L.GREY)


def wifi_row(wlan, ssid):
    if wlan.isconnected():
        step("wifi", wlan.ifconfig()[0], L.GREEN)
    else:
        step("wifi", "not joined" if ssid else "no secrets.py", L.RED)


def draw():
    """One frame. Each call advances the leg chase, so a periodic redraw animates it."""
    global _frame
    if lcd is None:
        return
    _frame += 1
    d = lcd
    T.gradient(d, 0, 240, T.RGB["navy"], T.RGB["bg"])
    # the die: 48 px body, 8 legs a side, one colour of the rainbow per leg walking round
    cx, cy = 120, 42
    if _waiting:
        r = 34 + (_frame % 3) * 2
        d.ellipse(cx, cy, r, r, T.shade("config", 0.5))
    d.fill_rect(cx - 24, cy - 24, 48, 48, T.C["ink"])
    d.rect(cx - 24, cy - 24, 48, 48, T.C["chip"])
    d.fill_rect(cx - 18, cy - 18, 5, 5, T.C["learn"])
    I.draw(d, "chip", cx - 8, cy - 8, T.shade("chip", 0.6))
    for i in range(8):
        y = cy - 21 + i * 6
        left = T.C[T.RAINBOW[(_frame + i) % 7]] if _waiting or _frame < 40 else T.C["dim"]
        right = T.C[T.RAINBOW[(_frame + 15 - i) % 7]] if _waiting or _frame < 40 else T.C["dim"]
        d.fill_rect(cx - 33, y, 9, 3, left)
        d.fill_rect(cx + 24, y, 9, 3, right)
    d.center_text("picowallet", 76, L.WHITE, 2)
    done = sum(1 for r in rows if r[2] == L.GREEN)
    d.fill_rect(40, 96, 160, 3, T.C["ink"])
    d.fill_rect(40, 96, 40 * done, 3, T.C["learn"])
    y = 110
    for key, text, color in rows:
        I.draw(d, ICON.get(key, "chip"), 20, y - 4, color if color != L.GREY else T.C["config"])
        d.text(text[:24], 44, y, color)
        y += 20
    d.text("%.1fs" % (time.ticks_diff(time.ticks_ms(), _t0) / 1000), 4, 228, T.C["dim"])
    d.show()
