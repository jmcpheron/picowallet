# picowallet

A hardware wallet for one stablecoin, built from three off-the-shelf parts in an evening, no
soldering. It shows your balance in dollars. When a website asks it to send money, it puts the
amount and the recipient on its own screen and does nothing until you press the green button.

![picowallet](buildlog/images/2026-09-05-18-hero-case-on-black.jpg)

The main flow is deliberately narrow: one token (USDS), one vault contract, one key that lives in
a secure element and never leaves it. An advanced hardware-signed call can recover other assets or
interact with contracts. Fork it, swap the token, redraw the screens, print a different case.

On 2026-09-05 it sent 69 USDS to atg.eth on Ethereum mainnet:
[`0x87638ae1…`](https://etherscan.io/tx/0x87638ae169eccb9f002d4eb6ce8b60e7d6603e4d3d4e562164ea10e9023f9313).

> **Security notice:** that historical deployment is legacy authorization v1 with a mutable signer.
> Do not fund or copy it. Current source is authorization v5; read [`SECURITY.md`](SECURITY.md) before use.

## Current contract

Authorization v5 is deployed on Ethereum mainnet at
[`0x4564fA634b073AcBcA814DCA5210835EC9376324`](https://etherscan.io/address/0x4564fA634b073AcBcA814DCA5210835EC9376324).

- No admin, upgrade, or unsigned spending path.
- Hardware-signed USDS transfers and arbitrary contract calls.
- ETH and accidental-token recovery through signed calls.
- Hardware-signed ENS reverse-name setup.
- Fixed recovery wallet with a 14-day signer-change delay. Any valid current-chip action cancels it.

**Audit:** [One Dollar Audit engagement 850](https://www.onedollaraudit.com/audit/850) reviewed this
exact deployment on 2026-09-06. [Full report](https://bafkreiha7yyl727uubma4shj2f5z5mlnezuya7wqg7yzqkjaqr443k4eg4.ipfs.community.bgipfs.com/):
3 high, 3 medium, 4 low, 3 informational. Its main warnings are known trade-offs: a compromised chip
can keep cancelling recovery, approvals can outlive signer recovery, and the fixed recovery wallet
is a single point of failure. This is a PoC, not an audit guarantee.

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
  valid P-256 signature from the current hardware key, over a digest that
  includes recipient, amount, nonce, deadline, chain and contract. There is no admin or upgrade.
  A fixed recovery wallet can rotate the signer only after an uninterrupted 14-day delay.
- The wallet **rebuilds the digest itself** from the security-critical raw fields and refuses a
  mismatch. Names, symbols, and formatted values are untrusted display hints; production forks must
  pin the chain/vault/token and use authenticated transport as described in `SECURITY.md`.
- The relay just pays gas. It has no contract privilege and cannot replace the signer.
- Chip-signed general execution can recover accidental tokens/ETH and interact with contracts.
  The signature covers the exact target, ETH value, calldata, nonce, deadline, chain, and wallet.
  This is powerful: approve unknown calls only after decoding every field.

## 1. Order the parts

| part | ~price | link |
|---|---|---|
| Raspberry Pi Pico 2 W, **pre-soldered header** | $12 | Amazon `B0DRJXPPWL` (Freenove) or any Pico 2 W with headers |
| Waveshare Pico-LCD-1.3 (240×240 IPS, joystick, A/B/X/Y) | $15 | Amazon `B092VVCBQP` |
| Adafruit ATECC608 breakout, STEMMA QT | $6 | Adafruit 4314 |
| STEMMA QT / JST-SH 4-pin cable, any ends | $1 to $8 | Amazon `B08HQ1VSVL` (the kit we used, several ends), or single: Adafruit 4209 ($0.95, snip the pins off and strip) |
| micro-USB cable, data not charge-only | | |

About $35. No soldering iron.

## 2. Print the case

`case/waveshare-13-pico-lcd-case-tomas-plass.stl`: both halves in one file, PLA, 0.2 mm layers,
no supports. Snaps together, micro-USB slot on the end, screen window, the four buttons and the
joystick poke through. Keycaps and a joystick dome are in `case/out/` (PLA, 0.12 mm layers).
`case/gen.py` regenerates them if your parts differ.

![both halves on the printer](buildlog/images/2026-09-05-24-case-on-the-printer.jpg)

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

`SOLDERING.md` has the pinout diagram and the soldered perfboard version, with an 18650 cell behind
a switch and a diode for running unplugged, and how to explore a fresh chip without changing it.

## 4. Flash the firmware

1. Hold BOOTSEL on the Pico, plug it into a computer, release. A drive named `RP2350` appears.
2. Drag [MicroPython for the Pico 2 W](https://micropython.org/download/RPI_PICO2_W/) (`.uf2`)
   onto it. The drive disappears and the board reboots.
3. On the computer: `uv tool install mpremote` (or `pip install mpremote`).
4. Copy `firmware/secrets.example.py` to `firmware/secrets.py`. Put in your WiFi and the app URL
   (step 6 gives you that, `http://<your-laptop-lan-ip>:3001`).
5. First time, over USB: `mpremote cp firmware/*.py :` then `mpremote reset`.

The passwordless WiFi console is disabled by default because it grants full control of the signer.
For isolated development only, set `ENABLE_NETWORK_CONSOLE = True`; then `./tools/push` deploys
firmware over the air and `./tools/pico` opens the console. Disable it before holding real value.

The screen comes up, finds the chip on the bus, and shows "no key" until step 5.

## 5. Set up the chip (once)

A fresh ATECC608 refuses to make a key until its config zone is locked, once, permanently. This
is normal; every chip in use is locked. Generate the final key before deploying the contract:

1. In `firmware/secrets.py` temporarily set `ALLOW_LOCK = True` and `ALLOW_GENKEY = True`, then
   `tools/usb push` (or `tools/push` over the WiFi console).
2. On the wallet: **X** for the CHIP MAP, CONFIG, `WRITE WALLET CONFIG` (reversible: the diff shows
   first and the chip's original bytes are saved as a snapshot). Hold **B and Y** together for 3 s
   to arm, then `LOCK CONFIG FOREVER` and hold A 3 s: the rules are sealed. Then DATA, slot 0,
   `NEW KEY`, hold A 3 s: the key is drawn from the chip's own random generator. `SHOW PUBLIC KEY`
   gives `qx` and `qy`; `SIGN TEST` proves the slot signs; A on the public key shows it as a QR code to scan. The app's
   Setup page can drive the lock
   and key steps over WiFi instead; it needs the same flags and the same arming on the device.
   The driver refuses the lock unless the chip really holds the wallet table with a P-256 slot 0.
3. Set both flags back to `False`, leave `ENABLE_NETWORK_CONSOLE = False`, and push again.
4. Put `qx` and `qy` in `app/packages/foundry/.env`, set a fixed `RECOVERY_ADDRESS`, and deploy.
   Losing the chip starts the documented 14-day recovery process.

`reference/pi/README.md` shows the equivalent provisioning flow from a Raspberry Pi with real output.

### Keys and slots, on the wallet itself

Press **X** on the home screen for the **CHIP MAP**: the chip drawn as a floor plan you can walk
through. CONFIG (128 bytes of rules) across the top, DATA (16 slots of 36, 416 or 72 bytes, a 4×4
field of tiles coloured by what each slot is), OTP (64 write-once bytes), COUNTERS (two numbers
that only go up) and the LAB docked below, where each question is one real command
("WHO ARE YOU?", "ARE YOU HEALTHY?", "MAKE RANDOMNESS") with the answer in words, the bytes, a
"why that's weird" layer and the raw command underneath. The header always says where you are
(`CHIP > DATA > SLOT 3`) and whether the wallet is `SAFE` or `ARMED`. **B** opens **LEARN**, five
short chapters that lead into those screens. A refusal from the chip is shown as a lesson: the
reason first ("the CONFIG zone is still open, so the DATA zone is hidden"), the status byte second.

Every action is one of three classes, said by colour, a glyph and words: `o SAFE TO EXPLORE`
(changes nothing), `~ REVERSIBLE` (can be restored: writing the config table while the zone is
still open, after the chip's original bytes are saved as a snapshot, with a diff of what changes
shown first), `! PERMANENT` (cannot be undone). A permanent action needs three things: the
`ALLOW_LOCK` / `ALLOW_GENKEY` flag in `secrets.py` on the board, the wallet **armed** (hold B and Y
together for 3 s; good for 60 s, shown in the header), and A held for 3 s on the red screen. The
permanent steps end in a small ceremony: the CONFIG strip on the die pulses and the padlock closes
for RULES SEALED; noise from the chip's own randomness settles into the key for KEY CREATED. A key
slot has a SIGN TEST (sign, then verify on the Pico, and watch counter 0 climb); the clear data
slots take a NOTE you can overwrite until the data zone is locked. `CHIPMAP.md` has the tour.

How the slots work. The ATECC608 has 16 data slots. What each slot *is* (a P-256 private key, a
public key, an AES key, plain data) and what it *may do* (sign digests handed in from outside, be
regenerated with GenKey, be locked on its own) is a table in the 128-byte config zone. That zone is
written once and locked forever, and the chip refuses GenKey and Sign until it is. With the
reference table the firmware writes (`atecc.CONFIG`, Microchip's own):

| slot | is | GenKey | external sign | lockable | note |
|---|---|---|---|---|---|
| 0 | P-256 private key | yes | yes | yes | the wallet key; every use counts on counter 0 |
| 2 | P-256 private key | yes | yes | no | a second independent account |
| 7 | P-256 private key | yes | yes | yes | also accepts an encrypted PrivWrite import |
| 11, 14, 15 | P-256 public key | | | yes | |
| 5, 10 | AES key | | | yes | |
| rest | plain data | | | some | |

So one chip is up to three independent signing keys with no seed phrase. The wallet remembers the
active slot in `slot.txt`; switching slots re-announces the new key, and the app shows *paired*
only for the key the vault was deployed with. The three locks, all permanent:

- **config zone**: freezes the table above. Required. Every chip in use is config-locked.
- **data zone**: no more clear-text writes to any slot. GenKey still works where the table allows.
- **one slot**: the key in it can never be replaced. `KeyConfig.Lockable` decides which slots can.

Try it without hardware: the emulator (`tools/emu`, below) has a virtual ATECC608 on its I2C bus
that starts as a fresh part with the factory table a real Adafruit breakout ships with.
`tools/emu run main`, press X for the map, CONFIG, WRITE WALLET CONFIG (a reversible change),
then arm the wallet (hold B and Y) and LOCK CONFIG FOREVER, then DATA, slot 0, NEW KEY.
`tools/emu chip ready` skips to a provisioned chip, `tools/emu chip fresh` goes back to a fresh one.

## 6. Run the app

`app/` is a Scaffold-ETH 2 project: the vault contract, a Next.js site, and the queue and relay as
route handlers. Locally, with play money:

```sh
cd app && yarn install
yarn chain                                  # anvil, a local chain
yarn deploy                                 # requires CHIP_PUBKEY_X/Y in packages/foundry/.env
yarn workspace @se-2/nextjs dev -p 3001     # http://localhost:3001
```

The wallet announces its key to the app. `/setup` verifies that it matches the current on-chain
key. The screen shows the vault balance and a QR of the vault address. Type a recipient and an
amount on the Send page. The wallet turns green. Press A. Watch it settle.

Mainnet, with real money, in `app/packages/nextjs/.env.local`:

```
NEXT_PUBLIC_TARGET_NETWORK=mainnet
NEXT_PUBLIC_ALCHEMY_API_KEY=<a restricted project-specific key>
RELAYER_KEYSTORE=<a foundry keystore name>          # an account with a little ETH for gas
RELAYER_KEYSTORE_PASSWORD_FILE=/path/to/password.txt
USDS_ADDRESS=0xdC035D45d973E3EC169d2276DDab16f1e407384F
```

Deploy your own vault with the chip's public key baked in (the Setup page shows it):

```sh
# app/packages/foundry/.env: CHIP_PUBKEY_X/Y=0x… USDS_ADDRESS=0x… ENS_REVERSE_REGISTRAR=0x…
cd app && yarn deploy --network mainnet --keystore <name>
```

Send USDS to the vault address it prints. Scan the QR on the wallet to get that address into
your phone wallet. Each transfer costs the relay about 82k gas.

For ENS, first create a subname such as `hard.atg.eth` and make its ETH record point to the vault.
Then use **Set the vault ENS name** in the app and approve the exact name on the device. This sets
reverse/primary resolution only; it does not create the subname.

Recovery uses the fixed `RECOVERY_ADDRESS` chosen at deployment. That wallet proposes a new P-256
key, waits 14 days, then finalizes. Any successful current-chip action cancels the proposal; the app
also has **Cancel on Pico**. Monitor `RecoveryStarted` events. See `SECURITY.md` before funding.

## The screens

![SIGN? $69 USDS to atg.eth, green bar at A, red bar at Y](buildlog/images/2026-09-05-20-sign-screen-69-usds.jpg)

**Boot:** a navy gradient, a chip die whose legs chase the rainbow while a step waits, an underline
that fills as the steps complete, and a checklist with an icon per step: screen, wifi (joining,
then the IP), chip (part, address, and whether it is new, empty or holds a key), app.

**Chip map and LEARN:** X and B from the home screen, described under "Keys and slots" above. The
chip's own refusals, the fixed Random pattern before the lock, and the reversible config write are
all part of the tour; nothing permanent happens without the three gates.

**Home:** balance in dollars, a QR of the vault to deposit into, chain label top-left so test money
and real money never look alike, pairing dot top-right, a warning line along the bottom (relay
gas low, unpaired, app unreachable). Refreshes every 12 s and flashes the delta when money moves.
Until there is a balance to show, the same screen is a status page instead: NEW CHIP (config zone
open, never set up), LOCKED, NO KEY, or KEY and the fingerprint; the part, I2C address and serial;
both lock states; the WiFi name and IP; the app host and its last answer; and what to do next.
So a board with a chip fresh from the bag says so at a glance.

**Sign:** green SIGN bar in line with the A button, red REJECT bar in line with Y. Amount,
recipient name and address between them. Joystick down shows nonce, deadline, chain, vault and the
digest the device computed.

![details page: full address, amount in base units, nonce, deadline, vault, digest](buildlog/images/2026-09-05-23-details-screen.jpg)

## Change it

- **Another token:** set `USDS_ADDRESS` before deploying. The token address is immutable, so changing
  assets requires a new vault.
- **Another chain:** `targetNetworks` in `app/packages/nextjs/scaffold.config.ts`. The wallet
  shows the chain id it is told and bakes it into the digest.
- **The screens:** `firmware/wallet.py`, functions `draw_home` and `draw_confirm`. 240×240,
  framebuf, an 8×8 font scaled up. Try it on the virtual wallet first: `tools/emu` opens
  http://localhost:4242 with the same MicroPython running the same files, the case in 3D and
  the keyboard on the buttons (W A S D, space, numpad 9 6 3 .); `tools/emu run NAME`, `key A`, `shot` drive it from a terminal
  (`emu/README.md`). To have an AI write for it, give it `emu/SKILL.md` and this repo; in Claude
  Code it is the `/pico-emu` skill. Then `./tools/push` and look.
- **The case:** `case/gen.py`, CadQuery, every dimension is a named number at the top.
- **The contract:** `app/packages/foundry/contracts/ChipAccount.sol`, with 34 tests.

## What is where

| path | what |
|---|---|
| `firmware/` | MicroPython for the Pico: `wallet.py` loop and screens, `atecc.py` chip driver, `signer.py`, `eip712.py` + `keccak.py` + `p256.py` pure-Python crypto, `lcd.py`, `net.py` |
| `app/` | contracts, tests, site, relay |
| `case/` | STLs, the generator, the measurements |
| `emu/` | the virtual wallet: MicroPython in WebAssembly, `machine` shims, the case STLs in 3D, a CLI for bots |
| `tools/` | `pico` console, `push` firmware, `qr` (QR of the vault for the screen), `emu` (the virtual wallet) |
| `buildlog/` | dated notes and photos of what actually happened, including the mistakes |
| `reference/` | the Pi signer this grew out of, with the fresh-chip guide; SeedSigner cap parts (MIT) |
| `PLAN.md`, `SOLDERING.md` | the plan, and the wiring guide |
| `CHIPMAP.md` | the chip explorer: the map, LEARN, the three classes and gates, the reversible config write, and how the code is laid out |
| `TESTPLAN.md`, `UPSTREAM.md`, `UPSTREAM-ISSUE.md` | bring-up and test plan for a fresh chip and the battery; notes to send upstream (the config-table bug, flashing, what a fresh chip answers); the issue text, ready to paste |

## Trust model, short

The current chip key is the only thing that can spend the vault. The delayed recovery wallet can
replace that key but cannot spend directly. The relay only pays gas. The app
has no auth, so anyone who can reach it can queue deceptive requests or cause denial of service;
keep it on a trusted network for this PoC. The passwordless development console must stay disabled
when holding value. Read [`SECURITY.md`](SECURITY.md) before funding a deployment or publishing the
app to the internet.

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
