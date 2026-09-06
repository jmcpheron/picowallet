# The thing that holds the key. Two backends with one shape:
#   pubkey() -> (x, y)      sign(digest) -> (r, s) low-s      status() -> dict      name
# SoftSigner: P-256 key in a file on the Pico's flash. Only until the ATECC608 is wired.
# ChipSigner: the ATECC608 over I2C. The key never leaves the chip.
import os
import p256

KEY_FILE = "key.bin"


class SoftSigner:
    name = "pico-soft"

    def __init__(self):
        if KEY_FILE in os.listdir():
            self.d = int.from_bytes(open(KEY_FILE, "rb").read(), "big")
        else:
            self.d = p256.rand_scalar()
            open(KEY_FILE, "wb").write(self.d.to_bytes(32, "big"))
        self._pub = p256.pubkey(self.d)

    def pubkey(self):
        return self._pub

    def sign(self, digest):
        return p256.sign(self.d, digest)

    def genkey(self):
        self.d = p256.rand_scalar()
        open(KEY_FILE, "wb").write(self.d.to_bytes(32, "big"))
        self._pub = p256.pubkey(self.d)
        return self._pub

    def status(self):
        return {"configLocked": True, "dataLocked": False, "slot": 0, "hasKey": True, "note": "software key on the Pico (no chip yet)"}


class ChipSigner:
    name = "atecc608"

    def __init__(self):
        from atecc import ATECC608
        self.chip = ATECC608()
        self._pub = None

    def pubkey(self):
        if self._pub is None:
            self._pub = self.chip.pubkey()
        return self._pub

    def sign(self, digest):
        r, s = self.chip.sign(digest)
        if s > p256.N // 2:
            s = p256.N - s
        return r, s

    def genkey(self):
        raise Exception("refusing to replace the chip key from the app")

    def status(self):
        return self.chip.status()


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
