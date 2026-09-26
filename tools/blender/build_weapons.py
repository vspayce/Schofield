"""Build public/assets/models/weapons.glb — Schofield revolver, coach gun, Winchester.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_weapons.py [-- --quick]

Blender space: barrel points -Y (=> +Z in glTF), Z up, origin at the grip (where the
firing hand holds). Each weapon is one root mesh with a child empty Muzzle_<Name> at
the muzzle.  All three share one baked 1024 atlas / material "Weapons".
"""
import bpy
import bmesh
import math
import os
import shutil
import subprocess
import sys
import time
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sch_lib as L  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
QUICK = '--quick' in ARGS
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'models', 'weapons.glb')
BUILD = os.path.join(HERE, 'build', 'weapons')
TEX = 256 if QUICK else 1024
PY = shutil.which('python3') or '/usr/bin/python3'
T0 = time.time()


def log(*a):
    print('[weapons %5.1fs]' % (time.time() - T0), *a, flush=True)


L.reset_scene()
L.setup_cycles(6 if QUICK else 48)

# ----------------------------------------------------------------------------
# materials (no ground dust on guns: dust only in cavities)
# ----------------------------------------------------------------------------
GUN_DUST = dict(dust=0.25, dust_z=(-5, -4), dust_up=0.0, dust_col=L.srgb(120, 104, 84))


def case_hardened(mb, st):
    P = mb.pos
    n1 = mb.noise(P, 60.0, 4.0, 0.6, dist=1.5)
    n2 = mb.noise(P, 35.0, 3.0, 0.5, dist=2.0)
    c = mb.mixc(mb.smooth(n1, 0.4, 0.6), L.srgb(40, 50, 80), L.srgb(120, 86, 60))
    c = mb.mixc(mb.smooth(n2, 0.45, 0.62), c, L.srgb(90, 70, 110))
    st['col'] = mb.mixc(0.8, st['col'], c)


def walnut_fig(mb, st):
    P = mb.pos
    f = mb.smooth(mb.noise(P, 18.0, 5.0, 0.7, dist=3.0), 0.5, 0.7)
    st['col'] = mb.mixc(mb.m('MULTIPLY', f, 0.6), st['col'], L.srgb(40, 20, 10))


M = {}
M['blued'] = L.surface('blued', L.srgb(30, 33, 42), var=0.12, var_scale=20, rough=0.3, metal=0.85,
                       wear_col=L.srgb(170, 170, 168), wear=0.9, wear_rough=0.25, wear_metal=1.0,
                       edge_r=0.0025, edge_w=(0.01, 0.1), wear_scale=120, scratches=0.3, ao=0.7,
                       ao_dist=0.03, bump=0.05, bump_scale=600, blotch=0.3, **GUN_DUST)
M['nickel'] = L.surface('nickel', L.srgb(176, 172, 164), var=0.08, var_scale=20, rough=0.22, metal=1.0,
                        wear_col=L.srgb(120, 110, 96), wear=0.5, edge_r=0.002, wear_scale=120, ao=0.7,
                        ao_dist=0.03, bump=0.05, bump_scale=600, blotch=0.4, **GUN_DUST)
M['case'] = L.surface('case', L.srgb(80, 70, 70), var=0.1, var_scale=20, rough=0.3, metal=0.9,
                      wear_col=L.srgb(180, 176, 170), wear=0.7, edge_r=0.0025, wear_scale=120, ao=0.7,
                      ao_dist=0.03, bump=0.05, bump_scale=600, extra=case_hardened, **GUN_DUST)
M['brass'] = L.surface('brass', L.srgb(196, 150, 72), var=0.1, var_scale=20, rough=0.3, metal=0.9,
                       wear_col=L.srgb(236, 204, 130), wear=0.8, wear_rough=0.2, edge_r=0.0025,
                       wear_scale=120, scratches=0.3, ao=0.75, ao_dist=0.03, blotch=0.5, bump=0.04,
                       bump_scale=600, **GUN_DUST)
M['walnut'] = L.surface('walnut', L.srgb(92, 50, 26), var=0.15, var_scale=12, rough=0.4,
                        wear_col=L.srgb(140, 92, 54), wear=0.7, edge_r=0.004, wear_scale=90,
                        grain='Y', grain_amt=0.55, grain_freq=6.0, ao=0.7, ao_dist=0.03, bump=0.15,
                        bump_scale=400, extra=walnut_fig, scratches=0.3, **GUN_DUST)

PARTS = []


def P(name, bm, mat, weapon, smooth=35, prio=1.0):
    ob = L.obj_from_bm(name, bm, mat, smooth=smooth, props=dict(weapon=weapon, prio=prio))
    PARTS.append(ob)
    return ob


def extrude(bm, pts, hx, bev=0.0, x0=0.0):
    """Extrude a side-view profile [(y, z)] symmetrically in X (half thickness hx), with a
    small chamfer made by shrinking the outer rings towards the centroid."""
    cy = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)

    def shrink(k):
        return [(cy + (y - cy) * k, cz + (z - cz) * k) for (y, z) in pts]
    size = max(max(p[0] for p in pts) - min(p[0] for p in pts),
               max(p[1] for p in pts) - min(p[1] for p in pts))
    k = 1 - 2 * bev / max(size, 1e-4)
    if bev > 0:
        rings = [(x0 - hx, shrink(k)), (x0 - hx + bev, pts), (x0 + hx - bev, pts), (x0 + hx, shrink(k))]
    else:
        rings = [(x0 - hx, pts), (x0 + hx, pts)]
    L.add_loft(bm, [[(x, y, z) for (y, z) in pr] for (x, pr) in rings])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def tube_y(bm, y0, y1, r, z, x=0.0, segs=12, r1=None, caps=True):
    """Cylinder along -Y from y0 to y1 (y1 < y0 is forward)."""
    L.add_sweep(bm, [(x, y0, z), (x, y1, z)], L.circle_profile(r, segs, 0.0),
                scales=[1.0, (r1 or r) / r], uv=None, caps=caps, up=(0, 0, 1))


def sweep_round(bm, pts, r, n=6, smooth=3):
    L.add_sweep(bm, L.catmull(pts, smooth) if len(pts) > 2 else pts, L.circle_profile(r, n),
                uv=None, up=(1, 0, 0))


def sweep_rect(bm, pts, w, h, smooth=3):
    L.add_sweep(bm, L.catmull(pts, smooth) if len(pts) > 2 else pts, L.rect_profile(w, h, min(w, h) * 0.25),
                uv=None, up=(1, 0, 0))


# ----------------------------------------------------------------------------
# SCHOFIELD (S&W No.3 top-break, 7" barrel, blued, walnut grips) ~0.32 m
# grip centre at origin, bore axis at z = ZB
# ----------------------------------------------------------------------------
log('schofield')
ZB = 0.078
S = 'Schofield'
GY, GZ = 0.030, -0.008          # grip centre in the drawing coords -> moved to origin


def sp(y, z):
    return (y - GY, z - GZ)


def s3(y, z):
    return (0.0, y - GY, z - GZ)


bm = bmesh.new()
# frame in pieces so the fluted cylinder sits in an open window
rear = [(-0.026, 0.050), (-0.026, 0.100), (0.004, 0.100), (0.012, 0.105), (0.022, 0.101),
        (0.030, 0.091), (0.035, 0.076), (0.042, 0.052), (0.050, 0.025), (0.056, -0.005),
        (0.062, -0.032), (0.066, -0.050), (0.063, -0.060), (0.053, -0.067), (0.040, -0.067),
        (0.028, -0.061), (0.020, -0.040), (0.014, -0.012), (0.010, 0.010), (0.004, 0.032),
        (-0.008, 0.046)]
extrude(bm, [sp(*p) for p in rear], 0.0112, 0.0025)
extrude(bm, [sp(*p) for p in [(-0.079, 0.052), (-0.079, 0.093), (-0.071, 0.099), (-0.064, 0.099),
                                (-0.064, 0.050)]], 0.0112, 0.002)
extrude(bm, [sp(*p) for p in [(-0.066, 0.0975), (-0.066, 0.1035), (-0.024, 0.1035), (-0.024, 0.0975)]],
        0.0075, 0.0015)
extrude(bm, [sp(*p) for p in [(-0.066, 0.049), (-0.066, 0.056), (-0.024, 0.056), (-0.024, 0.049)]],
        0.010, 0.0015)
# barrel: tapered round barrel + top rib, ejector housing, front sight
by0, by1 = -0.077 - GY, -0.255 - GY
tube_y(bm, by0, by1, 0.0092, ZB - GZ, segs=12, r1=0.0082)
L.add_beam(bm, (0, by0, ZB - GZ + 0.0085), (0, by1 + 0.004, ZB - GZ + 0.0078), 0.007, 0.006, up=(0, 0, 1))
tube_y(bm, by0, -0.170 - GY, 0.0062, ZB - GZ - 0.0145, segs=8)
L.add_beam(bm, (0, by0, ZB - GZ - 0.0105), (0, -0.170 - GY, ZB - GZ - 0.0105), 0.009, 0.010, up=(0, 0, 1))
L.add_box(bm, (0.0025, 0.012, 0.008), (0, by1 + 0.008, ZB - GZ + 0.014))
L.add_beam(bm, (0, by1 + 0.001, ZB - GZ), (0, by1 - 0.0008, ZB - GZ), 0.021, 0.021)   # muzzle crown
# barrel latch (distinctive stirrup on top strap) + hinge pivot at frame front bottom
L.add_box(bm, (0.019, 0.016, 0.010), (0, 0.004 - GY, 0.104 - GZ), bevel=0.002)
L.add_box(bm, (0.023, 0.006, 0.014), (0, -0.003 - GY, 0.101 - GZ), bevel=0.002)
L.add_cyl(bm, 0.0065, 0.0065, 0.027, 10, loc=(0, -0.075 - GY, 0.056 - GZ), rot=(0, math.pi / 2, 0))
# hammer
extrude(bm, [sp(0.014, 0.092), sp(0.020, 0.108), sp(0.030, 0.121), sp(0.040, 0.124),
             sp(0.039, 0.117), sp(0.030, 0.110), sp(0.028, 0.094)], 0.0045, 0.001)
# trigger guard + trigger
sweep_round(bm, [s3(-0.040, 0.050), s3(-0.040, 0.034), s3(-0.024, 0.020), s3(-0.004, 0.024),
                 s3(0.004, 0.036)], 0.0032, 6)
sweep_rect(bm, [s3(-0.014, 0.050), s3(-0.020, 0.040), s3(-0.020, 0.030), s3(-0.014, 0.024)], 0.005, 0.004)
# butt lanyard ring
L.add_lathe(bm, [(0.006, -0.0015), (0.009, -0.0015), (0.009, 0.0015), (0.006, 0.0015)], 8,
            Matrix.Translation(Vector((0, 0.058 - GY, -0.070 - GZ))) @ Matrix.Rotation(math.pi / 2, 4, 'Y'),
            closed=True)
P('sch_steel', bm, M['blued'], S, smooth=40)

bm = bmesh.new()   # fluted cylinder
cyc = Vector((0, -0.045 - GY, ZB - GZ))
segs, R = 24, 0.0205
prof = [(-0.019, 0.55), (-0.017, 1.0), (0.017, 1.0), (0.019, 0.55)]
rings = []
for (ay, kr) in prof:
    ring = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        flute = max(0.0, math.cos(6 * a)) ** 2 if abs(ay) < 0.018 else 0.0
        r = R * kr if kr < 1 else R - 0.0038 * flute * (1 if abs(ay) < 0.012 else 0.5)
        ring.append((cyc.x + r * math.sin(a), cyc.y + ay, cyc.z + r * math.cos(a)))
    rings.append(ring)
L.add_loft(bm, rings)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
P('sch_cyl', bm, M['blued'], S, smooth=50)

bm = bmesh.new()   # walnut grip panels
grip = [(0.008, 0.036), (0.030, 0.050), (0.038, 0.047), (0.045, 0.024), (0.051, -0.004),
        (0.057, -0.030), (0.060, -0.047), (0.057, -0.055), (0.049, -0.060), (0.039, -0.060),
        (0.030, -0.055), (0.024, -0.038), (0.018, -0.012), (0.014, 0.010)]
extrude(bm, [sp(*p) for p in grip], 0.0155, 0.004)
P('sch_grip', bm, M['walnut'], S, smooth=40, prio=1.2)
SCH_MUZZLE = (0, by1 - 0.002, ZB - GZ)

# ----------------------------------------------------------------------------
# COACH GUN (short side-by-side, exposed hammers) ~0.95 m, origin at the wrist
# ----------------------------------------------------------------------------
log('coach gun')
C = 'CoachGun'
BZ = 0.040
bm = bmesh.new()
for sx in (-1, 1):
    tube_y(bm, -0.135, -0.612, 0.0112, BZ, x=sx * 0.0112, segs=12, r1=0.0104)
L.add_beam(bm, (0, -0.135, BZ + 0.0105), (0, -0.610, BZ + 0.0095), 0.008, 0.006)   # rib
L.add_beam(bm, (0, -0.135, BZ - 0.011), (0, -0.605, BZ - 0.010), 0.006, 0.006)      # lower rib
L.add_box(bm, (0.003, 0.006, 0.005), (0, -0.600, BZ + 0.0145))                        # bead
for sx in (-1, 1):   # muzzle bores (dark rings)
    L.add_lathe(bm, [(0.0105, 0.0), (0.0085, 0.0)], 12,
                Matrix.Translation((sx * 0.0112, -0.6125, BZ)) @ Matrix.Rotation(math.pi / 2, 4, 'X'),
                closed=False)
P('cg_barrels', bm, M['blued'], C, smooth=40, prio=0.8)

bm = bmesh.new()   # action body with fences, hammers, triggers, guard, top lever
extrude(bm, [(-0.140, 0.012), (-0.140, 0.052), (-0.128, 0.058), (-0.050, 0.058), (-0.020, 0.052),
             (0.010, 0.046), (0.010, 0.038), (-0.022, 0.028), (-0.030, 0.004), (-0.060, -0.004),
             (-0.120, 0.000)], 0.023, 0.004)
for sx in (-1, 1):
    extrude(bm, [(-0.044, 0.050), (-0.036, 0.074), (-0.026, 0.086), (-0.014, 0.088), (-0.016, 0.081),
                 (-0.026, 0.074), (-0.028, 0.054)], 0.0035, 0.001, x0=sx * 0.0145)
sweep_rect(bm, [(0.0, -0.028, 0.058), (0.0, -0.010, 0.060), (0.012, 0.004, 0.061)], 0.010, 0.004)
sweep_round(bm, [(0, -0.082, 0.000), (0, -0.080, -0.020), (0, -0.055, -0.030), (0, -0.030, -0.022),
                 (0, -0.024, 0.005)], 0.0035, 6)
for (ty, tz) in ((-0.068, 0.0), (-0.050, 0.004)):
    sweep_rect(bm, [(0, ty, tz), (0, ty - 0.004, tz - 0.012), (0, ty + 0.002, tz - 0.022)], 0.005, 0.004)
P('cg_action', bm, M['case'], C, smooth=40, prio=1.1)

bm = bmesh.new()   # stock + forend
stock_rings = []
for (y, zt, zb, hw) in ((-0.028, 0.050, 0.004, 0.019), (0.0, 0.044, -0.004, 0.017),
                        (0.050, 0.042, -0.030, 0.019), (0.120, 0.040, -0.050, 0.020),
                        (0.220, 0.036, -0.074, 0.021), (0.318, 0.034, -0.094, 0.022),
                        (0.330, 0.033, -0.094, 0.021)):
    zc, hz = (zt + zb) / 2, (zt - zb) / 2
    ring = []
    for i in range(10):
        a = 2 * math.pi * i / 10
        ring.append((hw * math.cos(a) * (0.85 + 0.15 * abs(math.sin(a))), y, zc + hz * math.sin(a)))
    stock_rings.append(list(reversed(ring)))
L.add_loft(bm, stock_rings)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
fore = []
for (y, zt, zb, hw) in ((-0.142, 0.030, 0.006, 0.024), (-0.18, 0.030, 0.008, 0.025),
                        (-0.33, 0.030, 0.012, 0.023), (-0.345, 0.030, 0.018, 0.018)):
    zc, hz = (zt + zb) / 2, (zt - zb) / 2
    fore.append([(hw * math.cos(2 * math.pi * i / 10), y, zc + hz * math.sin(2 * math.pi * i / 10))
                 for i in range(10)])
L.add_loft(bm, fore)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
P('cg_wood', bm, M['walnut'], C, smooth=45, prio=1.0)
bm = bmesh.new()
L.add_box(bm, (0.046, 0.008, 0.132), (0, 0.334, -0.030), bevel=0.003)   # butt plate
P('cg_butt', bm, M['blued'], C, smooth=40, prio=0.3)
CG_MUZZLE = (0, -0.614, BZ)

# ----------------------------------------------------------------------------
# WINCHESTER (lever action, brass receiver, octagon barrel) ~1.08 m, origin at wrist
# ----------------------------------------------------------------------------
log('winchester')
W = 'Winchester'
WZ = 0.044
bm = bmesh.new()
extrude(bm, [(-0.195, 0.006), (-0.195, 0.056), (-0.180, 0.062), (-0.040, 0.062), (-0.020, 0.056),
             (0.008, 0.050), (0.008, 0.040), (-0.030, 0.028), (-0.040, 0.004), (-0.090, -0.004),
             (-0.180, -0.004)], 0.0175, 0.003)
L.add_beam(bm, (0.0181, -0.160, 0.030), (0.0181, -0.120, 0.030), 0.0015, 0.012)       # loading gate
P('win_receiver', bm, M['brass'], W, smooth=40, prio=1.2)

bm = bmesh.new()
L.add_sweep(bm, [(0, -0.195, WZ), (0, -0.760, WZ)], L.circle_profile(0.0102, 8, math.pi / 8),
            scales=[1.0, 0.92], uv=None, up=(0, 0, 1))                                 # octagon barrel
tube_y(bm, -0.195, -0.715, 0.0078, WZ - 0.019, segs=8)                                # magazine
for by in (-0.395, -0.700):
    L.add_lathe(bm, [(0.0125, -0.006), (0.0125, 0.006)], 10,
                Matrix.Translation((0, by, WZ - 0.008)) @ Matrix.Rotation(math.pi / 2, 4, 'X')
                @ Matrix.Diagonal((1.0, 1.55, 1.0, 1.0)), closed=False)
L.add_box(bm, (0.003, 0.010, 0.007), (0, -0.745, WZ + 0.013))                          # front sight
L.add_box(bm, (0.012, 0.012, 0.006), (0, -0.330, WZ + 0.012))                          # rear sight
extrude(bm, [(-0.040, 0.054), (-0.030, 0.076), (-0.020, 0.084), (-0.010, 0.084), (-0.012, 0.078),
             (-0.022, 0.070), (-0.024, 0.056)], 0.004, 0.001)                         # hammer
sweep_rect(bm, [(0, -0.088, 0.0), (0, -0.090, -0.016), (0, -0.075, -0.028), (0, -0.045, -0.030),
                (0, -0.012, -0.032), (0, 0.022, -0.040), (0, 0.042, -0.032), (0, 0.040, -0.016),
                (0, 0.018, -0.010), (0, -0.004, -0.006)], 0.009, 0.005, smooth=2)       # lever loop
sweep_rect(bm, [(0, -0.058, 0.0), (0, -0.062, -0.014), (0, -0.056, -0.024)], 0.005, 0.004)  # trigger
P('win_steel', bm, M['blued'], W, smooth=40, prio=0.8)

bm = bmesh.new()
stock_rings = []
for (y, zt, zb, hw) in ((-0.022, 0.055, 0.006, 0.018), (0.0, 0.050, 0.000, 0.016),
                        (0.060, 0.048, -0.024, 0.018), (0.140, 0.046, -0.050, 0.020),
                        (0.250, 0.042, -0.076, 0.021), (0.335, 0.040, -0.094, 0.022),
                        (0.345, 0.039, -0.092, 0.020)):
    zc, hz = (zt + zb) / 2, (zt - zb) / 2
    ring = [(hw * math.cos(2 * math.pi * i / 10) * (0.85 + 0.15 * abs(math.sin(2 * math.pi * i / 10))), y,
             zc + hz * math.sin(2 * math.pi * i / 10)) for i in range(10)]
    stock_rings.append(list(reversed(ring)))
L.add_loft(bm, stock_rings)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
fore = []
for (y, zt, zb, hw) in ((-0.197, 0.040, 0.012, 0.017), (-0.22, 0.040, 0.012, 0.018),
                        (-0.388, 0.040, 0.014, 0.017)):
    zc, hz = (zt + zb) / 2, (zt - zb) / 2
    fore.append([(hw * math.cos(2 * math.pi * i / 10), y, zc + hz * math.sin(2 * math.pi * i / 10))
                 for i in range(10)])
L.add_loft(bm, fore)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
P('win_wood', bm, M['walnut'], W, smooth=45)
bm = bmesh.new()
L.add_sweep(bm, L.catmull([(0, 0.338, 0.044), (0, 0.352, 0.010), (0, 0.352, -0.040), (0, 0.340, -0.098)], 3),
            L.rect_profile(0.044, 0.008, 0.002), uv=None, up=(0, 1, 0))                # crescent butt plate
P('win_butt', bm, M['brass'], W, smooth=40, prio=0.4)
WIN_MUZZLE = (0, -0.762, WZ)

# ----------------------------------------------------------------------------
# bake (weapons laid apart so AO doesn't cross-contaminate)
# ----------------------------------------------------------------------------
OFFS = {S: 0.0, C: 0.6, W: 1.2}
for o in PARTS:
    o.location.x = OFFS[o['weapon']]
tot = {}
for o in PARTS:
    tot[o['weapon']] = tot.get(o['weapon'], 0) + L.tri_count(o)
    log('  %-14s %5d' % (o.name, L.tri_count(o)))
log('tris per weapon', tot)

L.uv_atlas(PARTS, margin=0.006 if TEX >= 1024 else 0.012)
IMGS = {}
for kind in ('color', 'orm', 'normal'):
    img = L.new_image('weap_%s' % kind, TEX, non_color=(kind != 'color'))
    log('bake', kind)
    L.bake_pass(PARTS, img, kind)
    L.save_image(img, os.path.join(BUILD, 'weapons_%s.png' % kind))
    IMGS[kind] = img
conv = []
for kind in IMGS:
    q = {'color': 88, 'orm': 82, 'normal': 88}[kind]
    conv += [os.path.join(BUILD, 'weapons_%s.png' % kind), os.path.join(BUILD, 'weapons_%s.jpg' % kind), str(q)]
subprocess.run([PY, '-c', """
import sys
from PIL import Image
a = sys.argv[1:]
for i in range(0, len(a), 3):
    im = Image.open(a[i]).convert('RGB')
    if 'orm' in a[i]:
        im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
    im.save(a[i + 1], quality=int(a[i + 2]), optimize=True, subsampling=0 if 'normal' in a[i] else 2)
"""] + conv, check=True)
FIN = {}
for kind in IMGS:
    im = bpy.data.images.load(os.path.join(BUILD, 'weapons_%s.jpg' % kind))
    im.name = 'Weapons_%s' % kind
    if kind != 'color':
        im.colorspace_settings.name = 'Non-Color'
    FIN[kind] = im
mat = L.final_material('Weapons', FIN['color'], FIN['orm'], FIN['normal'])
for o in PARTS:
    L.assign_single_material(o, mat)
    L.strip_uvs(o)
    o.location.x = 0.0

roots = {}
GROUPS = {}
for o in PARTS:
    GROUPS.setdefault(o['weapon'], []).append(o)
for wname, muzzle in ((S, SCH_MUZZLE), (C, CG_MUZZLE), (W, WIN_MUZZLE)):
    objs = GROUPS[wname]
    ob = L.join(objs, wname)
    for key in list(ob.keys()):
        del ob[key]
    L.empty('Muzzle_' + wname, muzzle, ob, 0.03, 'ARROWS')
    roots[wname] = ob
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    log('%-11s tris %5d  length %.3f m  (y %.3f..%.3f)' % (wname, L.tri_count(ob),
        max(v.y for v in bb) - min(v.y for v in bb), min(v.y for v in bb), max(v.y for v in bb)))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'weapons.blend'), compress=True)
L.export_glb(OUT)
log('exported', OUT, '%.0f KB' % (os.path.getsize(OUT) / 1024))
