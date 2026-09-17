# Runs before main.py: the boot screen, then WiFi and, if secrets.py enables it, the development
# console (passwordless; off by default). The screen is best effort: WiFi comes up without it.
import net
try:
    import splash
    splash.begin()
    _ssid = getattr(net.secrets, "WIFI_SSID", "") if net.secrets else ""
    _spin = lambda ms: splash.spin("wifi", ("joining " + _ssid)[:20] if _ssid else "no secrets.py")
except Exception as e:
    print("boot screen:", e)
    splash = _spin = None
wlan = net.start(progress=_spin)
if splash:
    splash.wifi_row(wlan, _ssid)
