"""Build public/assets/models/stagecoach_treasure.glb — SCHOFIELD's Abbott-Downing
treasure coach: the armoured express coach the bank money rides in.

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_coach2.py [-- --quick] [--geom] [--out PATH]

  --quick   256 px atlases / 6 samples (look-dev bake, ~1 min)
  --geom    build the shapes, print tri counts + empty positions, stop before the bake

Same vehicle class as the Concord (tools/blender/build_stagecoach.py) and the same
dimensions (tools/blender/coach_dims.py), so the game can swap one for the other:
  - iron shutters with barred firing slots instead of open windows and curtains
  - iron strapping, bolt plates and corner brackets over the panels
  - a strongbox chained to the roof rack and an iron-plated rear boot
  - deep bottle-green paint with plain gold lining (express livery), black gear
  - heavier running gear: thicker spokes, wider tyres, fatter beams

Pipeline (identical to the Concord): bmesh geometry (Blender space: faces -Y, Z up,
LEFT = +X) with procedural weathered materials -> two atlases baked in Cycles
(colour+AO, rough/metal, tangent normals incl. rounded-edge bevel normals) -> plain
Principled materials -> GLB (export_yup: coach faces +Z in three.js).

Node contract (DESIGN.md, same names as stagecoach.glb):
  Stagecoach (root empty, ground origin)
    Chassis  (running gear, thoroughbraces, pole)   children: Wheel_FL/FR/RL/RR, Hitch
    Body     (everything that rocks on the braces)  children: Seat_Driver, Seat_Guard,
                                                              Lamp_L, Lamp_R
  Wheels: origin at hub, axle = local X.  Body origin = bottom-centre of the shell.
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
GEOM = '--geom' in ARGS          # shapes only, no bake/export (fast iteration)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'models', 'stagecoach_treasure.glb')
if '--out' in ARGS:
    OUT = os.path.abspath(ARGS[ARGS.index('--out') + 1])
BUILD = os.path.join(HERE, 'build', os.path.splitext(os.path.basename(OUT))[0])
TEX = 256 if QUICK else 1024
SAMPLES = 6 if QUICK else 64
PY = shutil.which('python3') or '/usr/bin/python3'

YC = D.YC
FW = YC - 1.166          # front wall y
RW = YC + 1.166          # rear wall y
RA, FA = D.REAR_AXLE_Y, D.FRONT_AXLE_Y
RT = 2.245               # roof load sits here
T0 = time.time()

# the contract's empties — logged in --geom so they can be diffed against the Concord
EMPTIES = dict(Hitch=('Chassis', tuple(D.HITCH)),
               Seat_Driver=('Body', (0.33, -1.31, 2.31)),
               Seat_Guard=('Body', (-0.42, YC + 0.80, 2.305)),
               Lamp_L=('Body', (0.84, FW + 0.10, 1.98)),
               Lamp_R=('Body', (-0.84, FW + 0.10, 1.98)))


def log(*a):
    print('[coach2 %5.1fs]' % (time.time() - T0), *a, flush=True)


# ----------------------------------------------------------------------------
# decals — painted by system python3 (PIL/numpy), projected on the body in the
# paint material.  Three projections: sides (Y,Z), rear/front (X,Z), strongbox.
#   *_col.png  RGBA  colour + coverage
#   *_msk.png  RGB   R = gold leaf, G = iron strap, B = bolt head (height)
# ----------------------------------------------------------------------------
SIDE = dict(y0=YC - 1.40, y1=YC + 1.40, z0=0.85, z1=2.30, w=2048)
REAR = dict(x0=-0.85, x1=0.85, z0=0.85, z1=2.30, w=1024)
BOXD = dict(u0=-0.46, u1=0.46, v0=0.0, v1=0.44, w=512)

DECALS = r'''
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT, YC = sys.argv[1], float(sys.argv[2])
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, sys.argv[3])
import coach_dims as D

GOLD = np.array([206, 166, 84], np.float32) / 255
GOLD_SH = np.array([12, 18, 14], np.float32) / 255
IRON = np.array([36, 39, 37], np.float32) / 255
SEAM = np.array([8, 12, 10], np.float32) / 255
BELT = np.array([14, 20, 16], np.float32) / 255
FONTS = ['/System/Library/Fonts/Supplemental/SuperClarendon.ttc',
         '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf']


def font(px):
    for f in FONTS:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, px)
            except Exception:
                pass
    return ImageFont.load_default()


class Canvas:
    def __init__(self, u0, u1, v0, v1, w):
        self.u0, self.u1, self.v0, self.v1, self.W = u0, u1, v0, v1, w
        self.px = (u1 - u0) / w
        self.H = int(round((v1 - v0) / self.px))
        us = u0 + (np.arange(self.W) + 0.5) * self.px
        vs = v1 - (np.arange(self.H) + 0.5) * self.px
        self.U, self.V = np.meshgrid(us, vs)
        self.rgb = np.zeros((self.H, self.W, 3), np.float32)
        self.a = np.zeros((self.H, self.W), np.float32)
        self.msk = np.zeros((self.H, self.W, 3), np.float32)

    def fill(self, sd):
        return np.clip(0.5 - sd / self.px, 0, 1)

    def stroke(self, sd, width, offset=0.0):
        return np.clip(0.5 - (np.abs(sd - offset) - width / 2) / self.px, 0, 1)

    def put(self, cov, col, gold=0.0, iron=0.0, bolt=0.0):
        cov = np.clip(cov, 0, 1).astype(np.float32)
        col = np.asarray(col, np.float32)
        self.rgb = self.rgb * (1 - cov[..., None]) + col * cov[..., None]
        self.a = self.a + cov * (1 - self.a)
        m = np.dstack([np.full_like(cov, gold), np.full_like(cov, iron),
                       np.full_like(cov, bolt)])
        self.msk = self.msk * (1 - cov[..., None]) + m * cov[..., None]

    def to_px(self, u, v):
        return ((u - self.u0) / self.px, (self.v1 - v) / self.px)

    def text(self, s, cu, cv, height, col=GOLD, gold=1.0, max_w=None, spacing=0.0):
        hpx = max(4, int(round(height / self.px)))
        f = font(int(hpx * 1.35))
        if spacing:
            s = (' ' * int(spacing)).join(list(s))
        bbox = f.getbbox(s)
        tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
        layer = Image.new('L', (tw + 8, th + 8), 0)
        ImageDraw.Draw(layer).text((4 - bbox[0], 4 - bbox[1]), s, font=f, fill=255)
        sx = 1.0
        if max_w and tw * self.px > max_w:
            sx = max_w / (tw * self.px)
        layer = layer.resize((max(1, int(layer.width * sx)),
                              max(1, int(layer.height * hpx / th))), Image.LANCZOS)
        cx, cy = self.to_px(cu, cv)
        big = Image.new('L', (self.W, self.H), 0)
        big.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))
        m = np.asarray(big, np.float32) / 255
        off = max(1, int(0.004 / self.px))
        self.put(np.roll(np.roll(m, off, 0), off, 1) * 0.85, GOLD_SH, 0.0)
        self.put(m, col, gold)

    def save(self, name):
        Image.fromarray((np.clip(np.dstack([self.rgb, self.a]), 0, 1) * 255 + 0.5
                         ).astype(np.uint8), 'RGBA').save(os.path.join(OUT, name + '_col.png'))
        Image.fromarray((np.clip(self.msk, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB'
                        ).save(os.path.join(OUT, name + '_msk.png'))


def sd_box(U, V, cu, cv, hu, hv, r=0.0):
    qx = np.abs(U - cu) - (hu - r)
    qy = np.abs(V - cv) - (hv - r)
    return (np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
            + np.minimum(np.maximum(qx, qy), 0) - r)


def sd_polygon(c, pts):
    pts = np.asarray(pts, np.float32)
    d = np.full(c.U.shape, 1e9, np.float32)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        ab = b - a
        t = np.clip(((c.U - a[0]) * ab[0] + (c.V - a[1]) * ab[1]) / max(ab @ ab, 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(c.U - (a[0] + t * ab[0]), c.V - (a[1] + t * ab[1])))
    mask = Image.new('L', (c.W, c.H), 0)
    ImageDraw.Draw(mask).polygon([c.to_px(p[0], p[1]) for p in pts], fill=255)
    return np.where(np.asarray(mask) > 127, -d, d)


def strap(c, horiz, at, lo, hi, w=0.085, inside=None, pitch=0.105):
    """Riveted iron strap + its two bolt rows."""
    lo, hi = min(lo, hi), max(lo, hi)
    if horiz:
        d = sd_box(c.U, c.V, (lo + hi) / 2, at, (hi - lo) / 2, w / 2)
    else:
        d = sd_box(c.U, c.V, at, (lo + hi) / 2, w / 2, (hi - lo) / 2)
    cov = c.fill(d)
    if inside is not None:
        cov = cov * inside
    c.put(cov, IRON, 0.0, 1.0)
    n = max(2, int((hi - lo) / pitch))
    for i in range(n):
        t = lo + (hi - lo) * (i + 0.5) / n
        cu, cv = (t, at) if horiz else (at, t)
        b = c.fill(np.hypot(c.U - cu, c.V - cv) - w * 0.21)
        if inside is not None:
            b = b * inside
        c.put(b * 0.9, IRON * 1.9, 0.0, 1.0, 1.0)


def side():
    c = Canvas(-1.40, 1.40, 0.85, 2.30, 2048)
    U, V = c.U, c.V
    sil = sd_polygon(c, [(y - YC, z) for (y, z) in D.side_outline()])
    ins = c.fill(sil + 0.004)

    # belt rail band + its two gold lines
    z0, z1 = D.BELT_Z
    c.put(np.clip(np.minimum((V - z0) / c.px + 0.5, (z1 - V) / c.px + 0.5), 0, 1), BELT)
    c.put(c.stroke(V - (z0 + 0.007), 0.004), GOLD, 1)
    c.put(c.stroke(V - (z1 - 0.007), 0.004), GOLD, 1)

    # plain gold lining following the silhouette (single line, no scrollwork)
    keep = ((V < 1.535) | ((V > 1.625) & (V < 2.13))).astype(np.float32)
    c.put(c.stroke(sil, 0.009, -0.038) * keep, GOLD, 1)

    # iron strapping over the panel joints, with bolt rows
    for u in (-1.105, -0.375, 0.375, 1.105):
        strap(c, False, u, 0.90, 2.20, 0.085, ins)
    for sgn in (-1, 1):
        strap(c, True, 1.245, sgn * 0.42, sgn * 1.16, 0.075, ins)
        d = sd_box(U, V, sgn * 0.755, 1.395, 0.305, 0.095, 0.035)
        c.put(c.stroke(d, 0.008), GOLD, 1)

    # door: seam + a plain gold line panel with the express name
    dy0, dy1 = D.DOOR_Y
    dz0, dz1 = D.DOOR_Z
    door = sd_box(U, V, 0, (dz0 + dz1) / 2, (dy1 - dy0) / 2, (dz1 - dz0) / 2, 0.035)
    c.put(c.stroke(door, 0.007), SEAM, 0)
    dp = sd_box(U, V, 0, 1.30, 0.235, 0.215, 0.04)
    c.put(c.stroke(dp, 0.008), GOLD, 1)
    c.text('EXPRESS', 0.0, 1.35, 0.078, max_w=0.40)
    c.text('No. 3', 0.0, 1.21, 0.052, max_w=0.24)

    # window surrounds (the shutters sit inside these)
    wz0, wz1 = D.WINDOW_Z
    for (y0, y1) in D.WINDOWS_Y:
        d = sd_box(U, V, (y0 + y1) / 2, (wz0 + wz1) / 2, (y1 - y0) / 2 + 0.052,
                   (wz1 - wz0) / 2 + 0.048, 0.04)
        c.put(c.stroke(d, 0.008), GOLD, 1)

    c.text('OVERLAND  EXPRESS  Co.', 0.0, 2.107, 0.044, max_w=1.60)
    c.save('coach2_side')


def rear():
    c = Canvas(-0.85, 0.85, 0.85, 2.30, 1024)
    U, V = c.U, c.V
    z0, z1 = D.BELT_Z
    c.put(np.clip(np.minimum((V - z0) / c.px + 0.5, (z1 - V) / c.px + 0.5), 0, 1), BELT)
    c.put(c.stroke(V - (z0 + 0.007), 0.004), GOLD, 1)
    c.put(c.stroke(V - (z1 - 0.007), 0.004), GOLD, 1)
    for u in (-0.60, -0.185, 0.185, 0.60):
        strap(c, False, u, 0.90, 2.20, 0.085)
    d = sd_box(U, V, 0, 2.055, 0.40, 0.068, 0.02)
    c.put(c.stroke(d, 0.007), GOLD, 1)
    c.text('No. 3', 0.0, 2.055, 0.058, max_w=0.36)
    for (a, b) in ((1.03, 1.49),):
        d = sd_box(U, V, 0, (a + b) / 2, 0.56, (b - a) / 2, 0.05)
        c.put(c.stroke(d, 0.008), GOLD, 1)
    c.save('coach2_rear')


def strongbox():
    c = Canvas(-0.46, 0.46, 0.0, 0.44, 512)
    U, V = c.U, c.V
    d = sd_box(U, V, 0, 0.190, 0.245, 0.140, 0.02)
    c.put(c.stroke(d, 0.007), GOLD, 1)
    c.text('OVERLAND', 0.0, 0.262, 0.042, max_w=0.40)
    c.text('EXPRESS', 0.0, 0.168, 0.060, max_w=0.42)
    c.save('coach2_box')


side()
rear()
strongbox()
print('coach2 decals ->', OUT)
'''

os.makedirs(BUILD, exist_ok=True)
log('decals')
subprocess.run([PY, '-c', DECALS, BUILD, str(YC), HERE], check=True)

L.reset_scene()
L.setup_cycles(SAMPLES)


def load_img(name, non_color=False):
    img = bpy.data.images.load(os.path.join(BUILD, name))
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


IMG = dict(side_col=load_img('coach2_side_col.png'),
           side_msk=load_img('coach2_side_msk.png', True),
           rear_col=load_img('coach2_rear_col.png'),
           rear_msk=load_img('coach2_rear_msk.png', True),
           box_col=load_img('coach2_box_col.png'),
           box_msk=load_img('coach2_box_msk.png', True))


# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------

def body_decal(mb, st):
    x, y, z = mb.xyz(mb.pos)
    nx, ny, nz = mb.xyz(mb.nrm)
    u = mb.m('DIVIDE', mb.m('SUBTRACT', y, SIDE['y0']), SIDE['y1'] - SIDE['y0'])
    u = mb.mixf(mb.m('GREATER_THAN', x, 0.0), mb.m('SUBTRACT', 1.0, u), u)   # mirror right
    v = mb.m('DIVIDE', mb.m('SUBTRACT', z, SIDE['z0']), SIDE['z1'] - SIDE['z0'])
    sc, sa = mb.image(IMG['side_col'], mb.comb(u, v, 0))
    sm, _ = mb.image(IMG['side_msk'], mb.comb(u, v, 0))
    ws = mb.smooth(mb.m('ABSOLUTE', nx), 0.45, 0.7)

    ur = mb.m('DIVIDE', mb.m('SUBTRACT', REAR['x1'], x), REAR['x1'] - REAR['x0'])
    ur = mb.mixf(mb.m('GREATER_THAN', ny, 0.0), mb.m('SUBTRACT', 1.0, ur), ur)
    vr = mb.m('DIVIDE', mb.m('SUBTRACT', z, REAR['z0']), REAR['z1'] - REAR['z0'])
    rc, ra = mb.image(IMG['rear_col'], mb.comb(ur, vr, 0))
    rm, _ = mb.image(IMG['rear_msk'], mb.comb(ur, vr, 0))
    wr = mb.smooth(mb.m('ABSOLUTE', ny), 0.45, 0.7)

    st['col'] = mb.mixc(mb.m('MULTIPLY', sa, ws), st['col'], sc)
    st['col'] = mb.mixc(mb.m('MULTIPLY', ra, wr), st['col'], rc)
    sg, si, sb = mb.xyz(sm)
    rg, ri, rb = mb.xyz(rm)

    def blend(a, b):
        return mb.m('MINIMUM', mb.m('ADD', mb.m('MULTIPLY', a, ws),
                                    mb.m('MULTIPLY', b, wr)), 1.0)
    gold, iron, bolt = blend(sg, rg), blend(si, ri), blend(sb, rb)
    st['rough'] = mb.mixf(iron, st['rough'], 0.52)
    st['rough'] = mb.mixf(gold, st['rough'], 0.30)
    st['metal'] = mb.mixf(iron, 0.0, 0.55)
    st['metal'] = mb.mixf(gold, st['metal'], 0.65)
    st['height'] = mb.m('ADD', st['height'], mb.m('MULTIPLY', bolt, 1.2))
    st['height'] = mb.m('SUBTRACT', st['height'], mb.m('MULTIPLY', iron, 0.25))


def box_decal(mb, st):
    """Express lettering on the strongbox's rear face (what the player stares at)."""
    x, y, z = mb.xyz(mb.pos)
    nx, ny, nz = mb.xyz(mb.nrm)
    u = mb.m('DIVIDE', mb.m('SUBTRACT', BOXD['u1'], mb.m('SUBTRACT', x, BOX_C[0])),
             BOXD['u1'] - BOXD['u0'])
    v = mb.m('DIVIDE', mb.m('SUBTRACT', z, BOX_Z0), BOXD['v1'] - BOXD['v0'])
    bc, ba = mb.image(IMG['box_col'], mb.comb(u, v, 0))
    bmk, _ = mb.image(IMG['box_msk'], mb.comb(u, v, 0))
    w = mb.m('MULTIPLY', mb.smooth(ny, 0.55, 0.8), mb.m('LESS_THAN', z, BOX_Z0 + 0.44))
    a = mb.m('MULTIPLY', ba, w)
    st['col'] = mb.mixc(a, st['col'], bc)
    gold = mb.m('MULTIPLY', mb.xyz(bmk)[0], w)
    st['rough'] = mb.mixf(gold, st['rough'], 0.30)
    st['metal'] = mb.mixf(gold, 0.0, 0.65)


def _grid(mb, a, b, sp, rad):
    fa = mb.m('SUBTRACT', mb.m('FRACT', mb.m('DIVIDE', a, sp)), 0.5)
    fb = mb.m('SUBTRACT', mb.m('FRACT', mb.m('DIVIDE', b, sp)), 0.5)
    d = mb.m('SQRT', mb.m('ADD', mb.m('MULTIPLY', fa, fa), mb.m('MULTIPLY', fb, fb)))
    return mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('MULTIPLY', d, sp), rad * 0.55, rad))


def rivets(sp=0.085, rad=0.014, edge=0.055):
    """Bolt heads on a grid, kept near plate edges so they read as riveted strapping."""
    def f(mb, st):
        x, y, z = mb.xyz(mb.pos)
        nx, ny, nz = mb.xyz(mb.nrm)
        b = None
        for (a0, a1, nc) in ((y, z, nx), (x, z, ny), (x, y, nz)):
            g = mb.m('MULTIPLY', _grid(mb, a0, a1, sp, rad),
                     mb.smooth(mb.m('ABSOLUTE', nc), 0.5, 0.85))
            b = g if b is None else mb.m('MAXIMUM', b, g)
        em = mb.smooth(mb.m('SUBTRACT', 1.0, mb.v('DOT_PRODUCT', mb.bevel_normal(edge, 6),
                                                  mb.nrm)), 0.02, 0.30)
        b = mb.m('MULTIPLY', b, mb.m('ADD', mb.m('MULTIPLY', em, 0.85), 0.15))
        st['height'] = mb.m('ADD', st['height'], mb.m('MULTIPLY', b, 1.4))
        st['col'] = mb.mixc(mb.m('MULTIPLY', b, 0.5), st['col'], L.srgb(104, 104, 98))
    return f


def rust(mb, st):
    r = mb.smooth(mb.noise(mb.pos, 4.0, 6.0, 0.7), 0.60, 0.74)
    st['col'] = mb.mixc(mb.m('MULTIPLY', r, 0.75), st['col'], L.srgb(96, 50, 26))
    st['rough'] = mb.mixf(r, st['rough'], 0.9)


def stitches(mb, st):
    u, v, _ = mb.xyz(mb.uv('SweepUV'))
    dash = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 2 * math.pi * 90)), 0.1, 0.5)
    lines = None
    for cst in (0.035, 0.285, 0.535, 0.785):
        ln = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', v, cst)),
                                             0.004, 0.009))
        lines = ln if lines is None else mb.m('MAXIMUM', lines, ln)
    sm = mb.m('MULTIPLY', mb.m('MULTIPLY', lines, dash), mb.m('GREATER_THAN', u, 0.0001))
    st['col'] = mb.mixc(sm, st['col'], L.srgb(132, 96, 58))
    st['height'] = mb.m('SUBTRACT', st['height'], mb.m('MULTIPLY', sm, 0.4))


def chain_links(mb, st):
    u, v, _ = mb.xyz(mb.uv('SweepUV'))
    t = mb.m('FRACT', mb.m('MULTIPLY', u, 22.0))
    s = mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', t, 0.5)), 0.30, 0.46)
    st['height'] = mb.m('SUBTRACT', 1.0, s)
    st['col'] = mb.mixc(mb.m('MULTIPLY', s, 0.5), st['col'], L.srgb(20, 20, 20))


log('materials')
M = {}
M['paint'] = L.surface('paint', L.srgb(27, 45, 36), var=0.10, rough=0.42, rough_var=0.1,
                       wear_col=L.srgb(58, 48, 34), wear=0.85, wear_rough=0.75, edge_r=0.014,
                       scratches=0.45, dust=0.60, dust_z=(0.85, 2.1), dust_up=0.85, ao=0.75,
                       bump=0.07, bump_scale=35, streaks=0.35, extra=body_decal, blotch=0.22)
M['roof'] = L.surface('roof', L.srgb(26, 30, 27), var=0.12, rough=0.72, wear_col=L.srgb(66, 60, 48),
                      wear=0.7, dust=0.32, dust_up=0.45, dust_z=(1.0, 2.6), ao=0.75, grain='Y',
                      grain_amt=0.25, blotch=0.22, bump=0.25)
M['plate'] = L.surface('plate', L.srgb(34, 38, 36), var=0.14, rough=0.5, metal=0.6,
                       wear_col=L.srgb(158, 154, 146), wear=0.9, wear_rough=0.3, wear_metal=0.9,
                       dust=0.45, dust_z=(0.0, 2.3), extra=rivets(), bump=0.45, bump_dist=0.004,
                       edge_r=0.006, blotch=0.3)
M['iron'] = L.surface('iron', L.srgb(36, 34, 32), var=0.15, rough=0.55, metal=0.6,
                      wear_col=L.srgb(150, 146, 138), wear=0.9, wear_rough=0.3, wear_metal=0.9,
                      dust=0.7, dust_z=(0.0, 1.5), extra=rust, bump=0.25, edge_r=0.008)
M['chain'] = L.surface('chain', L.srgb(44, 42, 40), var=0.12, rough=0.45, metal=0.75,
                       wear_col=L.srgb(168, 164, 156), wear=0.9, wear_rough=0.25, wear_metal=1.0,
                       dust=0.4, extra=chain_links, bump=0.8, bump_dist=0.004, bevel_normal=False)
M['gear'] = L.surface('gear', L.srgb(42, 50, 43), var=0.14, rough=0.5, wear_col=L.srgb(86, 66, 44),
                      wear=0.9, wear_rough=0.8, scratches=0.4, dust=0.8, dust_z=(0.0, 1.7),
                      dust_col=L.srgb(134, 114, 86), ao=0.75, streaks=0.3, blotch=0.35, bump=0.12,
                      edge_r=0.012)
M['leather'] = L.surface('leather', L.srgb(48, 30, 18), var=0.18, rough=0.5,
                         wear_col=L.srgb(112, 78, 48), wear=0.8, wear_rough=0.7, dust=0.55,
                         dust_z=(0.3, 2.2), bump=0.5, bump_scale=28, blotch=0.4, extra=stitches,
                         edge_r=0.01)
M['boot'] = L.surface('boot', L.srgb(32, 26, 22), var=0.2, rough=0.5, wear_col=L.srgb(96, 70, 46),
                      wear=0.8, wear_rough=0.7, dust=0.6, dust_up=1.0, dust_z=(0.8, 2.3), bump=0.9,
                      bump_scale=9, blotch=0.5, edge_r=0.02, ao=0.8)
M['blackleather'] = L.surface('blackleather', L.srgb(26, 24, 22), var=0.15, rough=0.45,
                              wear_col=L.srgb(80, 62, 44), wear=0.7, dust=0.5, dust_up=0.8,
                              bump=0.45, bump_scale=35, blotch=0.3)
M['brass'] = L.surface('brass', L.srgb(186, 140, 64), var=0.1, rough=0.32, metal=0.75,
                       wear_col=L.srgb(232, 196, 116), wear=0.6, wear_rough=0.2, dust=0.35, ao=0.8,
                       blotch=0.5, bump=0.05)
M['glass'] = L.surface('glass', L.srgb(66, 58, 38), var=0.2, rough=0.08, dust=0.4, bump=0.0, ao=0.5,
                       bevel_normal=False)
M['wood'] = L.surface('wood', L.srgb(72, 54, 36), var=0.15, rough=0.8, wear=0.6,
                      wear_col=L.srgb(104, 82, 56), grain='Y', grain_amt=0.6, dust=0.55, blotch=0.4)
M['interior'] = L.surface('interior', L.srgb(18, 16, 14), var=0.1, rough=0.85, dust=0.0, ao=0.9,
                          ao_dist=0.12, bump=0.0, bevel_normal=False)
M['canvas'] = L.surface('canvas', L.srgb(112, 100, 78), var=0.12, rough=0.9, dust=0.3, blotch=0.5,
                        bump=0.35, bump_scale=260)
M['crate'] = L.surface('crate', L.srgb(120, 92, 60), var=0.18, rough=0.8, grain='X', grain_amt=0.5,
                       wear=0.5, wear_col=L.srgb(156, 128, 92), dust=0.7, dust_up=1.0)
M['blanket'] = L.surface('blanket', L.srgb(74, 62, 52), var=0.12, rough=0.95, dust=0.45, bump=0.3,
                         bump_scale=240)

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
    cols = [-e] + (WIN_COLS if e > 1.0 else [c * e / REF_END for c in WIN_COLS]) + [e]
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


DENSE = D.rings_dense()


def ring_at(z):
    """Shell ring dims (z, half_len, half_width, corner_r) interpolated at height z."""
    rs = [r for r in DENSE if r[0] not in (1.558, 1.602)]
    if z <= rs[0][0]:
        return rs[0]
    for k in range(len(rs) - 1):
        a, b = rs[k], rs[k + 1]
        if a[0] <= z <= b[0] and b[0] > a[0]:
            t = (z - a[0]) / (b[0] - a[0])
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
    return rs[-1]


def band(bm, z0, z1, d):
    """Iron band hooped right round the body between z0 and z1, standing d proud."""
    a, b = ring_at(z0), ring_at(z1)
    L.add_loft(bm, [perimeter(z0, a[1], a[2], a[3]),
                    perimeter(z0, a[1] + d, a[2] + d, a[3] + d),
                    perimeter(z1, b[1] + d, b[2] + d, b[3] + d),
                    perimeter(z1, b[1], b[2], b[3])], cap0=False, cap1=False)


def in_ring(x, y, ring):
    z, hl, hw, cr = ring
    dx = abs(x) - (hw - cr)
    dy = abs(y - YC) - (hl - cr)
    if dx > cr or dy > cr:
        return False
    return math.hypot(max(dx, 0), max(dy, 0)) <= cr


def body_bottom(x, y):
    for k in range(len(DENSE) - 1):
        a, b = DENSE[k], DENSE[k + 1]
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
bm = bmesh.new()
vr, faces = L.add_loft(bm, [perimeter(*r) for r in DENSE], cap0=True, cap1=False)
m = len(vr[0])
jw = [i for i, r in enumerate(DENSE) if abs(r[0] - D.WINDOW_Z[0]) < 1e-4][0]
win = [faces[jw * m + i] for i in (1, 3, 5, 20, 22, 24)]
bmesh.ops.inset_individual(bm, faces=win, thickness=0.030, use_even_offset=True)
walls = bmesh.ops.inset_individual(bm, faces=win, thickness=0.004, depth=-0.075,
                                   use_even_offset=True)['faces']
for f in win + walls:
    f.material_index = 1
P('shell', bm, [M['paint'], M['interior']], 'Body', 'A', 1.25, smooth=32)

log('roof')
bm = bmesh.new()
top = DENSE[-1]
rr = [perimeter(D.ROOF_Z, top[1] + 0.035, top[2] + 0.035, top[3] + 0.035),
      perimeter(D.ROOF_Z + 0.032, top[1] + 0.035, top[2] + 0.035, top[3] + 0.035),
      perimeter(D.ROOF_Z + 0.040, top[1] + 0.022, top[2] + 0.022, top[3] + 0.022),
      perimeter(D.ROOF_TOP, top[1] - 0.25, top[2] - 0.30, top[3])]
L.add_loft(bm, rr, cap0=True, cap1=True)
P('roof', bm, M['roof'], 'Body', 'A', 1.0, smooth=30)

log('armour bands, corner brackets')
bm = bmesh.new()
band(bm, 1.085, 1.155, 0.014)          # belly hoop
band(bm, 2.138, 2.196, 0.014)          # under the roof lip
P('bands', bm, M['plate'], 'Body', 'A', 0.9, smooth=40)

bm = bmesh.new()
for (zc, h) in ((1.115, 0.40), (1.56, 0.50), (1.965, 0.30)):
    r = ring_at(zc)
    fx, fy, cr = r[2] - r[3], r[1] - r[3], r[3]
    k = (cr - 0.026) * math.sqrt(0.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            L.add_box(bm, (0.082, 0.082, h), (sx * (fx + k), YC + sy * (fy + k), zc),
                      rot=(0, 0, math.radians(45)))
for sx in (-1, 1):          # straps on the rear panel above the boot (game camera)
    L.add_box(bm, (0.085, 0.020, 0.195), (sx * 0.60, YC + 1.171, 2.050))
P('corners', bm, M['plate'], 'Body', 'A', 0.8, smooth=None)

log('iron shutters')
bm = bmesh.new()
bars = bmesh.new()
for sx in (-1, 1):
    px = sx * 0.769
    for (y0, y1) in D.WINDOWS_Y:
        cy, w = YC + (y0 + y1) / 2, (y1 - y0) + 0.07
        for (z0, z1) in ((1.617, 1.833), (1.887, 2.062)):
            L.add_box(bm, (0.046, w, z1 - z0), (px, cy, (z0 + z1) / 2))
        L.add_box(bm, (0.030, w, 0.024), (px + sx * 0.026, cy, 1.712))     # strap hinges
        L.add_box(bm, (0.030, w, 0.024), (px + sx * 0.026, cy, 1.985))
        for k in (-1, 0, 1):                                               # bars in the slot
            L.add_box(bars, (0.034, 0.020, 0.062), (px, cy + k * w * 0.26, 1.860))
P('shutters', bm, M['plate'], 'Body', 'A', 0.9, smooth=None)
P('shutter_bars', bars, M['iron'], 'Body', 'A', 0.5, smooth=None)

log('front boot, seat, shot shield')
bm = bmesh.new()
prof = [(0.0, 1.60), (-0.30, 1.60), (-0.38, 1.66), (-0.40, 1.90), (-0.38, 2.15), (-0.34, 2.22),
        (0.0, 2.22)]
rings_b = []
for (x, k) in ((-0.64, 0.92), (-0.61, 1.0), (0.61, 1.0), (0.64, 0.92)):
    rings_b.append([(x, FW + py * k, pz) for (py, pz) in prof])
L.add_loft(bm, rings_b)
recalc(bm)
P('front_boot', bm, M['boot'], 'Body', 'A', 0.8, smooth=40)

bm = bmesh.new()
L.add_box(bm, (1.34, 0.40, 0.09), (0, FW - 0.19, 2.265), bevel=0.03, segs=2)      # cushion
L.add_box(bm, (1.34, 0.07, 0.22), (0, FW + 0.02, 2.38), rot=(math.radians(-8), 0, 0),
          bevel=0.025, segs=2)                                                    # back
P('seat', bm, M['blackleather'], 'Body', 'A', 0.7, smooth=40)

bm = bmesh.new()
L.add_box(bm, (1.46, 0.46, 0.04), (0, -1.72, 1.77), rot=(math.radians(-8), 0, 0), bevel=0.008)
P('footboard', bm, M['wood'], 'Body', 'A', 0.6, smooth=None)

bm = bmesh.new()      # iron shot shield across the driver's footwell
L.add_box(bm, (1.46, 0.035, 0.30), (0, -1.97, 1.94), rot=(math.radians(14), 0, 0), bevel=0.010)
for sx in (-1, 1):
    L.add_box(bm, (0.055, 0.30, 0.035), (sx * 0.72, -1.87, 2.07), rot=(math.radians(14), 0, 0))
P('shield', bm, M['plate'], 'Body', 'A', 0.7, smooth=None)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_rod(bm, [(sx * 0.60, FW + 0.02, 1.52), (sx * 0.66, -1.50, 1.64), (sx * 0.70, -1.90, 1.78)],
              0.014, 4)
    L.add_rod(bm, L.catmull([(sx * 0.67, FW - 0.02, 2.30), (sx * 0.70, FW - 0.03, 2.44),
                             (sx * 0.71, FW - 0.25, 2.45), (sx * 0.70, FW - 0.40, 2.30)], 3), 0.012, 4)
L.add_rod(bm, [(0.76, -1.62, 1.74), (0.78, -1.53, 2.44)], 0.016, 5)      # brake lever (left)
L.add_box(bm, (0.04, 0.04, 0.09), (0.785, -1.525, 2.47))
L.add_rod(bm, [(0.76, -1.62, 1.76), (0.74, -1.30, 1.50), (0.74, -0.9, 1.30)], 0.011, 4)
P('front_irons', bm, M['iron'], 'Body', 'A', 0.4, smooth=40)

log('lamps')
for side_, sx in (('L', 1), ('R', -1)):
    cx, cy, cz = sx * 0.84, FW + 0.10, 1.98
    Mx = Matrix.Translation((cx, cy, cz))
    bm = bmesh.new()
    L.add_lathe(bm, [(0.012, -0.17), (0.05, -0.13), (0.075, -0.095), (0.075, -0.075)], 4, Mx,
                cap0=True, phase=math.pi / 4)
    L.add_lathe(bm, [(0.075, 0.075), (0.088, 0.085), (0.088, 0.10), (0.05, 0.13), (0.028, 0.16),
                     (0.03, 0.21), (0.045, 0.22), (0.02, 0.24)], 4, Mx, cap1=True, phase=math.pi / 4)
    L.add_beam(bm, (cx - sx * 0.03, cy, cz - 0.02), (sx * 0.735, cy, cz - 0.02), 0.032, 0.022)
    P('lamp_%s' % side_, bm, M['brass'], 'Body', 'A', 0.9, smooth=30)
    bm = bmesh.new()
    L.add_lathe(bm, [(0.072, -0.078), (0.072, 0.078)], 4, Mx, phase=math.pi / 4)
    P('lampglass_%s' % side_, bm, M['glass'], 'Body', 'A', 0.5, smooth=None)

log('door hardware, steps')
bm = bmesh.new()
for sx in (-1, 1):
    L.add_box(bm, (0.018, 0.09, 0.022), (sx * 0.772, YC + 0.24, 1.60), bevel=0.004)
P('handles', bm, M['brass'], 'Body', 'A', 0.3)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_box(bm, (0.15, 0.26, 0.022), (sx * 0.80, YC, 0.905), bevel=0.004)
    L.add_rod(bm, [(sx * 0.55, YC - 0.09, 0.935), (sx * 0.80, YC - 0.09, 0.91)], 0.013, 4)
    L.add_rod(bm, [(sx * 0.55, YC + 0.09, 0.935), (sx * 0.80, YC + 0.09, 0.91)], 0.013, 4)
    for zz in (1.30, 1.88):                                    # heavy door hinges
        L.add_box(bm, (0.014, 0.09, 0.042), (sx * 0.773, YC - 0.31, zz), bevel=0.003)
P('steps', bm, M['iron'], 'Body', 'A', 0.4)

log('armoured rear boot')
prof = [(0.0, 1.975), (0.20, 1.955), (0.36, 1.905), (0.47, 1.805), (0.52, 1.645), (0.535, 1.45),
        (0.515, 1.315), (0.40, 1.295), (0.0, 1.295)]
prof = list(reversed(prof))
BOOT_X = ((-0.63, 0.93, 0.95), (-0.60, 0.985, 0.99), (-0.3, 1, 1), (0.0, 1.01, 1),
          (0.3, 1, 1), (0.60, 0.985, 0.99), (0.63, 0.93, 0.95))
bm = bmesh.new()
lr = [[(x, RW + py * ky, 1.295 + (pz - 1.295) * kz) for (py, pz) in prof]
      for (x, ky, kz) in BOOT_X]
L.add_loft(bm, lr)
recalc(bm)
P('rear_boot', bm, M['plate'], 'Body', 'A', 1.3, smooth=50)


def boot_band(bm, i, w=0.075, d=0.018):
    """Riveted iron band hooped across the boot at profile point i (outward normal
    from the profile tangent, so it hugs the curve the way a real strap would)."""
    a, b = prof[max(i - 1, 0)], prof[min(i + 1, len(prof) - 1)]
    ty, tz = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(ty, tz) or 1.0
    ny, nz = tz / ln, -ty / ln
    py, pz = prof[i]
    path = [(x, RW + py * ky + ny * 0.004, 1.295 + (pz - 1.295) * kz + nz * 0.004)
            for (x, ky, kz) in BOOT_X]
    L.add_sweep(bm, path, L.rect_profile(w, d), up=(0, ny, nz), uv=None)

bm = bmesh.new()      # iron strap ribs over the boot lid, replacing the leather straps
for sx in (-1, 1):
    pts = [(sx * 0.345, RW + py * 1.0 + 0.014 * (1 if py > 0.1 else 0), pz + 0.012)
           for (py, pz) in [(0.0, 1.985), (0.20, 1.965), (0.36, 1.915), (0.475, 1.81),
                            (0.53, 1.645), (0.547, 1.45), (0.527, 1.31)]]
    L.add_sweep(bm, L.catmull(pts, 3), L.rect_profile(0.065, 0.014), up=(1, 0, 0), uv='SweepUV')
L.add_box(bm, (0.16, 0.055, 0.12), (0, RW + 0.556, 1.545), bevel=0.006)        # hasp plate
boot_band(bm, 4)                                                   # band above the lock
boot_band(bm, 6, 0.065)                                            # band over the lid crown
P('boot_ribs', bm, M['plate'], 'Body', 'A', 0.7, smooth=40)

bm = bmesh.new()      # padlock on the boot
L.add_box(bm, (0.075, 0.032, 0.085), (0, RW + 0.592, 1.475), bevel=0.008, segs=2)
L.add_rod(bm, L.catmull([(-0.026, RW + 0.592, 1.512), (-0.026, RW + 0.592, 1.552),
                         (0.0, RW + 0.592, 1.568), (0.026, RW + 0.592, 1.552),
                         (0.026, RW + 0.592, 1.512)], 2), 0.009, 4)
P('boot_lock', bm, M['brass'], 'Body', 'A', 0.5, smooth=40)

bm = bmesh.new()
L.add_box(bm, (1.34, 0.60, 0.055), (0, RW + 0.28, 1.262), bevel=0.01)
P('boot_platform', bm, M['wood'], 'Body', 'A', 0.6, smooth=None)

bm = bmesh.new()
for sx in (-1, 1):
    L.add_rod(bm, [(sx * 0.675, RW + 0.56, 1.28), (sx * 0.675, RW + 0.01, 1.93)], 0.016, 5)
    L.add_box(bm, (0.045, 0.045, 0.028), (sx * 0.675, RW + 0.555, 1.285))
P('boot_stays', bm, M['iron'], 'Body', 'A', 0.3)

# ----------------------------------------------------------------------------
# ROOF LOAD (Body group, atlas B). Rear-right (-X, +Y) stays clear for the guard.
# ----------------------------------------------------------------------------
log('strongbox')
BOX_C = (0.14, YC - 0.50, 0.0)
BOX_Z0 = RT + 0.02
BW, BL, BH = 0.92, 0.58, 0.40            # x, y, z of the chest body
M['strongbox'] = L.surface('strongbox', L.srgb(30, 42, 34), var=0.12, rough=0.45, metal=0.15,
                           wear_col=L.srgb(150, 146, 138), wear=0.9, wear_rough=0.3,
                           wear_metal=0.9, edge_r=0.012, edge_w=(0.01, 0.10), dust=0.55,
                           dust_up=1.0, dust_z=(1.6, 2.9), ao=0.8, bump=0.12, blotch=0.3,
                           extra=box_decal)

bm = bmesh.new()
L.add_box(bm, (BW, BL, BH - 0.07), (BOX_C[0], BOX_C[1], BOX_Z0 + (BH - 0.07) / 2), bevel=0.012)
L.add_box(bm, (BW + 0.02, BL + 0.02, 0.08), (BOX_C[0], BOX_C[1], BOX_Z0 + BH - 0.035),
          bevel=0.012)                                                      # lid
P('strongbox', bm, M['strongbox'], 'Body', 'B', 1.3, smooth=40)

bm = bmesh.new()      # iron bands round the chest + corner plates + hasp
for dx in (-0.30, 0.30):
    L.add_box(bm, (0.07, BL + 0.036, BH + 0.02), (BOX_C[0] + dx, BOX_C[1], BOX_Z0 + BH / 2 - 0.02))
L.add_box(bm, (0.10, 0.05, 0.13), (BOX_C[0], BOX_C[1] - BL / 2 - 0.02, BOX_Z0 + BH - 0.12))
for dx in (-0.26, 0.26):                                    # roof D-rings the chains tie to
    L.add_box(bm, (0.05, 0.075, 0.022), (BOX_C[0] + dx, YC + 0.105, RT + 0.015))
P('box_bands', bm, M['plate'], 'Body', 'B', 0.9, smooth=None)

bm = bmesh.new()      # padlock, driver's side of the chest
L.add_box(bm, (0.065, 0.028, 0.075), (BOX_C[0], BOX_C[1] - BL / 2 - 0.035, BOX_Z0 + BH - 0.195),
          bevel=0.008, segs=2)
P('box_lock', bm, M['brass'], 'Body', 'B', 0.4, smooth=40)

bm = bmesh.new()      # chains lashing the chest to the roof rail
for dx in (-0.26, 0.26):
    L.add_sweep(bm, L.catmull([(BOX_C[0] + dx, YC - 1.05, 2.40),
                               (BOX_C[0] + dx, BOX_C[1] - BL / 2 - 0.03, BOX_Z0 + BH + 0.01),
                               (BOX_C[0] + dx, BOX_C[1], BOX_Z0 + BH + 0.045),
                               (BOX_C[0] + dx, BOX_C[1] + BL / 2 + 0.03, BOX_Z0 + BH + 0.01),
                               (BOX_C[0] + dx, YC + 0.10, RT + 0.02)], 3),
                L.circle_profile(0.013, 4), uv='SweepUV')
P('box_chains', bm, M['chain'], 'Body', 'B', 0.5, smooth=60)

log('roof rack load')
bm = bmesh.new()      # iron-bound ammunition crate, left of the guard
L.add_box(bm, (0.46, 0.40, 0.28), (0.40, YC + 0.62, RT + 0.14), rot=(0, 0, math.radians(-5)),
          bevel=0.014)
P('crate', bm, M['crate'], 'Body', 'B', 0.8, smooth=None)
bm = bmesh.new()
for dy in (-0.13, 0.13):
    L.add_box(bm, (0.48, 0.05, 0.30), (0.40, YC + 0.62 + dy, RT + 0.14), rot=(0, 0, math.radians(-5)))
P('crate_bands', bm, M['plate'], 'Body', 'B', 0.5, smooth=None)

bm = bmesh.new()      # guard's folded blanket (his seat) + bedroll backrest
L.add_box(bm, (0.50, 0.46, 0.06), (-0.42, YC + 0.80, RT + 0.03), rot=(0, 0, math.radians(3)),
          bevel=0.02, segs=2)
L.add_cyl(bm, 0.105, 0.105, 0.64, 10, loc=(-0.40, YC + 1.06, RT + 0.10), rot=(0, math.pi / 2, 0))
P('blanket', bm, M['blanket'], 'Body', 'B', 0.8, smooth=40)
bm = bmesh.new()
for xs in (-0.60, -0.20):
    circ = [(xs, YC + 1.06 + 0.112 * math.cos(2 * math.pi * i / 10),
             RT + 0.10 + 0.112 * math.sin(2 * math.pi * i / 10)) for i in range(10)]
    L.add_sweep(bm, circ, L.rect_profile(0.03, 0.006), closed_path=True, uv='SweepUV', up=(1, 0, 0))
P('bedroll_straps', bm, M['leather'], 'Body', 'B', 0.2)

bm = bmesh.new()      # canvas roll wedged against the front rail
L.add_cyl(bm, 0.105, 0.105, 0.70, 8, loc=(-0.36, YC - 0.92, RT + 0.10), rot=(0, math.pi / 2, 0))
P('canvas_roll', bm, M['canvas'], 'Body', 'B', 0.5, smooth=60)

log('roof rail')
bm = bmesh.new()
RX, RY0, RY1, RZ = 0.705, YC - 1.07, YC + 1.12, 2.415
rc = 0.07
path = []
for (cx, cy, a0) in ((RX - rc, RY1 - rc, 0), (-RX + rc, RY1 - rc, 90), (-RX + rc, RY0 + rc, 180),
                     (RX - rc, RY0 + rc, 270)):
    for k in range(4):
        a = math.radians(a0 + k * 30)
        path.append((cx + rc * math.cos(a), cy + rc * math.sin(a), RZ))
L.add_sweep(bm, path, L.rect_profile(0.036, 0.028, 0.008), closed_path=True, uv=None)
posts = []
for y in [RY0 + 0.02, RY0 + 0.50, YC + 0.30, RY1 - 0.02]:
    posts += [(RX, y), (-RX, y)]
for x in (-0.36, 0.36):
    posts += [(x, RY1), (x, RY0)]
for (x, y) in posts:
    L.add_beam(bm, (x, y, D.ROOF_TOP - 0.03), (x, y, RZ), 0.024, 0.024, up=(0, 1, 0), caps=False)
for y in (YC - 1.02, YC + 1.06):                      # iron straps across the roof crown
    L.add_sweep(bm, [(RX, y, 2.215), (0.0, y, 2.268), (-RX, y, 2.215)],
                L.rect_profile(0.05, 0.012), uv=None, up=(0, 1, 0))
P('rail', bm, M['plate'], 'Body', 'A', 0.7, smooth=40)

# ----------------------------------------------------------------------------
# CHASSIS — same layout as the Concord, heavier timbers
# ----------------------------------------------------------------------------
log('chassis')
bm = bmesh.new()
L.add_box(bm, (1.34, 0.13, 0.12), (0, RA, D.REAR_R + 0.08), bevel=0.012)                  # rear bed
L.add_box(bm, (1.22, 0.12, 0.12), (0, FA, D.FRONT_R + 0.075), bevel=0.012)                # front bed
L.add_box(bm, (1.26, 0.14, 0.13), (0, FA, 0.715), bevel=0.012)                            # bolster
L.add_beam(bm, (0, FA + 0.05, 0.64), (0, RA + 0.2, 0.80), 0.095, 0.095, bevel=0.01)       # reach
for sx in (-1, 1):
    L.add_beam(bm, (0, RA - 0.75, 0.74), (sx * 0.58, RA, 0.80), 0.065, 0.065, bevel=0.008)
    L.add_beam(bm, (sx * 0.34, FA, 0.60), (0, FA - 0.50, 0.63), 0.058, 0.058, bevel=0.008)
    L.add_beam(bm, (sx * 0.34, FA, 0.60), (0, FA + 0.42, 0.64), 0.058, 0.058, bevel=0.008)
    # thoroughbrace jacks (C-standards)
    L.add_sweep(bm, L.catmull([(sx * 0.5, RA + 0.02, 0.80), (sx * 0.5, RA + 0.08, 0.97),
                               (sx * 0.5, RA + 0.20, 1.10), (sx * 0.5, RA + 0.33, 1.17),
                               (sx * 0.5, RA + 0.40, 1.19)], 3), L.rect_profile(0.075, 0.085, 0.012),
                uv=None)
    L.add_sweep(bm, L.catmull([(sx * 0.5, FA + 0.06, 0.76), (sx * 0.5, FA + 0.10, 0.95),
                               (sx * 0.5, FA + 0.04, 1.10), (sx * 0.5, FA - 0.06, 1.17),
                               (sx * 0.5, FA - 0.13, 1.19)], 3), L.rect_profile(0.075, 0.085, 0.012),
                uv=None)
# pole, yoke, doubletree, singletrees, brake beam
L.add_sweep(bm, [(0, FA + 0.2, 0.585), Vector(D.HITCH)], L.circle_profile(0.052, 8),
            scales=[1.0, 0.68], uv=None)
L.add_box(bm, (0.95, 0.06, 0.06), (0, D.HITCH[1] + 0.12, D.HITCH[2] - 0.02), bevel=0.01)
L.add_box(bm, (1.12, 0.08, 0.085), (0, FA - 0.40, 0.655), bevel=0.012)
for sx in (-1, 1):
    L.add_box(bm, (0.62, 0.055, 0.06), (sx * 0.55, FA - 0.48, 0.655), bevel=0.01)
L.add_box(bm, (1.92, 0.075, 0.08), (0, 0.175, 0.60), bevel=0.01)
P('gear_wood', bm, M['gear'], 'Chassis', 'B', 0.6, smooth=35)

bm = bmesh.new()
L.add_cyl(bm, 0.040, 0.040, 1.84, 8, loc=(0, RA, D.REAR_R), rot=(0, math.pi / 2, 0))
L.add_cyl(bm, 0.036, 0.036, 1.72, 8, loc=(0, FA, D.FRONT_R), rot=(0, math.pi / 2, 0))
L.add_lathe(bm, [(0.33, 0.645), (0.38, 0.645), (0.38, 0.668), (0.33, 0.668)], 16,
            Matrix.Translation((0, FA, 0)), closed=True)                    # fifth wheel
for sx in (-1, 1):
    L.add_box(bm, (0.085, 0.08, 0.055), (sx * 0.5, RA + 0.40, 1.20), bevel=0.006)
    L.add_box(bm, (0.085, 0.08, 0.055), (sx * 0.5, FA - 0.13, 1.20), bevel=0.006)
    L.add_box(bm, (0.09, 0.055, 0.19), (sx * D.REAR_TRACK, 0.20, 0.63), rot=(math.radians(-7), 0, 0),
              bevel=0.006)                                                  # brake shoes
    L.add_rod(bm, [(sx * 0.93, 0.175, 0.60), (sx * 0.62, RA - 0.02, 0.83)], 0.012, 4)
L.add_cyl(bm, 0.038, 0.038, 0.12, 8, loc=(0, D.HITCH[1] + 0.05, D.HITCH[2]),
          rot=(math.pi / 2 + math.atan2(0.335, 2.2), 0, 0))
L.add_lathe(bm, [(0.05, -0.013), (0.078, -0.013), (0.078, 0.013), (0.05, 0.013)], 8,
            Matrix.Translation((0, D.HITCH[1] - 0.02, D.HITCH[2])) @ Matrix.Rotation(math.pi / 2, 4, 'X'),
            closed=True)
P('gear_iron', bm, M['iron'], 'Chassis', 'B', 0.5, smooth=40)

log('thoroughbraces')
bm = bmesh.new()
for sx in (-1, 1):
    x = sx * D.BRACE_X
    front_tip, rear_tip = (FA - 0.10, 1.215), (RA + 0.37, 1.215)
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
    path = ([(x, front_tip[0] - 0.05, 1.20)] + [(x, yy, zz) for (yy, zz) in simp]
            + [(x, rear_tip[0] + 0.05, 1.20)])
    L.add_sweep(bm, path, L.rect_profile(0.100, 0.055, 0.010), uv='SweepUV', up=(0, 0, 1))
P('thoroughbraces', bm, M['leather'], 'Chassis', 'B', 0.9, smooth=40)

# ----------------------------------------------------------------------------
# WHEELS (built at their hub, spin axis = X, outer face = +X; right side mirrored)
# ----------------------------------------------------------------------------
log('wheels')


def build_wheel(name, R, nsp, segs, hub, cx, cy):
    cz = R
    W = Matrix.Translation((cx, cy, cz)) @ Matrix.Rotation(math.pi / 2, 4, 'Y')  # local Z -> +X
    bm = bmesh.new()
    rim = [(R - 0.105, -0.036), (R - 0.022, -0.036), (R, -0.032), (R, 0.032), (R - 0.022, 0.036),
           (R - 0.105, 0.036)]
    _, segf = L.add_lathe(bm, rim, segs, W, closed=True)
    for j, fs in enumerate(segf):
        for f in fs:
            f.material_index = 1 if j in (1, 2, 3) else 0
    hp = [(0.078 * hub, -0.21), (0.096 * hub, -0.195), (0.110 * hub, -0.125), (0.118 * hub, -0.07),
          (0.118 * hub, 0.0), (0.110 * hub, 0.045), (0.096 * hub, 0.085), (0.090 * hub, 0.095),
          (0.090 * hub, 0.115), (0.068 * hub, 0.12), (0.056 * hub, 0.165), (0.022, 0.173)]
    _, hs = L.add_lathe(bm, hp, 10, W @ Matrix.Translation((0, 0, -0.03)), cap0=True, cap1=True)
    for j, fs in enumerate(hs):
        for f in fs:
            f.material_index = 1 if j in (0, 7, 8, 9, 10, 11, 12) else 0
    for i in range(nsp):
        a = 2 * math.pi * (i + 0.5) / nsp
        d = Vector((math.cos(a), math.sin(a), 0))
        stag = 0.013 if i % 2 else -0.013
        p0 = W @ (d * (0.106 * hub) + Vector((0, 0, -0.045 + stag)))
        p1 = W @ (d * (R - 0.085) + Vector((0, 0, 0.0)))
        L.add_sweep(bm, [p0, p1], L.rect_profile(0.042, 0.056, 0.011), scales=[1.0, 0.80],
                    up=W.to_3x3() @ Vector((0, 0, 1)), caps=False, uv=None)
    ob = P(name, bm, [M['gear'], M['iron']], 'Wheel', 'B', 0.9 if R > 0.6 else 0.75, smooth=40)
    ob['hub'] = (cx, cy, cz)
    return ob


wheel_RL = build_wheel('Wheel_RL', D.REAR_R, 14, 28, 1.0, D.REAR_TRACK, RA)
wheel_FL = build_wheel('Wheel_FL', D.FRONT_R, 12, 24, 0.85, D.FRONT_TRACK, FA)

# ----------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------
for o in PARTS:
    o.data.update()
tot = 0
grp_tot = {}
for o in PARTS:
    n = L.tri_count(o)
    k = 2 if o.get('grp') == 'Wheel' else 1
    tot += n * k
    grp_tot[o['grp']] = grp_tot.get(o['grp'], 0) + n * k
    log('  %-16s %5d tris  atlas %s' % (o.name, n, o['atlas']))
log('groups', grp_tot)
log('TOTAL tris (with mirrored wheels):', tot, '   Concord reference: 11194')

pts = [o.matrix_world @ Vector(c) for o in PARTS for c in o.bound_box]
log('bbox  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f  (L %.3f W %.3f H %.3f)'
    % (min(p.x for p in pts), max(p.x for p in pts), min(p.y for p in pts), max(p.y for p in pts),
       min(p.z for p in pts), max(p.z for p in pts),
       max(p.y for p in pts) - min(p.y for p in pts),
       max(p.x for p in pts) - min(p.x for p in pts),
       max(p.z for p in pts) - min(p.z for p in pts)))
for k, (par, loc) in EMPTIES.items():
    log('  empty %-12s parent %-8s (%.3f, %.3f, %.3f)' % (k, par, *loc))
log('  hubs FL %s  RL %s' % (wheel_FL['hub'], wheel_RL['hub']))

if GEOM:
    log('geometry only — stopping before bake')
    sys.exit(0)

# ----------------------------------------------------------------------------
# bake
# ----------------------------------------------------------------------------
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
        img = L.new_image('coach2%s_%s' % (k, kind), TEX, non_color=(kind != 'color'))
        log('bake', k, kind)
        L.bake_pass(objs, img, kind)
        L.save_image(img, os.path.join(BUILD, 'coach2%s_%s.png' % (k, kind)))
        IMGS[(k, kind)] = img

for w in (wheel_RL, wheel_FL):
    w.location.x -= 40.0

# JPEG copies for embedding (smaller GLB) — converted with PIL (system python)
conv = []
for (k, kind) in IMGS:
    q = {'color': 86, 'orm': 80, 'normal': 85}[kind]
    conv += [os.path.join(BUILD, 'coach2%s_%s.png' % (k, kind)),
             os.path.join(BUILD, 'coach2%s_%s.jpg' % (k, kind)), str(q)]
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
FINAL = {}
for (k, kind) in IMGS:
    im2 = bpy.data.images.load(os.path.join(BUILD, 'coach2%s_%s.jpg' % (k, kind)))
    im2.name = 'Coach2%s_%s' % (k, kind)
    if kind != 'color':
        im2.colorspace_settings.name = 'Non-Color'
    FINAL[(k, kind)] = im2

MAT_NAMES = {'A': 'Treasure_Body', 'B': 'Treasure_Gear'}
FMAT = {k: L.final_material(MAT_NAMES[k], FINAL[(k, 'color')], FINAL[(k, 'orm')],
                            FINAL[(k, 'normal')]) for k in atlases}
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
    r = w.copy()                       # mirrored copy for the right side, same UVs/texture
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
for w in list(wheels.values()) + [body, chassis]:
    for key in list(w.keys()):
        del w[key]

root = L.empty('Stagecoach', (0, 0, 0), size=0.5)
bpy.context.view_layer.update()
L.parent_keep(chassis, root)
L.parent_keep(body, root)
for w in wheels.values():
    L.parent_keep(w, chassis)
for name, (par, loc) in EMPTIES.items():
    L.empty(name, loc, chassis if par == 'Chassis' else body, 0.15, 'ARROWS')
bpy.context.view_layer.update()

for o in bpy.data.objects:
    if o.type == 'MESH':
        log('  final %-10s %5d tris' % (o.name, L.tri_count(o)))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'stagecoach_treasure.blend'), compress=True)
L.export_glb(OUT)
log('exported', OUT, '%.0f KB' % (os.path.getsize(OUT) / 1024))
