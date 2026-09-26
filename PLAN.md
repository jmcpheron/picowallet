# Plan

Status 2026-09-05: steps 1, 2, 3 done (mainnet transfer signed on the wallet). 5 in progress (v0 case printed, keycaps in the printer). 4 and 6 next.

Goal: a working wallet you can hold, that signs a real transaction, built from Amazon parts by someone who can solder 8 joints.

## 1. Prove the ATECC on the Pico
- Solder 4 wires: 3V3, GND, GP4, GP5 → ATECC breakout.
- MicroPython on the Pico 2 W. `I2C(0, sda=Pin(4), scl=Pin(5))`, `i2c.scan()` shows 0x60.
- Driver: `ucryptoauthlib` (MicroPython port of cryptoauthlib) or a minimal hand-rolled one (Info, Random, GenKey, Sign, plus the CRC and wake pulse).
- Config: slot 0 = P-256 private key, GenKey allowed. Lock config zone. This chip is the blank #2 from the CELL 2-pack. Lock is permanent, so `verify` first.
- Test: GenKey slot 0, sign a 32-byte hash, verify the signature on the Mac with the pubkey.

## 2. Screen and buttons
- Waveshare's `Pico-LCD-1.3.py` example (framebuf over SPI1).
- Screens: home (address + QR), tx review (to / amount / chain), confirm (A = sign, B = reject), settings.
- Joystick scrolls, A/B/X/Y act.

## 3. Sign a real transaction
- Chain side: smart account with P-256 verifier (RIP-7212 precompile on Base / OP). Same contracts as the ATECC608-demo on the Pi.
- Device side: receive the hash to sign, show what it is, sign on A, return `r,s`.
- Transport v1: USB serial (a small script on the Mac pushes the tx, reads the sig back).
- Transport v2 (WiFi stays on): the device joins your WiFi, a tiny HTTP server takes a tx, shows it on screen, holds until you press A, returns the signature. Bluetooth later.
- Testnet first, then a small mainnet amount.

## 4. Battery
v2 goes with an 18650 + protected TP4056 into VSYS through a Schottky: see `hardware/MCGUFFIN.md`.
Earlier options for the v1 HAT build:
- **TP4056 USB-C charger module** (~17×19 mm) wired to a LiPo and to VSYS through a Schottky diode. Charge over its own USB-C. Two more solder joints plus the battery leads.
- **Pimoroni LiPo SHIM for Pico** — solders to the header pins under the Pico, has charger, protection and a power button. Cleanest, needs stacking headers because the SHIM sits where the LCD's header wants to be.
- Cell: 502030 (5×20×30 mm, 250 mAh) fits the gap. Pico + backlight ≈ 50–100 mA, so ~3 h on, days in sleep.

## 5. Case
- Print "Waveshare Pico 1.3 LCD Case" (printables.com/model/1322102) first to check fit.
- Then our own: a stick, two halves, cutouts for screen / joystick / 4 buttons / USB, a pocket in the middle for ATECC + battery + charger board. Generate from Python like the CELL parts so it re-fits when parts change.

## 6. Ship
- One-page build guide with photos.
- Firmware as a single `.uf2` or a folder to drop on the Pico.
- Web page to create the smart account, register the device pubkey, send a test tx.

## v2: the McGuffin
The signing chip (Trust M or ATECC608) moves into a plug-in key with a 3.5 mm and a 2.5 mm TRRS plug; the wallet gets an ILI9341 screen, a rotary dial and an 18650. Wiring, parts and bring-up: `hardware/MCGUFFIN.md`. First build and handoff: `hardware/BUILD1.md`, `hardware/HANDOFF.md`.

## Order
1 → 2 → 3 (USB serial) → 5 (case on USB power) → 4 → 3 (WiFi) → 6

## Open questions
- Which ATECC breakout is this exactly (pin order, pull-ups on board?).
- Keep the Pico 2 W or move to a plain Pico 2 for the final. Radio on is a feature for v1.
- Does the LCD board expose backlight PWM? Matters for battery life.
