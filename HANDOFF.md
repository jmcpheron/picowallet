# HANDOFF

For the next agent, or me after a context reset. State as of 2026-09-06. Plain facts, then how to
run each piece, then gotchas, then what is open. Public repo, so no secrets here; they are named
by file and location only.

## What exists and works

- A hardware wallet: Pico 2 W + Waveshare Pico-LCD-1.3 + Adafruit ATECC608 breakout, no solder.
  The ATECC is the Adafruit STEMMA QT board from the ATECC608-demo Pi, serial
  `01235e6763cc8d97ee`. Its key owns the mainnet vault. Four STEMMA cable wires are wedged into
  the LCD board's header beside the Pico pins (3V3 pin 36, GND 38, GP4 SDA pin 6, GP5 SCL pin 7).
- Mainnet vault `ChipAccount` v5 at `0x4564fA634b073AcBcA814DCA5210835EC9376324` (legacy v1 at
  `0x0336aD6afc8bE414D6BD1f7A16caEb14BCCd16e9`, do not fund), token USDS
  `0xdC035D45d973E3EC169d2276DDab16f1e407384F`. Relay/admin `0x7FE7f508A267BF45D2D161F244DbB12743e2cf49`,
  a foundry keystore named `atecc-relay` in `~/.foundry/keystores` with its password in a file
  beside it. Vault ~$41.66, nonce 10, relay ~0.001 ETH (about 80 sends) on 2026-09-06.
- Transfers done from the wallet on mainnet: 5 USDS `0x0fbd390b…`, 69 USDS `0x87638ae1…`, more.
  Each is ~82k gas.
- The repo is public at https://github.com/austintgriffith/picowallet, MIT, branch `main`.
  Push as austintgriffith (`gh auth switch --user austintgriffith`, then back to clawdbotatg).

## The pieces and how to run them

### Wallet firmware (`firmware/`, MicroPython 1.26.1 on the Pico)
- `boot.py` joins WiFi and opens the console (`net.py`, TCP 2323, `os.dupterm`). `main.py` starts
  `wallet.py` on a 50 ms `machine.Timer` and returns to the REPL. Nothing may block the REPL.
- `wallet.py`: announce to the app every 30 s, fetch `/api/state` every 12 s, poll
  `/api/requests?status=pending`, rebuild the EIP-712 digest on device (`eip712.py`, `keccak.py`),
  refuse on mismatch, show SIGN (A) / REJECT (Y), details on joystick down, sign on the chip
  (`signer.py` → `atecc.py`, 150 ms), post the signature, or post `/reject`.
- `secrets.py` (gitignored, on the Pico and in `firmware/`): WIFI_SSID, WIFI_PASS, HOSTNAME,
  APP_URL (`http://192.168.68.63:3001`, the Mac's LAN IP), DEVICE_NAME, ALLOW_LOCK, ALLOW_GENKEY.
- Reach it from the Mac: `./tools/pico <mpremote args>` (WiFi console with retries), `./tools/push`
  (copy all firmware, reboot via a one-shot Timer), `./tools/qr` (build `qr.bin` of the vault
  address for the home screen; rerun when the vault changes). mpremote is at `~/.local/bin`.
- USB rescue: plug the Pico's USB into the omen laptop (`ssh omen`), device
  `/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_*-if00`, mpremote there with `resume`. Use
  only if the WiFi console is dead. `/tmp/usb.py` on omen is a raw serial helper.
  The Pico is not a USB drive: plugging it into any computer gives a serial port only
  (`/dev/tty.usbmodem*` on the Mac), no drag and drop, no SSH. Every mpremote command in
  `tools/pico` works the same over USB if you swap the `socket://` target for that port.
  BOOTSEL-while-plugging gives the RPI-RP2 drive, which is only for flashing `.uf2` firmware.
- Chip provisioning (lock config zone, generate key) is implemented in `atecc.py` and gated by
  ALLOW_LOCK / ALLOW_GENKEY. It has never run on a fresh chip. The config bytes are the ones the Pi
  signer used successfully. Do not enable those flags on the wallet holding the mainnet key.

### App (`app/`, Scaffold-ETH 2, Foundry + Next.js)
- Run: `cd app && yarn workspace @se-2/nextjs dev -p 3001`. Mainnet mode comes from
  `app/packages/nextjs/.env.local` (gitignored): NEXT_PUBLIC_TARGET_NETWORK, RELAYER_KEYSTORE,
  RELAYER_KEYSTORE_PASSWORD_FILE, USDS_ADDRESS, NEXT_PUBLIC_ALCHEMY_API_KEY.
- Routes: `api/device` (announce), `api/state` (one poll, 5 s chain-read cache), `api/requests`
  (queue, digest), `api/requests/[id]/signature` (verify + relay), `api/requests/[id]/reject`
  (added 2026-09-05), `api/commands` (setup jobs), `api/pair`, `api/fund` (local only).
- Store is a JSON file in `app/packages/nextjs/.chip/` (gitignored).
- Local play chain: `yarn chain`, `yarn deploy` (ChipAccount + MockUSDS, 1000 USDS), unset
  NEXT_PUBLIC_TARGET_NETWORK. An orphan `anvil --silent` from 2026-09-04 may still own :8545.
- Port 3000 on the Mac was yesterday's ATECC608-demo app in mainnet mode. If it is running, do
  not point the wallet or a browser at it by mistake.

### Case (`case/`)
- v0: `waveshare-13-pico-lcd-case-tomas-plass.stl` (CC BY-NC), both halves in one STL, printed
  and fits. Print inbox drop `20260905-193939-…`.
- `gen.py` (CadQuery, `uv run --python 3.11 --with cadquery python case/gen.py`): measurements at
  the top, `keycap()` press-fit caps (wrong idea, printed, rejected), `cap()` flanged caps for a
  future taller lid, and after `v05` arg: `straddle_cap()` + `grip_dome()`.
- `tools/lid` cuts the v0 lid mesh (trimesh + manifold): button slot 4.5 → 7.7 mm, joystick hole
  round 8.6 mm. Output `case/out/v0_lid_wide_slot.stl`.
- Untested lid + 4 straddle caps + dome: print drop `20260905-214230-v05_lid_caps_dome_plate`.
  That work is on local branch `case-v05`, NOT on main, by Austin's instruction until tested.
- Measured on the v0 lid STL: case 57×31×26 outer, lid plate 2.0 mm, screen window 30×27 at
  x +2.0 from board center, button column x +22.25 with 5.17 mm pitch, joystick x −19.5. Switch
  body 4.5 mm, plunger 2.04 mm dia, plungers sit flush with the lid face. Joystick stem ~4.2 mm
  above the lid face; its metal housing pokes through the lid.
- Printer: Bambu P2S via the print inbox at `http://GriffithRobots-Mac-mini.local:8800`
  (skill `send-to-printer`). A drop is a request; Austin tells the print Claude to go.

## Gotchas that cost hours

1. rp2 reads the socket console only while the REPL is idle. Any `while True` in main.py makes
   the board unreachable over WiFi, and Ctrl-C over the socket never lands.
2. The rp2 scheduler queue is 8 deep. A periodic Timer plus a blocking call over ~0.4 s fills it,
   the console's accept callback is dropped, and every later connect gets TCP RST until reboot.
   Fix in place: one timer, paused around HTTP; `net.poll_accept()` from the tick; app caches
   chain reads. On mainnet `/api/state` was 0.5–3 s before the cache.
3. mpremote soft-resets before the first command unless `resume`. `tools/pico` always passes it.
4. macOS has no `timeout`. Reboot the Pico with a one-shot `machine.Timer` so mpremote returns
   before the socket drops.
5. The wallet posting a signature while the relay has no ETH: chip signs, relay fails
   "insufficient funds". Fund the relay first. ~0.000012 ETH per send at Sept 2026 gas.
6. Two copies of the site (3000 and 3001) look identical. A request on the wrong one never
   reaches the wallet.
7. Rejecting on the wallet without telling the app kept the request pending and reserved its
   amount; the next proposal failed the balance check. Now `/reject` exists.
8. gitleaks pre-commit fires on 12 lowercase English words in a row (bip39 rule). Reword.
9. Photos: Austin does not want feet, legs or home clutter in the repo. History was purged once
   with git filter-repo before the first push. Check every photo (PIL contact sheet) before adding.
10. The Waveshare wiki and Printables block plain fetches; use the browser tool.

## Contract v5 (2026-09-06)

A second session hardened the contract and app: `ChipAccount` authorization v5, no admin, fixed
recovery address with a 14-day delay, arbitrary signed calls, ENS reverse name. Deployed to
mainnet at `0x4564fA634b073AcBcA814DCA5210835EC9376324` and audited (One Dollar Audit 850, see
README). The old vault `0x0336aD6a…` is legacy v1 with a mutable signer: the app refuses to relay
for it. Do not fund it. `api/pair` is gone; the chip key is fixed at deployment. `SECURITY.md`
has the threat model. All of that is committed on `main` now.

## Case: stopped (2026-09-06)

Printed caps and a joystick hat three times; none fit. The button pitch used since 2026-09-05 was
a guess (5.17), the real one is about 5.58, and the joystick's push-down stopped working during the
tests. Austin stopped it: the wallet lives in the original white v0 case with bare buttons. The
calipers and photo measurements are in `case/BUTTONS.md`. `gen.py v06` and `tools/lid` build the
last, unprinted version. Do not restart this unless Austin asks.

## Sensitive things to know

- An Alchemy API key was in `.env.example` and `scaffold.config.ts` from the first push until this
  commit. It is in the public git history. Rotate it in the Alchemy dashboard.
- `firmware/secrets.py`, `app/packages/nextjs/.env.local`, `.chip/`, and the relay keystore are
  gitignored. Keep it that way.

## Open threads, in order

1. Joystick push-down on the board no longer registers; check the switch and `lcd.py` Keys.
2. Run the fresh-chip provisioning path on a real blank ATECC608 and fix what breaks.
3. Host the app somewhere with a persistent store so "go to a website" works off the LAN.
4. Battery (PLAN.md step 4).
5. Case v1 (own design, battery pocket) only if Austin brings it up.

## Where the notes are

`README.md` (build guide), `buildlog/BUILDLOG.md` (dated, with mistakes), `PLAN.md`,
`SOLDERING.md`, `case/README.md` + `case/BUTTONS.md` (measurements, cap research, decisions),
`reference/pi/README.md` (fresh-chip walkthrough on a Pi), `reference/ATECC608-demo-HANDOFF.md`.
