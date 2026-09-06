# picowallet

A hardware wallet for stablecoins that you can build from three Amazon parts in an evening, with no
soldering. It shows your balance in dollars, and when a website asks it to send money it puts the
amount and the recipient on its screen and waits for you to press the green button.

![picowallet](buildlog/images/2026-09-05-18-hero-case-on-black.jpg)

On 2026-09-05 it sent 5 USDS to atg.eth on Ethereum mainnet, signed by the secure element inside it:
[`0x0fbd390b…`](https://etherscan.io/tx/0x0fbd390b3e82bc4566f9ef9c66c178e58904debaf728ec9d941b4090610c6257).

## How it works

```
website ──"send $5 to atg.eth"──▶ app (queue + relay)
                                     │  poll
                                     ▼
                              picowallet (WiFi)
                              rebuilds the EIP-712 digest from the fields it shows you
                              screen: SIGN? $5 USDS to atg.eth      A = sign   Y = reject
                              ATECC608 signs the digest (P-256), key never leaves the chip
                                     │  (r, s)
                                     ▼
                         relay pays gas ──▶ ChipAccount.executeTransfer ──▶ USDS.transfer
```

- The private key lives in an **ATECC608** secure element. It never existed anywhere else.
- On chain, a small vault contract (`ChipAccount`) holds the stablecoin and accepts P-256
  signatures from that key. Verification uses the RIP-7212 precompile where the chain has it.
- The device **rebuilds the digest itself** from the fields on screen. If the website's digest
  does not match what is displayed, the device refuses. The screen cannot be lied to.
- A relay account pays gas. It cannot spend anything; it can only refuse.

## The three parts

| part | what it does | ~price |
|---|---|---|
| Raspberry Pi Pico 2 W with pre-soldered header | runs the screen, buttons, WiFi | $12 |
| Waveshare Pico-LCD-1.3 (240×240 IPS, joystick, A/B/X/Y) | the face of the wallet | $15 |
| ATECC608 breakout with a STEMMA QT / Qwiic connector (Adafruit 4314 or similar) | holds the key, signs | $6 |

Plus a STEMMA QT cable with bare or female Dupont ends, a micro-USB cable, and a printed case.

## Put it together, no solder

![the stack: Pico on the LCD board, ATECC breakout in the gap](buildlog/images/2026-09-05-22-stack-with-atecc.jpg)

1. Plug the Pico into the LCD board's female header, component side toward the LCD.
2. Plug the STEMMA QT cable into the ATECC breakout.
3. Push the cable's four wires into the LCD board's header socket **beside** the Pico pins. The
   spring contact grips both. Counting from the USB end: red into 3V3 (pin 36), black into GND
   (pin 38), blue into GP4 (pin 6), yellow into GP5 (pin 7). Tug lightly, then tape flat.
4. Tuck the breakout into the gap between the boards.

![ATECC608 breakout jammed in the gap](buildlog/images/2026-09-05-21-atecc-jammed-in-the-gap.jpg)

`SOLDERING.md` has the pinout diagram and the soldered version if you want it permanent.

## Firmware

MicroPython on the Pico. Copy `firmware/secrets.example.py` to `firmware/secrets.py`, fill in WiFi
and the app URL, then:

```sh
uv tool install mpremote                  # or pip install mpremote
./tools/push                              # copies firmware/*.py and reboots the board
```

The first flash needs USB: hold BOOTSEL, plug in, drag the MicroPython `.uf2` onto the `RP2350`
drive, then push over USB once. After that the board is on WiFi and `./tools/pico` reaches it
at `picowallet.local` for everything (`./tools/pico ls`, `./tools/pico exec 'print(1)'`).

What is in `firmware/`:

| file | what |
|---|---|
| `wallet.py` | the loop: announce to the app, poll, show, sign on A, reject on Y |
| `atecc.py` | ATECC608 over I2C: wake, serial, public key, sign a 32-byte digest |
| `signer.py` | uses the chip if it answers, else a software P-256 key (dev only) |
| `eip712.py`, `keccak.py`, `p256.py` | pure Python; the device checks the digest and can verify signatures itself |
| `lcd.py` | ST7789 driver, keys, joystick |
| `net.py`, `boot.py` | WiFi and a TCP console on port 2323 so the board can be developed over the air |

Two things learned the hard way, both in `buildlog/BUILDLOG.md`: main.py must return to the REPL
(the console is only read when the board idles), and nothing in a timer callback may block for
long (the scheduler queue is 8 deep). The wallet runs off one 50 ms timer and pauses it around
network calls.

## The app

`app/` is a Scaffold-ETH 2 project, forked from
[ATECC608-demo](https://github.com/clawdbotatg/ATECC608-demo): the `ChipAccount` vault contract,
a Next.js site with the queue and the relay as route handlers, and a Setup page to pair a chip.

```sh
cd app && yarn install
yarn chain        # anvil
yarn deploy       # ChipAccount + MockUSDS, 1000 USDS in the vault
yarn workspace @se-2/nextjs dev -p 3001
```

Point the wallet's `APP_URL` at `http://<your-lan-ip>:3001`. It announces its key; press
**Pair** on `/setup`; the screen shows the vault balance and a green dot. Type a recipient and an
amount on the Send page, and the wallet turns green. For mainnet, `app/packages/nextjs/.env.example`
lists the four variables (network, relay keystore, its password file, USDS address).

## The screens

![SIGN? $69 USDS to atg.eth, green bar at A, red bar at Y](buildlog/images/2026-09-05-20-sign-screen-69-usds.jpg)

| home | sign |
|---|---|
| balance in dollars, a QR of the vault to deposit into, chain label top-left, pairing dot top-right, warnings along the bottom (relay gas low, unpaired, app unreachable). Refreshes every 12 s and flashes the delta when money moves. | green SIGN bar in line with the A button, red REJECT bar in line with Y, amount, recipient name and address between them. Joystick down shows nonce, deadline, chain, vault and the digest. |

## Case

`case/` has a printable v0 (Tomáš Plass's Waveshare Pico 1.3 LCD case, CC BY-NC) and
`case/gen.py`, a CadQuery generator for press-fit keycaps and a joystick dome. The v1 case with
floating caps and a battery pocket is designed there too; see `case/BUTTONS.md`.

## What is where

| path | what |
|---|---|
| `firmware/` | MicroPython for the Pico |
| `app/` | contracts, site, relay |
| `case/` | STLs and the generator |
| `tools/` | `pico` (talk to the board), `push` (deploy firmware), `qr` (QR of the vault for the screen) |
| `buildlog/` | dated notes and photos, what actually happened |
| `reference/` | the Pi signer from the demo this grew out of, and SeedSigner cap parts (MIT) |
| `PLAN.md`, `SOLDERING.md` | the plan, and the wiring guide |

## Trust model, short

The chip key is the only thing that can spend the vault. The relay only pays gas. The app has no
auth: anyone who can reach it can queue a request, which is why the wallet shows every request
and signs nothing without a button press. The contract's admin can re-pair a new key; for real
money hand that to a multisig or burn it. Audit notes for the contract are in the demo's README.
