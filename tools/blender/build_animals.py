"""Build public/assets/models/animals.glb — the ambient wildlife of SCHOFIELD:
American bison, black/grizzly bear, pronghorn and a gliding red-tail hawk.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_animals.py [-- --quick] [--geom] [--out PATH]

Blender space: the animal faces -Y (=> +Z in glTF), Z up, origin on the ground
between the feet (the hawk's origin is at its body centre — it is only ever seen
in the air).  Nothing is skinned: the game animates these in JS by rotating
named child nodes, so every animal exports as a root mesh plus child meshes
whose origins sit on the joint they turn about:

  Buffalo / Bear / Goat   <Name>_LegFL .._LegFR .._LegRL .._LegRR  (origin at the
                          shoulder / hip; rotate about local X to swing)
                          <Name>_Head   (origin at the base of the neck; rotate
                          about local X to raise / lower the head)
  Hawk                    Hawk_WingL, Hawk_WingR (origin at the shoulder)

+X is the animal's LEFT (same convention as build_horse.py).
All four share one baked 1024 atlas / material "Animals".
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
GEOM = '--geom' in ARGS         # build shapes, skip the bake (fast iteration)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'models', 'animals.glb')
if '--out' in ARGS:
    OUT = os.path.abspath(ARGS[ARGS.index('--out') + 1])
BUILD = os.path.join(HERE, "build", os.path.splitext(os.path.basename(OUT))[0])
TEX = 256 if QUICK else 1024
PY = shutil.which('python3') or '/usr/bin/python3'
T0 = time.time()


def log(*a):
    print('[animals %5.1fs]' % (time.time() - T0), *a, flush=True)


L.reset_scene()
L.setup_cycles(6 if QUICK else 40)
# small islands (four animals in one atlas): a big EXTEND margin would flood them
bpy.context.scene.render.bake.margin = 6 if TEX >= 1024 else 2

# ----------------------------------------------------------------------------
# materials — fur/hide/feather.  No bevel-shader normals (thin wings, soft
# organic edges), a little ground dust low down, hair grain from noise.
# ----------------------------------------------------------------------------
DUSTY = dict(dust=0.22, dust_z=(0.0, 0.9), dust_up=0.0, dust_scale=4.0,
             dust_col=L.srgb(152, 130, 100))
FUR = dict(metal=0.0, rough=0.78, rough_var=0.10, wear=0.0, bevel_normal=False,
           ao=0.55, ao_dist=0.12, bump=0.35, bump_scale=110.0, bump_dist=0.004, **DUSTY)


def shag(mb, st, y0, y1, dark, amt=0.9, strands=30.0):
    """Long hanging hair between y0 (none) and y1 (full): vertical strands."""
    P = mb.pos
    h = mb.noise(mb.aniso(P, strands, strands, 3.5), 1.0, 5.0, 0.72)
    hs = mb.smooth(h, 0.32, 0.68)
    x, y, z = mb.xyz(P)
    fore = mb.mapr(y, y0, y1, 0.0, 1.0)
    m = mb.m('MULTIPLY', mb.m('MULTIPLY', fore, hs), amt)
    st['col'] = mb.mixc(m, st['col'], dark)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.35),
                        mb.m('MULTIPLY', mb.m('MULTIPLY', fore, hs), 1.4))


def bison_hide(mb, st):
    # dark shaggy forehand, lighter close-cropped hindquarters
    x, y, z = mb.xyz(mb.pos)
    st['col'] = mb.mixc(mb.mapr(y, 0.05, 0.55, 0.0, 0.75), st['col'], L.srgb(104, 74, 48))
    shag(mb, st, -0.10, -0.60, L.srgb(44, 29, 19), 0.85, 26.0)


def bison_shag(mb, st):
    shag(mb, st, 0.30, -1.60, L.srgb(34, 22, 15), 0.95, 22.0)


def bear_hide(mb, st):
    x, y, z = mb.xyz(mb.pos)
    n = mb.noise(mb.aniso(mb.pos, 34.0, 34.0, 6.0), 1.0, 5.0, 0.7)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(n, 0.34, 0.72), 0.55), st['col'],
                        L.srgb(28, 20, 15))
    # sun-tipped guard hair along the topline
    nx, ny, nz = mb.xyz(mb.nrm)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(nz, 0.35, 0.95), 0.30), st['col'],
                        L.srgb(122, 90, 58))


def goat_hide(mb, st):
    x, y, z = mb.xyz(mb.pos)
    nx, ny, nz = mb.xyz(mb.nrm)
    pale = L.srgb(232, 226, 210)
    # white belly and inner flanks
    belly = mb.m('MULTIPLY', mb.smooth(nz, -0.05, -0.60), mb.mapr(z, 0.72, 0.56, 0.0, 1.0))
    st['col'] = mb.mixc(mb.m('MULTIPLY', belly, 0.92), st['col'], pale)
    # white rump patch
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.mapr(y, 0.34, 0.45, 0.0, 1.0), 0.92), st['col'], pale)
    # dark dorsal line / mane
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(nz, 0.75, 1.0), 0.35), st['col'],
                        L.srgb(112, 76, 44))


def goat_face(mb, st):
    x, y, z = mb.xyz(mb.pos)
    nx, ny, nz = mb.xyz(mb.nrm)
    pale = L.srgb(236, 230, 214)
    # two white throat bands + white muzzle sides, dark nose bridge
    b = mb.m('SINE', mb.m('MULTIPLY', y, 42.0))
    band = mb.m('MULTIPLY', mb.smooth(b, 0.25, 0.8), mb.smooth(mb.m('MULTIPLY', nz, -1.0), 0.0, 0.6))
    st['col'] = mb.mixc(mb.m('MULTIPLY', band, 0.9), st['col'], pale)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.mapr(y, -0.60, -0.74, 0.0, 1.0), 0.55), st['col'], pale)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(nz, 0.6, 1.0), 0.55), st['col'],
                        L.srgb(70, 46, 28))


def hawk_plume(mb, st):
    ox, oy, oz = mb.xyz(mb.tc.outputs['Object'])      # object space: immune to the bake offset
    nx, ny, nz = mb.xyz(mb.nrm)
    pale = L.srgb(212, 196, 170)
    dn = mb.smooth(mb.m('MULTIPLY', nz, -1.0), -0.15, 0.45)    # 1 on the underside
    bars = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', oy, 80.0)), -0.2, 0.6)
    under = mb.mixc(mb.m('MULTIPLY', bars, 0.80), pale, L.srgb(128, 102, 74))
    st['col'] = mb.mixc(mb.m('MULTIPLY', dn, 0.94), st['col'], under)
    # dark belly band (red-tail), dark primaries, mottled back
    band = mb.m('MULTIPLY', mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', oy, 0.01)), 0.075, 0.03),
                mb.smooth(mb.m('ABSOLUTE', ox), 0.075, 0.03))
    st['col'] = mb.mixc(mb.m('MULTIPLY', band, 0.75), st['col'], L.srgb(84, 60, 42))
    tips = mb.mapr(mb.m('ABSOLUTE', ox), 0.26, 0.44, 0.0, 1.0)
    st['col'] = mb.mixc(mb.m('MULTIPLY', tips, 0.80), st['col'], L.srgb(46, 35, 28))
    n = mb.noise(mb.pos, 40.0, 4.0, 0.6)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(n, 0.42, 0.72), 0.45), st['col'],
                        L.srgb(58, 42, 30))


M = {}
M['bison'] = L.surface('bison', L.srgb(88, 59, 36), var=0.16, var_scale=5.0, blotch=0.30,
                       extra=bison_hide, **FUR)
M['bison_shag'] = L.surface('bison_shag', L.srgb(62, 41, 24), var=0.18, var_scale=6.0,
                            blotch=0.35, extra=bison_shag, **FUR)
M['bear'] = L.surface('bear', L.srgb(74, 51, 34), var=0.18, var_scale=5.0, blotch=0.35,
                      extra=bear_hide, **FUR)
M['muzzle'] = L.surface('muzzle', L.srgb(112, 86, 58), var=0.14, var_scale=8.0, blotch=0.3,
                        **FUR)
M['goat'] = L.surface('goat', L.srgb(158, 110, 60), var=0.13, var_scale=6.0, blotch=0.25,
                      extra=goat_hide, **FUR)
M['goat_face'] = L.surface('goat_face', L.srgb(154, 108, 58), var=0.12, var_scale=9.0,
                           blotch=0.22, extra=goat_face, **FUR)
M['hawk'] = L.surface('hawk', L.srgb(88, 62, 42), var=0.15, var_scale=7.0, blotch=0.28,
                      extra=hawk_plume, **dict(FUR, bump_scale=200.0, bump=0.3, dust=0.0,
                                               ao_dist=0.05, rough=0.62))
HARD = dict(metal=0.0, wear=0.0, bevel_normal=False, ao=0.6, ao_dist=0.08, **DUSTY)
M['horn'] = L.surface('horn', L.srgb(56, 50, 46), var=0.16, var_scale=14.0, rough=0.42,
                      blotch=0.3, grain='Z', grain_amt=0.35, grain_freq=9.0, bump=0.22,
                      bump_scale=180.0, **HARD)
M['hoof'] = L.surface('hoof', L.srgb(42, 37, 34), var=0.14, var_scale=18.0, rough=0.38,
                      bump=0.18, bump_scale=200.0, **HARD)
M['eye'] = L.surface('eye', L.srgb(18, 13, 10), var=0.05, var_scale=30.0, rough=0.18,
                     bump=0.0, **HARD)
M['beak'] = L.surface('beak', L.srgb(176, 154, 96), var=0.12, var_scale=20.0, rough=0.35,
                      bump=0.12, bump_scale=220.0, **HARD)

# ----------------------------------------------------------------------------
# parts / nodes
# ----------------------------------------------------------------------------
PARTS = []
PIVOTS = {}     # (animal, sub) -> world pivot point


def P(name, bm, mat, animal, sub=None, smooth=55, prio=1.0):
    """sub='LegFL' keeps the part out of the animal's joined root mesh and exports
    it as a child node <Animal>_<sub> with its origin on PIVOTS[animal, sub]."""
    ob = L.obj_from_bm(name, bm, mat, smooth=smooth,
                       props=dict(animal=animal, sub=sub or '', prio=prio))
    PARTS.append(ob)
    return ob


def body(bm, secs, n=12, xc=0.0):
    """Loft a run of cross sections along Y.  Each section is
    (y, z_top, z_bottom, half_width[, k_top, k_bottom]) — k pinches the top or
    bottom of the ellipse (a bison hump is a narrow ridge, a brisket is a keel).
    xc shifts the whole run sideways (a paw under a leg)."""
    rings = []
    for s in secs:
        y, zt, zb, hw = s[0], s[1], s[2], s[3]
        ktop = s[4] if len(s) > 4 else 1.0
        kbot = s[5] if len(s) > 5 else 1.0
        zc, hz = (zt + zb) / 2.0, (zt - zb) / 2.0
        ring = []
        for i in range(n):
            a = 2 * math.pi * i / n
            sa, ca = math.sin(a), math.cos(a)
            k = ktop if ca > 0 else kbot
            ring.append((xc + hw * sa * (1 + (k - 1) * abs(ca)), y, zc + hz * ca))
        rings.append(ring)
    L.add_loft(bm, rings)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return rings


def limb(bm, pts, radii, n=7):
    """Tapered round limb through pts (world), one radius per point."""
    rmax = max(radii)
    L.add_sweep(bm, [Vector(p) for p in pts], L.circle_profile(rmax, n),
                scales=[r / rmax for r in radii], uv=None, up=(0, 0, 1), caps=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def blob(bm, loc, size):
    """20-tri icosahedral ellipsoid — eyes, nose pads, the tail tassel."""
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0,
                               matrix=L.mat_trs(loc, (0, 0, 0), size))


def ear(bm, base, tip, r0, r1, n=6):
    """Blunt leaf-shaped ear: a bulge two thirds of the way out, then a point."""
    b, t = Vector(base), Vector(tip)
    limb(bm, [b, b.lerp(t, 0.45), b.lerp(t, 0.80), t], [r0 * 0.75, r0, r0 * 0.62, r1], n)


def eyes(bm, loc, r=0.022):
    for sx in (1, -1):
        blob(bm, (sx * loc[0], loc[1], loc[2]), (r, r * 0.8, r))


# ============================================================================
# BUFFALO — American bison.  2.8 m nose to tail, 1.70 m at the hump.
# Silhouette: enormous shoulder hump, head carried low and shaggy, short legs,
# narrow sloping hindquarters.
# ============================================================================
log('buffalo')
A = 'Buffalo'
BUF_NECK = (0.0, -0.70, 1.32)

bm = bmesh.new()
body(bm, [
    (-0.82, 1.200, 0.82, 0.200, 0.80, 0.66),
    (-0.72, 1.420, 0.74, 0.300, 0.60, 0.74),
    (-0.60, 1.600, 0.68, 0.380, 0.48, 0.84),
    (-0.46, 1.700, 0.66, 0.425, 0.44, 0.90),
    (-0.28, 1.655, 0.66, 0.440, 0.48, 0.94),
    (-0.08, 1.490, 0.68, 0.420, 0.60, 0.98),
    (0.12, 1.335, 0.76, 0.365, 0.78, 1.00),
    (0.36, 1.245, 0.86, 0.315, 0.90, 1.00),
    (0.60, 1.205, 0.94, 0.265, 1.00, 1.00),
    (0.80, 1.170, 1.01, 0.190, 1.00, 1.00),
    (0.93, 1.130, 1.06, 0.090, 1.00, 1.00),
], 12)
P('buf_body', bm, M['bison'], A, smooth=60)

bm = bmesh.new()   # brisket / dewlap: the long hair hanging under the chest
body(bm, [
    (-0.80, 1.05, 0.68, 0.11, 0.9, 0.45),
    (-0.66, 1.02, 0.50, 0.17, 0.9, 0.40),
    (-0.50, 1.00, 0.54, 0.18, 0.9, 0.45),
    (-0.36, 0.98, 0.68, 0.13, 0.9, 0.55),
], 8)
P('buf_brisket', bm, M['bison_shag'], A, smooth=60, prio=0.9)

bm = bmesh.new()   # tail with its tassel
limb(bm, [(0, 0.94, 1.08), (0, 1.06, 0.94), (0, 1.12, 0.78), (0, 1.145, 0.64)],
     [0.055, 0.032, 0.024, 0.030], 6)
blob(bm, (0.0, 1.155, 0.575), (0.055, 0.105, 0.070))
P('buf_tail', bm, M['bison_shag'], A, smooth=60, prio=0.7)

# --- head + neck (one child node, pivot at the base of the neck)
bm = bmesh.new()
body(bm, [
    (-0.64, 1.44, 0.94, 0.290, 0.66, 0.9),
    (-0.80, 1.43, 0.86, 0.266, 0.72, 0.9),
    (-0.94, 1.34, 0.83, 0.235, 0.80, 0.95),
    (-1.06, 1.32, 0.80, 0.222, 0.90, 1.0),
    (-1.18, 1.28, 0.79, 0.200, 1.0, 1.0),
    (-1.30, 1.16, 0.81, 0.148, 1.0, 1.0),
    (-1.40, 1.07, 0.84, 0.106, 1.0, 1.0),
    (-1.48, 1.02, 0.88, 0.078, 1.0, 1.0),
], 10)
P('buf_headmass', bm, M['bison_shag'], A, sub='Head', smooth=60, prio=1.15)

bm = bmesh.new()   # shaggy forehead cap + chin beard, the bison's signature
body(bm, [
    (-1.00, 1.38, 1.08, 0.225, 0.85, 1.0),
    (-1.14, 1.35, 1.04, 0.210, 0.9, 1.0),
    (-1.26, 1.24, 1.01, 0.155, 1.0, 1.0),
], 8)
body(bm, [
    (-1.04, 0.92, 0.72, 0.105, 0.9, 0.45),
    (-1.20, 0.94, 0.60, 0.110, 0.9, 0.45),
    (-1.34, 0.93, 0.66, 0.088, 0.9, 0.55),
    (-1.42, 0.92, 0.79, 0.056, 0.9, 0.8),
], 8)
P('buf_mane', bm, M['bison_shag'], A, sub='Head', smooth=60, prio=1.1)

bm = bmesh.new()   # muzzle
blob(bm, (0.0, -1.50, 0.965), (0.078, 0.060, 0.058))
P('buf_nose', bm, M['muzzle'], A, sub='Head', smooth=50, prio=0.8)

bm = bmesh.new()   # horns: short and thick, out of the cap then up and in
for sx in (1, -1):
    limb(bm, [(sx * 0.108, -1.155, 1.225), (sx * 0.195, -1.185, 1.212),
              (sx * 0.262, -1.195, 1.255), (sx * 0.286, -1.195, 1.325),
              (sx * 0.266, -1.188, 1.372)],
         [0.060, 0.050, 0.038, 0.024, 0.007], 6)
P('buf_horn', bm, M['horn'], A, sub='Head', smooth=40, prio=0.8)

bm = bmesh.new()
for sx in (1, -1):
    ear(bm, (sx * 0.160, -1.070, 1.130), (sx * 0.300, -1.010, 1.105), 0.046, 0.010, 6)
P('buf_ear', bm, M['bison_shag'], A, sub='Head', smooth=50, prio=0.7)

bm = bmesh.new()
eyes(bm, (0.178, -1.238, 1.115), 0.028)
P('buf_eye', bm, M['eye'], A, sub='Head', smooth=50, prio=0.5)
PIVOTS[(A, 'Head')] = BUF_NECK

# --- legs: short, heavy, the forelegs wearing shaggy chaps
for tag, (py, pz, px, fore) in (('LegFL', (-0.50, 0.98, 0.225, 1)),
                                ('LegFR', (-0.50, 0.98, -0.225, 1)),
                                ('LegRL', (0.56, 1.02, 0.200, 0)),
                                ('LegRR', (0.56, 1.02, -0.200, 0))):
    bm = bmesh.new()
    if fore:
        pts = [(px * 0.62, py, pz + 0.09), (px * 0.92, py - 0.01, pz - 0.10),
               (px * 0.88, py - 0.02, 0.52), (px * 0.86, py, 0.30),
               (px * 0.86, py + 0.01, 0.13), (px * 0.86, py + 0.005, 0.085)]
        rad = [0.120, 0.155, 0.105, 0.072, 0.062, 0.070]
    else:
        pts = [(px * 0.60, py - 0.01, pz + 0.08), (px * 0.92, py + 0.04, pz - 0.16),
               (px * 0.90, py - 0.02, 0.50), (px * 0.90, py + 0.02, 0.28),
               (px * 0.90, py + 0.01, 0.13), (px * 0.90, py + 0.005, 0.085)]
        rad = [0.105, 0.135, 0.090, 0.062, 0.055, 0.062]
    limb(bm, pts, rad, 7)
    P('buf_%s' % tag, bm, M['bison_shag'] if fore else M['bison'], A, sub=tag,
      smooth=60, prio=0.85)
    bm = bmesh.new()   # cloven hoof
    limb(bm, [(pts[-1][0], pts[-1][1], 0.10), (pts[-1][0], pts[-1][1] - 0.012, 0.012)],
         [0.070, 0.080], 6)
    P('buf_%s_hoof' % tag, bm, M['hoof'], A, sub=tag, smooth=40, prio=0.5)
    PIVOTS[(A, tag)] = (px, py, pz)

# ============================================================================
# BEAR — 2.0 m nose to tail, 1.10 m at the shoulder.  Heavy shoulder hump,
# rounded ears, blunt snout, flat plantigrade paws, no tail to speak of.
# ============================================================================
log('bear')
A = 'Bear'
BEAR_NECK = (0.0, -0.52, 0.92)

bm = bmesh.new()
body(bm, [
    (-0.62, 0.98, 0.50, 0.15, 0.85, 0.85),
    (-0.52, 1.10, 0.44, 0.215, 0.72, 0.90),
    (-0.40, 1.160, 0.40, 0.255, 0.66, 0.95),
    (-0.22, 1.125, 0.385, 0.270, 0.78, 1.0),
    (0.0, 1.050, 0.385, 0.265, 0.92, 1.0),
    (0.24, 1.020, 0.40, 0.258, 1.0, 1.0),
    (0.48, 1.010, 0.44, 0.238, 1.0, 1.0),
    (0.68, 0.980, 0.50, 0.198, 1.0, 1.0),
    (0.84, 0.900, 0.58, 0.125, 1.0, 1.0),
    (0.92, 0.820, 0.64, 0.055, 1.0, 1.0),
], 12)
limb(bm, [(0, 0.88, 0.80), (0, 0.98, 0.74)], [0.055, 0.035], 6)   # stub tail
P('bear_body', bm, M['bear'], A, smooth=60)

bm = bmesh.new()   # head + neck
body(bm, [
    (-0.44, 1.020, 0.540, 0.195, 0.85, 0.90),
    (-0.58, 1.008, 0.600, 0.178, 0.88, 0.92),
    (-0.70, 0.992, 0.662, 0.162, 0.95, 1.0),
    (-0.80, 0.972, 0.702, 0.146, 1.0, 1.0),
    (-0.87, 0.944, 0.740, 0.100, 1.0, 1.0),
    (-0.93, 0.924, 0.766, 0.074, 1.0, 1.0),
    (-0.975, 0.906, 0.792, 0.046, 1.0, 1.0),
], 10)
P('bear_head', bm, M['bear'], A, sub='Head', smooth=60, prio=1.2)

bm = bmesh.new()   # tan snout
body(bm, [
    (-0.845, 0.938, 0.742, 0.096, 1.0, 1.0),
    (-0.915, 0.926, 0.766, 0.079, 1.0, 1.0),
    (-0.975, 0.906, 0.790, 0.050, 1.0, 1.0),
], 8)
blob(bm, (0.0, -0.995, 0.850), (0.040, 0.026, 0.028))           # rounded nose end
P('bear_snout', bm, M['muzzle'], A, sub='Head', smooth=55, prio=0.9)

bm = bmesh.new()   # round ears, set into the skull
for sx in (1, -1):
    L.add_cyl(bm, 0.064, 0.056, 0.026, 8, loc=(sx * 0.092, -0.668, 0.988),
              rot=(0, math.pi / 2 * sx, 0))
P('bear_ear', bm, M['bear'], A, sub='Head', smooth=45, prio=0.7)

bm = bmesh.new()
eyes(bm, (0.086, -0.838, 0.912), 0.019)
blob(bm, (0.0, -1.006, 0.852), (0.030, 0.020, 0.022))           # nose pad
P('bear_face', bm, M['eye'], A, sub='Head', smooth=50, prio=0.6)
PIVOTS[(A, 'Head')] = BEAR_NECK

for tag, (py, pz, px, fore) in (('LegFL', (-0.42, 0.80, 0.180, 1)),
                                ('LegFR', (-0.42, 0.80, -0.180, 1)),
                                ('LegRL', (0.46, 0.80, 0.175, 0)),
                                ('LegRR', (0.46, 0.80, -0.175, 0))):
    bm = bmesh.new()
    if fore:
        pts = [(px * 0.62, py, pz + 0.10), (px * 0.94, py - 0.02, pz - 0.14),
               (px * 0.92, py - 0.03, 0.34), (px * 0.90, py - 0.03, 0.16),
               (px * 0.90, py - 0.05, 0.055)]
        rad = [0.100, 0.128, 0.098, 0.086, 0.076]
    else:
        pts = [(px * 0.60, py + 0.02, pz + 0.10), (px * 0.94, py + 0.06, pz - 0.16),
               (px * 0.92, py - 0.04, 0.32), (px * 0.90, py - 0.04, 0.15),
               (px * 0.90, py - 0.06, 0.055)]
        rad = [0.108, 0.145, 0.094, 0.082, 0.072]
    limb(bm, pts, rad, 7)
    # flat plantigrade paw
    body(bm, [
        (pts[-1][1] + 0.050, 0.086, 0.006, 0.062, 1.0, 1.0),
        (pts[-1][1] - 0.035, 0.080, 0.0, 0.076, 1.0, 1.0),
        (pts[-1][1] - 0.090, 0.052, 0.0, 0.068, 1.0, 1.0),
        (pts[-1][1] - 0.118, 0.028, 0.0, 0.042, 1.0, 1.0),
    ], 8, xc=pts[-1][0])
    P('bear_%s' % tag, bm, M['bear'], A, sub=tag, smooth=60, prio=0.9)
    PIVOTS[(A, tag)] = (px, py, pz)

# ============================================================================
# GOAT — pronghorn.  1.2 m nose to rump, 0.90 m at the shoulder.  Slender legs,
# white belly / rump / throat bands, black pronged horns.
# ============================================================================
log('goat')
A = 'Goat'
GOAT_NECK = (0.0, -0.34, 0.80)

bm = bmesh.new()
body(bm, [
    (-0.40, 0.84, 0.60, 0.075, 0.9, 0.9),
    (-0.30, 0.905, 0.545, 0.112, 0.82, 0.95),
    (-0.18, 0.920, 0.510, 0.134, 0.80, 1.0),
    (0.0, 0.890, 0.495, 0.142, 0.88, 1.0),
    (0.18, 0.880, 0.510, 0.138, 0.95, 1.0),
    (0.34, 0.870, 0.555, 0.120, 1.0, 1.0),
    (0.46, 0.820, 0.610, 0.082, 1.0, 1.0),
    (0.52, 0.780, 0.655, 0.040, 1.0, 1.0),
], 12)
blob(bm, (0.0, 0.50, 0.745), (0.068, 0.055, 0.058))             # white rump puff
P('goat_body', bm, M['goat'], A, smooth=60)

bm = bmesh.new()   # neck + head
body(bm, [
    (-0.30, 0.900, 0.660, 0.098, 0.9, 0.95),
    (-0.40, 0.975, 0.740, 0.086, 0.9, 0.95),
    (-0.50, 1.045, 0.812, 0.076, 0.95, 1.0),
    (-0.575, 1.090, 0.858, 0.070, 1.0, 1.0),
    (-0.645, 1.078, 0.862, 0.060, 1.0, 1.0),
    (-0.715, 1.030, 0.862, 0.046, 1.0, 1.0),
    (-0.775, 0.990, 0.872, 0.034, 1.0, 1.0),
], 10)
P('goat_head', bm, M['goat_face'], A, sub='Head', smooth=60, prio=1.4)

bm = bmesh.new()   # pronged horns
for sx in (1, -1):
    limb(bm, [(sx * 0.036, -0.600, 1.075), (sx * 0.046, -0.578, 1.150),
              (sx * 0.054, -0.562, 1.222), (sx * 0.050, -0.582, 1.284),
              (sx * 0.040, -0.614, 1.316)],
         [0.031, 0.022, 0.015, 0.010, 0.004], 6)
    limb(bm, [(sx * 0.050, -0.570, 1.198), (sx * 0.052, -0.616, 1.222)],
         [0.013, 0.004], 5)                                     # forward prong
P('goat_horn', bm, M['horn'], A, sub='Head', smooth=40, prio=0.8)

bm = bmesh.new()
for sx in (1, -1):
    ear(bm, (sx * 0.044, -0.574, 1.026), (sx * 0.152, -0.532, 1.098), 0.032, 0.005, 6)
P('goat_ear', bm, M['goat_face'], A, sub='Head', smooth=50, prio=0.7)

bm = bmesh.new()
eyes(bm, (0.058, -0.640, 0.995), 0.019)
blob(bm, (0.0, -0.792, 0.952), (0.030, 0.022, 0.024))
P('goat_face', bm, M['eye'], A, sub='Head', smooth=50, prio=0.5)
PIVOTS[(A, 'Head')] = GOAT_NECK

for tag, (py, pz, px, fore) in (('LegFL', (-0.26, 0.74, 0.092, 1)),
                                ('LegFR', (-0.26, 0.74, -0.092, 1)),
                                ('LegRL', (0.30, 0.76, 0.088, 0)),
                                ('LegRR', (0.30, 0.76, -0.088, 0))):
    bm = bmesh.new()
    if fore:
        pts = [(px * 0.55, py, pz + 0.06), (px * 0.85, py - 0.01, pz - 0.10),
               (px * 0.92, py - 0.015, 0.36), (px * 0.90, py, 0.14),
               (px * 0.90, py + 0.005, 0.075)]
        rad = [0.040, 0.052, 0.032, 0.022, 0.020]
    else:
        pts = [(px * 0.55, py - 0.01, pz + 0.06), (px * 0.85, py + 0.05, pz - 0.14),
               (px * 0.92, py - 0.03, 0.34), (px * 0.90, py - 0.01, 0.14),
               (px * 0.90, py - 0.005, 0.075)]
        rad = [0.044, 0.058, 0.030, 0.021, 0.019]
    limb(bm, pts, rad, 6)
    P('goat_%s' % tag, bm, M['goat'], A, sub=tag, smooth=60, prio=0.8)
    bm = bmesh.new()
    limb(bm, [(pts[-1][0], pts[-1][1], 0.085), (pts[-1][0], pts[-1][1] - 0.010, 0.008)],
         [0.021, 0.028], 6)
    P('goat_%s_hoof' % tag, bm, M['hoof'], A, sub=tag, smooth=40, prio=0.5)
    PIVOTS[(A, tag)] = (px, py, pz)

# ============================================================================
# HAWK — 1.10 m wingspan, wings spread for gliding.  Origin at the body centre
# (it is never on the ground), head at -Y so it flies the way it faces.
# ============================================================================
log('hawk')
A = 'Hawk'

bm = bmesh.new()   # body: breast, belly, tail base
body(bm, [
    (-0.185, 0.026, -0.018, 0.016),
    (-0.155, 0.044, -0.034, 0.034),
    (-0.110, 0.054, -0.052, 0.050),
    (-0.045, 0.052, -0.056, 0.054),
    (0.030, 0.044, -0.046, 0.046),
    (0.100, 0.034, -0.032, 0.034),
    (0.160, 0.026, -0.020, 0.023),
    (0.200, 0.020, -0.012, 0.015),
], 10)
# head, tucked forward of the shoulders
body(bm, [
    (-0.140, 0.056, -0.026, 0.038),
    (-0.180, 0.052, -0.020, 0.034),
    (-0.212, 0.038, -0.014, 0.022),
], 8)
# broad fanned tail
body(bm, [
    (0.175, 0.010, -0.005, 0.030),
    (0.245, 0.008, -0.004, 0.080),
    (0.320, 0.007, -0.004, 0.110),
    (0.385, 0.006, -0.004, 0.115),
    (0.412, 0.005, -0.003, 0.098),
], 8)
# legs tucked up under the tail
for sx in (1, -1):
    limb(bm, [(sx * 0.022, -0.020, -0.042), (sx * 0.028, 0.045, -0.050),
              (sx * 0.024, 0.085, -0.038)], [0.018, 0.013, 0.009], 5)
P('hawk_body', bm, M['hawk'], A, smooth=60, prio=1.5)

bm = bmesh.new()   # short hooked beak
limb(bm, [(0, -0.212, 0.028), (0, -0.232, 0.022), (0, -0.244, 0.008)],
     [0.016, 0.011, 0.003], 6)
P('hawk_beak', bm, M['beak'], A, smooth=40, prio=0.6)
bm = bmesh.new()
eyes(bm, (0.024, -0.196, 0.034), 0.010)
P('hawk_eye', bm, M['eye'], A, smooth=50, prio=0.5)

# wings: spread, thin, slight dihedral, swept trailing edge, fingered primaries
WING = [   # (x, y_leading, y_trailing, z, thickness)
    (0.030, -0.098, 0.100, 0.010, 0.026),
    (0.075, -0.116, 0.098, 0.018, 0.020),
    (0.145, -0.126, 0.100, 0.026, 0.016),
    (0.215, -0.128, 0.112, 0.031, 0.013),
    (0.285, -0.124, 0.124, 0.035, 0.010),
    (0.345, -0.112, 0.132, 0.037, 0.008),
    (0.395, -0.092, 0.132, 0.038, 0.006),
    (0.430, -0.066, 0.118, 0.037, 0.004),
]
PRIM = [   # fingered primaries fanning off the wrist, (dx, dy_tip)
    (0.072, 0.020), (0.058, 0.060), (0.038, 0.098), (0.014, 0.128), (-0.012, 0.148),
]
for tag, sx in (('WingL', 1), ('WingR', -1)):
    bm = bmesh.new()
    rings = []
    for (x, yl, yt, z, th) in WING:
        c = yt - yl
        rings.append([
            (sx * x, yl, z),
            (sx * x, yl + 0.30 * c, z + th * 0.50),
            (sx * x, yt - 0.28 * c, z + th * 0.28),
            (sx * x, yt, z - th * 0.06),
            (sx * x, yt - 0.28 * c, z - th * 0.30),
            (sx * x, yl + 0.30 * c, z - th * 0.50),
        ])
    if sx < 0:
        rings = [list(reversed(r)) for r in rings]
    L.add_loft(bm, rings)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    # primaries: flat tapered slabs off the wingtip, fanned
    wx, wyl, wyt, wz, wth = WING[-1]
    for k, (dx, dy) in enumerate(PRIM):
        x0 = wx - 0.02 - 0.012 * k
        y0 = wyl + 0.02 + 0.030 * k
        x1 = wx + 0.040 + dx
        y1 = y0 + dy
        hw = 0.019 - 0.0012 * k
        zz = wz + 0.002 * k
        quad = [
            [(sx * x0, y0 - hw, zz + 0.003), (sx * x0, y0 + hw, zz + 0.003),
             (sx * x0, y0 + hw, zz - 0.003), (sx * x0, y0 - hw, zz - 0.003)],
            [(sx * (x0 + (x1 - x0) * 0.55), y0 + (y1 - y0) * 0.5 - hw * 0.85, zz + 0.0038),
             (sx * (x0 + (x1 - x0) * 0.55), y0 + (y1 - y0) * 0.5 + hw * 0.85, zz + 0.0038),
             (sx * (x0 + (x1 - x0) * 0.55), y0 + (y1 - y0) * 0.5 + hw * 0.85, zz - 0.0018),
             (sx * (x0 + (x1 - x0) * 0.55), y0 + (y1 - y0) * 0.5 - hw * 0.85, zz - 0.0018)],
            [(sx * x1, y1 - hw * 0.30, zz + 0.004), (sx * x1, y1 + hw * 0.30, zz + 0.004),
             (sx * x1, y1 + hw * 0.30, zz + 0.001), (sx * x1, y1 - hw * 0.30, zz + 0.001)],
        ]
        if sx < 0:
            quad = [list(reversed(r)) for r in quad]
        L.add_loft(bm, quad)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    P('hawk_%s' % tag, bm, M['hawk'], A, sub=tag, smooth=70, prio=1.5)
    PIVOTS[(A, tag)] = (sx * 0.028, -0.010, 0.014)

# ----------------------------------------------------------------------------
# lay the animals apart in X so ambient occlusion does not bleed between them
# ----------------------------------------------------------------------------
OFFS = {'Buffalo': 0.0, 'Bear': 3.2, 'Goat': 5.8, 'Hawk': 7.6}
for o in PARTS:
    o.location.x = OFFS[o['animal']]
bpy.context.view_layer.update()

tot = {}
for o in PARTS:
    tot[o['animal']] = tot.get(o['animal'], 0) + L.tri_count(o)
    log('  %-18s %5d  %s' % (o.name, L.tri_count(o), o['sub'] or '-'))
log('tris per animal', tot)

if GEOM:
    for a in ('Buffalo', 'Bear', 'Goat', 'Hawk'):
        objs = [o for o in PARTS if o['animal'] == a]
        pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
        log('%-9s tris %5d  L %.3f m  W %.3f  H %.3f  (y %.3f..%.3f, z %.3f..%.3f)'
            % (a, sum(L.tri_count(o) for o in objs),
               max(p.y for p in pts) - min(p.y for p in pts),
               max(p.x for p in pts) - min(p.x for p in pts),
               max(p.z for p in pts) - min(p.z for p in pts),
               min(p.y for p in pts), max(p.y for p in pts),
               min(p.z for p in pts), max(p.z for p in pts)))
    log('geometry only — stopping before bake')
    sys.exit(0)

# ----------------------------------------------------------------------------
# bake one shared atlas
# ----------------------------------------------------------------------------
L.uv_atlas(PARTS, margin=0.006 if TEX >= 1024 else 0.012)
IMGS = {}
for kind in ('color', 'orm', 'normal'):
    img = L.new_image('anim_%s' % kind, TEX, non_color=(kind != 'color'))
    log('bake', kind)
    L.bake_pass(PARTS, img, kind)
    L.save_image(img, os.path.join(BUILD, 'animals_%s.png' % kind))
    IMGS[kind] = img
conv = []
for kind in IMGS:
    q = {'color': 88, 'orm': 82, 'normal': 88}[kind]
    conv += [os.path.join(BUILD, 'animals_%s.png' % kind),
             os.path.join(BUILD, 'animals_%s.jpg' % kind), str(q)]
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
    im = bpy.data.images.load(os.path.join(BUILD, 'animals_%s.jpg' % kind))
    im.name = 'Animals_%s' % kind
    if kind != 'color':
        im.colorspace_settings.name = 'Non-Color'
    FIN[kind] = im
mat = L.final_material('Animals', FIN['color'], FIN['orm'], FIN['normal'])
for o in PARTS:
    L.assign_single_material(o, mat)
    L.strip_uvs(o)
    o.location.x = 0.0
bpy.context.view_layer.update()

# ----------------------------------------------------------------------------
# join into root + animated child nodes
# ----------------------------------------------------------------------------
GROUPS = {}
for o in PARTS:
    GROUPS.setdefault(o['animal'], []).append(o)

for a in ('Buffalo', 'Bear', 'Goat', 'Hawk'):
    objs = list(GROUPS[a])
    subs = {}
    for o in list(objs):
        tag = o.get('sub') or ''
        if tag:
            subs.setdefault(tag, []).append(o)
            objs.remove(o)
    root = L.join(objs, a)
    for key in list(root.keys()):
        del root[key]
    for tag in sorted(subs):
        sob = L.join(subs[tag], '%s_%s' % (a, tag))
        for key in list(sob.keys()):
            del sob[key]
        bpy.context.view_layer.update()
        L.set_origin(sob, Vector(PIVOTS[(a, tag)]))
        L.parent_keep(sob, root)
        log('  node %-14s %5d tris  pivot (%.3f %.3f %.3f)'
            % (sob.name, L.tri_count(sob), *PIVOTS[(a, tag)]))
    bpy.context.view_layer.update()
    kids = [c for c in root.children]
    pts = [o.matrix_world @ Vector(c) for o in [root] + kids for c in o.bound_box]
    log('%-9s root %5d tris, total %5d  L %.2f m  H %.2f m'
        % (a, L.tri_count(root), L.tri_count(root) + sum(L.tri_count(k) for k in kids),
           max(p.y for p in pts) - min(p.y for p in pts),
           max(p.z for p in pts) - min(p.z for p in pts)))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'animals.blend'), compress=True)
L.export_glb(OUT)
log('exported', OUT, '%.0f KB' % (os.path.getsize(OUT) / 1024))
