# Read-only chip report for the test plan (TESTPLAN.md). Touches nothing permanent: it scans the
# bus, wakes the chip, reads the config zone, decodes the slot table, pulls one random block, and
# prints it all in a form you can paste into notes. Run at the REPL: `import chipcheck`, or from a
# laptop: `tools/usb run firmware/chipcheck.py`.
# On a wallet that is already running (main.py started wallet.py), stop the timer first:
# `import wallet; wallet.stop()`, or run this from a fresh boot with main.py held back.
import time


def main():

    print("== picowallet chipcheck ==")
    try:
        import atecc
    except Exception as e:
        print("cannot import atecc:", e)
        return

    found = atecc.scan()
    print("i2c scan:", ["0x%02x" % a for a in found] or "nothing answers (wiring? power? SDA/SCL swapped?)")
    if not found:
        return

    chip = atecc.ATECC608()
    print("using address: 0x%02x" % chip.addr)
    t0 = time.ticks_ms()
    chip.wake(); chip.sleep()
    print("wake: ok (%d ms)" % time.ticks_diff(time.ticks_ms(), t0))

    cfg = chip.read_config_all()
    print("serial:   %s" % "".join("%02x" % b for b in cfg[0:4] + cfg[8:13]))
    rev = chip.revision()
    print("revision: %s (%s)" % ("".join("%02x" % b for b in rev), {b"\x00\x00\x60\x02": "ATECC608A", b"\x00\x00\x60\x03": "ATECC608B"}.get(bytes(rev), "unknown")))
    print("i2c address byte 16: 0x%02x (7-bit 0x%02x)" % (cfg[16], cfg[16] >> 1))
    print("config zone: %s   data zone: %s   (byte 87 = 0x%02x, byte 86 = 0x%02x; 0x55 = unlocked, 0x00 = locked)"
          % ("LOCKED" if cfg[87] == 0 else "unlocked", "LOCKED" if cfg[86] == 0 else "unlocked", cfg[87], cfg[86]))
    print("slot locked bytes 88-89: %02x %02x" % (cfg[88], cfg[89]))
    print("raw config zone (128 bytes, 16 per row):")
    for r in range(8):
        print("  %3d: %s" % (r * 16, " ".join("%02x" % b for b in cfg[r * 16:r * 16 + 16])))
    same = cfg[16:84] == atecc.CONFIG[16:84] and cfg[88:] == atecc.CONFIG[88:]
    print("matches the reference table (bytes 16-83, 88-127): %s" % ("yes" if same else "no"))

    print("slot table as the chip has it:")
    print("  slot kind  ext-sign genkey privwrite pubinfo lockable locked  key")
    for s in chip.slots(cfg, probe=cfg[87] == 0):
        key = ("%08x" % (s["qx"] >> 224)) if s.get("hasKey") else ("empty" if s["kind"] == "P256" and cfg[87] == 0 else "-")
        print("  %4d %-5s %-8s %-6s %-9s %-7s %-8s %-7s %s" % (s["slot"], s["kind"], s["extSign"], s["genKey"], s["privWrite"], s["pubInfo"], s["lockable"], s["locked"], key))

    try:
        r = chip.random()
        print("random (32 bytes): %s" % "".join("%02x" % b for b in r))
    except Exception as e:
        print("random failed:", e)
    if cfg[87] != 0:
        print("NOTE: config zone is unlocked. GenKey and Sign will refuse (status 0x0f) until it is locked, and Random")
        print("      returns the fixed test pattern ffff0000... (datasheet) instead of random bytes; both are normal.")
    print("== end ==")


main()
