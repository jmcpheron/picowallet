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
