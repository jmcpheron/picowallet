# CHIP MAP: the ATECC608 as a place you can walk through. The chip's real structure (CONFIG 128 B,
# DATA 16 slots of 36/416/72 B, OTP 64 B, two COUNTERS), a breadcrumb that says where you are, the
# CONFIG page with its snapshot and the reversible write flow, the pages that read OTP and counters,
# and the screen the chip's refusals land on: the reason first, the raw status second.
#
# Every action carries a class, shown by colour AND a glyph AND words, never colour alone:
#   o SAFE TO EXPLORE: changes nothing      ~ REVERSIBLE CHANGE: can be restored
#   ! PERMANENT: cannot be undone
# ARM is the wallet's own safety catch, not a chip feature, so it lives in the header, not on the
# map: hold B and Y together 3 s and permanent actions are armed for a minute (signer.arm).
# These functions take the SlotsUI object (slots.py) and draw on ui.d; the state machine is there.
import time
import lcd as L
import signer as S
import atecc
import theme as T
import icons as I

CLASS = {"safe": ("o", T.C["safe"], "SAFE TO EXPLORE: no changes"),
         "rev": ("~", T.C["rev"], "REVERSIBLE: can be restored"),
         "perm": ("!", T.C["perm"], "PERMANENT: cannot be undone")}
KIND_COLOR = {"P256": T.C["learn"], "PUB": T.C["config"], "AES": T.C["counters"], "DATA": T.C["grey"], "?": T.C["dim"]}
KIND_ICON = {"P256": "key", "PUB": "pub", "AES": "aes", "DATA": "bytes", "?": "bytes"}
ARM_HOLD_MS = 3000
DIM = L.color(90, 90, 100)
NAMES = {"zones": "CHIP", "list": "DATA", "cfg": "CONFIG", "raw": "RAW", "diff": "DIFF", "otp": "OTP",
         "counters": "COUNTERS", "lab": "LAB", "learn": "LEARN", "labres": "ANSWER", "why": "WHY",
         "rawcmd": "RAW", "refused": "REFUSED", "confirm": "PERMANENT", "confirm_write": "WRITE",
         "result": "RESULT", "busy": "...", "pubkey": "PUBKEY"}


# ----------------------------------------------------------------------------- text and chrome
def wrap(s, w=29):
    """Word-wrap into lines of at most w characters (the 8x8 font gives 29 per row at x=4)."""
    out, line = [], ""
    for word in s.split(" "):
        while len(word) > w:
            if line:
                out.append(line); line = ""
            out.append(word[:w]); word = word[w:]
        if len(line) + len(word) + (1 if line else 0) > w:
            out.append(line); line = word
        else:
            line = line + " " + word if line else word
    if line:
        out.append(line)
    return out


def crumb(ui, limit=22):
    """Where you are: CHIP > DATA > SLOT 3. Long trails lose their head, never their tail."""
    parts = []
    for v, _, _ in ui.stack + [(ui.view, 0, 0)]:
        if v == "slot":
            parts.append("SLOT %d" % ui.cur)
        elif v == "card" and ui.card is not None:
            parts.append("%d" % (ui.card + 1))
        elif v in NAMES:
            parts.append(NAMES[v])
    s = " > ".join(parts)
    while len(s) > limit and len(parts) > 1:
        parts.pop(0)
        s = ".. " + " > ".join(parts)
    return s


def header(ui, text=None):
    """One line in the bar: the breadcrumb left, the wallet's ARM state right."""
    d = ui.d
    d.fill_rect(0, 0, 240, 22, T.shade(T.zone_of(ui.view), 0.35))
    left = S.armed()
    arm = ("! ARMED %ds" % left) if left else "SAFE o"
    d.text(text[:28 - len(arm)] if text is not None else crumb(ui, 28 - len(arm)), 4, 7, L.WHITE)
    d.text(arm, 236 - 8 * len(arm), 7, L.RED if left else L.GREEN)


def footer(ui, text, color=L.GREY):
    ui.d.fill_rect(0, 226, 240, 14, L.DARK)
    ui.d.text(text[:29], 4, 229, color)


def icon(d, name, x, y, c, scale=1):
    """A 16 px bitmap from icons.py in colour c: check, cross, warn, lock, unlock, key, ..."""
    I.draw(d, name, x, y, c, scale)


def badge(d, cls, x, y):
    """The class as a small filled square with its glyph: o safe, ~ reversible, ! permanent."""
    glyph, color, _ = CLASS[cls]
    d.fill_rect(x, y - 1, 10, 10, color)
    d.text(glyph, x + 1, y, L.BLACK)


def menu(ui, items, y, sel):
    """Rows of (kind, label, cls, off). Glyph in the class colour, label white (yellow when picked,
    dim when off). Returns the next y. The footer words come from menu_footer."""
    d = ui.d
    zone = T.C[T.zone_of(ui.view)]
    for i, (kind, label, cls, off) in enumerate(items):
        if i == sel:
            d.fill_rect(0, y - 2, 240, 13, T.C["ink"])
            d.fill_rect(0, y - 2, 3, 13, zone)
        badge(d, cls, 10, y)
        d.text(label[:26], 26, y, DIM if off else (L.YELLOW if i == sel else L.WHITE))
        y += 14
    return y


def menu_footer(ui, items, sel):
    if not items:
        footer(ui, "Y back")
        return
    kind, label, cls, off = items[sel]
    if off:
        footer(ui, ("off: " + off)[:29], L.RED)
    else:
        glyph, color, words = CLASS[cls]
        footer(ui, words, color)


def draw_scroll(ui, lines, y=26, bottom=224, color=L.WHITE):
    """Lines from ui.scroll down to the footer; up/down move it (scroll_tick)."""
    d = ui.d
    n = (bottom - y) // 12
    ui.scroll = max(0, min(ui.scroll, max(0, len(lines) - n)))
    for line in lines[ui.scroll:ui.scroll + n]:
        d.text(line, 4, y, color)
        y += 12
    if len(lines) > n:
        d.text("%d/%d" % (ui.scroll // n + 1, (len(lines) + n - 1) // n), 200, 229, L.GREY)


def scroll_tick(ui, pressed, step=8):
    if "up" in pressed:
        ui.scroll = max(0, ui.scroll - step); ui.dirty = True
    if "down" in pressed:
        ui.scroll += step; ui.dirty = True


def hexs(b, per=16):
    return " ".join("%02x" % x for x in b[:per])


# ----------------------------------------------------------------------------- ARM
def arm_tick(ui, pressed, keys):
    """Hold B and Y together ARM_HOLD_MS to arm the wallet (or disarm it while armed). Single B
    and Y presses are delivered on release, so the pair never triggers a back or a card first.
    Returns the presses the view should see."""
    now = time.ticks_ms()
    out = [k for k in pressed if k not in ("B", "Y")]
    for k in ("B", "Y"):
        if k in pressed:
            ui.pend[k] = now
    b, y = keys.held("B"), keys.held("Y")
    if b and y:
        ui.pend.clear()
        ui.pair = True
        if ui.armhold is None:
            ui.armhold = now
            ui.dirty = True
        elif time.ticks_diff(now, ui.armhold) >= ARM_HOLD_MS:
            if S.armed():
                S.disarm()
            else:
                S.arm()
            ui.armhold = None
            ui.pair = "done"        # swallow both keys until both are up
            ui.dirty = True
        elif ui.n % 4 == 0:
            ui.dirty = True         # the bar moves 5 times a second; a full redraw is up to 140 ms
        return out
    if ui.armhold is not None:
        ui.armhold, ui.dirty = None, True
    if not b and not y:
        ui.pair = False
    for k in ("B", "Y"):
        if k in ui.pend and not keys.held(k):
            del ui.pend[k]
            if not ui.pair:
                out.append(k)
    return out


def draw_arm_bar(ui):
    d = ui.d
    d.fill_rect(0, 200, 240, 40, L.BLACK)
    armed = S.armed()
    d.center_text("keep holding B+Y to %s" % ("DISARM" if armed else "ARM"), 204, L.YELLOW)
    d.rect(20, 218, 200, 12, L.WHITE)
    w = min(198, 198 * time.ticks_diff(time.ticks_ms(), ui.armhold) // ARM_HOLD_MS)
    d.fill_rect(21, 219, w, 10, L.GREEN if armed else L.RED)


# ----------------------------------------------------------------------------- CHIP MAP
ZONES = (("cfg", "CONFIG", "config", "the rules for every slot"),
         ("list", "DATA", "data", "keys and bytes, 36/416/72 B"),
         ("otp", "OTP", "otp", "64 write-once bytes"),
         ("counters", "COUNTERS", "counters", "two numbers, only ever up"),
         ("lab", "LAB", "lab", "ask the chip, read-only"))


def regions(x, y, w, h):
    """Where each zone sits on the die, as (rx, ry, rw, rh)."""
    return {"cfg": (x + 8, y + 8, w - 16, 26),
            "list": (x + 8, y + 40, 116, 72),
            "otp": (x + 132, y + 40, w - 140, 32),
            "counters": (x + 132, y + 80, w - 140, 32),
            "lab": (x + 8, y + 118, w - 16, 16)}


def draw_die(d, ui, x, y, w, h, sel=None, pulse=None, locked=None):
    """The chip as a floor plan: CONFIG across the top, the 4x4 field of slots, OTP, COUNTERS, the
    LAB docked at the bottom. sel gets a white frame; pulse recolours the selected region."""
    st = ui.st
    cfg = st.get("configLocked") if locked is None else locked
    data = st.get("dataLocked")
    for i in range(6):
        ly = y + 14 + i * 22
        d.fill_rect(x - 8, ly, 8, 4, T.C["dim"])
        d.fill_rect(x + w, ly, 8, 4, T.C["dim"])
    d.fill_rect(x, y, w, h, T.C["ink"])
    d.rect(x, y, w, h, T.C["chip"])
    d.fill_rect(x + 3, y + 3, 4, 4, T.C["learn"])
    R = regions(x, y, w, h)
    for key, name, zone, _ in ZONES:
        rx, ry, rw, rh = R[key]
        color = T.C[zone]
        fill = pulse if (pulse and key == sel) else T.shade(zone, 0.28)
        d.fill_rect(rx, ry, rw, rh, fill)
        d.rect(rx, ry, rw, rh, color)
        if key == "list":
            for n in range(16):
                s = ui.row(n)
                kc = KIND_COLOR.get(s["kind"], T.C["dim"]) if cfg or s["kind"] != "?" else T.C["dim"]
                tx, ty = rx + 6 + (n % 4) * 27, ry + 14 + (n // 4) * 14
                d.fill_rect(tx, ty, 20, 10, kc if s["kind"] != "DATA" else T.shade("data", 0.5))
                if n == ui.sig.slot:
                    d.rect(tx - 1, ty - 1, 22, 12, T.C["safe"])
            d.text("DATA", rx + 4, ry + 3, color)
        elif key == "cfg":
            I.draw(d, "config", rx + 4, ry + 5, color)
            d.text("CONFIG 128 B", rx + 24, ry + 9, L.WHITE)
            I.draw(d, "lock" if cfg else "unlock", rx + rw - 22, ry + 5, T.C["safe"] if cfg else T.C["perm"])
        elif key == "otp":
            I.draw(d, "otp", rx + 3, ry + 8, color)
            d.text("OTP", rx + 22, ry + 12, L.WHITE)
            if not cfg:
                d.text("?", rx + rw - 12, ry + 12, T.C["perm"])
        elif key == "counters":
            I.draw(d, "counter", rx + 3, ry + 8, color)
            d.text("CTR", rx + 22, ry + 12, L.WHITE)
        elif key == "lab":
            I.draw(d, "lab", rx + 2, ry, color)
            d.text("LAB: ask the chip", rx + 22, ry + 4, L.WHITE)
        if key == sel:
            d.rect(rx - 2, ry - 2, rw + 4, rh + 4, L.WHITE)
            d.rect(rx - 3, ry - 3, rw + 6, rh + 6, L.WHITE)
    return R


def draw_zones(ui):
    d = ui.d
    st = ui.st
    header(ui)
    draw_die(d, ui, 20, 30, 200, 140, sel=ZONES[ui.act][0])
    cfg, data = st.get("configLocked"), st.get("dataLocked")
    key, name, zone, blurb = ZONES[ui.act]
    state = {"cfg": ("LOCKED" if cfg else "OPEN", T.C["safe"] if cfg else T.C["perm"]),
             "list": (("LOCKED" if data else "open") if cfg else "hidden", T.C["safe"] if data else (T.C["rev"] if cfg else T.C["perm"])),
             "otp": (("LOCKED" if data else "open") if cfg else "hidden", T.C["safe"] if data else (T.C["rev"] if cfg else T.C["perm"])),
             "counters": ("", L.WHITE), "lab": ("", L.WHITE)}[key]
    size = {"cfg": "128 B", "list": "16 slots", "otp": "64 B", "counters": "2", "lab": ""}[key]
    y = 180
    I.draw(d, {"cfg": "config", "list": "data", "otp": "otp", "counters": "counter", "lab": "lab"}[key], 4, y - 4, T.C[zone])
    d.text(name, 24, y, T.C[zone])
    d.text(size, 24 + 8 * len(name) + 8, y, L.GREY)
    if state[0]:
        d.text(state[0], 236 - 8 * len(state[0]), y, state[1])
    d.text(blurb[:29], 4, y + 14, L.WHITE)
    d.text("%s  i2c %s" % (ui.part(), st.get("i2cAddr", "?")), 4, y + 28, DIM)
    footer(ui, "A open  B learn  Y home")


def tick_zones(ui, pressed):
    for k in pressed:
        if k == "up":
            ui.act = (ui.act - 1) % len(ZONES)
        elif k == "down":
            ui.act = (ui.act + 1) % len(ZONES)
        elif k == "A" or k == "press":
            view = ZONES[ui.act][0]
            if view in ("otp", "counters"):
                open_zone(ui, view)
            else:
                ui.go(view)
        elif k == "Y":
            ui.back()
        ui.dirty = True


def open_zone(ui, view):
    """OTP and COUNTERS: read on open; a refusal is the lesson, not an error."""
    chip = getattr(ui.sig, "chip", None)
    if chip is None:
        return refuse(ui, view, None, "There is no chip on the bus: the software key has no zones.")
    try:
        if view == "otp":
            ui.zone = chip.read_otp(0) + chip.read_otp(1)
        else:
            ui.zone = (chip.counter(0), chip.counter(1))
        ui.go(view)
    except atecc.AteccError as e:
        refuse(ui, view, e)


def draw_otp(ui):
    header(ui)
    lines = ["64 bytes you write once, in", "32-byte halves; bits only go", "from 1 to 0, never back.", ""]
    b = ui.zone
    for r in range(4):
        lines.append("%2d: %s" % (r * 16, hexs(b[r * 16:r * 16 + 16])))
    draw_scroll(ui, lines)
    footer(ui, "Y back")


def draw_counters(ui):
    header(ui)
    c0, c1 = ui.zone
    lines = wrap("Two counters that only go up, to 2 097 151 at most. A slot can be tied to counter 0 so every signature costs one.")
    lines += ["", "counter 0   %d" % c0, "counter 1   %d" % c1]
    draw_scroll(ui, lines)
    footer(ui, "Y back")


def draw_tile(d, ui, s, x, y, w, h, sel=False):
    """One slot as a tile: number, kind icon, size, and a fingerprint or state word."""
    cfg = ui.st.get("configLocked")
    kind = s["kind"]
    color = KIND_COLOR.get(kind, T.C["dim"])
    d.fill_rect(x, y, w, h, T.shade("data", 0.18) if kind == "DATA" else T.C["ink"])
    d.text("%2d" % s["slot"], x + 2, y + 3, L.WHITE if kind != "DATA" else L.GREY)
    if s["locked"]:
        I.draw(d, "lock", x + w - 19, y + 2, T.C["perm"])
    else:
        I.draw(d, KIND_ICON.get(kind, "bytes"), x + w - 19, y + 2, color)
    d.text("%dB" % s.get("bytes", 36), x + 2, y + h - 21, DIM)
    if kind == "P256":
        if s.get("hasKey"):
            what, wc = ("%08x" % (s["qx"] >> 224))[:6], L.WHITE
        elif not cfg:
            what, wc = "hidden", T.C["perm"]
        elif not s.get("pubInfo", True):
            what, wc = "secret", L.GREY
        else:
            what, wc = "empty", T.C["rev"]
        d.text(what, x + 2, y + h - 10, wc)
    elif kind == "DATA":
        d.text("secret" if s.get("isSecret") else "clear", x + 2, y + h - 10, T.C["dim"] if s.get("isSecret") else color)
    elif kind != "?":
        d.text(kind.lower(), x + 2, y + h - 10, color)
    if s["slot"] == ui.sig.slot:
        d.fill_rect(x, y + h - 2, w, 2, T.C["safe"])
    if sel:
        d.rect(x - 1, y - 1, w + 2, h + 2, L.WHITE)
        d.rect(x - 2, y - 2, w + 4, h + 4, L.WHITE)


# ----------------------------------------------------------------------------- CONFIG
def cfg_same(a, b):
    """Two config tables agree where writes can reach (bytes 16-83, 88-127)."""
    return a is not None and b is not None and a[16:84] == b[16:84] and a[88:] == b[88:]


def cfg_state(ui):
    """original | wallet | modified: what is on the chip now, against the snapshot and atecc.CONFIG."""
    if cfg_same(ui.cfgb, atecc.CONFIG):
        return "wallet"
    if ui.snap is None or cfg_same(ui.cfgb, ui.snap):
        return "original"
    return "modified"


def cfg_actions(ui):
    st = ui.st
    cfg, data = st.get("configLocked"), st.get("dataLocked")
    state = cfg_state(ui)
    out = [("raw", "RAW BYTES", "safe", "")]
    if ui.snap is not None:
        out.append(("diff", "COMPARE WITH SAVED", "safe", ""))
    if not cfg:
        out.append(("writecfg", "WRITE WALLET CONFIG", "rev", "" if state != "wallet" else "the chip holds it already"))
        if ui.snap is not None:
            out.append(("restore", "RESTORE SAVED CONFIG", "rev", "" if state != "original" else "the chip holds it already"))
        out.append(("lockcfg", "LOCK CONFIG FOREVER", "perm", ui.sig.gate("lock") or ("" if state == "wallet" else "write the wallet config first")))
    elif not data:
        out.append(("lockdata", "LOCK DATA ZONE", "perm", ui.sig.gate("lock")))
    out.append(("refresh", "RE-READ", "safe", ""))
    return out


def draw_cfg(ui):
    d = ui.d
    st = ui.st
    header(ui)
    y = 27
    cfg, data = st.get("configLocked"), st.get("dataLocked")
    X = 104
    d.text("CONFIG ZONE", 4, y, L.WHITE)
    d.text("128 B", X, y, L.GREY)
    d.text("LOCKED" if cfg else "OPEN", X + 56, y, L.GREEN if cfg else L.RED); y += 12
    d.text("  sealed, never changes again" if cfg else "  rewritable until locked", 4, y, L.GREY); y += 14
    state = cfg_state(ui)
    d.text("CURRENT", 4, y, L.GREY)
    d.text({"original": "original bytes", "wallet": "wallet config", "modified": "modified"}[state], X, y,
           L.WHITE if state != "modified" else L.YELLOW); y += 12
    d.text("SNAPSHOT", 4, y, L.GREY)
    d.text("none yet" if ui.snap is None else "saved", X, y, DIM if ui.snap is None else L.GREEN); y += 12
    d.text("  the original bytes, kept" if ui.snap is not None else "  taken before the first write", 4, y, DIM); y += 14
    d.text("DATA ZONE", 4, y, L.GREY)
    d.text("hidden" if not cfg else ("LOCKED" if data else "open"), X, y, L.RED if not cfg else (L.GREEN if data else L.YELLOW)); y += 12
    d.text("  until CONFIG is locked" if not cfg else ("  no clear writes, ever" if data else "  clear writes allowed"), 4, y, DIM); y += 16
    items = cfg_actions(ui)
    menu(ui, items, y, ui.act)
    menu_footer(ui, items, ui.act)


def tick_cfg(ui, pressed):
    items = cfg_actions(ui)
    for k in pressed:
        if k == "up":
            ui.act = (ui.act - 1) % len(items)
        elif k == "down":
            ui.act = (ui.act + 1) % len(items)
        elif k == "Y":
            ui.back()
        elif k == "A" or k == "press":
            kind, label, cls, off = items[ui.act]
            if off:
                ui.show_result("off: " + off + ". Nothing was changed.", False)
            elif kind == "raw":
                ui.go("raw")
            elif kind == "diff":
                ui.diff = atecc.diff_config(ui.cfgb, ui.snap)
                ui.difftitle = "chip vs saved snapshot"
                ui.go("diff")
            elif kind in ("writecfg", "restore"):
                start_write(ui, kind)
            elif kind == "refresh":
                ui.refresh()
                ui.act = 0
            else:
                ui.choose(kind, None)
        ui.dirty = True


def draw_raw(ui):
    """The 128 config bytes, 8 a row: the table the chip lives by, readable off the screen."""
    d = ui.d
    header(ui)
    cfg = ui.cfgb or b""
    for r in range(16):
        y = 26 + r * 12
        d.text("%3d" % (r * 8), 2, y, L.GREY)
        row = cfg[r * 8:r * 8 + 8]
        if r in (2, 3, 12, 13, 14, 15):
            c = L.WHITE      # SlotConfig (20-51) and KeyConfig (96-127) rows: the slot table
        elif r == 10:
            c = L.YELLOW     # 84-87 lock bytes, 88-89 slot locked
        else:
            c = L.GREY
        d.text(" ".join("%02x" % b for b in row), 30, y, c)
    footer(ui, "white=slot table  Y back")


def diff_lines(diff, full=True):
    """The change list as screen lines."""
    lines = ["%d bytes would change" % len(diff["bytes"]) if diff["bytes"] else "nothing would change"]
    if diff["addrChanges"]:
        lines.append("! I2C ADDRESS WOULD CHANGE")
    names = {"kind": "kind", "extSign": "sign", "genKey": "genkey", "privWrite": "privwrite", "pubInfo": "pub readable",
             "lockable": "lockable", "isSecret": "secret", "clearWrite": "write"}
    yn = lambda v: v if isinstance(v, str) else ("yes" if v else "no")
    for slot, fields in diff["slots"]:
        kinds = [(a, b) for k, a, b in fields if k == "kind"]
        if kinds:
            lines.append("slot %d: %s -> %s" % (slot, kinds[0][0], kinds[0][1]))
        elif full:
            lines.append("slot %d (%s):" % (slot, fields and "same kind" or ""))
        if full:
            for k, a, b in fields:
                if k != "kind":
                    lines.append("  %s: %s -> %s" % (names[k], yn(a), yn(b)))
    return lines


def draw_diff(ui):
    header(ui)
    lines = [ui.difftitle] + diff_lines(ui.diff)
    draw_scroll(ui, lines)
    footer(ui, "up/dn scroll  Y back")


# ----------------------------------------------------------------------------- the reversible write
NOTE_TEXT = "hello from picowallet"


def start_write(ui, kind, slot=None):
    """Show what a write would change, then wait for A held: a REVERSIBLE CHANGE, yellow."""
    if kind == "note":
        ui.diff = None
    else:
        target = atecc.CONFIG if kind == "writecfg" else ui.snap
        ui.diff = atecc.diff_config(ui.cfgb, target)
        ui.difftitle = "chip vs " + ("wallet config" if kind == "writecfg" else "saved snapshot")
    ui.action, ui.hold, ui.ret = (kind, slot), None, ui.view
    ui.view = "confirm_write"


def draw_confirm_write(ui):
    d = ui.d
    kind = ui.action[0]
    diff = ui.diff
    header(ui, "REVERSIBLE CHANGE")
    y = 27
    badge(d, "rev", 4, y)
    d.text({"writecfg": "WRITE WALLET CONFIG", "restore": "RESTORE SAVED CONFIG", "note": "WRITE A NOTE INTO SLOT %s" % ui.action[1]}[kind], 18, y, L.YELLOW); y += 12
    d.text("can be restored", 18, y, L.YELLOW); y += 14
    if kind == "note":
        for line in wrap("32 bytes of clear text go into slot %s (plain data, readable in clear). Writing again replaces them, so this can be undone until the data zone is locked." % ui.action[1]):
            d.text(line, 4, y, L.WHITE); y += 12
        y += 6
        d.text('"%s"' % NOTE_TEXT[:27], 4, y, L.WHITE); y += 12
    else:
        for line in diff_lines(diff, full=False)[:6]:
            d.text(line[:29], 4, y, L.WHITE); y += 12
        d.text("I2C address unchanged 0x%02x" % ((ui.cfgb[16] >> 1) if ui.cfgb else 0), 4, y, L.GREEN if not diff["addrChanges"] else L.RED); y += 12
        d.text("config zone stays OPEN", 4, y, L.GREEN); y += 12
    d.center_text("hold A to write", 176, L.YELLOW)
    d.rect(20, 192, 200, 14, L.WHITE)
    if ui.hold is not None:
        w = min(198, 198 * time.ticks_diff(time.ticks_ms(), ui.hold) // ui.HOLD_REV)
        d.fill_rect(21, 193, w, 12, L.YELLOW)
    footer(ui, "B cancel" if kind == "note" else "Y details  B cancel")


def run_write(ui, kind, slot=None):
    """The write itself, then the checks."""
    try:
        if kind == "note":
            ui.sig.write_note(NOTE_TEXT, slot)
            back = ui.sig.read_note(slot)
            ui.checks = (("WRITE COMPLETE", True), ("READ BACK: " + back[:14], back == NOTE_TEXT), ("DATA ZONE STILL OPEN", not ui.st.get("dataLocked")))
            ui.show_result("Slot %d now holds the note. READ THE BYTES shows it; writing again replaces it." % slot, True)
            return
        n = ui.sig.write_config() if kind == "writecfg" else ui.sig.restore_snapshot()
        ui.refresh()
        ui.checks = (("WRITE COMPLETE", True), ("READBACK MATCHES", True), ("CONFIG STILL OPEN", not ui.st.get("configLocked")))
        ui.show_result("%d bytes changed. Nothing has been permanently locked." % n, True)
    except Exception as e:
        ui.refresh()
        ui.checks = (("WRITE COMPLETE", False),)
        if kind == "note":
            ui.show_result("%s." % e, False)
        else:
            ui.show_result("%s. The chip's table may now be a mix: RESTORE SAVED CONFIG puts the snapshot back." % e, False)
    ui.on_change()


# ----------------------------------------------------------------------------- refusals
def why_refused(ui, what, status):
    cfg_open = not ui.st.get("configLocked")
    if status == 0x0F and cfg_open:
        zone = {"otp": "the OTP zone", "data": "the DATA zone", "counters": "the counters", "keyvalid": "any key"}
        if what in zone:
            return "The CONFIG zone is still open. Until its rules are locked, the chip will not expose %s." % zone[what]
        if what in ("genkey", "sign", "pubkey"):
            return "GenKey and Sign are refused until the CONFIG zone is locked: no key can exist before the rules are sealed."
        return "The chip will not do this while its CONFIG zone is open."
    if status == 0x0F and what == "data":
        return "Slot 8's rules mark it secret: the chip never hands its bytes out in clear. Slots 12 and 13 are the clear ones."
    if status == 0x03:
        return "The chip did not understand the command as sent. That is a firmware bug, not the chip's state."
    if status is None:
        return "The chip did not answer at all: wiring, power, or it fell asleep."
    return atecc.explain(status)


def refuse(ui, what, e, why=None):
    status = getattr(e, "status", None)
    chip = getattr(ui.sig, "chip", None)
    ui.ref = {"what": what, "status": status, "why": why or why_refused(ui, what, status), "err": str(e) if e else "",
              "trace": chip.trace if chip else None}
    ui.ret = ui.view if ui.view not in ("busy",) else ui.ret
    ui.view, ui.dirty = "refused", True


def draw_refused(ui):
    d = ui.d
    r = ui.ref
    header(ui)
    y = 27
    d.text("CHIP SAYS:", 4, y, L.GREY); y += 14
    icon(d, "cross", 6, y, L.RED)
    d.big_text("NOT ALLOWED", 24, y - 1, L.RED, 2)
    y += 22
    d.text("Why?", 4, y, L.YELLOW); y += 12
    for line in wrap(r["why"])[:7]:
        d.text(line, 4, y, L.WHITE); y += 12
    y += 4
    if r["status"] is not None:
        d.text("STATUS 0x%02X" % r["status"], 4, y, L.GREY); y += 12
        for line in wrap(atecc.explain(r["status"]))[:2]:
            d.text(line, 4, y, L.GREY); y += 12
    elif r["err"]:
        for line in wrap(r["err"])[:2]:
            d.text(line, 4, y, L.GREY); y += 12
    footer(ui, "A raw command  Y back" if r["trace"] else "Y back")


def rawcmd_lines(trace):
    if not trace:
        return ["no command was sent"]
    d = trace["data"]
    lines = ["op 0x%02x  p1 0x%02x  p2 0x%04x" % (trace["op"], trace["p1"], trace["p2"]),
             "sent %d data bytes" % len(d)]
    for i in range(0, len(d), 8):
        lines.append("  " + hexs(d[i:i + 8], 8))
    r = trace["resp"]
    if len(r) == 1:
        lines.append("answer: status 0x%02x" % r[0])
        lines += ["  " + l for l in wrap(atecc.explain(r[0]), 27)]
    else:
        lines.append("answer: %d bytes" % len(r))
        for i in range(0, len(r), 8):
            lines.append("  " + hexs(r[i:i + 8], 8))
    lines.append("round trip %d ms" % trace["ms"])
    return lines


def draw_rawcmd(ui):
    header(ui)
    src = ui.ref if ui.view_from == "refused" else ui.lab
    draw_scroll(ui, rawcmd_lines(src["trace"] if src else None))
    footer(ui, "up/dn scroll  Y back")
