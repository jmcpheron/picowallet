# A virtual ATECC608 on the emulator's I2C bus at 0x60. Speaks the chip's packet protocol
# (wake token, 0x03 command packets with CRC-16, count+payload+CRC responses) so firmware/atecc.py
# runs here unchanged. Models what a wallet touches: the config zone and its locks, the slot table
# (SlotConfig / KeyConfig), GenKey, Nonce pass-through + Sign, Random, Info, per-slot locks.
# Also answered, read-only: Info KeyValid/State, SelfTest (all pass), SHA-256, Counter reads, and
# Read of the OTP and data zones once the config zone is locked (zeros; writes there are not
# modeled). Not modeled: MAC/encrypted anything, the watchdog, counter increments.
#
# A fresh emulator answers like a real fresh part: the factory config of an Adafruit 4314 breakout
# (UPSTREAM.md section 3: slots 0-2 already typed P-256, GenKey allowed), config zone unlocked, and
# Random returning the datasheet's fixed pattern until the lock. The state persists across reboots
# through the host (server: emu/chip.json). wipe() / provision() reset it.
import json
import _emu

ADDR = 0x60
WAKE = b"\x04\x11\x33\x43"
STATUS_OK, STATUS_PARSE, STATUS_EXEC, STATUS_CRC = 0x00, 0x03, 0x0F, 0xFF
OP_READ, OP_NONCE, OP_GENKEY, OP_SIGN, OP_RANDOM, OP_INFO, OP_WRITE, OP_LOCK = 0x02, 0x16, 0x40, 0x41, 0x1B, 0x30, 0x12, 0x17
OP_COUNTER, OP_SHA, OP_SELFTEST = 0x24, 0x47, 0x77
SLOT_BYTES = (36,) * 8 + (416,) + (72,) * 7

# what a fresh part answers: the serial (bytes 0-3, 8-12) and revision 00006002 (608A) of the
# virtual chip, then byte for byte the factory table read off a real Adafruit breakout on
# 2026-09-16: I2C address 0xC0, SlotConfig 2083 2087 208f for slots 0-2, lock bytes 86/87 = 0x55,
# SlotLocked = 0xFFFF, KeyConfig 0033 for slots 0-2 (P-256 private, GenKey allowed).
FRESH = bytearray(bytes([
    0x01, 0x23, 0xE1, 0x00, 0x00, 0x00, 0x60, 0x02, 0xE1, 0xE1, 0xE1, 0xE1, 0xEE, 0xC1, 0x55, 0x00,
    0xC0, 0x00, 0x00, 0x00, 0x83, 0x20, 0x87, 0x20, 0x8F, 0x20, 0xC4, 0x8F, 0x8F, 0x8F, 0x8F, 0x8F,
    0x9F, 0x8F, 0xAF, 0x8F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xAF, 0x8F, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x55, 0x55, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x33, 0x00, 0x33, 0x00, 0x33, 0x00, 0x1C, 0x00, 0x1C, 0x00, 0x1C, 0x00, 0x1C, 0x00, 0x1C, 0x00,
    0x3C, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x1C, 0x00,
]))
FIXED_RANDOM = bytes([0xFF, 0xFF, 0x00, 0x00]) * 8     # what an unlocked chip answers to Random


def crc16(data):
    crc = 0
    for b in data:
        for shift in range(8):
            data_bit = (b >> shift) & 1
            crc_bit = (crc >> 15) & 1
            crc = (crc << 1) & 0xFFFF
            if data_bit != crc_bit:
                crc ^= 0x8005
    return bytes([crc & 0xFF, crc >> 8])


class Chip:
    def __init__(self):
        self.cfg = bytearray(FRESH)
        self.keys = {}          # slot -> private scalar
        self.counters = [0, 0]
        self.otp = bytearray(64)
        self.data = {}          # slot -> bytearray, on first read
        self.sha = None
        self.awake = False
        self.tempkey = None
        self.resp = b""
        self.load()

    # --- persistence through the host ----------------------------------------------------
    def load(self):
        try:
            raw = _emu.chip_load()
        except Exception:
            raw = None
        if not raw:
            return
        try:
            st = json.loads(raw)
            self.cfg = bytearray(bytes.fromhex(st["config"]))
            self.keys = {int(k): int(v, 16) for k, v in st.get("keys", {}).items()}
            self.counters = list(st.get("counters", [0, 0]))
        except Exception as e:
            print("atecc_sim: bad saved state (%s), starting blank" % e)

    def save(self):
        st = {"config": "".join("%02x" % b for b in self.cfg), "keys": {str(k): "%064x" % v for k, v in self.keys.items()},
              "counters": self.counters}
        try:
            _emu.chip_save(json.dumps(st))
        except Exception as e:
            print("atecc_sim: could not save state: %s" % e)

    # --- config zone helpers ---------------------------------------------------------------
    def config_locked(self):
        return self.cfg[87] == 0x00

    def data_locked(self):
        return self.cfg[86] == 0x00

    def slot_cfg(self, slot):
        return self.cfg[20 + 2 * slot] | self.cfg[21 + 2 * slot] << 8

    def key_cfg(self, slot):
        return self.cfg[96 + 2 * slot] | self.cfg[97 + 2 * slot] << 8

    def slot_locked(self, slot):
        return not (self.cfg[88 + (slot >> 3)] >> (slot & 7)) & 1

    def is_p256_private(self, slot):
        kc = self.key_cfg(slot)
        return bool(kc & 1) and (kc >> 2) & 7 == 4

    # --- bus ---------------------------------------------------------------------------------
    def write(self, buf):
        """One I2C write to 0x60. Word address byte first: 0x01 sleep, 0x02 idle, 0x03 command."""
        if not self.awake:
            raise OSError(5, "EIO: chip is asleep")
        wa = buf[0]
        if wa == 0x01 or wa == 0x02:
            self.awake = False
            self.tempkey = None
            self.resp = b""
            return
        if wa != 0x03:
            raise OSError(5, "EIO: unknown word address 0x%02x" % wa)
        pkt = bytes(buf[1:])
        if len(pkt) < 7 or pkt[0] != len(pkt) or crc16(pkt[:-2]) != pkt[-2:]:
            self.resp = self._status(STATUS_CRC)
            return
        opcode, p1, p2 = pkt[1], pkt[2], pkt[3] | pkt[4] << 8
        data = pkt[5:-2]
        try:
            out = self.execute(opcode, p1, p2, data)
        except _Fail as f:
            out = self._status(f.code)
        self.resp = out

    def read(self, n):
        if not self.awake:
            raise OSError(5, "EIO: chip is asleep")
        if not self.resp:
            raise OSError(5, "EIO: busy")   # the driver retries until the wait time has passed
        out = self.resp[:n]
        return out + bytes(n - len(out))

    def wake_token(self):
        self.awake = True
        self.tempkey = None
        self.resp = WAKE

    def _status(self, code):
        body = bytes([4, code])
        return body + crc16(body)

    def _data(self, payload):
        body = bytes([len(payload) + 3]) + payload
        return body + crc16(body)

    # --- commands ----------------------------------------------------------------------------
    def execute(self, opcode, p1, p2, data):
        if opcode == OP_INFO:
            mode = p1 & 0x0F
            if mode == 0:
                return self._data(bytes(self.cfg[4:8]))
            if mode == 1:       # KeyValid: byte 0 is 1 when the slot holds a usable key
                return self._data(bytes([1 if (p2 & 0xF) in self.keys and self.config_locked() else 0, 0, 0, 0]))
            if mode == 2:       # State: bit 7 of byte 0 = TempKey valid (the rest is not modeled)
                return self._data(bytes([0x80 if self.tempkey else 0x00, 0, 0, 0]))
            if mode == 3:       # GPIO
                return self._data(bytes(4))
            raise _Fail(STATUS_PARSE)
        if opcode == OP_RANDOM:
            if not self.config_locked():
                return self._data(FIXED_RANDOM)    # datasheet: a fixed pattern until the config lock
            return self._data(bytes(_emu.random(32)))
        if opcode == OP_SELFTEST:
            return self._data(b"\x00")             # every test passes
        if opcode == OP_SHA:
            return self.sha_cmd(p1 & 0x07, p2, data)
        if opcode == OP_COUNTER:
            if p2 > 1:
                raise _Fail(STATUS_PARSE)
            if p1 & 1:
                self.counters[p2] += 1
                self.save()
            return self._data(self.counters[p2].to_bytes(4, "little"))
        if opcode == OP_READ:
            zone = p1 & 3
            if zone == 3:
                raise _Fail(STATUS_PARSE)
            if zone != 0 and not self.config_locked():
                raise _Fail(STATUS_EXEC)      # data and OTP are hidden until the config zone is locked
            if zone == 1:
                block = p2 >> 3
                if block > 1 or not p1 & 0x80:
                    raise _Fail(STATUS_PARSE)
                return self._data(bytes(self.otp[block * 32:block * 32 + 32]))
            if zone == 2:
                slot, block = (p2 >> 3) & 0xF, p2 >> 8
                if block * 32 + 32 > SLOT_BYTES[slot] or not p1 & 0x80:
                    raise _Fail(STATUS_PARSE)
                if self.slot_cfg(slot) & 0x80:
                    raise _Fail(STATUS_EXEC)  # IsSecret: never readable in clear
                buf = self.data.setdefault(slot, bytearray(SLOT_BYTES[slot]))
                return self._data(bytes(buf[block * 32:block * 32 + 32]))
            if p1 & 0x80:
                block = p2 >> 3
                if block > 3:
                    raise _Fail(STATUS_PARSE)
                return self._data(bytes(self.cfg[block * 32:block * 32 + 32]))
            if p2 > 31:
                raise _Fail(STATUS_PARSE)
            return self._data(bytes(self.cfg[p2 * 4:p2 * 4 + 4]))
        if opcode == OP_WRITE:
            if p1 & 3 != 0 or p1 & 0x80 or len(data) != 4:
                raise _Fail(STATUS_PARSE)
            if self.config_locked() or p2 < 4 or p2 == 21 or p2 > 31:
                raise _Fail(STATUS_EXEC)     # locked zone, or the read-only words
            self.cfg[p2 * 4:p2 * 4 + 4] = data
            self.save()
            return self._status(STATUS_OK)
        if opcode == OP_LOCK:
            return self.lock(p1)
        if opcode == OP_GENKEY:
            return self.genkey(p1, p2)
        if opcode == OP_NONCE:
            if p1 & 3 != 3 or len(data) != 32:
                raise _Fail(STATUS_PARSE)     # only pass-through mode is modeled
            self.tempkey = bytes(data)
            return self._status(STATUS_OK)
        if opcode == OP_SIGN:
            return self.sign(p1, p2)
        raise _Fail(STATUS_PARSE)

    def sha_cmd(self, mode, length, data):
        try:
            import hashlib
        except ImportError:
            raise _Fail(STATUS_PARSE)
        if mode == 0:
            self.sha = hashlib.sha256()
            return self._status(STATUS_OK)
        if self.sha is None:
            raise _Fail(STATUS_EXEC)
        if mode == 1:
            if len(data) != 64:
                raise _Fail(STATUS_PARSE)
            self.sha.update(data)
            return self._status(STATUS_OK)
        if mode == 2:
            if len(data) != length or length > 63:
                raise _Fail(STATUS_PARSE)
            self.sha.update(data)
            out, self.sha = self.sha.digest(), None
            return self._data(out)
        raise _Fail(STATUS_PARSE)

    def lock(self, mode):
        what = mode & 3
        if what == 0:
            if self.config_locked():
                raise _Fail(STATUS_EXEC)
            self.cfg[87] = 0x00
        elif what == 1:
            if not self.config_locked() or self.data_locked():
                raise _Fail(STATUS_EXEC)
            self.cfg[86] = 0x00
        elif what == 2:
            slot = (mode >> 2) & 0xF
            if not self.config_locked() or not self.key_cfg(slot) & 0x20 or self.slot_locked(slot):
                raise _Fail(STATUS_EXEC)      # KeyConfig.Lockable clear, or already locked
            self.cfg[88 + (slot >> 3)] &= ~(1 << (slot & 7)) & 0xFF
        else:
            raise _Fail(STATUS_PARSE)
        self.save()
        return self._status(STATUS_OK)

    def genkey(self, mode, slot):
        import p256
        if slot > 15:
            raise _Fail(STATUS_PARSE)
        if not self.config_locked() or not self.is_p256_private(slot):
            raise _Fail(STATUS_EXEC)          # a blank chip, or the slot is not a private key
        if mode & 0x04:
            # create: SlotConfig.WriteConfig bit 13 (GenKey allowed) and the slot not locked
            if not self.slot_cfg(slot) >> 13 & 1 or self.slot_locked(slot):
                raise _Fail(STATUS_EXEC)
            self.keys[slot] = p256.rand_scalar()
            self.save()
        elif mode & 0x0F:
            raise _Fail(STATUS_PARSE)
        else:
            # public key of the stored key: needs a key and KeyConfig.PubInfo
            if slot not in self.keys or not self.key_cfg(slot) & 2:
                raise _Fail(STATUS_EXEC)
        x, y = p256.pubkey(self.keys[slot])
        return self._data(x.to_bytes(32, "big") + y.to_bytes(32, "big"))

    def sign(self, mode, slot):
        import p256
        if not mode & 0x80:
            raise _Fail(STATUS_PARSE)         # only external (TempKey) signing is modeled
        if slot > 15 or self.tempkey is None:
            raise _Fail(STATUS_EXEC)
        if not self.config_locked() or not self.is_p256_private(slot) or slot not in self.keys:
            raise _Fail(STATUS_EXEC)
        if not self.slot_cfg(slot) & 1:
            raise _Fail(STATUS_EXEC)          # ReadKey bit 0: external signatures not permitted
        digest, self.tempkey = self.tempkey, None
        r, s = p256.sign(self.keys[slot], digest)
        return self._data(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


class _Fail(Exception):
    def __init__(self, code):
        self.code = code


_chip = None


def chip():
    global _chip
    if _chip is None:
        _chip = Chip()
    return _chip


# --- knobs for tools/emu chip ... and sketches -------------------------------------------
def wipe():
    """Back to a fresh part: the factory table, config unlocked, no keys. Reboot after."""
    c = chip()
    c.cfg = bytearray(FRESH)
    c.keys = {}
    c.counters = [0, 0]
    c.save()
    return "chip wiped: fresh, config zone unlocked"


def provision(slot=0):
    """A chip as the wallet ships it: reference config written and locked, a fresh key in `slot`."""
    import p256
    from atecc import CONFIG
    c = chip()
    cfg = bytearray(CONFIG)
    cfg[0:16] = FRESH[0:16]
    cfg[84:88] = bytes([0x00, 0x00, 0x00, 0x00])   # data zone stays unlocked, config locked
    cfg[86] = 0x55
    c.cfg = cfg
    c.keys = {slot: p256.rand_scalar()}
    c.save()
    return "chip provisioned: config locked, key in slot %d" % slot


def state():
    c = chip()
    return {"configLocked": c.config_locked(), "dataLocked": c.data_locked(), "keys": sorted(c.keys),
            "slotLocked": [n for n in range(16) if c.slot_locked(n)]}
