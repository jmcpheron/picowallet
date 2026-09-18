# Open hardware signing, and the Pico as one leg of a multisig

Notes, 2026-09-18. Thinking out loud, not a plan yet. The question: where does a $35 hobby signer
fit once you take "not your silicon, not your keys" seriously, and what would a multisig made of
cheap, understandable, *different* signers look like.

## 1. The prompt

Vitalik's mid-September 2026 thread on AI and cybersecurity. The part that matters here:

- People treat hardware as an opaque box with "skeletons in the closet that nobody can understand".
  He says reject that fatalism. The stack that holds your keys has to become open, inspectable and
  formally verifiable all the way down: OS (GrapheneOS-style), ISA (RISC-V), chip designs you can
  image (IRIS, X-ray), and proofs that hardware plus software meet a spec. AI-assisted formal
  verification is the lever that makes the trusted computing base small enough to actually check.
- His slogan since late 2025: **"Not your silicon, not your keys."** Cryptography gives you
  mathematical guarantees *assuming* the hardware does what it claims. Closed firmware and
  microcode, side channels (timing, power, EM), supply-chain inserts, and leaky compiler/OS/library
  layers all break that assumption silently.
- Multisig and social recovery help at the application layer but do not fix a compromised root of
  trust *in one leg*. They do, however, mean one bad leg is not enough. That is the whole point of
  this note.

Coverage: [Vitalik Buterin Argues AI Can Strengthen Cybersecurity Through Mathematical Proofs](https://www.kucoin.com/news/flash/vitalik-buterin-argues-ai-can-strengthen-cybersecurity-through-mathematical-proofs),
[Vitalik Buterin rejects AI cybersecurity doom claim](https://crypto.news/vitalik-buterin-rejects-ai-cybersecurity-doom-claim/),
[Vitalik Buterin Calls for Verifiable Silicon Hardware](https://cryptomoonpress.com/news/vitalik-buterin-blockchain/).
(The original thread is on X. Add the direct link when we have it.)

## 2. Where picowallet actually stands against that bar

Honest inventory of what is open and what is a black box in the current device.

| layer | what we ship | open? | notes |
|---|---|---|---|
| contract | `ChipAccount.sol`, 34 tests, verified on Etherscan | yes | no admin, no upgrade; the part that is easiest to audit |
| signing app | `firmware/*.py` in MicroPython | yes | digest rebuilt on-device from raw fields; `eip712.py`, `keccak.py`, `p256.py` are pure Python you can read on the screen if you want |
| runtime | MicroPython, upstream `.uf2` | yes | reproducible from source in principle; we currently drag a prebuilt UF2 |
| MCU | RP2350 (Pico 2 W) | half | Arm Cortex-M33 cores are closed. The **Hazard3 RISC-V cores are open-source RTL**, and the chip can boot on them. Bootrom source is public. The SoC as a whole, and the OTP/secure-boot block, are not. |
| radio | CYW43439 on the Pico 2 W | no | closed firmware blob loaded by MicroPython. Off the signing path, but on the bus. |
| secure element | ATECC608 (Microchip) | **no** | full datasheet under NDA; internal firmware closed; we cannot image or verify it. This is exactly the box Vitalik is pointing at. |
| display | Waveshare Pico-LCD-1.3, ST7789 | mostly | the driver is ours; the panel controller is a commodity part |
| transport | WiFi, plain HTTP, no auth | open but weak | already documented in `SECURITY.md` |

So: the *software* half of the wallet meets the "open and inspectable" bar today. The two chips do
not. The one that holds the key is the one that matters, and it is the most closed thing on the
board.

### What we know about the closed parts

- **ATECC608**. The key cannot be read out through the command interface, and that is the property
  we rely on. But Ledger Donjon extracted slot contents from the predecessor **ATECC508A** with
  laser fault injection (SSTIC 2020, Black Hat 2020); Microchip then marked the 508A "not
  recommended for new designs". The 608 has countermeasures the 508 lacked, but we cannot inspect
  them. Read the 608 as "hardened against a curious neighbour, not against a $200k lab, and not
  verifiable by us either way".
  [SSTIC 2020 paper](https://www.sstic.org/media/SSTIC2020/SSTIC-actes/blackbox_laser_fault_injection_on_a_secure_memory/SSTIC2020-Article-blackbox_laser_fault_injection_on_a_secure_memory-heriveaux.pdf),
  [Coinkite write-up](https://blog.coinkite.com/laser-fault-injection/).
- **RP2350**. Raspberry Pi ran a public hacking challenge on its secure boot. It was broken
  several ways: a voltage glitch on the OTP read that re-enables the "permanently disabled" RISC-V
  cores with debug on (erratum E16, no mitigation, well under $1000 of gear), plus a laser attack
  past the glitch detectors. Good for us in one sense: this is *transparency working*. Bad in
  another: nothing in the Pico's own secure-boot story should be counted as a security boundary
  for a wallet.
  [Results](https://www.raspberrypi.com/news/security-through-transparency-rp2350-hacking-challenge-results-are-in/),
  [WOOT '25 paper](https://www.usenix.org/system/files/woot25-muench.pdf).
- Neither of these is a reason to stop. It is a reason to stop pretending a single ATECC608 is a
  root of trust, and to make it one signer among several.

## 3. The multisig idea

The thing I keep coming back to: **the Pico is not a Ledger competitor, it is a very good
multisig leg.** It is cheap, its firmware fits in your head, its display is driven by code you
wrote, and it uses a different secure element vendor than the other things you probably own.

Diversity is the property. If every leg of an n-of-m is a different silicon vendor and a different
firmware stack, then Vitalik's compromised-root-of-trust problem has to happen n times, in n
unrelated supply chains, to spend. That is a much better story than "trust this one box".

### P-256 is the common denominator

Everything below signs ECDSA P-256 over a 32-byte digest, and the contract already verifies P-256
through the EIP-7951 precompile. So a mixed-vendor multisig needs no new curve on chain:

| leg | silicon | firmware you can read | cost | notes |
|---|---|---|---|---|
| **picowallet** | Microchip ATECC608 + RP2350 | yes, all of it | $35 | what we have |
| second Pico, chip #2 | same vendor | yes | $35 | cheap second leg, but *same* silicon vendor, so it only covers loss/theft, not a vendor backdoor |
| Raspberry Pi + ATECC608 (`reference/pi/`) | same SE, different host | yes | | the signer this grew out of; a Linux host is a bigger TCB than the Pico |
| phone passkey (WebAuthn) | Apple Secure Enclave / Google Titan / Android StrongBox | no | $0 | huge vendor diversity vs Microchip; needs a WebAuthn verifier on chain because the signed bytes are `authenticatorData ‖ sha256(clientDataJSON)`, not the raw digest |
| YubiKey (PIV or FIDO2) | Infineon | no | $50 | third vendor; PIV signs a raw digest, FIDO2 needs the WebAuthn wrapper |
| **TROPIC01** (Tropic Square) | open-architecture RISC-V secure element, auditable design, GA and in full production as of 2025; shipping in Trezor Safe 7 | design is open | dev kit price TBD | the first leg that could actually meet Vitalik's bar for the SE. Needs a MicroPython driver; SPI, not I2C. |
| software key on Pico flash | none | yes, fully | $12 | zero tamper resistance, but 100% inspectable. As one leg of a 3-of-5 that is not crazy: it covers the "every secure element is backdoored" case, and the other legs cover the "someone stole the Pico" case. The firmware already has this as a fallback (`SECURITY.md` says fail closed instead; for a multisig leg, make it explicit and deliberate). |
| SeedSigner-style, stateless | commodity Pi Zero, no SE | yes | $50 | different philosophy: nothing persistent to extract, key rebuilt from a seed each session. Bitcoin-only today; the *approach* transfers. |
| OpenTitan / Earl Grey | open silicon RoT | design is open | not hobby-priced yet | the long-term answer, watch it |

Sources on TROPIC01: [official GA announcement](https://www.tropicsquare.com/news-and-events/tropic-square-announces-official-launch-general-availability-of-tropic01---the-industrys-first-open-architecture-tamper-proof-secure-element),
[full production](https://www.tropicsquare.com/news-and-events/tropic01-the-future-proof-secure-element-now-in-full-production-and-available-worldwide),
[CNX overview](https://www.cnx-software.com/2025/03/01/tropic-square-tropic01-is-an-auditable-open-architecture-tamper-proof-risc-v-secure-element-se-for-iot-and-microcontrollers/).

### Roles the Pico could play

1. **One of n spenders.** 2-of-3: Pico + phone passkey + YubiKey. Three vendors, three form
   factors, each one understandable on its own. The Pico is the only one whose display firmware you
   can read, so it is the leg you trust for *what am I signing*, and the others confirm.
2. **The backup / recovery leg.** Today `RECOVERY_ADDRESS` is a fixed EOA. It could be a second
   ChipAccount (chip #2 in a drawer), or a multisig. The 14-day delay already exists; the recovery
   signer just becomes hardware instead of a hot key. This is the smallest change and the one the
   user is most likely to actually set up.
3. **The "safe, understandable" leg in a Safe.** Keep the vault as a Gnosis Safe with normal
   owners, and add the Pico as one owner. Two ways:
   - ChipAccount implements EIP-1271 `isValidSignature`, so the Safe accepts a chip signature as an
     owner signature. Cleanest.
   - Or the chip signs a general call to `Safe.approveHash(hash)`. Works today with v5's
     `executeCall`, no contract change, but the device shows raw calldata, which is what
     `SECURITY.md` warns about. Would want a decoded "APPROVE SAFE TX" screen.

### What multisig does not fix

Say it plainly so the note is honest:

- A leaked key in one leg is still a leaked key. Diversity makes it *insufficient*, not harmless.
- Every leg still has the display problem: what you see is what you sign. Passkeys and YubiKeys
  have no screen at all. The Pico's screen is the whole reason it is on the list, and its screen
  firmware is only as trustworthy as the RP2350 running it, which we just said is glitchable. Fine
  for a hobbyist threat model; say so.
- The relay, the app and WiFi are still unauthenticated. Multisig raises the bar to spend, not to
  spam, spoof or DoS.
- n-of-m with hobby hardware means n devices to keep charged, updated and findable. Recovery
  paths for *losing legs* matter more than in the single-signer design.

## 4. Threat matrix, first cut

Which failure each leg absorbs. Fill this in properly before designing the contract.

| failure | single ATECC608 (today) | 2-of-3 Pico + passkey + YubiKey | + one software leg |
|---|---|---|---|
| Pico stolen, powered off | safe (key in SE) until glitched | safe | safe |
| Pico stolen, attacker has lab | at risk (508A precedent) | safe, needs a second leg | safe |
| Microchip backdoor / bad batch | lost | safe | safe |
| Apple/Google/Infineon backdoor | n/a | safe, each is one leg | safe |
| all secure-element vendors compromised | lost | lost | safe if software leg + one more |
| compromised laptop / relay | can only spoof display hints, not spend | same, and now needs to fool two devices | same |
| user loses one device | 14-day recovery | still spendable, rotate the lost leg | same |
| user loses two devices | lost until recovery | 14-day recovery | same |

## 5. Things to actually try, in order

1. **Hardware recovery leg.** Deploy a v5 vault where `RECOVERY_ADDRESS` is a second
   ChipAccount owned by chip #2 on a second Pico. No contract change. Rehearse start / cancel /
   finalize with two devices on the desk. Cheapest possible experiment. Photograph it for the
   buildlog.
2. **EIP-1271 on ChipAccount.** Small Solidity change, lets the vault be a Safe owner. Tests.
   Then a Safe with Pico + MetaMask + a hardware EOA as 2-of-3, and a decoded Safe-approval screen
   in `wallet.py`. Try the screen on the emulator first (`tools/emu`).
3. **WebAuthn leg.** Passkey in the browser as a P-256 co-signer. Needs a WebAuthn verifier
   contract (Daimo's `p256-verifier` / Coinbase Smart Wallet's `WebAuthn.sol` are the usual
   references) and a `ChipMultisig` k-of-n variant, or skip our contract and use a Safe module.
   Decide after 2.
4. **TROPIC01 driver.** Get a dev board, write `firmware/tropic.py` over SPI, same `pubkey()` /
   `sign(digest)` interface as `atecc.py`. Then the *same* firmware runs with an open secure
   element. This is the leg that answers Vitalik's point directly.
5. **Boot on Hazard3.** Build MicroPython for the RP2350's RISC-V cores instead of the Cortex-M33.
   The signing path then runs on open-source cores. Cheap to try, mostly a bragging right, but it
   is a real shrink of the closed part of the TCB.
6. **Reproducible firmware.** Stop dragging a prebuilt UF2. Build MicroPython from a pinned commit
   and publish the hash. Closes the "how do I know this UF2 is upstream" gap in the table above.

## 6. Open questions

- Is it better to extend `ChipAccount` into a k-of-n of P-256 keys, or to keep it single-signer
  and lean on Safe for the multisig? Safe brings a big, audited codebase and a UI; our own
  contract stays small enough to read in one sitting. Leaning: EIP-1271 + Safe for real money,
  a tiny `ChipMultisig` as a teaching contract.
- How does a Pico with no persistent identity (SeedSigner style) fit? Would mean a seed phrase
  and P-256 derivation in pure Python on the device, every boot. Slow but fully inspectable.
- What is the smallest honest spec for "the display shows what the chip signs" that someone could
  actually formally check? The `eip712.py` rebuild-and-compare step is close to a spec already.
- Does any of this change the case? Two Picos in one shell, or a second-leg "key fob" with no
  screen, is a different `case/gen.py`.

## 7. Thought experiment: bring your own entropy, verify the chip's key

The question (2026-09-18): on an air-gapped machine, make our own randomness, emulate what the
chip would do with it, check the result independently, then feed the *same* entropy to the real
chip and confirm it reports the same public key. Does the ATECC608 let you do that?

### Short answer

- **Seeding GenKey: no.** GenKey (0x40, mode "create") draws from the chip's internal RNG and takes
  no input. There is no command that says "derive a key from these bytes I give you". You cannot
  reproduce or predict a GenKey result from outside, by design.
- **Importing the key itself: yes, PrivWrite (0x46).** You generate the 32-byte private scalar
  yourself, write it into a P-256 slot, then ask the chip for the slot's public key and compare it
  with the one you computed offline. Match means the chip holds exactly the scalar you gave it.
  That is the check you were after, one level down: import the key, not the entropy.
- **Traditional EOA key (secp256k1): no,** not on this chip. The ATECC608 is P-256 only. The same
  import-then-compare trick works on any secure element that has a key-import command and the
  curve you want (NXP SE050 lists secp256k1; check TROPIC01's curve list before assuming).
- **It closes one door, not two.** Importing the key removes the chip's RNG from *key generation*.
  ECDSA still needs a fresh random `k` for every signature, and the ATECC608 picks `k` internally
  from the same RNG, with no deterministic (RFC 6979) mode and no host-supplied `k`. A dishonest RNG
  can leak the private key through the signatures. You cannot detect that from outside if it is
  done competently. So even with your own key inside, every signature still trusts the chip.

### How the relevant commands actually behave

| command | what the host supplies | what it does | usable for this? |
|---|---|---|---|
| Random (0x1B) | nothing | 32 bytes from the internal RNG mixed with an EEPROM seed | you can read it, not steer it |
| Nonce (0x16) | 20 or 32 bytes | mixes host bytes into TempKey (mode 0x03 is the pass-through the wallet uses to load a digest) | feeds Sign, GenDig, MAC. GenKey never reads TempKey. |
| GenKey (0x40) mode 0x04 | nothing | new random private key in the slot, returns the public key | no input path for entropy |
| GenKey (0x40) mode 0x00 | nothing | returns the public key of the key already in the slot | **the read-back half of the check**; this is `atecc.pubkey()` |
| PrivWrite (0x46) | 36 bytes: 4 zero pad + 32-byte scalar | writes a private key into a slot whose config allows it | **the import half of the check** |
| DeriveKey (0x1C), KDF (0x56) | a nonce / input | SHA-256 or HKDF-derived 32-byte secrets into a slot | symmetric keys; not a documented way to make an ECC private key |
| Sign (0x41) | digest via TempKey | ECDSA with the chip's own random `k` | no host `k`, not deterministic |

PrivWrite is gated per slot by `SlotConfig.WriteConfig` bit 2 (bit 1 is GenKey). Encrypted
PrivWrite uses a session key derived from a "write key" in another slot. cryptoauthlib's
`atcab_priv_write` states the unencrypted form is allowed only while the **data zone is unlocked**,
which on a provisioning bench is the case you want anyway: the scalar goes over I2C once, in the
clear, on an air-gapped Pico over USB with no WiFi firmware loaded.

### The procedure that does work

1. Air-gapped machine. Make the scalar `d` from entropy you control. Dice plus the OS RNG, hashed
   together, is the usual move: if either source is honest, `d` is fine. Reject `d = 0` or
   `d >= n`.
2. Compute `Q = d·G` with **two independent implementations** and require them to agree. This
   repo already has both: `firmware/p256.py` `pubkey(d)` (pure Python, readable in one sitting)
   and the `cryptography` library, which `reference/pi/signer.py` already uses via
   `derive_private_key`. `openssl` is a third.
3. PrivWrite `d` into a slot configured for it. Data zone unlocked, so plaintext is allowed.
4. Read back the public key with GenKey mode 0x00. Compare with `Q`. Match, or stop.
5. Sign a known digest on the chip, verify it against `Q` offline (PLAN step 1 already does this).
6. Decide what happens to `d` on the bench. Wipe it, and the key now exists only in the chip,
   same story as today. Or keep it on paper in a safe, and the story becomes "hardware for daily
   use, paper for disaster". For a *backup leg* of a multisig the paper copy is arguably the point.
7. Optionally lock the data zone. After that nothing can be written to the slot again.

### What this buys

- Rules out a weak or kleptographic RNG in key generation. You cannot detect a Dual-EC-style
  backdoor by inspecting outputs; a key you generated yourself is the only defence.
- Rules out "the factory pre-loaded a key someone else knows". (An honest GenKey also rules that
  out, but "honest" is the thing in question.)
- Gives you a public key you computed on a machine you trust, before the chip ever saw it. The
  contract can be deployed from that value, and the chip's report is a confirmation rather than
  the source of truth.

### What it does not buy

- Nonce leakage, as above. A cold backup leg that signs a handful of times in its life is exposed
  to this far less than a daily signer, which is another argument for the Pico as the backup leg.
- Side channels, hidden commands, laser and glitch extraction: unchanged.
- The key crossed a wire and lived in a host's RAM. The bench has to be clean and the wipe has to
  be real. This is the SeedSigner trade: trust your process instead of the chip's RNG.
- "Emulating the chip" only reproduces `d → Q`. Signatures are not reproducible because `k` is
  random. What the Pico *can* do cheaply is verify-only emulation: `p256.verify` already exists,
  so the firmware could check every chip signature against the pinned `Q` before handing it to the
  relay. That catches a swapped chip or the wrong slot. It does not catch a leaky `k`.

### What the chips we have can and cannot do

Decoded from the two config arrays in the repo (`SlotConfig` bytes 20-51, `KeyConfig` 96-127):

- **Chip #1** (on the Pi, config locked, data unlocked) was provisioned with
  `reference/pi/provision.py`'s config. Slot 0: P-256, external sign, `WriteConfig = 0b0010`,
  so **GenKey only, PrivWrite refused**. Slot 7 allows PrivWrite (`0b0110`) but its `ReadKey`
  permits ECDH only, no external signatures. No slot on chip #1 can take an imported *signing*
  key. The config is locked, so that will never change.
- **Chip #2** is blank. It can get a config where slot 0 has `WriteConfig = 0b0110` (GenKey and
  PrivWrite), `ReadKey = 0xF`, `KeyConfig = 0x0033`. That is the chip for this experiment.

### A bug found while decoding, do not lock a chip with the Pico's CONFIG

`firmware/atecc.py` says its `CONFIG` is "the same bytes the Pi signer used". It is not. The
Pico array has an extra row of `0xFF` at bytes 96-111, which is where `KeyConfig` for slots 0-7
lives. Decoded, slot 0's `KeyConfig` is `0xFFFF`: `KeyType = 7`, not P-256. The Pi's array has
`0x0033` there, which is correct, and its `KeyConfig` row for slots 8-15 is what the Pico array
has shifted down into bytes 112-127.

The buildlog for 2026-09-05 says the Pico's lock and GenKey paths "have NOT yet run on a fresh
chip", which is consistent: no chip has been locked with this array. If someone follows README
step 5 on a fresh chip, `lock_config` is permanent and GenKey on slot 0 will most likely be
refused, bricking that chip for our purpose. Fix before anyone provisions from the wallet, and
before chip #2 is touched: make the Pico array byte-identical to the Pi's (and add the PrivWrite
bit for slot 0 while at it, if the import experiment is wanted), and add a test that decodes
`KeyConfig[0]` and asserts P-256.
