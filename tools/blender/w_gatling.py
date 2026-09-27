"""Gatling geometry for build_weapons.py. See weapon_mods.py for the contract.

1866 Model, hand-cranked, as bought by the US Army: six .58 barrels in a round
bundle, bronze breech casing, vertical gravity-feed magazine standing on top,
crank at the rear right.  Mounted on the coach roof rail in game, so the carriage
is reduced to a trunnion yoke and a short post under the breech.

  barrels point -Y, Z up, X across.  Origin is the crank/breech end where the
  gunner stands; the bore-cluster axis runs down -Y at z = ZC.
"""
NAME = 'Gatling'
LENGTH = 1.20

# ---- layout ---------------------------------------------------------------
ZC = 0.030          # centre axis of the barrel cluster and the breech casing
RC = 0.036          # pitch radius the six barrels sit on
RB = 0.0170         # barrel radius at the breech  (cluster o/d = 2*(RC+RB) = 0.106)
YR = 0.020          # datum for the casing lathe; its rear face lands at YR + 0.014
BY0, BY1 = -0.272, -1.060   # barrel breech (just inside the casing) and muzzle
CX = 0.028          # crank axle, offset to the gunner's right


def build(ctx):
    L, M, math, Matrix = ctx.L, ctx.M, ctx.math, ctx.Matrix
    cos, sin, pi = math.cos, math.sin, math.pi

    def bore(y):
        """Lathe matrix on the bore axis at y; profile axial runs forward (-Y)."""
        return Matrix.Translation((0, y, ZC)) @ Matrix.Rotation(pi / 2, 4, 'X')

    def ring_y(bm, y, r_in, r_out, length, segs=14, lip=0.006):
        """Collar around the bore axis: flat band with a chamfer at each end."""
        L.add_lathe(bm, [(r_in, 0.0), (r_out, lip), (r_out, length - lip), (r_in, length)],
                    segs, bore(y), closed=False)

    def cyl_y(bm, r, y0, y1, x=0.0, z=ZC, segs=8):
        """Capped cylinder along the gun axis (used for the crank shaft / grip)."""
        L.add_cyl(bm, r, r, abs(y1 - y0), segs, loc=(x, (y0 + y1) / 2, z), rot=(pi / 2, 0, 0))

    # ------------------------------------------------------------------ brass
    # Breech casing: one lathe from the flat rear plate through the full-diameter
    # drum to the front barrel plate the six barrels pass through. The short
    # shoulder at each end keeps it reading as a machined bronze drum rather than
    # an egg once the normals are smoothed.
    bm = ctx.bmesh.new()
    L.add_lathe(bm, [(0.016, -0.014), (0.050, -0.014), (0.055, -0.006), (0.062, 0.008),
                     (0.063, 0.030), (0.063, 0.210), (0.060, 0.262), (0.054, 0.300)],
                16, bore(YR), cap0=True, cap1=True)
    L.add_cyl(bm, 0.024, 0.024, 0.024, 10, loc=(CX, 0.028, ZC), rot=(pi / 2, 0, 0))  # crank gear case
    L.add_box(bm, (0.008, 0.100, 0.058), (-0.060, -0.150, ZC))                       # inspection plate
    for sx in (-1, 1):                                                               # trunnion end caps
        L.add_cyl(bm, 0.014, 0.014, 0.008, 10, loc=(sx * 0.063, -0.150, ZC - 0.006),
                  rot=(0, pi / 2, 0))
    L.add_box(bm, (0.044, 0.070, 0.026), (0, -0.130, 0.086))                         # feed throat on the casing
    L.add_box(bm, (0.058, 0.094, 0.008), (0, -0.130, 0.230))                         # magazine mouth flange
    # Gravity magazine: a tall brass box, flared at the top so the cartridges drop.
    L.add_sweep(bm, [(0, -0.130, 0.080), (0, -0.130, 0.228)],
                L.rect_profile(0.046, 0.078, 0.008), scales=[1.0, 1.12], uv=None, up=(0, 1, 0))
    ctx.P('gat_brass', bm, M['brass'], smooth=40, prio=1.3)

    # -------------------------------------------------- barrel cluster (spins)
    # Tagged sub='Barrels' so it exports as a child node the game can rotate about
    # the bore axis. Only what is bolted to the bundle goes in here.
    # Six barrels, one at top dead centre so the bundle is symmetric about X=0.
    # Each is a slightly tapered 8-sided tube -- at 33 mm across that reads round.
    bm = ctx.bmesh.new()
    for i in range(6):
        a = pi / 2 + i * pi / 3
        bx, bz = RC * cos(a), ZC + RC * sin(a)
        L.add_sweep(bm, [(bx, BY0, bz), (bx, -0.420, bz), (bx, BY1, bz)],
                    L.circle_profile(RB, 8), scales=[1.0, 0.96, 0.90], uv=None, up=(0, 0, 1))
    ctx.P('gat_barrels', bm, M['blued'], smooth=40, prio=1.0, sub='Barrels')

    # The three bronze rings are shrunk onto the bundle and turn with it.
    bm = ctx.bmesh.new()
    ring_y(bm, -0.320, 0.051, 0.0585, 0.030)                                         # rear barrel band
    ring_y(bm, -0.690, 0.051, 0.0575, 0.028)                                         # mid barrel band
    ring_y(bm, -1.026, 0.051, 0.0585, 0.032)                                         # muzzle band
    ctx.P('gat_barrel_bands', bm, M['brass'], smooth=40, prio=1.1, sub='Barrels')

    # ------------------------------------------------------- steel, all static
    bm = ctx.bmesh.new()
    # Trunnion yoke: axle pin through the casing, two cheeks down to a stub post
    # that drops into the coach's roof-rail socket.
    L.add_cyl(bm, 0.009, 0.009, 0.130, 8, loc=(0, -0.150, ZC - 0.006), rot=(0, pi / 2, 0))
    for sx in (-1, 1):
        L.add_beam(bm, (sx * 0.062, -0.150, 0.026), (sx * 0.030, -0.150, -0.062),
                   0.016, 0.052, up=(0, 1, 0))
    L.add_box(bm, (0.070, 0.048, 0.016), (0, -0.150, -0.056))                        # yoke crosspiece
    L.add_cyl(bm, 0.022, 0.022, 0.056, 10, loc=(0, -0.150, -0.082))                  # mounting post
    L.add_box(bm, (0.058, 0.050, 0.010), (0, -0.150, -0.112))                        # bed plate
    # Crank: axle out of the gear case, a flat arm swung down to the right, and a
    # steel collar where the wooden grip is pinned on. The throw is deliberately
    # wide so the crank still reads as a crank from the side.
    gx, gz = CX + 0.052 * cos(-0.52), ZC + 0.052 * sin(-0.52)
    cyl_y(bm, 0.009, 0.026, 0.088, x=CX)
    L.add_beam(bm, (CX - 0.004, 0.074, ZC + 0.002), (gx + 0.003, 0.074, gz - 0.002),
               0.020, 0.013, up=(0, 1, 0))
    cyl_y(bm, 0.0145, 0.062, 0.076, x=gx, z=gz)
    # Sights: leaf on the casing, blade riding above the muzzle band. The blade
    # stays with the frame -- a sight that spun with the cluster would be wrong,
    # and the band it sits over is a surface of revolution, so nothing shows.
    L.add_box(bm, (0.018, 0.024, 0.008), (0, -0.062, ZC + 0.066))
    L.add_box(bm, (0.020, 0.005, 0.016), (0, -0.056, ZC + 0.076))
    L.add_box(bm, (0.010, 0.016, 0.014), (0, -1.040, ZC + 0.062))
    ctx.P('gat_steel', bm, M['blued'], smooth=40, prio=1.0)

    # ------------------------------------------------------------------- wood
    bm = ctx.bmesh.new()
    cyl_y(bm, 0.0115, 0.074, 0.140, x=gx, z=gz)                                      # crank grip
    ctx.P('gat_wood', bm, M['walnut'], smooth=45, prio=0.5)

    return (0.0, BY1, ZC)
