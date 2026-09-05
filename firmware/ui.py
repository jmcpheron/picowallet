# Demo screen: title, IP, and whatever key you press.
# Runs from a periodic Timer so main.py returns to the REPL. That matters: on rp2 the
# network console (os.dupterm) is only read while the REPL is idle, so a blocking
# main loop would make the board unreachable over WiFi.
import time, network, machine
import lcd as L

d = None
keys = None
timer = None
last = "press a key"
count = 0
dirty = True
err = None
_busy = False


def draw():
    d.fill(L.BLACK)
    d.fill_rect(0, 0, 240, 28, L.DARK)
    d.center_text("picowallet", 6, L.YELLOW, 2)
    d.center_text(ip, 40, L.GREY)
    d.center_text(last, 100, L.WHITE, 4 if len(last) <= 7 else 3)
    d.center_text("presses: %d" % count, 160, L.GREY)
    d.text("A", 224, 60, L.GREEN); d.text("B", 224, 110, L.GREEN)
    d.text("X", 224, 160, L.GREEN); d.text("Y", 224, 210, L.GREEN)
    d.show()


def tick(t):
    global last, count, dirty, err, _busy
    if _busy:
        return
    _busy = True
    try:
        for k in keys.pressed():
            last = k
            count += 1
            dirty = True
        if dirty:
            draw()
            dirty = False
    except Exception as e:
        err = e
    finally:
        _busy = False


def start(period_ms=30):
    global d, keys, timer, ip
    d = L.LCD()
    keys = L.Keys()
    ip = network.WLAN(network.STA_IF).ifconfig()[0]
    draw()
    timer = machine.Timer(period=period_ms, mode=machine.Timer.PERIODIC, callback=tick)


def stop():
    if timer:
        timer.deinit()
