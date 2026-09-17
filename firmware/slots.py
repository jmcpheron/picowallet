# The KEYS screen: the chip's slot table on the wallet itself. Pick which slot signs, make a new
# key in a slot, read a slot's public key, lock the config zone / data zone / one slot. Every
# permanent action needs A held for a while on a red screen, and the ALLOW_* flags in secrets.py.
#
# Used by wallet.py: ui = SlotsUI(d, sig, on_change); ui.open(); each tick ui.tick(pressed, keys)
# returns "home" when the user leaves. Runs on the wallet's 50 ms timer, so nothing here may take
# long except the chip operations themselves (GenKey ~120 ms on the ATECC, ~1 s in software).
import time
import lcd as L

HOLD_MS = 1500          # hold A this long to confirm a permanent action
ROW_Y, ROW_H = 18, 13   # 16 slot rows fit between the header and the footer
DIM = L.color(90, 90, 100)
KIND_COLOR = {"P256": L.WHITE, "PUB": L.GREY, "AES": L.GREY, "DATA": DIM, "?": DIM}
KIND_LABEL = {"?": "-"}     # a blank chip types nothing yet

DESC = {"P256": "P-256 private key", "PUB": "P-256 public key", "AES": "AES-128 key", "DATA": "plain data",
        "?": "untyped: the config zone is open"}


def fp(s):
    return "%08x" % (s["qx"] >> 224)


class SlotsUI:
    def __init__(self, d, sig, on_change):
        self.d = d
        self.sig = sig
        self.on_change = on_change      # called after anything that may change the active key
        self.view = "list"
        self.cur = 0            # cursor on the list
        self.act = 0            # cursor on an action menu
        self.table = []
        self.st = {}
        self.action = None      # ("genkey", slot) etc while confirming
        self.hold = None        # ticks_ms when A went down on the confirm screen
        self.msg = ""
        self.ok = True
        self.back = "list"      # where a result screen returns to
        self.dirty = True

    # ----------------------------------------------------------------------------- data
    def open(self):
        self.view = "list"
        self.cur = getattr(self.sig, "slot", 0)
        self.refresh()

    def refresh(self):
        try:
            self.table = self.sig.slots()
        except Exception as e:
            self.table = []
            self.msg, self.ok, self.view = "slot table: %r" % e, False, "result"
        try:
            self.st = self.sig.status()
        except Exception as e:
            self.st = {"note": str(e)}
        self.dirty = True

    def row(self, n):
        for s in self.table:
            if s["slot"] == n:
                return s
        return {"slot": n, "kind": "?", "locked": False, "lockable": False, "genKey": False, "extSign": False, "pubInfo": False, "privWrite": False}

    def actions(self, s):
        """What the cursor can do to this slot, given what the config zone allows."""
        out = []
        active = s["slot"] == self.sig.slot
        cfg_locked = self.st.get("configLocked", False)
        if s["kind"] == "P256":
            if s.get("hasKey") and not active:
                out.append(("use", "USE THIS KEY"))
            if s["genKey"] and not s["locked"]:
                out.append(("genkey", "NEW KEY" if cfg_locked else "NEW KEY (lock config first)"))
            if s.get("hasKey"):
                out.append(("pubkey", "SHOW PUBLIC KEY"))
        if s["lockable"] and not s["locked"]:
            out.append(("lockslot", "LOCK SLOT FOREVER"))
        return out

    def chip_actions(self):
        out = []
        if not self.st.get("configLocked"):
            out.append(("lockcfg", "WRITE + LOCK CONFIG"))
        elif not self.st.get("dataLocked"):
            out.append(("lockdata", "LOCK DATA ZONE"))
        out.append(("refresh", "RE-READ CHIP"))
        return out

    # ----------------------------------------------------------------------------- drawing
    def draw(self):
        d = self.d
        d.fill(L.BLACK)
        v = self.view
        if v == "list":
            self.draw_list()
        elif v == "slot":
            self.draw_slot()
        elif v == "chip":
            self.draw_chip()
        elif v == "pubkey":
            self.draw_pubkey()
        elif v == "confirm":
            self.draw_confirm()
        elif v == "busy":
            self.header("WORKING", L.BLUE)
            d.center_text(self.msg[:28], 100, L.WHITE)
        elif v == "result":
            self.header("DONE" if self.ok else "ERROR", L.GREEN if self.ok else L.RED)
            self.lines(self.msg, 40, L.WHITE)
            d.center_text("A = ok", 224, L.GREY)
        d.show()
        self.dirty = False

    def header(self, title, color):
        self.d.fill_rect(0, 0, 240, 22, color)
        self.d.center_text(title, 3, L.WHITE, 2)

    def lines(self, s, y, c, w=29):
        """Word-wrapped text, w chars a line."""
        line = ""
        for word in s.split(" "):
            while len(word) > w:
                if line:
                    self.d.text(line, 4, y, c); y += 12; line = ""
                self.d.text(word[:w], 4, y, c); y += 12
                word = word[w:]
            if len(line) + len(word) + (1 if line else 0) > w:
                self.d.text(line, 4, y, c); y += 12; line = word
            else:
                line = line + " " + word if line else word
        if line:
            self.d.text(line, 4, y, c); y += 12
        return y

    def draw_list(self):
        d = self.d
        d.text("KEYS", 4, 4, L.YELLOW)
        d.text(self.sig.name[:9], 48, 4, L.GREY)
        cfg = self.st.get("configLocked")
        d.text("cfg " + ("locked" if cfg else "OPEN"), 140, 4, L.GREEN if cfg else L.RED)
        if not self.table:
            d.center_text("no slot table", 100, L.RED)
        for n in range(16):
            s = self.row(n)
            y = ROW_Y + n * ROW_H
            if n == self.cur:
                d.fill_rect(0, y - 2, 240, ROW_H, L.DARK)
                d.text(">", 2, y, L.YELLOW)
            c = KIND_COLOR.get(s["kind"], L.DARK)
            active = n == self.sig.slot
            d.text("%2d" % n, 12, y, L.GREEN if active else c)
            d.text(KIND_LABEL.get(s["kind"], s["kind"]), 36, y, c)
            if s["kind"] == "P256":
                if s.get("hasKey"):
                    what, wc = fp(s), L.WHITE
                elif not cfg:
                    what, wc = "config open", L.RED
                elif not s.get("pubInfo", True):
                    what, wc = "hidden", L.GREY
                else:
                    what, wc = "empty", L.YELLOW
                d.text(what, 80, y, wc)
                if active:
                    d.text("ACTIVE", 168, y, L.GREEN)
            if s["locked"]:
                d.text("L", 226, y, L.RED)
        d.fill_rect(0, 226, 240, 14, L.DARK)
        d.text("A open  X chip  Y back", 4, 229, L.GREY)

    def draw_slot(self):
        d = self.d
        s = self.row(self.cur)
        self.header("SLOT %d" % self.cur, L.BLUE)
        y = 28
        d.text(DESC.get(s["kind"], s["kind"]), 4, y, L.WHITE); y += 12
        if s["kind"] == "P256":
            if s.get("hasKey"):
                d.text("key " + fp(s), 4, y, L.GREEN if self.cur == self.sig.slot else L.WHITE)
                if self.cur == self.sig.slot:
                    d.text("ACTIVE", 160, y, L.GREEN)
            elif not self.st.get("configLocked"):
                d.text("unusable until config locks", 4, y, L.RED)
            else:
                d.text("empty", 4, y, L.YELLOW)
            y += 12
            flags = (("sign external digests", s["extSign"]), ("genkey allowed", s["genKey"]),
                     ("privwrite (import)", s["privWrite"]), ("pubkey readable", s["pubInfo"]),
                     ("limited use (counter)", s.get("limitedUse", False)), ("lockable", s["lockable"]))
        else:
            flags = (("lockable", s["lockable"]),)
        for name, on in flags:
            d.text(name, 12, y, L.WHITE if on else L.GREY)
            d.text("yes" if on else "no", 200, y, L.GREEN if on else L.GREY)
            y += 12
        d.text("slot locked", 12, y, L.WHITE)
        d.text("YES" if s["locked"] else "no", 200, y, L.RED if s["locked"] else L.GREY)
        y += 16
        acts = self.actions(s)
        if not acts:
            d.text("nothing to do here", 12, y, L.GREY)
        for i, (_, label) in enumerate(acts):
            sel = i == self.act
            if sel:
                d.fill_rect(0, y - 2, 240, 13, L.DARK)
            d.text((">" if sel else " ") + label, 4, y, L.YELLOW if sel else L.WHITE)
            y += 14
        d.fill_rect(0, 226, 240, 14, L.DARK)
        d.text("A do  up/dn pick  Y back", 4, 229, L.GREY)

    def draw_chip(self):
        d = self.d
        st = self.st
        self.header("CHIP", L.BLUE)
        y = 28
        d.text(self.sig.name, 4, y, L.WHITE); y += 12
        if st.get("serial"):
            d.text("serial " + st["serial"], 4, y, L.GREY); y += 12
        if st.get("revision"):
            d.text("rev " + st["revision"] + (" 608A" if st["revision"].endswith("02") else ""), 4, y, L.GREY); y += 12
        y += 4
        cfg, data = st.get("configLocked"), st.get("dataLocked")
        d.text("config zone", 4, y, L.WHITE)
        d.text("LOCKED" if cfg else "OPEN", 160, y, L.GREEN if cfg else L.RED); y += 12
        d.text(" the slot table, frozen once", 4, y, L.GREY); y += 12
        d.text("data zone", 4, y, L.WHITE)
        d.text("LOCKED" if data else "open", 160, y, L.GREEN if data else L.YELLOW); y += 12
        d.text(" no clear writes, genkey ok", 4, y, L.GREY); y += 12
        locked = [str(s["slot"]) for s in self.table if s["locked"]]
        d.text("locked slots " + (" ".join(locked) if locked else "none"), 4, y, L.WHITE); y += 12
        d.text("active slot %d" % self.sig.slot, 4, y, L.GREEN); y += 16
        for i, (_, label) in enumerate(self.chip_actions()):
            sel = i == self.act
            if sel:
                d.fill_rect(0, y - 2, 240, 13, L.DARK)
            d.text((">" if sel else " ") + label, 4, y, L.YELLOW if sel else L.WHITE)
            y += 14
        d.fill_rect(0, 226, 240, 14, L.DARK)
        d.text("A do  up/dn pick  Y back", 4, 229, L.GREY)

    def draw_pubkey(self):
        d = self.d
        s = self.row(self.cur)
        self.header("SLOT %d PUBKEY" % self.cur, L.BLUE)
        y = 30
        for name, v in (("qx", s["qx"]), ("qy", s["qy"])):
            d.text(name, 4, y, L.YELLOW); y += 12
            h = "%064x" % v
            for i in range(0, 64, 32):
                d.text(h[i:i + 32][:29], 4, y, L.WHITE)
                d.text(h[i + 29:i + 32], 4, y + 12, L.WHITE)
                y += 24
            y += 4
        d.center_text("the vault pins this key", 200, L.GREY)
        d.center_text("Y back", 224, L.GREY)

    def draw_confirm(self):
        d = self.d
        kind, slot = self.action
        self.header("ARE YOU SURE", L.RED)
        if kind == "genkey":
            body = ("NEW KEY IN SLOT %d" % slot, "", "replaces the key there. a vault paired to the old key can NEVER be spent again.")
        elif kind == "lockslot":
            body = ("LOCK SLOT %d FOREVER" % slot, "", "the key in it can never be replaced or removed.")
        elif kind == "lockcfg":
            body = ("LOCK CONFIG ZONE", "", "writes the reference slot table and freezes it. permanent. every chip in use is config-locked.")
        elif kind == "lockdata":
            body = ("LOCK DATA ZONE", "", "no more clear-text writes to any slot. genkey stays allowed where the table says. permanent.")
        else:
            body = (kind,)
        y = 30
        for line in body:
            y = self.lines(line, y, L.WHITE) if line else y + 8
        d.center_text("hold A to confirm", 176, L.YELLOW)
        d.rect(20, 192, 200, 14, L.WHITE)
        if self.hold is not None:
            w = min(198, 198 * time.ticks_diff(time.ticks_ms(), self.hold) // HOLD_MS)
            d.fill_rect(21, 193, w, 12, L.RED)
        d.center_text("Y cancel", 224, L.GREY)

    # ----------------------------------------------------------------------------- input
    def tick(self, pressed, keys):
        """pressed: key names that went down this tick. keys: lcd.Keys, for held(). Returns "home" to leave."""
        v = self.view
        if v == "confirm":
            if "Y" in pressed:
                self.hold, self.view, self.dirty = None, self.back, True
            elif keys.held("A"):
                if self.hold is None:
                    self.hold = time.ticks_ms()
                if time.ticks_diff(time.ticks_ms(), self.hold) >= HOLD_MS:
                    self.hold = None
                    self.run(*self.action)
                self.dirty = True
            elif self.hold is not None:
                self.hold, self.dirty = None, True
        elif v == "list":
            for k in pressed:
                if k == "up":
                    self.cur = (self.cur - 1) % 16
                elif k == "down":
                    self.cur = (self.cur + 1) % 16
                elif k == "A" or k == "press":
                    self.view, self.act = "slot", 0
                elif k == "X":
                    self.view, self.act = "chip", 0
                elif k == "Y":
                    return "home"
                self.dirty = True
        elif v == "slot":
            acts = self.actions(self.row(self.cur))
            for k in pressed:
                if k == "up" and acts:
                    self.act = (self.act - 1) % len(acts)
                elif k == "down" and acts:
                    self.act = (self.act + 1) % len(acts)
                elif k == "left":
                    self.cur, self.act = (self.cur - 1) % 16, 0
                elif k == "right":
                    self.cur, self.act = (self.cur + 1) % 16, 0
                elif k == "Y":
                    self.view = "list"
                elif (k == "A" or k == "press") and acts:
                    self.choose(acts[self.act][0], self.cur, "slot")
                self.dirty = True
        elif v == "chip":
            acts = self.chip_actions()
            for k in pressed:
                if k == "up":
                    self.act = (self.act - 1) % len(acts)
                elif k == "down":
                    self.act = (self.act + 1) % len(acts)
                elif k == "Y":
                    self.view = "list"
                elif k == "A" or k == "press":
                    self.choose(acts[self.act][0], None, "chip")
                self.dirty = True
        elif v == "pubkey":
            if "Y" in pressed or "A" in pressed:
                self.view, self.dirty = "slot", True
        elif v == "result":
            if "A" in pressed or "Y" in pressed:
                self.view, self.dirty = self.back, True
        if self.dirty:
            self.draw()
        return None

    def choose(self, kind, slot, back):
        self.back = back
        if kind == "use":
            self.run(kind, slot)
        elif kind == "pubkey":
            self.view = "pubkey"
        elif kind == "refresh":
            self.refresh()
            self.act = 0
        elif kind == "genkey" and not self.st.get("configLocked"):
            self.msg, self.ok, self.view = "the chip refuses genkey until the config zone is locked. X on the list, then WRITE + LOCK CONFIG.", False, "result"
        else:
            self.action, self.hold, self.view = (kind, slot), None, "confirm"

    def run(self, kind, slot):
        self.view, self.msg = "busy", {"genkey": "making a key in slot %s" % slot, "use": "switching to slot %s" % slot}.get(kind, kind + "...")
        self.draw()
        try:
            if kind == "use":
                self.sig.use(slot)
                out = "slot %d is now the signing key. the app shows paired only if the vault was deployed with it." % slot
            elif kind == "genkey":
                x, _ = self.sig.genkey(slot)
                out = "new key in slot %d: %08x. record qx/qy from SHOW PUBLIC KEY before deploying a vault." % (slot, x >> 224)
                if slot == self.sig.slot:
                    out = "new key in slot %d (the ACTIVE slot): %08x. the app will show not paired until a vault uses it." % (slot, x >> 224)
            elif kind == "lockslot":
                out = str(self.sig.lock_slot(slot))
            elif kind == "lockcfg":
                out = str(self.sig.lock_config()) + ". slots 0, 2 and 7 are now P-256 key slots. next: NEW KEY in a slot."
            elif kind == "lockdata":
                out = str(self.sig.lock_data())
            else:
                out = "unknown action " + kind
            self.ok = True
        except Exception as e:
            out, self.ok = "%s failed: %s" % (kind, e), False
        self.msg = out[:200]
        self.refresh()
        self.act = 0
        self.view = "result"
        self.dirty = True
        if kind in ("use", "genkey"):
            self.on_change()
