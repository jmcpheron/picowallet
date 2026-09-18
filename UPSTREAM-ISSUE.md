# Issue for austintgriffith/picowallet: `firmware/atecc.py` CONFIG has a shifted KeyConfig table; locking a fresh ATECC608 with it leaves slot 0 unable to ever hold a key

Ready to paste. The long notes with dumps and decodes are in `UPSTREAM.md`; the fix and the
guards are on `jmcpheron/picowallet` branch `claude/pico-wallet-signing-keys-uyr7mc`.

---

**Summary.** `firmware/atecc.py`'s `CONFIG` is documented as "Microchip's ATECC608 reference config,
the same bytes the Pi signer used", but it is not the table in `reference/pi/signer.py` (the one that
provisioned chip #1). It is the ATECC508 test table with an extra row of `0xFF` at bytes 96-111 and
the last row dropped. Bytes 96-127 are KeyConfig, two bytes per slot, so slots 0-7 decode to
`0xFFFF`: KeyType 7, "not an ECC key". `lock_config()` writes that table and locks the config zone,
which is permanent; afterwards GenKey in slot 0 is refused forever and the chip can never hold a
wallet key. Nobody has hit it because chip #1 was provisioned by the Pi code with the right bytes;
the next person following README step 5 with a fresh chip would.

**Decoded, main's table vs the Pi's:**

| slot | main `CONFIG` KeyConfig | decodes as | Pi / cryptoauthlib `test_ecc608_configdata` |
|---|---|---|---|
| 0 | `0xFFFF` | KeyType 7, not ECC | `0x0033`: P-256 private, PubInfo, lockable, GenKey allowed |
| 2, 7 | `0xFFFF` | not ECC | `0x0033` / `0x0033`: P-256 private |
| 8, 10 | `0x0033` / `0x0013` | P-256, but SlotConfig `0x0F0F`: GenKey not allowed | data |

**Verified on real silicon (2026-09-17, Adafruit 4314, ATECC608A, serial `0123f3acfd2a826bee`):**

- With the Pi's bytes written and locked from the wallet, GenKey in slot 0 works: four keys made in
  a row, each replacing the last (one of them on battery power); Info KeyValid reads 1; the public
  key reads back; Sign verified on the Pico twice; counter 0 climbed to 2 (slot 0 has LimitedUse).
- Control on the same sealed chip: GenKey on slot 3, whose SlotConfig allows GenKey but whose
  KeyConfig is `0x001C` (KeyType 7), is refused with status `0x0F`. That is the state main's table
  puts slots 0-7 in. The failure mode is observed, not inferred.
- Nobody locked a chip with main's table; the slot 3 experiment is the same condition at no cost.

**What else a fresh 608A taught us, in case it saves someone a chip:**

- The factory table is not blank: an Adafruit breakout ships with slots 0-2 typed P-256, GenKey
  allowed, and the rest as secret data. Full dump in `UPSTREAM.md` section 3.
- Until the config zone is locked, Random returns the datasheet's fixed pattern `ffff0000` eight
  times, every time; SelfTest, SHA-256 and counter reads work; every Data and OTP read is refused.
- After the config lock, with the data zone still open: Random is live, GenKey and Sign work in
  P-256 slots, clear writes into slots and OTP are accepted, but no Data or OTP read succeeds until
  the data zone is locked too. GenKey does not spend a count; signing from a LimitedUse slot does.
- The config zone is rewritable until the lock, and the chip reads it back, so writing the table
  and locking it are safely two steps with a checkpoint between.

**The locking process that worked:** write the 27 writable 4-byte words (skip words 0-3 and 21) as
`write_config` does, read the whole zone back and compare bytes 16-83 and 88-127, confirm slot 0
decodes as P-256 private with GenKey allowed, then Lock mode `0x80`, then read byte 87 (`0x00`).
Leave the data zone unlocked so GenKey can be re-run and slots written.

**Fix (on the fork branch):**

1. Replace `CONFIG` with the bytes of `reference/pi/signer.py`, byte for byte (one hunk). Better still,
   generate it from cryptoauthlib rather than hand-edit.
2. Two guards: assert at import that `decode_slot(CONFIG, 0)` is a P-256 private slot with GenKey
   allowed, and have `lock_config()` read the zone back and refuse to send Lock unless the chip's
   table matches `CONFIG` and slot 0 passes the same check.
3. README step 5 says "Over USB, lock the config zone and generate the key"; there is no USB command
   for that. The mechanism is the app's Setup page (`lock-config`, `genkey` over `/api/commands`),
   or on the fork the wallet's own screens.
