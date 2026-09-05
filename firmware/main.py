# picowallet firmware. boot.py already brought WiFi + console up.
# Start the UI on a timer and return, so the REPL idles and the WiFi console works.
import sys
try:
    import ui
    ui.start()
except Exception as e:
    with open("error.log", "w") as f:
        sys.print_exception(e, f)
    sys.print_exception(e)
