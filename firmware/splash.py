# Boot screen: a chip icon, the name, and a checklist that fills in as the board comes up (screen,
# wifi, chip, app). While a step waits the icon's legs light up one after another. boot.py starts
# it before WiFi so the join is visible; wallet.start() keeps the same LCD, adds the chip and app
# rows, shows it a moment longer, then hands over to the home screen.
import time
import lcd as L

lcd = None
rows = []           # [key, text, color], drawn in ORDER
ORDER = ("screen", "wifi", "chip", "app")
_t0 = 0
_frame = 0
_last = 0


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
    for r in rows:
        if r[0] == key:
            r[1], r[2] = text, color
            break
    else:
        rows.append([key, text, color])
        rows.sort(key=lambda r: ORDER.index(r[0]) if r[0] in ORDER else 9)
    draw()


def spin(key, text):
    """A row that is waiting: call it as often as you like, it redraws at most ~8 times a second."""
    global _last
    now = time.ticks_ms()
    if time.ticks_diff(now, _last) < 120:
        return
    _last = now
    step(key, text, L.GREY)


def wifi_row(wlan, ssid):
    if wlan.isconnected():
        step("wifi", wlan.ifconfig()[0], L.GREEN)
    else:
        step("wifi", "not joined" if ssid else "no secrets.py", L.RED)


def draw():
    """One frame. Each call advances the leg animation, so a periodic redraw animates it."""
    global _frame
    if lcd is None:
        return
    _frame += 1
    d = lcd
    d.fill(L.BLACK)
    # the chip: a dark square, eight legs, a dot at pin 1; one leg lit per frame, walking round
    cx, cy = 120, 34
    d.fill_rect(cx - 18, cy - 18, 36, 36, L.DARK)
    d.rect(cx - 18, cy - 18, 36, 36, L.GREY)
    d.fill_rect(cx - 13, cy - 13, 4, 4, L.YELLOW)
    lit = _frame % 8
    for i in range(4):
        y = cy - 12 + i * 8
        d.fill_rect(cx - 27, y, 9, 3, L.YELLOW if lit == i else L.GREY)            # left, top to bottom
        d.fill_rect(cx + 18, y, 9, 3, L.YELLOW if lit == 7 - i else L.GREY)        # right, bottom to top
    d.center_text("picowallet", 62, L.WHITE, 2)
    y = 100
    for key, text, color in rows:
        d.text(key, 24, y, L.GREY)
        d.text(text[:20], 80, y, color)
        y += 16
    d.text("%.1fs" % (time.ticks_diff(time.ticks_ms(), _t0) / 1000), 4, 228, L.GREY)
    d.show()
