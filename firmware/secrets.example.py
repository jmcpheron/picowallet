# Copy to secrets.py (gitignored) and fill in.
WIFI_SSID = "your-ssid"
WIFI_PASS = "your-password"
HOSTNAME = "picowallet"
APP_URL = "http://<mac-lan-ip>:3001"
DEVICE_NAME = "picowallet"
# Provisioning a FRESH chip from the app's Setup page. Both are permanent; leave False otherwise.
ALLOW_LOCK = False     # lock the config zone once (required before the chip will make a key)
ALLOW_GENKEY = False   # make a new key in slot 0, replacing the old one
