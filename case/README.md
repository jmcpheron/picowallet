# Case

## v0: print this first

`waveshare-13-pico-lcd-case-tomas-plass.stl`, from
[Waveshare Pico 1.3 LCD Case by Tomáš Plass](https://www.printables.com/model/1322102-waveshare-pico-13-lcd-case)
on Printables. License CC BY-NC 4.0 (remix ok, attribution required, no commercial use).

What it is: a two-piece snap-fit box for exactly our stack, Pico plugged into the Pico-LCD-1.3.
Both halves are in the one STL, side by side. Closed box about 60 x 34 x 26 mm.

- Lid: screen window, a slot the four bare A/B/X/Y buttons poke through, a diamond hole the
  joystick stem pokes through. No caps, you press the parts directly. That is the honest state of
  the art for this board: nobody has published floating caps for it.
- End: micro-USB slot (the Pico 2 W is micro-USB, not USB-C).
- Base: four M2 posts for the Pico, optional.
- Print: 0.2 mm layers, no supports (author says a small one under the USB cutout is optional).

Fit risk for us: the ATECC breakout and the four wedged wires live in the 11 mm gap between the
boards, inside the box footprint, so they should be fine. The wires leave the header at the USB end
and bend into the gap; keep them flat. Print it and see.

## v1: our own

Generate from Python (like the CELL parts) so it re-fits when parts change. Wants:
- floating caps for A/B/X/Y and a joystick hat, captured by the lid
- pocket for the ATECC breakout and a 502030 LiPo + charger
- USB cutout, maybe a lanyard hole

Board facts for that: Pico-LCD-1.3 is 52.0 x 26.5 mm, display 23.4 x 23.4 mm active. Waveshare
wiki: https://www.waveshare.com/wiki/Pico-LCD-1.3. A CAD model of the board exists on GrabCAD:
https://grabcad.com/library/waveshare-1-3-inch-lcd-for-pico-65k-240x240-1. Button and joystick
centers still need measuring with calipers.

Print inbox drop 2026-09-05: `20260905-193939-waveshare-13-pico-lcd-case-tomas-plass` (PLA, black, 0.20 mm).

## Buttons and joystick: research (2026-09-05)

Nobody has published caps for the Pico-LCD-1.3. But its Pi HAT twin (Waveshare 1.3inch LCD HAT,
same 240x240 panel, same 5-way joystick, same tact switches, 3 buttons instead of 4) is the
SeedSigner bitcoin wallet's screen, and that project has years of open enclosures with printed caps:

- SeedSigner enclosures, MIT: https://github.com/SeedSigner/seedsigner/tree/dev/enclosures
  Copies of the parts that matter are in `reference/seedsigner/`:
  - `orange_pill_button.stl` 11.7 x 4.7 x 4.8 mm, `orange_pill_joystick.stl` 13 x 13 x 10 mm.
    Author says the thumbstick is clumsy and wants resin.
  - `open_pill_mini_w_coverplate_Buttons.stl` (three caps on a sprue, 20 mm tall), `Thumbstick_PLA`
    and `Thumbstick_TPU` (11.8 x 11.8 x 5.6 mm). FDM-only, TPU for the controls, no hardware.
- revetuzo's Open Pill caps, CC BY-SA: https://www.printables.com/model/179924
  Sticks and pads in 12/14/15 mm with a 2.05 mm square socket, "fits the 2 mm stick on the
  Waveshare HAT". Plus a glue-on button.
- Crackedconsole's HAT case with 3 buttons + joystick cap v2, Sketchup source:
  https://www.thingiverse.com/thing:3334127. Note: 0.1 mm more clearance per button was too loose.
- Adafruit 4697 rubber nubbin cap, $0.50, fits the classic 5-way nav stem. Zero-effort option.
- The joystick family: ALPS SKQU (10 mm square, 4-way + center push). Datasheet: SMD center-push
  type is 8.6 mm tall overall, stem 3.2 mm square, 2.8 mm above the housing, travel 0.4 mm tilt /
  0.2 mm push, 1.57 N tilt / 3.14 N push. Waveshare's part is a clone; SeedSigner people measure
  the stem at 2 mm square, so measure ours.
- General cap design: https://www.printables.com/model/236991 (tact cap with assembly template),
  https://www.thingiverse.com/thing:1557650, Apple's button patents. Same idea every time.

## How we will do it

Caps are loose parts trapped between the lid and the board. Nothing glued, nothing on the board.

```
        cap top (visible, any color)          ___
   lid  ======|   |======   <- hole in lid   |   |  lid hole = cap body + 0.25 mm/side
   flange  ___|   |___      <- wider than    |___|  flange 1.0 mm out, 1.0 mm thick
   post       |___|         the hole         | | |  post lands on the tact plunger
   board  ----[tact]----
```

- A/B/X/Y caps: round or square top 6 mm, flange 8 mm, post the size of the plunger. Cap body
  height = lid thickness + stand-off so the flange sits 0.3 mm above the plunger at rest, and
  bottoms on the lid underside just after the click (over-travel stop).
- Joystick hat: a 12 mm dome with a square socket that press-fits the stem (start at stem + 0.05 mm,
  like revetuzo's 2.05 mm), flange under a 13 mm lid hole so it can tilt 0.4 mm each way. A ring on
  the lid underside keeps it from lifting off. TPU hat is the comfy version.
- Lid holes get a 0.5 mm skirt under them so caps can't rock.
- Print caps top-face down on a textured plate for a clean face. Any color per cap.
- Generator: Python (CadQuery or OpenSCAD), parameters = the caliper numbers below.

Numbers we need from calipers, with the stack assembled:
1. Tact switch: plunger diameter, plunger height above the LCD PCB, switch body size (6x6?).
2. Joystick: stem width (square?), stem height above the metal housing, housing size, housing height
   above the PCB.
3. Height from LCD PCB top to the top of the screen glass.
4. Centers (x, y in mm): joystick + 4 buttons, measured from the PCB corner at the USB end
   (or a straight-down photo with a ruler in it).
5. The v0 case lid thickness at the button slot, once printed.
