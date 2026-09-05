# picowallet build log

## 2026-09-05 — parts on the bench

Three parts, all from Amazon. Pico plugs face-down into the LCD board's female header. The ATECC608 breakout fits in the ~11 mm gap between them.

![stack end-on, ATECC wedged inside](images/2026-09-05-01-stack-end-atecc-inside.jpg)
![stack end-on 2](images/2026-09-05-02-stack-end-2.jpg)
![stack side](images/2026-09-05-03-stack-side.jpg)
![Pico-LCD-1.3 top: joystick, screen, A/B/X/Y](images/2026-09-05-04-pico-lcd-1.3-top.jpg)
![Pico 2 W](images/2026-09-05-05-pico-2-w.jpg)

Decisions today:
- Screen and buttons work out of the box through the header. Only the ATECC and the battery need wires.
- ATECC gets 4 soldered wires to the Pico (3V3, GND, GP4 SDA, GP5 SCL). The LCD board eats every pin, no pass-through, so no jumper trick.
- Battery: solder it too, keep it in the gap.
- WiFi/Bluetooth stay on for v1. Idea: send a tx to the device over the radio, it shows it on screen, you approve, it sends the signature back.

## 2026-09-05 — first boot

Pico 2 W plugged into the omen box (Arch laptop, `ssh austin@omen.local`). Blank Pico shows up as a USB drive `RP2350`, no LED, no other sign of life. That's normal.

- Flashed MicroPython v1.26.1 (`RPI_PICO2_W-20250911-v1.26.1.uf2`) by copying it onto the `RP2350` drive.
- Board reboots as `/dev/ttyACM0`. `mpremote` installed on omen via pipx. Added `austin` to `uucp` group for serial access.
- `firmware/main.py` blinks the onboard LED. First light.

Workflow from the Mac: `scp` a file to omen, then `mpremote connect /dev/ttyACM0 cp file :file` and `mpremote reset`.
