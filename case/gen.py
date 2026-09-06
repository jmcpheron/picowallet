"""picowallet case parts, parametric. Run: uv run --python 3.11 --with cadquery python case/gen.py

v1: loose caps for the four A/B/X/Y tact switches and a joystick dome, sized for the v0 lid
(Tomáš Plass): 2.0 mm plate, one 4.5 x 21 mm slot for the buttons, 7.1 mm rotated-square hole for
the joystick. Caps drop into the slot from inside the lid; a flange wider than the slot keeps them
in; a pocket on the underside slips over the switch plunger.

All dimensions mm. Names ending in _GUESS are placeholders until measured (see BUTTONS.md).
"""
import cadquery as cq

# --- measured / from the v0 lid STL ---------------------------------------------------------
LID_T = 2.0            # lid plate thickness
SLOT_W = 4.5           # button slot width (across)
PITCH = 5.17           # button center to center
SWITCH_BODY = 4.5      # tact switch body, square
PLUNGER_D = 2.04       # round plunger diameter (Austin's 2.04 reading, to confirm)

# --- to confirm with the depth rod ------------------------------------------------------------
PLUNGER_BELOW_LID_GUESS = 0.6   # lid outer face down to plunger top
SWITCH_TOP_BELOW_LID_GUESS = 1.4  # lid outer face down to the switch body top (flange lives here)
STEM_W_GUESS = 2.0              # joystick stem across flats (square)
STEM_ABOVE_LID_GUESS = 1.5      # stem top above the lid outer face

# --- design choices ---------------------------------------------------------------------------
CLEAR = 0.15           # radial clearance cap body to slot wall
CAP_ACROSS = SLOT_W - 2 * CLEAR          # 4.2
CAP_ALONG = PITCH - 0.75                 # 4.42, leaves 0.75 between neighbours
CAP_PROUD = 1.2        # how far the cap top stands above the lid face
FLANGE_OUT = 1.0       # flange beyond the body on each side, across only (along has no room)
REST_GAP = 0.3         # flange top to lid underside at rest, = click travel before it bottoms
TOP_R = 0.6            # edge round on the cap top


def cap(clear=CLEAR, plunger_below=PLUNGER_BELOW_LID_GUESS, switch_top_below=SWITCH_TOP_BELOW_LID_GUESS):
    across = SLOT_W - 2 * clear
    body_h = LID_T + CAP_PROUD                       # part that lives in the slot + stands proud
    # space under the lid before the switch body: that is all the flange can have
    flange_t = max(0.6, switch_top_below - LID_T - REST_GAP)
    total_h = CAP_PROUD + plunger_below + 0.4        # 0.4 mm of pocket depth over the plunger top
    body = cq.Workplane("XY").box(across, CAP_ALONG, body_h, centered=(True, True, False)).translate((0, 0, total_h - body_h))
    body = body.edges(">Z").fillet(TOP_R)
    flange = cq.Workplane("XY").box(across + 2 * FLANGE_OUT, CAP_ALONG, flange_t, centered=(True, True, False)).translate((0, 0, total_h - body_h - flange_t))
    part = body.union(flange)
    # fill down to z=0 under the flange so the pocket has walls, then cut the pocket
    stub_h = total_h - body_h - flange_t
    if stub_h > 0.05:
        part = part.union(cq.Workplane("XY").box(across, CAP_ALONG, stub_h + 0.01, centered=(True, True, False)))
    pocket_d = PLUNGER_D + 0.25
    pocket_depth = plunger_below + 0.4 - (LID_T - REST_GAP) + 0.0  # reaches to just under the lid plate line
    pocket_depth = max(0.5, min(pocket_depth, total_h - 1.0))
    part = part.cut(cq.Workplane("XY").circle(pocket_d / 2).extrude(pocket_depth))
    return part


def joystick_dome(stem_w=STEM_W_GUESS, stem_above=STEM_ABOVE_LID_GUESS, hole_d=9.0):
    """Dome that press-fits the stem. Flange under a round hole so it can tilt. Print in TPU or PLA."""
    dome_d = 9.5
    h = stem_above + 2.5
    dome = cq.Workplane("XY").circle(dome_d / 2).extrude(h).faces(">Z").edges().fillet(2.0)
    flange = cq.Workplane("XY").circle(hole_d / 2 + 1.2).extrude(0.8).translate((0, 0, -0.8))
    part = dome.union(flange)
    socket = cq.Workplane("XY").rect(stem_w + 0.08, stem_w + 0.08).extrude(stem_above + 1.2).translate((0, 0, -0.8))
    return part.cut(socket)


def export(shape, name):
    cq.exporters.export(shape, f"case/out/{name}.stl")
    bb = shape.val().BoundingBox()
    print(f"{name}.stl  {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm")


if __name__ == "__main__":
    # caps in two clearances, four of each on one plate, flange down (top face up: print it upside
    # down? no: flange is wider than the body, so print flange DOWN, top up; bridge-free)
    for clear in (0.15, 0.25):
        plate = cq.Workplane("XY")
        parts = None
        for i in range(4):
            c = cap(clear=clear).translate((i * 8.0, 0, 0))
            parts = c if parts is None else parts.union(c)
        export(parts, f"caps_x4_clear{clear:.2f}")
    export(joystick_dome(), "joystick_dome")
