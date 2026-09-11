# emu: the virtual Pico wallet

Real MicroPython (the WebAssembly build of 1.26, the board runs 1.26.1) running the firmware in
`firmware/` unchanged, with the `machine`/`network`/`requests` modules replaced by shims that talk
to the page. The screen is captured from the ST7789 SPI stream, so what you see is the exact
framebuffer. The device is drawn in 3D from the case STLs in `case/zez0000/`.

```
tools/emu                 # start the server, open http://localhost:4242
tools/emu run hello       # reboot + import emu/sketches/hello.py
tools/emu key A           # press a button (A B X Y up down left right press), key right:300 holds
tools/emu shot            # emu/shots/latest.png
tools/emu exec 'mock.goto("send")'
tools/emu log             # console lines
tools/emu headless mock --wait 300 --key right --shot emu/shots/x.png    # no browser
```

Page: left = files, editor (Cmd/Ctrl+Enter runs the open file), console with a REPL; right = the
device (orbit with the mouse, click the caps) or the flat view. Keyboard: arrows and Enter for
the joystick, a/b/x/y for the buttons, after clicking the device. `main` picks what boots on reset.

The flash is `firmware/*.py` and `*.bin` (never `secrets.py`; a stub is generated with
`APP_URL = "/app"`, which the server proxies to the wallet app, `--app http://host:port`,
default `http://localhost:3001`) plus `emu/sketches/*` on top. Saving in the editor writes to disk.

`tools/emu run` and `--wait/--key/--shot` steps make the bot loop: see `SKILL.md`, also linked
from `.claude/skills/pico-emu`.

What is modeled: pins (keys pull low when pressed), SPI display window commands, the SPI transfer
time (24 MHz cap until `machine.freq(cpu, peri)` raises the peripheral clock, like rp2), PWM
backlight, `Pin("LED")` (the base glows), `Timer` periodic/one-shot, `Pin.irq`, `machine.reset()`,
a 448 KB heap. Not modeled: I2C (the ATECC608 is absent, the software signer is used), sockets,
PIO, native/viper code generation (runs as bytecode), real timing of Python itself (wasm is much
faster than the RP2350).

Needs node 18+ and `npm install` in `emu/` (done by `tools/emu` on first run). No build step.
