"""Shared dimensions for the SCHOFIELD Concord stagecoach.

Pure Python (no bpy) so both the Blender builder (build_stagecoach.py) and the
PIL decal painter (tools/textures/coach_decals.py) agree on panel layout.

Blender space, metres: coach faces -Y, Z up, coach LEFT = +X, RIGHT = -X.
"""

YC = 0.0675          # body centre along Y (body is front/back symmetric about this)

# Body shell horizontal rings, bottom -> top:
#   (z, half_length, half_width, plan_corner_radius)
# The body is an egg/"D" shape in side view: the belly narrows and curves up
# at both ends, sides flare out towards the belt rail (tumble-under).
RINGS = [
    (0.930, 0.660, 0.560, 0.22),
    (0.970, 0.855, 0.615, 0.20),
    (1.050, 0.995, 0.668, 0.17),
    (1.180, 1.090, 0.708, 0.14),
    (1.350, 1.143, 0.742, 0.12),
    (1.520, 1.165, 0.760, 0.11),
    (1.555, 1.168, 0.764, 0.11),
    (1.558, 1.184, 0.780, 0.115),   # belt rail moulding (protrudes 16 mm)
    (1.602, 1.184, 0.780, 0.115),
    (1.605, 1.168, 0.764, 0.11),
    (1.660, 1.167, 0.762, 0.10),
    (2.020, 1.165, 0.750, 0.09),
    (2.140, 1.165, 0.746, 0.09),
    (2.200, 1.166, 0.745, 0.09),
]
BELT_Z = (1.555, 1.605)
ROOF_Z = 2.20        # top of shell; roof slab sits on this
ROOF_TOP = 2.255

# Side windows (relative to YC): (y0, y1) ; all share z range
WINDOWS_Y = [(-0.97, -0.52), (-0.23, 0.23), (0.52, 0.97)]
WINDOW_Z = (1.66, 2.02)          # ring band the opening is inset from
DOOR_Y = (-0.31, 0.31)
DOOR_Z = (1.00, 2.06)

# Decal projection windows (world coords)
SIDE_DECAL = dict(y0=YC - 1.40, y1=YC + 1.40, z0=0.85, z1=2.30, w=2048)
REAR_DECAL = dict(x0=-0.85, x1=0.85, z0=0.85, z1=2.30, w=1024)

# Running gear
REAR_AXLE_Y = 0.95
FRONT_AXLE_Y = -1.40
REAR_R = 0.725       # wheel radius (1.45 m diameter)
FRONT_R = 0.50       # (1.0 m diameter)
REAR_TRACK = 0.885   # hub centre |x|
FRONT_TRACK = 0.835
BRACE_X = 0.50       # thoroughbrace |x|
HITCH = (0.0, -3.40, 0.92)


def _cr(p0, p1, p2, p3, t):
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


def rings_dense():
    """RINGS with Catmull-Rom midpoints inserted in the curved belly (z < 1.4)."""
    out = []
    n = len(RINGS)
    for i in range(n):
        out.append(RINGS[i])
        if i + 1 < n and RINGS[i + 1][0] <= 1.36:
            a = RINGS[max(i - 1, 0)]
            b, c = RINGS[i], RINGS[i + 1]
            d = RINGS[min(i + 2, n - 1)]
            out.append(tuple(round(_cr(a[k], b[k], c[k], d[k], 0.5), 4) for k in range(4)))
    return out


def side_outline():
    """Closed side-view silhouette polygon [(y, z)] of the shell (no belt)."""
    rings = [r for r in rings_dense() if r[0] not in (1.558, 1.602)]
    front = [(YC - hl, z) for (z, hl, hw, cr) in rings]
    rear = [(YC + hl, z) for (z, hl, hw, cr) in reversed(rings)]
    return front + rear
