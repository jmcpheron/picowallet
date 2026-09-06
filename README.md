# picowallet

A hardware wallet for one stablecoin, built from three off-the-shelf parts in an evening, no
soldering. It shows your balance in dollars. When a website asks it to send money, it puts the
amount and the recipient on its own screen and does nothing until you press the green button.

![picowallet](buildlog/images/2026-09-05-18-hero-case-on-black.jpg)

It is deliberately narrow: one token (USDS), one vault contract, one key that lives in a secure
element and never leaves it. That is what makes it small enough to build, read, and change.
Fork it, swap the token, redraw the screens, print a different case.

On 2026-09-05 it sent 5 USDS to atg.eth on Ethereum mainnet:
[`0x0fbd390b…`](https://etherscan.io/tx/0x0fbd390b3e82bc4566f9ef9c66c178e58904debaf728ec9d941b4090610c6257).

## How it works

```
website ──"send $5 to atg.eth"──▶ app (queue + relay, runs on your laptop)
                                     │  the wallet polls over WiFi
                                     ▼
                              picowallet
                              rebuilds the EIP-712 digest from the fields it shows you
                              screen:  SIGN  $5 USDS to atg.eth  REJECT
                              ATECC608 signs the digest (P-256), key never leaves the chip
                                     │  (r, s)
                                     ▼
                         relay pays gas ──▶ ChipAccount.executeTransfer ──▶ USDS.transfer
```

- The key is generated inside an **ATECC608** secure element and cannot be read out.
- On chain, a small vault contract (`ChipAccount`) holds the stablecoin and moves it only with a
  valid P-256 signature from that key, over a digest that includes recipient, amount, nonce,
  deadline, chain and contract. Verification uses the RIP-7212 precompile where the chain has it.
- The wallet **rebuilds the digest itself** from the fields on its screen. If the app's digest does
  not match, it refuses. The screen cannot be lied to.
- The relay just pays gas. It cannot spend anything.

## 1. Order the parts

| part | ~price | link |
|---|---|---|
| Raspberry Pi Pico 2 W, **pre-soldered header** | $12 | Amazon `B0DRJXPPWL` (Freenove) or any Pico 2 W with headers |
| Waveshare Pico-LCD-1.3 (240×240 IPS, joystick, A/B/X/Y) | $15 | Amazon `B092VVCBQP` |
| Adafruit ATECC608 breakout, STEMMA QT | $6 | Adafruit 4314 |
| STEMMA QT / JST-SH 4-pin cable with bare wire ends | $1 | Adafruit 4209 (or cut any STEMMA QT cable in half) |
| micro-USB cable, data not charge-only | | |

About $35. No soldering iron.

## 2. Print the case

`case/waveshare-13-pico-lcd-case-tomas-plass.stl`: both halves in one file, PLA, 0.2 mm layers,
no supports. Snaps together, micro-USB slot on the end, screen window, the four buttons and the
joystick poke through. Keycaps and a joystick dome are in `case/out/` (PLA, 0.12 mm layers).
`case/gen.py` regenerates them if your parts differ.

## 3. Put it together

![the stack: Pico on the LCD board, ATECC breakout in the gap](buildlog/images/2026-09-05-22-stack-with-atecc.jpg)

1. Plug the Pico into the LCD board's female header, component side toward the LCD, USB at the
   joystick end.
2. Plug the STEMMA QT cable into the ATECC breakout.
3. Push the cable's four bare wires into the LCD board's header socket **beside** the Pico pins.
   The spring contact grips both. Counting from the USB end, right side: red into 3V3 (pin 36),
   black into GND (pin 38). Left side: blue into GP4 (pin 6), yellow into GP5 (pin 7). Tug lightly.
4. Jam the breakout into the gap between the two boards, wires flat.

![ATECC608 breakout jammed in the gap](buildlog/images/2026-09-05-21-atecc-jammed-in-the-gap.jpg)

`SOLDERING.md` has the pinout diagram and the soldered version if you want it permanent.

## 4. Flash the firmware

1. Hold BOOTSEL on the Pico, plug it into a computer, release. A drive named `RP2350` appears.
2. Drag [MicroPython for the Pico 2 W](https://micropython.org/download/RPI_PICO2_W/) (`.uf2`)
   onto it. The drive disappears and the board reboots.
3. On the computer: `uv tool install mpremote` (or `pip install mpremote`).
4. Copy `firmware/secrets.example.py` to `firmware/secrets.py`. Put in your WiFi and the app URL
   (step 6 gives you that, `http://<your-laptop-lan-ip>:3001`).
5. First time, over USB: `mpremote cp firmware/*.py :` then `mpremote reset`.

From then on the board is on WiFi and `./tools/push` deploys firmware over the air. `./tools/pico`
is a console to it (`./tools/pico ls`, `./tools/pico exec 'print(1)'`).

The screen comes up, finds the chip on the bus, and shows "no key" until step 5.

## 5. Set up the chip (once)

A fresh ATECC608 refuses to make a key until its config zone is locked, once, permanently. This
is normal; every chip in use is locked. Locking puts no key in and does not stop you making new
keys later. The wallet does it from the app's Setup page, but only after you opt in on the device,
because both steps are irreversible:

1. In `firmware/secrets.py` set `ALLOW_LOCK = True` and `ALLOW_GENKEY = True`, then `./tools/push`.
2. Run the app (step 6), open `/setup`, press **Lock config zone**, then **Generate key**, then
   **Pair key**. The wallet shows a green dot.
3. Set both flags back to `False` and push again. Now nothing on the network can replace the key.

Moving a chip that is already locked and paired (say, from the demo this grew out of)? Skip to
Pair. `reference/pi/README.md` shows the same steps from a Raspberry Pi with real output.

## 6. Run the app

`app/` is a Scaffold-ETH 2 project: the vault contract, a Next.js site, and the queue and relay as
route handlers. Locally, with play money:

```sh
cd app && yarn install
yarn chain                                  # anvil, a local chain
yarn deploy                                 # ChipAccount + MockUSDS, 1000 USDS in the vault
yarn workspace @se-2/nextjs dev -p 3001     # http://localhost:3001
```

The wallet announces its key to the app. On `/setup` press **Pair**. The screen shows the
vault balance and a QR of the vault address. Type a recipient and an amount on the Send page.
The wallet turns green. Press A. Watch it settle.

Mainnet, with real money, in `app/packages/nextjs/.env.local`:

```
NEXT_PUBLIC_TARGET_NETWORK=mainnet
RELAYER_KEYSTORE=<a foundry keystore name>          # an account with a little ETH for gas
RELAYER_KEYSTORE_PASSWORD_FILE=/path/to/password.txt
USDS_ADDRESS=0xdC035D45d973E3EC169d2276DDab16f1e407384F
```

Deploy your own vault with the chip's public key baked in (the Setup page shows it):

```sh
# app/packages/foundry/.env: CHIP_PUBKEY_X=0x… CHIP_PUBKEY_Y=0x… USDS_ADDRESS=0x…
cd app && yarn deploy --network mainnet --keystore <name>
```

Send USDS to the vault address it prints. Scan the QR on the wallet to get that address into
your phone wallet. Each transfer costs the relay about 82k gas.

## The screens

![SIGN? $69 USDS to atg.eth, green bar at A, red bar at Y](buildlog/images/2026-09-05-20-sign-screen-69-usds.jpg)

**Home:** balance in dollars, a QR of the vault to deposit into, chain label top-left so test money
and real money never look alike, pairing dot top-right, a warning line along the bottom (relay
gas low, unpaired, app unreachable). Refreshes every 12 s and flashes the delta when money moves.

**Sign:** green SIGN bar in line with the A button, red REJECT bar in line with Y. Amount,
recipient name and address between them. Joystick down shows nonce, deadline, chain, vault and the
digest the device computed.

## Change it

- **Another token:** `USDS_ADDRESS` in the app env. The wallet reads the symbol and decimals from
  the app. The contract is token-agnostic.
- **Another chain:** `targetNetworks` in `app/packages/nextjs/scaffold.config.ts`. The wallet
  shows the chain id it is told and bakes it into the digest.
- **The screens:** `firmware/wallet.py`, functions `draw_home` and `draw_confirm`. 240×240,
  framebuf, an 8×8 font scaled up. `./tools/push` and look.
- **The case:** `case/gen.py`, CadQuery, every dimension is a named number at the top.
- **The contract:** `app/packages/foundry/contracts/ChipAccount.sol`, 100 lines, 12 tests.

## What is where

| path | what |
|---|---|
| `firmware/` | MicroPython for the Pico: `wallet.py` loop and screens, `atecc.py` chip driver, `signer.py`, `eip712.py` + `keccak.py` + `p256.py` pure-Python crypto, `lcd.py`, `net.py` |
| `app/` | contracts, tests, site, relay |
| `case/` | STLs, the generator, the measurements |
| `tools/` | `pico` console, `push` firmware, `qr` (QR of the vault for the screen) |
| `buildlog/` | dated notes and photos of what actually happened, including the mistakes |
| `reference/` | the Pi signer this grew out of, with the fresh-chip guide; SeedSigner cap parts (MIT) |
| `PLAN.md`, `SOLDERING.md` | the plan, and the wiring guide |

## Trust model, short

The chip key is the only thing that can spend the vault. The relay only pays gas. The app has no
auth, so anyone who can reach it on your network can queue a request; that is why the wallet shows
every request and signs nothing without a button press. The contract's admin can re-pair a new
key; for real money hand that to a multisig or burn it. An AI audit of the contract is summarized
in the [demo it grew out of](https://github.com/clawdbotatg/ATECC608-demo).

## Credits

Grew out of [ATECC608-demo](https://github.com/clawdbotatg/ATECC608-demo) (a Pi doing the same
job). Case v0 by [Tomáš Plass](https://www.printables.com/model/1322102-waveshare-pico-13-lcd-case),
CC BY-NC. Cap and joystick geometry learned from the
[SeedSigner](https://github.com/SeedSigner/seedsigner) enclosures, MIT. App scaffold by
[Scaffold-ETH 2](https://scaffoldeth.io).

## License

MIT for everything here except where noted: the v0 case STL is Tomáš Plass's, CC BY-NC 4.0;
the SeedSigner parts in `reference/seedsigner/` are MIT with their own copyright; `app/` carries
Scaffold-ETH 2's MIT license.
