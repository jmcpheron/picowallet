# LEARN and LAB: the ATECC608 as a tutorial you operate. LEARN is five chapters, each a short card
# that leads into the real screen (the map, the lab, the config page). LAB asks the chip questions
# in plain words, one command each, and shows the answer three ways: what it means, the bytes, and
# the raw command underneath. A refusal is an answer too. Nothing here changes a byte on the chip.
import lcd as L
import atecc
import chipmap as C
import theme as T
import icons as I

CARD_ICON = ("chip", "lab", "config", "key", "lock", "book")

CARDS = (
    ("WHAT'S INSIDE?", "zones",
     "Inside the ATECC608 are four regions. CONFIG: 128 bytes of rules, four for each slot, saying what the slot is and what it may do. DATA: 16 slots, 36 bytes each for 0-7, 416 for slot 8, 72 for 9-15; keys and plain bytes live here. OTP: 64 bytes you can write once, bit by bit. COUNTERS: two numbers that only ever go up. Press A to open the map."),
    ("ASK THE CHIP", "lab",
     "Every screen here sends real commands over I2C and shows what the chip answers. In the LAB each question is one command. Some it answers, some it refuses, and a refusal is an answer too: it tells you what state the chip is in. Nothing in the LAB changes a byte. Press A to start asking."),
    ("CHANGE THE RULES", "cfg",
     "The CONFIG zone is the only region you can write while it is open, and you can write it again and again. Before the first write the wallet saves this chip's original bytes as a snapshot, so writing here is a REVERSIBLE CHANGE: RESTORE puts the snapshot back, and every write shows what will change first. The rules only become permanent when you LOCK the zone. Press A for the config page."),
    ("MAKE A KEY", "list",
     "A key is made by GenKey: the chip draws it from its own random generator and keeps it. You never see it, choose it, or read it out; only the public half comes out. Slot 7 also accepts PrivWrite, a key you bring, sent encrypted. A new key REPLACES the old one: there is no erase, and a locked slot never changes again. The chip refuses GenKey until the rules are sealed, so this chapter waits for that. Press A to look at the slots."),
    ("SEAL THE VAULT", "cfg",
     "Three one-way doors. LOCK CONFIG seals the rules: after it keys can be made and slots written, but the table can never change, and the chip reads nothing back from slots or OTP until the next door. LOCK DATA ZONE ends clear writes and opens reads. LOCK SLOT seals one key forever. Every red step needs three things: the flag on the board, the wallet ARMED (hold B and Y together 3 s), and A held 3 s on the red screen."),
    ("COLOURS AND GATES", None,
     "o green SAFE TO EXPLORE: changes nothing. ~ yellow REVERSIBLE CHANGE: can be restored. ! red PERMANENT: cannot be undone. Red needs ALLOW_LOCK or ALLOW_GENKEY True in secrets.py on the board, the wallet ARMED (hold B+Y 3 s, good for 60 s, shown in the header), and the red screen's hold. Refusals from the chip are shown as the chip said them, with the reason first."),
)
CONTEXT = {"zones": 0, "otp": 0, "counters": 0, "lab": 1, "labres": 1, "why": 1, "rawcmd": 1, "cfg": 2, "raw": 2, "diff": 2,
           "confirm_write": 2, "list": 3, "slot": 3, "pubkey": 3, "confirm": 4, "refused": 1, "result": 5, "learn": 5}


def draw_learn(ui):
    d = ui.d
    C.header(ui)
    y = 27
    d.text("the chip, one step at a time", 4, y, L.GREY); y += 16
    for i, (title, view, _) in enumerate(CARDS):
        sel = i == ui.act
        if sel:
            d.fill_rect(0, y - 4, 240, 20, T.C["ink"])
            d.fill_rect(0, y - 4, 3, 20, T.C["learn"])
        I.draw(d, CARD_ICON[i], 8, y - 4, T.C["learn"] if sel else T.C["grey"])
        d.text("%d" % (i + 1) if i < 5 else "?", 30, y, L.GREY)
        d.text(title, 46, y, L.YELLOW if sel else L.WHITE)
        if i in ui.done:
            I.draw(d, "check", 216, y - 4, T.C["safe"])
        y += 20
    C.footer(ui, "A read  Y home")


def tick_learn(ui, pressed):
    for k in pressed:
        if k == "up":
            ui.act = (ui.act - 1) % len(CARDS)
        elif k == "down":
            ui.act = (ui.act + 1) % len(CARDS)
        elif k == "A" or k == "press":
            ui.card = ui.act
            ui.go("card")
        elif k == "Y":
            ui.back()
        ui.dirty = True


def draw_card(ui):
    d = ui.d
    title, view, text = CARDS[ui.card]
    C.header(ui, "LEARN > %d %s" % (ui.card + 1, title) if ui.card < 5 else "LEARN > " + title)
    C.draw_scroll(ui, C.wrap(text), bottom=196)
    I.draw(d, CARD_ICON[ui.card], 206, 194, T.C["learn"], 2)
    C.footer(ui, ("A go  up/dn  Y back") if view else "up/dn scroll  Y back")


def tick_card(ui, pressed):
    C.scroll_tick(ui, pressed, 6)
    title, view, _ = CARDS[ui.card]
    for k in pressed:
        if k == "Y":
            ui.back()
        elif (k == "A" or k == "press") and view:
            ui.done.add(ui.card)
            ui.stack = []           # the chapter's screen is a fresh trail from CHIP
            if view == "zones":
                ui.view, ui.act, ui.scroll = "zones", 0, 0
            else:
                ui.view = "zones"
                ui.go(view)
            ui.dirty = True


def context(ui):
    """B anywhere in the chip UI: the card for the screen you are on."""
    i = CONTEXT.get(ui.view)
    if i is None or ui.view in ("card", "learn"):
        return
    ui.card = i
    ui.go("card")


# ----------------------------------------------------------------------------- LAB
FIXED = bytes([0xFF, 0xFF, 0x00, 0x00]) * 8
PARTS = {"00006002": "ATECC608A", "00006003": "ATECC608B", "00005000": "ATECC508A"}


def q_who(ui, chip):
    rev = chip.info(0)
    part = PARTS.get("".join("%02x" % b for b in rev), "a part I do not recognise")
    return ("I am an %s. My serial is %s and I answer at I2C address 0x%02x." % (part, ui.sig.serial(), chip.addr), rev, None)


def q_health(ui, chip):
    b = chip.selftest()
    if b == 0:
        return ("Every self test passed: random generator, ECDSA, ECDH, AES and SHA.", bytes([b]), None)
    why = ("One byte came back, 0x%02x, and a single byte is ambiguous: read as a status it says '%s'; read as test results it names bits %s as failed. "
           "On a chip whose rules are still open, a refusal is the likely reading." % (b, atecc.explain(b), [i for i in range(6) if b >> i & 1]))
    return ("Answer byte 0x%02x." % b, bytes([b]), why)


def q_random(ui, chip):
    r = chip.random()
    if r == FIXED:
        return ("Not randomness: the fixed pattern. My rules are not sealed yet.", r,
                "This is the datasheet's test pattern, ffff0000 repeated. Until the CONFIG zone is locked the chip answers Random with it every time, "
                "so anyone can tell an unlocked chip from a sealed one at a glance. Real random bytes only come after the lock.")
    return ("32 bytes from my hardware random generator, different every time.", r, None)


def q_hash(ui, chip):
    msg = b"picowallet"
    h = chip.sha256(msg)
    try:
        import hashlib
        same = h == hashlib.sha256(msg).digest()
        text = "SHA-256 of 'picowallet', computed on the chip. It %s the Pico's own answer." % ("matches" if same else "DIFFERS from")
    except ImportError:
        text = "SHA-256 of 'picowallet', computed on the chip."
    return (text, h, None)


def q_keyvalid(ui, chip):
    slot = ui.sig.slot
    v = chip.info(1, slot)
    if v[0] == 1:
        return ("Slot %d holds a usable key." % slot, v, None)
    why = ("GenKey is refused until the rules are sealed, so no slot can hold a key yet." if not ui.st.get("configLocked")
           else "Nothing has been generated in slot %d yet." % slot)
    return ("Slot %d holds no usable key." % slot, v, why)


def q_counter(ui, chip):
    n = chip.counter(0)
    return ("Counter 0 reads %d. It only ever goes up; slot 0's key can be set to spend one count per signature." % n, n.to_bytes(4, "little"), None)


def q_otp(ui, chip):
    return ("The first 32 of my 64 OTP bytes. Readable only once the DATA zone is locked.", chip.read_otp(0), None)


def q_data(ui, chip):
    return ("The first 32 bytes of slot 8, my biggest slot: 416 bytes. Its rules allowed a clear read.", chip.read_data(8, 0), None)


def q_addr(ui, chip):
    w = chip.read_config_word(4)
    return ("Config word 4. Its first byte is my I2C address as I store it, 0x%02x, which is 0x%02x on the bus (the chip keeps it shifted one bit)." % (w[0], w[0] >> 1), w, None)


QUESTIONS = (("WHO ARE YOU?", "Info revision + serial", "info", q_who, "idcard"),
             ("ARE YOU HEALTHY?", "SelfTest", "selftest", q_health, "heart"),
             ("MAKE RANDOMNESS", "Random", "random", q_random, "dice"),
             ("HASH SOMETHING", "SHA-256 of 'picowallet'", "sha", q_hash, "hash"),
             ("IS YOUR SLOT A KEY?", "Info KeyValid, this slot", "keyvalid", q_keyvalid, "key"),
             ("WHAT'S COUNTER 0?", "Counter read", "counters", q_counter, "counter"),
             ("WHAT'S IN YOUR OTP?", "Read OTP block 0", "otp", q_otp, "otp"),
             ("TRY READING SECRET SLOT 8", "Read data slot 8", "data", q_data, "bytes"),
             ("READ YOUR OWN ADDRESS", "Read config word 4", "info", q_addr, "pin"))


def draw_lab(ui):
    d = ui.d
    C.header(ui)
    y = 26
    top = max(0, min(ui.act - 4, len(QUESTIONS) - 6))
    for i in range(top, min(len(QUESTIONS), top + 6)):
        title, cmd, what, fn, ic = QUESTIONS[i]
        sel = i == ui.act
        if sel:
            d.fill_rect(0, y - 2, 240, 30, T.C["ink"])
            d.fill_rect(0, y - 2, 3, 30, T.C["lab"])
        I.draw(d, ic, 8, y + 2, T.C["lab"] if sel else T.C["grey"])
        C.badge(d, "safe", 28, y)
        d.text(title, 42, y, L.YELLOW if sel else L.WHITE)
        d.text(cmd[:24], 42, y + 12, C.DIM)
        y += 31
    C.footer(ui, C.CLASS["safe"][2], T.C["safe"])


def tick_lab(ui, pressed):
    for k in pressed:
        if k == "up":
            ui.act = (ui.act - 1) % len(QUESTIONS)
        elif k == "down":
            ui.act = (ui.act + 1) % len(QUESTIONS)
        elif k == "A" or k == "press":
            ask(ui, ui.act)
        elif k == "Y":
            ui.back()
        ui.dirty = True


def ask(ui, i):
    title, cmd, what, fn, ic = QUESTIONS[i]
    chip = getattr(ui.sig, "chip", None)
    if chip is None:
        return C.refuse(ui, what, None, "There is no chip on the bus; the software key cannot answer questions.")
    ui.busy(cmd + "...")
    try:
        text, raw, why = fn(ui, chip)
    except atecc.AteccError as e:
        ui.view = "lab"
        return C.refuse(ui, what, e)
    except Exception as e:
        ui.view = "lab"
        return C.refuse(ui, what, None, "The Pico side failed: %s" % e)
    ui.lab = {"q": title, "cmd": cmd, "text": text, "raw": raw, "why": why, "trace": chip.trace, "icon": ic}
    ui.ret, ui.view, ui.act2, ui.dirty = "lab", "labres", 0, True


def labres_items(ui):
    items = []
    if ui.lab.get("why"):
        items.append(("why", "WHY THAT'S WEIRD >", "safe", ""))
    items.append(("rawcmd", "RAW COMMAND >", "safe", ""))
    return items


def draw_labres(ui):
    d = ui.d
    lab = ui.lab
    C.header(ui)
    y = 27
    I.draw(d, lab.get("icon", "lab"), 206, 192, T.C["lab"], 2)
    d.text(lab["q"], 4, y, L.YELLOW); y += 14
    for line in C.wrap(lab["text"])[:6]:
        d.text(line, 4, y, L.WHITE); y += 12
    raw = lab.get("raw")
    if raw:
        h = "".join("%02x" % b for b in raw)
        for i in range(0, len(h), 29):
            d.text(h[i:i + 29], 4, y, L.GREY); y += 12
    y += 6
    items = labres_items(ui)
    C.menu(ui, items, y, ui.act2)
    C.footer(ui, "A open  Y back to LAB")


def tick_labres(ui, pressed):
    items = labres_items(ui)
    for k in pressed:
        if k == "up":
            ui.act2 = (ui.act2 - 1) % len(items)
        elif k == "down":
            ui.act2 = (ui.act2 + 1) % len(items)
        elif k == "Y":
            ui.view = ui.ret
        elif k == "A" or k == "press":
            kind = items[ui.act2][0]
            ui.view_from = "labres"
            ui.go(kind)
        ui.dirty = True


def draw_why(ui):
    C.header(ui)
    C.draw_scroll(ui, C.wrap(ui.lab["why"]))
    C.footer(ui, "up/dn scroll  Y back")
