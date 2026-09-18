# The one-way doors get a moment, not a menu line. Each ceremony is a handful of frames drawn
# synchronously right after the chip has done the permanent thing, before the SEALED / DONE screen:
#   rules_sealed(ui)          LOCK CONFIG: the CONFIG strip on the die pulses, a flash, the lock closes
#   key_created(ui, slot, fp) NEW KEY: noise settles into the key icon and the new fingerprint
#   sealed(ui, title, sub)    LOCK SLOT / LOCK DATA ZONE: the padlock closes
# About ten frames of ~60 ms each; a full show() is 38 ms, so nothing here is long.
import time
import os
import lcd as L
import theme as T
import icons as I
import chipmap as C


def _hold(d, ms=60):
    d.show()
    time.sleep_ms(ms)


def rules_sealed(ui):
    d = ui.d
    for f in range(4):
        d.fill(L.BLACK)
        C.header(ui, "SEALING")
        C.draw_die(d, ui, 20, 28, 200, 140, sel="cfg", pulse=T.C["perm"] if f % 2 == 0 else T.C["white"])
        d.center_text("the rules are being sealed", 184, L.WHITE)
        _hold(d, 70)
    d.fill(L.WHITE)
    _hold(d, 40)
    for f in range(3):
        d.fill(L.BLACK)
        C.header(ui, "SEALED")
        C.draw_die(d, ui, 20, 28, 200, 140, sel="cfg", pulse=T.C["safe"], locked=True)
        I.draw(d, "lock", 104, 172, T.C["safe"], 2)
        if f > 0:
            d.center_text("RULES SEALED", 208, T.C["safe"], 2)
        _hold(d, 90)
    d.center_text("never to change again", 226, L.GREY)
    _hold(d, 400)


def key_created(ui, slot, fp):
    d = ui.d
    x, y, w, h = 64, 60, 112, 92
    for f in range(8):
        d.fill(L.BLACK)
        C.header(ui, "MAKING A KEY")
        d.fill_rect(x, y, w, h, T.C["ink"])
        d.rect(x, y, w, h, T.C["learn"])
        # noise from the chip's own randomness, thinning out as the key settles
        n = 140 - f * 18
        for _ in range(max(0, n)):
            r = os.urandom(3)
            d.fill_rect(x + 2 + r[0] % (w - 6), y + 2 + r[1] % (h - 6), 3, 3,
                        T.C["learn"] if r[2] & 1 else T.C["dim"])
        if f >= 3:
            I.draw(d, "key", x + w // 2 - 16, y + 12, T.C["learn"], 2)
        if f >= 5:
            d.center_text("slot %d" % slot, y + 52, L.WHITE)
            d.center_text(fp, y + 66, T.C["learn"])
        d.center_text("drawn from the chip's RNG", 170, L.GREY)
        _hold(d, 60)
    d.center_text("KEY CREATED", 196, T.C["learn"], 2)
    _hold(d, 500)


def sealed(ui, title, sub):
    d = ui.d
    for f in range(4):
        d.fill(L.BLACK)
        C.header(ui, "SEALING")
        I.draw(d, "unlock" if f < 2 else "lock", 104, 70, T.C["perm"] if f < 2 else T.C["safe"], 2)
        if f >= 2:
            d.center_text(title, 120, T.C["safe"], 2)
        _hold(d, 120)
    d.center_text(sub, 150, L.GREY)
    _hold(d, 400)
