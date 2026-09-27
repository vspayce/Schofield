"""Sharps "Old Reliable" 1874 — the falling-block buffalo gun.

Percussion-era military pattern (as in references/sharps-rifle-wild-west.jpg): a short,
tall, flat-sided case-hardened frame; a big external side hammer; the trigger guard
doubling as the operating lever, looping down and back under the wrist; a heavy round
barrel in a long banded forend; and a straight-wrist stock with a flat iron butt plate.

See weapon_mods.py for the module contract. Origin = the wrist (firing hand), barrel
along -Y, Z up. Proportions were taken off the reference photo at ~1.70 mm per pixel.
"""

NAME = 'Sharps'
LENGTH = 1.25

ZB = 0.045                      # bore axis height
MUZ = -0.920                    # muzzle, so butt(+0.330) .. muzzle = 1.25 m
BR0, BR1 = 0.0150, 0.0118       # barrel radius at breech / at muzzle — much fatter than the '73
RX = 0.017                      # receiver half-width (flat slab sides)
FR, FF = -0.126, -0.797         # forend: rear (at the frame) / front tip


def build(ctx):
    L, M, math, Matrix = ctx.L, ctx.M, ctx.math, ctx.Matrix
    bmesh, extrude = ctx.bmesh, ctx.extrude

    def oval(y, zt, zb, hw, n=10, flat=0.0):
        """One loft ring: an ellipse in the XZ plane at y, optionally squared off at the
        sides by `flat` so wood reads as a stock rather than a tube."""
        zc, hz = (zt + zb) / 2, (zt - zb) / 2
        out = []
        for i in range(n):
            a = 2 * math.pi * i / n
            k = 1.0 - flat + flat * abs(math.sin(a))
            out.append((hw * math.cos(a) * k, y, zc + hz * math.sin(a)))
        return out

    def band(bm, y, rx, rz, zc, half=0.007, segs=10):
        """Barrel band — a short elliptical hoop clamping barrel and forend together."""
        L.add_lathe(bm, [(rx, -half), (rx, half)], segs,
                    Matrix.Translation((0, y, zc)) @ Matrix.Rotation(math.pi / 2, 4, 'X')
                    @ Matrix.Diagonal((1.0, rz / rx, 1.0, 1.0)), closed=False)

    def bar(bm, pts, w, h, n=2):
        """Flat steel strap swept along a smoothed side-view path [(y, z)] — lever, trigger."""
        L.add_sweep(bm, L.catmull([(0, y, z) for (y, z) in pts], n),
                    L.rect_profile(w, h, min(w, h) * 0.25), uv=None, up=(1, 0, 0))

    # ------------------------------------------------------------------
    # receiver group (case-hardened): frame, hammer, lock plate, lever, trigger
    # ------------------------------------------------------------------
    bm = bmesh.new()
    # frame: tall flat slab with a vertical front face. Full height only over the barrel
    # ring at the front; behind that the top drops away to leave the hammer standing clear.
    # Traced front-top -> front-bottom -> along the bottom -> up the rear -> back along the top.
    extrude(bm, [(-0.129, 0.060), (-0.129, -0.001), (-0.070, -0.006), (-0.046, -0.004),
                 (-0.030, 0.008), (-0.024, 0.040), (-0.052, 0.045), (-0.076, 0.046),
                 (-0.084, 0.060)], RX, 0.0018)
    L.add_beam(bm, (0, -0.028, 0.045), (0, 0.052, 0.028), 0.013, 0.006)          # upper tang
    L.add_beam(bm, (0, -0.048, -0.008), (0, 0.030, -0.026), 0.012, 0.007)        # lower tang
    # Lock plate let into the wrist behind the frame, hammer pivoting at its nose.
    # Both sit at -X: with the barrel down -Y and up +Z, the gun's right side is
    # forward x up = -X, and a Sharps carries its lock on the right.
    extrude(bm, [(-0.026, 0.020), (-0.026, -0.014), (0.012, -0.018), (0.042, -0.008),
                 (0.044, 0.004), (0.014, 0.018)], 0.0020, 0.0012, x0=-0.0150)
    # hammer: fat body round the pivot, waisted spur flaring into a thumb piece well clear
    # of the frame top, nose hooking forward over the breech. Stands proud of the lock plate.
    extrude(bm, [(-0.072, 0.098), (-0.050, 0.094), (-0.046, 0.076), (-0.054, 0.060),
                 (-0.066, 0.054), (-0.080, 0.052), (-0.088, 0.044), (-0.086, 0.030),
                 (-0.070, 0.020), (-0.050, 0.018), (-0.038, 0.038), (-0.048, 0.064),
                 (-0.062, 0.080)], 0.0065, 0.0018, x0=-0.0215)
    # trigger guard / operating lever: one strap from the frame's lower front, down and
    # back under the trigger, dipping into the finger loop, then up into the wrist
    bar(bm, [(-0.128, 0.000), (-0.126, -0.019), (-0.110, -0.031), (-0.082, -0.033),
             (-0.052, -0.028), (-0.030, -0.034), (-0.010, -0.046), (0.014, -0.046),
             (0.034, -0.032)], 0.012, 0.007)
    bar(bm, [(-0.049, -0.004), (-0.053, -0.019), (-0.046, -0.030)], 0.005, 0.005)  # trigger
    ctx.P('shp_receiver', bm, M['case'], smooth=40, prio=1.3)

    # ------------------------------------------------------------------
    # barrel group (blued): barrel, bands, sights
    # ------------------------------------------------------------------
    bm = bmesh.new()
    ctx.tube_y(bm, -0.055, MUZ, BR0, ZB, segs=12, r1=BR1)                        # heavy round barrel
    band(bm, -0.320, 0.0192, 0.0240, 0.036)                                      # rear band
    band(bm, -0.540, 0.0172, 0.0205, 0.039)                                      # middle band
    band(bm, -0.788, 0.0163, 0.0188, 0.040, half=0.009)                          # nose cap
    L.add_box(bm, (0.011, 0.030, 0.006), (0, -0.235, ZB + 0.015))                # rear sight base
    L.add_box(bm, (0.008, 0.005, 0.010), (0, -0.223, ZB + 0.022))                # ladder leaf
    L.add_box(bm, (0.003, 0.009, 0.009), (0, -0.873, ZB + 0.012))                # front blade
    ctx.P('shp_steel', bm, M['blued'], smooth=40, prio=0.9)

    # ------------------------------------------------------------------
    # wood (walnut): straight-wrist butt stock + long half-stock forend
    # ------------------------------------------------------------------
    bm = bmesh.new()
    stock = [oval(y, zt, zb, hw, flat=0.15) for (y, zt, zb, hw) in
             ((-0.044, 0.044, -0.006, 0.0160), (-0.020, 0.048, -0.018, 0.0170),
              (0.014, 0.036, -0.026, 0.0155), (0.048, 0.030, -0.030, 0.0150),
              (0.090, 0.024, -0.050, 0.0170), (0.150, 0.012, -0.078, 0.0200),
              (0.230, -0.003, -0.105, 0.0220), (0.305, -0.018, -0.126, 0.0225),
              (0.317, -0.021, -0.131, 0.0215))]
    L.add_loft(bm, [list(reversed(r)) for r in stock])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    fore = [oval(y, zt, zb, hw) for (y, zt, zb, hw) in
            ((FR, 0.047, 0.012, 0.0185), (-0.200, 0.046, 0.012, 0.0180),
             (-0.400, 0.045, 0.016, 0.0165), (-0.620, 0.044, 0.020, 0.0150),
             (FF, 0.043, 0.023, 0.0140))]
    L.add_loft(bm, fore)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ctx.P('shp_wood', bm, M['walnut'], smooth=45)

    # ------------------------------------------------------------------
    # flat iron butt plate, with the heel tang running forward along the comb
    # ------------------------------------------------------------------
    bm = bmesh.new()
    face = L.rect_profile(0.043, 0.112, 0.013)
    L.add_loft(bm, [[(x * 1.00, 0.316, -0.076 + z) for (x, z) in face],
                    [(x * 0.96, 0.330, -0.076 + z * 0.97) for (x, z) in face]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    L.add_beam(bm, (0, 0.328, -0.020), (0, 0.266, -0.010), 0.019, 0.005)
    ctx.P('shp_butt', bm, M['blued'], smooth=40, prio=0.4)

    return (0, MUZ, ZB)
