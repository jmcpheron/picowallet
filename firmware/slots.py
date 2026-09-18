# The chip UI's state machine, and the DATA screens: the slot list, one slot, its public key, the
# red PERMANENT confirm, WORKING and result screens. The map, config page, lab and tutorial live in
# chipmap.py and learn.py and draw through this object. X on the home screen opens the map, B the
# tutorial; Y walks back up the trail (ui.stack) and out to home.
#
# Every action has a class shown by colour, glyph and words (chipmap.CLASS). A permanent action needs
# the secrets.py flag, the wallet ARMED (hold B+Y 3 s), and A held 3 s here on the red screen.
# Runs on the wallet's 50 ms timer: nothing here may take long except the chip operations.
import time
import lcd as L
import signer as S
import atecc
import chipmap as C
import learn as LN
import ceremony as CE
import theme as T
import icons as I

HOLD_PERM = 3000        # A held this long on the red screen
HOLD_REV = 1500         # and this long on the yellow one
ROW_Y, ROW_H = 25, 12   # 16 slot rows between the header and the footer
KIND_COLOR = {"P256": L.WHITE, "PUB": L.GREY, "AES": L.GREY, "DATA": C.DIM, "?": C.DIM}
KIND_LABEL = {"?": "-"}
DESC = {"P256": "P-256 private key", "PUB": "P-256 public key", "AES": "AES-128 key", "DATA": "plain data",
        "?": "untyped by the rules"}
TRANSIENT = ("busy", "confirm", "confirm_write", "result", "refused", "labres")
PARTS = {"00006002": "ATECC608A", "00006003": "ATECC608B", "00005000": "ATECC508A"}


def fp(s):
    return "%08x" % (s["qx"] >> 224)


class SlotsUI:
    HOLD_REV = HOLD_REV

    def __init__(self, d, sig, on_change):
        self.d = d
        self.sig = sig
        self.on_change = on_change      # called after anything that may change the active key or the table
        self.view = "zones"
        self.stack = []                 # (view, act, scroll) trail for Y
        self.ret = "zones"              # where a transient screen returns to
        self.cur = 0                    # cursor on the slot list
        self.act = 0                    # cursor on a menu
        self.act2 = 0                   # cursor on a result's sub-menu
        self.scroll = 0
        self.table = []
        self.st = {}
        self.cfgb = None                # the 128 config bytes as last read
        self.snap = None                # the saved snapshot, if any
        self.action = None              # (kind, slot) while confirming
        self.hold = None                # ticks_ms when A went down on a confirm screen
        self.armhold = None             # ticks_ms when B+Y went down
        self.pend = {}                  # B/Y presses waiting for release (chipmap.arm_tick)
        self.pair = False
        self.msg = ""
        self.ok = True
        self.checks = None              # ((label, ok), ...) on a result screen
        self.sealed = False
        self.lab = None
        self.ref = None
        self.card = None
        self.done = set()
        self.diff = None
        self.difftitle = ""
        self.zone = None
        self.view_from = ""
        self.n = 0
        self.leave = False
        self.dirty = True

    # ----------------------------------------------------------------------------- navigation
    def go(self, view, act=0):
        self.stack.append((self.view, self.act, self.scroll))
        self.view, self.act, self.scroll, self.dirty = view, act, 0, True

    def back(self):
        if self.stack:
            self.view, self.act, self.scroll = self.stack.pop()
        else:
            self.leave = True
        self.dirty = True

    def open(self, view="zones"):
        self.stack = []
        self.view, self.act, self.scroll = view, 0, 0
        self.cur = getattr(self.sig, "slot", 0)
        self.refresh()

    def busy(self, msg):
        self.view, self.msg = "busy", msg
        self.draw()

    def show_result(self, msg, ok):
        if self.view not in TRANSIENT:
            self.ret = self.view
        self.msg, self.ok, self.view, self.dirty = msg[:220], ok, "result", True

    # ----------------------------------------------------------------------------- data
    def refresh(self):
        try:
            self.table = self.sig.slots()
        except Exception as e:
            self.table = []
            self.show_result("slot table: %r" % e, False)
        try:
            self.st = self.sig.status()
        except Exception as e:
            self.st = {"note": str(e)}
        try:
            self.cfgb = self.sig.config()
        except Exception:
            self.cfgb = None
        try:
            self.snap = self.sig.snapshot()
        except Exception:
            self.snap = None
        self.dirty = True

    def row(self, n):
        for s in self.table:
            if s["slot"] == n:
                return s
        return {"slot": n, "kind": "?", "bytes": atecc.SLOT_BYTES[n], "locked": False, "lockable": False, "genKey": False,
                "extSign": False, "pubInfo": False, "privWrite": False, "clearWrite": "?", "encRead": False, "isSecret": False}

    def part(self):
        rev = self.st.get("revision", "")
        return PARTS.get(rev, self.sig.name if not rev else "ATECC?")

    def actions(self, s):
        """What the cursor can do to this slot, with its class and why it is off."""
        out = []
        active = s["slot"] == self.sig.slot
        cfg_locked = self.st.get("configLocked", False)
        data_locked = self.st.get("dataLocked", False)
        if s["kind"] == "P256":
            if s.get("hasKey") and not active:
                out.append(("use", "USE THIS KEY", "safe", ""))
            if s.get("hasKey"):
                out.append(("pubkey", "SHOW PUBLIC KEY", "safe", ""))
                out.append(("signtest", "SIGN TEST", "safe", "" if s["extSign"] else "this slot may not sign"))
            if s["genKey"] and not s["locked"]:
                out.append(("genkey", "NEW KEY", "perm", "config zone still open" if not cfg_locked else self.sig.gate("genkey")))
        if s["kind"] == "DATA":
            if s.get("clearWrite") == "clear" and not s.get("isSecret"):
                out.append(("note", "WRITE A NOTE", "rev", "config zone still open" if not cfg_locked else ("data zone is locked" if data_locked else "")))
            if not s.get("isSecret"):
                out.append(("readnote", "READ THE BYTES", "safe", "config zone still open" if not cfg_locked else ("data zone open: reads after its lock" if not data_locked else "")))
        if s["lockable"] and not s["locked"]:
            out.append(("lockslot", "LOCK SLOT FOREVER", "perm", "config zone still open" if not cfg_locked else self.sig.gate("lock")))
        return out

    # ----------------------------------------------------------------------------- drawing
    def draw(self):
        d = self.d
        d.fill(L.BLACK)
        v = self.view
        if v == "zones":
            C.draw_zones(self)
        elif v == "list":
            self.draw_list()
        elif v == "slot":
            self.draw_slot()
        elif v == "pubkey":
            self.draw_pubkey()
        elif v == "cfg":
            C.draw_cfg(self)
        elif v == "raw":
            C.draw_raw(self)
        elif v == "diff":
            C.draw_diff(self)
        elif v == "otp":
            C.draw_otp(self)
        elif v == "counters":
            C.draw_counters(self)
        elif v == "refused":
            C.draw_refused(self)
        elif v == "rawcmd":
            C.draw_rawcmd(self)
        elif v == "confirm_write":
            C.draw_confirm_write(self)
        elif v == "confirm":
            self.draw_confirm()
        elif v == "lab":
            LN.draw_lab(self)
        elif v == "labres":
            LN.draw_labres(self)
        elif v == "why":
            LN.draw_why(self)
        elif v == "learn":
            LN.draw_learn(self)
        elif v == "card":
            LN.draw_card(self)
        elif v == "busy":
            C.header(self, "WORKING")
            d.center_text(self.msg[:28], 100, L.WHITE)
        elif v == "result":
            self.draw_result()
        if self.armhold is not None:
            C.draw_arm_bar(self)
        d.show()
        self.dirty = False

    TILE_W, TILE_H, TILE_X, TILE_Y = 56, 46, 4, 27

    def draw_list(self):
        """The 16 slots as a 4x4 field of tiles, the chip's own layout."""
        d = self.d
        C.header(self)
        cfg = self.st.get("configLocked")
        if not self.table:
            d.center_text("no slot table", 100, L.RED)
        for n in range(16):
            x = self.TILE_X + (n % 4) * (self.TILE_W + 4)
            y = self.TILE_Y + (n // 4) * (self.TILE_H + 3)
            C.draw_tile(d, self, self.row(n), x, y, self.TILE_W, self.TILE_H, sel=n == self.cur)
        C.footer(self, "A open  Y up" if cfg else "cfg OPEN: keys hidden  Y up", L.GREY if cfg else L.RED)

    def draw_slot(self):
        d = self.d
        s = self.row(self.cur)
        C.header(self)
        y = 27
        I.draw(d, "lock" if s["locked"] else C.KIND_ICON.get(s["kind"], "bytes"), 220, y - 1, T.C["perm"] if s["locked"] else C.KIND_COLOR.get(s["kind"], C.DIM))
        d.text(DESC.get(s["kind"], s["kind"]), 4, y, L.WHITE); y += 12
        d.text("%d bytes" % s.get("bytes", atecc.SLOT_BYTES[self.cur]), 4, y, L.GREY); y += 12
        if s["kind"] == "P256":
            if s.get("hasKey"):
                d.text("key " + fp(s), 4, y, L.GREEN if self.cur == self.sig.slot else L.WHITE)
                if self.cur == self.sig.slot:
                    d.text("ACTIVE", 160, y, L.GREEN)
            elif not self.st.get("configLocked"):
                d.text("hidden until the rules lock", 4, y, L.RED)
            else:
                d.text("empty", 4, y, L.YELLOW)
            y += 12
            flags = (("sign external digests", s["extSign"]), ("genkey allowed", s["genKey"]),
                     ("privwrite (import)", s["privWrite"]), ("pubkey readable", s["pubInfo"]),
                     ("limited use (counter)", s.get("limitedUse", False)), ("lockable", s["lockable"]))
        elif s["kind"] == "DATA":
            d.text("write", 12, y, L.WHITE); d.text(s.get("clearWrite", "?"), 120, y, L.GREY); y += 12
            d.text("read", 12, y, L.WHITE)
            d.text("secret" if s.get("isSecret") else ("encrypted" if s.get("encRead") else "clear"), 120, y, L.GREY); y += 12
            flags = (("lockable", s["lockable"]),)
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
            d.text("nothing to do here yet", 12, y, L.GREY)
            C.footer(self, "left/right slots  Y up")
        else:
            C.menu(self, acts, y, self.act)
            C.menu_footer(self, acts, self.act)

    def draw_pubkey(self):
        d = self.d
        s = self.row(self.cur)
        C.header(self)
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
        C.footer(self, "Y back")

    def draw_confirm(self):
        d = self.d
        kind, slot = self.action
        C.header(self, "PERMANENT")
        C.icon(d, "unlock", 4, 26, L.RED, 2)
        d.big_text("PERMANENT", 40, 26, L.RED, 2)
        d.text("! cannot be undone", 40, 44, L.RED)
        if kind == "genkey":
            body = ("NEW KEY IN SLOT %d" % slot, "The chip draws a new key from its own randomness and keeps it. The key there now is gone for good; a vault paired to it can never be spent again.")
        elif kind == "lockslot":
            body = ("LOCK SLOT %d FOREVER" % slot, "The key in it can never be replaced or removed.")
        elif kind == "lockcfg":
            body = ("SEAL THE RULES", "The config zone on the chip is frozen as it is now. The table can never change again; the data zone opens up and keys can be made.")
        elif kind == "lockdata":
            body = ("LOCK DATA ZONE", "No more clear-text writes to any slot, ever. GenKey stays allowed where the rules say.")
        else:
            body = (kind, "")
        y = 62
        d.text(body[0], 4, y, L.WHITE); y += 14
        for line in C.wrap(body[1])[:5]:
            d.text(line, 4, y, L.WHITE); y += 12
        d.center_text("hold A for 3 s", 164, L.YELLOW)
        d.rect(20, 178, 200, 14, L.WHITE)
        if self.hold is not None:
            e = time.ticks_diff(time.ticks_ms(), self.hold)
            d.fill_rect(21, 179, min(198, 198 * e // HOLD_PERM), 12, L.RED)
            d.center_text("%d" % max(1, (HOLD_PERM - e + 999) // 1000), 198, L.RED, 2)
        C.footer(self, "Y cancel")

    def draw_result(self):
        d = self.d
        C.header(self, "SEALED" if self.sealed else ("DONE" if self.ok else "ERROR"))
        y = 30
        if self.sealed:
            C.icon(d, "lock", 4, y - 6, L.GREEN, 2)
            d.big_text("SEALED", 40, y - 2, L.GREEN, 2); y += 28
        for label, ok in self.checks or ():
            C.icon(d, "check" if ok else "cross", 4, y - 4, L.GREEN if ok else L.RED)
            d.text(label[:26], 24, y, L.GREEN if ok else L.RED); y += 14
        if self.checks:
            y += 4
        for line in C.wrap(self.msg)[:9]:
            d.text(line, 4, y, L.WHITE if self.ok else L.YELLOW); y += 12
        C.footer(self, "A ok")

    # ----------------------------------------------------------------------------- input
    def tick(self, pressed, keys):
        """pressed: key names that went down this tick. keys: lcd.Keys, for held(). Returns "home" to leave."""
        self.n += 1
        v = self.view
        if v not in ("confirm", "confirm_write", "busy"):
            pressed = C.arm_tick(self, pressed, keys)
        if v == "confirm" or v == "confirm_write":
            need = HOLD_PERM if v == "confirm" else HOLD_REV
            if "Y" in pressed or (v == "confirm_write" and "B" in pressed):
                if v == "confirm_write" and "Y" in pressed:
                    self.go("diff")
                else:
                    self.hold, self.view, self.dirty = None, self.ret, True
            elif keys.held("A"):
                if self.hold is None:
                    self.hold = time.ticks_ms()
                if time.ticks_diff(time.ticks_ms(), self.hold) >= need:
                    self.hold = None
                    if v == "confirm":
                        self.run(*self.action)
                    else:
                        self.busy("writing..." if self.action[0] == "note" else "writing the config zone...")
                        C.run_write(self, self.action[0], self.action[1])
                self.dirty = True
            elif self.hold is not None:
                self.hold, self.dirty = None, True
        elif v == "busy":
            pass
        elif v == "result":
            if "A" in pressed or "Y" in pressed:
                self.checks, self.sealed = None, False
                self.view, self.dirty = self.ret, True
        elif v == "refused":
            if "A" in pressed and self.ref and self.ref.get("trace"):
                self.view_from = "refused"
                self.go("rawcmd")
            elif "Y" in pressed or "A" in pressed:
                self.view, self.dirty = self.ret, True
        elif v == "pubkey":
            if "Y" in pressed or "A" in pressed:
                self.back()
        elif v in ("raw", "diff", "otp", "counters", "rawcmd", "why"):
            C.scroll_tick(self, pressed)
            if "Y" in pressed or "A" in pressed:
                self.back()
        elif v == "card":
            LN.tick_card(self, pressed)
        elif v == "zones":
            C.tick_zones(self, pressed)
        elif v == "list":
            self.tick_list(pressed)
        elif v == "slot":
            self.tick_slot(pressed)
        elif v == "cfg":
            C.tick_cfg(self, pressed)
        elif v == "lab":
            LN.tick_lab(self, pressed)
        elif v == "labres":
            LN.tick_labres(self, pressed)
        elif v == "learn":
            LN.tick_learn(self, pressed)
        if "B" in pressed and v not in ("confirm", "confirm_write", "busy", "card", "learn"):
            LN.context(self)
        if S.armed() and self.n % 20 == 0:
            self.dirty = True       # the countdown in the header
        if self.dirty:
            self.draw()
        if self.leave:
            self.leave = False
            return "home"
        return None

    def tick_list(self, pressed):
        for k in pressed:
            if k == "up":
                self.cur = (self.cur - 4) % 16
            elif k == "down":
                self.cur = (self.cur + 4) % 16
            elif k == "left":
                self.cur = (self.cur - 1) % 16
            elif k == "right":
                self.cur = (self.cur + 1) % 16
            elif k == "A" or k == "press":
                self.go("slot")
            elif k == "Y":
                self.back()
            self.dirty = True

    def tick_slot(self, pressed):
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
                self.back()
            elif (k == "A" or k == "press") and acts:
                kind, label, cls, off = acts[self.act]
                if off:
                    self.show_result("off: " + off + ". Nothing was changed.", False)
                else:
                    self.choose(kind, self.cur)
            self.dirty = True

    def choose(self, kind, slot):
        """A live action from a slot or the config page: safe ones run, permanent ones go red."""
        self.ret = self.view
        if kind in ("use", "signtest", "readnote"):
            self.run(kind, slot)
        elif kind == "pubkey":
            self.go("pubkey")
        elif kind == "note":
            C.start_write(self, "note", slot)
        elif kind in ("genkey", "lockslot", "lockcfg", "lockdata"):
            self.action, self.hold, self.view = (kind, slot), None, "confirm"

    def run(self, kind, slot):
        self.busy({"genkey": "making a key in slot %s" % slot, "use": "switching to slot %s" % slot,
                   "signtest": "signing 32 bytes in slot %s" % slot}.get(kind, kind + "..."))
        sealed = False
        self.checks = None
        try:
            if kind == "use":
                self.sig.use(slot)
                out = "slot %d is now the signing key. the app shows paired only if the vault was deployed with it." % slot
            elif kind == "genkey":
                x, _ = self.sig.genkey(slot)
                CE.key_created(self, slot, "%08x" % (x >> 224))
                out = "new key in slot %d: %08x. record qx/qy from SHOW PUBLIC KEY before deploying a vault." % (slot, x >> 224)
            elif kind == "signtest":
                ok_sig, r, sg = self.sig.sign_test(slot)
                cnt = ""
                chip = getattr(self.sig, "chip", None)
                if chip and self.row(slot).get("limitedUse"):
                    try:
                        cnt = " Counter 0 is now %d: this slot spends one count per signature." % chip.counter(0)
                    except Exception:
                        pass
                self.checks = (("SIGNATURE VERIFIED" if ok_sig else "SIGNATURE DID NOT VERIFY", ok_sig),)
                out = "Slot %d signed SHA-256 of 'picowallet' and the Pico verified it with the slot's public key. r %08x.. s %08x..%s" % (slot, r >> 224, sg >> 224, cnt)
                if not ok_sig:
                    raise Exception(out)
            elif kind == "readnote":
                note = self.sig.read_note(slot)
                out = 'Slot %d says: "%s"' % (slot, note) if note else "Slot %d holds no text yet (all zero bytes)." % slot
            elif kind == "lockslot":
                out = str(self.sig.lock_slot(slot)) + ". The key in it can never be replaced."
                CE.sealed(self, "KEY SEALED", "slot %d can never change" % slot)
                sealed = True
            elif kind == "lockcfg":
                out = str(self.sig.lock_config()) + ". These rules can never be changed again. The data zone is open: NEW KEY in slot 0 is next."
                self.refresh()
                CE.rules_sealed(self)
                sealed = True
            elif kind == "lockdata":
                out = str(self.sig.lock_data()) + ". No more clear-text writes, ever."
                CE.sealed(self, "DATA SEALED", "no clear writes, ever")
                sealed = True
            else:
                out = "unknown action " + kind
            ok = True
        except Exception as e:
            out, ok, sealed = "%s failed: %s" % (kind, e), False, False
        self.refresh()
        self.act = 0
        self.sealed = sealed
        self.show_result(out, ok)
        if kind in ("use", "genkey", "lockcfg"):
            self.on_change()
