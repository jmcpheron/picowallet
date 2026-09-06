# picowallet: the loop. Talks to the app, shows what is being asked, signs only on a button press.
#
# Two timers, both scheduled (soft) callbacks so main.py can return to the REPL and the WiFi
# console keeps working:
#   ui tick   30 ms   keys + redraw
#   net tick  1 s     announce / poll commands / poll requests / post signatures
# While a request is on screen waiting for A or B, the net tick does nothing, so no button press
# gets lost inside a blocking HTTP call.
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
last_announce = 0
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


def draw_home():
    d.fill(L.BLACK)
    d.fill_rect(0, 0, 240, 26, L.DARK)
    d.text(NAME, 6, 9, L.YELLOW)
    d.text(sig.name if sig else "", 240 - 8 * len(sig.name if sig else "") - 6, 9, L.GREY)
    bal = info.get("account", {}).get("balanceFormatted")
    if bal is None:
        d.center_text("connecting...", 100, L.GREY)
    else:
        whole, _, frac = bal.partition(".")
        s = "$" + whole + "." + (frac + "00")[:2]
        d.center_text(s, 84, L.WHITE, 4 if len(s) <= 7 else 3)
        d.center_text(info.get("token", {}).get("symbol", ""), 128, L.GREY)
        acct = info.get("account", {}).get("address", "")
        d.center_text(short(acct), 150, L.GREY)
    st = "paired" if paired else ("not paired" if qx else "no key")
    d.center_text(st, 180, L.GREEN if paired else L.RED)
    if time.ticks_diff(msg_until, time.ticks_ms()) > 0:
        d.center_text(msg[:30], 214, L.YELLOW)
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
def ui_tick(t):
    global dirty, page, state, _busy
    if _busy:
        return
    _busy = True
    try:
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
    r = requests.post(APP + "/api/device", json=body, timeout=10)
    try:
        paired = bool(r.json().get("paired"))
    finally:
        r.close()
    last_announce = time.ticks_ms()


def fetch_state():
    global info, dirty
    r = requests.get(APP + "/api/state", timeout=10)
    try:
        info = r.json()
    finally:
        r.close()
    dirty = True


def run_commands():
    r = requests.get(APP + "/api/commands?status=pending", timeout=10)
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
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": True, "result": res}, timeout=10).close()
        except Exception as e:
            requests.post(APP + "/api/commands/%s/result" % cid, json={"ok": False, "error": str(e)}, timeout=10).close()
        announce()


def check_digest(r):
    """Rebuild the EIP-712 digest from the fields the screen shows. Refuse if it differs."""
    mine = eip712.transfer_digest(int(r["chainId"]), r["account"], r["token"], r["to"], int(r["amount"]), int(r["nonce"]), int(r["deadline"]))
    return "0x" + "".join("%02x" % b for b in mine) == r["digest"].lower()


def poll_requests():
    global req, state, page, dirty
    r = requests.get(APP + "/api/requests?status=pending", timeout=10)
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


def net_tick(t):
    global state, _busy, dirty
    if _busy or state in ("confirm", "working"):
        return
    _busy = True
    try:
        if not network.WLAN(network.STA_IF).isconnected():
            return
        if time.ticks_diff(time.ticks_ms(), last_announce) > 30000:
            announce()
            fetch_state()
            if state == "boot":
                state = "home"; dirty = True
        run_commands()
        if paired:
            poll_requests()
        elif time.ticks_diff(time.ticks_ms(), last_announce) > 5000:
            announce()
    except Exception as e:
        _log("net: %r" % e)
        say("net: %r" % e, 5)
    finally:
        _busy = False
        gc.collect()


# ----------------------------------------------------------------------------- entry
def start():
    global d, keys, sig, ui_timer, net_timer, dirty
    d = L.LCD()
    keys = L.Keys()
    draw()
    sig = S.load()
    dirty = True
    ui_timer = machine.Timer(period=30, mode=machine.Timer.PERIODIC, callback=ui_tick)
    net_timer = machine.Timer(period=1000, mode=machine.Timer.PERIODIC, callback=net_tick)


def decide(yes=True):
    """Dev hook from the console: same as pressing A (True) or B (False)."""
    if state == "confirm":
        approve(yes)


def stop():
    ui_timer.deinit(); net_timer.deinit()
