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

## 4b. The chip on its own terms: CHIP MAP, LAB, a reversible write

Still `ALLOW_LOCK = False`, `ALLOW_GENKEY = False`. The only write here can be undone.

- [ ] X on the home screen: CHIP MAP. Header `CHIP` and `SAFE o`. CONFIG `OPEN`, DATA and OTP
      `hidden`, COUNTERS `2`, LAB.
- [ ] LAB: run every question and write down the chip's answer, including refusals (status byte and
      the reason the wallet gives). New facts for upstream: which of SelfTest, SHA, Counter, Info
      State a fresh 608A accepts. Record: `______________________________________________`
- [ ] OTP and COUNTERS from the map: refused (0x0F) or answered? Record: `________`
- [ ] B: LEARN. Read the six cards; A from a card lands on the right screen.
- [ ] Hold B and Y 3 s anywhere in the chip UI: header turns `! ARMED 60s`, counts down, expires.
      The red items stay off (`ALLOW_LOCK is False on the board`).
- [ ] CONFIG page: CURRENT `original bytes`, SNAPSHOT `none yet`. `~ WRITE WALLET CONFIG`: the diff
      screen says how many bytes change and lists the slot changes; hold A 1.5 s. Three checks:
      WRITE COMPLETE, READBACK MATCHES, CONFIG STILL OPEN. Record bytes changed: `____`
- [ ] `tools/usb run firmware/chipcheck.py`: `matches the reference table: yes`, byte 87 still 0x55.
      `tools/usb ls` shows `snapshot-<serial>.bin`.
- [ ] DATA list: slots 0, 2, 7 `P256 hidden`, 5 and 10 `AES`, 11, 14, 15 `PUB`.
- [ ] `~ RESTORE SAVED CONFIG`, then chipcheck: dump identical to the one in UPSTREAM.md section 3.
      Byte 16 (the address) never changed. Record: `________`

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

1. `secrets.py`: `ALLOW_LOCK = True`, `ALLOW_GENKEY = True`. `tools/usb push`.
2. X, CONFIG. CURRENT must read `wallet config`; if it reads `original bytes`, `~ WRITE WALLET
   CONFIG` (the diff first, hold A 1.5 s, three green checks).
   - [x] chipcheck: `matches the reference table: yes`, byte 87 = 0x55. Bytes changed: `49`
3. Hold B and Y together 3 s: header `! ARMED 60s`. CONFIG, `! LOCK CONFIG FOREVER` (live only with
   the wallet table on the chip), read the red screen, hold A 3 s through the countdown. RULES
   SEALED ceremony, then the green SEALED screen.
   - [x] chipcheck: byte 87 = 0x00, `matches the reference table: yes`, slots 0/2/7 `P256 empty`,
         `random` no longer `ffff0000`. Lock round trip: `not timed (done on the device)`
4. LAB: MAKE RANDOMNESS twice, different, no WHY layer. ARE YOU HEALTHY? passes. WHAT'S IN YOUR OTP?
   and TRY READING SECRET SLOT 8: both refused with "the DATA zone is still open" (the chip reads
   nothing back from slots or OTP until the data lock). IS YOUR SLOT A KEY?: no.
   - [x] Seen 2026-09-17: every Data/OTP read refused with 0x0F while the data zone is open.
5. Arm again if the header says SAFE. DATA, slot 0 (`empty`), `! NEW KEY`, red screen, hold A 3 s.
   KEY CREATED ceremony; the tile shows the fingerprint over the green bar.
   - [x] `SHOW PUBLIC KEY`: qx and qy. From the laptop `tools/usb exec 'import wallet;
         print(["0x%064x" % v for v in wallet.sig.pubkey()])'` prints the same.
   - [x] LAB IS YOUR SLOT A KEY?: yes. chipcheck: slot 0 `P256 <fingerprint>`.
   Record: fingerprint `cc01b14a` (third key; the first was `a427c739`, one was made on battery),
   qx `0xcc01b14ac97dd23eb2810865ba4ac37df91e9719089b72f029ccf416196f3d24`,
   qy `0xc25a18a11de1086c98eb05d135de120e5d5943370d4392d168b9d9dde88cb079`, GenKey round trip
   `about 130 ms`. Control: GenKey on slot 3 (KeyType 7) refused 0x0F, slot 0 untouched.
6. Slot 0, `o SIGN TEST`: SIGNATURE VERIFIED, r and s, counter 0 is now 1. Again: 2. LAB WHAT'S
   COUNTER 0? agrees. Record: sign round trip `____ ms`.
7. Optional: slot 12, `~ WRITE A NOTE`, hold A 1.5 s: WRITE COMPLETE, and "read back after data
   lock" (the chip accepts the clear write but will not read it back until the DATA zone is locked).
   Also optional and never run on real silicon: slot 2 `NEW KEY` then `USE THIS KEY` (the app would
   say not paired; `USE` slot 0 puts it back).
8. Do NOT lock the data zone or any slot in this session unless you have decided you never want
   to regenerate that key. Leave them for a later, deliberate step.
9. Flags back to False, push. CONFIG page: `! LOCK DATA ZONE` off with `ALLOW_LOCK is False`.

Record: whether step 7 was done `____`, anything the emulator got wrong compared with the board
`________________`.

## 7. Wrap up

- [ ] `UPSTREAM.md` filled in: chipcheck dump, what worked, what did not, screen photos.
- [ ] Commit the notes on this branch and push.
- [ ] If anything in the firmware misbehaved on the board, the traceback is in `error.log` on the
      Pico (`tools/usb cat error.log`) and in `wallet.log` at the REPL (`import wallet; wallet.log`).
