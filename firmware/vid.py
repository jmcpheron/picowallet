# Play a .pv file (see tools/gif2pv) full screen. 120x120 frames are pixel-doubled to 240.
# vid.play('earth.pv')  loops until X is pressed; prints fps.
import time, struct, machine, micropython
from machine import Pin, SPI
from lcd import LCD, KEYS

lcd = LCD()
_x = Pin(KEYS["X"], Pin.IN, Pin.PULL_UP)


def fast_spi(baud=75_000_000):
    """MicroPython leaves the peripheral clock at 48 MHz, which caps SPI at 24. Re-derive it."""
    machine.freq(150_000_000, 150_000_000)
    lcd.spi = SPI(1, baud, polarity=0, phase=0, sck=Pin(10), mosi=Pin(11), miso=None)


@micropython.viper
def _blit2x(buf: ptr8, src: ptr8, pal: ptr8, w: int, h: int):
    for y in range(h):
        row = y * w
        o = y * 960
        for x in range(w):
            v = int(src[row + x]) << 1
            hi = pal[v]; lo = pal[v + 1]
            buf[o] = hi; buf[o + 1] = lo; buf[o + 2] = hi; buf[o + 3] = lo
            buf[o + 480] = hi; buf[o + 481] = lo; buf[o + 482] = hi; buf[o + 483] = lo
            o += 4


@micropython.viper
def _blit1x(buf: ptr8, src: ptr8, pal: ptr8, n: int):
    o = 0
    for i in range(n):
        v = int(src[i]) << 1
        buf[o] = pal[v]; buf[o + 1] = pal[v + 1]
        o += 2


def play(path, loop=True, baud=75_000_000):
    if baud:
        fast_spi(baud)
    f = open(path, "rb")
    hdr = f.read(12)
    assert hdr[:3] == b"PV1", "not a .pv file"
    w, h, n, ms = struct.unpack("<HHHH", hdr[4:])
    pal = f.read(512)
    frame = bytearray(w * h)
    start = f.tell()
    frames = 0; t0 = time.ticks_ms()
    print("%dx%d, %d frames, %d ms/frame" % (w, h, n, ms))
    while True:
        for _ in range(n):
            t = time.ticks_ms()
            f.readinto(frame)
            if w == 120:
                _blit2x(lcd.buffer, frame, pal, w, h)
            else:
                _blit1x(lcd.buffer, frame, pal, w * h)
            lcd.show()
            frames += 1
            if _x.value() == 0:
                fps = frames * 1000 // time.ticks_diff(time.ticks_ms(), t0)
                print("stopped, %d fps" % fps)
                return fps
            while time.ticks_diff(time.ticks_ms(), t) < ms:
                pass
        fps = frames * 1000 // time.ticks_diff(time.ticks_ms(), t0)
        if not loop:
            print("%d fps" % fps)
            return fps
        f.seek(start)
