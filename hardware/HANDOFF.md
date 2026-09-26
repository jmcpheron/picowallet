# Hardware handoff: Build 1 (2026-09-26)

Start here if you are picking up the McGuffin hardware. It covers what is on the bench, how it is
wired, the next steps and what is still undecided. The detail lives in the files linked from it.

## The goal

**The McGuffin** is the signing chip in a 3D-printed sci-fi key, with a 3.5 mm and a 2.5 mm TRRS
plug side by side on one end. The wallet (Pico 2 W, screen, knob) has the matching pair of jacks. The
key never leaves the chip, and the wallet cannot sign without the McGuffin plugged in.
- 3.5 mm plug: I2C and power.
- 2.5 mm plug: detect, plus reset and ID for a Trust M key.

Build 1 is the first real one, made only from parts on hand. It has an ATECC608 key and runs on USB power.

## Parts

**On the bench**

| part | used in Build 1 | notes |
|---|---|---|
| Raspberry Pi Pico 2 W (RP2350) | yes | |
| 2.0" ST7789 TFT 240x320, 8-pin (from the variety pack) | yes | GND VCC SCL SDA RES DC CS BLK |
| EC11 rotary encoder with push | yes | the only control for now |
| 3.5 mm TRRS jack + plug | yes | 4-pole |
| 2.5 mm TRRS jack + plug | yes | 4-pole |
| Adafruit ATECC608 STEMMA QT breakouts (a batch, unconfigured) | yes, one | the key chip |
| STEMMA QT cables | yes, one | cut for the McGuffin plug |
| 18650 cell + new clips | no | waits for the charger board, below |

**Arriving Monday:** 5 to 10 Adafruit OPTIGA Trust M STEMMA boards (I2C 0x30). No firmware for
them yet.

**Not bought yet** (for the full v2 in [MCGUFFIN.md](MCGUFFIN.md#parts)):

| part | unblocks |
|---|---|
| TP4056 USB-C board **with protection** (DW01 + 8205) | battery power with the 18650 |
| 1N5817 / SS14 Schottky | battery into VSYS |
| slide switch | power on/off |
| resistors: 100 Ω, 1 kΩ, 10 kΩ, 33 kΩ, 100 kΩ | battery sense, key ID, PNP bias, series protection |
| caps: 10 nF, 100 nF, 10 µF | knob debounce, key power |
| 2N3906 / S8550 PNP | switched key power (replaces GPIO power) |
| 6x6 mm tact switches (4) | A/B/X/Y |

## Wiring (Build 1)

The drawn diagram is [build1-wiring.svg](build1-wiring.svg), and the full guide is [BUILD1.md](BUILD1.md).
Pin numbers are Pico header pins, component side up with USB at the top.

| part | pin | Pico |
|---|---|---|
| screen | GND / VCC | GND (18) / 3V3 OUT (36) |
| | SCL / SDA | GP10 (14) / GP11 (15), SPI1 |
| | RES / DC / CS / BLK | GP12 (16) / GP8 (11) / GP9 (12) / GP13 (17) |
| knob | A / B | GP2 (4) / GP3 (5) |
| | C + one switch leg | GND (3) |
| | other switch leg | GP1 (2) |
| 3.5 mm jack | Tip SDA / Ring1 SCL | GP4 (6) / GP5 (7), I2C0 |
| | Ring2 key VCC / Sleeve | GP6 (9) / GND (8) |
| 2.5 mm jack | Tip DETECT / Sleeve | GP22 (29) / GND (28) |
| | Ring1 RST / Ring2 ID | GP26 (31) / GP27 (32), wired now, used by a Trust M key |
| McGuffin 3.5 mm plug | T / R1 / R2 / S | blue SDA / yellow SCL / red VIN / black GND |
| McGuffin 2.5 mm plug | T to S jumper | R1, R2 empty; both Sleeves linked |

**Reserved for later:**
- A/B/X/Y buttons on GP15 (20), GP17 (22), GP19 (25), GP21 (27).
- Battery sense on GP28 (34).
- Battery in on VSYS (39).
- Free: GP0, GP7, GP14, GP16, GP18, GP20.
- Never use GP23, GP24, GP25 or GP29. They belong to the WiFi chip.

## Build order

Each step has a test that says it is done. The REPL snippets are in [BUILD1.md](BUILD1.md#bring-up).

- [ ] Flash MicroPython on the Pico 2 W (top README, step 4). *Done when:* the REPL answers.
- [ ] Find and mark the T/R1/R2/S lugs on both jacks with a meter. *Done when:* each lug is labelled.
- [ ] Screen. *Done when:* GP13 high lights the backlight and `LCD().fill(RED)` shows red. Only a 240x240 area fills, which is expected.
- [ ] Knob. *Done when:* the poll loop prints A/B changing on a turn and the switch going to 0 on a press.
- [ ] Jacks, nothing plugged in. *Done when:* GP22 reads 1.
- [ ] Solder the McGuffin plugs (shells and heat shrink on first). *Done when:* the continuity checks in BUILD1.md pass.
- [ ] Key in. *Done when:* GP22 reads 0; with GP6 high, the wake + scan shows `['0x60']`.
- [ ] Chip status. *Done when:* `ATECC().status()` prints the serial with `configLocked: False`.
- [ ] Photo and a dated entry in `buildlog/BUILDLOG.md`.

## Rules that prevent damage

- **Screen VCC to 3V3 (36), not 5 V or VBUS.**
- **GP6 low before plugging or unplugging the key.** A TRRS plug drags every contact past every other.
- **Never plug the McGuffin into a phone or laptop jack.** Mic bias lands on a key pin.
- **Only charge the 18650 through a protected TP4056.** Don't hot-swap the cell while it is charging.
- **Locking an ATECC's config zone is permanent.** Don't run `lock_config()` until the slot plan below is decided. Wiring and scanning don't need it.

## Firmware to do, in order

1. `firmware/lcd.py`: a width/height/offset option so the 240x320 ST7789 fills. Keep the 240x240
   default for the v1 boards.
2. Knob input with the same event names `wallet.py` uses now: turn = up/down, short press = select,
   2 s hold = approve/sign.
3. Key handling in `firmware/wallet.py`:
   - DETECT (GP22) low and steady
   - GP6 on, wake, scan for 0x60
   - use `firmware/atecc.py`
   - GP6 off on unplug
   - NO KEY screen otherwise
4. Fresh-chip flow on the Pico, one screen per step, using `atecc.py` `status` / `write_config` /
   `lock_config` / `genkey_new`. Needs the slot plan first.
5. `firmware/trustm.py` next to `atecc.py` once the Trust M boards arrive. Pick the driver from the
   2.5 mm ID pin.
6. Emulator (`emu/`): a 240x320 screen, the knob, a plug-in key.

## Open decisions

- Trust M or ATECC608 as the production McGuffin chip.
- Slot plan for McGuffin ATECCs (which slot, can it re-key, data zone locked or not) before locking
  any of the batch.
- Jack spacing: measure the parts, then design the key body and case around it.
- Which 18650 clip or holder goes in the case, and where.
- Key power from GPIO (now) or the PNP switch (MCGUFFIN.md).
- RP2350 secure boot: permanent OTP. Try it on one spare Pico only, after the rest works.

## Pin changes in this session

MCGUFFIN.md was changed to match Build 1. Older notes may still show the old pins:
- key VCC GP14 → **GP6**
- key RST GP6 → **GP26**
- knob push GP16 → **GP1**

## Where the notes are

| file | what |
|---|---|
| [BUILD1.md](BUILD1.md) | Build 1 guide: wiring tables, jack lugs, McGuffin soldering, bring-up REPL tests |
| [build1-wiring.svg](build1-wiring.svg) | drawn wiring diagram |
| [MCGUFFIN.md](MCGUFFIN.md) | full v2: battery, buttons, PNP key switch, ID resistors, Trust M, secure boot, parts list |
| `app/SOLDERING.md` | the ATECC wake pulse and scan; v1 wiring |
| `reference/pi/README.md` | ATECC config and data locks explained |
| `PLAN.md` | project plan; v2 section points here |
| `HANDOFF.md` (root) | v1 wallet, app and case handoff. Kept as local notes, not edited here |
