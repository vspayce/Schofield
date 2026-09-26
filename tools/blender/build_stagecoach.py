"""Build public/assets/models/stagecoach.glb — SCHOFIELD's Concord stagecoach.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_stagecoach.py [-- --quick]

Pipeline: bmesh geometry (Blender space: faces -Y, Z up, LEFT = +X) with procedural
weathered materials -> two 1024 atlases baked in Cycles (colour+AO, rough/metal,
tangent normals incl. rounded-edge bevel normals) -> plain Principled materials ->
GLB (export_yup: coach faces +Z in three.js).

Node contract (DESIGN.md):
  Stagecoach (root empty, ground origin)
    Chassis  (running gear, thoroughbraces, pole)   children: Wheel_FL/FR/RL/RR, Hitch
    Body     (everything that rocks on the braces)  children: Seat_Driver, Seat_Guard,
                                                              Lamp_L, Lamp_R
  Wheels: origin at hub, axle = local X.  Body origin = bottom-centre of the shell,
  on the thoroughbraces (natural pitch/roll pivot).
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
import sch_lib as L          # noqa: E402
import coach_dims as D       # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
QUICK = '--quick' in ARGS
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'models', 'stagecoach.glb')
BUILD = os.path.join(HERE, 'build', 'stagecoach')
SRC_TEX = os.path.join(HERE, 'src_tex')
TEX = 256 if QUICK else 1024
SAMPLES = 6 if QUICK else 64

YC = D.YC
T0 = time.time()


def log(*a):
    print('[coach %5.1fs]' % (time.time() - T0), *a, flush=True)


# ----------------------------------------------------------------------------
# decals (PIL, system python)
# ----------------------------------------------------------------------------
py = shutil.which('python3') or '/usr/bin/python3'
try:
    subprocess.run([py, os.path.join(ROOT, 'tools', 'textures', 'coach_decals.py')], check=True)
except Exception as e:
    if not os.path.exists(os.path.join(SRC_TEX, 'coach_side_col.png')):
        raise
    print('decal regen failed, using existing:', e)

L.reset_scene()
L.setup_cycles(SAMPLES)


# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------

def load_img(name, non_color=False):
    img = bpy.data.images.load(os.path.join(SRC_TEX, name))
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


IMG = dict(side_col=load_img('coach_side_col.png'), side_gold=load_img('coach_side_gold.png', True),
           rear_col=load_img('coach_rear_col.png'), rear_gold=load_img('coach_rear_gold.png', True))


def body_decal(mb, st):
    P, N = mb.pos, mb.nrm
    x, y, z = mb.xyz(P)
    nx, ny, nz = mb.xyz(N)
    S, R = D.SIDE_DECAL, D.REAR_DECAL
    u = mb.m('DIVIDE', mb.m('SUBTRACT', y, S['y0']), S['y1'] - S['y0'])
    pos_x = mb.m('GREATER_THAN', x, 0.0)
    u = mb.mixf(pos_x, mb.m('SUBTRACT', 1.0, u), u)     # mirror on the right side
    v = mb.m('DIVIDE', mb.m('SUBTRACT', z, S['z0']), S['z1'] - S['z0'])
    sc, sa = mb.image(IMG['side_col'], mb.comb(u, v, 0))
    sg, _ = mb.image(IMG['side_gold'], mb.comb(u, v, 0))
    ws = mb.smooth(mb.m('ABSOLUTE', nx), 0.45, 0.7)
    ur = mb.m('DIVIDE', mb.m('SUBTRACT', R['x1'], x), R['x1'] - R['x0'])
    rear = mb.m('GREATER_THAN', ny, 0.0)
    ur = mb.mixf(rear, mb.m('SUBTRACT', 1.0, ur), ur)
    vr = mb.m('DIVIDE', mb.m('SUBTRACT', z, R['z0']), R['z1'] - R['z0'])
    rc, ra = mb.image(IMG['rear_col'], mb.comb(ur, vr, 0))
    rg, _ = mb.image(IMG['rear_gold'], mb.comb(ur, vr, 0))
    wr = mb.smooth(mb.m('ABSOLUTE', ny), 0.45, 0.7)
    a1 = mb.m('MULTIPLY', sa, ws)
    a2 = mb.m('MULTIPLY', ra, wr)
    st['col'] = mb.mixc(a1, st['col'], sc)
    st['col'] = mb.mixc(a2, st['col'], rc)
    gold = mb.m('ADD', mb.m('MULTIPLY', mb.xyz(sg)[0], ws), mb.m('MULTIPLY', mb.xyz(rg)[0], wr))
    gold = mb.m('MINIMUM', gold, 1.0)
    st['rough'] = mb.mixf(gold, st['rough'], 0.3)
    st['metal'] = mb.mixf(gold, 0.0, 0.6)


def rust(mb, st):
    r = mb.smooth(mb.noise(mb.pos, 4.0, 6.0, 0.7), 0.58, 0.72)
    st['col'] = mb.mixc(mb.m('MULTIPLY', r, 0.8), st['col'], L.srgb(98, 52, 28))
    st['rough'] = mb.mixf(r, st['rough'], 0.9)
    st['metal'] = mb.mixf(r, st['metal'], 0.1)


def stitches(mb, st):
    uvv = mb.uv('SweepUV')
    u, v, _ = mb.xyz(uvv)
    dash = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 2 * math.pi * 90)), 0.1, 0.5)
    lines = None
    for c in (0.035, 0.285, 0.535, 0.785):
        ln = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', v, c)), 0.004, 0.009))
        lines = ln if lines is None else mb.m('MAXIMUM', lines, ln)
    sm = mb.m('MULTIPLY', lines, dash)
    has = mb.m('GREATER_THAN', u, 0.0001)
    sm = mb.m('MULTIPLY', sm, has)
    st['col'] = mb.mixc(sm, st['col'], L.srgb(146, 108, 66))
    st['height'] = mb.m('SUBTRACT', st['height'], mb.m('MULTIPLY', sm, 0.4))


def rope_twist(mb, st):
    uvv = mb.uv('SweepUV')
    u, v, _ = mb.xyz(uvv)
    t = mb.m('FRACT', mb.m('ADD', mb.m('MULTIPLY', u, 34.0), mb.m('MULTIPLY', v, 3.0)))
    s = mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', t, 0.5)), 0.25, 0.5)
    st['col'] = mb.mixc(mb.m('MULTIPLY', s, 0.7), st['col'], L.srgb(70, 52, 32))
    st['height'] = mb.m('SUBTRACT', 1.0, s)


def trunk_bands(x_centres, width, col, lid_z=None):
    def f(mb, st):
        x, y, z = mb.xyz(mb.pos)
        band = None
        for xc in x_centres:
            b = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', x, xc)),
                                                width * 0.45, width * 0.55))
            band = b if band is None else mb.m('MAXIMUM', band, b)
        if lid_z is not None:
            seam = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', z, lid_z)),
                                                   0.004, 0.009))
            st['col'] = mb.mixc(seam, st['col'], L.srgb(20, 16, 12))
            st['height'] = mb.m('SUBTRACT', st['height'], seam)
        st['col'] = mb.mixc(band, st['col'], col)
        st['rough'] = mb.mixf(band, st['rough'], 0.55)
        st['height'] = mb.m('ADD', st['height'], mb.m('MULTIPLY', band, 0.6))
    return f


def carpet(mb, st):
    P = mb.pos
    a = mb.smooth(mb.noise(P, 14.0, 2.0, 0.4), 0.45, 0.55)
    st['col'] = mb.mixc(a, st['col'], L.srgb(46, 60, 40))
    d = mb.voronoi(P, 18.0)
    dots = mb.m('SUBTRACT', 1.0, mb.smooth(d, 0.12, 0.2))
    st['col'] = mb.mixc(mb.m('MULTIPLY', dots, 0.8), st['col'], L.srgb(170, 130, 60))


def blanket(mb, st):
    x, y, z = mb.xyz(mb.pos)
    s1 = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', x, 2 * math.pi * 2.4)), 0.72, 0.8)
    s2 = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', x, 2 * math.pi * 7.2)), 0.8, 0.88)
    st['col'] = mb.mixc(s1, st['col'], L.srgb(200, 180, 140))
    st['col'] = mb.mixc(s2, st['col'], L.srgb(24, 22, 26))


def crate_planks(mb, st):
    x, y, z = mb.xyz(mb.pos)
    g = mb.m('FRACT', mb.m('MULTIPLY', z, 1 / 0.1))
    line = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', g, 0.5)), 0.44, 0.48))
    line = mb.m('SUBTRACT', 1.0, line)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.m('SUBTRACT', 1.0, line), 0.0), st['col'], st['col'])
    edge = mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', g, 0.5)), 0.46, 0.5)
    st['col'] = mb.mixc(edge, st['col'], L.srgb(40, 28, 18))
    st['height'] = mb.m('SUBTRACT', st['height'], edge)


def stencil_mail(mb, st):
    pass


log('materials')
M = {}
M['paint'] = L.surface('paint', L.srgb(84, 23, 17), var=0.10, rough=0.36, rough_var=0.1,
                       wear_col=L.srgb(70, 46, 30), wear=0.9, wear_rough=0.75, edge_r=0.014,
                       scratches=0.45, dust=0.6, dust_z=(0.85, 2.3), dust_up=1.0, ao=0.75,
                       bump=0.06, bump_scale=35, streaks=0.35, extra=body_decal, blotch=0.25)
M['roof'] = L.surface('roof', L.srgb(66, 24, 18), var=0.12, rough=0.6, wear_col=L.srgb(84, 60, 40),
                      wear=0.8, dust=0.9, dust_up=1.4, dust_z=(1.0, 2.6), ao=0.75, grain='Y',
                      grain_amt=0.35, blotch=0.4, bump=0.2)
M['gear'] = L.surface('gear', L.srgb(178, 118, 38), var=0.12, rough=0.55, wear_col=L.srgb(92, 64, 40),
                      wear=0.9, wear_rough=0.8, scratches=0.4, dust=1.0, dust_z=(0.0, 1.5),
                      ao=0.75, streaks=0.3, blotch=0.35, bump=0.12, edge_r=0.012)
M['iron'] = L.surface('iron', L.srgb(40, 37, 34), var=0.15, rough=0.55, metal=0.6,
                      wear_col=L.srgb(150, 146, 138), wear=0.9, wear_rough=0.3, wear_metal=0.9,
                      dust=0.7, dust_z=(0.0, 1.5), extra=rust, bump=0.25, edge_r=0.008)
M['leather'] = L.surface('leather', L.srgb(64, 37, 21), var=0.18, rough=0.5, wear_col=L.srgb(124, 86, 52),
                         wear=0.8, wear_rough=0.7, dust=0.55, dust_z=(0.3, 2.2), bump=0.5,
                         bump_scale=28, blotch=0.4, extra=stitches, edge_r=0.01)
M['boot'] = L.surface('boot', L.srgb(44, 28, 20), var=0.2, rough=0.5, wear_col=L.srgb(110, 78, 50),
                      wear=0.8, wear_rough=0.7, dust=0.6, dust_up=1.0, dust_z=(0.8, 2.3), bump=0.9,
                      bump_scale=9, blotch=0.5, edge_r=0.02, ao=0.8)
M['blackleather'] = L.surface('blackleather', L.srgb(30, 22, 18), var=0.15, rough=0.45,
                              wear_col=L.srgb(88, 64, 44), wear=0.7, dust=0.5, dust_up=0.8, bump=0.45,
                              bump_scale=35, blotch=0.3)
M['brass'] = L.surface('brass', L.srgb(200, 150, 70), var=0.1, rough=0.3, metal=0.75,
                       wear_col=L.srgb(236, 200, 120), wear=0.6, wear_rough=0.2, dust=0.35, ao=0.8,
                       blotch=0.5, bump=0.05)
M['glass'] = L.surface('glass', L.srgb(70, 60, 40), var=0.2, rough=0.08, dust=0.4, bump=0.0, ao=0.5,
                       bevel_normal=False)
M['wood'] = L.surface('wood', L.srgb(112, 82, 54), var=0.15, rough=0.75, wear=0.6,
                      wear_col=L.srgb(150, 118, 84), grain='Y', grain_amt=0.6, dust=0.7, blotch=0.3)
M['interior'] = L.surface('interior', L.srgb(34, 14, 11), var=0.1, rough=0.8, dust=0.0, ao=0.9,
                          ao_dist=0.12, bump=0.0, bevel_normal=False)
M['canvas'] = L.surface('canvas', L.srgb(180, 162, 126), var=0.12, rough=0.9, dust=0.5, blotch=0.5,
                        bump=0.35, bump_scale=260)
M['rope'] = L.surface('rope', L.srgb(160, 130, 88), var=0.1, rough=0.9, dust=0.4, extra=rope_twist,
                      bump=0.7, bump_dist=0.004, bevel_normal=False)
M['trunkA'] = L.surface('trunkA', L.srgb(44, 58, 46), var=0.12, rough=0.5, wear_col=L.srgb(196, 146, 70),
                        wear=1.0, wear_metal=0.7, wear_rough=0.3, edge_w=(0.01, 0.08), edge_r=0.02,
                        dust=0.6, dust_up=1.0, extra=trunk_bands((0.22, 0.56), 0.05, L.srgb(70, 42, 24), 2.51))
M['trunkB'] = L.surface('trunkB', L.srgb(98, 60, 32), var=0.15, rough=0.55, wear_col=L.srgb(150, 110, 70),
                        wear=0.8, edge_r=0.02, dust=0.6, dust_up=1.0, blotch=0.4, bump=0.3, bump_scale=30,
                        extra=trunk_bands((-0.52, -0.22), 0.045, L.srgb(40, 26, 16), 2.46))
M['crate'] = L.surface('crate', L.srgb(140, 108, 70), var=0.18, rough=0.8, grain='X', grain_amt=0.5,
                       wear=0.5, wear_col=L.srgb(170, 140, 100), dust=0.7, dust_up=1.0, extra=crate_planks)
M['carpet'] = L.surface('carpet', L.srgb(112, 40, 32), var=0.1, rough=0.85, dust=0.5, bump=0.4,
                        bump_scale=220, extra=carpet)
M['blanket'] = L.surface('blanket', L.srgb(152, 44, 32), var=0.1, rough=0.95, dust=0.4, bump=0.3,
                         bump_scale=240, extra=blanket)

# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------
PARTS = []


def P(name, bm, mat, grp, atlas, prio=1.0, smooth=35):
    ob = L.obj_from_bm(name, bm, mat, smooth=smooth, props=dict(grp=grp, atlas=atlas, prio=prio))
    PARTS.append(ob)
    return ob


def recalc(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


REF_END = 1.166 - 0.09
WIN_COLS = [-0.97, -0.52, -0.23, 0.23, 0.52, 0.97]


def perimeter(z, hl, hw, cr, cy=YC):
    """38 points CCW (seen from above) around a rounded-rect ring."""
    e = hl - cr
    f = hw - cr
    if e > 1.0:
        cols = [-e] + WIN_COLS + [e]
    else:
        cols = [-e] + [c * e / REF_END for c in WIN_COLS] + [e]
    pts = []

    def corner(cx, cyy, a0):
        for k in (1, 2, 3):
            a = a0 + k * math.pi / 8
            pts.append((cx + cr * math.cos(a), cy + cyy + cr * math.sin(a), z))
    for c in cols:
        pts.append((hw, cy + c, z))
    corner(f, e, 0)
    for xx in (f, 0.5 * f, 0, -0.5 * f, -f):
        pts.append((xx, cy + hl, z))
    corner(-f, e, math.pi / 2)
    for c in reversed(cols):
        pts.append((-hw, cy + c, z))
    corner(-f, -e, math.pi)
    for xx in (-f, -0.5 * f, 0, 0.5 * f, f):
        pts.append((xx, cy - hl, z))
    corner(f, -e, 1.5 * math.pi)
    return pts


def in_ring(x, y, ring):
    z, hl, hw, cr = ring
    dx = abs(x) - (hw - cr)
    dy = abs(y - YC) - (hl - cr)
    if dx > cr or dy > cr:
        return False
    return math.hypot(max(dx, 0), max(dy, 0)) <= cr


def body_bottom(x, y):
    rs = D.rings_dense()
    for k in range(len(rs) - 1):
        a, b = rs[k], rs[k + 1]
        for s in range(10):
            t = s / 10
            r = tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
            if in_ring(x, y, r):
                return r[0]
    return None


# ----------------------------------------------------------------------------
# BODY
# ----------------------------------------------------------------------------
log('body shell')
rings = D.rings_dense()
bm = bmesh.new()
vr, faces = L.add_loft(bm, [perimeter(*r) for r in rings], cap0=True, cap1=False)
m = len(vr[0])
jw = [i for i, r in enumerate(rings) if abs(r[0] - D.WINDOW_Z[0]) < 1e-4][0]
win = [faces[jw * m + i] for i in (1, 3, 5, 20, 22, 24)]
fr = bmesh.ops.inset_individual(bm, faces=win, thickness=0.028, use_even_offset=True)
walls = bmesh.ops.inset_individual(bm, faces=win, thickness=0.004, depth=-0.075,
                                   use_even_offset=True)['faces']
for f in win + walls:
    f.material_index = 1
shell = P('shell', bm, [M['paint'], M['interior']], 'Body', 'A', 1.25, smooth=32)

log('roof')
bm = bmesh.new()
top = rings[-1]
rr = [perimeter(D.ROOF_Z, top[1] + 0.035, top[2] + 0.035, top[3] + 0.035),
      perimeter(D.ROOF_Z + 0.032, top[1] + 0.035, top[2] + 0.035, top[3] + 0.035),
      perimeter(D.ROOF_Z + 0.040, top[1] + 0.022, top[2] + 0.022, top[3] + 0.022),
      perimeter(D.ROOF_TOP, top[1] - 0.25, top[2] - 0.30, top[3])]
L.add_loft(bm, rr, cap0=True, cap1=True)
P('roof', bm, M['roof'], 'Body', 'A', 1.0, smooth=30)

log('rail')
bm = bmesh.new()
RX, RY0, RY1, RZ = 0.705, YC - 1.07, YC + 1.12, 2.415
rc = 0.07
path = []
for (cx, cy, a0) in ((RX - rc, RY1 - rc, 0), (-RX + rc, RY1 - rc, 90), (-RX + rc, RY0 + rc, 180),
                     (RX - rc, RY0 + rc, 270)):
    for k in range(4):
        a = math.radians(a0 + k * 30)
        path.append((cx + rc * math.cos(a), cy + rc * math.sin(a), RZ))
L.add_sweep(bm, path, L.rect_profile(0.024, 0.02, 0.006), closed_path=True, uv=None)
posts = []
for y in [RY0 + 0.02, RY0 + 0.45, YC - 0.2, YC + 0.3, YC + 0.72, RY1 - 0.02]:
    posts += [(RX, y), (-RX, y)]
for x in (-0.35, 0.0, 0.35):
    posts += [(x, RY1), (x, RY0)]
for (x, y) in posts:
    L.add_beam(bm, (x, y, D.ROOF_TOP - 0.03), (x, y, RZ), 0.016, 0.016, up=(0, 1, 0), caps=False)
P('rail', bm, M['iron'], 'Body', 'A', 0.7, smooth=40)

log('front boot, seat, footboard')
FW = YC - 1.166        # front wall y
bm = bmesh.new()
# front boot: leather-covered, rounded front
prof = [(0.0, 1.60), (-0.30, 1.60), (-0.38, 1.66), (-0.40, 1.90), (-0.38, 2.15), (-0.34, 2.22),
        (0.0, 2.22)]
rings_b = []
for (x, k) in ((-0.64, 0.92), (-0.61, 1.0), (0.61, 1.0), (0.64, 0.92)):
    rings_b.append([(x, FW + py * k, pz if pz in (1.60, 2.22) else pz) for (py, pz) in prof])
L.add_loft(bm, rings_b)
recalc(bm)
P('front_boot', bm, M['blackleather'], 'Body', 'A', 0.8, smooth=40)

bm = bmesh.new()
L.add_box(bm, (1.34, 0.40, 0.09), (0, FW - 0.19, 2.265), bevel=0.03, segs=2)      # cushion
L.add_box(bm, (1.34, 0.07, 0.30), (0, FW + 0.02, 2.42), rot=(math.radians(-8), 0, 0),
          bevel=0.025, segs=2)                                                      # back
P('seat', bm, M['blackleather'], 'Body', 'A', 0.7, smooth=40)

bm = bmesh.new()
L.add_box(bm, (1.46, 0.46, 0.04), (0, -1.72, 1.77), rot=(math.radians(-8), 0, 0), bevel=0.008)
P('footboard', bm, M['wood'], 'Body', 'A', 0.6, smooth=None)

bm = bmesh.new()
L.add_box(bm, (1.46, 0.035, 0.26), (0, -1.955, 1.90), rot=(math.radians(12), 0, 0), bevel=0.012)
P('dash', bm, M['blackleather'], 'Body', 'A', 0.6, smooth=None)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_rod(bm, [(sx * 0.60, FW + 0.02, 1.52), (sx * 0.66, -1.50, 1.64), (sx * 0.70, -1.90, 1.78)],
              0.012, 4)
    L.add_rod(bm, L.catmull([(sx * 0.67, FW - 0.02, 2.30), (sx * 0.70, FW - 0.03, 2.44),
                             (sx * 0.71, FW - 0.25, 2.45), (sx * 0.70, FW - 0.40, 2.30)], 3), 0.011, 4)
# brake lever (driver side = left = +X)
L.add_rod(bm, [(0.76, -1.62, 1.74), (0.78, -1.53, 2.44)], 0.014, 5)
L.add_box(bm, (0.035, 0.035, 0.08), (0.785, -1.525, 2.47))
L.add_rod(bm, [(0.76, -1.62, 1.76), (0.74, -1.30, 1.50), (0.74, -0.9, 1.30)], 0.01, 4)
P('front_irons', bm, M['iron'], 'Body', 'A', 0.4, smooth=40)

log('lamps')
for side, sx in (('L', 1), ('R', -1)):
    cx, cy, cz = sx * 0.84, FW + 0.10, 1.98
    Mx = Matrix.Translation((cx, cy, cz))
    bm = bmesh.new()
    L.add_lathe(bm, [(0.012, -0.17), (0.05, -0.13), (0.075, -0.095), (0.075, -0.075)], 4, Mx,
                cap0=True, phase=math.pi / 4)
    L.add_lathe(bm, [(0.075, 0.075), (0.088, 0.085), (0.088, 0.10), (0.05, 0.13), (0.028, 0.16),
                     (0.03, 0.21), (0.045, 0.22), (0.02, 0.24)], 4, Mx, cap1=True, phase=math.pi / 4)
    # bracket to the body
    L.add_beam(bm, (cx - sx * 0.03, cy, cz - 0.02), (sx * 0.735, cy, cz - 0.02), 0.03, 0.02)
    P('lamp_%s' % side, bm, M['brass'], 'Body', 'A', 0.9, smooth=30)
    bm = bmesh.new()
    L.add_lathe(bm, [(0.072, -0.078), (0.072, 0.078)], 4, Mx, phase=math.pi / 4)
    P('lampglass_%s' % side, bm, M['glass'], 'Body', 'A', 0.5, smooth=None)

log('door hardware, steps, curtains')
bm = bmesh.new()
for sx in (-1, 1):
    L.add_box(bm, (0.018, 0.09, 0.022), (sx * 0.772, YC + 0.24, 1.66), bevel=0.004)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
P('handles', bm, M['brass'], 'Body', 'A', 0.3)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_box(bm, (0.13, 0.24, 0.018), (sx * 0.80, YC, 0.905), bevel=0.004)
    L.add_rod(bm, [(sx * 0.55, YC - 0.08, 0.935), (sx * 0.80, YC - 0.08, 0.91)], 0.011, 4)
    L.add_rod(bm, [(sx * 0.55, YC + 0.08, 0.935), (sx * 0.80, YC + 0.08, 0.91)], 0.011, 4)
    # door hinges
    for zz in (1.30, 1.88):
        L.add_box(bm, (0.012, 0.07, 0.035), (sx * 0.772, YC - 0.31, zz), bevel=0.003)
P('steps', bm, M['iron'], 'Body', 'A', 0.4)

bm = bmesh.new()
for sx in (-1, 1):
    for (y0, y1) in D.WINDOWS_Y:
        L.add_rod(bm, [(sx * 0.70, YC + y0 + 0.01, 1.975), (sx * 0.70, YC + y1 - 0.01, 1.975)], 0.03, 6,
                  up=(0, 0, 1), uv='SweepUV')
    # one curtain let half down on each side
    y0, y1 = D.WINDOWS_Y[2] if sx > 0 else D.WINDOWS_Y[0]
    L.add_box(bm, (0.012, (y1 - y0) - 0.02, 0.19), (sx * 0.715, YC + (y0 + y1) / 2, 1.87), bevel=0.003)
P('curtains', bm, M['blackleather'], 'Body', 'A', 0.5)

log('rear boot')
RW = YC + 1.166    # rear wall y
prof = [(0.0, 1.975), (0.20, 1.955), (0.36, 1.905), (0.47, 1.805), (0.52, 1.645), (0.535, 1.45),
        (0.515, 1.315), (0.40, 1.295), (0.0, 1.295)]
prof = list(reversed(prof))
bm = bmesh.new()
lr = []
for (x, ky, kz, sag) in ((-0.63, 0.93, 0.95, 0), (-0.60, 0.985, 0.99, 0.004), (-0.3, 1, 1, 0.012),
                         (0.0, 1.01, 1, 0.016), (0.3, 1, 1, 0.012), (0.60, 0.985, 0.99, 0.004),
                         (0.63, 0.93, 0.95, 0)):
    ring = []
    for (py, pz) in prof:
        zz = 1.295 + (pz - 1.295) * kz
        if pz > 1.8 and py > 0.05:
            zz -= sag
        ring.append((x, RW + py * ky, zz))
    lr.append(ring)
L.add_loft(bm, lr)
recalc(bm)
P('rear_boot', bm, M['boot'], 'Body', 'A', 1.3, smooth=50)

bm = bmesh.new()
for sx in (-1, 1):
    pts = [(sx * 0.33, RW + py * 1.0 + 0.012 * (1 if py > 0.1 else 0), pz + (0.01 if pz > 1.8 else 0))
           for (py, pz) in [(0.0, 1.985), (0.20, 1.965), (0.36, 1.915), (0.475, 1.81), (0.53, 1.645),
                            (0.547, 1.45), (0.527, 1.31)]]
    L.add_sweep(bm, L.catmull(pts, 3), L.rect_profile(0.055, 0.008), up=(1, 0, 0), uv='SweepUV')
P('boot_straps', bm, M['leather'], 'Body', 'A', 0.6)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_box(bm, (0.075, 0.014, 0.06), (sx * 0.33, RW + 0.553, 1.60), bevel=0.003)
P('buckles', bm, M['brass'], 'Body', 'A', 0.3)

bm = bmesh.new()
L.add_box(bm, (1.34, 0.60, 0.05), (0, RW + 0.28, 1.265), bevel=0.01)
P('boot_platform', bm, M['wood'], 'Body', 'A', 0.6, smooth=None)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_rod(bm, [(sx * 0.675, RW + 0.56, 1.28), (sx * 0.675, RW + 0.01, 1.93)], 0.009, 4)
    L.add_box(bm, (0.03, 0.03, 0.02), (sx * 0.675, RW + 0.56, 1.28))
P('boot_chains', bm, M['iron'], 'Body', 'A', 0.3)

# ----------------------------------------------------------------------------
# LUGGAGE (Body group, atlas B). Rear-right (-X, +Y) is left clear for the guard.
# ----------------------------------------------------------------------------
log('luggage')
RT = 2.245
bm = bmesh.new()      # dome-top steamer trunk, front-left
tp = [(-0.21, 0.0), (0.21, 0.0), (0.21, 0.27), (0.17, 0.325), (0.09, 0.355), (0.0, 0.362),
      (-0.09, 0.355), (-0.17, 0.325), (-0.21, 0.27)]
tcx, tcy = 0.39, YC - 0.74
tr = []
for (x, k) in ((-0.31, 0.975), (-0.30, 1.0), (0.30, 1.0), (0.31, 0.975)):
    tr.append([(tcx + x, tcy + py * k, RT + pz * (1 if k == 1 else 0.985)) for (py, pz) in tp])
L.add_loft(bm, tr)
recalc(bm)
P('trunk_dome', bm, M['trunkA'], 'Body', 'B', 1.0, smooth=35)

bm = bmesh.new()      # flat leather trunk front-right + small case on top
L.add_box(bm, (0.60, 0.46, 0.30), (-0.37, YC - 0.76, RT + 0.15), rot=(0, 0, math.radians(4)),
          bevel=0.02, segs=2)
P('trunk_flat', bm, M['trunkB'], 'Body', 'B', 0.9, smooth=35)
bm = bmesh.new()
L.add_box(bm, (0.42, 0.28, 0.17), (-0.36, YC - 0.78, RT + 0.30 + 0.085), rot=(0, 0, math.radians(-14)),
          bevel=0.015, segs=2)
P('case', bm, M['crate'], 'Body', 'B', 0.7, smooth=35)

bm = bmesh.new()      # mail sacks lying fore-aft on the left
sack = [(0.03, 0.0), (0.11, 0.03), (0.165, 0.12), (0.175, 0.32), (0.155, 0.52), (0.10, 0.60),
        (0.045, 0.64), (0.05, 0.69), (0.035, 0.73), (0.01, 0.745)]
for (sx, sy, rz) in ((0.40, YC - 0.34, 0.08), (0.20, YC + 0.02, -0.25)):
    Mx = (Matrix.Translation((sx, sy, RT + 0.105)) @ Matrix.Rotation(rz, 4, 'Z')
          @ Matrix.Rotation(-math.pi / 2, 4, 'X') @ Matrix.Diagonal((1.0, 0.62, 1.0, 1.0))
          @ Matrix.Translation((0, 0, -0.33)))
    L.add_lathe(bm, sack, 8, Mx, cap0=True, cap1=True)
P('mail_sacks', bm, M['canvas'], 'Body', 'B', 0.9, smooth=60)

bm = bmesh.new()      # carpet bag, middle-right
cb = [(0, 0), (0.44, 0), (0.44, 0.16), (0.38, 0.27), (0.22, 0.30), (0.06, 0.27), (0.0, 0.16)]
bx0, by = -0.52, YC - 0.12
cbr = []
for (y, k) in ((-0.13, 0.9), (-0.11, 1.0), (0.11, 1.0), (0.13, 0.9)):
    cbr.append([(bx0 + px + (0.22 - px) * (1 - k), by + y, RT + pz * k) for (px, pz) in cb])
L.add_loft(bm, cbr)
recalc(bm)
P('carpet_bag', bm, M['carpet'], 'Body', 'B', 0.7, smooth=40)
bm = bmesh.new()
L.add_rod(bm, L.catmull([(bx0 + 0.12, by, RT + 0.28), (bx0 + 0.16, by, RT + 0.39),
                         (bx0 + 0.28, by, RT + 0.39), (bx0 + 0.32, by, RT + 0.28)], 3), 0.012, 4,
          uv='SweepUV')
P('bag_handle', bm, M['leather'], 'Body', 'B', 0.2)

bm = bmesh.new()      # crate, middle-left behind the sacks
L.add_box(bm, (0.44, 0.36, 0.28), (0.42, YC + 0.46, RT + 0.14), rot=(0, 0, math.radians(-6)), bevel=0.012)
P('crate', bm, M['crate'], 'Body', 'B', 0.8, smooth=None)

bm = bmesh.new()      # rope coils, rear-left
for (zz, rr_, ph) in ((RT + 0.03, 0.16, 0.0), (RT + 0.085, 0.14, 0.4)):
    circ = [(0.42 + rr_ * math.cos(ph + 2 * math.pi * i / 14), YC + 0.93 + rr_ * math.sin(ph + 2 * math.pi * i / 14), zz)
            for i in range(14)]
    L.add_sweep(bm, circ, L.circle_profile(0.03, 5), closed_path=True, uv='SweepUV')
P('rope_coil', bm, M['rope'], 'Body', 'B', 0.6, smooth=60)

bm = bmesh.new()      # lashing ropes over the luggage
lash = [
    [(0.72, YC - 0.62, 2.415), (0.60, YC - 0.62, RT + 0.30), (0.39, YC - 0.62, RT + 0.375),
     (0.18, YC - 0.62, RT + 0.30), (0.08, YC - 0.62, RT + 0.05)],
    [(0.72, YC - 0.88, 2.415), (0.60, YC - 0.88, RT + 0.30), (0.39, YC - 0.88, RT + 0.375),
     (0.18, YC - 0.88, RT + 0.30), (0.08, YC - 0.88, RT + 0.05)],
    [(-0.72, YC - 0.70, 2.415), (-0.62, YC - 0.70, RT + 0.31), (-0.36, YC - 0.70, RT + 0.315),
     (-0.12, YC - 0.70, RT + 0.31), (-0.05, YC - 0.70, RT + 0.05)],
    [(0.72, YC - 0.05, 2.415), (0.50, YC - 0.08, RT + 0.19), (0.22, YC - 0.05, RT + 0.19),
     (0.05, YC - 0.03, RT + 0.02)],
]
for ln in lash:
    L.add_sweep(bm, L.catmull(ln, 3), L.circle_profile(0.011, 4), uv='SweepUV')
P('lashing', bm, M['rope'], 'Body', 'B', 0.4, smooth=60)

bm = bmesh.new()      # guard's folded blanket (seat) + bedroll backrest
L.add_box(bm, (0.50, 0.46, 0.06), (-0.42, YC + 0.80, RT + 0.03), rot=(0, 0, math.radians(3)),
          bevel=0.02, segs=2)
L.add_cyl(bm, 0.105, 0.105, 0.64, 10, loc=(-0.40, YC + 1.06, RT + 0.10), rot=(0, math.pi / 2, 0))
P('blanket', bm, M['blanket'], 'Body', 'B', 0.8, smooth=40)
bm = bmesh.new()
for xs in (-0.60, -0.20):
    circ = [(xs, YC + 1.06 + 0.112 * math.cos(2 * math.pi * i / 10), RT + 0.10 + 0.112 * math.sin(2 * math.pi * i / 10))
            for i in range(10)]
    L.add_sweep(bm, circ, L.rect_profile(0.03, 0.006), closed_path=True, uv='SweepUV', up=(1, 0, 0))
P('bedroll_straps', bm, M['leather'], 'Body', 'B', 0.2)

# ----------------------------------------------------------------------------
# CHASSIS
# ----------------------------------------------------------------------------
log('chassis')
RA, FA = D.REAR_AXLE_Y, D.FRONT_AXLE_Y
bm = bmesh.new()
L.add_box(bm, (1.32, 0.11, 0.10), (0, RA, D.REAR_R + 0.075), bevel=0.012)                  # rear bed
L.add_box(bm, (1.20, 0.10, 0.10), (0, FA, D.FRONT_R + 0.07), bevel=0.012)                  # front bed
L.add_box(bm, (1.24, 0.12, 0.11), (0, FA, 0.715), bevel=0.012)                             # bolster
L.add_beam(bm, (0, FA + 0.05, 0.64), (0, RA + 0.2, 0.80), 0.08, 0.08, bevel=0.01)          # reach
for sx in (-1, 1):
    L.add_beam(bm, (0, RA - 0.75, 0.74), (sx * 0.58, RA, 0.80), 0.055, 0.055, bevel=0.008)  # hounds
    L.add_beam(bm, (sx * 0.34, FA, 0.60), (0, FA - 0.50, 0.63), 0.05, 0.05, bevel=0.008)
    L.add_beam(bm, (sx * 0.34, FA, 0.60), (0, FA + 0.42, 0.64), 0.05, 0.05, bevel=0.008)
    # thoroughbrace jacks (C-standards)
    L.add_sweep(bm, L.catmull([(sx * 0.5, RA + 0.02, 0.80), (sx * 0.5, RA + 0.08, 0.97),
                               (sx * 0.5, RA + 0.20, 1.10), (sx * 0.5, RA + 0.33, 1.17),
                               (sx * 0.5, RA + 0.40, 1.19)], 3), L.rect_profile(0.065, 0.075, 0.012),
                uv=None)
    L.add_sweep(bm, L.catmull([(sx * 0.5, FA + 0.06, 0.76), (sx * 0.5, FA + 0.10, 0.95),
                               (sx * 0.5, FA + 0.04, 1.10), (sx * 0.5, FA - 0.06, 1.17),
                               (sx * 0.5, FA - 0.13, 1.19)], 3), L.rect_profile(0.065, 0.075, 0.012),
                uv=None)
# pole, yoke, doubletree, singletrees, brake beam
L.add_sweep(bm, [(0, FA + 0.2, 0.585), Vector(D.HITCH)], L.circle_profile(0.046, 8),
            scales=[1.0, 0.68], uv=None)
L.add_box(bm, (0.95, 0.055, 0.055), (0, D.HITCH[1] + 0.12, D.HITCH[2] - 0.02), bevel=0.01)
L.add_box(bm, (1.10, 0.07, 0.075), (0, FA - 0.40, 0.655), bevel=0.012)
for sx in (-1, 1):
    L.add_box(bm, (0.62, 0.05, 0.055), (sx * 0.55, FA - 0.48, 0.655), bevel=0.01)
L.add_box(bm, (1.92, 0.065, 0.07), (0, 0.175, 0.60), bevel=0.01)
P('gear_wood', bm, M['gear'], 'Chassis', 'B', 0.6, smooth=35)

bm = bmesh.new()
L.add_cyl(bm, 0.034, 0.034, 1.84, 8, loc=(0, RA, D.REAR_R), rot=(0, math.pi / 2, 0))
L.add_cyl(bm, 0.03, 0.03, 1.72, 8, loc=(0, FA, D.FRONT_R), rot=(0, math.pi / 2, 0))
# fifth wheel ring
L.add_lathe(bm, [(0.33, 0.645), (0.37, 0.645), (0.37, 0.665), (0.33, 0.665)], 16,
            Matrix.Translation((0, FA, 0)), closed=True)
for sx in (-1, 1):
    # jack tip irons
    L.add_box(bm, (0.075, 0.07, 0.05), (sx * 0.5, RA + 0.40, 1.20), bevel=0.006)
    L.add_box(bm, (0.075, 0.07, 0.05), (sx * 0.5, FA - 0.13, 1.20), bevel=0.006)
    # brake shoes
    L.add_box(bm, (0.08, 0.05, 0.17), (sx * D.REAR_TRACK, 0.20, 0.63), rot=(math.radians(-7), 0, 0),
              bevel=0.006)
    L.add_rod(bm, [(sx * 0.93, 0.175, 0.60), (sx * 0.62, RA - 0.02, 0.83)], 0.01, 4)
# pole tip + ring
L.add_cyl(bm, 0.034, 0.034, 0.12, 8, loc=(0, D.HITCH[1] + 0.05, D.HITCH[2]),
          rot=(math.pi / 2 + math.atan2(0.335, 2.2), 0, 0))
L.add_lathe(bm, [(0.05, -0.012), (0.075, -0.012), (0.075, 0.012), (0.05, 0.012)], 8,
            Matrix.Translation((0, D.HITCH[1] - 0.02, D.HITCH[2])) @ Matrix.Rotation(math.pi / 2, 4, 'X'),
            closed=True)
P('gear_iron', bm, M['iron'], 'Chassis', 'B', 0.5, smooth=40)

log('thoroughbraces')
bm = bmesh.new()
for sx in (-1, 1):
    x = sx * D.BRACE_X
    front_tip = (FA - 0.10, 1.215)
    rear_tip = (RA + 0.37, 1.215)
    pts = [front_tip]
    y = front_tip[0] + 0.02
    while y < rear_tip[0]:
        zb = body_bottom(x, y)
        if zb is not None:
            pts.append((y, zb - 0.026))
        y += 0.02
    pts.append(rear_tip)
    pts.sort()
    hull = []
    for p in pts:
        while len(hull) >= 2:
            o, a = hull[-2], hull[-1]
            if (a[0] - o[0]) * (p[1] - o[1]) - (a[1] - o[1]) * (p[0] - o[0]) <= 0:
                hull.pop()
            else:
                break
        hull.append(p)
    simp = [hull[0]]
    for p in hull[1:-1]:
        if math.hypot(p[0] - simp[-1][0], p[1] - simp[-1][1]) > 0.09:
            simp.append(p)
    simp.append(hull[-1])
    path = [(x, yy, zz) for (yy, zz) in simp]
    # wrap over the jack tips
    path = [(x, front_tip[0] - 0.05, 1.20)] + path + [(x, rear_tip[0] + 0.05, 1.20)]
    L.add_sweep(bm, path, L.rect_profile(0.085, 0.045, 0.008), uv='SweepUV', up=(0, 0, 1))
P('thoroughbraces', bm, M['leather'], 'Chassis', 'B', 0.9, smooth=40)

# ----------------------------------------------------------------------------
# WHEELS (built at their hub, spin axis = X, outer face = +X; right side mirrored later)
# ----------------------------------------------------------------------------
log('wheels')


def build_wheel(name, R, nsp, segs, hub, cx, cy):
    cz = R
    W = Matrix.Translation((cx, cy, cz)) @ Matrix.Rotation(math.pi / 2, 4, 'Y')  # local Z -> +X
    bm = bmesh.new()
    rim = [(R - 0.085, -0.028), (R - 0.018, -0.028), (R, -0.025), (R, 0.025), (R - 0.018, 0.028),
           (R - 0.085, 0.028)]
    _, segf = L.add_lathe(bm, rim, segs, W, closed=True)
    for j, fs in enumerate(segf):
        for f in fs:
            f.material_index = 1 if j in (1, 2, 3) else 0
    hp = [(0.072 * hub, -0.20), (0.088 * hub, -0.185), (0.10 * hub, -0.12), (0.108 * hub, -0.07),
          (0.108 * hub, 0.0), (0.10 * hub, 0.045), (0.088 * hub, 0.085), (0.082 * hub, 0.095),
          (0.082 * hub, 0.115), (0.062 * hub, 0.12), (0.052 * hub, 0.16), (0.02, 0.168)]
    _, hs = L.add_lathe(bm, hp, 10, W @ Matrix.Translation((0, 0, -0.03)), cap0=True, cap1=True)
    for j, fs in enumerate(hs):
        for f in fs:
            f.material_index = 1 if j in (0, 7, 8, 9, 10, 11, 12) else 0
    for i in range(nsp):
        a = 2 * math.pi * (i + 0.5) / nsp
        d = Vector((math.cos(a), math.sin(a), 0))
        stag = 0.012 if i % 2 else -0.012
        p0 = W @ (d * (0.098 * hub) + Vector((0, 0, -0.045 + stag)))
        p1 = W @ (d * (R - 0.07) + Vector((0, 0, 0.0)))
        L.add_sweep(bm, [p0, p1], L.rect_profile(0.03, 0.044, 0.009), scales=[1.0, 0.78],
                    up=W.to_3x3() @ Vector((0, 0, 1)), caps=False, uv=None)
    ob = P(name, bm, [M['gear'], M['iron']], 'Wheel', 'B', 0.9 if R > 0.6 else 0.75, smooth=40)
    ob['hub'] = (cx, cy, cz)
    return ob


wheel_RL = build_wheel('Wheel_RL', D.REAR_R, 14, 28, 1.0, D.REAR_TRACK, RA)
wheel_FL = build_wheel('Wheel_FL', D.FRONT_R, 12, 24, 0.85, D.FRONT_TRACK, FA)

# ----------------------------------------------------------------------------
# report & bake
# ----------------------------------------------------------------------------
for o in PARTS:
    o.data.update()
tot = 0
for o in PARTS:
    n = L.tri_count(o)
    tot += n * (2 if o.get('grp') == 'Wheel' else 1)
    log('  %-16s %5d tris  atlas %s' % (o.name, n, o['atlas']))
log('TOTAL tris (with mirrored wheels):', tot)

atlases = {}
for o in PARTS:
    atlases.setdefault(o['atlas'], []).append(o)

log('uv atlases')
for k, objs in atlases.items():
    L.uv_atlas(objs, margin=0.006 if TEX >= 1024 else 0.012)

# move the wheels away so they don't bake chassis AO into a spinning texture
for w in (wheel_RL, wheel_FL):
    w.location.x += 40.0

IMGS = {}
for k, objs in atlases.items():
    for kind in ('color', 'orm', 'normal'):
        img = L.new_image('coach%s_%s' % (k, kind), TEX, non_color=(kind != 'color'))
        log('bake', k, kind)
        L.bake_pass(objs, img, kind)
        ext = '.png'
        path = os.path.join(BUILD, 'coach%s_%s%s' % (k, kind, ext))
        L.save_image(img, path)
        IMGS[(k, kind)] = img

for w in (wheel_RL, wheel_FL):
    w.location.x -= 40.0

# JPEG copies for embedding (smaller GLB)
FINAL = {}
for (k, kind), img in IMGS.items():
    q = {'color': 90, 'orm': 85, 'normal': 92}[kind]
    path = os.path.join(BUILD, 'coach%s_%s.jpg' % (k, kind))
    L.save_image(img, path, quality=q)
    im2 = bpy.data.images.load(path)
    im2.name = 'Coach%s_%s' % (k, kind)
    if kind != 'color':
        im2.colorspace_settings.name = 'Non-Color'
    FINAL[(k, kind)] = im2

MAT_NAMES = {'A': 'Coach_Body', 'B': 'Coach_Gear'}
FMAT = {k: L.final_material(MAT_NAMES[k], FINAL[(k, 'color')], FINAL[(k, 'orm')], FINAL[(k, 'normal')])
        for k in atlases}

for o in PARTS:
    L.assign_single_material(o, FMAT[o['atlas']])
    L.strip_uvs(o)

# ----------------------------------------------------------------------------
# assemble hierarchy
# ----------------------------------------------------------------------------
log('assemble')
body_parts = [o for o in PARTS if o['grp'] == 'Body']
chassis_parts = [o for o in PARTS if o['grp'] == 'Chassis']
body = L.join(body_parts, 'Body')
chassis = L.join(chassis_parts, 'Chassis')
L.set_origin(body, (0, YC, 0.93))

wheels = {}
for w, base in ((wheel_RL, 'R'), (wheel_FL, 'F')):
    hub = Vector(w['hub'])
    L.set_origin(w, hub)
    wheels[base + 'L'] = w
    # mirrored copy for the right side (outer face -> -X), same UVs/texture
    r = w.copy()
    r.data = w.data.copy()
    r.name = 'Wheel_%sR' % base
    r.data.name = r.name
    L.link(r)
    bm = bmesh.new()
    bm.from_mesh(r.data)
    bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=bm.verts[:])
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(r.data)
    bm.free()
    r.location = (-hub.x, hub.y, hub.z)
    wheels[base + 'R'] = r
for k, w in wheels.items():
    for key in list(w.keys()):
        del w[key]
for ob in (body, chassis):
    for key in list(ob.keys()):
        del ob[key]

root = L.empty('Stagecoach', (0, 0, 0), size=0.5)
bpy.context.view_layer.update()
L.parent_keep(chassis, root)
L.parent_keep(body, root)
for w in wheels.values():
    L.parent_keep(w, chassis)
L.empty('Hitch', D.HITCH, chassis, 0.15, 'ARROWS')
L.empty('Seat_Driver', (0.33, -1.31, 2.31), body, 0.15, 'ARROWS')
L.empty('Seat_Guard', (-0.42, YC + 0.80, 2.305), body, 0.15, 'ARROWS')
L.empty('Lamp_L', (0.84, FW + 0.10, 1.98), body, 0.08)
L.empty('Lamp_R', (-0.84, FW + 0.10, 1.98), body, 0.08)
bpy.context.view_layer.update()

for o in bpy.data.objects:
    if o.type == 'MESH':
        log('  final %-10s %5d tris' % (o.name, L.tri_count(o)))

# keep a .blend for inspection
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'stagecoach.blend'), compress=True)
L.export_glb(OUT)
log('exported', OUT, '%.0f KB' % (os.path.getsize(OUT) / 1024))
