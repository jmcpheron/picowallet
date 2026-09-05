# Runs before main.py. WiFi + console first so a broken main.py can still be fixed remotely.
import net
wlan = net.start()
