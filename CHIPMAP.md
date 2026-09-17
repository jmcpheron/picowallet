# CHIP MAP: exploring the ATECC608 on the wallet itself

The secure element usually disappears under a product. On this wallet it is the other way round:
press a button and the chip is a place you can walk through, with rules, memory, secrets, a random
generator and a few one-way doors. This is how that part of the firmware works: the screens, the
keys, the three safety classes, the gates in front of anything permanent, and the code behind it.

Everything below runs on the Pico 2 W with the Waveshare Pico-LCD-1.3 (240×240, joystick, A/B/X/Y)
and on the emulator (`tools/emu`), which has a virtual ATECC608 that answers like a fresh Adafruit
breakout.

## Two doors: X and B

From the home screen:

- **X** opens the **CHIP MAP**. Everything on the map is a thing that exists on the chip.
- **B** opens **LEARN**, a tutorial of five short chapters. Each chapter is one card of text; A on
  the card takes you to the real screen it talks about. Inside the chip UI, B is "what is this?":
  the card for the screen you are on.

Y always goes up one level, and from the top of the map or the tutorial it goes home.

![the chip map](buildlog/images/chipmap-01-map.png)
![the tutorial](buildlog/images/chipmap-11-learn.png)

## The header: where you are, and whether the wallet is armed

Every chip screen has the same 22-pixel header bar. On the left is the breadcrumb: `CHIP`,
`CHIP > CONFIG`, `CHIP > DATA > SLOT 3`, `LEARN > 2 ASK THE CHIP`. It is built from the trail of
screens you came through; when it gets long it loses its head, never its tail (`.. DATA > SLOT 0`).

On the right is the wallet's state: `SAFE o` in green, or `! ARMED 57s` in red counting down.
ARM is not on the map on purpose. It is the wallet's own safety catch, not a feature of the chip.

## The map

```
CHIP  (ATECC608A, i2c 0x60, serial ...)
├── CONFIG     128 B   OPEN | LOCKED     the rules for every slot
│   ├── o RAW BYTES                       the 128 bytes, 8 a row, slot table in white
│   ├── o COMPARE WITH SAVED              chip vs the saved snapshot
│   ├── ~ WRITE WALLET CONFIG             reversible while the zone is open
│   ├── ~ RESTORE SAVED CONFIG            reversible: the snapshot goes back
│   ├── ! LOCK CONFIG FOREVER             permanent (only once the chip holds the wallet table)
│   ├── ! LOCK DATA ZONE                  permanent (only after the config lock)
│   └── o RE-READ
├── DATA       16 slots                   keys and bytes, 36 B (0-7), 416 B (8), 72 B (9-15)
│   └── SLOT n                            kind, size, what it may do, then its actions
│       ├── o USE THIS KEY                make it the signing slot
│       ├── ! NEW KEY                     permanent: GenKey replaces what is there
│       ├── o SHOW PUBLIC KEY             qx and qy
│       └── ! LOCK SLOT FOREVER           permanent
├── OTP        64 B                       write-once bits; hidden until the config lock
├── COUNTERS   2                          only ever go up
└── LAB                                   questions, one real command each
    ├── WHO ARE YOU?                      Info revision + serial
    ├── ARE YOU HEALTHY?                  SelfTest
    ├── MAKE RANDOMNESS                   Random
    ├── HASH SOMETHING                    SHA-256 of "picowallet", compared with the Pico's
    ├── IS YOUR SLOT A KEY?               Info KeyValid on the active slot
    ├── WHAT'S COUNTER 0?                 Counter read
    ├── WHAT'S IN YOUR OTP?               Read OTP block 0
    ├── TRY READING SLOT 8                Read data slot 8
    └── READ YOUR OWN ADDRESS             Read config word 4 (the I2C address byte)

LEARN
├── 1 WHAT'S INSIDE?        -> the map
├── 2 ASK THE CHIP          -> the LAB
├── 3 CHANGE THE RULES      -> the CONFIG page
├── 4 MAKE A KEY            -> the DATA list (waits for sealed rules)
├── 5 SEAL THE VAULT        -> the CONFIG page (the three one-way doors; not today)
└── ? COLOURS AND GATES
```

Keys on every menu: joystick up/down moves, A (or the joystick press) opens or does, Y goes up.
On a slot, left/right steps to the neighbouring slots. Result screens dismiss with A.

![the data list](buildlog/images/chipmap-02-data-list.png)
![slot 0](buildlog/images/chipmap-03-slot-0.png)

## Three classes, said three ways

Every action is one of three kinds, and each is shown by its colour, a glyph, and words, so it is
never colour alone:

| glyph | colour | words in the footer when the item is selected | examples |
|---|---|---|---|
| `o` | green | `SAFE TO EXPLORE: no changes` | reads, the LAB, RAW BYTES, SHOW PUBLIC KEY |
| `~` | yellow | `REVERSIBLE: can be restored` | WRITE WALLET CONFIG, RESTORE SAVED CONFIG |
| `!` | red | `PERMANENT: cannot be undone` | the three locks, NEW KEY |

An item that cannot run right now is dimmed and the footer says why: `off: config zone still
open`, `off: ALLOW_LOCK is False on the board`, `off: not armed: hold B+Y 3 s`, `off: write the
wallet config first`.

### The gates in front of red

A permanent action goes through three gates, in this order:

1. **The flag on the board.** `ALLOW_LOCK` or `ALLOW_GENKEY` must be `True` in `secrets.py` on the
   Pico. Shipped default: both `False`. This needs a laptop and a push.
2. **ARM.** Hold **B and Y together for 3 seconds** on any chip screen. A bar fills along the
   bottom; when it completes the header turns `! ARMED 60s` and counts down. Holding B+Y again
   disarms. This lives in `signer.py`, so the app's remote `genkey` and `lock-config` commands
   over WiFi need it too: nothing permanent happens without someone at the device.
3. **The red screen.** `PERMANENT: cannot be undone`, an open padlock, exactly what is about to be
   sealed, and A held for **3 seconds** with a bar and a 3-2-1 countdown. Y cancels. A lock ends
   on a green padlock and `SEALED`.

![armed](buildlog/images/chipmap-12-armed.png)
![the red screen while holding A](buildlog/images/chipmap-13-permanent-hold.png)
![sealed](buildlog/images/chipmap-14-sealed.png)

The yellow screen is the lighter version: what will change, `I2C address unchanged`, `config zone
stays OPEN`, and A held for 1.5 s. Y shows the full diff; B cancels.

## Refusals are part of the lesson

A fresh chip says no to a lot: it hides the DATA and OTP zones, refuses GenKey and Sign, and
answers Random with a fixed test pattern until its config zone is locked. The UI treats each refusal
as an answer. The screen says `CHIP SAYS: NOT ALLOWED`, then **Why?** in plain words for this chip
state ("The CONFIG zone is still open. Until its rules are locked, the chip will not expose the
OTP zone."), then the raw truth: `STATUS 0x0F`, `execution error: not allowed in this state`.
A on that screen shows the exact command: opcode, parameters, data, the answer bytes, round trip.

![a refusal](buildlog/images/chipmap-10-refused.png)

In the LAB the same idea has one more layer. An answer screen gives the meaning in words and the
bytes; when the answer is odd (`MAKE RANDOMNESS` on an unlocked chip returns `ffff0000` eight
times) it offers `WHY THAT'S WEIRD >`; `RAW COMMAND >` is always there.

![the lab](buildlog/images/chipmap-07-lab.png)
![the fixed random pattern](buildlog/images/chipmap-08-lab-random.png)
![why it is weird](buildlog/images/chipmap-09-lab-why.png)

What the real fresh ATECC608A answered on 2026-09-16 is in `UPSTREAM.md` section 3b. In short:
it identifies itself, passes its self tests, hashes (matching the Pico's SHA-256) and reads its
counters while unlocked; it refuses OTP and data reads with `0x0F`; Info GPIO refuses with `0x03`.

## The reversible write, and why it is reversible

A fresh chip has exactly one region you may write: the config zone, and only until it is locked.
Writing it again overwrites it again. So the wallet offers the write as a **reversible change**:

1. Before the first write, the chip's current 128 bytes are saved once to `snapshot-<serial>.bin`
   on the Pico's flash (`ChipSigner.save_snapshot`). It is never overwritten. It is *this chip's*
   original bytes, not a Microchip default.
2. The yellow screen shows the diff first (`atecc.diff_config`): how many bytes change, which slots
   change kind (`slot 1: P256 -> DATA`), and that the I2C address byte stays put.
3. `atecc.write_config` refuses to change byte 16 (the I2C address: the chip would answer somewhere
   else after its next wake) and refuses if the zone is locked. It writes the 27 writable 4-byte
   words (words 0-3 and 21 are read-only), then reads the whole zone back and compares bytes
   16-83 and 88-127 with what it wrote.
4. The result screen shows three checks: `WRITE COMPLETE`, `READBACK MATCHES`, `CONFIG STILL OPEN`,
   and "N bytes changed. Nothing has been permanently locked."
5. `RESTORE SAVED CONFIG` is the same flow with the snapshot as the target. `COMPARE WITH SAVED`
   shows the diff without writing.

![the diff before the write](buildlog/images/chipmap-05-write-diff.png)
![after the write](buildlog/images/chipmap-06-write-done.png)

The CONFIG page names what is on the chip: `CURRENT original bytes`, `wallet config`, or
`modified` (a partial write, which RESTORE fixes), and whether a snapshot exists.

![the config page](buildlog/images/chipmap-04-config-page.png)

`LOCK CONFIG FOREVER` is offered only when the chip already holds the wallet table, so the old
one-step "write + lock" is now two steps with a checkpoint you can undo in between.

## How the code is put together

Four firmware modules and one driver:

- **`firmware/slots.py`** is the state machine, `SlotsUI`. `wallet.py` creates it with the LCD, the
  signer and a callback, calls `open("zones")` or `open("learn")`, and on every 50 ms tick passes
  the keys that went down; `tick()` returns `"home"` when the trail is exhausted. It also draws the
  DATA screens (list, slot, public key), the red confirm, WORKING and the result screen.
- **`firmware/chipmap.py`** draws the map, the CONFIG page and its write flow, OTP and COUNTERS,
  the refusal screen and the raw-command view, and holds the shared chrome: the header with the
  breadcrumb and ARM state, menus with class glyphs, footers, word wrap, scrolling, drawn icons
  (check, cross, warning, open and closed padlock, since the 8×8 font has no such glyphs), and the
  B+Y arming gesture.
- **`firmware/learn.py`** holds the LEARN cards, the context lookup (which card B opens on which
  screen), and the LAB: each question is a small function that runs one driver call and returns
  (words, bytes, why-or-None).
- **`firmware/signer.py`** gained `arm() / disarm() / armed()` and `gate(what)`, the snapshot
  functions, `write_config()` and `restore_snapshot()`, and `lock_config()` that now only locks
  (`provision()` keeps write-then-lock for the app's command). `_allowed(flag)` is the single
  choke point: the flag AND armed.
- **`firmware/atecc.py`** gained names for the chip's status codes, a `trace` of the last command
  (for the RAW views), `info(mode)`, `selftest()`, `sha256()`, `counter()`, `read_otp()`,
  `read_data()`, `read_config_word()`, slot sizes and write/read policy in `decode_slot()`,
  `diff_config()`, and the address guard plus readback in `write_config()`.

Navigation is a trail. `ui.go(view)` pushes the current screen onto `ui.stack` and `ui.back()`
pops it; the breadcrumb is rendered from that stack. Short-lived screens (WORKING, results,
refusals, the confirms, a LAB answer) do not go on the trail; they remember `ui.ret`, the screen to
return to, so A or Y lands where you were.

Two details worth knowing if you change it:

- **B and Y are delivered on release** inside the chip UI (`chipmap.arm_tick`). Otherwise pressing
  B then Y to arm would first open a card or go back. A B or Y that was part of a B+Y hold is
  swallowed until both are up.
- **Draw only when dirty.** A full redraw is about 45 ms of a 50 ms tick; redrawing every tick
  starves the REPL so badly mpremote cannot connect (this happened once). Screens set `ui.dirty`
  on input, the header's countdown once a second, the arm bar while holding.

The screen is 240 px wide with an 8×8 font: 29 characters per line at the 4-pixel margin, 12 px
per text row, about 17 rows between the header and the footer. Menus use 14 px rows. Anything
longer is wrapped by `chipmap.wrap` or scrolled by `draw_scroll`.

## The virtual chip

`emu/core/shims/atecc_sim.py` answers on the emulator's I2C bus at 0x60 with the real packet
protocol. A fresh virtual part now carries the factory table read off a real Adafruit breakout
(slots 0-2 typed P-256, GenKey allowed), returns the fixed `ffff0000` pattern for Random until the
lock, answers Info KeyValid and State, SelfTest (all pass), SHA-256, counter reads, and refuses
OTP and data reads with `0x0F` until the config lock, zeros after. Writes to OTP and data slots are
not modelled yet.

Recipes that exercise it headless (`tools/emu headless main ...`, screenshots land where `--shot`
says):

```sh
# the map, the list, slot 0
tools/emu headless main --wait 2800 --key X --wait 400 --shot map.png --key down --key A --wait 400 --shot list.png
# arm, then look at the config page armed
tools/emu headless main --wait 2800 --key X --hold B --hold Y --wait 3400 --release B --release Y --key A --wait 400 --shot cfg.png
# write the wallet config (hold A on the yellow screen), then restore the snapshot
tools/emu headless main --wait 2800 --key X --key A --key down --key A --hold A --wait 1900 --release A --wait 1200 --shot written.png
# the red ceremony on a provisioned chip: `tools/emu chip ready` in the page, or --chip state.json headless
```

On the real board, `TESTPLAN.md` phase 4b walks the same things in order, ending with the
write-and-restore round trip checked by `tools/usb run firmware/chipcheck.py`.

## What is not here yet

- Writes to data slots and OTP (they need the config lock first), PrivWrite, counter increments.
- The full lock ceremony: the red screen has the padlock, the countdown and `SEALED`, but the
  animated transition (rules OPEN, then the lock closing) is a later step.
- Balances per key, which needs a lookup route in the app.
