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
SWITCH_TOP_BELOW_LID_GUESS = 3.0  # lid outer face down to the switch body top (flange lives here). If this is under 2.7 there is no room for a flange and the caps become press-fit keycaps instead.
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


def cap(clear=CLEAR, plunger_below=PLUNGER_BELOW_LID_GUESS, switch_top_below=SWITCH_TOP_BELOW_LID_GUESS, verbose=False):
    """Vertical frame: z = 0 at the lid OUTER face, up is +. Lid underside at -LID_T, plunger top at
    -plunger_below, switch body top at -switch_top_below. Returned part is shifted so its lowest
    point is z = 0 (print flange down)."""
    across = SLOT_W - 2 * clear
    top_z = CAP_PROUD
    flange_top = -LID_T - REST_GAP
    flange_bot = max(-switch_top_below + 0.1, flange_top - 1.0)     # never touch the switch body
    flange_t = flange_top - flange_bot
    assert flange_t >= 0.4, "no room for a flange under the lid: measure again or thin the lid"
    body = cq.Workplane("XY").box(across, CAP_ALONG, top_z - flange_top, centered=(True, True, False)).translate((0, 0, flange_top))
    body = body.edges(">Z").fillet(TOP_R)
    flange = cq.Workplane("XY").box(across + 2 * FLANGE_OUT, CAP_ALONG, flange_t, centered=(True, True, False)).translate((0, 0, flange_bot))
    part = body.union(flange)
    plunger_top = -plunger_below
    if plunger_top > flange_bot + 0.2:
        # plunger reaches up into the cap: pocket from the bottom up to the plunger top
        pocket_d = PLUNGER_D + 0.25
        depth = plunger_top - flange_bot
        part = part.cut(cq.Workplane("XY").circle(pocket_d / 2).extrude(depth + 0.01).translate((0, 0, flange_bot - 0.01)))
        mode = "pocket %.2f deep" % depth
        low = flange_bot
    else:
        # cap bottom is above the plunger: a post reaches down to it
        post_h = flange_bot - plunger_top
        part = part.union(cq.Workplane("XY").circle((PLUNGER_D + 0.6) / 2).extrude(post_h + 0.01).translate((0, 0, plunger_top)))
        mode = "post %.2f long" % post_h
        low = plunger_top
    if verbose:
        print("cap: across %.2f along %.2f, proud %.2f, flange %.2f thick at %.2f..%.2f below lid face, %s, total %.2f" % (
            across, CAP_ALONG, CAP_PROUD, flange_t, -flange_top, -flange_bot, mode, top_z - low))
    return part.translate((0, 0, -low))


def keycap(pocket_d=1.95, proud=1.5, plunger_below=0.25, skirt=0.6):
    """For the v0 lid, where the plungers sit flush with the lid face and the switch bodies are
    inside the slot: no room for a flange, so the cap press-fits onto the 2.04 mm plunger and the
    slot walls guide it. A dot of glue if the fit is loose. Print pocket-side down."""
    across = SLOT_W - 2 * CLEAR
    h = proud + plunger_below + skirt
    part = cq.Workplane("XY").box(across, CAP_ALONG, h, centered=(True, True, False))
    part = part.edges(">Z").fillet(TOP_R)
    part = part.cut(cq.Workplane("XY").circle(pocket_d / 2).extrude(plunger_below + skirt + 0.2 - 0.0).translate((0, 0, -0.01)))
    return part


def joystick_dome(stem_w=STEM_W_GUESS, stem_above=STEM_ABOVE_LID_GUESS, hole_d=9.0):
    """Dome that press-fits the stem. Flange under a round hole so it can tilt. Print in TPU or PLA."""
    dome_d = 9.5
    h = stem_above + 2.5
    dome = cq.Workplane("XY").circle(dome_d / 2).extrude(h).faces(">Z").edges().fillet(2.0)
    part = dome
    if hole_d:
        flange = cq.Workplane("XY").circle(hole_d / 2 + 1.2).extrude(0.8).translate((0, 0, -0.8))
        part = dome.union(flange)
    socket = cq.Workplane("XY").rect(stem_w + 0.08, stem_w + 0.08).extrude(stem_above + 1.2).translate((0, 0, -0.81))
    return part.cut(socket)


def export(shape, name):
    cq.exporters.export(shape, f"case/out/{name}.stl")
    bb = shape.val().BoundingBox()
    print(f"{name}.stl  {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm")


if __name__ == "__main__":
    # caps in two clearances, four of each on one plate, flange down (top face up: print it upside
    # down? no: flange is wider than the body, so print flange DOWN, top up; bridge-free)
    # v0 lid: press-fit keycaps, two pocket sizes (PLA holes print small; try both)
    for pocket in (1.95, 2.05):
        parts = None
        for i in range(4):
            c = keycap(pocket_d=pocket).translate((i * 8.0, 0, 0))
            parts = c if parts is None else parts.union(c)
        export(parts, f"keycaps_x4_pocket{pocket:.2f}")
    # v1 lid (raised): floating caps with a flange. Needs SWITCH_TOP_BELOW_LID measured on the v1 lid.
    cap(verbose=True)
    for clear in (0.15, 0.25):
        parts = None
        for i in range(4):
            c = cap(clear=clear).translate((i * 8.0, 0, 0))
            parts = c if parts is None else parts.union(c)
        export(parts, f"v1_floating_caps_x4_clear{clear:.2f}")
    export(joystick_dome(hole_d=0), "joystick_dome")
