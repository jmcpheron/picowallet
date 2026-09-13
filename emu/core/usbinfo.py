# Serial-port helpers for the emulator's device list (pyserial from the mpremote install).
#   usbinfo.py list            JSON: [{port, product, manufacturer, vid, pid, serial}]
#   usbinfo.py touch PORT      1200-baud touch: Arduino-style firmware reboots into the UF2 bootloader
#   usbinfo.py banner PORT     read one second of whatever the board prints
import sys, json, time
import serial
from serial.tools import list_ports

cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
if cmd == "list":
    out = []
    for p in list_ports.comports():
        if p.vid is None:
            continue
        out.append({"port": p.device, "product": p.product, "manufacturer": p.manufacturer, "vid": p.vid, "pid": p.pid, "serial": p.serial_number})
    print(json.dumps(out))
elif cmd == "touch":
    s = serial.Serial(sys.argv[2], 1200)
    s.dtr = False
    s.close()
    print("touched")
elif cmd == "banner":
    s = serial.Serial(sys.argv[2], 115200, timeout=0.2)
    time.sleep(1.0)
    b = s.read(2000)
    s.close()
    print(b.decode("utf8", "replace").strip()[:200])
