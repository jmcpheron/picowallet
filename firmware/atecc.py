# Minimal ATECC608 driver over I2C for MicroPython. Just what a wallet needs:
# wake, serial, lock state, the slot table, public key of a slot, sign a 32-byte digest with a slot,
# and the one-time provisioning steps (write + lock config, GenKey, lock data, lock a slot).
# Packet format and CRC follow Microchip's cryptoauthlib.
#
# How slots work, in short (datasheet sections "Configuration Zone" and "Data Zone"):
#   The chip has 16 data slots. What each one IS (a P-256 private key, a public key, an AES key,
#   plain data) and what it MAY DO (sign external digests, be regenerated with GenKey, be written,
#   be locked on its own) is a 4-byte-per-slot table in the 128-byte config zone: SlotConfig at
#   bytes 20-51 and KeyConfig at bytes 96-127. The config zone is written once and then locked
#   forever; the chip refuses GenKey and Sign until it is. Locking the DATA zone freezes clear-text
#   writes but GenKey stays allowed where the table says so. A single slot can also be locked for
#   good (KeyConfig.Lockable), after which nothing can replace the key in it.
from machine import I2C, Pin
import time

ADDR = 0x60
KNOWN_ADDRS = (0x60, 0x35, 0x6A, 0x58, 0x36, 0x59)   # Adafruit breakout, Trust&Go/TrustFLEX parts, others seen in the wild
WAKE_OK = b"\x04\x11\x33\x43"
OP_READ, OP_NONCE, OP_GENKEY, OP_SIGN, OP_RANDOM, OP_INFO, OP_WRITE, OP_LOCK = 0x02, 0x16, 0x40, 0x41, 0x1B, 0x30, 0x12, 0x17
OP_COUNTER, OP_SHA, OP_SELFTEST = 0x24, 0x47, 0x77

# The one status byte the chip answers with when it has no data for you (datasheet "Status/Error Codes").
STATUS = {0x00: "ok", 0x01: "checkmac or verify miscompare", 0x03: "parse error: the chip did not understand the command",
          0x05: "ecc fault: try again", 0x07: "self-test failed", 0x08: "health test error",
          0x0F: "execution error: not allowed in this state", 0x11: "just woke up: send the command again",
          0xEE: "watchdog about to expire", 0xFF: "crc or communication error"}
SLOT_BYTES = (36,) * 8 + (416,) + (72,) * 7     # data zone: slots 0-7, slot 8, slots 9-15


def explain(code):
    return STATUS.get(code, "unknown status 0x%02x" % code)

# Microchip's ATECC608 reference config (cryptoauthlib test/api_calib/test_calib_config.c,
# test_ecc608_configdata), byte for byte what reference/pi/signer.py wrote to chip #1, the chip
# that owns the mainnet vault. Bytes 0-15 (serial, revision) and 84-87 (lock bytes) are
# read-only and skipped by write_config. With this table (see decode_slot):
#   slot 0   P-256 private key, external sign, GenKey allowed, lockable   <- the wallet key
#   slot 2   P-256 private key, external sign, GenKey allowed
#   slot 7   P-256 private key, external sign, GenKey + encrypted PrivWrite, lockable
#   slots 11, 14, 15  P-256 public keys; 5, 10 AES keys; the rest plain data
# An earlier copy of this table in the firmware had an extra row of 0xFF and lost the last row,
# which typed slots 0-7 as "not an ECC key". Locking a chip with that would have left it unable
# to ever hold a wallet key. Never edit these bytes by hand; regenerate them from cryptoauthlib.
CONFIG = bytes([
    0x01, 0x23, 0x00, 0x00, 0x00, 0x00, 0x60, 0x00, 0x04, 0x05, 0x06, 0x07, 0xEE, 0x01, 0x01, 0x00,
    0xC0, 0x00, 0xA1, 0x00, 0xAF, 0x2F, 0xC4, 0x44, 0x87, 0x20, 0xC4, 0xF4, 0x8F, 0x0F, 0x0F, 0x0F,
    0x9F, 0x8F, 0x83, 0x64, 0xC4, 0x44, 0xC4, 0x64, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F,
    0x0F, 0x0F, 0x0F, 0x0F, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
    0x00, 0x00, 0x00, 0x00, 0xFF, 0x84, 0x03, 0xBC, 0x09, 0x69, 0x76, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0x0E, 0x40, 0x00, 0x00, 0x00, 0x00,
    0x33, 0x00, 0x1C, 0x00, 0x13, 0x00, 0x1C, 0x00, 0x3C, 0x00, 0x3A, 0x10, 0x1C, 0x00, 0x33, 0x00,
    0x1C, 0x00, 0x1C, 0x00, 0x38, 0x00, 0x30, 0x00, 0x3C, 0x00, 0x3C, 0x00, 0x32, 0x00, 0x30, 0x00,
])

KEY_TYPE = {4: "P256", 6: "AES", 7: "DATA"}


def decode_slot(cfg, slot):
    """What the config zone says about one slot. cfg = all 128 config bytes.
    kind: P256 (private key), PUB (P-256 public key), AES, DATA, or ? (reserved type)."""
    sc = cfg[20 + 2 * slot] | cfg[21 + 2 * slot] << 8
    kc = cfg[96 + 2 * slot] | cfg[97 + 2 * slot] << 8
    private = bool(kc & 1)
    ktype = (kc >> 2) & 7
    kind = KEY_TYPE.get(ktype, "?")
    if ktype == 4 and not private:
        kind = "PUB"
    wc = sc >> 12
    write_policy = ("clear", "pubinvalid", "never", "never", "encrypted", "encrypted", "never", "never")[wc >> 1]
    return {
        "slot": slot,
        "kind": kind,
        "bytes": SLOT_BYTES[slot],
        "private": private,
        "clearWrite": write_policy,       # the Write command on this slot: clear, encrypted, pubinvalid, never
        "encRead": bool(sc & 0x40),       # reads come out encrypted
        "pubInfo": bool(kc & 2),          # private key: its public half may be read out
        "lockable": bool(kc & 0x20),      # this slot can be locked on its own, forever
        "reqRandom": bool(kc & 0x40),
        "reqAuth": bool(kc & 0x80),
        "isSecret": bool(sc & 0x80),
        "extSign": private and bool(sc & 1),        # may sign digests handed in from outside
        "intSign": private and bool(sc & 2),
        "limitedUse": bool(sc & 0x20),              # every use counts against counter 0
        "genKey": private and bool(wc & 2),         # GenKey may create a new random key here
        "privWrite": private and bool(wc & 4),      # PrivWrite may import a key (encrypted)
        "locked": not (cfg[88 + (slot >> 3)] >> (slot & 7)) & 1,   # SlotLocked: bit clear = locked
    }


def diff_config(cur, new):
    """What writing `new` over `cur` would change: the writable bytes that differ (16-83, 88-127), the
    per-slot fields that change, and whether the I2C address byte (16) would move."""
    changed = [i for i in range(128) if (16 <= i < 84 or i >= 88) and cur[i] != new[i]]
    slots = []
    for n in range(16):
        a, b = decode_slot(cur, n), decode_slot(new, n)
        fields = [(k, a[k], b[k]) for k in ("kind", "extSign", "genKey", "privWrite", "pubInfo", "lockable", "isSecret", "clearWrite") if a[k] != b[k]]
        if fields:
            slots.append((n, fields))
    return {"bytes": changed, "slots": slots, "addrChanges": cur[16] != new[16]}


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


class AteccError(Exception):
    status = None       # the chip's status byte when it answered with one, else None (transport)


def scan(sda=4, scl=5, freq=100_000):
    """Every I2C address that answers. A sleeping ATECC does not ACK, so wake the bus first."""
    i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
    try:
        i2c.writeto(0, b"\x00")
    except OSError:
        pass
    time.sleep_ms(2)
    return i2c.scan()


class ATECC608:
    def __init__(self, sda=4, scl=5, addr=None, freq=100_000):
        """addr None: use 0x60 if it answers, else the first known ATECC address on the bus."""
        self.i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
        if addr is None:
            found = scan(sda, scl, freq)
            addr = ADDR if ADDR in found or not found else next((a for a in KNOWN_ADDRS if a in found), found[0])
        self.addr = addr
        self.trace = None       # the last command as sent and answered: op, p1, p2, data, resp, ms

    # --- transport ---------------------------------------------------------
    def wake(self):
        try:
            self.i2c.writeto(0, b"\x00")  # SDA held low long enough to count as the wake token
        except OSError:
            pass
        time.sleep_ms(2)
        for _ in range(3):
            try:
                if self.i2c.readfrom(self.addr, 4) == WAKE_OK:
                    return
            except OSError:
                time.sleep_ms(2)
        raise AteccError("no wake response")

    def sleep(self):
        try:
            self.i2c.writeto(self.addr, b"\x01")
        except OSError:
            pass

    def idle(self):
        try:
            self.i2c.writeto(self.addr, b"\x02")
        except OSError:
            pass

    def command(self, opcode, p1, p2, data=b"", resp_len=4, wait_ms=5, timeout_ms=300, raw=False):
        """One command packet, then its answer. A 1-byte nonzero answer is a status code and raises,
        unless raw (SelfTest answers with a bitmap that looks like one). self.trace keeps the exchange."""
        body = bytes([len(data) + 7, opcode, p1, p2 & 0xFF, p2 >> 8]) + data
        pkt = b"\x03" + body + crc16(body)
        self.trace = {"op": opcode, "p1": p1, "p2": p2, "data": bytes(data), "resp": b"", "ms": 0}
        t_send = time.ticks_ms()
        self.i2c.writeto(self.addr, pkt)
        time.sleep_ms(wait_ms)
        t0 = time.ticks_ms()
        while True:
            try:
                resp = self.i2c.readfrom(self.addr, resp_len + 3)
                break
            except OSError:
                if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                    raise AteccError("timeout on opcode 0x%02x" % opcode)
                time.sleep_ms(3)
        self.trace["ms"] = time.ticks_diff(time.ticks_ms(), t_send)
        n = resp[0]
        if n < 4 or n > len(resp):
            raise AteccError("bad length %d" % n)
        if crc16(resp[: n - 2]) != resp[n - 2 : n]:
            raise AteccError("bad crc")
        payload = resp[1 : n - 2]
        self.trace["resp"] = bytes(payload)
        if len(payload) == 1 and payload[0] != 0 and not raw:
            e = AteccError("status 0x%02x on opcode 0x%02x" % (payload[0], opcode))
            e.status = payload[0]
            raise e
        return payload

    def run(self, *args, **kw):
        """wake, one command, back to sleep."""
        self.wake()
        try:
            return self.command(*args, **kw)
        finally:
            self.sleep()

    # --- commands ----------------------------------------------------------
    def read_config(self, block):
        """32 bytes of the config zone. block 0..3."""
        return self.run(OP_READ, 0x80, block << 3, resp_len=32, wait_ms=2)

    def read_config_all(self):
        """All 128 config bytes: serial, revision, lock bytes, the slot table."""
        return b"".join(self.read_config(b) for b in range(4))

    def serial(self):
        c = self.read_config(0)
        return c[0:4] + c[8:13]

    def revision(self):
        """4 bytes; 00006002 = 608A, 00006003 = 608B."""
        return self.run(OP_INFO, 0x00, 0x0000, resp_len=4, wait_ms=2)

    def lock_state(self):
        c = self.read_config(2)
        return {"configLocked": c[87 - 64] == 0x00, "dataLocked": c[86 - 64] == 0x00}

    def random(self):
        """32 bytes from the chip's RNG. Until the config zone is locked the chip answers the fixed
        test pattern ffff0000... instead (datasheet); that is how you know it is unlocked."""
        return self.run(OP_RANDOM, 0x00, 0x0000, resp_len=32, wait_ms=25)

    # --- read-only questions (the LAB) --------------------------------------
    def info(self, mode, param=0):
        """Info: mode 0 revision, 1 KeyValid (param = slot; byte 0 is 1 when the slot holds a usable
        key), 2 State (TempKey flags), 3 GPIO. 4 bytes."""
        return self.run(OP_INFO, mode, param, resp_len=4, wait_ms=2)

    def selftest(self, mask=0x3F):
        """608 only. Runs the chip's own tests and returns the answer byte: 0 = every test passed,
        otherwise each set bit is a failed test (0 RNG, 1 ECDSA verify, 2 ECDSA sign, 3 ECDH, 4 AES,
        5 SHA), or a status code if the chip refused (the byte alone cannot tell those apart)."""
        return self.run(OP_SELFTEST, mask, 0x0000, resp_len=1, wait_ms=250, timeout_ms=1500, raw=True)[0]

    def sha256(self, data):
        """SHA-256 of up to 63 bytes, computed on the chip: Start, then End with the bytes."""
        if len(data) > 63:
            raise ValueError("63 bytes at most here")
        self.wake()
        try:
            self.command(OP_SHA, 0x00, 0x0000, resp_len=1, wait_ms=9)
            return self.command(OP_SHA, 0x02, len(data), bytes(data), resp_len=32, wait_ms=9)
        finally:
            self.sleep()

    def counter(self, idx=0):
        """Read monotonic counter 0 or 1 (never increments)."""
        return int.from_bytes(self.run(OP_COUNTER, 0x00, idx, resp_len=4, wait_ms=20), "little")

    def read_otp(self, block=0):
        """32 bytes of the OTP zone (blocks 0 and 1). Refused until the config zone is locked."""
        return self.run(OP_READ, 0x81, block << 3, resp_len=32, wait_ms=2)

    def read_data(self, slot, block=0):
        """32 bytes of a data slot. Refused until the config zone is locked, and per the slot's rules."""
        return self.run(OP_READ, 0x82, (block << 8) | (slot << 3), resp_len=32, wait_ms=2)

    def write_data(self, slot, block, data):
        """Write 32 bytes into a data slot in clear (Write zone 2). Allowed once the config zone is
        locked and while the data zone is open, where the slot's rules say clear writes are ok.
        Overwriting again is allowed, so this is reversible until the data zone is locked."""
        if len(data) != 32:
            raise ValueError("32 bytes at a time")
        if block * 32 + 32 > SLOT_BYTES[slot]:
            raise ValueError("block %d is past the end of slot %d" % (block, slot))
        self.run(OP_WRITE, 0x82, (block << 8) | (slot << 3), bytes(data), resp_len=1, wait_ms=30)

    def read_config_word(self, word):
        """4 bytes of the config zone (word 4 holds the I2C address byte)."""
        return self.run(OP_READ, 0x00, word, resp_len=4, wait_ms=2)

    def pubkey(self, slot=0):
        """Public key of the private key in `slot`: (x, y) ints. Fails on an empty slot or one
        whose KeyConfig.PubInfo is clear."""
        pub = self.run(OP_GENKEY, 0x00, slot, resp_len=64, wait_ms=120)
        return int.from_bytes(pub[:32], "big"), int.from_bytes(pub[32:], "big")

    def sign(self, digest, slot=0):
        """ECDSA over a 32-byte digest with the key in `slot`. Returns (r, s) ints, s not normalized."""
        if len(digest) != 32:
            raise ValueError("digest must be 32 bytes")
        self.wake()
        try:
            self.command(OP_NONCE, 0x03, 0x0000, digest, resp_len=1, wait_ms=8)  # pass-through -> TempKey
            sig = self.command(OP_SIGN, 0x80, slot, resp_len=64, wait_ms=120)      # external message from TempKey
        finally:
            self.sleep()
        return int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")

    def slots(self, cfg=None, probe=True):
        """The slot table as the chip has it, plus (when probe and the config is locked) whether
        each P-256 private slot holds a key and its public key."""
        if cfg is None:
            cfg = self.read_config_all()
        locked = cfg[87] == 0x00
        out = []
        for n in range(16):
            s = decode_slot(cfg, n)
            if s["kind"] == "P256":
                s["hasKey"] = False
                if probe and locked and s["pubInfo"]:
                    try:
                        x, y = self.pubkey(n)
                        s["hasKey"] = True
                        s["qx"], s["qy"] = x, y
                    except AteccError:
                        pass
            out.append(s)
        return out

    # --- provisioning (once per fresh chip) --------------------------------
    def write_config(self, cfg=CONFIG):
        """Write the config zone in 4-byte words, skipping the read-only words (0-3 and 21), then read
        it back. REVERSIBLE while the zone is open: it can be written again, and again. Refuses to move
        the I2C address byte (16), since the chip would answer somewhere else after its next wake.
        Returns how many bytes changed; raises if the readback differs from what was written."""
        assert len(cfg) == 128
        before = self.read_config_all()
        if before[87] == 0x00:
            raise AteccError("config zone is locked: it can never be written again")
        if cfg[16] != before[16]:
            raise AteccError("refusing to change the I2C address byte (0x%02x -> 0x%02x)" % (before[16], cfg[16]))
        self.wake()
        try:
            for word in range(32):
                if word < 4 or word == 21:
                    continue
                self.command(OP_WRITE, 0x00, word, cfg[word * 4:word * 4 + 4], resp_len=1, wait_ms=30)
        finally:
            self.sleep()
        after = self.read_config_all()
        bad = [i for i in range(128) if (16 <= i < 84 or i >= 88) and after[i] != cfg[i]]
        if bad:
            raise AteccError("readback differs at %d bytes (first at byte %d)" % (len(bad), bad[0]))
        return sum(1 for i in range(128) if before[i] != after[i])

    def lock_config(self):
        """PERMANENT. Lock the config zone (no CRC check, mode 0x80). Refuses if already locked."""
        if self.lock_state()["configLocked"]:
            raise AteccError("config zone is already locked")
        self.run(OP_LOCK, 0x80, 0x0000, resp_len=1, wait_ms=35)
        if not self.lock_state()["configLocked"]:
            raise AteccError("lock command returned but the zone is still unlocked")

    def lock_data(self):
        """PERMANENT. Lock the data (and OTP) zone, mode 0x81: no more clear-text slot writes.
        GenKey keeps working on slots whose config allows it."""
        st = self.lock_state()
        if not st["configLocked"]:
            raise AteccError("lock the config zone first")
        if st["dataLocked"]:
            raise AteccError("data zone is already locked")
        self.run(OP_LOCK, 0x81, 0x0000, resp_len=1, wait_ms=35)
        if not self.lock_state()["dataLocked"]:
            raise AteccError("lock command returned but the data zone is still unlocked")

    def lock_slot(self, slot):
        """PERMANENT. Lock one slot (mode 0x82 | slot << 2). The key in it can never be replaced.
        Needs KeyConfig.Lockable for that slot."""
        cfg = self.read_config_all()
        s = decode_slot(cfg, slot)
        if cfg[87] != 0x00:
            raise AteccError("lock the config zone first")
        if not s["lockable"]:
            raise AteccError("slot %d is not lockable" % slot)
        if s["locked"]:
            raise AteccError("slot %d is already locked" % slot)
        self.run(OP_LOCK, 0x82 | (slot << 2), 0x0000, resp_len=1, wait_ms=35)
        if not decode_slot(self.read_config_all(), slot)["locked"]:
            raise AteccError("lock command returned but slot %d is still unlocked" % slot)

    def genkey_new(self, slot=0):
        """Create a NEW random private key in `slot`, replacing whatever was there. Returns (x, y)."""
        pub = self.run(OP_GENKEY, 0x04, slot, resp_len=64, wait_ms=120)
        return int.from_bytes(pub[:32], "big"), int.from_bytes(pub[32:], "big")

    def status(self, slot=0):
        s = self.lock_state()
        s["i2cAddr"] = "0x%02x" % self.addr
        s["serial"] = "".join("%02x" % b for b in self.serial())
        try:
            s["revision"] = "".join("%02x" % b for b in self.revision())
        except AteccError:
            pass
        s["slot"] = slot
        try:
            self.pubkey(slot)
            s["hasKey"] = True
        except AteccError as e:
            s["hasKey"] = False
            s["note"] = str(e)
        return s
