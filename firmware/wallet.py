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
import eip712
import signer as S
import secrets

APP = secrets.APP_URL
NAME = getattr(secrets, "DEVICE_NAME", "picowallet")

d = None
keys = None
sig = None          # the signer backend
state = "boot"      # boot | home | confirm | working | done | error
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
    acct = info.get("account", {}).get("address", "")
    bal = info.get("account", {}).get("balanceFormatted")
    if bal is None:
        d.center_text("connecting...", 8, L.GREY, 2)
    else:
        whole, _, frac = bal.partition(".")
        s = "$" + whole + "." + (frac + "00")[:2]
        d.center_text(s, 4, L.WHITE, 3 if len(s) <= 9 else 2)
    if _qr and acct and _qr[0].lower() == acct.lower():
        box = draw_qr(34, 6)   # 29 modules * 6 + 16 = 190 px
        d.center_text(acct[:21], 34 + box + 4, L.GREY)
        d.center_text(acct[21:], 34 + box + 14, L.GREY)
    else:
        d.center_text(short(acct) if acct else "", 120, L.GREY)
        d.center_text("run tools/qr", 140, L.RED)
    if time.ticks_diff(msg_until, time.ticks_ms()) > 0:
        d.fill_rect(0, 224, 240, 16, L.DARK)
        d.center_text(msg[:30], 228, L.YELLOW)
    elif not paired:
        d.fill_rect(0, 224, 240, 16, L.DARK)
        d.center_text("not paired" if qx else "no key", 228, L.RED)
    d.show()


def draw_confirm():
    d.fill(L.BLACK)
    d.fill_rect(0, 0, 240, 26, L.RED)
    d.center_text("SIGN?", 5, L.WHITE, 2)
    if page == 0:
        amt = "$" + req["amountFormatted"]
        d.center_text(amt, 44, L.WHITE, 4 if len(amt) <= 7 else 3)
        d.center_text(req["tokenSymbol"], 84, L.GREY)
        d.center_text("to", 108, L.GREY)
        name = req.get("toName") or short(req["to"])
        d.center_text(name[:14], 128, L.YELLOW, 2)
        d.center_text(short(req["to"]), 152, L.GREY)
        d.center_text("A = sign   B = reject", 190, L.WHITE)
        d.center_text("down: details", 210, L.GREY)
    else:
        y = 34
        for line in (
            "to " + req["to"][:22], "   " + req["to"][22:],
            "amount " + req["amount"],
            "nonce %s  chain %s" % (req["nonce"], req["chainId"]),
            "deadline " + str(req["deadline"]),
            "vault " + short(req["account"]),
            "digest (checked on device)",
            req["digest"][2:34], req["digest"][34:],
        ):
            d.text(line[:30], 4, y, L.WHITE if not line.startswith("digest") else L.GREEN)
            y += 14
        d.center_text("A = sign   B = reject", 190, L.WHITE)
        d.center_text("up: summary", 210, L.GREY)
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


def draw():
    if state in ("boot", "home"):
        draw_home()
    elif state == "confirm":
        draw_confirm()
    elif state == "working":
        draw_msg("SIGNING", L.BLUE)
    elif state == "done":
        draw_msg("SENT", L.GREEN)
    elif state == "error":
        draw_msg("ERROR", L.RED)


# ----------------------------------------------------------------------------- ui tick
_n = 0


def tick(t):
    global dirty, page, state, _busy, _n
    if _busy:
        return
    _busy = True
    try:
        _n += 1
        if _n % 20 == 0:
            net_work()
        for k in keys.pressed():
            if state == "confirm":
                if k == "A":
                    approve(True)
                elif k == "B":
                    approve(False)
                elif k == "down":
                    page = 1; dirty = True
                elif k == "up":
                    page = 0; dirty = True
            elif state in ("done", "error") and k == "A":
                state = "home"; dirty = True
        if state == "home" and time.ticks_diff(msg_until, time.ticks_ms()) > 0:
            dirty = True  # keep the status line fresh
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
        x, y = sig.pubkey()
        qx, qy = hex32(x), hex32(y)
    body = {"name": NAME, "backend": sig.name, "chip": sig.status(), "qx": qx, "qy": qy}
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
                raise Exception("lock-config is not done from the wallet")
            else:
                raise Exception("unknown command " + ctype)
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": True, "result": res}, timeout=5).close()
        except Exception as e:
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": False, "error": str(e)}, timeout=5).close()
        announce()


def check_digest(r):
    """Rebuild the EIP-712 digest from the fields the screen shows. Refuse if it differs."""
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
        _log("request %s: %s %s to %s" % (p["id"], p["amountFormatted"], p["tokenSymbol"], p.get("toName") or p["to"]))
        return


def approve(yes):
    global state, dirty, msg
    if not yes:
        _log("rejected " + req["id"])
        say("rejected", 3)
        state = "home"; dirty = True
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


def net_work():
    global state, dirty, last_announce, last_fetch
    if state in ("confirm", "working"):
        return
    try:
        if not network.WLAN(network.STA_IF).isconnected():
            return
        now = time.ticks_ms()
        every = 30000 if paired else 5000
        if last_announce == 0 or time.ticks_diff(now, last_announce) > every:
            announce()
            _log("announced, paired=%s" % paired)
        if last_fetch == 0 or time.ticks_diff(now, last_fetch) > STATE_EVERY_MS:
            fetch_state()
            if state == "boot":
                state = "home"; dirty = True
        run_commands()
        if paired:
            poll_requests()
    except Exception as e:
        _log("net: %r" % e)
        say("net: %r" % e, 5)
    gc.collect()


# ----------------------------------------------------------------------------- entry
timer = None


def start_timer():
    global timer
    timer = machine.Timer(period=50, mode=machine.Timer.PERIODIC, callback=tick)


def start():
    global d, keys, sig, dirty
    d = L.LCD()
    keys = L.Keys()
    load_qr()
    draw()
    sig = S.load()
    dirty = True
    start_timer()


def decide(yes=True):
    """Dev hook from the console: same as pressing A (True) or B (False)."""
    if state == "confirm":
        approve(yes)


def stop():
    timer.deinit()
