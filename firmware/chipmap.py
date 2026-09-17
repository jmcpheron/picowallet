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

CLASS = {"safe": ("o", L.GREEN, "SAFE TO EXPLORE: no changes"),
         "rev": ("~", L.YELLOW, "REVERSIBLE: can be restored"),
         "perm": ("!", L.RED, "PERMANENT: cannot be undone")}
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
    d.fill_rect(0, 0, 240, 22, L.DARK)
    left = S.armed()
    arm = ("! ARMED %ds" % left) if left else "SAFE o"
    d.text(text[:28 - len(arm)] if text is not None else crumb(ui, 28 - len(arm)), 4, 7, L.WHITE)
    d.text(arm, 236 - 8 * len(arm), 7, L.RED if left else L.GREEN)


def footer(ui, text, color=L.GREY):
    ui.d.fill_rect(0, 226, 240, 14, L.DARK)
    ui.d.text(text[:29], 4, 229, color)


def icon(d, name, x, y, c):
    """Small marks the 8x8 font cannot type: check, cross, warn, lock (open/closed). 12 px tall."""
    if name == "check":
        for dx in (0, 1):
            d.line(x + dx, y + 6, x + 4 + dx, y + 10, c)
            d.line(x + 4 + dx, y + 10, x + 11 + dx, y + 2, c)
    elif name == "cross":
        for dx in (0, 1):
            d.line(x + dx, y + 1, x + 9 + dx, y + 10, c)
            d.line(x + 9 + dx, y + 1, x + dx, y + 10, c)
    elif name == "warn":
        d.line(x + 5, y, x, y + 11, c); d.line(x + 5, y, x + 10, y + 11, c); d.line(x, y + 11, x + 10, y + 11, c)
        d.fill_rect(x + 5, y + 4, 1, 4, c); d.fill_rect(x + 5, y + 9, 1, 1, c)
    elif name == "lock":
        d.fill_rect(x, y + 6, 12, 8, c)
        d.rect(x + 2, y + 1, 8, 6, c)
    elif name == "unlock":
        d.fill_rect(x, y + 6, 12, 8, c)
        d.rect(x + 6, y, 8, 6, c)
        d.fill_rect(x + 7, y + 5, 6, 2, L.BLACK)


def menu(ui, items, y, sel):
    """Rows of (kind, label, cls, off). Glyph in the class colour, label white (yellow when picked,
    dim when off). Returns the next y. The footer words come from menu_footer."""
    d = ui.d
    for i, (kind, label, cls, off) in enumerate(items):
        glyph, color, _ = CLASS[cls]
        if i == sel:
            d.fill_rect(0, y - 2, 240, 13, L.DARK)
        d.text(">" if i == sel else " ", 2, y, L.YELLOW)
        d.text(glyph, 12, y, color)
        d.text(label[:26], 24, y, DIM if off else (L.YELLOW if i == sel else L.WHITE))
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
        elif time.ticks_diff(now, ui.armhold) >= ARM_HOLD_MS:
            if S.armed():
                S.disarm()
            else:
                S.arm()
            ui.armhold = None
            ui.pair = "done"        # swallow both keys until both are up
        ui.dirty = True
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
ZONES = (("cfg", "CONFIG", "the rules for every slot"),
         ("list", "DATA", "keys and bytes, 36/416/72 B"),
         ("otp", "OTP", "64 write-once bytes"),
         ("counters", "COUNTERS", "two numbers, only ever up"),
         ("lab", "LAB", "ask the chip, read-only"))


def draw_zones(ui):
    d = ui.d
    st = ui.st
    header(ui)
    y = 27
    part = ui.part()
    d.text(part, 4, y, L.WHITE)
    if st.get("i2cAddr"):
        d.text("i2c " + st["i2cAddr"], 240 - 8 * 8, y, L.GREY)
    y += 12
    d.text("serial " + st.get("serial", "?"), 4, y, L.GREY); y += 16
    cfg, data = st.get("configLocked"), st.get("dataLocked")
    for i, (view, name, blurb) in enumerate(ZONES):
        sel = i == ui.act
        if sel:
            d.fill_rect(0, y - 2, 240, 25, L.DARK)
        d.text(">" if sel else " ", 2, y, L.YELLOW)
        d.text(name, 14, y, L.YELLOW if sel else L.WHITE)
        if view == "cfg":
            d.text("128 B", 92, y, L.GREY)
            d.text("LOCKED" if cfg else "OPEN", 150, y, L.GREEN if cfg else L.RED)
        elif view == "list":
            d.text("16 slots", 92, y, L.GREY)
            d.text("hidden" if not cfg else ("LOCKED" if data else "open"), 162, y, L.RED if not cfg else (L.GREEN if data else L.YELLOW))
        elif view == "otp":
            d.text("64 B", 92, y, L.GREY)
            d.text("hidden" if not cfg else ("LOCKED" if data else "open"), 162, y, L.RED if not cfg else (L.GREEN if data else L.YELLOW))
        elif view == "counters":
            d.text("2", 92, y, L.GREY)
        d.text(blurb, 14, y + 12, DIM)
        y += 26
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
def start_write(ui, kind):
    """Show what a write would change, then wait for A held: a REVERSIBLE CHANGE, yellow."""
    target = atecc.CONFIG if kind == "writecfg" else ui.snap
    ui.diff = atecc.diff_config(ui.cfgb, target)
    ui.difftitle = "chip vs " + ("wallet config" if kind == "writecfg" else "saved snapshot")
    ui.action, ui.hold, ui.ret = (kind, None), None, ui.view
    ui.view = "confirm_write"


def draw_confirm_write(ui):
    d = ui.d
    kind = ui.action[0]
    diff = ui.diff
    header(ui, "REVERSIBLE CHANGE")
    y = 27
    d.text("WRITE WALLET CONFIG" if kind == "writecfg" else "RESTORE SAVED CONFIG", 4, y, L.YELLOW); y += 12
    d.text("~ can be restored", 4, y, L.YELLOW); y += 14
    for line in diff_lines(diff, full=False)[:6]:
        d.text(line[:29], 4, y, L.WHITE); y += 12
    d.text("I2C address unchanged 0x%02x" % ((ui.cfgb[16] >> 1) if ui.cfgb else 0), 4, y, L.GREEN if not diff["addrChanges"] else L.RED); y += 12
    d.text("config zone stays OPEN", 4, y, L.GREEN); y += 12
    d.center_text("hold A to write", 176, L.YELLOW)
    d.rect(20, 192, 200, 14, L.WHITE)
    if ui.hold is not None:
        w = min(198, 198 * time.ticks_diff(time.ticks_ms(), ui.hold) // ui.HOLD_REV)
        d.fill_rect(21, 193, w, 12, L.YELLOW)
    footer(ui, "Y details  B cancel")


def run_write(ui, kind):
    """The write itself, then the three checks."""
    try:
        n = ui.sig.write_config() if kind == "writecfg" else ui.sig.restore_snapshot()
        ui.refresh()
        ui.checks = (("WRITE COMPLETE", True), ("READBACK MATCHES", True), ("CONFIG STILL OPEN", not ui.st.get("configLocked")))
        ui.show_result("%d bytes changed. Nothing has been permanently locked." % n, True)
    except Exception as e:
        ui.refresh()
        ui.checks = (("WRITE COMPLETE", False),)
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
        return "This slot's rules forbid reading it in clear (IsSecret), or the block is out of range."
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
