# picowallet: the loop. Talks to the app, shows what is being asked, signs only on a button press.
#
# One 50 ms Timer (a scheduled, soft callback) so main.py can return to the REPL and the WiFi
# console keeps working. Every tick polls keys and redraws; every 20th tick talks to the app.
# Why one timer: the rp2 scheduler queue holds 8 callbacks. A second fast timer fills it while an
# HTTP call blocks, and then the console's socket-accept callback gets dropped for good.
# Signing + relaying can take seconds, so approve() stops the timer and restarts it after.
import time, json, machine, network, gc
import requests
import lcd as L
import net
import eip712
import signer as S
gc.collect()        # the chip UI modules are big; compiling them wants contiguous heap (a MemoryError here was seen once at power-up)
import slots as SL
import power
import splash
import icons as ICONS
import theme as THEME
try:
    import secrets
except ImportError:
    secrets = None      # fresh board: the home screen says "no secrets.py" instead of connecting

APP = secrets.APP_URL if secrets else None
NAME = getattr(secrets, "DEVICE_NAME", "picowallet")
SSID = getattr(secrets, "WIFI_SSID", "") if secrets else ""
APP_HOST = (APP or "").replace("http://", "").replace("https://", "").rstrip("/")
# The account is the chip's key. Without a chip there is no account, so the wallet stops on a
# NO CHIP screen. The emulator sets ALLOW_SOFT_KEY in its generated secrets.py to test the flow.
SOFT_OK = bool(getattr(secrets, "ALLOW_SOFT_KEY", False)) if secrets else False

d = None
keys = None
sig = None          # the signer backend
state = "boot"      # boot | home | confirm | working | done | error | keys | nochip
slots_ui = None     # the KEYS screen (slots.py): X on the home screen
chip_st = {}        # sig.status() as of the last probe or key change, plus "part" and "state" (new | empty | key)
net_err = ""        # last app error, shown on the status home until a fetch succeeds
splash_until = 0    # the boot screen stays up until then (ticks_ms), then home
page = 0            # confirm: 0 = summary, 1 = details
req = None          # request on screen
info = {}           # last /api/state
msg = ""            # status line / result text
msg_until = 0
seen = set()        # request ids already handled
last_announce = 0        # 0 = never; the first tick announces right away
last_fetch = 0
STATE_EVERY_MS = 12000   # about one block; the balance shows up fast after a deposit
paired = False
qx = qy = ""
dirty = True
_busy = False
log = []


def say(s, secs=4):
    global msg, msg_until, dirty
    msg = s
    msg_until = time.ticks_add(time.ticks_ms(), secs * 1000)
    dirty = True
    _log(s)


def _log(s):
    log.append(s)
    if len(log) > 30:
        log.pop(0)


# ----------------------------------------------------------------------------- screens
def short(a):
    return a[:6] + ".." + a[-4:] if len(a) > 14 else a


def eth_amount(wei):
    n = int(wei)
    whole, frac = n // 1000000000000000000, n % 1000000000000000000
    if not frac:
        return str(whole)
    return "%d.%s" % (whole, ("%018d" % frac).rstrip("0")[:6])


_qr = None          # (address, n, rows) from qr.bin, built by tools/qr
_last_bal = None


def load_qr():
    global _qr
    try:
        b = open("qr.bin", "rb").read()
        addr, n = b[:42].decode(), b[42]
        w = (n + 7) // 8
        rows = [int.from_bytes(b[43 + i * w:43 + (i + 1) * w], "little") for i in range(n)]
        _qr = (addr, n, rows)
    except Exception as e:
        _qr = None
        _log("no qr.bin: %r" % e)


def draw_qr(y0, size):
    """QR of the vault address, centered, black on white. size = px per module."""
    addr, n, rows = _qr
    pad = 8
    box = n * size + 2 * pad
    x0 = (240 - box) // 2
    d.fill_rect(x0, y0, box, box, L.WHITE)
    for r in range(n):
        bits = rows[r]
        for c in range(n):
            if bits >> c & 1:
                d.fill_rect(x0 + pad + c * size, y0 + pad + r * size, size, size, L.BLACK)
    return box


def draw_home():
    d.fill(L.BLACK)
    account = info.get("account", {})
    acct = account.get("address", "")
    ens_name = account.get("ensName")
    bal = account.get("balanceFormatted")
    chain = info.get("chain", {})
    # top-left: which chain. Test money and real money must never look alike.
    if chain:
        d.text("mainnet" if chain.get("id") == 1 else (chain.get("name", "?").lower()[:8]), 4, 4, L.GREEN if chain.get("id") == 1 else L.YELLOW)
    # top-middle: power. USB, or the cell voltage from the divider on GP28 (power.py, SOLDERING.md)
    pw = power.status()
    if pw["usb"] and not pw["percent"]:
        d.text("usb", 100, 4, L.GREY)
    elif pw["percent"] is not None:
        d.rect(92, 4, 14, 8, L.GREY)
        d.fill_rect(106, 6, 2, 4, L.GREY)
        d.fill_rect(94, 6, max(1, 10 * pw["percent"] // 100), 4, L.RED if pw["low"] else L.GREEN)
        d.text("%.1fV" % pw["vbat"], 112, 4, L.RED if pw["low"] else L.GREY)
    # top-right: the KEYS screen hint and the pairing dot
    d.text("X map", 178, 4, L.GREY)
    d.fill_rect(226, 4, 8, 8, L.GREEN if paired else L.RED)
    # top-centre: which key. The chip is the point; a software key must never pass unnoticed.
    if sig and sig.name != "atecc608":
        d.center_text("NO CHIP", 4, L.RED)
    # balance, big; without one, what the board is (chip, wifi, app) instead of a bare "connecting"
    if bal is None:
        draw_status()
    else:
        whole, _, frac = bal.partition(".")
        sbal = "$" + whole + "." + (frac + "00")[:2]
        d.center_text(sbal, 24, L.WHITE, 4 if len(sbal) <= 7 else 3)
        d.center_text(info.get("token", {}).get("symbol", ""), 62, L.GREY)
    # QR of the vault, small
    if _qr and acct and _qr[0].lower() == acct.lower():
        box = draw_qr(80, 4)   # 29 * 4 + 16 = 132 px
        if ens_name:
            d.center_text(ens_name[:20], 80 + box + 4, L.YELLOW, 2 if len(ens_name) <= 18 else 1)
        else:
            d.center_text(acct[:21], 80 + box + 4, L.GREY)
            d.center_text(acct[21:], 80 + box + 14, L.GREY)
    elif acct:
        d.center_text(ens_name or short(acct), 130, L.YELLOW if ens_name else L.GREY)
        d.center_text("run tools/qr", 150, L.RED)
    # status bar: a flash message beats a warning beats nothing
    warn = None
    try:
        if float(info.get("relayer", {}).get("balanceFormatted", "1")) < 0.0005:
            warn = "relay gas low"
    except ValueError:
        pass
    age = time.ticks_diff(time.ticks_ms(), last_fetch) // 1000 if last_fetch else 0
    if age > 45:
        warn = "no app for %ds" % age
    if not paired:
        warn = "not paired" if qx else "no key"
    if not paired and chip_st.get("state") == "new":
        warn = "new chip, untouched: X to look"
    if pw["low"] and not pw["usb"]:
        warn = "battery low %.2fV" % pw["vbat"]
    if sig and sig.name != "atecc608":
        warn = "no chip: software key"
    if not network.WLAN(network.STA_IF).isconnected():
        warn = ("no wifi: %s not found" % SSID)[:30] if SSID else "no wifi: no SSID in secrets.py"
    if secrets is None:
        warn = "copy secrets.py to the board"
    if time.ticks_diff(msg_until, time.ticks_ms()) > 0:
        d.fill_rect(0, 224, 240, 16, L.DARK)
        d.center_text(msg[:30], 228, L.YELLOW)
    elif warn:
        d.fill_rect(0, 224, 240, 16, L.DARK)
        d.center_text(warn, 228, L.RED)
    d.show()


def draw_status():
    """Home without a balance to show: the board at a glance. Is the chip new, set up, or holding a
    key; wifi; the app. Nothing here touches the chip, it reads chip_st from the last probe."""
    st = chip_st
    soft = sig is not None and sig.name != "atecc608"
    if sig is not None and not soft:
        ICONS.draw(d, "chip", 4, 22, THEME.C["chip"])
        ICONS.draw(d, "lock" if st.get("configLocked") else "unlock", 220, 22, THEME.C["safe"] if st.get("configLocked") else THEME.C["perm"])
    if secrets is None:
        d.center_text("no secrets.py", 22, L.RED, 2)
        d.center_text("copy it to the board", 44, L.GREY)
    elif soft:
        d.center_text("SOFTWARE KEY", 22, L.RED, 2)
        d.center_text("no chip on the bus", 44, L.GREY)
    elif st.get("state") == "new":
        d.center_text("NEW CHIP", 22, L.YELLOW, 2)
        d.center_text("config open, never set up", 44, L.GREY)
    elif st.get("state") == "empty":
        d.center_text("LOCKED, NO KEY", 22, L.YELLOW, 2)
        d.center_text("set up, slot %d is empty" % st.get("activeSlot", 0), 44, L.GREY)
    elif paired:
        d.center_text("connecting...", 22, L.GREY, 2)
    else:
        d.center_text("KEY " + st.get("fingerprint", "?")[:8], 22, L.WHITE, 2)
        d.center_text("waiting for the app to pair", 44, L.GREY)
    y, X = 64, 60
    if sig is not None:
        d.text("chip", 4, y, L.GREY)
        d.text(((st.get("part") or sig.name) + ("  i2c " + st["i2cAddr"] if st.get("i2cAddr") else ""))[:22], X, y, L.WHITE); y += 12
        if st.get("serial"):
            d.text("serial", 4, y, L.GREY); d.text(st["serial"], X, y, L.WHITE); y += 12
        cfg, data = st.get("configLocked"), st.get("dataLocked")
        d.text("config", 4, y, L.GREY); d.text("LOCKED" if cfg else "OPEN", X, y, L.GREEN if cfg else L.RED)
        d.text("data", 124, y, L.GREY); d.text("LOCKED" if data else "open", 164, y, L.GREEN if data else L.YELLOW); y += 12
        d.text("slot %d" % st.get("activeSlot", 0), 4, y, L.GREY)
        d.text(("key " + st["fingerprint"]) if st.get("hasKey") else "no key", X, y, L.WHITE if st.get("hasKey") else L.YELLOW); y += 16
    w = network.WLAN(network.STA_IF)
    d.text("wifi", 4, y, L.GREY)
    if secrets is None:
        d.text("no secrets.py", X, y, L.RED); y += 12
    elif w.isconnected():
        d.text(SSID[:22], X, y, L.WHITE); y += 12
        d.text(w.ifconfig()[0], X, y, L.GREEN); y += 12
    else:
        d.text(("not found: " + SSID)[:22], X, y, L.RED); y += 12
    d.text("app", 4, y, L.GREY)
    d.text(APP_HOST[:22] if APP_HOST else "none in secrets.py", X, y, L.WHITE); y += 12
    if last_fetch:
        d.text("ok %ds ago" % (time.ticks_diff(time.ticks_ms(), last_fetch) // 1000), X, y, L.GREEN)
    elif net_err:
        d.text(net_err[:22], X, y, L.RED)
    elif secrets is not None:
        d.text("not reached yet", X, y, L.GREY)
    # what to do next, by state
    if secrets is None or soft:
        hint = ()
    elif st.get("state") == "new":
        hint = ("next: X, chip page, WRITE +", "LOCK CONFIG (needs ALLOW_LOCK)")
    elif st.get("state") == "empty":
        hint = ("next: X, slot %d, NEW KEY" % st.get("activeSlot", 0), "(ALLOW_GENKEY in secrets.py)")
    elif not w.isconnected():
        hint = ("offline: the chip map, LAB and", "snake work; wifi retries itself")
    elif not paired:
        hint = ("next: run the app, it pairs", "a vault to this key")
    else:
        hint = ()
    for i, line in enumerate(hint):
        d.center_text(line, 180 + 12 * i, L.GREY)
    d.center_text("X chip map    B learn", 208, L.GREY)


def tri_right(x, y, h, c):
    """Solid triangle pointing right, tip at (x+h//2, y), height h."""
    for i in range(h // 2):
        d.vline(x + i, y - (h // 2 - i), h - 2 * i, c)


def bar(y, h, label, color, scale):
    """Full-width bar with a label and an arrow at the right edge pointing at the physical button."""
    d.fill_rect(0, y, 240, h, color)
    d.center_text(label, y + (h - 8 * scale) // 2, L.WHITE, scale)
    tri_right(222, y + h // 2, 16, L.WHITE)


# The A/B/X/Y column sits along the right edge of the screen: A near the top, Y at the bottom.
# SIGN lives in a green bar in line with A, REJECT in a red bar in line with Y.
SIGN_BAR = (0, 60)
REJECT_BAR = (190, 50)


def draw_confirm():
    d.fill(L.BLACK)
    if page == 0:
        bar(SIGN_BAR[0], SIGN_BAR[1], "SIGN", L.GREEN, 3)
        if req.get("kind") == "setName":
            d.center_text("SET ENS NAME", 76, L.WHITE, 2)
            d.center_text(req["name"][:18], 112, L.YELLOW, 2)
            d.center_text("for " + short(req["account"]), 146, L.GREY)
        elif req.get("kind") == "cancelRecovery":
            d.center_text("CANCEL RECOVERY", 76, L.YELLOW, 2)
            d.center_text("KEEP CURRENT KEY", 116, L.WHITE, 2)
            d.center_text(short(req["account"]), 150, L.GREY)
        elif req.get("kind") == "execute":
            selector = req["data"][:10] if len(req["data"]) >= 10 else "0x00000000"
            title = "TOKEN TRANSFER" if selector == "0xa9059cbb" else ("TOKEN APPROVAL" if selector == "0x095ea7b3" else "GENERAL CALL")
            d.center_text(title, 72, L.YELLOW, 2)
            d.center_text(short(req["target"]), 108, L.WHITE, 2)
            d.center_text(eth_amount(req["value"]) + " ETH", 138, L.GREY, 2)
            d.center_text(selector, 166, L.GREY)
        else:
            amt = "$" + req["amountFormatted"]
            d.center_text(amt, 68, L.WHITE, 4 if len(amt) <= 7 else 3)
            d.center_text(req["tokenSymbol"], 104, L.GREY)
            d.center_text("to", 122, L.GREY)
            name = req.get("toName") or short(req["to"])
            d.center_text(name[:14], 138, L.YELLOW, 2)
            d.center_text(short(req["to"]), 162, L.GREY)
        bar(REJECT_BAR[0], REJECT_BAR[1], "REJECT", L.RED, 3)
    else:
        bar(0, 22, "SIGN", L.GREEN, 1)
        y = 28
        if req.get("kind") == "setName":
            lines = (
                "name " + req["name"],
                "nonce %s  chain %s" % (req["nonce"], req["chainId"]),
                "deadline " + str(req["deadline"]),
                "vault " + short(req["account"]),
                "digest (checked on device)",
                req["digest"][2:34], req["digest"][34:],
            )
        elif req.get("kind") == "cancelRecovery":
            lines = (
                "CANCEL RECOVERY",
                "keep current hardware key",
                "nonce %s  chain %s" % (req["nonce"], req["chainId"]),
                "deadline " + str(req["deadline"]),
                "vault " + short(req["account"]),
                "digest (checked on device)",
                req["digest"][2:34], req["digest"][34:],
            )
        elif req.get("kind") == "execute":
            raw = bytes.fromhex(req["data"][2:])
            data_hash = "".join("%02x" % b for b in eip712.data_hash(raw))
            selector = req["data"][:10] if len(req["data"]) >= 10 else "0x00000000"
            lines = (
                "target " + req["target"][:20], "       " + req["target"][20:],
                "value " + req["value"] + " wei",
                "selector " + selector,
                "calldata %d bytes" % len(raw),
                "data hash (device)", data_hash[:32], data_hash[32:],
                "nonce %s  chain %s" % (req["nonce"], req["chainId"]),
                "deadline " + str(req["deadline"]),
                "vault " + short(req["account"]),
                "digest (checked on device)",
                req["digest"][2:34], req["digest"][34:],
            )
        else:
            lines = (
                "to " + req["to"][:22], "   " + req["to"][22:],
                "amount " + req["amount"],
                "nonce %s  chain %s" % (req["nonce"], req["chainId"]),
                "deadline " + str(req["deadline"]),
                "vault " + short(req["account"]),
                "token " + req["token"][:22], "      " + req["token"][22:],
                "digest (checked on device)",
                req["digest"][2:34], req["digest"][34:],
            )
        for line in lines:
            d.text(line[:30], 4, y, L.GREEN if line.startswith("digest") else L.WHITE)
            y += 14
        bar(218, 22, "REJECT", L.RED, 1)
    d.show()


def draw_msg(title, color):
    d.fill(L.BLACK)
    d.fill_rect(0, 0, 240, 26, color)
    d.center_text(title, 5, L.WHITE, 2)
    y = 60
    for i in range(0, len(msg), 28):
        d.text(msg[i:i + 28], 6, y, L.WHITE)
        y += 14
    d.center_text("A = ok", 210, L.GREY)
    d.show()


def draw_nochip():
    d.fill(L.BLACK)
    d.fill_rect(0, 0, 240, 26, L.RED)
    d.center_text("NO CHIP", 5, L.WHITE, 2)
    y = 50
    for line in ("no ATECC608 answered", "on I2C (GP4 SDA, GP5 SCL)", "", "the account is the",
                 "chip's key, so there", "is no account here", "", "wire the chip, then", "press A to look again"):
        d.center_text(line, y, L.WHITE if line else L.BLACK)
        y += 16
    d.show()


def draw():
    if state == "boot" and splash_until and time.ticks_diff(splash_until, time.ticks_ms()) > 0:
        splash.draw()
        return
    if state == "nochip":
        draw_nochip()
    elif state in ("boot", "home"):
        draw_home()
    elif state == "confirm":
        draw_confirm()
    elif state == "keys":
        slots_ui.draw()
    elif state == "working":
        draw_msg("SIGNING", L.BLUE)
    elif state == "done":
        draw_msg("SENT", L.GREEN)
    elif state == "error":
        draw_msg("ERROR", L.RED)


# ----------------------------------------------------------------------------- ui tick
_n = 0


def tick(t):
    global dirty, page, state, _busy, _n, splash_until
    if _busy:
        return
    _busy = True
    try:
        _n += 1
        net.poll_accept()
        if _n % 20 == 0:
            timer.deinit()      # no timer events pile up while HTTP blocks (mainnet: 0.5-3 s)
            try:
                net_work()
            finally:
                start_timer()
        pressed = keys.pressed()
        if state == "keys":
            if slots_ui.tick(pressed, keys) == "home":
                state = "home"; dirty = True
            pressed = ()
        for k in pressed:
            if state == "nochip":
                if k == "A":
                    probe_chip(); dirty = True
            elif state == "confirm":
                if k == "A":
                    approve(True)
                elif k == "Y":
                    approve(False)
                elif k == "down":
                    page = 1; dirty = True
                elif k == "up":
                    page = 0; dirty = True
            elif state in ("done", "error") and k == "A":
                state = "home"; dirty = True
            elif state in ("home", "boot") and k in ("X", "press"):   # boot: no app yet, the chip is explorable anyway
                slots_ui.open("zones")
                state = "keys"; dirty = True
            elif state in ("home", "boot") and k == "B":
                slots_ui.open("learn")
                state = "keys"; dirty = True
        if splash_until:
            if time.ticks_diff(splash_until, time.ticks_ms()) > 0:
                if _n % 3 == 0:
                    dirty = True    # the boot screen's legs walk
            else:
                splash_until = 0; dirty = True
        if state in ("home", "boot") and _n % 20 == 0:
            dirty = True  # status line, wifi and app rows: once a second. Never per tick: a full
                          # redraw is ~45 ms of a 50 ms tick and starves the REPL (seen on USB)
        if dirty:
            draw()
            dirty = False
    except Exception as e:
        _log("ui: %r" % e)
    finally:
        _busy = False


# ----------------------------------------------------------------------------- app protocol
def hex32(n):
    return "0x%064x" % n


def announce():
    global paired, qx, qy, last_announce
    if not qx:
        read_key()   # a fresh chip announces its status without a key
    body = {"name": NAME, "backend": sig.name, "chip": sig.status()}
    if qx:
        body["qx"], body["qy"] = qx, qy
    r = requests.post(APP + "/api/device", json=body, timeout=5)
    try:
        paired = bool(r.json().get("paired"))
    finally:
        r.close()
    last_announce = time.ticks_ms()


def fetch_state():
    global info, dirty, _last_bal
    r = requests.get(APP + "/api/state", timeout=8)
    try:
        info = r.json()
    finally:
        r.close()
    global last_fetch
    last_fetch = time.ticks_ms()
    bal = info.get("account", {}).get("balanceFormatted")
    if bal is not None and _last_bal is not None and bal != _last_bal:
        try:
            delta = float(bal) - float(_last_bal)
            say(("+$%.2f" if delta >= 0 else "-$%.2f") % abs(delta), 8)
        except ValueError:
            pass
    if bal is not None:
        _last_bal = bal
    dirty = True


def run_commands():
    r = requests.get(APP + "/api/commands?status=pending", timeout=5)
    try:
        cmds = r.json().get("commands", [])
    finally:
        r.close()
    for c in cmds:
        cid, ctype = c["id"], c["type"]
        _log("command " + ctype)
        try:
            if ctype == "status":
                res = sig.status()
            elif ctype == "genkey":
                x, y = sig.genkey()
                res = {"qx": hex32(x), "qy": hex32(y)}
                global qx, qy
                qx, qy = res["qx"], res["qy"]
            elif ctype == "lock-config":
                res = sig.provision()
            else:
                raise Exception("unknown command " + ctype)
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": True, "result": res}, timeout=5).close()
        except Exception as e:
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": False, "error": str(e)}, timeout=5).close()
        announce()


def check_digest(r):
    """Rebuild the EIP-712 digest from the fields the screen shows. Refuse if it differs."""
    expected_chain = getattr(secrets, "EXPECTED_CHAIN_ID", None)
    expected_vault = getattr(secrets, "EXPECTED_VAULT", None)
    expected_token = getattr(secrets, "EXPECTED_TOKEN", None)
    if expected_chain is not None and int(r["chainId"]) != int(expected_chain):
        return False
    if expected_vault and r["account"].lower() != expected_vault.lower():
        return False
    if r.get("kind") == "transfer" and expected_token and r["token"].lower() != expected_token.lower():
        return False
    if r.get("kind") == "setName":
        mine = eip712.set_name_digest(int(r["chainId"]), r["account"], r["name"], int(r["nonce"]), int(r["deadline"]))
    elif r.get("kind") == "cancelRecovery":
        mine = eip712.cancel_recovery_digest(int(r["chainId"]), r["account"], int(r["nonce"]), int(r["deadline"]))
    elif r.get("kind") == "execute":
        mine = eip712.execute_digest(int(r["chainId"]), r["account"], r["target"], int(r["value"]), bytes.fromhex(r["data"][2:]), int(r["nonce"]), int(r["deadline"]))
    else:
        mine = eip712.transfer_digest(int(r["chainId"]), r["account"], r["token"], r["to"], int(r["amount"]), int(r["nonce"]), int(r["deadline"]))
    return "0x" + "".join("%02x" % b for b in mine) == r["digest"].lower()


def poll_requests():
    global req, state, page, dirty
    r = requests.get(APP + "/api/requests?status=pending", timeout=5)
    try:
        pending = r.json().get("requests", [])
    finally:
        r.close()
    for p in pending:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        if not check_digest(p):
            say("digest mismatch! refused " + p["id"], 10)
            _log("REFUSED %s: app digest does not match the fields" % p["id"])
            return
        req, page, state, dirty = p, 0, "confirm", True
        if p.get("kind") == "setName":
            _log("request %s: set ENS name %s" % (p["id"], p["name"]))
        elif p.get("kind") == "cancelRecovery":
            _log("request %s: cancel recovery" % p["id"])
        elif p.get("kind") == "execute":
            _log("request %s: execute %s on %s" % (p["id"], p["data"][:10], p["target"]))
        else:
            _log("request %s: %s %s to %s" % (p["id"], p["amountFormatted"], p["tokenSymbol"], p.get("toName") or p["to"]))
        return


def approve(yes):
    global state, dirty, msg
    if not yes:
        _log("rejected " + req["id"])
        say("rejected", 3)
        state = "home"; dirty = True
        draw()
        try:
            requests.post(APP + "/api/requests/%s/reject" % req["id"], json={"by": NAME}, timeout=8).close()
        except Exception as e:
            _log("reject post failed: %r" % e)
        return
    state, msg, dirty = "working", "signing on " + sig.name, True
    draw()
    timer.deinit()  # long blocking work ahead; keep the scheduler queue empty
    try:
        digest = bytes.fromhex(req["digest"][2:])
        t0 = time.ticks_ms()
        r_, s_ = sig.sign(digest)
        _log("signed in %d ms" % time.ticks_diff(time.ticks_ms(), t0))
        msg = "relaying..."; draw()
        body = {"r": hex32(r_), "s": hex32(s_), "qx": qx, "qy": qy}
        resp = requests.post(APP + "/api/requests/%s/signature" % req["id"], json=body, timeout=120)
        try:
            out = resp.json()
        finally:
            resp.close()
        if out.get("status") == "confirmed":
            if req.get("kind") == "setName":
                msg = "ENS %s  tx %s" % (req["name"], short(out.get("txHash", "")))
            elif req.get("kind") == "cancelRecovery":
                msg = "recovery cancelled  tx %s" % short(out.get("txHash", ""))
            elif req.get("kind") == "execute":
                msg = "executed %s  tx %s" % (req["data"][:10], short(out.get("txHash", "")))
            else:
                msg = "$%s to %s  tx %s" % (req["amountFormatted"], req.get("toName") or short(req["to"]), short(out.get("txHash", "")))
            state = "done"
        else:
            msg = "%s: %s" % (out.get("status"), out.get("error", ""))[:100]
            state = "error"
    except Exception as e:
        msg, state = "sign/post failed: %r" % e, "error"
    _log(msg)
    dirty = True
    start_timer()


def short_err(e):
    """An app error in the width of one status row: the usual OSErrors by name, the rest as repr."""
    a = getattr(e, "args", ())
    if isinstance(e, OSError) and a and isinstance(a[0], int):
        return {-2: "dns: host not found", 104: "connection reset", 110: "timed out",
                111: "connection refused", 113: "host unreachable"}.get(a[0], "OSError %d" % a[0])
    return repr(e)[:23]


def net_work():
    global state, dirty, last_announce, last_fetch, net_err
    if state in ("confirm", "working", "keys", "nochip") or secrets is None:
        return
    try:
        if not network.WLAN(network.STA_IF).isconnected():
            if time.ticks_diff(time.ticks_ms(), net.last_try) > 30000:
                net.retry()         # returns at once; the radio reports later
                _log("wifi: retrying " + SSID)
            return
        if not net.up:
            net.joined()            # a retry got us here: LED, console if wanted
            _log("wifi up: " + network.WLAN(network.STA_IF).ifconfig()[0])
        now = time.ticks_ms()
        every = 30000 if paired else 5000
        if last_announce == 0 or time.ticks_diff(now, last_announce) > every:
            last_announce = now     # also when it fails: an unreachable app is retried on the cadence, not every second
            announce()
            _log("announced, paired=%s" % paired)
        if last_fetch == 0 or time.ticks_diff(now, last_fetch) > STATE_EVERY_MS:
            fetch_state()
            net_err = ""
            if state == "boot":
                state = "home"; dirty = True
        run_commands()
        if paired:
            poll_requests()
    except Exception as e:
        net_err = short_err(e)
        _log("net: %r" % e)
        say("app: " + net_err, 5)
    gc.collect()


# ----------------------------------------------------------------------------- entry
timer = None


def start_timer():
    global timer
    timer = machine.Timer(period=50, mode=machine.Timer.PERIODIC, callback=tick)


def read_key():
    """qx/qy of the active slot, or empty on a fresh chip. The home screen says "no key" until then."""
    global qx, qy
    try:
        x, y = sig.pubkey()
        qx, qy = hex32(x), hex32(y)
    except Exception as e:
        qx = qy = ""
        _log("no key in slot %s: %r" % (getattr(sig, "slot", 0), e))


def read_chip():
    """Cache sig.status() for the home screen, with the part name and whether the chip is new
    (config open), set up but empty, or holding a key in the active slot."""
    global chip_st
    try:
        st = sig.status()
    except Exception as e:
        st = {"note": str(e)}
    rev = st.get("revision", "")
    st["part"] = {"00006002": "ATECC608A", "00006003": "ATECC608B", "00005000": "ATECC508A"}.get(rev, "ATECC?" if rev else "")
    st["state"] = "new" if not st.get("configLocked") else ("key" if st.get("hasKey") else "empty")
    chip_st = st


def chip_line():
    """One boot-screen row: part, address, and new / no key / key fp."""
    st = chip_st
    if sig.name != "atecc608":
        return "none, software key"
    what = {"new": "new", "empty": "no key", "key": "key " + st.get("fingerprint", "")[:8]}.get(st.get("state"), "?")
    return "%s %s %s" % (st.get("part") or "ATECC", st.get("i2cAddr", ""), what)


def key_changed():
    """The KEYS screen switched or replaced the signing key: announce it again, from scratch."""
    global paired, last_announce
    read_key()
    read_chip()
    paired = False
    last_announce = 0


def probe_chip():
    """Find the signer. No chip and no ALLOW_SOFT_KEY: stop on the NO CHIP screen (A probes again).
    Otherwise read the active key and build the KEYS screen around whichever backend answered."""
    global sig, state, slots_ui
    sig = S.load()
    if sig.name != "atecc608" and not SOFT_OK:
        state = "nochip"
        return
    if state == "nochip":
        state = "boot"
    read_key()
    read_chip()
    slots_ui = SL.SlotsUI(d, sig, key_changed)


def start():
    global d, keys, sig, dirty, slots_ui, splash_until
    d = splash.begin()      # the LCD boot.py already drew on, or a new one
    keys = L.Keys()
    load_qr()
    splash.step("chip", "probing i2c...", L.GREY)
    probe_chip()
    if state == "nochip":
        splash.step("chip", "none on i2c", L.RED)
    else:
        splash.step("chip", chip_line(), L.GREEN if sig.name == "atecc608" else L.RED)
    w = network.WLAN(network.STA_IF)
    if secrets and not w.isconnected() and not net.tried:
        # boot.py already waited on the wallet Pico; a board that got wallet.py by hand, or the emulator, did not
        net.connect(progress=lambda ms: splash.spin("wifi", ("join " + SSID)[:12] + " A skips") or bool(keys.pressed()))
    splash.wifi_row(w, SSID if secrets else "")
    splash.step("app", APP_HOST[:20] if APP_HOST else "none", L.GREY)
    splash_until = time.ticks_add(time.ticks_ms(), 1500)
    dirty = True
    start_timer()


def decide(yes=True):
    """Dev hook from the console: same as pressing A (True) or B (False)."""
    if state == "confirm":
        approve(yes)


def stop():
    timer.deinit()
