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
