# Hardware alternatives

Status 2026-09-16: research only. Nothing in this file has been built. The stack in `README.md`
(Pico 2 W on a Waveshare Pico-LCD-1.3, Adafruit ATECC608 breakout in the gap) is still the
wallet. This is the map of what else the same idea can be, for two shapes in particular:

1. **Key cartridge + base.** The secure element is its own small thing you plug in. The base has
   the MCU, the screen and the controls. Several keys, one base; one key, several bases.
2. **Desk unit.** Separately wired parts in a case we design: a bigger screen, real controls,
   USB-C, a battery.

Prices are single-unit list, seen 2026-09, rounded. Anything marked *unverified* was not read
from a datasheet or a live product page and should be checked before ordering.

## What stays the same

- The key lives in a secure element. It is generated on the chip (`GenKey`), the config zone is
  locked, and the chip signs a 32-byte digest the MCU hands it. It never leaves. `firmware/atecc.py`
  is the whole driver: wake, Read, Nonce, GenKey, Sign, Write, Lock, 175 lines.
- The curve is P-256. `ChipAccount.sol` verifies P-256 through the EIP-7951 precompile and the app
  only knows P-256 points, so any chip that signs P-256 over an external digest drops in and
  anything else means a new contract. This doc stays on P-256.
- `firmware/signer.py` is the seam. One shape, `pubkey() -> (x, y)`, `sign(digest) -> (r, s)`
  low-s, `status() -> dict`, `name`; `SoftSigner` and `ChipSigner` already share it, a third
  backend for another chip goes next to them and nothing above changes.
- An instant-on microcontroller running MicroPython, no OS. The board is on 1.26.1; upstream is
  at 1.29.0 (2026-08-24), which matters below for `machine.USBDevice` and for which boards have
  an official build.

## The key: ATECC608 and its siblings

Every chip that could hold the wallet key, judged by one question: does it generate a P-256 key
on-chip and sign an arbitrary external 32-byte digest with it, from MicroPython, with parts you can
buy one of.

| chip | curve | bus | on-chip GenKey | signs external digest | breakout | bare chip | MicroPython driver | verdict |
|---|---|---|---|---|---|---|---|---|
| ATECC608A (ours) | P-256 | I2C, SWI | yes | yes | Adafruit 4314 ~$5 (out of stock 2026-09), Mikroe Secure 4 Click ~$11 | ~$1.00, in stock, NRND | `firmware/atecc.py`, ucryptoauthlib | what we have |
| ATECC608B | P-256 | I2C, SWI | yes | yes | Mikroe Secure 8 Click ~$10, Microchip DT100104 ~$24 | ~$0.90, in stock | same driver, revision `00006003` | the drop-in |
| ATECC608B-TNGTLS (Trust&Go) | P-256 | I2C addr 0x35 | slots 2 to 4 only | yes | DT100104, Mikroe ECC608 Trust Click (608C now) | 608C replaces it | same, minus Write/Lock config | works, different slot |
| ATECC608B-TFLXTLS (TrustFLEX) | P-256 | I2C addr 0x36 | slots 2 to 4 only | yes | as above | as above | same | works, different slot |
| ATECC508A | P-256 | I2C, SWI | yes | yes | SparkFun DEV-15573 ~$8 (backorder) | ~$1 | same command set | fine, older |
| ECC204 | P-256, one key | I2C 400 kHz or 2-pin SWI-PWM | yes, slot 0 | yes, external only | Microchip EV92R58A ~$27 (mikroBUS), no hobby board | ~$0.44 | none | cheapest signer, no driver |
| ECC206 | P-256, one key | 2-pin SWI-PWM, parasitic power | yes | *unverified* (summary datasheet only) | none; socket kit + DM320118 | ~$0.51 at 10k, 6-week lead | none | the two-contact key, a project |
| DS28E38 / E39 (ADI) | P-256 | 1-Wire, parasitic | yes (PUF) | no: signs a chip-built page-auth message with a host challenge, *unverified* for E38 itself | DS28E38EVKIT ~$77 to $104 | ~$4.45 | maltahan/DS28E38 (ESP32) | not a wallet signer |
| DS28C36 / E36 (ADI) | P-256 | I2C / 1-Wire | yes | same page-auth model, *unverified* | evkits | ~$4.56 | none | same |
| OPTIGA Trust M (Infineon) | P-256/384 (+521, Brainpool, RSA on V3) | I2C 1 MHz, IFX I2C framed protocol | yes | yes, CalcSign over a 32-byte digest | Shield2Go ~$9.50, 0 stock at DigiKey | discontinued at DigiKey | none (C lib, CPython ctypes) | works, heavy host protocol |
| SE050 / SE051 (NXP) | P-256 and many more, secp256k1 and ed25519 included | I2C, T=1 over I2C, ISO7816 APDUs | yes | yes | OM-SE050ARD ~$84; Mikroe Plug&Trust Click ~$15 (retired at SparkFun) | ~$4.35, in stock | none (C middleware) | works, heaviest protocol, the one to remember if the curve ever changes |
| STSAFE-A110 / A120 (ST) | P-256/384 (A120 adds 521, Brainpool, 25519) | I2C 400 kHz, ST framing | yes | yes | X-NUCLEO-SAFEA1B ~$17, X-NUCLEO-ESE01A1 ~$18 | A120 ~$2.66, in stock | none | works, no driver |
| SHA104 / SHA105 | none (SHA-256 MAC) | I2C, SWI | | no | | | | not ECDSA |

### What this says

- **ATECC608B is the answer to "similar chips".** Same packet format, same config zone, same
  slots, same commands; `firmware/atecc.py` runs on it unchanged. Microchip says start new
  designs on the B (AN2237). The B fixes a real bug we have not hit only because the chip is
  alone on its bus: on a shared bus at 300 kHz or below, an A can mistake other traffic for a
  wake pulse and corrupt it. That matters the moment an encoder or a mux shares I2C0 (below).
  Bare 608B is $0.90 and stocked; the hobby breakouts are Mikroe's Secure 8 Click (mikroBUS, so
  wire it) or waiting on Adafruit 4314 restock, which is a 608A.
- **Trust&Go and TrustFLEX are pre-locked.** Config and OTP zones come locked from the fab, slot 0
  and 1 hold factory keys you cannot regenerate, slots 2, 3, 4 accept `GenKey` until you lock the
  slot. So `write_config` / `lock_config` go away and `slot=2` replaces the hardcoded 0 in
  `atecc.py`. Default I2C address is 0x35 / 0x36, not 0x60. Good for a key you want to be blank
  and lockable the day it arrives; no permanent-lock step to get wrong.
- **The I2C address is ours to set.** It is config byte 16; in `firmware/atecc.py` `CONFIG` that
  byte is `0xC0`, the 8-bit form of 0x60. Any value works, written with the normal Write before
  the config lock. After lock the 608B allows one change via UpdateExtra (byte 85, once, only if
  it is 0x00). Two keys at two addresses on one bus is therefore a config choice, not a mux.
- **ECC204 / ECC206 are the small ones.** One key, sign only, no ECDH, no verify. The 204 has a
  normal I2C mode (address 0x39) and costs 44 cents. The 206 is a two-lead contact package
  (2 x 2.35 mm), powered parasitically over its single data line, meant to be glued or
  pogo-pinned, not soldered. That is the physical form of a "key" if a key were one contact and
  a ground. The protocol is not the 608's UART-style SWI; it is Microchip's PWM single-wire (bit
  frames, 100 kbps parasitic), no MicroPython driver exists, so on a Pico it is a PIO program.
- **The ADI DS28xx family is authentication, not signing.** They sign a message the chip
  composes (ROM ID, page data, page number, the host's challenge). A wallet needs the chip to
  sign our digest. Unless the DS28E38 datasheet, which would not download, shows an
  arbitrary-digest command, skip them.
- **OPTIGA, SE050, STSAFE all work on paper** and all speak framed, CRC'd, T=1-style protocols
  with no MicroPython port. Each is a driver project the size of `atecc.py` times three. SE050 is
  the one to remember: it is the chip that also does secp256k1 and ed25519, so if this ever
  needs a Bitcoin or Nostr key, that is the board to reach for.
- **The MCU's own vault is not a substitute.** RP2350 has 8 KB of OTP with soft and hard locks
  and secure boot, but no asymmetric engine: firmware that signs with a key must read it into RAM.
  ESP32-S3's DS peripheral signs without exposing the key, but RSA only; the ECDSA-in-eFuse
  peripheral is on H2/C6/P4, not S3. A discrete element stays the point.

### For a pluggable key

- Wake after hot-plug: the chip wakes on a low SDA pulse and goes back to sleep on its own; our
  `wake()` retries three times. Presence is a wake plus `pubkey()`, cheap enough to poll every
  second when no key is known.
- Supply 2.0 to 5.5 V, IO 1.8 to 5.5 V, so a key built for 3V3 tolerates a 5 V base.
- Sleep current is microamps; a parked key on a jack costs nothing.
- Exposed contacts want ESD protection the breakout does not have; a TVS array on the base side
  of the jack, or the TCA4307 buffer below, is the fix.
- Adafruit's own note: with anything else on the bus run I2C at 400 kHz, or use a 608B.

## The base: MCU boards

Wanted: USB-C, a LiPo charger on board, a STEMMA QT / Qwiic socket on board, an official
MicroPython build, and the radio if the WiFi transport stays.

| board | MCU | radio | USB | Qwiic on board | LiPo charger | MicroPython | ~price | size mm |
|---|---|---|---|---|---|---|---|---|
| Pico 2 W (ours) | RP2350A | WiFi + BT | **micro-USB** | no | no | official `RPI_PICO2_W` | $7 | 51 x 21 |
| Pico 2 | RP2350A | none | micro-USB | no | no | official `RPI_PICO2` | $5 to $6 | 51 x 21 |
| Adafruit Feather RP2350 (6130) | RP2350A, 8 MB PSRAM | none | USB-C | yes | yes | official `ADAFRUIT_FEATHER_RP2350` | $15.50 | 52 x 23 |
| Pimoroni Pico LiPo 2 XL W | RP2350B, 8 MB PSRAM | WiFi + BT (RM2) | USB-C | yes (Qw/ST) | yes (MCP73831, JST-PH) | Pimoroni build; the W asset was not in the v1.29.0-2 release, *unverified* | ~$28 | 77 x 21 |
| Pimoroni Pico Plus 2 W | RP2350B | WiFi + BT | USB-C | yes | no | same caveat | ~$22 | 53 x 21 |
| Adafruit Feather ESP32-S3 (5477) | ESP32-S3, 2 MB PSRAM | WiFi + BLE | USB-C | yes | yes, plus MAX17048 gauge | `ESP32_GENERIC_S3` | $17.50 | 52 x 23 |
| Adafruit Feather ESP32-S3 Reverse TFT (5691) | ESP32-S3 | WiFi + BLE | USB-C | yes | yes | `ESP32_GENERIC_S3` | $24.95 | ~52 x 23 |
| Seeed XIAO RP2350 / ESP32S3 | RP2350A / ESP32-S3R8 | none / WiFi + BLE | USB-C | no | yes (pads) | official `SEEED_XIAO_RP2350`, `SEEED_XIAO_ESP32S3` | $4.90 / $7.49 | 21 x 18 |
| LilyGO T-Display-S3 | ESP32-S3R8 | WiFi + BLE | USB-C | yes | yes | `ESP32_GENERIC_S3` + a custom-built i80 display module | $9 to $23 | 63 x 25 |
| LilyGO T-Deck | ESP32-S3 | WiFi + BLE (+LoRa) | USB-C | Grove | yes, 2000 mAh built in | `ESP32_GENERIC_S3`, SPI ST7789 | ~$47 | 100 x 68 |
| M5Stack Cardputer / Adv | ESP32-S3, no PSRAM | WiFi + BLE | USB-C | Grove | yes, built in | M5's UIFlow2 fork only | $24 (EOL) / $30 | 84 x 54 |
| Waveshare ESP32-S3-LCD-1.28 | ESP32-S3R2 | WiFi + BLE | USB-C via CH343 UART | no | yes | Waveshare build or GENERIC_S3 + gc9a01 | $16 | round 1.28" |
| Seeed XIAO ESP32C3 / C6 | RISC-V | WiFi + BLE | USB-C (serial only) | no | yes | official | $5 | 21 x 18 |

Notes.

- **rp2 keeps all the firmware.** `wallet.py` is built around one 50 ms `machine.Timer` because
  the rp2 scheduler queue is 8 deep and a second timer plus a blocking HTTP call drops the
  console's accept callback for good (`firmware/wallet.py:3-7`, `HANDOFF.md` gotcha 2). That is
  an rp2 fact. Any RP2350 board runs `lcd.py`, `atecc.py`, `net.py` as they are.
- **esp32 is a port change, not a rewrite.** `machine.I2C`, `SPI`, `Pin`, `PWM`, `Timer`,
  `framebuf`, `network.WLAN`, `requests` all exist on `ESP32_GENERIC_S3`. Pin numbers change,
  `SPI(1, ...)` becomes `SPI(2, ...)` or a `SoftSPI`, `network` is the same API, and the
  single-timer dance could become plain `asyncio`, which both ports ship. `net.py`'s TCP console
  is `socket` code and moves too. The emulator does not care which port the firmware thinks it
  is on; its shims are the `machine` API.
- **Feather RP2350 is the closest thing to "Pico 2 W with USB-C, a charger and a socket".**
  Official build, same port, same code, but no radio. The WiFi transport would need a WiFi
  FeatherWing or the transport moves to USB (below). **Pico LiPo 2 XL W** has everything
  including the radio, on Pimoroni's build; confirm the W firmware exists before buying.
- **Feather ESP32-S3 Reverse TFT is a whole base on one board:** 240 x 135 ST7789 on the back,
  three user buttons, USB-C, charger, STEMMA QT. Plug a key in, done. Different port, different
  screen size.
- **Native USB.** `machine.USBDevice` exists on rp2 and on esp32 S2/S3 (not C3/C6, whose USB-C
  is a serial bridge). This is what a USB HID / CTAP transport would sit on (see cool stuff).
- **RP2350 secure boot** would sign the MicroPython UF2 (`picotool seal --sign`, boot key in
  OTP), not the `.py` files on the filesystem, and MicroPython has no support for it. It raises
  the bar on `SECURITY.md`'s "compromised firmware" line but does not close it; the 2024 hacking
  challenge broke the A2 stepping four ways with lab gear (glitch, laser, FIB), A4 fixes most.
  A thread for later, not for this doc.

## Display and controls

`wallet.py` draws into a 240 x 240 RGB565 `framebuf` and hardcodes 240 in `draw_qr`, `bar`,
`draw_home`, `draw_msg` (`firmware/wallet.py:88,142,145,158,255`) and right-edge literals like
the pairing dot at x 226 (`wallet.py:109`), plus `mock.py` and `keytest.py`. Same-resolution,
same-driver panels are an `lcd.py` change (pins, init bytes). Anything else is a `draw_*` pass.

### Displays

| panel | res | driver | bus | ~price | MicroPython | note |
|---|---|---|---|---|---|---|
| Waveshare Pico-LCD-1.3 (ours) | 240 x 240 | ST7789 | SPI | $8 | `lcd.py` | joystick + 4 keys, 52 x 26.5 mm |
| Adafruit 1.54" TFT (3787) | 240 x 240 | ST7789 | SPI, EYESPI | $17.50 | `lcd.py` as is | same pixels, 25% bigger glass, the no-brainer desk panel |
| Waveshare Pico-LCD-2 | 320 x 240 | ST7789 | SPI | $13 | pins + geometry | 4 keys, no joystick, 52 x 35 mm, still a hat |
| Pimoroni Pico Display Pack 2.0 / 2.8 | 320 x 240 | ST7789 | SPI | £16 | Pimoroni build, or generic ST7789 | 4 keys + RGB LED; the 2.8 has a Qw/ST socket on the hat |
| Adafruit 2.0" TFT (4311) | 320 x 240 | ST7789 | SPI, EYESPI | $20 | pins + geometry | bare module, 59 x 36 mm |
| Adafruit 2.4" / 2.8" touch (2478 / 1770) | 320 x 240 | ILI9341 | SPI | $30 | rdagger/micropython-ili9341 | resistive touch |
| Waveshare Pico-ePaper-2.13 | 250 x 122 | SSD1680-class, *unverified* | SPI | $14 | Waveshare demo, nano-gui | 2 s full / 0.3 s partial refresh, 0 µA standby, must full-refresh after some partials |
| Adafruit 2.13" tri-color FeatherWing (4814) | 250 x 122 | SSD1680 | SPI | $25 | nano-gui | red/black/white, slow |
| Adafruit Sharp memory 1.3" (3502) | 168 x 144 | Sharp | SPI | $25 | nano-gui | ~4 µA always-on, mono |
| Pico-OLED-1.3 / FeatherWing OLED (4650) | 128 x 64 | SH1107 | I2C / SPI | $9 / $15 | nano-gui sh1107 | tiny, the 4650 has 3 buttons and STEMMA QT |
| generic 0.96" SSD1306 | 128 x 64 | SSD1306 | I2C | ~$3 | official micropython-lib `ssd1306` | tiny |

Driver health (last commit): russhughes/st7789_mpy 2026-07 (C, needs a custom build),
russhughes/st7789py_mpy 2024-08 (pure Python), peterhinch/micropython-nano-gui 2026-06 (ST7789,
ILI9341, SSD1306, SH1106, e-paper, Sharp), mcauser/micropython-waveshare-epaper 2018 (dead).
Our `lcd.py` needs none of them for ST7789; it is 100 lines of `framebuf` plus init bytes.

### Controls

| part | what | pins | ~price | MicroPython |
|---|---|---|---|---|
| Adafruit ANO rotary navigation encoder (5001) + breakout (5221) | iPod-style wheel: rotary ring around a 5-way nav (up down left right center) | 7 GPIO direct (5 keys + A/B) | $8.95 + $1.50 | keys are `Pin` pull-ups like today; ring via miketeachman/micropython-rotary (2023) or a 20-line IRQ handler |
| ANO I2C adapter (5740) | same encoder over STEMMA QT via a seesaw MCU | I2C | $4.95 | no MicroPython seesaw port exists; would need a small register driver |
| Adafruit 5-way nav switch, through-hole (504) | ALPS SKQUCAA010, the family our joystick is a clone of | 5 GPIO | $1.95 | as today |
| EC11-style rotary encoder with push (377) | 24 detents | 3 GPIO | $4.50 | micropython-rotary |
| I2C rotary encoder + NeoPixel (4991), NeoKey 1x4 (4980) | seesaw over STEMMA QT | I2C | $6 / $10 | same seesaw gap |
| MPR121 capacitive touch (4830) | 12 pads | I2C | $7 | community drivers, not checked |
| Cardputer / T-Deck keyboards | full QWERTY | I2C | | for typing a name, overkill for approve/reject |

The ANO encoder is the desk-unit control. Five directions map one-to-one onto today's
`KEYS["up"|"down"|"left"|"right"|"press"]` so `wallet.py` does not change; the ring is a new
input for scrolling long details and typing. Wire it direct: the I2C adapter needs a seesaw
driver nobody has written for MicroPython. peterhinch/micropython-micro-gui already does menus
from 2 to 5 buttons or an encoder, if the screens ever grow past hand-drawn.

## The key connector

The key is the ATECC608 breakout (25.5 x 17.7 mm) with four lines, 3V3 GND SDA SCL, in a printed
shell. The base has a socket. Candidates:

| connector | contacts | mating order control | cycles | hot-plug story | ~price | verdict |
|---|---|---|---|---|---|---|
| JST-SH 4-pin (STEMMA QT / Qwiic) | 4 | none | JST publishes none; third parties say ~50, *unverified* | Adafruit: I2C "wasn't really designed for hot-plugging" | cable $1 | fine on the bench, no panel-mount part exists, tiny and fragile as a daily plug |
| 3.5 mm TRRS jack + plug | 4 | none: the tip wipes across every jack contact on the way in | audio-grade, thousands | QMK split keyboards use it for I2C and say power off before plugging or "you can short the controller" | jack $1.20 (CUI SJ-43514), plug $1.50 | the satisfying click; needs series resistors and a mating-order plan |
| 3.5 mm TS mono jack (Adafruit 4361, panel mount) | 2 | none | thousands | only for a 1-wire / SWI element (ECC206) | $0.95 | config D only |
| magnetic pogo pair (Adafruit 5358, 4 contacts, right angle) | 4 | by pin length, GND longest | industrial parts say 10k+, Adafruit publishes none | best of the lot; polarised by the magnets | $6.50 a pair | the MagSafe key |
| 2.54 mm card-edge socket + a key PCB with gold fingers | any | by finger length | high | like a Game Boy cartridge | socket ~$2 | cheapest "cartridge" feel, needs a custom key PCB |
| microSD / SIM push-push socket | 8 | by pad geometry | high | | breakout $7.50 | cute, the key would be a custom PCB the size of a SIM |
| USB-C shell carrying I2C | 4 of 24 | | | a 3V3 I2C key will get plugged into a laptop and a charger will put 5 V on it | | no |

### I2C over a jack, the rules

```
   TRRS plug     tip    ring1   ring2   sleeve
   assignment    SDA    SCL     3V3     GND        sleeve mates first and breaks last
                 |      |       |       |
   base side    100R   100R   P-FET   ----         100 R in series on SDA/SCL limits the
                 |      |     or none               wipe-through short; 3V3 to the key can be
                4k7    4k7                          switched on only after presence is seen
   base I2C0   GP4    GP5
```

- Ground on the sleeve, always. Power on the ring next to it. Data on tip and ring1.
- 100 to 330 Ω in series on SDA and SCL. The 608 does not care at 100 kHz.
- Hot-plug bus lock-up: MicroPython `machine.I2C` has no bus-clear (`clear_bus()` PR 13281 was
  closed unmerged 2025-06). The recipe on `OSError`: `deinit()`, drive SCL as a GPIO for 9 to 16
  clocks while SDA is low, pulse a STOP, re-create the `I2C`. Or in hardware: Adafruit TCA4307
  hot-swap I2C buffer (5159, STEMMA QT, $4.95) sits between the base and the jack, disconnects a
  stuck side after 40 ms and clocks it free.
- Presence: with no key known, once a second `wake()`; on success `pubkey()`, compare to the
  paired point, go live. On any I2C error mid-session, drop to "no key", clear the cached point.
  Today `signer.load()` runs once at boot (`firmware/wallet.py` start) and `ChipSigner` caches
  `_pub`; the change is a re-probe path and an "insert key" screen.
- Several keys at once: either give each key its own I2C address before locking (byte 16, above),
  or a PCA9548 mux (Adafruit 5626, eight STEMMA QT ports, $6.95) and every key stays at 0x60.

### The key shell

```
        side view, ~ 45 x 20 x 9 mm printed, two halves, snap or two M2 screws

         ________________________________________
        |  ____________________________________  |
        | |  ATECC608 breakout  25.5 x 17.7    | |==== TRRS plug (or pogo pad, or edge fingers)
        | |  STEMMA QT socket -> 4 wires ------|-|
        | |____________________________________| |
        |________________________________________|
                       lanyard hole
```

The breakout's own STEMMA QT socket is the internal connector; four wires to the plug. A
different key (Trust&Go, a 608B on a Click board, a hand-soldered 608B on a 2 x 2 cm PCB) is a
different shell insert, same plug. Colour of the shell = which key.

## Configurations

Costs exclude a printer, a USB cable and the parts already on the bench.

### A. Cartridge + the stack we have

The smallest step. The Pico 2 W and the Pico-LCD-1.3 stay, the case stays, the firmware stays.
The ATECC608 leaves the gap between the boards and moves into a shell on a plug; the base grows a
panel-mount jack wired to the same four header positions the wires go to today.

| part | ~price | link |
|---|---|---|
| everything in `README.md` step 1 (Pico 2 W, Pico-LCD-1.3, ATECC608 4314, STEMMA QT cable) | $35 | |
| panel-mount TRRS jack, CUI SJ-43514 | $1.20 | DigiKey |
| TRRS metal plug for the key end | $1.50 | SparkFun |
| or: Adafruit DIY magnetic connector pair, 4 contacts (5358) | $6.50 | Adafruit |
| optional: TCA4307 hot-swap I2C buffer (5159) | $4.95 | Adafruit |
| 2 x 100 Ω resistors | | |

Wiring, base side, unchanged from `app/SOLDERING.md`: red 3V3 pin 36, black GND pin 38, blue SDA
GP4 pin 6, yellow SCL GP5 pin 7; the jack sits in the case wall at the USB end, where the wires
already leave the header. The TCA4307 goes in the ~11 mm gap the ATECC used to occupy.

Firmware: `signer.py` gets a `probe()` for hot-plug, `wallet.py` gets a "plug in your key" state
and re-probes when the chip errors. `lcd.py`, `atecc.py`, the emulator: untouched.
Case: `tools/zezbase` gains a 6 mm round hole in one end wall; a new `case/key_shell.py`.

Why: you can hand someone the base, keep the key; two keys for two vaults on one base; a key
in the drawer is a cold key. Costs $40, no new solder if the jack's lugs take the pushed-in
wires like the header does.

### B. One-board base: Feather ESP32-S3 Reverse TFT

Plug-and-play like today, different shape, USB-C and a battery for free.

| part | ~price | link |
|---|---|---|
| Adafruit Feather ESP32-S3 Reverse TFT (5691): 240 x 135 ST7789, 3 buttons, USB-C, charger, STEMMA QT | $24.95 | Adafruit |
| ATECC608 breakout (4314) + shell + jack as in A | $5 + $3 | |
| STEMMA QT cable to the jack | $1 | |
| 502030 LiPo 250 mAh, JST-PH | ~$5 | Amazon |
| optional: FeatherWing Doubler for a second wing (e.g. the OLED + 3 buttons 4650) | $7.50 | |

Wiring: none. The key jack hangs off the STEMMA QT socket; the LiPo plugs into the JST-PH.

Firmware: port `lcd.py` to the S3's pins and 135 x 240 (the TFT is ST7789, so the init bytes are
the same), redo `draw_*` for the smaller frame, map 3 buttons to A / B / Y with "up" and "down"
on a long press or a second wing. `net.py` runs as is on `ESP32_GENERIC_S3`. The single-timer
architecture can stay or become asyncio. Emulator: new pin map and frame size in
`emu/core/runtime.mjs`, a new STL.

Why: the least wiring of any option with a charger and USB-C; a 52 x 23 mm base the size of the
key. Cost about $45.

### C. Desk unit: wired parts in our own case

Everything on wires, the way a deliberate object is built. The Pico 2 W stays the brain because
it keeps the radio, the rp2 port and all the firmware; the trade is that flashing is still
micro-USB inside the case, and USB-C on the outside is for charging.

| part | ~price | link |
|---|---|---|
| Pico 2 W | $7 | |
| Adafruit 1.54" 240 x 240 ST7789 (3787), or 2.0" 320 x 240 (4311) | $17.50 / $20 | Adafruit; both are EYESPI, so also the EYESPI breakout (5613, *unverified* price ~$3) or solder the FPC header |
| Adafruit ANO rotary navigation encoder (5001) + breakout (5221) | $8.95 + $1.50 | Adafruit |
| panel-mount TRRS jack (SJ-43514) or magnetic pogo pair (5358) | $1.20 / $6.50 | |
| TP4056 USB-C charger module with DW01A protection | ~$2 | Amazon 5-pack |
| 803040 LiPo 1000 mAh with PCM, or 502030 250 mAh | ~$5 | |
| P-FET (DMG2305UX) or Schottky into VSYS, per the Pico 2 W datasheet §3.5 | $1 | |
| slide switch, TVS array, a few resistors | $2 | |
| ATECC608 key in its shell | $8 | |

About $60, roughly 30 solder joints, all through-hole or module pads.

Wiring keeps `lcd.py`'s numbers so the pin map, and the emulator's copy of it, do not change:

| signal | Pico GPIO | pin | goes to |
|---|---|---|---|
| SPI1 SCK / MOSI | GP10 / GP11 | 14 / 15 | display SCK / MOSI |
| DC / CS / RST / BL | GP8 / GP9 / GP12 / GP13 | 11 / 12 / 16 / 17 | display |
| up / down / left / right / press | GP2 / GP18 / GP16 / GP20 / GP3 | 4 / 24 / 21 / 26 / 5 | ANO nav switches, common to GND |
| A / B / X / Y | GP15 / GP17 / GP19 / GP21 | 20 / 22 / 25 / 27 | four tact switches if kept, else unused |
| encoder A / B | GP14 / GP22 | 19 / 29 | ANO ring |
| I2C0 SDA / SCL | GP4 / GP5 | 6 / 7 | key jack via 100 Ω |
| VSYS | | 39 | P-FET from the charger's BAT+ |
| VBUS | | 40 | gates the P-FET so USB wins over the battery |
| 3V3 / GND | | 36 / 38 | display, encoder, key jack |

```
      top view, ~ 90 x 60 mm, lid 2 mm, parts on a 3 mm shelf

       ______________________________________________
      |   ______________________     _____           |
      |  |                      |   /     \          |   screen left, wheel right,
      |  |   1.54" 240 x 240    |  |  ANO  |   [A]   |   two tact keys for sign / reject
      |  |                      |   \_____/    [Y]   |   under the thumb
      |  |______________________|                    |
      |  (o) key jack                     USB-C  [=] |
      |______________________________________________|
```

Firmware with the 1.54": `lcd.py` init bytes may want a different `0x36` value and the panel
has no offset; otherwise the same 240 x 240 frame, `wallet.py` untouched. With the 2.0" it is
the `draw_*` pass. Add a 30-line encoder reader. Battery: read VSYS/3 on ADC3 for a gauge; the
backlight PWM already exists for dimming (`lcd.py` `backlight()`). Case: `case/gen.py` style,
every dimension a name at the top.

Why: this is the object. The screen you can read across a desk, a wheel you can scroll with,
the key on a jack in the front, charging over USB-C, a lanyard hole. If Pimoroni ships the
Pico LiPo 2 XL W firmware, that board replaces the Pico 2 W, the TP4056 and the P-FET in one go
and gives USB-C flashing too.

### D. Two-contact key (an investigation, not a build)

An ECC206 is a 2 x 2.35 mm two-lead contact package: ground and one data line that also powers
it. Put one on a coin-sized PCB with two pads, or in a mono 3.5 mm plug, and the key is a ring
on a keychain with no visible electronics. The base drives Microchip's PWM single-wire protocol
(100 kbps parasitic) from a PIO state machine; nobody has written that for MicroPython, the
full datasheet is under NDA, the chip has a 6-week lead and no hobby board. The ECC204 in its
I2C mode (0x39, 44 cents) is the same chip family with a normal bus and is the thing to try
first on a breadboard, to learn the command set, before committing to the two-pin part.

The DS28E38 is the other two-contact candidate (1-Wire, which MicroPython has, and a MicroPython
driver exists), but it signs a chip-composed page-auth message, not our digest, so it would
need a different contract or turn out to be unusable. Read its datasheet before buying.

### Summary

| | A. cartridge + stack | B. Feather base | C. desk unit | D. two-contact key |
|---|---|---|---|---|
| cost | ~$40 | ~$45 | ~$60 | ~$20 + a PIO driver |
| solder joints | 0 to 4 | 0 | ~30 | few, SMD contact pads |
| screen | 1.3" 240 x 240 | 1.14" 240 x 135 | 1.54" 240 x 240 or 2.0" 320 x 240 | any base |
| controls | joystick + 4 | 3 buttons | ANO wheel + 2 | any base |
| battery | no | yes, on board | yes, wired | |
| USB-C | no | yes | charging only | |
| radio | WiFi | WiFi | WiFi | |
| firmware delta | hot-plug path | port to esp32, new geometry | encoder reader, maybe geometry | a new signer backend and a PIO program |
| case | jack hole in the zez0000 base + a key shell | new, simple | new, the real one | shell only |

## Firmware impact

For whoever builds one; none of this is on this branch.

- `firmware/signer.py` is the seam for another chip: a `TrustGoSigner` is `ChipSigner` with
  `slot=2` and no lock methods; an `Ecc204Signer` is a new driver behind the same four names.
- `firmware/lcd.py` is the only pin and panel binding, but `wallet.py`, `mock.py` and
  `keytest.py` hold the 240 x 240 geometry, and the emulator holds its own copy of the pin map
  (`emu/core/runtime.mjs:18-21`, `W, H = 240`) and STL names (`emu/web/device3d.js:74`). A
  second board is the moment to make a `board.py` (pins, width, height, key map) that `lcd.py`,
  `wallet.py` and the emulator stub all read.
- Hot-plug is a state, not a driver feature: "no key" screen, periodic probe, drop on error.
- On esp32, `machine.Timer` and the scheduler-queue workaround are not needed; asyncio would do.

## Cool stuff this opens up

- **A base on every desk, one key in the pocket.** The sign-in chip idea literally: the base is a
  terminal, the key is you. Bases can be different shapes (A, B, C above) and share one key.
- **Two keys, one screen.** Two addresses on one bus, or a mux: a 2-of-2 transfer where both keys
  must be in the base, shown on one screen, signed twice. The contract already knows one P-256
  signer; a second is a `ChipAccount` variant, not a new idea.
- **Key and base recognise each other.** The 608 does ECDH. A base can hold its own 608 (or a
  Trust&Go, pre-provisioned) and derive a shared secret with the key on insertion; a base refuses
  a key it has not been introduced to, a key's owner can list the bases it trusts on the app.
  Slot 1 to 7 are free for that.
- **The same key as a passkey.** P-256 is exactly the WebAuthn ES256 curve. `machine.USBDevice`
  on rp2 / S3 can present a USB HID; CTAP2 over HID with self-attestation is a protocol project,
  but the outcome is a hardware passkey whose key is the same chip that signs the vault, in a
  printed shell, for $5. Pair it with a base that shows what site is asking.
- **Air-gapped desk unit.** Config C with a plain Pico 2: no radio, the request comes in as a QR
  on the laptop screen read by a camera module, the signature goes back as a QR on the 1.54".
  The app already shows the vault QR; the reverse path is a QR decoder on the Pico, which
  SeedSigner does on a Pi.
- **Always-on plate.** An e-ink base that shows the vault address and balance with the power off;
  the AMS two-colour QR already inlaid in `case/zez0000/base_v5_qr` is the physical half of the
  same idea.
- **Physical key switch.** A slide switch in the base that breaks SDA. Signing is impossible with
  the switch off, whatever the firmware is doing; the sort of guarantee `SECURITY.md` says the
  chip alone cannot give against compromised firmware.
- **Colour = key.** Shell colour and an RGB LED on the base that lights the key's colour when it
  is recognised, from a byte stored in slot 8.
- **USB transport.** With USB-C on the base, the request could arrive over USB HID or serial
  from the browser (WebHID / WebSerial) instead of WiFi, which removes the LAN, the app URL and
  the unauthenticated HTTP from `SECURITY.md` in one move.

## Open questions

- Adafruit 4314 is out of stock and is a 608A: is the next key a bare 608B on a 2 x 2 cm PCB we
  have made (four pads, a decoupling cap, done), or Mikroe's Secure 8 Click on wires?
- Does the Pimoroni Pico LiPo 2 XL W have a shipping MicroPython W build? If yes, C gets USB-C
  flashing and loses two parts.
- TRRS or magnetic pogo for the daily plug: print both jacks into one test base and live with
  them a week.
- Does the pushed-in-wire trick hold on a jack's solder lugs, or is A the first soldered thing?
- 1.54" versus 2.0": is the `draw_*` pass worth 80 more pixels of width?
- ECC204 on a breadboard: how far is its command set from the 608's, and is a two-contact key
  worth a PIO driver?
