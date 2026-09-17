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
refused. Hardware verification: *(fill in from TESTPLAN phase 6, if done)*.

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
(chipcheck output)
```

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
  `tools/usb` alone opens the REPL, anything else is passed to mpremote. `tools/push` and
  `tools/pico` are unchanged and still need the WiFi console.
- The emulator now has a virtual chip and starts blank; `tools/emu chip ready` gives a provisioned
  one. The generated emulator `secrets.py` sets both ALLOW flags True (virtual chip, no harm).

Flashing log *(fill in)*: mpremote version, MicroPython build, port, anything that needed a retry.

## 5. What worked and what did not on hardware *(fill in)*

- Chip found at: `____`
- KEYS screen: `____`
- Permanent-action gate refused with flags off: `____`
- Battery: `usb` detection via `WL_GPIO2` / GP24: `____`; `vbat` vs meter: `____`
- Anything the emulator got wrong compared with the board: `____`

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
```
