# picowallet

A cheap, off-the-shelf hardware wallet. Three Amazon parts, four soldered wires, a battery, a printed case. Started 2026-09-05.

The secure element (ATECC608) holds the key and signs. The Pico runs the screen and buttons. On chain, a smart account with a P-256 verifier accepts the ATECC's signatures.

## Parts
| part | ASIN | ~price |
|---|---|---|
| Raspberry Pi Pico 2 W, pre-soldered header (Freenove) | B0DRJXPPWL | $12 |
| Waveshare Pico-LCD-1.3 (240×240 ST7789, joystick, A/B/X/Y) | B092VVCBQP | $15 |
| ATECC608 breakout (2-pack) | B0G58G6FFR | $8 for 2 |
| LiPo 502030 (5×20×30 mm, ~250 mAh) or 401230 | TBD | $5 |
| LiPo charger (see PLAN.md) | TBD | $5 |

## Layout
```
[ Pico-LCD-1.3 : screen, joystick, A/B/X/Y ]   <- female header
[ gap ~11 mm : ATECC608 breakout + LiPo    ]
[ Pico 2 W, component side up, USB out end ]   <- male header
```

## Wiring
Pico pin | goes to
---|---
3V3 (OUT) | ATECC VCC
GND | ATECC GND
GP4 (I2C0 SDA) | ATECC SDA
GP5 (I2C0 SCL) | ATECC SCL

Solder to the header solder blobs on the Pico's component side (they face the gap). Everything else on the Pico is taken by the LCD board.

Pico-LCD-1.3 uses: DC GP8, CS GP9, SCK GP10, MOSI GP11, RST GP12, BL GP13, keys A GP15 / B GP17 / X GP19 / Y GP21, joystick up GP2 / down GP18 / left GP16 / right GP20 / press GP3. (Verify against waveshare.com/wiki/Pico-LCD-1.3.) Free: GP0/1, GP4/5, GP6/7, GP14, GP22, GP26–28.

## Docs
- `PLAN.md` — the build plan
- `buildlog/BUILDLOG.md` — photos and what happened, dated
- `case/` — STLs and the generator
- `firmware/` — MicroPython for the Pico
