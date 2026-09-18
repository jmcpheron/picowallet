# Notes for upstream (austintgriffith/picowallet)

Working notes from the `claude/pico-wallet-signing-keys-uyr7mc` branch of the jmcpheron fork, to
turn into an issue and a PR against the upstream repo. Sections marked *(fill in)* get their data
from the hardware session in `TESTPLAN.md`.

## 1. The bug: `firmware/atecc.py` CONFIG has a shifted KeyConfig table

**Where:** `firmware/atecc.py`, the `CONFIG` constant. Introduced in upstream commit `5cdebf1`
("chip provisioning from the Setup page (lock config, new key), gated by flags on the device;
README step 5").

**What it says it is:** Microchip's ATECC608 reference config, "the same bytes the Pi signer used
successfully" (`reference/pi/signer.py`, `AteccSigner.CONFIG`, which really did provision chip
#1, the one that owns the mainnet vault).

**What it actually is:** the ATECC508 test table from cryptoauthlib (`test_ecc_configdata`), with
an extra row of sixteen `0xFF` inserted at bytes 96 to 111 and the last row dropped. Bytes 96 to
127 are KeyConfig, two bytes per slot, so the shift puts `0xFFFF` in slots 0 to 7. In KeyConfig,
bits 2 to 4 are KeyType and `111` means "not an ECC key".

Decoded, the upstream table gives:

```
slot  KeyConfig  kind        SlotConfig genkey
   0   0xffff   not ECC     0x208f   yes
   1   0xffff   not ECC     0x44c4   no
   2   0xffff   not ECC     0x2087   yes
   ...
   7   0xffff   not ECC     0x2082   yes
   8   0x0033   P256 priv   0x0f0f   no     <- the Pi table's slot 0 entry, shifted down 8 slots
  10   0x0013   P256 priv   0x0f0f   no
  15   0x0030   P256 pub    0x0f0f   no
```

The Pi's table (cryptoauthlib `test_ecc608_configdata`) gives slot 0 KeyConfig `0x0033`: P-256,
private, PubInfo, lockable, with SlotConfig `0x2FAF` (external sign, GenKey allowed).

**Effect:** `ChipSigner.lock_config()` writes CONFIG and locks the config zone. That lock is
permanent. Afterwards GenKey on slot 0 returns status `0x0F` forever, because the slot is not
typed as an ECC key, and no other slot is both P-256 and GenKey-enabled. The chip can never hold a
wallet key. The Setup page's "Lock config zone" button runs exactly this path, and README step 5
tells a new builder to use it.

**Why nobody hit it:** HANDOFF.md, "Chip provisioning ... has never run on a fresh chip." Chip #1
was provisioned by the Pi code with the correct table.

**Fix (on this branch):** replace CONFIG with the bytes from `reference/pi/signer.py`, byte for
byte, plus a comment explaining what each P-256 slot is and a warning never to hand-edit the table.
The fix is a one-hunk change to the constant; the rest of the branch is optional.

**Verification available without hardware:** `emu/core/shims/atecc_sim.py` on this branch is a
virtual ATECC608 that speaks the packet protocol; with the fixed table, lock config, GenKey in
slot 0, and Sign all succeed and the signature verifies; with the old table GenKey on slot 0 is
refused.

**Hardware verification (2026-09-17, Adafruit 4314, ATECC608A, serial `0123f3acfd2a826bee`).** The
fixed table was written to the fresh chip from the wallet's own screen (49 bytes changed from the
factory table, read back identical), then the config zone was locked the same way. After the lock:
byte 87 = `0x00`, the table matches the fixed `CONFIG` byte for byte, slots 0, 2 and 7 decode as
P-256 private with GenKey allowed. GenKey in slot 0 succeeded three times in a row, each replacing
the last (`a427c739`, then two more, the current one `cc01b14a`, one of them on battery power);
Info KeyValid on slot 0 reads 1, the public key reads back, Random is live. Then the control
experiment on the same sealed chip: GenKey on slot 3, whose SlotConfig allows GenKey but whose
KeyConfig is `0x001C` (KeyType 7, "not an ECC key"), is refused with status `0x0F`; slot 1 likewise;
slot 0's key was untouched. Upstream's table gives every one of slots 0 to 7 KeyType 7 (KeyConfig
`0xFFFF`), so a chip locked with it answers GenKey on slot 0 exactly like our slot 3: `0x0F`,
permanently. A fourth key was then made (`9fad2e82`) and signed two test digests from the wallet's
SIGN TEST, each verified on the Pico with the slot's public key; counter 0 went 0, 1, 2 (slot 0 has
LimitedUse), confirming Sign as well. The short issue text is in `UPSTREAM-ISSUE.md`.

**Suggested upstream text:** the issue draft is at the end of this file.

## 2. Reading the slot table (what this branch adds, for context)

Not needed for the fix, but useful to upstream as documentation:

| slot | is | GenKey | external sign | lockable |
|---|---|---|---|---|
| 0 | P-256 private | yes | yes | yes (LimitedUse: counts on counter 0) |
| 2 | P-256 private | yes | yes | no |
| 7 | P-256 private | yes | yes | yes (also encrypted PrivWrite) |
| 11, 14, 15 | P-256 public | | | yes |
| 5, 10 | AES | | | yes |
| others | data | | | some |

So with the reference table one chip holds up to three independent signing keys (0, 2, 7), not
"slots 0-7" as `reference/ATECC608-demo-HANDOFF.md` says. `atecc.decode_slot()` derives this from
the bytes; the wallet's KEYS screen shows it live.

## 3. Factory config of a fresh ATECC608 *(fill in)*

Paste the `chipcheck` output from TESTPLAN phase 3 here. Of interest upstream: the revision byte
(608A vs 608B), the I2C address byte, and the factory SlotConfig/KeyConfig rows, which decide
whether anything works before the config lock.

```
== picowallet chipcheck ==
i2c scan: ['0x60']
using address: 0x60
wake: ok (3 ms)
serial:   0123f3acfd2a826bee
revision: 00006002 (ATECC608A)
i2c address byte 16: 0xc0 (7-bit 0x60)
config zone: unlocked   data zone: unlocked   (byte 87 = 0x55, byte 86 = 0x55; 0x55 = unlocked, 0x00 = locked)
slot locked bytes 88-89: ff ff
raw config zone (128 bytes, 16 per row):
    0: 01 23 f3 ac 00 00 60 02 fd 2a 82 6b ee c1 55 00
   16: c0 00 00 00 83 20 87 20 8f 20 c4 8f 8f 8f 8f 8f
   32: 9f 8f af 8f 00 00 00 00 00 00 00 00 00 00 00 00
   48: 00 00 af 8f ff ff ff ff 00 00 00 00 ff ff ff ff
   64: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
   80: 00 00 00 00 00 00 55 55 ff ff 00 00 00 00 00 00
   96: 33 00 33 00 33 00 1c 00 1c 00 1c 00 1c 00 1c 00
  112: 3c 00 3c 00 3c 00 3c 00 3c 00 3c 00 3c 00 1c 00
matches the reference table (bytes 16-83, 88-127): no
slot table as the chip has it:
  slot kind  ext-sign genkey privwrite pubinfo lockable locked  key
     0 P256  True     True   False     True    True     False   -
     1 P256  True     True   False     True    True     False   -
     2 P256  True     True   False     True    True     False   -
     3 DATA  False    False  False     False   False    False   -
     4 DATA  False    False  False     False   False    False   -
     5 DATA  False    False  False     False   False    False   -
     6 DATA  False    False  False     False   False    False   -
     7 DATA  False    False  False     False   False    False   -
     8 DATA  False    False  False     False   True     False   -
     9 DATA  False    False  False     False   True     False   -
    10 DATA  False    False  False     False   True     False   -
    11 DATA  False    False  False     False   True     False   -
    12 DATA  False    False  False     False   True     False   -
    13 DATA  False    False  False     False   True     False   -
    14 DATA  False    False  False     False   True     False   -
    15 DATA  False    False  False     False   False    False   -
random (32 bytes): ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000
NOTE: config zone is unlocked. GenKey and Sign will refuse (status 0x0f) until it is locked; that is normal.
== end ==
```

Read off it (2026-09-16, Adafruit 4314 breakout, run twice, output byte-identical):

- ATECC608**A** (revision `00006002`), serial `0123f3acfd2a826bee`, I2C address byte `0xC0`
  (7-bit 0x60), both zones unlocked (bytes 86, 87 = `0x55`), SlotLocked `ffff`.
- The factory slot table is not blank. SlotConfig `2083 2087 208f` and KeyConfig `0033` for slots
  0, 1 and 2: Microchip ships them typed as P-256 private keys with external sign and GenKey
  allowed; 3 to 15 are data, 8 to 14 lockable. `matches the reference table: no`, as expected.
  The emulator's blank part has an all-zero table, so its KEYS list shows `-` where the real
  chip shows `P256`; `atecc_sim.FRESH` should carry these factory bytes.
- `random` is `ffff0000` repeated, identical on both runs. That is datasheet behaviour: before
  the config zone is locked, Random returns a fixed test pattern. The test plan expected it to
  differ; corrected in TESTPLAN.md and SOLDERING.md.
- GenKey is refused (`status 0x0f`) on the unlocked zone even though the factory KeyConfig
  allows it, so the wallet says `no key` until the lock, as designed.
- Wake 3 ms.

## 3b. What a fresh 608A answers before the config lock

Asked from the driver on 2026-09-16 (the LAB's questions, `atecc.py` on the same chip as section
3, config zone still open), round trip in ms:

| command | answer |
|---|---|
| Info revision | `00006002` (9 ms) |
| Info KeyValid slot 0 | `00000000`: no usable key (10 ms) |
| Info State | `00000000` (9 ms) |
| Info GPIO (mode 3) | refused, status `0x03` parse error: no GPIO on this part (9 ms) |
| SelfTest mask 0x3F | `0x00`, every test passed (256 ms). **Works before the lock.** |
| SelfTest RNG only | `0x00` (256 ms) |
| SHA-256 of `picowallet` | `89dd4b2d…9c46`, identical to the Pico's hashlib (37 ms). **Works before the lock.** |
| Counter 0 / 1 read | `0` / `0` (26 ms). **Works before the lock.** |
| Read OTP block 0 | refused, status `0x0F` (12 ms): hidden until the config lock |
| Read data slot 8 / slot 3 | refused, status `0x0F` (11 ms): hidden until the config lock |
| Read config word 4 | `c0000000`: I2C address byte 0xC0 = 0x60 on the bus (9 ms) |
| Random | `ffff0000` ×8, the fixed pattern (39 ms) |

So an unlocked 608A will identify itself, self-test, hash, and report its counters; it hides both
data zones and returns the test pattern for Random. The wallet's CHIP MAP and LAB (this branch)
show each of these on the device, refusals included.

### After the config lock, data zone still open (2026-09-17, same chip)

| command | answer |
|---|---|
| lock bytes 87 / 86 | `00` / `55`: config locked, data open |
| Random, twice | two different 32-byte values: the RNG is live (40 ms) |
| SelfTest 0x3F | `0x00`, all pass (257 ms) |
| SHA-256, Info State, Counter 0 | as before |
| Info KeyValid slot 0 | `00000000`: no key yet |
| GenKey mode 0 (public key) slot 0 | refused `0x0F`: empty slot |
| Read OTP blocks 0 and 1 | refused `0x0F` |
| Read data slots 0, 8, 12, 13 | refused `0x0F`, clear and secret slots alike |

The rule, which the datasheet states and this confirms: with the config zone locked and the data
zone open the chip accepts clear writes into slots and OTP but refuses to read any of them back;
reads begin only once the data zone is locked (LockValue). Neither the wallet firmware nor the
emulator knew that until this chip said so; both now do.

## 4. Flashing this branch's firmware

What changed for someone flashing from upstream `main`:

- New files that must be copied: `firmware/slots.py` (KEYS screen), `firmware/power.py`
  (battery), `firmware/chipcheck.py` (report). `wallet.py` imports the first two, so an old
  `tools/push` that only copies changed files would leave the board with an ImportError; copy all.
- `secrets.py` keeps the same flags. Nothing new is required; `ALLOW_LOCK` now also gates the
  data-zone and per-slot locks.
- The active slot is stored in `slot.txt` on the Pico's flash (absent = slot 0). Deleting it is
  safe.
- `tools/usb` (new) does the USB flow: `tools/usb push` copies every firmware file and resets,
  `tools/usb` alone opens the REPL, anything else is passed to mpremote. `push` is one mpremote
  session: soft-reset first, every `cp` chained, `os.sync()`, and only then a hard reset, the same
  order as upstream `261b373` gave `ship` after a reset right after a copy lost writes on
  LittleFS. `tools/push` and `tools/pico` are unchanged and still need the WiFi console.
- The emulator now has a virtual chip and starts blank; `tools/emu chip ready` gives a provisioned
  one. The generated emulator `secrets.py` sets both ALLOW flags True (virtual chip, no harm).

Flashing log (2026-09-16, macOS, perfboard build): mpremote 1.29.0, MicroPython v1.26.1
(2025-09-11, RPI_PICO2_W), port `/dev/cu.usbmodem112301`. `tools/usb push` copied 18 files in
one session, no retry; every `.py` on the board matched its local size afterwards (`os.stat`).
The serial port took more than 10 s to come back after the hard reset, so anything scripted
has to wait for `/dev/cu.usbmodem*` before the next mpremote call.

## 5. What worked and what did not on hardware (2026-09-16, read-only session)

- Chip found at: `0x60`, first try, wake 3 to 4 ms, ATECC608A.
- KEYS screen: list, chip page, raw config, random, slot 0 all as designed. Rows 0 to 2 read
  `P256` on the factory table (section 3), the rest `DATA`.
- Permanent-action gate refused with flags off: yes. `WRITE + LOCK CONFIG (off)` + A gave the red
  ERROR naming ALLOW_LOCK; chipcheck afterwards showed byte 87 still `0x55`.
- Battery: `usb` detection via `WL_GPIO2` works on the Pico 2 W (the pin prints as `EXT_GPIO2`).
  With the cell out and the switch off, GP28 read 1.08 V, most likely the Schottky's reverse
  leakage from VSYS through the divider; the home screen showed an empty bar and `1.1V` instead of
  `usb`. `power.py` now treats anything under 2.5 V as no cell. `vbat` vs a meter: not measured,
  no cell yet.
- Anything the emulator got wrong compared with the board: two things, both fixed in
  `atecc_sim.py` on this branch afterwards. Its blank part had an all-zero slot table where the
  real factory part types slots 0 to 2 as P-256 (SlotConfig `2083 2087 208f`, KeyConfig `0033`),
  and its Random was random before the config lock where the real chip returns the fixed
  `ffff0000` pattern. The sim now also answers Info KeyValid/State, SelfTest, SHA, Counter reads,
  and refuses OTP and data reads with 0x0F until the config lock.

## 6. Open questions for upstream

- The Setup page "Lock config zone" path and the wallet's `WRITE + LOCK CONFIG` use the same
  `ChipSigner.lock_config()`; both were affected, both are fixed by the constant.
- Slot lock and data-zone lock have not been run on real silicon by anyone in this repo. The
  virtual chip models them as: slot lock needs `KeyConfig.Lockable` and a locked config zone,
  not a locked data zone; GenKey needs the slot's `WriteConfig` GenKey bit even while the data zone
  is unlocked. If hardware disagrees, `atecc_sim.py` is where to correct it.
- `reference/ATECC608-demo-HANDOFF.md` says "slots 0-7 are private keys"; with the reference table
  that is 0, 2 and 7. Worth a one-line correction there.

## Issue draft

```
Title: firmware/atecc.py CONFIG has a shifted KeyConfig table; locking a fresh chip with it leaves slot 0 unable to hold a P-256 key

firmware/atecc.py's CONFIG is documented as "Microchip's ATECC608 reference config, same bytes
the Pi signer used", but it differs from reference/pi/signer.py (the table that provisioned chip #1).

The firmware copy is the ATECC508 test table with an extra row of 0xFF at bytes 96-111 and the
last row dropped. Bytes 96-111 are KeyConfig for slots 0-7, so they decode to 0xFFFF: KeyType 7,
"not an ECC key". After lock_config() writes and locks that table, GenKey on slot 0 fails
permanently (status 0x0F) and the config zone lock cannot be undone.

Decoded, main's table gives: slots 0-7 not ECC; slots 8 and 10 P-256 private but with SlotConfig
0x0F0F (no GenKey); nothing the wallet can use. The Pi's table gives slot 0 = 0x0033 (P-256
private, GenKey allowed), which is what the wallet expects.

Nobody has hit it because the firmware lock path has never run on a fresh chip (HANDOFF.md). It
would bite the next person following README step 5, since the Setup page's "lock config" runs
this table.

Fix: replace CONFIG with the bytes from reference/pi/signer.py (cryptoauthlib
test/api_calib/test_calib_config.c, test_ecc608_configdata). Regenerating from cryptoauthlib
rather than hand-editing would avoid a repeat. A PR with the one-hunk fix is at <link>.

Verified on a fresh Adafruit ATECC608A (2026-09-17): with the reference bytes written and locked,
GenKey in slot 0 works (four keys made in a row, KeyValid 1, public key readable, Sign verified
twice with counter 0 climbing, Random live).
On the same sealed chip, GenKey on a slot whose KeyConfig has KeyType 7 but whose SlotConfig
allows GenKey (slot 3 of the reference table) is refused with status 0x0F. That is the state
main's table puts slots 0-7 in, so the failure mode is observed, not inferred.

Two cheap guards would stop this class of bug for good (both on the fork's branch): assert at
import that decode_slot(CONFIG, 0) is a P-256 private slot with GenKey allowed, and have
lock_config() read the zone back and refuse to send Lock unless the chip's table matches CONFIG
and slot 0 passes the same check. Also README step 5 says "over USB, lock the config zone and
generate the key", but there is no USB command for that; the mechanism is the app's Setup page
(or, on the fork, the wallet's own screens).
```
