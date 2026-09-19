# WiFi plus an optional network console for isolated development.
# The console is passwordless arbitrary code execution and must remain disabled when holding value.
import network, socket, os, time
from machine import Pin
try:
    import secrets
except ImportError:
    secrets = None      # a board without secrets.py: no WiFi, no console; wallet.py says so on screen

led = Pin("LED", Pin.OUT)
PORT = 2323
_listen = None
tried = False       # connect() ran once (boot.py); wallet.start does not wait a second time
last_try = 0        # ticks_ms of the last join attempt; wallet.net_work retries every 30 s without blocking
up = False          # joined() ran: LED on, console started if wanted


def connect(timeout_s=12, progress=None):
    """Join the WiFi in secrets.py, waiting at most timeout_s. progress(elapsed_ms), if given, is called
    while waiting (the boot screen animates on it) and may return True to stop waiting (a key press);
    the LED blinks either way. A network that is not there costs 12 s once, never more: the wallet
    retries in the background (retry) and everything local works without it."""
    global tried, last_try
    tried = True
    last_try = time.ticks_ms()
    wlan = network.WLAN(network.STA_IF)
    if secrets is None:
        print("no secrets.py: not joining WiFi")
        return wlan
    network.hostname(secrets.HOSTNAME)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        t0 = time.ticks_ms()
        while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < timeout_s * 1000:
            led.toggle()
            if progress:
                try:
                    if progress(time.ticks_diff(time.ticks_ms(), t0)):
                        print("wifi: wait skipped")
                        break
                except Exception:
                    pass
            time.sleep_ms(150)
    if wlan.isconnected():
        led.on()
        print("wifi up:", wlan.ifconfig()[0], "hostname:", secrets.HOSTNAME)
    else:
        led.off()
        print("wifi failed, status", wlan.status())
    return wlan


def retry():
    """Ask the radio to join again and return at once; isconnected() says later whether it did."""
    global last_try, up
    last_try = time.ticks_ms()
    up = False
    if secrets is None:
        return
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        try:
            wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        except OSError as e:
            print("wifi retry:", e)


def joined():
    """Call once the network is up (boot, or a later retry): LED on, the console if secrets.py wants it."""
    global up
    up = True
    led.on()
    if _listen is None and getattr(secrets, "ENABLE_NETWORK_CONSOLE", False):
        console()


def _accept(ls):
    try:
        conn, addr = ls.accept()
    except OSError:
        return  # nothing pending (non-blocking listen socket)
    print("console from", addr)
    conn.setblocking(False)
    os.dupterm(conn, 0)


def poll_accept():
    """Call from a timer tick. The socket-accept callback needs a free scheduler slot, which a busy
    timer can starve; polling here means a connection can never get stuck in the backlog."""
    if _listen:
        _accept(_listen)


def console(port=PORT):
    global _listen
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(socket.getaddrinfo("0.0.0.0", port)[0][-1])
    s.listen(2)
    s.setblocking(False)
    s.setsockopt(socket.SOL_SOCKET, 20, _accept)  # 20 = register accept callback
    _listen = s
    print("console listening on", port)


def start(progress=None):
    wlan = connect(progress=progress)
    if wlan.isconnected():
        joined()
        if _listen is None:
            print("network console disabled")
    return wlan
