# One palette for the wallet's chip screens: a deep background, an identity colour per zone of
# the chip (used for header tints, icons, tiles and captions), and the three action classes.
# Colours are kept as RGB triples so shades and gradients can be computed; lcd.color turns them
# into the panel's byte-swapped RGB565.
import lcd as L

RGB = {
    "bg": (6, 10, 26), "navy": (14, 26, 70), "panel": (20, 30, 58), "ink": (34, 42, 70),
    "chip": (200, 210, 230),
    "config": (70, 140, 255), "data": (40, 210, 160), "otp": (255, 150, 40), "counters": (180, 110, 255),
    "lab": (255, 90, 160), "learn": (255, 200, 60),
    "safe": (0, 220, 90), "rev": (255, 200, 0), "perm": (255, 40, 40),
    "lost": (90, 230, 255),     # the one thing a permanent action erases or seals: the only non-red on the red screen
    "white": (255, 255, 255), "grey": (120, 120, 120), "dim": (90, 90, 100),
}
C = {name: L.color(*rgb) for name, rgb in RGB.items()}
# which identity a screen belongs to (chipmap.header tints the bar with it)
ZONE = {"zones": "chip", "cfg": "config", "raw": "config", "diff": "config", "confirm_write": "config",
        "list": "data", "slot": "data", "pubkey": "data", "pubqr": "data", "otp": "otp", "counters": "counters",
        "lab": "lab", "labres": "lab", "why": "lab", "rawcmd": "lab", "snake": "lab", "learn": "learn", "card": "learn",
        "refused": "perm", "confirm": "perm", "result": "safe", "busy": "chip"}
RAINBOW = ("config", "data", "learn", "otp", "perm", "lab", "counters")   # the boot screen's leg chase


def shade(name, f):
    """The zone colour scaled by f (0 dark .. 1 full)."""
    r, g, b = RGB[name]
    return L.color(int(r * f), int(g * f), int(b * f))


def mix(a, b, t):
    """Between two RGB triples, t in 0..1."""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(d, y0, y1, a, b, band=8):
    """Horizontal bands from triple a at y0 to b at y1."""
    n = max(1, (y1 - y0) // band)
    for i in range(n):
        d.fill_rect(0, y0 + i * band, 240, band, L.color(*mix(a, b, i / max(1, n - 1))))


def zone_of(view):
    return ZONE.get(view, "chip")
