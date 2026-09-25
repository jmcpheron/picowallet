# v2 wiring: the McGuffin

The v2 wallet hardware, still on the bench. The v1 build (Pico-LCD-1.3 HAT with the ATECC608 on
wires) stays the documented build in the top README until v2 works.

**The idea:** the signing key does not live in the wallet. It lives in **the McGuffin**, a
3D-printed sci-fi key with one signing chip inside and two headphone plugs, a 3.5 mm and a
2.5 mm, coming out of the same side. The wallet has the matching pair of jacks. Plug the
McGuffin in and the wallet can sign. Pull it out and the wallet holds nothing.

| part | notes |
|---|---|
| Raspberry Pi Pico 2 W (RP2350) | same board as v1; RP2350 has secure boot in OTP (see the end) |
| ILI9341 2.4 to 2.8" SPI TFT, 240x320 | from the Amazon variety pack; the red board with the 14-pin header |
| EC11 rotary encoder with push switch | the dial; replaces the v1 joystick |
| 4 tact switches, 6x6 mm | A, B, X, Y, same roles as v1 |
| 18650 cell + holder | |
| TP4056 USB-C charger **with protection** | the 6-pad board with B+ B- OUT+ OUT- (DW01 + 8205 chips on it) |
| signing chip, one per McGuffin | Adafruit OPTIGA Trust M STEMMA (I2C 0x30) or Adafruit ATECC608 STEMMA (I2C 0x60). Which one is still open |
| 3.5 mm + 2.5 mm TRRS jacks and plugs | **4-pole (TRRS)**, not 3-pole TRS. Count the black rings on the plug: 3 rings = 4 contacts |

Full shopping list with resistors and diodes: [parts](#parts).

## The McGuffin plugs

Two prongs give 8 contacts. I2C needs 4, so the other 4 add reset, key detection and a chip ID.

```
   McGuffin (printed body, chip inside)
  ┌──────────────────────┐
  │                      ├══[S]=[R2]=[R1]=>T   3.5 mm:  T SDA   R1 SCL   R2 VCC   S GND
  │   Trust M or ATECC   │
  │                      ├══[S]=[R2]=[R1]=>T   2.5 mm:  T DETECT  R1 RST  R2 ID  S GND
  └──────────────────────┘
```

| prong | Tip | Ring 1 | Ring 2 | Sleeve |
|---|---|---|---|---|
| 3.5 mm | SDA (blue) | SCL (yellow) | VCC (red) | GND (black) |
| 2.5 mm | DETECT: wire to this plug's Sleeve | RST (Trust M RST pin; ATECC: leave unconnected) | ID: resistor to Sleeve | GND |

Inside the key: the chip breakout's STEMMA QT cable is cut and its four wires go straight to the
3.5 mm plug, colours as in the table. On the 2.5 mm plug, a short wire links Tip to Sleeve, the ID
resistor sits between Ring 2 and Sleeve, and one wire goes from Ring 1 to the breakout's RST pad
(Trust M only; check the silkscreen, it is a header pin, not on the STEMMA connector). Join the two
Sleeves inside the key.

**ID resistor:** the wallet reads it on GP27 with a 10 kΩ pull-up, so firmware knows which
driver to load without a setting.

| key | ID resistor | GP27 reads |
|---|---|---|
| Trust M | 10 kΩ | 3.3 × 10/20 ≈ 1.65 V |
| ATECC608 | 33 kΩ | 3.3 × 33/43 ≈ 2.53 V |
| nothing in, or unknown | open | 3.3 V |

### Why this order, and hot-plug rules

A plug slides in tip first, so the plug's tip wipes across every jack contact on the way in. The
jack's sleeve contact is at the mouth. Putting GND on the sleeve means that during insertion the
signal lines only brush GND, which open-drain I2C does not mind. VCC is the one line that can do
harm, so **the wallet keeps key VCC switched off** until the key is fully in:

1. DETECT (GP22, pull-up) reads 0 steadily for ~300 ms. Both prongs are seated: the 2.5 mm tip only
   meets the tip contact at the end of the travel.
2. Switch VCC on (GP14 low), wait 10 ms, check SDA and SCL read 1 (a pair of headphones would hold
   them low), then read the ID and talk I2C.
3. DETECT goes 1 or I2C errors: VCC off, and set GP4, GP5, GP6 to inputs so nothing back-powers the
   chip through its pins. Power cycling is also the reset of last resort.

Do not plug the McGuffin into a phone or laptop: their mic bias (about 2 V) lands on a contact.
Headphones in the wallet are harmless: DETECT never goes low, so VCC never turns on.

**Jack spacing:** the two jacks in the wallet must sit at the same centre-to-centre distance as
the two plugs in the key body. Measure the parts when they arrive and put the number in the case
generator; the plug shells need about 1 mm of wall between them.

## Pin map, Pico 2 W

The TFT and A/B/X/Y keep the v1 GPIO numbers from `firmware/lcd.py`, and the key bus keeps the
v1 ATECC pins from `firmware/atecc.py`. Only the display driver changes (ST7789 to ILI9341) and the
joystick becomes the dial.

| function | GPIO | Pico pin | notes |
|---|---|---|---|
| dial A | GP2 | 4 | internal pull-up, 10 nF to GND |
| dial B | GP3 | 5 | internal pull-up, 10 nF to GND |
| key SDA | GP4 | 6 | I2C0, 100 Ω in series at the jack |
| key SCL | GP5 | 7 | I2C0, 100 Ω in series at the jack |
| key RST | GP6 | 9 | 100 Ω in series; active low on the Trust M |
| TFT DC | GP8 | 11 | |
| TFT CS | GP9 | 12 | |
| TFT SCK | GP10 | 14 | SPI1 |
| TFT MOSI (SDI) | GP11 | 15 | SPI1 |
| TFT RESET | GP12 | 16 | |
| TFT LED | GP13 | 17 | PWM backlight, see [screen](#screen) |
| key VCC enable | GP14 | 19 | low = on, drives the PNP |
| key A | GP15 | 20 | tact switch to GND, internal pull-up |
| dial push | GP16 | 21 | switch to GND, internal pull-up |
| key B | GP17 | 22 | |
| key X | GP19 | 25 | |
| key Y | GP21 | 27 | |
| key DETECT | GP22 | 29 | internal pull-up |
| key ID | GP27 | 32 | ADC1, 10 kΩ pull-up to 3V3 |
| battery sense | GP28 | 34 | ADC2, 100k/100k divider |
| 3V3 OUT | | 36 | TFT VCC, key switch, pull-ups |
| VSYS | | 39 | battery in, through the Schottky |
| GND | | 3, 8, 13, 18, 23, 28, 33, 38 | any |

Spare: GP0/GP1 (UART0, handy for a debug console), GP7, GP18, GP20, GP26. GP23, GP24, GP25 and
GP29 are wired to the WiFi chip on the Pico 2 W and are not on the header; do not use them.

```
                         USB
                  ┌─────┤   ├─────┐
  (spare)   GP0   1 │ o           o │ 40  VBUS
  (spare)   GP1   2 │ o           o │ 39  VSYS      <- battery via Schottky
            GND   3 │ o           o │ 38  GND       <- battery -, all grounds
  dial A    GP2   4 │ o           o │ 37  3V3_EN    (leave alone)
  dial B    GP3   5 │ o           o │ 36  3V3 OUT   -> TFT VCC, key PNP, pull-ups
  key SDA   GP4   6 │ o           o │ 35  ADC_VREF
  key SCL   GP5   7 │ o           o │ 34  GP28      battery sense
            GND   8 │ o           o │ 33  GND
  key RST   GP6   9 │ o           o │ 32  GP27      key ID
  (spare)   GP7  10 │ o           o │ 31  GP26      (spare)
  TFT DC    GP8  11 │ o           o │ 30  RUN
  TFT CS    GP9  12 │ o           o │ 29  GP22      key DETECT
            GND  13 │ o           o │ 28  GND
  TFT SCK   GP10 14 │ o           o │ 27  GP21      key Y
  TFT MOSI  GP11 15 │ o           o │ 26  GP20      (spare)
  TFT RST   GP12 16 │ o           o │ 25  GP19      key X
  TFT LED   GP13 17 │ o           o │ 24  GP18      (spare)
            GND  18 │ o           o │ 23  GND
  key VCC   GP14 19 │ o           o │ 22  GP17      key B
  key A     GP15 20 │ o           o │ 21  GP16      dial push
                  └─────────────────┘
```

## Key jack circuit

```
 3V3 OUT (36) ──┬──────────────── E
                │                  \
               10k               PNP  2N3906 / S8550
                │                  /
 GP14 ──1k──────┴──────────────── B
                                   C ──┬──┬──── 3.5 mm Ring 2 (key VCC)
                                       │  │
                                     10µF 100nF
                                       │  │
                                      GND GND

 GP4  ── 100Ω ──┬────────────────────── 3.5 mm Tip    (SDA)
                10k ── key VCC
 GP5  ── 100Ω ──┬────────────────────── 3.5 mm Ring 1 (SCL)
                10k ── key VCC

 GP6  ── 100Ω ──────────────────────── 2.5 mm Ring 1 (RST)
 GP22 (pull-up) ────────────────────── 2.5 mm Tip    (DETECT)
 3V3 ──10k──┬───────────────────────── 2.5 mm Ring 2 (ID)
            └── GP27
 GND ───────────────────────────────── both Sleeves
```

- The 10k pull-ups on SDA/SCL go to **key VCC** (the PNP collector), not to 3V3. Pulled to 3V3
  they would feed the chip through its pin diodes while VCC is off. The breakouts have their own
  pull-ups too; these are extra margin for the plug contacts.
- The PNP drops 0.1 to 0.2 V, so the key sees about 3.1 V. Both chips are fine with that.
- Most panel jacks have extra pins for a built-in switch. Leave them unconnected; DETECT does
  that job and works the same on every jack.

## Power

```
 18650 ── holder ── TP4056 B+ / B-          (charge through the TP4056's own USB-C)
                    TP4056 OUT+ ──┬── slide switch ── 1N5817 ▶| ── VSYS (39)
                                  │
                                100k
                                  ├──────── GP28 (34)   + 100 nF to GND
                                100k
                                  │
                    TP4056 OUT- ──┴──────────────────────── GND (38)
```

- The Pico already has a Schottky from VBUS to VSYS, so USB and the battery OR together. Plugging
  USB into the Pico with the battery switched on is safe.
- Battery voltage in MicroPython: `ADC(28).read_u16() * 3.3 / 65535 * 2`. 4.2 V full, about
  3.3 V empty (the TP4056 board cuts off at about 2.5 V, well under what you want to reach).
- The divider sits on the battery side of the switch, so GP28 reads the cell even with the switch
  off (once USB powers the Pico). It draws 21 µA, which is nothing next to an 18650.
- Budget: Pico 25 to 50 mA, 2.8" backlight 40 to 80 mA, key a few mA. A 2500 to 3000 mAh cell is
  roughly a day of screen-on time; dim the backlight when idle.
- Never charge an unprotected 18650 without the protected TP4056 board, and don't hot-swap the
  cell with the TP4056 plugged in.

## Screen

The common red ILI9341 board pins, in header order: VCC, GND, CS, RESET, DC, SDI(MOSI), SCK, LED,
SDO(MISO), then T_CLK, T_CS, T_DIN, T_DO, T_IRQ for touch if fitted. Check your board's silkscreen.

| TFT | Pico |
|---|---|
| VCC | 3V3 OUT (36), and short the J1 pads on the back (bypasses its 3.3 V regulator). Or VSYS with J1 open |
| GND | GND |
| CS | GP9 |
| RESET | GP12 |
| DC | GP8 |
| SDI (MOSI) | GP11 |
| SCK | GP10 |
| LED | GP13, after the test below |
| SDO (MISO), touch, SD card | leave unconnected for now |

**Backlight test before wiring LED to a GPIO:** meter in current mode between 3V3 and LED.
- Under ~10 mA: the board has its own transistor; wire LED straight to GP13 and PWM it.
- More: drive it through a PNP. Emitter to 3V3, collector to LED, 1 kΩ from base to GP13. PWM is
  then inverted (low = bright).

## Dial and buttons

EC11 has 3 pins on one side (A, common, B) and 2 on the other (the push switch).
- Common and one push pin to GND.
- A to GP2, B to GP3, each with a 10 nF cap to GND to calm contact bounce.
- The other push pin to GP16.
- A, B, X, Y: one leg of each tact switch to its GPIO, the other to GND.

All inputs use the internal pull-ups, as `lcd.py` does now. No external resistors.

## Parts

| qty | part | where it goes |
|---|---|---|
| 2 | 1N5817 or SS14 Schottky (1 spare) | battery to VSYS |
| 2 | 100 kΩ | battery divider |
| 5 | 10 kΩ | 2 SDA/SCL pull-ups, 1 PNP base-emitter, 1 ID pull-up, 1 Trust M ID resistor |
| 2 | 1 kΩ | PNP bases (key switch, backlight if needed) |
| 3 | 100 Ω | SDA, SCL, RST series |
| 1 | 33 kΩ | ATECC McGuffin ID resistor |
| 2 | 2N3906 or S8550 PNP | key VCC switch, backlight if needed |
| 2 | 10 nF ceramic | dial A/B |
| 2 | 100 nF ceramic | key VCC, battery divider |
| 1 | 10 µF | key VCC |
| 1 | EC11 rotary encoder with push, plus knob | |
| 4 | 6x6 mm tact switch | A B X Y |
| 1 + 1 | 3.5 mm TRRS panel jack + solder-type TRRS plug | one plug per McGuffin |
| 1 + 1 | 2.5 mm TRRS panel jack + solder-type TRRS plug | one plug per McGuffin |
| 1 | TP4056 USB-C with protection | |
| 1 | SPDT slide switch | power |
| 1 | 18650 holder (+ cell) | |
| | perfboard, 26 to 28 AWG silicone wire, heat shrink | |

Resistor values that are close work the same: 4.7k to 10k for pull-ups, 47 to 220 Ω for the
series resistors. Buy a few extra plugs; they are the fiddly joints.

## Bring-up

One step at a time, on USB power, with the battery disconnected until the last step.

1. **Bare Pico:** flash MicroPython (top README, step 4). REPL works.
2. **Screen:** wire it, do the backlight test, check with a meter that no pin is shorted to its
   neighbour. The ILI9341 driver is still to be written; for now `Pin(13, Pin.OUT).value(1)` should
   light the backlight.
3. **Keys and dial:** `from machine import Pin; [Pin(p, Pin.IN, Pin.PULL_UP).value() for p in (2,3,15,16,17,19,21)]`
   shows 1s, and each switch makes its own 0.
4. **Jacks, nothing in:** GP22 reads 1, `ADC(27).read_u16()` near 65535. With GP14 high (or
   floating), 0 V on the 3.5 mm Ring 2 contact.
5. **McGuffin in:** GP22 reads 0, GP27 matches the ID table. Then:
   ```
   from machine import Pin, I2C
   Pin(14, Pin.OUT).value(0)          # key VCC on
   print(I2C(0, sda=Pin(4), scl=Pin(5), freq=100_000).scan())
   ```
   Trust M shows `[48]` (0x30). ATECC shows `[96]` (0x60) after the wake pulse in
   `app/SOLDERING.md`.
6. **Battery:** meter TP4056 OUT+ (3.7 to 4.2 V) and the Schottky's output before touching the
   Pico. Then connect VSYS, unplug USB, and check `ADC(28)` gives the cell voltage.

## Secure boot (later, not wiring)

The RP2350 can refuse to run firmware not signed with your key: you burn a hash of your public key
into its OTP with `picotool`, and from then on it only boots signed images. It is **permanent**.
Do it on one spare Pico, only after v2 works, and keep the signing key safe: lose it and that
board can never take new firmware.

What it buys the McGuffin: SECURITY.md notes the chip will sign whatever the MCU asks. Secure boot
means the MCU runs only your firmware, so a plugged-in McGuffin only signs what that firmware shows
on the screen and you confirm.

## Still to do

- `firmware/ili9341.py` with the same API as `lcd.py`.
- `firmware/trustm.py` (OPTIGA I2C protocol, P-256 sign) next to `atecc.py`.
- Key detect / ID / power handling and dial input in `wallet.py`.
- Emulator: ILI9341 screen size, dial, a plug-in key.
- Case: wallet body with the jack pair; McGuffin key body.
