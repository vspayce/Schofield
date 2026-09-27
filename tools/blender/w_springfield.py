"""Springfield Allin conversion rifle — US Army "trapdoor", .50-70, 1866.

A long infantry rifle built on the 1863 rifle-musket: a one-piece walnut stock
whose forend runs almost to the muzzle with the barrel let in deep (only the top
third of the barrel shows), clamped by three barrel bands and a nose cap; a
straight-wrist butt under a deep iron butt plate; an external side hammer on a
case-hardened lock plate; and the hinged breech block — the "trapdoor" — lying
on top of the barrel just ahead of the hammer, with the long ladder rear sight
on the barrel in front of it.

Proportions are read off references/springfield-allin-conversion-rifle.png (left
profile, muzzle right), scaled to 1.30 m overall: pixel x 49 (butt) .. 757
(muzzle), origin at pixel 240, and the bore line fitted through the barrel so
the photo's slight tilt is taken out.

Space: barrel down -Y, Z up, origin at the wrist where the firing hand grips.
"""
NAME = 'Springfield'
LENGTH = 1.30

ZB = 0.045                      # bore axis height
MUZ = -0.949                    # muzzle face
BREECH = -0.016                 # rear face of the barrel, buried in the breech frame


def build(ctx):
    L, M, math, Matrix = ctx.L, ctx.M, ctx.math, ctx.Matrix

    def ring(y, zt, zb, hw, n=10):
        """One loft ring of the stock: a slightly squared-off oval."""
        zc, hz = (zt + zb) / 2, (zt - zb) / 2
        return [(hw * math.cos(2 * math.pi * i / n) * (0.86 + 0.14 * abs(math.sin(2 * math.pi * i / n))),
                 y, zc + hz * math.sin(2 * math.pi * i / n)) for i in range(n)]

    # ------------------------------------------------------------------
    # barrel, bands, sights, ramrod  (blued)
    # ------------------------------------------------------------------
    bm = ctx.bmesh.new()
    L.add_sweep(bm, [(0, BREECH, ZB), (0, -0.300, ZB), (0, MUZ, ZB)],
                L.circle_profile(0.0136, 12), scales=[1.0, 0.885, 0.795],
                uv=None, up=(0, 0, 1))                                        # round barrel, tapered

    # bands clamp forend and barrel together — flattened rings, shrinking forward
    for (by, hx, hz, cz) in ((-0.268, 0.0183, 0.0183, 0.0396),                # lower band
                             (-0.543, 0.0174, 0.0164, 0.0404),                # middle band
                             (-0.812, 0.0166, 0.0150, 0.0407),                # upper band
                             (-0.874, 0.0164, 0.0147, 0.0409)):               # nose cap
        L.add_lathe(bm, [(0.93, -0.0090), (1.0, 0.0), (0.93, 0.0090)], 10,
                    Matrix.Translation((0, by, cz)) @ Matrix.Rotation(math.pi / 2, 4, 'X')
                    @ Matrix.Diagonal((hx, hz, 1.0, 1.0)), closed=False)

    L.add_box(bm, (0.016, 0.086, 0.008), (0, -0.144, 0.0580))                 # ladder sight base
    L.add_box(bm, (0.011, 0.018, 0.014), (0, -0.110, 0.0655))                 # folded sight leaf
    L.add_box(bm, (0.004, 0.012, 0.008), (0, -0.909, 0.0590))                 # front sight blade
    L.add_rod(bm, [(0, -0.300, 0.0295), (0, -0.880, 0.0295), (0, -0.930, 0.0295)],
              0.0038, 6, scales=[1.0, 1.0, 1.2])                              # ramrod in its groove
    ctx.P('spr_barrel', bm, M['blued'], smooth=40, prio=1.0)

    # ------------------------------------------------------------------
    # breech frame, trapdoor block, lock, trigger  (case-hardened)
    # ------------------------------------------------------------------
    bm = ctx.bmesh.new()
    # the frame sits entirely ahead of the hammer — behind it is bare wrist and lock
    ctx.extrude(bm, [(-0.010, 0.028), (-0.010, 0.058), (-0.098, 0.058),
                     (-0.104, 0.044), (-0.104, 0.028)], 0.0155, 0.003)        # breech frame
    ctx.extrude(bm, [(-0.010, 0.050), (-0.012, 0.071), (-0.092, 0.064), (-0.102, 0.060),
                     (-0.102, 0.052), (-0.090, 0.049)], 0.0132, 0.002)        # hinged trapdoor block
    L.add_box(bm, (0.020, 0.014, 0.013), (0, -0.100, 0.0635), bevel=0.002)    # cam latch / thumb piece
    ctx.extrude(bm, [(0.058, 0.022), (0.044, 0.029), (0.024, 0.031), (0.000, 0.030),
                     (-0.020, 0.025), (-0.018, 0.014), (0.014, 0.011),
                     (0.042, 0.015)], 0.0170, 0.002)                          # lock plate, proud of the wrist
    ctx.extrude(bm, [(0.024, 0.030), (0.026, 0.044), (0.016, 0.060), (0.014, 0.080),
                     (0.006, 0.094), (-0.010, 0.093), (-0.018, 0.074), (-0.016, 0.058),
                     (-0.006, 0.044), (0.012, 0.030)], 0.0058, 0.0012, x0=-0.0202)
    # ^ external side hammer: round boss on the lock plate, thumb spur up, nose down
    #   on the rear face of the breech block
    ctx.sweep_rect(bm, [(0, 0.050, 0.010), (0, 0.030, -0.016), (0, -0.002, -0.019),
                        (0, -0.026, -0.009), (0, -0.036, 0.009)], 0.009, 0.005, smooth=2)  # guard bow
    ctx.sweep_rect(bm, [(0, 0.004, 0.008), (0, -0.003, -0.002), (0, -0.010, -0.011)],
                   0.005, 0.004, smooth=2)                                    # trigger
    ctx.P('spr_lock', bm, M['case'], smooth=40, prio=1.2)

    # ------------------------------------------------------------------
    # one-piece stock: butt, straight wrist, full-length forend  (walnut)
    # ------------------------------------------------------------------
    bm = ctx.bmesh.new()
    L.add_loft(bm, [ring(*r) for r in (
        (0.342, 0.004, -0.096, 0.0196),     # butt face, behind the plate
        (0.332, 0.006, -0.099, 0.0218),     # widest point
        (0.288, 0.009, -0.088, 0.0226),
        (0.238, 0.013, -0.075, 0.0220),
        (0.188, 0.017, -0.059, 0.0208),
        (0.140, 0.020, -0.041, 0.0193),
        (0.112, 0.016, -0.029, 0.0180),     # comb nose
        (0.072, 0.030, -0.013, 0.0170),     # wrist
        (0.030, 0.044, -0.004, 0.0168),
        (-0.014, 0.046, 0.008, 0.0150),     # narrows into the breech-frame inlet
        (-0.100, 0.046, 0.014, 0.0150),
        (-0.116, 0.049, 0.015, 0.0166),     # swells back out ahead of the frame
        (-0.330, 0.049, 0.023, 0.0158),
        (-0.620, 0.048, 0.026, 0.0150),
        (-0.885, 0.048, 0.028, 0.0142))])   # forend tip, a hand short of the muzzle
    ctx.bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ctx.P('spr_wood', bm, M['walnut'], smooth=45)

    # ------------------------------------------------------------------
    # butt plate (blued iron, deep musket curve with a tang over the comb)
    # ------------------------------------------------------------------
    bm = ctx.bmesh.new()
    L.add_sweep(bm, L.catmull([(0, 0.334, 0.005), (0, 0.352, -0.006),
                               (0, 0.351, -0.062), (0, 0.341, -0.100)], 2),
                L.rect_profile(0.044, 0.007, 0.002), uv=None, up=(0, 1, 0))
    ctx.P('spr_butt', bm, M['blued'], smooth=40, prio=0.4)

    return (0.0, MUZ, ZB)
