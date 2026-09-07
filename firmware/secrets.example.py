# Copy to secrets.py (gitignored) and fill in.
WIFI_SSID = "your-ssid"
WIFI_PASS = "your-password"
HOSTNAME = "picowallet"
APP_URL = "http://<mac-lan-ip>:3001"
DEVICE_NAME = "picowallet"

# Passwordless MicroPython REPL on TCP/2323. Full signer control: isolated development only.
ENABLE_NETWORK_CONSOLE = False

# Production forks: pin all three after deploying. None keeps the PoC development workflow flexible.
EXPECTED_CHAIN_ID = None
EXPECTED_VAULT = None
EXPECTED_TOKEN = None
# Provisioning a FRESH chip from the app's Setup page. Both are permanent; leave False otherwise.
ALLOW_LOCK = False     # lock the config zone once (required before the chip will make a key)
ALLOW_GENKEY = False   # make a new key in slot 0, replacing the old one
