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

## 2026-09-__ — a fresh chip, read only

*(Template for the hardware session. Replace the bracketed prompts with what happened; delete
the ones that did not apply. Photos go in `images/` named by content, `2026-09-__-NN-what.jpg`,
no feet. Keep the numbers, they are the point of this entry: nobody in this repo has recorded
what a blank ATECC608 looks like before anyone touches it.)*

The chip: Adafruit ATECC608 breakout (4314), bought from [Amazon / Adafruit, order date],
sealed [yes/no], marking on the chip package `[what is printed on it]`. Wired to the Pico's
pin tails on the perfboard per `SOLDERING.md`: red 3V3 (36), black GND (8), blue SDA (6), yellow
SCL (7). Battery [not yet / wired, cell out]. Firmware: this branch at `[git rev]`, MicroPython
`[version from the REPL banner]`, deployed with `tools/usb push` from `[machine]`.

Rule for today: `ALLOW_LOCK = False`, `ALLOW_GENKEY = False`. Nothing written to the chip.

![the perfboard with the chip wired](images/2026-09-__-01-perfboard-chip-wired.jpg)

**Bench, nothing powered.** Continuity on all four wires [ok / what was wrong]. 3V3 to GND open
[yes]. [Anything that surprised you.]

**First power, USB only.** Screen came up [first try / after ...]. Home screen: `usb` top row,
`X keys`, red dot, `no key`. [Time from plug-in to home screen, roughly.]

**What an untouched chip reports.** `tools/usb exec 'import wallet; wallet.stop()'` then
`tools/usb run firmware/chipcheck.py`. The whole output, verbatim:

```
[paste chipcheck output]
```

Read off it:
- I2C scan found `[0x60]`. [If anything else answered, what and why.]
- Serial `[...]`, revision `[00006002 = 608A / 00006003 = 608B]`, address byte 16 `[0xC0]`.
- Config zone `[unlocked, byte 87 = 0x55]`, data zone `[unlocked, byte 86 = 0x55]`.
- The factory slot table: `[what the SlotConfig rows 16-51 and KeyConfig rows 96-127 held; all
  zero? Microchip defaults? which slots, if any, decode as P256 before anyone writes a table]`.
- Random block changed between two runs `[yes]`.
- Second run: serial and config identical `[yes]`.

This is the "as shipped" state. Compare against the reference table in `atecc.py`: `[matches:
no, as expected]`.

**The KEYS screen on the real chip.** X: `[what the list showed; the header said cfg OPEN]`.
X again: chip page `[i2c 0x60, serial, rev, permanent actions off]`. RAW CONFIG ZONE `[agreed
with the chipcheck dump; row 80 ended 55 55]`. RANDOM twice `[different both times]`. Cursor on
`WRITE + LOCK CONFIG (off)`, A: `[the red ERROR screen naming ALLOW_LOCK; nothing changed]`.
Re-ran chipcheck after: byte 87 still `[0x55]`.

![KEYS list on the fresh chip](images/2026-09-__-02-keys-list-fresh.jpg)
![chip page, permanent actions off](images/2026-09-__-03-chip-page-off.jpg)
![raw config zone](images/2026-09-__-04-raw-config.jpg)

**Timings.** Wake `[n ms]`, config read `[n ms]`, random `[n ms]` (from chipcheck / the REPL).
[Anything slower or flakier than the old wedged-wire build.]

**Battery** (if wired today): meter on the cell `[V]`, screen `[V]`, `usb` shown with USB in
`[yes/no, and which pin power.py ended up using: WL_GPIO2 or GP24]`, VSYS with USB `[V]`, VSYS on
cell `[V]`, ran on cell for `[minutes]`, switch off read `[0 V]` at GP28.

Decisions today:
- [Locking waits until ... / the app side needs ... before the key is made.]
- [Keep the perfboard layout / move the chip / shorten the I2C wires.]
- [Anything to change in the firmware after seeing the real chip.]

Gotchas:
- [Whatever cost time. Port name, mpremote retry, a swapped wire, the screen hint.]

Not done today, on purpose: config lock, GenKey, data-zone lock, slot lock. The chip leaves this
session exactly as it arrived. Next: `TESTPLAN.md` phase 6, when the vault deployment is planned.
