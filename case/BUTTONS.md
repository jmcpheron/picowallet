# Next: printed buttons and a joystick hat

Goal: no bare board parts showing. Four colored caps and a joystick dome, loose parts trapped
under the lid, pressing the board's own switches. Nothing glued to the board.

Why it works: a cap is a top + a flange wider than the lid hole + a post that lands on the switch.
The flange bottoms on the lid just after the click, so the switch can't be crushed. The joystick
dome press-fits the stem and its flange sits under a slightly larger hole so it can tilt 0.4 mm.

Prior art we copy from (details in README.md): SeedSigner Open Pill Mini caps and thumbstick (MIT,
copies in `reference/seedsigner/`), revetuzo's 2.05 mm socket sticks, ALPS SKQU datasheet.

Plan:
1. Calipers on the assembled stack (list in README.md, "Numbers we need").
2. `case/gen.py` (CadQuery): lid with holes + skirts, 4 caps, joystick dome, all parametric.
3. Print caps first, alone, in two clearances (+0.20 / +0.30 mm). Pick the one that drops in and
   doesn't rock. Same for the dome socket (+0.05 / +0.10 mm).
4. Print the lid, assemble, click test, adjust flange-to-plunger gap.
5. Then the full v1 case: pocket for ATECC + battery, USB slot, lanyard hole.

Numbers to bring back from the calipers:
- tact plunger diameter and height above the LCD PCB
- joystick stem width, stem height above its housing, housing height above the PCB
- PCB top to screen glass top
- centers of joystick and 4 buttons from the PCB corner at the USB end
- v0 lid thickness at the button slot
