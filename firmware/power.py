# Battery and USB state for the perfboard build (SOLDERING.md): an 18650 behind a switch and a
# Schottky diode into VSYS, and a 100k/100k divider from the switched battery side to GP28 so the
# wallet can show the cell voltage. Everything here is optional: with nothing wired, or the switch
# off, GP28 sits between 0 and about 1 V (a floating pin, or the Schottky's reverse leakage from
# VSYS through the divider: 1.08 V measured on the perfboard build with the cell out). Anything
# under NO_CELL counts as no cell and the home screen just shows USB.
#
# Why not read VSYS on the Pico's own ADC3 (GP29)? On the Pico W / Pico 2 W that pin doubles as
# the WiFi chip's SPI clock, and borrowing it while the wallet keeps WiFi up is a gamble. A
# divider on a free ADC pin costs two resistors and a capacitor, and never touches the radio.
from machine import ADC, Pin

SENSE_PIN = 28          # GP28 / ADC2, physical pin 34; free on the Waveshare Pico-LCD-1.3
DIVIDER = 2.0           # (R_top + R_bottom) / R_bottom: 100k over 100k
VREF = 3.3
FULL, EMPTY = 4.15, 3.3     # an 18650 under a light load; the Pico's regulator quits well below 3.0
LOW = 3.45                  # warn here; a few percent left
NO_CELL = 2.5               # below this it is leakage or a floating pin: a protected 18650 cuts off near 2.5 V

_adc = None
_vbus = None


def _init():
    global _adc, _vbus
    if _adc is None:
        _adc = ADC(Pin(SENSE_PIN))
    if _vbus is None:
        # VBUS presence: WL_GPIO2 on the Pico W / Pico 2 W, GP24 on a plain Pico
        for name in ("WL_GPIO2", 24):
            try:
                _vbus = Pin(name, Pin.IN)
                break
            except Exception:
                pass


def vbat():
    """Volts at the divider. Near 0 with nothing wired; up to about 1 V of diode leakage with the
    switch off. percent() and status() treat anything under NO_CELL as no cell."""
    _init()
    try:
        raw = sum(_adc.read_u16() for _ in range(8)) // 8
    except Exception:
        return 0.0
    return raw * VREF / 65535 * DIVIDER


def usb():
    """True when VBUS is present (USB plugged in)."""
    _init()
    try:
        return bool(_vbus.value()) if _vbus else True
    except Exception:
        return True


def percent(v=None):
    v = vbat() if v is None else v
    if v < NO_CELL:
        return None
    return max(0, min(100, int((v - EMPTY) * 100 / (FULL - EMPTY))))


def status():
    v = vbat()
    return {"usb": usb(), "vbat": round(v, 2), "percent": percent(v), "low": NO_CELL <= v < LOW}
