# Test plan: fresh chip, perfboard build, this branch

For the session where the new ATECC608 and the battery get wired up on the perfboard build and
this branch (`claude/pico-wallet-signing-keys-uyr7mc`) goes onto the Pico. Every step says what to
do, what to expect, and what to write down. Fill in the result boxes as you go; the notes are what
goes upstream afterwards (see `UPSTREAM.md`).

Rule for the whole session: `ALLOW_LOCK = False` and `ALLOW_GENKEY = False` stay in `secrets.py`
until phase 6. Phases 1 to 5 change nothing on the chip.

## 0. Before touching hardware

- [x] Dev machine has `mpremote` (`uv tool install mpremote` or `pip install mpremote`).
- [x] This branch checked out; `git log --oneline -3` shows the "Perfboard wiring guide" and
      "Pluggable signing keys" commits.
- [x] Rehearse once on the emulator so the screens are familiar:
      `tools/emu chip fresh`, `tools/emu run main`, X, X, walk the chip page.
- [x] `firmware/secrets.py` exists (copy of `secrets.example.py`) with your WiFi and app URL,
      `ENABLE_NETWORK_CONSOLE = False`, both ALLOW flags False.

Record: mpremote version `1.29.0`, MicroPython build on the Pico (step 2) `v1.26.1 (2025-09-11) RPI_PICO2_W`.

## 1. Bench checks with nothing powered

From `SOLDERING.md` sections 1 and 2, with the cell OUT and USB unplugged:

- [ ] Cable mapped by pad, not color: each bare wire beeps on exactly one of the breakout's VIN /
      GND / SDA / SCL pads. Record the color for each pad (table in SOLDERING.md section 1).
- [ ] Continuity: VIN wire to pin 36, GND wire to pin 8, SDA wire to pin 6, SCL wire to pin 7.
- [ ] No continuity pin 36 to pin 8 (3V3 to GND).
- [ ] Diode mode across the Schottky: ~0.2 to 0.35 V one way, open the other. Band toward pin 39.
- [ ] Switch OFF: the holder's + lead is open to everything.
- [ ] Switch ON: holder + to the diode anode, and to the top 100k.
- [ ] Resistance pin 39 to GND is not a short (expect kΩ or more; the Pico's input caps make it
      settle upward).

Record anything that surprised you: `________________________________`

## 2. Flash the firmware (USB, cell out, switch OFF)

Plug USB. If the Pico has no MicroPython yet: hold BOOTSEL while plugging, drop the
`RPI_PICO2_W` `.uf2` from micropython.org onto the drive, wait for the reboot.

```sh
tools/usb                       # opens the REPL; Ctrl-] leaves. Confirms the port and the build.
tools/usb push                  # copies firmware/*.py (not secrets.example.py) and resets
```

`tools/usb` finds `/dev/ttyACM*` or `/dev/tty.usbmodem*`; set `PICO_PORT=` if it picks wrong.
Then, separately, copy your secrets: `tools/usb cp firmware/secrets.py :secrets.py`, then
`tools/usb reset`.

- [x] `tools/usb ls` lists `atecc.py chipcheck.py power.py signer.py slots.py wallet.py ...`
- [x] After reset the screen shows the home screen with `usb` at the top, `X keys` at the right,
      a red dot, and `no key` in the status bar (no app reachable is fine, it says `connecting...`).

Record: what the REPL banner printed (MicroPython version line): `MicroPython v1.26.1 on 2025-09-11; Raspberry Pi Pico 2 W with RP2350`

## 3. Chip alive, read-only

Stop the wallet loop so the bus is free, then run the report:

```sh
tools/usb exec 'import wallet; wallet.stop()'
tools/usb run firmware/chipcheck.py
```

Expected on a fresh Adafruit breakout:

- `i2c scan: ['0x60']`
- `wake: ok`
- `revision: 00006002 (ATECC608A)` or `00006003 (ATECC608B)`
- `config zone: unlocked   data zone: unlocked   (byte 87 = 0x55, byte 86 = 0x55)`
- a raw dump of 128 bytes
- `matches the reference table: no` (it is the factory table)
- a slot table with slots 0, 1, 2 as `P256` (Microchip's factory KeyConfig `0x0033` on the
  Adafruit 608A, GenKey allowed) and the rest `DATA`; the key column is `-` until the lock
- `random (32 bytes): ffff0000ffff0000...`, the same every run: before the config lock the Random
  command returns a fixed test pattern (datasheet). Real random bytes only after the lock.
- the NOTE about GenKey and Sign refusing until lock

If `i2c scan` finds nothing: swap blue and yellow (SDA/SCL are the usual mistake), check red is on
3V3 not VSYS, check black. If it finds `0x35` or `0x6a`: that is a Trust&Go or TrustFLEX part, not
a blank one; stop and read its slot table before deciding anything.

- [x] Paste the whole chipcheck output into `UPSTREAM.md` section "Factory config of a fresh
      ATECC608" (that dump is useful upstream: nobody has recorded what a blank part reports).
- [x] Run chipcheck a second time; output byte-identical (random included, until the lock).

Record: serial `0123f3acfd2a826bee`, revision `00006002 (608A)`, address `0x60`.

## 4. The KEYS screen on the real chip

`tools/usb reset`, wait for the home screen. Then on the device:

- [x] X: the slot list. Header reads `KEYS atecc608 cfg OPEN`. Rows show `-` or whatever the
      factory table decodes to. Joystick up/down moves the cursor; Y goes home.
- [x] X again from the list: the chip page. `i2c 0x60`, the serial from step 3, the revision,
      `permanent actions off`, `config zone OPEN`, `data zone open`.
- [x] Cursor on `WRITE + LOCK CONFIG (off)`, press A: red ERROR screen saying ALLOW_LOCK is False,
      nothing was changed. A to dismiss. Re-run chipcheck later to prove byte 87 is still 0x55.
- [x] `RAW CONFIG ZONE`: 16 rows of 8 bytes; row 80 shows `55 55` at the end in yellow. Compare a
      few bytes against the chipcheck dump.
- [x] `RANDOM (chip alive?)`: a DONE screen with 64 hex chars: `ffff0000` repeated on an unlocked
      chip (the fixed pattern until the config lock; still proves the wire and the protocol),
      different every time once the chip is locked.
- [x] Open slot 0: `untyped` or the factory kind; `nothing to do here` or a `(off)` item.

Record: the screen photos are worth keeping (`buildlog/images/`, no feet in the shot).

## 5. Battery

Cell out, USB in, switch OFF:

- [ ] Home screen top row shows `usb`. `tools/usb exec 'import power; print(power.status())'`
      shows `usb: True`, `percent: None`. `vbat` can read up to about 1 V with the switch off
      (1.08 V seen: Schottky reverse leakage through the divider); under 2.5 V counts as no cell.

Cell IN, USB in, switch ON:

- [ ] `power.status()` shows `vbat` within 0.1 V of a meter on the cell, `usb: True`. The home
      screen shows a bar and the voltage. Record: meter `____ V`, screen `____ V`.
- [ ] Meter on pin 39 (VSYS) to GND: about 4.6 to 4.8 V (USB wins).
- [ ] Meter across the Schottky: reverse-biased, roughly VSYS minus Vcell.

Unplug USB with the switch ON:

- [ ] The wallet keeps running, no reboot. Top row: bar + voltage, no `usb`.
- [ ] Pin 39 to GND: Vcell minus ~0.3 V.
- [ ] Leave it on battery for 10 minutes; screen stays up; note `vbat` at start and end.

Switch OFF with USB out:

- [ ] Screen dies. Pin 34 (GP28) to GND reads 0 V (nothing back-feeds).

Plug USB back in, switch still OFF:

- [ ] Boots normally. Now switch ON while on USB: no glitch, `vbat` appears.

If `usb` never shows or is wrong: `power.py` tries `WL_GPIO2` then GP24 for VBUS sense; note which
one the Pico 2 W actually reports and whether it toggles. Record: `WL_GPIO2` (2026-09-16, USB in; toggling untested, no cell).

If `vbat` reads high or noisy: check the 100 nF is at GP28 and that the divider taps before the
diode. Record raw ADC: `tools/usb exec 'from machine import ADC, Pin; print(ADC(Pin(28)).read_u16())'`.

## 6. Committing the chip (only when ready, and only on the NEW chip)

Do not do this on the wallet that owns the mainnet vault. Do not do it until the app side
(`app/packages/foundry/.env`, recovery address) is planned, because the key made here is the one
the next vault gets deployed with.

1. `secrets.py`: `ALLOW_LOCK = True`, `ALLOW_GENKEY = True`. `tools/usb cp ... reset`.
2. Chip page shows `permanent actions ARMED` in red.
3. `WRITE + LOCK CONFIG`: red screen, hold A 1.5 s. DONE says slots 0, 2, 7 are P-256 slots.
   - [ ] `chipcheck`: byte 87 = 0x00, `matches the reference table: yes`, slots 0/2/7 `P256 empty`.
4. Slot 0, `NEW KEY`, hold A. DONE shows an 8-hex fingerprint; the row reads `0 P256 <fp> ACTIVE`.
   - [ ] `SHOW PUBLIC KEY`: write down qx and qy. `tools/usb exec 'import signer; s=signer.load(); print(["0x%064x" % v for v in s.pubkey()])'` prints the same.
   - [ ] Sign test: `tools/usb exec 'import signer, p256; s=signer.load(); d=bytes(range(32)); r,ss=s.sign(d); print(p256.verify(s.pubkey()[0], s.pubkey()[1], d, r, ss))'` prints `True`.
5. Optional, and these two have never run on real silicon: slot 2 `NEW KEY` then `USE THIS KEY`
   (the app should now say not paired; `USE` slot 0 again puts it back). Then slot 7 `NEW KEY`.
6. Do NOT lock the data zone or any slot in this session unless you have decided you never want
   to regenerate that key. Leave them for a later, deliberate step.
7. Flags back to False, `tools/usb cp` secrets, reset. Chip page: `permanent actions off`.

Record: fingerprint slot 0 `________`, qx `________`, qy `________`, and whether step 5 was done.

## 7. Wrap up

- [ ] `UPSTREAM.md` filled in: chipcheck dump, what worked, what did not, screen photos.
- [ ] Commit the notes on this branch and push.
- [ ] If anything in the firmware misbehaved on the board, the traceback is in `error.log` on the
      Pico (`tools/usb cat error.log`) and in `wallet.log` at the REPL (`import wallet; wallet.log`).
