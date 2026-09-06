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
