# picowallet build log

## 2026-09-05 — parts on the bench

Three parts, all from Amazon. Pico plugs face-down into the LCD board's female header. The ATECC608 breakout fits in the ~11 mm gap between them.

![stack end-on, ATECC wedged inside](images/2026-09-05-01-stack-end-atecc-inside.jpg)
![Pico-LCD-1.3 top: joystick, screen, A/B/X/Y](images/2026-09-05-04-pico-lcd-1.3-top.jpg)
![Pico 2 W](images/2026-09-05-05-pico-2-w.jpg)

Decisions today:
- Screen and buttons work out of the box through the header. Only the ATECC and the battery need wires.
- ATECC gets 4 soldered wires to the Pico (3V3, GND, GP4 SDA, GP5 SCL). The LCD board eats every pin, no pass-through, so no jumper trick.
- Battery: solder it too, keep it in the gap.
- WiFi/Bluetooth stay on for v1. Idea: send a tx to the device over the radio, it shows it on screen, you approve, it sends the signature back.

## 2026-09-05 — first boot

Pico 2 W plugged into the omen box (Arch laptop, `ssh austin@omen.local`). Blank Pico shows up as a USB drive `RP2350`, no LED, no other sign of life. That's normal.

- Flashed MicroPython v1.26.1 (`RPI_PICO2_W-20250911-v1.26.1.uf2`) by copying it onto the `RP2350` drive.
- Board reboots as `/dev/ttyACM0`. `mpremote` installed on omen via pipx. Added `austin` to `uucp` group for serial access.
- `firmware/main.py` blinks the onboard LED. First light.

Workflow from the Mac: `scp` a file to omen, then `mpremote connect /dev/ttyACM0 cp file :file` and `mpremote reset`.

## 2026-09-05 — WiFi console

Going through omen's USB was a detour. The Pico 2 W has WiFi, so now it joins the house network on boot and listens for a console on TCP 2323. From the Mac:

```
./tools/pico ls
./tools/pico exec 'print(1)'
./tools/pico cp firmware/main.py :main.py
```

That is `mpremote connect socket://picowallet.local:2323 resume ...`. mDNS name `picowallet.local` works from the Mac. `firmware/secrets.py` (gitignored) holds the WiFi creds, template in `secrets.example.py`.

No SSH: MicroPython has no SSH server. The console has no password either, anyone on the LAN can run code on it. Fine for dev, not for the shipped firmware. LED: fast blink while joining WiFi, solid with a short blink every 2 s once up.

Gotcha: mpremote soft-resets the board before the first command, which reruns main.py and kills the socket. Always pass `resume` (the wrapper does).

## 2026-09-05 — screen and buttons

Pico stacked onto the Pico-LCD-1.3. `firmware/lcd.py` is a small ST7789 driver (SPI1 at 62.5 MHz, framebuf RGB565, PWM backlight) plus a `Keys` class for A/B/X/Y and the joystick. `firmware/ui.py` draws a title, the IP, and the last key pressed. Screen and all buttons confirmed working.

Lesson, cost an hour: on the rp2 port the network console (`os.dupterm` on a socket) is only read while the REPL is idle. A blocking `while True` in main.py makes the board deaf over WiFi, and Ctrl-C from the socket never lands. Fix: the UI runs from `machine.Timer(period=30ms)` and main.py returns to the REPL. The timer callback is scheduled (soft), so framebuf and SPI work inside it. Keep the callback quiet: prints from it would corrupt mpremote's raw REPL.

`boot.py` starts WiFi + console before main.py, so a broken main.py can still be fixed remotely.

`tools/push` copies all of `firmware/` and reboots via a one-shot Timer (so mpremote returns before the socket drops). macOS has no `timeout` command, that bit me too.

USB rescue path: the Pico's USB goes to the omen laptop. Device path there is `/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_*-if00` (the ttyACM number changes on each reboot).

## 2026-09-05 — the chip is on the wallet, no solder

The Adafruit ATECC608 from the Pi (serial `01235e6763cc8d97ee`, the key that owns the mainnet vault)
moved onto the Pico with zero solder: a STEMMA QT cable into the breakout, the four wires pushed into
the LCD board's female header beside the Pico pins (GP4 SDA blue, GP5 SCL yellow, 3V3 red, GND black),
breakout tucked in the gap. `i2c.scan()` finds `0x60`, the chip signs in 151 ms.

Firmware now: `atecc.py` driver, `signer.py` (chip if present, else software key), `wallet.py` loop
(announce, poll, show, sign on A), and the digest is rebuilt on the device from the displayed fields
before anything is shown. The home screen shows the vault's dollar balance and pairing state.
Local test stack: fork of the ATECC608-demo app on port 3001 against anvil.

![the stack with the four wires and the ATECC breakout](images/2026-09-05-06-atecc-stack-wired.jpg)
![ATECC608 breakout in the gap](images/2026-09-05-07-atecc-in-the-gap.jpg)
![home screen: $1000.00 USDS paired](images/2026-09-05-08-home-screen-1000-usds.jpg)
![home screen, atecc608 in the corner](images/2026-09-05-09-home-screen-paired.jpg)

## 2026-09-05 — first signed transfer from the wallet

Whole loop, end to end, on the local chain: `POST /api/requests` for 5 USDS to atg.eth, the wallet
rebuilt the EIP-712 digest from the fields and it matched, showed "SIGN? $5 USDS to atg.eth,
A = sign B = reject", Austin pressed A, the ATECC608 signed in 150 ms, the app's relay called
`executeTransfer`, confirmed in tx `0xc7c6f72a…`. Vault 1000 → 995 USDS, nonce 0 → 1. Screen:
"SENT $5 to atg.eth". Same chip, same key that owns the mainnet vault.

Bug of the day: two soft Timers plus a blocking HTTP call fill the rp2 scheduler queue (8 deep) and
the WiFi console's accept callback gets dropped, which shows up as "connection reset by peer" forever.
One 50 ms timer now, and it stops itself during sign + relay.

## 2026-09-05 — first mainnet transfer from the wallet

5 USDS to atg.eth, signed on the ATECC608 wedged into the Pico, relayed by the app on port 3001.
Tx [`0x0fbd390b…`](https://etherscan.io/tx/0x0fbd390b3e82bc4566f9ef9c66c178e58904debaf728ec9d941b4090610c6257),
81,715 gas. Vault 124.56 → 119.56 USDS, nonce 6 → 7. Screen: green SIGN bar, press A, "SENT",
then the home screen flashed "-$5.00".

Bumps on the way, all fixed:
- Two copies of the site were running (yesterday's on :3000, the fork on :3001). A Send on :3000
  never reaches the wallet. Use :3001.
- The app had no reject path, so a Y press left the request pending and reserved its amount; the
  next proposal failed the balance check. Added `POST /api/requests/[id]/reject`.
- Mainnet latency wedged the WiFi console (scheduler queue). Timer now pauses around HTTP, the
  console drains accepts from the tick, the app caches chain reads for 5 s.
- Two signed attempts failed on "insufficient funds" while the relay held 0.000008 ETH. It needs
  about 0.000012 ETH per send at tonight's gas. Funded with 0.001 ETH.

Home screen now: balance big, small QR of the vault, chain label, pairing dot, warning line.
Confirm screen: green SIGN bar in line with A, red REJECT bar in line with Y, details on down.

![the wallet in its case](images/2026-09-05-18-hero-case-on-black.jpg)
![case, portrait](images/2026-09-05-19-case-portrait.jpg)
![SIGN? $69 to atg.eth in front of the site](images/2026-09-05-20-sign-screen-69-usds.jpg)

## 2026-09-05 — provisioning from the wallet, and the repo goes public-ready

`atecc.py` grew `write_config`, `lock_config` and `genkey_new`, so a fresh chip can be locked
and given a key from the app's Setup page without a Pi. Both are gated by `ALLOW_LOCK` /
`ALLOW_GENKEY` in `secrets.py` on the device, default off; with them off the wallet refuses the
commands (checked on the real chip). The lock and new-key paths have NOT yet run on a fresh chip;
the config bytes and command sequence are the ones the Pi signer used successfully on 2026-09-04.

Photos: feet cropped or dropped, files renamed by content, five good shots added. README rewritten
as the build guide: order, print, assemble, flash, set up the chip, run, change it.

Then 69 USDS to atg.eth, same way: [`0x87638ae1…`](https://etherscan.io/tx/0x87638ae169eccb9f002d4eb6ce8b60e7d6603e4d3d4e562164ea10e9023f9313). That is the one in the tweet.

![the details page, joystick down on the sign screen](images/2026-09-05-23-details-screen.jpg)
![v0 case on the printer](images/2026-09-05-24-case-on-the-printer.jpg)

## 2026-09-17 — the KEYS screen, a virtual chip, and a bug in the config table

No hardware in this session, all of it on the emulator, on branch
`claude/pico-wallet-signing-keys-uyr7mc` of the jmcpheron fork.

The wallet now knows the ATECC608 has 16 slots, not just slot 0. X on the home screen opens a
KEYS screen: the slot table as the config zone types it (P256 / PUB / AES / DATA), which slot
signs, NEW KEY in a slot, SHOW PUBLIC KEY, and the three permanent locks (config zone, data zone,
one slot) each behind a red hold-A screen and the `ALLOW_*` flags. `signer.py` has one shape for
the chip and the software key, active slot in `slot.txt`.

To test it without a chip, the emulator grew a virtual ATECC608 on I2C at 0x60 that speaks the
real packet protocol (wake token, `0x03` command packets, CRC-16), so `atecc.py` runs against it
unchanged. It starts as a blank part. `tools/emu chip fresh|ready|show`. Config lock, GenKey in
slots 0/2/7, a signature that verifies, slot lock and data-zone lock all walked through with
screenshots.

Bug of the day, and a bad one: `atecc.py`'s `CONFIG` was not the table the Pi wrote to chip #1.
It was the ATECC508 test table with an extra row of `0xFF` at bytes 96-111 and the last row
dropped. Those bytes are KeyConfig for slots 0-7, so every one of them decoded to "not an ECC
key". Locking a fresh chip with it (README step 5, the Setup page button) would have made slot 0
unable to ever hold a P-256 key, permanently. It never bit anyone because the lock path has never
run on a fresh chip. Fixed by copying the Pi's bytes; with the real table only slots 0, 2 and 7
are P-256 private keys, not 0-7 as the old handoff said. Notes for upstream in `UPSTREAM.md`.

Also on the branch: `SOLDERING.md` with the perfboard wiring (chip on GP4/GP5/GND 8/3V3 36, an
18650 behind a switch and a Schottky into VSYS, 100k/100k divider to GP28 for a gauge),
`power.py` for the gauge, a read-only `chipcheck.py` report, `tools/usb` for deploying over USB
serial, and `TESTPLAN.md` for the next session.

Lesson from the emulator: a top-level `raise SystemExit` in a module you `import` at the
MicroPython REPL soft-reboots the board. `chipcheck.py` runs inside a function now.

## 2026-09-16 — a fresh chip, read only

The perfboard build's first session with the chip: an Adafruit ATECC608 breakout (4314) on the
Pico's pin tails per `SOLDERING.md` (VIN 36, GND 8, SDA 6, SCL 7), the 18650 holder, switch,
Schottky and divider wired as well, no cell in the holder, USB only. Firmware: branch
`claude/pico-wallet-signing-keys-uyr7mc` with upstream `main` (`87c717c`) merged in first,
MicroPython v1.26.1 (2025-09-11), deployed with `tools/usb push` from the Mac on
`/dev/cu.usbmodem112301`.

Rule for today: `ALLOW_LOCK = False`, `ALLOW_GENKEY = False`. Nothing written to the chip.

**Before the flash.** Upstream had moved 21 commits past the branch point. The one that mattered
here is `261b373`: a reset straight after a copy lost writes on LittleFS (atecc.py landed at 3584
of 7021 bytes). `tools/usb push` did exactly that sequence, so it now soft-resets first, chains
every copy, calls `os.sync()`, and only then resets. The merge also brought the NO CHIP screen,
the secrets-less boot and demo/vid. Rehearsed on the emulator (blank virtual chip: home, KEYS,
chip page, chipcheck; provisioned: slot 0 ACTIVE), then a read-only I2C scan on the board before
copying anything: `['0x60']`, first try.

**First power, USB only.** The board was already up on the mock screens; after the push it came
back on the wallet's home screen: `X keys`, red dot, `no key`, WiFi joined (secrets.py with real
credentials, console off, app URL a placeholder so the log says `net: OSError(-2,)`). No
`error.log`. Every `.py` on the board matched its local size (`os.stat`). The serial port took
over 10 s to come back after the hard reset.

**What an untouched chip reports.** `tools/usb exec 'import wallet; wallet.stop()'` then
`tools/usb run firmware/chipcheck.py`, three times over the session (twice before the KEYS walk,
once after). The whole output, verbatim:

```
== picowallet chipcheck ==
i2c scan: ['0x60']
using address: 0x60
wake: ok (3 ms)
serial:   0123f3acfd2a826bee
revision: 00006002 (ATECC608A)
i2c address byte 16: 0xc0 (7-bit 0x60)
config zone: unlocked   data zone: unlocked   (byte 87 = 0x55, byte 86 = 0x55; 0x55 = unlocked, 0x00 = locked)
slot locked bytes 88-89: ff ff
raw config zone (128 bytes, 16 per row):
    0: 01 23 f3 ac 00 00 60 02 fd 2a 82 6b ee c1 55 00
   16: c0 00 00 00 83 20 87 20 8f 20 c4 8f 8f 8f 8f 8f
   32: 9f 8f af 8f 00 00 00 00 00 00 00 00 00 00 00 00
   48: 00 00 af 8f ff ff ff ff 00 00 00 00 ff ff ff ff
   64: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
   80: 00 00 00 00 00 00 55 55 ff ff 00 00 00 00 00 00
   96: 33 00 33 00 33 00 1c 00 1c 00 1c 00 1c 00 1c 00
  112: 3c 00 3c 00 3c 00 3c 00 3c 00 3c 00 3c 00 1c 00
matches the reference table (bytes 16-83, 88-127): no
slot table as the chip has it:
  slot kind  ext-sign genkey privwrite pubinfo lockable locked  key
     0 P256  True     True   False     True    True     False   -
     1 P256  True     True   False     True    True     False   -
     2 P256  True     True   False     True    True     False   -
     3 DATA  False    False  False     False   False    False   -
     4 DATA  False    False  False     False   False    False   -
     5 DATA  False    False  False     False   False    False   -
     6 DATA  False    False  False     False   False    False   -
     7 DATA  False    False  False     False   False    False   -
     8 DATA  False    False  False     False   True     False   -
     9 DATA  False    False  False     False   True     False   -
    10 DATA  False    False  False     False   True     False   -
    11 DATA  False    False  False     False   True     False   -
    12 DATA  False    False  False     False   True     False   -
    13 DATA  False    False  False     False   True     False   -
    14 DATA  False    False  False     False   True     False   -
    15 DATA  False    False  False     False   False    False   -
random (32 bytes): ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000
NOTE: config zone is unlocked. GenKey and Sign will refuse (status 0x0f) until it is locked; that is normal.
== end ==
```

Read off it:
- I2C scan found `['0x60']`, nothing else.
- Serial `0123f3acfd2a826bee`, revision `00006002` = 608A, address byte 16 `0xc0`.
- Config zone unlocked (byte 87 = 0x55), data zone unlocked (byte 86 = 0x55), SlotLocked `ff ff`.
- The factory slot table is not blank: SlotConfig `2083 2087 208f` and KeyConfig `0033` for slots
  0, 1, 2, so Microchip ships them as P-256 private keys, external sign, GenKey allowed; slots 3
  to 15 data, 8 to 14 lockable. `matches the reference table: no`, as expected.
- Random did NOT change between runs: `ffff0000` repeated. Datasheet behaviour before the config
  lock (a fixed test pattern). The test plan expected it to differ; corrected.
- Second and third runs: serial, config and random byte-identical (only the wake time moved, 3 to
  4 ms).

This is the "as shipped" state.

**The KEYS screen on the real chip.** X: header `KEYS atecc608 cfg OPEN`, rows 0 to 2 `P256`, the
rest `DATA` (the emulator's blank part shows `-` everywhere; its fresh table should be these
factory bytes). X again: the chip page, `i2c 0x60`, the serial, `rev 00006002 608A`, `permanent
actions off`, `config zone OPEN`. Cursor on `WRITE + LOCK CONFIG (off)`, A: the red ERROR naming
ALLOW_LOCK, nothing changed. RAW CONFIG ZONE agreed with the dump, row 80 ended `55 55`. RANDOM
twice: `ffff0000...` both times, as above. Slot 0: `P256` with the `(off)` item. Chipcheck after
the walk: byte 87 still `0x55`.

**Timings.** Wake 3 to 4 ms; the whole chipcheck (config read, slot decode, random) well under a
second. Nothing flaky over the session.

**Battery** (wired, cell out, switch off): `power.status()` said `usb: True` via `WL_GPIO2`, and
`vbat: 1.08` where 0 was expected. With the switch off the divider's top is open, so the volt at
GP28 is most likely the Schottky's reverse leakage from VSYS through the divider. The home screen
showed an empty bar and `1.1V` instead of `usb`. Fixed in `power.py`: anything under 2.5 V counts
as no cell (a protected 18650 cuts off near 2.5 V, and the Pico's regulator quits before that).

Decisions today:
- Locking waits. The app side (vault deployment, recovery address) is not planned yet, and the key
  made at lock time is the one the next vault gets.
- The perfboard layout stays; the chip answered first try.

Gotchas:
- A hard reset drops the USB port for over 10 s; anything scripted must wait for
  `/dev/cu.usbmodem*` before the next mpremote call.
- Random before the lock is a fixed pattern, and the factory table already types slots 0 to 2 as
  P-256: two things the emulator's chip model does not do. Both in `UPSTREAM.md` for `atecc_sim.py`.

Not done today, on purpose: config lock, GenKey, data-zone lock, slot lock. The chip leaves this
session exactly as it arrived. Not done for lack of a cell: TESTPLAN phase 5. Next: the battery
phase when a cell is here; `TESTPLAN.md` phase 6 when the vault deployment is planned.

## 2026-09-17 — the map, the ceremony, and the chip is sealed

The chip UI grew a look: the map is the die itself, drawn as a floor plan with the CONFIG strip,
the 4x4 field of slots coloured by kind, OTP, COUNTERS and the LAB docked below; DATA is a grid
of tiles; menus carry class badges; headers are tinted by zone; 25 sixteen-pixel icons, a palette
in `theme.py`; the boot screen got a navy gradient and a rainbow leg chase. Icons are packed from
ASCII art at import (the first draw of a screen paid 8 ms per icon before that). On the panel a
`show()` is 46 ms and the busiest screen draws in about 70 ms. Two new actions: SIGN TEST on a key
slot (sign, verify on the Pico, read counter 0) and WRITE A NOTE on a clear data slot. Two guards
before the lock: `CONFIG` is checked at import for a P-256 slot 0, and `lock_config()` reads the
zone back and refuses unless the table matches and slot 0 decodes right. `CHIPMAP.md` has it all.

Then the finale on the one chip, flags flipped in `secrets.py` and pushed. Jason at the device,
me reading the chip from the laptop between steps:

- WRITE WALLET CONFIG (the chip had been restored to its original bytes earlier): 49 bytes
  changed, read back identical, config still open. chipcheck: `matches the reference table: yes`.
- Hold B+Y, `! LOCK CONFIG FOREVER`, hold A three seconds: the CONFIG strip pulsed, a flash, the
  padlock closed, RULES SEALED ("the cool sealed animation"). chipcheck: byte 87 = `0x00`, slots
  0/2/7 `P256 empty`. Random live: two different 32-byte values. SelfTest all pass.
- OTP from the map: NOT ALLOWED, status 0x0F. Not a bug on our side of the wire: with the config
  zone locked and the data zone still open the chip accepts clear writes into slots and OTP but
  reads nothing back until the data zone is locked too. Every Data and OTP read refused, clear and
  secret slots alike. Neither the firmware nor the emulator knew; both do now (write-only state on
  the map, the reason on the refusal screen, the note reports "read back after data lock").
- NEW KEY in slot 0: KEY CREATED, `a427c739`. Then Jason unplugged USB, ran the wallet on the
  18650 and made another key on battery; back on USB, rebooted, a third: `cc01b14a`. Counters 0
  and 0 throughout, which is right: GenKey does not spend a count, signing does.
- The control experiment for upstream: GenKey on slot 3 (KeyType 7 but GenKey allowed by its
  SlotConfig, the shape of every slot 0-7 in upstream's table) refused with 0x0F; slot 0 untouched.
- One rewrite while it happened: the red screen now leads with what is LOST (the key being
  replaced and its fingerprint, in red; "nothing, the slot is empty" otherwise; for the locks, the
  abilities that go away).

Decisions today:
- Slot 0 stays replaceable; LOCK SLOT waits for a vault deployed with it.
- The data zone stays open; the note in slot 12 and the OTP wait for that decision.
- Slot 7 is where a brought key would go (PrivWrite, encrypted against the write-only secret in
  slot 4); a seed phrase via SLIP-10 nist256p1 is the idea. Not built.
- The upstream issue has its silicon evidence now (UPSTREAM.md section 1 and the draft at the end).

Gotchas:
- My checkpoint script ended with a reset and rebooted the wallet under Jason's hands. Pause the
  timer (`wallet.stop()`), read, `wallet.start_timer()`: the screen stays where it was.
- The plan said slot 8 was 416 bytes of clear data. Under the wallet config it is secret (write
  never, read never in clear); the clear ones are 12 and 13.
- Reads of Data and OTP need the data lock, not just the config lock.

Later the same evening: the red screen's doomed key went cyan at double size, the one thing on
that screen that is not red ("this is the unique thing that's going to be deleted"). Jason made
a fourth key with it (`9fad2e82`), then SIGN TEST twice: SIGNATURE VERIFIED both times and counter 0
went 1, 2, on the screen and from the laptop. `UPSTREAM-ISSUE.md` is the short version for Austin.

Not done today, on purpose: LOCK SLOT 0, LOCK DATA ZONE, PrivWrite, the note in slot 12, slot 2.
Flags back to False and pushed.
