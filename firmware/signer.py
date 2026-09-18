# The thing that holds the keys. Two backends with one shape:
#   slot                       the active slot; sign() and pubkey() use it unless told otherwise
#   slots() -> [dict]          the slot table: kind, hasKey, qx/qy, locked, genKey, ... (see atecc.decode_slot)
#   pubkey(slot=None) -> (x, y)
#   sign(digest, slot=None) -> (r, s) low-s
#   genkey(slot=None) -> (x, y)      NEW random key in the slot, replacing the old one
#   use(slot)                        make a slot the active signer (persisted in slot.txt)
#   lock_config() / lock_data() / lock_slot(slot)      permanent, gated by secrets.ALLOW_LOCK
#   status() -> dict                 what the app sees on announce
#   allowed(what) -> bool            "genkey" or "lock": may it happen right now (secrets.py flag AND the wallet is armed)
#   gate(what) -> str                "" when allowed, else why not ("not armed", "ALLOW_LOCK is False")
#   write_config() / restore_snapshot()   REVERSIBLE while the config zone is open; snapshot() the original bytes
#   provision()                      write the wallet config and lock it (the app's lock-config command)
#   config() -> bytes                the 128 config bytes (the software signer fakes them)
#   random() -> bytes                32 bytes from the chip's RNG, a harmless "is it alive" test
#   name
# SoftSigner: P-256 keys in files on the Pico's flash, one per slot. Only until the ATECC608 is wired.
# ChipSigner: the ATECC608 over I2C. The keys never leave the chip.
import os
import time
import p256

KEY_FILE = "key.bin"        # slot 0 of the software signer, the file older firmware used
SLOT_FILE = "slot.txt"      # the active slot, both backends
SOFT_SLOTS = 8              # the software signer pretends to be a chip with 8 P-256 slots


def _read_slot():
    try:
        return int(open(SLOT_FILE).read().strip())
    except Exception:
        return 0


def _write_slot(n):
    with open(SLOT_FILE, "w") as f:
        f.write(str(n))


# ARM: permanent actions also need someone at the device. Hold B and Y together for 3 s on the
# wallet (chipmap.py) and it is armed for a minute; every red action, including the ones the app
# can request over WiFi, is refused until then. This lives here, not on the chip: it is the wallet's
# own safety catch, the chip knows nothing about it.
ARM_SECONDS = 60
_armed_until = None


def arm(seconds=ARM_SECONDS):
    global _armed_until
    _armed_until = time.ticks_add(time.ticks_ms(), seconds * 1000)


def disarm():
    global _armed_until
    _armed_until = None


def armed():
    """Seconds left on the arm, 0 when not armed."""
    if _armed_until is None:
        return 0
    left = time.ticks_diff(_armed_until, time.ticks_ms())
    return (left + 999) // 1000 if left > 0 else 0


def flag(name):
    """A secrets.py flag; False when secrets.py is missing."""
    try:
        import secrets
    except ImportError:
        return False        # no secrets.py on the board: every permanent action is off
    return bool(getattr(secrets, name, False))


def gate(what):
    """Why a permanent action may not run now: "" when it may."""
    name = "ALLOW_GENKEY" if what == "genkey" else "ALLOW_LOCK"
    if not flag(name):
        return "%s is False on the board" % name
    if not armed():
        return "not armed: hold B+Y 3 s"
    return ""


def _allowed(name):
    return flag(name) and armed() > 0


def _refused(what):
    return "%s refused: %s" % (what, gate(what))


def _fp(x):
    """8 hex chars of qx: enough to tell keys apart on a 240 px screen."""
    return "%08x" % (x >> 224)


class SoftSigner:
    name = "pico-soft"

    def __init__(self):
        self.slot = _read_slot()
        self._pub = {}

    def _file(self, slot):
        return KEY_FILE if slot == 0 else "key%d.bin" % slot

    def _scalar(self, slot):
        f = self._file(slot)
        if f in os.listdir():
            return int.from_bytes(open(f, "rb").read(), "big")
        if slot == 0:
            # the first boot of a bare Pico makes a slot-0 key on its own, as before
            d = p256.rand_scalar()
            open(f, "wb").write(d.to_bytes(32, "big"))
            return d
        return None

    def pubkey(self, slot=None):
        slot = self.slot if slot is None else slot
        if slot not in self._pub:
            d = self._scalar(slot)
            if d is None:
                raise Exception("slot %d is empty" % slot)
            self._pub[slot] = p256.pubkey(d)
        return self._pub[slot]

    def sign(self, digest, slot=None):
        slot = self.slot if slot is None else slot
        d = self._scalar(slot)
        if d is None:
            raise Exception("slot %d is empty" % slot)
        return p256.sign(d, digest)

    def genkey(self, slot=None):
        slot = self.slot if slot is None else slot
        if slot >= SOFT_SLOTS:
            raise Exception("slot %d is not a key slot" % slot)
        d = p256.rand_scalar()
        open(self._file(slot), "wb").write(d.to_bytes(32, "big"))
        self._pub[slot] = p256.pubkey(d)
        return self._pub[slot]

    def use(self, slot):
        self.pubkey(slot)   # must hold a key
        self.slot = slot
        _write_slot(slot)

    def slots(self):
        out = []
        for n in range(16):
            s = {"slot": n, "kind": "P256" if n < SOFT_SLOTS else "DATA", "locked": False, "lockable": False,
                 "genKey": n < SOFT_SLOTS, "extSign": n < SOFT_SLOTS, "pubInfo": n < SOFT_SLOTS,
                 "privWrite": False, "limitedUse": False, "hasKey": False}
            if n < SOFT_SLOTS:
                try:
                    s["qx"], s["qy"] = self.pubkey(n)
                    s["hasKey"] = True
                except Exception:
                    pass
            out.append(s)
        return out

    def lock_config(self):
        return "software key: nothing to lock"

    def lock_data(self):
        return "software key: nothing to lock"

    def lock_slot(self, slot):
        return "software key: nothing to lock"

    def allowed(self, what):
        return True

    def gate(self, what):
        return ""

    def config(self):
        from atecc import CONFIG
        return CONFIG

    def snapshot(self):
        return None

    def write_config(self):
        return 0

    def restore_snapshot(self):
        return 0

    def provision(self):
        return "software key: nothing to lock"

    def sign_test(self, slot=None):
        import hashlib
        slot = self.slot if slot is None else slot
        digest = hashlib.sha256(b"picowallet").digest()
        r, s = self.sign(digest, slot)
        qx, qy = self.pubkey(slot)
        return p256.verify(qx, qy, digest, r, s), r, s

    def write_note(self, text, slot=12):
        raise Exception("software key: no data slots")

    def read_note(self, slot=12):
        raise Exception("software key: no data slots")

    def random(self):
        return os.urandom(32)

    def status(self):
        st = {"configLocked": True, "dataLocked": False, "slot": self.slot, "activeSlot": self.slot,
              "note": "software keys on the Pico (no chip yet)"}
        try:
            x, _ = self.pubkey()
            st["hasKey"] = True
            st["fingerprint"] = _fp(x)
        except Exception:
            st["hasKey"] = False
        st["slots"] = summary(self.slots())
        return st


class ChipSigner:
    name = "atecc608"

    def __init__(self):
        from atecc import ATECC608
        self.chip = ATECC608()
        self.slot = _read_slot()
        self._pub = {}
        self._slots = None      # cached table; every key op invalidates it
        self._serial = None

    def serial(self):
        if self._serial is None:
            self._serial = "".join("%02x" % b for b in self.chip.serial())
        return self._serial

    def pubkey(self, slot=None):
        slot = self.slot if slot is None else slot
        if slot not in self._pub:
            self._pub[slot] = self.chip.pubkey(slot)
        return self._pub[slot]

    def sign(self, digest, slot=None):
        slot = self.slot if slot is None else slot
        r, s = self.chip.sign(digest, slot)
        if s > p256.N // 2:
            s = p256.N - s
        return r, s

    def genkey(self, slot=None):
        """Only when secrets.ALLOW_GENKEY is True: this REPLACES the key in the slot. A vault paired
        to the old key can never be spent again."""
        slot = self.slot if slot is None else slot
        if not _allowed("ALLOW_GENKEY"):
            raise Exception(_refused("genkey"))
        self._slots = None
        self._pub.pop(slot, None)
        self._pub[slot] = self.chip.genkey_new(slot)
        return self._pub[slot]

    def use(self, slot):
        self.pubkey(slot)   # must hold a readable key
        self.slot = slot
        _write_slot(slot)

    def slots(self):
        if self._slots is None:
            self._slots = self.chip.slots()
        return self._slots

    # --- the config zone: reversible while open, then sealed ---------------
    def snapshot_path(self):
        return "snapshot-%s.bin" % self.serial()

    def snapshot(self):
        """This chip's config bytes as this wallet first saw them, or None before the first write."""
        p = self.snapshot_path()
        return open(p, "rb").read() if p in os.listdir() else None

    def save_snapshot(self):
        """Keep the original 128 bytes once, before anything is written. Never overwritten."""
        p = self.snapshot_path()
        if p in os.listdir():
            return False
        with open(p, "wb") as f:
            f.write(self.chip.read_config_all())
        return True

    def write_config(self):
        """REVERSIBLE while the config zone is open: write the wallet's slot table (atecc.CONFIG) and
        read it back, without locking. The chip's original bytes are snapshotted first."""
        self.save_snapshot()
        self._slots = None
        return self.chip.write_config()

    def restore_snapshot(self):
        """REVERSIBLE: put the snapshot's bytes back on the chip (the config zone must still be open)."""
        snap = self.snapshot()
        if snap is None:
            raise Exception("no snapshot saved for this chip yet")
        self._slots = None
        return self.chip.write_config(snap)

    def lock_config(self):
        """PERMANENT. Locks whatever table is on the chip now. Needs ALLOW_LOCK and the wallet armed."""
        if not _allowed("ALLOW_LOCK"):
            raise Exception(_refused("lock"))
        self._slots = None
        self.chip.lock_config()
        return "config zone locked"

    def provision(self):
        """The app's lock-config command: write the wallet config, then lock it. PERMANENT."""
        if not _allowed("ALLOW_LOCK"):
            raise Exception(_refused("lock"))
        self.write_config()
        self.chip.lock_config()
        self._slots = None
        return "config zone written and locked"

    def lock_data(self):
        if not _allowed("ALLOW_LOCK"):
            raise Exception(_refused("lock"))
        self._slots = None
        self.chip.lock_data()
        return "data zone locked"

    def lock_slot(self, slot):
        if not _allowed("ALLOW_LOCK"):
            raise Exception(_refused("lock"))
        self._slots = None
        self.chip.lock_slot(slot)
        return "slot %d locked" % slot

    def sign_test(self, slot=None):
        """Sign SHA-256 of b"picowallet" with the slot and verify it on the Pico. Returns
        (verified, r, s). A signature spends one count on counter 0 if the slot has LimitedUse."""
        import hashlib
        slot = self.slot if slot is None else slot
        digest = hashlib.sha256(b"picowallet").digest()
        r, s = self.sign(digest, slot)
        qx, qy = self.pubkey(slot)
        return p256.verify(qx, qy, digest, r, s), r, s

    def write_note(self, text, slot=12):
        """REVERSIBLE while the data zone is open: put a short line into a clear data slot (with
        the wallet config, slots 12 and 13 are the clear ones: 72 bytes, read and written in clear)."""
        b = text.encode()[:32]
        b = b + bytes(32 - len(b))
        self.chip.write_data(slot, 0, b)
        return len(text)

    def read_note(self, slot=12):
        b = self.chip.read_data(slot, 0)
        return bytes(b).rstrip(b"\x00").decode()

    def allowed(self, what):
        return _allowed("ALLOW_GENKEY" if what == "genkey" else "ALLOW_LOCK")

    def gate(self, what):
        return gate(what)

    def config(self):
        return self.chip.read_config_all()

    def random(self):
        return self.chip.random()

    def status(self):
        st = self.chip.status(self.slot)
        st["allowLock"], st["allowGenkey"] = flag("ALLOW_LOCK"), flag("ALLOW_GENKEY")
        st["armed"] = armed()
        st["activeSlot"] = self.slot
        if st.get("hasKey"):
            st["fingerprint"] = _fp(self.pubkey()[0])
        try:
            st["slots"] = summary(self.slots())
        except Exception as e:
            st["note"] = "slot table: %s" % e
        return st


def summary(slots):
    """The slot table without the big numbers, small enough to send on every announce."""
    out = []
    for s in slots:
        if s["kind"] == "P256":
            row = {"slot": s["slot"], "kind": s["kind"], "hasKey": s.get("hasKey", False), "locked": s["locked"],
                   "genKey": s["genKey"], "lockable": s["lockable"]}
            if s.get("hasKey"):
                row["fingerprint"] = _fp(s["qx"])
            out.append(row)
    return out


def load():
    """ChipSigner if an ATECC answers on the bus, else the software key."""
    try:
        s = ChipSigner()
        s.chip.wake()
        s.chip.sleep()
        return s
    except Exception as e:
        print("no chip (%s), using software key" % e)
        return SoftSigner()
