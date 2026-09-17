# The thing that holds the keys. Two backends with one shape:
#   slot                       the active slot; sign() and pubkey() use it unless told otherwise
#   slots() -> [dict]          the slot table: kind, hasKey, qx/qy, locked, genKey, ... (see atecc.decode_slot)
#   pubkey(slot=None) -> (x, y)
#   sign(digest, slot=None) -> (r, s) low-s
#   genkey(slot=None) -> (x, y)      NEW random key in the slot, replacing the old one
#   use(slot)                        make a slot the active signer (persisted in slot.txt)
#   lock_config() / lock_data() / lock_slot(slot)      permanent, gated by secrets.ALLOW_LOCK
#   status() -> dict                 what the app sees on announce
#   name
# SoftSigner: P-256 keys in files on the Pico's flash, one per slot. Only until the ATECC608 is wired.
# ChipSigner: the ATECC608 over I2C. The keys never leave the chip.
import os
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


def _allowed(flag):
    import secrets
    return getattr(secrets, flag, False)


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
            raise Exception("genkey refused: set ALLOW_GENKEY = True in secrets.py on the Pico first")
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

    def lock_config(self):
        """Only when secrets.ALLOW_LOCK is True. Writes the reference config, then locks it. Permanent."""
        if not _allowed("ALLOW_LOCK"):
            raise Exception("lock refused: set ALLOW_LOCK = True in secrets.py on the Pico first")
        self._slots = None
        self.chip.write_config()
        self.chip.lock_config()
        return "config zone locked"

    def lock_data(self):
        if not _allowed("ALLOW_LOCK"):
            raise Exception("lock refused: set ALLOW_LOCK = True in secrets.py on the Pico first")
        self._slots = None
        self.chip.lock_data()
        return "data zone locked"

    def lock_slot(self, slot):
        if not _allowed("ALLOW_LOCK"):
            raise Exception("lock refused: set ALLOW_LOCK = True in secrets.py on the Pico first")
        self._slots = None
        self.chip.lock_slot(slot)
        return "slot %d locked" % slot

    def status(self):
        st = self.chip.status(self.slot)
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
