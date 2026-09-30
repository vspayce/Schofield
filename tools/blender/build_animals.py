"""Build public/assets/models/animals.glb — the ambient wildlife of SCHOFIELD:
American plains bison, black/grizzly bear, pronghorn, a soaring red-tailed hawk,
the turkey vultures that work a trail carcass, and the carcass itself (a dead
horse beside the stage road, some weeks old).

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
  Buffalo                 Buffalo_Tail (origin at the tail root);
                          Buffalo_HornBull / Buffalo_HornCow under Buffalo_Head —
                          show one: thick bull horns or a cow's slender hooked ones
  Hawk                    Hawk_WingL, Hawk_WingR (origin at the shoulder), wings
                          built flat: the soaring dihedral is a rotation in code
  Vulture                 Vulture_WingL, Vulture_WingR (shoulder; flat, V in code)
                          Vulture_Head  (neck base; peck / hunch)
                          Vulture_Folded  folded wings, shown when perched
                          Vulture_Legs  (hip) standing legs, hidden in flight
                          Built in its flight attitude with the origin under the
                          feet; perched, code pitches the root nose-up by
                          PERCH (0.45 rad) about that origin — the legs are
                          modelled so they stand straight in that pose.
  Carcass                 static.  Empties Carcass_Perch (horaltic perch on the
                          hip) and Carcass_Feed1..3 (where a feeding bird stands,
                          rotated to face its food).

+X is the animal's LEFT (same convention as build_horse.py).
All six share one baked 1024 atlas / material "Animals".
"""
import bpy
import bmesh
import math
import os
import random
import shutil
import subprocess
import sys
import time
from mathutils import Vector, Matrix, noise as NZ

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
ANIMALS = ('Buffalo', 'Bear', 'Goat', 'Hawk', 'Vulture', 'Carcass')
PERCH = 0.45        # vulture standing pitch, nose up (wildlife.js has the same)


def log(*a):
    print('[animals %5.1fs]' % (time.time() - T0), *a, flush=True)


L.reset_scene()
L.setup_cycles(6 if QUICK else 40)
# small islands (six animals in one atlas): a big EXTEND margin would flood them
bpy.context.scene.render.bake.margin = 6 if TEX >= 1024 else 2

# ----------------------------------------------------------------------------
# materials — fur/hide/feather.  No bevel-shader normals (thin wings, soft
# organic edges), a little ground dust low down, hair grain from noise.
# Masks read object-space position (immune to the bake offset) or the 'P'
# UV layer some parts carry: wings (span, chord), tails (across, along),
# horns and bills (metres from the base).
# ----------------------------------------------------------------------------
DUSTY = dict(dust=0.22, dust_z=(0.0, 0.9), dust_up=0.0, dust_scale=4.0,
             dust_col=L.srgb(152, 130, 100))
FUR = dict(metal=0.0, rough=0.78, rough_var=0.10, wear=0.0, bevel_normal=False,
           ao=0.55, ao_dist=0.12, bump=0.35, bump_scale=110.0, bump_dist=0.004, **DUSTY)
FEATHER = dict(FUR, bump_scale=200.0, bump=0.3, dust=0.0, ao_dist=0.05, rough=0.62)


def oxyz(mb):
    return mb.xyz(mb.tc.outputs['Object'])


def puv(mb):
    u, v, _ = mb.xyz(mb.uv('PUV'))
    return u, v


def band(mb, x, a, b, soft):
    """1 inside [a, b], soft edges."""
    return mb.m('MULTIPLY', mb.smooth(x, a - soft, a + soft), mb.smooth(x, b + soft, b - soft))


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


def strands(mb, st, freq, amt, dark, light=None, vert=4.0):
    """Hanging hair: stretched noise -> strand height, dark roots, paler tips."""
    h = mb.noise(mb.aniso(mb.tc.outputs['Object'], freq, freq, vert), 1.0, 5.0, 0.7)
    hs = mb.smooth(h, 0.30, 0.72)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.m('SUBTRACT', 1.0, hs), amt), st['col'], dark)
    if light is not None:
        st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(h, 0.62, 0.82), amt * 0.6), st['col'], light)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', hs, 1.2))


# --- plains bison, late summer: tawny cape, blackish head / beard / chaps,
#     short dark-chocolate hindquarters with the last ragged moult tufts
def bison_rear(mb, st):
    ox, oy, oz = oxyz(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    # short dense hair lying back along the body
    g = mb.noise(mb.aniso(mb.tc.outputs['Object'], 90.0, 14.0, 90.0), 1.0, 4.0, 0.6)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(g, 0.4, 0.75), 0.25), st['col'], L.srgb(30, 20, 13))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.4), mb.m('MULTIPLY', g, 0.5))
    # ragged pale moult tufts on the flanks and thighs
    n1 = mb.noise(mb.tc.outputs['Object'], 3.2, 3.0, 0.6)
    n2 = mb.noise(mb.aniso(mb.tc.outputs['Object'], 40.0, 40.0, 12.0), 1.0, 4.0, 0.7)
    patch = mb.m('MULTIPLY', mb.smooth(n1, 0.60, 0.68), mb.smooth(n2, 0.35, 0.6))
    patch = mb.m('MULTIPLY', patch, mb.smooth(mb.m('ABSOLUTE', nx), 0.25, 0.6))
    patch = mb.m('MULTIPLY', patch, band(mb, oz, 0.75, 1.45, 0.08))
    patch = mb.m('MULTIPLY', patch, band(mb, oy, 0.05, 1.10, 0.1))
    st['col'] = mb.mixc(mb.m('MULTIPLY', patch, 0.9), st['col'], L.srgb(110, 90, 69))
    st['height'] = mb.m('ADD', st['height'], mb.m('MULTIPLY', patch, 0.9))
    # darker belly and lower legs
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(oz, 0.95, 0.55), 0.45), st['col'], L.srgb(33, 23, 16))


def bison_cape(mb, st):
    ox, oy, oz = oxyz(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    # woolly curls: clumps of matted wool with dark crevices
    wool = mb.aniso(mb.tc.outputs['Object'], 1.0, 1.0, 0.6)      # locks hang a little longer
    vo = mb.voronoi(wool, 38.0, 'F1', 'Distance')
    ed = mb.voronoi(wool, 38.0, 'DISTANCE_TO_EDGE', 'Distance')
    curl = mb.m('MULTIPLY', mb.smooth(vo, 0.55, 0.0), mb.smooth(ed, 0.0, 0.12))
    n = mb.noise(mb.tc.outputs['Object'], 9.0, 4.0, 0.6)
    # golden-tawny on the hump, browner down the shoulder, dark toward head,
    # throat and the hanging brisket
    top = mb.m('MULTIPLY', mb.smooth(oz, 1.35, 1.75), mb.smooth(nz, -0.2, 0.6))
    st['col'] = mb.mixc(top, st['col'], L.srgb(132, 96, 60))
    low = mb.m('MAXIMUM', mb.smooth(oz, 1.40, 1.05), mb.smooth(oy, -0.90, -1.15))
    st['col'] = mb.mixc(mb.m('MULTIPLY', low, 0.95), st['col'], L.srgb(40, 28, 20))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.m('SUBTRACT', 1.0, curl), 0.22), st['col'], L.srgb(40, 27, 18))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(n, 0.55, 0.75), 0.25), st['col'], L.srgb(160, 122, 80))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', curl, 1.3))


def bison_dark(mb, st):
    strands(mb, st, 30.0, 0.5, L.srgb(20, 14, 10), L.srgb(66, 48, 34))


def bison_face(mb, st):
    ox, oy, oz = oxyz(mb)
    g = mb.noise(mb.aniso(mb.tc.outputs['Object'], 60.0, 20.0, 60.0), 1.0, 4.0, 0.6)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(g, 0.45, 0.8), 0.3), st['col'], L.srgb(60, 44, 32))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.4), mb.m('MULTIPLY', g, 0.4))


def horn_base(base_col, reach):
    def fn(mb, st):
        u, v = puv(mb)
        st['col'] = mb.mixc(mb.smooth(u, reach, reach * 0.35), st['col'], base_col)
        ring = mb.m('MULTIPLY', mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 140.0)), 0.3, 0.9),
                    mb.smooth(u, reach * 1.3, 0.0))
        st['height'] = mb.m('ADD', st['height'], mb.m('MULTIPLY', ring, 0.6))
        st['rough'] = mb.mixf(mb.smooth(u, reach, 0.0), st['rough'], 0.7)
    return fn


# --- red-tailed hawk, western light morph
def rt_body(mb, st):
    ox, oy, oz = oxyz(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    pale = L.srgb(239, 228, 214)
    under = mb.smooth(nz, 0.25, -0.25)                        # 1 below
    ob = mb.tc.outputs['Object']
    streak = mb.smooth(mb.noise(mb.aniso(ob, 260.0, 55.0, 260.0), 1.0, 3.0, 0.6), 0.5, 0.66)
    col = mb.mixc(mb.m('MULTIPLY', streak, 0.25), pale, L.srgb(150, 110, 78))
    # belly band: heavy dark streaks and rufous wash across the lower breast
    bb = mb.m('MULTIPLY', band(mb, oy, -0.06, 0.035, 0.022), mb.smooth(mb.m('ABSOLUTE', ox), 0.09, 0.01))
    blot = mb.smooth(mb.noise(mb.aniso(ob, 150.0, 70.0, 150.0), 1.0, 3.0, 0.6), 0.40, 0.58)
    col = mb.mixc(mb.m('MULTIPLY', bb, 0.55), col, L.srgb(201, 138, 90))
    col = mb.mixc(mb.m('MULTIPLY', bb, mb.m('MULTIPLY', blot, 0.95)), col, L.srgb(74, 48, 32))
    # rufous-washed flanks and barred trousers
    col = mb.mixc(mb.m('MULTIPLY', band(mb, oy, 0.05, 0.12, 0.02), 0.45), col, L.srgb(196, 140, 96))
    # brown head, a darker (calurus) throat and cheeks
    head = mb.smooth(oy, -0.115, -0.135)
    col = mb.mixc(mb.m('MULTIPLY', head, 0.85), col, L.srgb(104, 76, 54))
    st['col'] = mb.mixc(under, st['col'], col)
    # back: dark brown, pale mottled scapulars in a loose V
    mot = mb.smooth(mb.noise(ob, 120.0, 3.0, 0.6), 0.52, 0.64)
    v = mb.m('MULTIPLY', band(mb, oy, -0.07, 0.04, 0.02), band(mb, mb.m('ABSOLUTE', ox), 0.02, 0.06, 0.012))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.m('MULTIPLY', v, mot), mb.m('SUBTRACT', 1.0, under)),
                        st['col'], L.srgb(200, 182, 156))
    fe = mb.smooth(mb.voronoi(mb.aniso(ob, 1.0, 0.6, 1.0), 70.0, 'F1', 'Distance'), 0.1, 0.5)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', fe, 0.6))


def rt_wing(mb, st):
    u, v = puv(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    under = mb.smooth(nz, 0.2, -0.2)
    # feather rows: coverts in scalloped rows, flight feathers in long vanes
    rows = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 140.0)), 0.6, 1.0)
    flight = mb.smooth(v, 0.44, 0.52)
    # --- underside: pale linings and flight feathers, fine grey bars,
    #     dark trailing edge and tips, patagial bar and carpal comma
    bars = mb.m('MULTIPLY', mb.smooth(mb.m('SINE', mb.m('MULTIPLY', v, 70.0)), 0.55, 0.9), flight)
    ucol = mb.mixc(mb.m('MULTIPLY', bars, 0.30), L.srgb(240, 232, 222), L.srgb(160, 150, 142))
    spk = mb.smooth(mb.noise(mb.aniso(mb.tc.outputs['Object'], 90.0, 90.0, 20.0), 1.0, 3.0, 0.6), 0.6, 0.7)
    ucol = mb.mixc(mb.m('MULTIPLY', mb.m('MULTIPLY', spk, mb.m('SUBTRACT', 1.0, flight)), 0.45), ucol,
                   L.srgb(170, 112, 72))
    trail = mb.m('MULTIPLY', mb.smooth(v, 0.80, 0.90), mb.smooth(u, 0.80, 0.70))
    tips = mb.smooth(u, 0.80, 0.90)
    dark = L.srgb(46, 36, 32)
    ucol = mb.mixc(mb.m('MAXIMUM', mb.m('MULTIPLY', trail, 0.8), mb.m('MULTIPLY', tips, 0.92)), ucol, dark)
    pat = mb.m('MULTIPLY', mb.smooth(v, 0.15, 0.09), band(mb, u, 0.08, 0.48, 0.02))
    cd = mb.v('LENGTH', mb.comb(mb.m('DIVIDE', mb.m('SUBTRACT', u, 0.495), 0.030),
                                mb.m('DIVIDE', mb.m('SUBTRACT', v, 0.08), 0.14), 0.0))
    comma = mb.smooth(cd, 1.0, 0.72)
    ucol = mb.mixc(mb.m('MAXIMUM', pat, comma), ucol, L.srgb(58, 38, 24))
    # --- top: dark brown, paler-edged coverts, pale scapular mottling at the root
    cov = mb.smooth(mb.noise(mb.aniso(mb.tc.outputs['Object'], 60.0, 90.0, 60.0), 1.0, 3.0, 0.6), 0.5, 0.7)
    tcol = mb.mixc(mb.m('MULTIPLY', mb.m('MAXIMUM', mb.m('MULTIPLY', rows, 0.3), cov),
                        mb.m('MULTIPLY', mb.m('SUBTRACT', 1.0, flight), 0.45)),
                   L.srgb(78, 53, 36), L.srgb(132, 100, 70))
    tcol = mb.mixc(mb.m('MULTIPLY', flight, 0.55), tcol, L.srgb(56, 42, 32))
    tcol = mb.mixc(mb.m('MULTIPLY', tips, 0.8), tcol, dark)
    scap = mb.m('MULTIPLY', mb.smooth(u, 0.14, 0.05), band(mb, v, 0.12, 0.5, 0.05))
    mot = mb.smooth(mb.noise(mb.tc.outputs['Object'], 110.0, 3.0, 0.6), 0.5, 0.62)
    tcol = mb.mixc(mb.m('MULTIPLY', scap, mot), tcol, L.srgb(196, 176, 150))
    st['col'] = mb.mixc(under, tcol, ucol)
    vane = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 260.0)), 0.8, 1.0)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.25),
                        mb.m('MULTIPLY', mb.m('MAXIMUM', mb.m('MULTIPLY', rows, 0.6), vane), 0.3))


def rt_tail(mb, st):
    u, v = puv(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    under = mb.smooth(nz, 0.2, -0.2)
    sub = band(mb, v, 0.84, 0.90, 0.012)
    tip = mb.smooth(v, 0.94, 0.975)
    tcol = mb.mixc(mb.m('MULTIPLY', sub, 0.9), st['col'], L.srgb(52, 30, 20))
    tcol = mb.mixc(mb.m('MULTIPLY', tip, 0.8), tcol, L.srgb(222, 206, 184))
    tcol = mb.mixc(mb.smooth(v, 0.18, 0.06), tcol, L.srgb(120, 72, 44))    # under the coverts
    ucol = mb.mixc(mb.m('MULTIPLY', sub, 0.35), L.srgb(230, 195, 172), L.srgb(140, 104, 88))
    ucol = mb.mixc(tip, ucol, L.srgb(240, 230, 214))
    st['col'] = mb.mixc(under, tcol, ucol)
    shaft = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 75.4)), 0.85, 1.0)   # 12 rectrices
    st['col'] = mb.mixc(mb.m('MULTIPLY', shaft, 0.25), st['col'], L.srgb(70, 40, 26))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', shaft, 0.5))


# --- turkey vulture: blackish-brown, silvery flight feathers below, bare red head
def tv_body(mb, st):
    ob = mb.tc.outputs['Object']
    fe = mb.voronoi(mb.aniso(ob, 1.0, 0.55, 1.0), 55.0, 'F1', 'Distance')
    edge = mb.smooth(fe, 0.25, 0.5)
    st['col'] = mb.mixc(mb.m('MULTIPLY', edge, 0.35), st['col'], L.srgb(74, 58, 46))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', mb.smooth(fe, 0.0, 0.5), 0.7))


def tv_wing(mb, st):
    u, v = puv(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    under = mb.smooth(nz, 0.2, -0.2)
    flight = mb.smooth(v, 0.42, 0.50)
    rows = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 110.0)), 0.55, 1.0)
    crow = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', v, 60.0)), 0.5, 1.0)
    # below: black linings, silvery-grey flight feathers (the two-tone), darker tips
    ucol = mb.mixc(flight, L.srgb(30, 25, 22), L.srgb(172, 170, 165))
    ucol = mb.mixc(mb.m('MULTIPLY', mb.smooth(mb.m('SINE', mb.m('MULTIPLY', v, 90.0)), 0.7, 1.0),
                        mb.m('MULTIPLY', flight, 0.18)), ucol, L.srgb(110, 108, 104))
    ucol = mb.mixc(mb.m('MULTIPLY', mb.smooth(u, 0.90, 0.98), 0.45), ucol, L.srgb(80, 76, 72))
    # above: brown coverts with pale fringes, blackish-brown flight feathers
    fr = mb.m('MULTIPLY', mb.m('MULTIPLY', rows, crow), mb.m('SUBTRACT', 1.0, flight))
    tcol = mb.mixc(mb.m('MULTIPLY', fr, 0.7), L.srgb(74, 58, 46), L.srgb(128, 108, 88))
    tcol = mb.mixc(flight, tcol, L.srgb(40, 32, 27))
    tcol = mb.mixc(mb.m('MULTIPLY', mb.m('MULTIPLY', flight, mb.smooth(u, 0.2, 0.7)), 0.25), tcol,
                   L.srgb(88, 80, 74))
    st['col'] = mb.mixc(under, tcol, ucol)
    vane = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 200.0)), 0.7, 1.0)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.25),
                        mb.m('MULTIPLY', mb.m('MAXIMUM', mb.m('MULTIPLY', fr, 0.7), vane), 0.5))


def tv_fold(mb, st):
    u, v = puv(mb)
    cov = mb.smooth(u, 0.48, 0.38)
    rows = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 70.0)), 0.55, 1.0)
    crow = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', v, 40.0)), 0.5, 1.0)
    fr = mb.m('MULTIPLY', mb.m('MULTIPLY', rows, crow), cov)
    col = mb.mixc(mb.m('MULTIPLY', fr, 0.75), L.srgb(76, 60, 48), L.srgb(132, 112, 92))
    col = mb.mixc(mb.m('SUBTRACT', 1.0, cov), col, L.srgb(42, 34, 29))
    # silvery-brown edges to the folded secondaries
    edge = mb.m('MULTIPLY', mb.smooth(mb.m('SINE', mb.m('MULTIPLY', v, 55.0)), 0.8, 1.0),
                mb.m('SUBTRACT', 1.0, cov))
    col = mb.mixc(mb.m('MULTIPLY', edge, 0.4), col, L.srgb(110, 100, 90))
    st['col'] = mb.mixc(mb.smooth(u, 0.88, 0.97), col, L.srgb(26, 22, 20))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', fr, 0.7))


def tv_tail(mb, st):
    u, v = puv(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    under = mb.smooth(nz, 0.2, -0.2)
    st['col'] = mb.mixc(under, st['col'], L.srgb(140, 138, 134))
    st['col'] = mb.mixc(mb.m('MULTIPLY', under, mb.smooth(v, 0.3, 0.05)), st['col'], L.srgb(34, 28, 24))
    shaft = mb.smooth(mb.m('SINE', mb.m('MULTIPLY', u, 75.4)), 0.85, 1.0)
    st['col'] = mb.mixc(mb.m('MULTIPLY', shaft, 0.3), st['col'], L.srgb(24, 20, 18))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.m('MULTIPLY', shaft, 0.5))


def tv_head(mb, st):
    ob = mb.tc.outputs['Object']
    ox, oy, oz = oxyz(mb)
    # bare wrinkled skin: folds across the neck, warts, paler about the eye
    wr = mb.noise(mb.aniso(ob, 40.0, 260.0, 90.0), 1.0, 4.0, 0.7)
    wart = mb.smooth(mb.voronoi(ob, 190.0, 'F1', 'Distance'), 0.35, 0.0)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(wr, 0.55, 0.8), 0.35), st['col'], L.srgb(130, 36, 34))
    eye = mb.smooth(mb.v('DISTANCE', mb.comb(mb.m('ABSOLUTE', ox), oy, oz), (0.021, -0.380, 0.261)), 0.02, 0.008)
    st['col'] = mb.mixc(mb.m('MULTIPLY', eye, 0.8), st['col'], L.srgb(216, 106, 94))
    st['col'] = mb.mixc(mb.m('MULTIPLY', wart, 0.5), st['col'], L.srgb(214, 120, 104))
    # dusky nape where the skin meets the ruff
    st['col'] = mb.mixc(mb.smooth(oy, -0.35, -0.335), st['col'], L.srgb(96, 40, 40))
    st['col'] = mb.mixc(mb.smooth(oy, -0.325, -0.305), st['col'], L.srgb(44, 34, 30))   # feathered lower neck
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.2),
                        mb.m('ADD', mb.m('MULTIPLY', wr, 0.8), mb.m('MULTIPLY', wart, 0.6)))


def bill_base(base_col, reach):
    def fn(mb, st):
        u, v = puv(mb)
        st['col'] = mb.mixc(mb.smooth(u, reach, reach * 0.4), st['col'], base_col)
    return fn


def tv_leg(mb, st):
    sc = mb.voronoi(mb.tc.outputs['Object'], 500.0, 'F1', 'Distance')
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3), mb.smooth(sc, 0.0, 0.5))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(sc, 0.3, 0.6), 0.25), st['col'], L.srgb(170, 150, 140))


# --- carcass: sun-dried, dust-caked hide, weathered bone, a dark dry cavity
def carc_hide(mb, st):
    ob = mb.tc.outputs['Object']
    ox, oy, oz = oxyz(mb)
    nx, ny, nz = mb.xyz(mb.nrm)
    # dry cracking and rubbed-bare patches
    cr = mb.voronoi(ob, 9.0, 'DISTANCE_TO_EDGE', 'Distance')
    crack = mb.m('MULTIPLY', mb.smooth(cr, 0.012, 0.0), mb.smooth(mb.noise(ob, 3.0, 2.0), 0.55, 0.7))
    st['col'] = mb.mixc(mb.m('MULTIPLY', crack, 0.35), st['col'], L.srgb(84, 70, 56))
    hs = mb.noise(mb.aniso(ob, 160.0, 25.0, 160.0), 1.0, 4.0, 0.6)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(hs, 0.45, 0.75), 0.3), st['col'], L.srgb(104, 88, 70))
    bare = mb.smooth(mb.noise(ob, 5.0, 4.0, 0.6), 0.58, 0.68)
    st['col'] = mb.mixc(mb.m('MULTIPLY', bare, 0.55), st['col'], L.srgb(170, 150, 122))
    # the old coat's darker points on the lower legs, and a bleached upper flank
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(ox, 0.60, 0.85), 0.7), st['col'], L.srgb(92, 76, 62))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(nz, 0.5, 0.95), 0.30), st['col'], L.srgb(152, 134, 110))
    hair = mb.noise(mb.aniso(ob, 70.0, 12.0, 70.0), 1.0, 4.0, 0.6)
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.3),
                        mb.m('ADD', mb.m('MULTIPLY', mb.m('ADD', hair, hs), 0.3), mb.m('MULTIPLY', crack, -0.5)))


def bone(mb, st):
    ob = mb.tc.outputs['Object']
    cr = mb.noise(mb.aniso(ob, 12.0, 60.0, 12.0), 1.0, 4.0, 0.7)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(cr, 0.62, 0.72), 0.5), st['col'], L.srgb(150, 136, 110))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(mb.noise(ob, 8.0, 3.0), 0.55, 0.7), 0.6), st['col'],
                        L.srgb(232, 226, 210))
    st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.4), mb.m('MULTIPLY', cr, 0.4))


def cavity(mb, st):
    n = mb.noise(mb.tc.outputs['Object'], 18.0, 5.0, 0.7)
    st['col'] = mb.mixc(mb.smooth(n, 0.4, 0.7), st['col'], L.srgb(40, 26, 20))
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(n, 0.66, 0.8), 0.5), st['col'], L.srgb(92, 70, 52))


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
    band_ = mb.m('MULTIPLY', mb.smooth(b, 0.25, 0.8), mb.smooth(mb.m('MULTIPLY', nz, -1.0), 0.0, 0.6))
    st['col'] = mb.mixc(mb.m('MULTIPLY', band_, 0.9), st['col'], pale)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.mapr(y, -0.60, -0.74, 0.0, 1.0), 0.55), st['col'], pale)
    st['col'] = mb.mixc(mb.m('MULTIPLY', mb.smooth(nz, 0.6, 1.0), 0.55), st['col'],
                        L.srgb(70, 46, 28))


M = {}
M['bis_rear'] = L.surface('bis_rear', L.srgb(64, 42, 24), var=0.12, var_scale=5.0, blotch=0.25,
                          extra=bison_rear, **dict(FUR, bump_scale=160.0))
M['bis_cape'] = L.surface('bis_cape', L.srgb(112, 80, 50), var=0.14, var_scale=6.0, blotch=0.3,
                          extra=bison_cape, **dict(FUR, bump=0.5))
M['bis_dark'] = L.surface('bis_dark', L.srgb(35, 24, 18), var=0.14, var_scale=7.0, blotch=0.3,
                          extra=bison_dark, **dict(FUR, bump=0.5))
M['bis_face'] = L.surface('bis_face', L.srgb(40, 28, 20), var=0.12, var_scale=9.0, blotch=0.2,
                          extra=bison_face, **FUR)
M['bear'] = L.surface('bear', L.srgb(74, 51, 34), var=0.18, var_scale=5.0, blotch=0.35,
                      extra=bear_hide, **FUR)
M['muzzle'] = L.surface('muzzle', L.srgb(112, 86, 58), var=0.14, var_scale=8.0, blotch=0.3,
                        **FUR)
M['goat'] = L.surface('goat', L.srgb(158, 110, 60), var=0.13, var_scale=6.0, blotch=0.25,
                      extra=goat_hide, **FUR)
M['goat_face'] = L.surface('goat_face', L.srgb(154, 108, 58), var=0.12, var_scale=9.0,
                           blotch=0.22, extra=goat_face, **FUR)
M['rt_body'] = L.surface('rt_body', L.srgb(78, 53, 36), var=0.12, var_scale=9.0, blotch=0.2,
                         extra=rt_body, **FEATHER)
M['rt_wing'] = L.surface('rt_wing', L.srgb(78, 53, 36), var=0.08, var_scale=9.0, blotch=0.0,
                         extra=rt_wing, **FEATHER)
M['rt_tail'] = L.surface('rt_tail', L.srgb(168, 68, 32), var=0.07, var_scale=12.0, blotch=0.0,
                         extra=rt_tail, **FEATHER)
M['tv_body'] = L.surface('tv_body', L.srgb(42, 33, 28), var=0.10, var_scale=9.0, blotch=0.2,
                         extra=tv_body, **dict(FEATHER, rough=0.55))
M['tv_wing'] = L.surface('tv_wing', L.srgb(42, 33, 28), var=0.07, var_scale=9.0, blotch=0.0,
                         extra=tv_wing, **dict(FEATHER, rough=0.55))
M['tv_fold'] = L.surface('tv_fold', L.srgb(42, 33, 28), var=0.07, var_scale=9.0, blotch=0.0,
                         extra=tv_fold, **dict(FEATHER, rough=0.55))
M['tv_tail'] = L.surface('tv_tail', L.srgb(40, 32, 27), var=0.07, var_scale=12.0, blotch=0.0,
                         extra=tv_tail, **dict(FEATHER, rough=0.55))
M['tv_head'] = L.surface('tv_head', L.srgb(184, 64, 58), var=0.10, var_scale=40.0, blotch=0.2,
                         extra=tv_head, **dict(FEATHER, rough=0.5, bump=0.5, bump_scale=300.0))
M['carc_hide'] = L.surface('carc_hide', L.srgb(126, 106, 86), var=0.14, var_scale=4.0, blotch=0.35,
                           extra=carc_hide, **dict(FUR, rough=0.9, dust=0.45, dust_z=(0.0, 0.35)))
M['carc_hair'] = L.surface('carc_hair', L.srgb(58, 46, 37), var=0.14, var_scale=9.0, blotch=0.2,
                           extra=lambda mb, st: strands(mb, st, 60.0, 0.4, L.srgb(34, 27, 22),
                                                        L.srgb(110, 94, 76), 1.0),
                           **dict(FUR, dust=0.35))
M['cavity'] = L.surface('cavity', L.srgb(58, 36, 28), var=0.12, var_scale=10.0, blotch=0.3,
                        extra=cavity, **dict(FUR, rough=0.95, dust=0.0, ao=0.8, ao_dist=0.2))
HARD = dict(metal=0.0, wear=0.0, bevel_normal=False, ao=0.6, ao_dist=0.08, **DUSTY)
M['horn'] = L.surface('horn', L.srgb(56, 50, 46), var=0.16, var_scale=14.0, rough=0.42,
                      blotch=0.3, grain='Z', grain_amt=0.35, grain_freq=9.0, bump=0.22,
                      bump_scale=180.0, **HARD)
M['bis_horn'] = L.surface('bis_horn', L.srgb(26, 22, 20), var=0.10, var_scale=20.0, rough=0.40,
                          blotch=0.2, bump=0.25, bump_scale=160.0, extra=horn_base(L.srgb(74, 64, 56), 0.10),
                          **HARD)
M['hoof'] = L.surface('hoof', L.srgb(42, 37, 34), var=0.14, var_scale=18.0, rough=0.38,
                      bump=0.18, bump_scale=200.0, **HARD)
M['bis_hoof'] = L.surface('bis_hoof', L.srgb(30, 26, 22), var=0.12, var_scale=18.0, rough=0.65,
                          bump=0.2, bump_scale=200.0, **HARD)
M['bis_nose'] = L.surface('bis_nose', L.srgb(21, 18, 16), var=0.10, var_scale=40.0, rough=0.22,
                          bump=0.35, bump_scale=260.0, **dict(HARD, dust=0.0))
M['eye'] = L.surface('eye', L.srgb(18, 13, 10), var=0.05, var_scale=30.0, rough=0.18,
                     bump=0.0, **HARD)
M['bis_eye'] = L.surface('bis_eye', L.srgb(42, 26, 16), var=0.05, var_scale=30.0, rough=0.12,
                         bump=0.0, **dict(HARD, dust=0.0))
BIRD = dict(HARD, dust=0.0)
M['rt_beak'] = L.surface('rt_beak', L.srgb(43, 43, 46), var=0.08, var_scale=40.0, rough=0.35,
                         bump=0.1, bump_scale=300.0, extra=bill_base(L.srgb(96, 108, 122), 0.014), **BIRD)
M['rt_cere'] = L.surface('rt_cere', L.srgb(227, 194, 74), var=0.08, var_scale=40.0, rough=0.45,
                         bump=0.1, bump_scale=300.0, **BIRD)
M['rt_foot'] = L.surface('rt_foot', L.srgb(230, 190, 60), var=0.10, var_scale=60.0, rough=0.5,
                         bump=0.3, bump_scale=600.0, **BIRD)
M['rt_eye'] = L.surface('rt_eye', L.srgb(90, 48, 24), var=0.05, var_scale=40.0, rough=0.1,
                        bump=0.0, **BIRD)
M['claw'] = L.surface('claw', L.srgb(20, 18, 17), var=0.06, var_scale=40.0, rough=0.3,
                      bump=0.0, **BIRD)
M['tv_bill'] = L.surface('tv_bill', L.srgb(230, 222, 198), var=0.08, var_scale=40.0, rough=0.35,
                         bump=0.15, bump_scale=300.0, extra=bill_base(L.srgb(200, 120, 104), 0.016),
                         **BIRD)
M['tv_leg'] = L.surface('tv_leg', L.srgb(214, 195, 182), var=0.10, var_scale=40.0, rough=0.6,
                        bump=0.4, bump_scale=300.0, extra=tv_leg, **BIRD)
M['tv_eye'] = L.surface('tv_eye', L.srgb(70, 40, 26), var=0.05, var_scale=40.0, rough=0.1,
                        bump=0.0, **BIRD)
M['skull'] = L.surface('skull', L.srgb(196, 184, 160), var=0.12, var_scale=10.0, rough=0.85,
                       blotch=0.35, bump=0.35, bump_scale=120.0, extra=bone,
                       **dict(HARD, ao=0.8, dust=0.7, dust_z=(0.0, 0.3), dust_col=L.srgb(150, 128, 100)))
M['carc_hoof'] = L.surface('carc_hoof', L.srgb(58, 50, 44), var=0.14, var_scale=18.0, rough=0.78,
                           bump=0.25, bump_scale=200.0, **dict(HARD, dust=0.6, dust_z=(0.0, 0.4)))
M['bone'] = L.surface('bone', L.srgb(216, 205, 180), var=0.08, var_scale=10.0, rough=0.7,
                      blotch=0.2, bump=0.3, bump_scale=120.0, extra=bone,
                      **dict(HARD, ao=0.7, dust=0.3, dust_z=(0.0, 0.25)))

# ----------------------------------------------------------------------------
# parts / nodes
# ----------------------------------------------------------------------------
PARTS = []
PIVOTS = {}     # (animal, sub) -> world pivot point
PARENT = {}     # (animal, sub) -> sub node it hangs from (default: the root)
EMPTIES = []    # (animal, name, loc, rot_z)


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
    loft(bm, rings)
    return rings


def buv(bm):
    """The bake UV layer: created first so it is the active one."""
    return L.uv_layer(bm, 'BakeUV')


def planar_uv(faces, uvl, off=100.0):
    """Flat projection for caps (their own islands, parked out of the way)."""
    for f in faces:
        f.normal_update()
        n = f.normal if f.normal.length > 1e-6 else Vector((0, 0, 1))
        t = n.orthogonal().normalized()
        b = n.cross(t)
        for lp in f.loops:
            lp[uvl].uv = (lp.vert.co.dot(t) + off, lp.vert.co.dot(b))


def sweep_uv(bm, faces, per, puv=False):
    """add_sweep writes u = metres along, v = 0..1 around: make v metres too,
    flat-map the two caps, optionally copy u into PUV (metres from the base)."""
    bu = buv(bm)
    pu = L.uv_layer(bm, 'PUV') if puv else None
    for f in faces[:-2]:
        for lp in f.loops:
            u, v = lp[bu].uv
            lp[bu].uv = (u, v * per)
            if pu:
                lp[pu].uv = (u, v)
    planar_uv(faces[-2:], bu)


def limb(bm, pts, radii, n=7):
    """Tapered round limb through pts (world), one radius per point."""
    rmax = max(radii)
    buv(bm)
    sc = [r / rmax for r in radii]
    _, faces = L.add_sweep(bm, [Vector(p) for p in pts], L.circle_profile(rmax, n),
                           scales=sc, uv='BakeUV', up=(0, 0, 1), caps=True)
    sweep_uv(bm, faces, 2 * math.pi * rmax * sum(sc) / len(sc))
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def tube(bm, pts, radii, n=8, sub=3, aspect=1.0, up=(0, 0, 1)):
    """Smooth tube through a Catmull-Rom of pts; UV 'PUV' u = metres from the
    first point (horn bases, bill tips).  aspect squashes the section."""
    path = L.catmull(pts, sub)
    k = (len(path) - 1) / (len(pts) - 1)
    rr = []
    for i in range(len(path)):
        f = i / k
        j = min(int(f), len(radii) - 2)
        rr.append(radii[j] + (radii[j + 1] - radii[j]) * (f - j))
    rmax = max(rr)
    prof = [(rmax * math.cos(2 * math.pi * i / n), rmax * aspect * math.sin(2 * math.pi * i / n))
            for i in range(n)]
    buv(bm)
    sc = [r / rmax for r in rr]
    _, faces = L.add_sweep(bm, path, prof, scales=sc, uv='BakeUV', up=up, caps=True)
    sweep_uv(bm, faces, math.pi * rmax * (1 + aspect) * sum(sc) / len(sc), puv=True)
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def blob(bm, loc, size, sub=1):
    """Icosahedral ellipsoid — eyes, nose pads, tufts."""
    buv(bm)
    r = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0,
                                   matrix=L.mat_trs(loc, (0, 0, 0), size), calc_uvs=True)
    return r['verts']


def ear(bm, base, tip, r0, r1, n=6):
    """Blunt leaf-shaped ear: a bulge two thirds of the way out, then a point."""
    b, t = Vector(base), Vector(tip)
    limb(bm, [b, b.lerp(t, 0.45), b.lerp(t, 0.80), t], [r0 * 0.75, r0, r0 * 0.62, r1], n)


def eyes(bm, loc, r=0.022):
    for sx in (1, -1):
        blob(bm, (sx * loc[0], loc[1], loc[2]), (r, r * 0.8, r))


def hsh(*a):
    """Stable 0..1 hash of a few numbers."""
    s = math.sin(sum(v * k for v, k in zip(a, (127.1, 311.7, 74.7, 19.9)))) * 43758.5453
    return s - math.floor(s)


def loft(bm, rings, prm=None, caps=True):
    """Loft closed rings of points; prm: matching (u, v) per point -> UV 'PUV'.
    Bake UVs unroll the tube (metres around each ring x metres along); the
    caps are flat-mapped islands of their own."""
    bu = buv(bm)
    uvl = L.uv_layer(bm, 'PUV') if prm else None
    vr = [[bm.verts.new(Vector(p)) for p in r] for r in rings]
    m = len(vr[0])
    faces = []
    arc, alo = [], [0.0]
    for j, r in enumerate(rings):
        pts = [Vector(p) for p in r]
        a = [0.0]
        for i in range(m):
            a.append(a[-1] + (pts[(i + 1) % m] - pts[i]).length)
        arc.append(a)
        if j:
            c0 = sum((Vector(p) for p in rings[j - 1]), Vector()) / m
            c1 = sum(pts, Vector()) / m
            alo.append(alo[-1] + max((c1 - c0).length, 1e-4))

    def uvs(f, ids):
        if uvl:
            for lp, (j, i) in zip(f.loops, ids):
                lp[uvl].uv = prm[j][i % m]
    for j in range(len(vr) - 1):
        for i in range(m):
            i2 = (i + 1) % m
            f = bm.faces.new((vr[j][i], vr[j][i2], vr[j + 1][i2], vr[j + 1][i]))
            ids = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
            uvs(f, ids)
            for lp, (jj, ii) in zip(f.loops, ids):
                lp[bu].uv = (arc[jj][ii], alo[jj])
            faces.append(f)
    if caps:
        k = len(vr) - 1
        f = bm.faces.new(list(reversed(vr[0])))
        uvs(f, [(0, i) for i in reversed(range(m))])
        faces.append(f)
        f2 = bm.faces.new(vr[k])
        uvs(f2, [(k, i) for i in range(m)])
        faces.append(f2)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    if caps:
        planar_uv(faces[-2:], bu)
    return vr, faces


def lumps(bm, amp, freq, seed=0.0, stretch=(1, 1, 1), mask=None, verts=None):
    """Push verts along their normals by Perlin noise (amp ~ one sd): matted
    hair, wool, hide."""
    bm.normal_update()
    off = Vector((seed * 7.13, seed * 3.37, seed * 5.71))
    moves = []
    for v in (verts or bm.verts):
        m = mask(v.co) if mask else 1.0
        if m <= 0:
            continue
        p = Vector((v.co.x * freq * stretch[0], v.co.y * freq * stretch[1],
                    v.co.z * freq * stretch[2])) + off
        moves.append((v, v.normal * (NZ.noise(p) * 3.0 * amp * m)))   # noise sd ~0.3
    for v, d in moves:
        v.co += d


def drip(bm, amt, zmin=-9.0, nz=-0.35, verts=None, seed=0.0):
    """Hanging hair: pull the downward-facing verts lower, unevenly, into tufts."""
    bm.normal_update()
    moves = []
    for v in (verts or bm.verts):
        if v.normal.z > nz or v.co.z < zmin:
            continue
        k = (-v.normal.z - (-nz)) / (1.0 + nz)
        h = hsh(v.co.x * 9.1 + seed, v.co.y * 7.3, v.co.z * 5.9)
        moves.append((v, amt * min(1.0, k * 1.6) * (0.25 + 0.75 * h * h)))
    for v, d in moves:
        v.co.z -= d


class Prof:
    """Cross sections (y, z_top, z_bottom, half_width[, k_top, k_bottom]),
    interpolated smoothly in y.  at(y, a, grow) is the surface point at angle a
    (from +Z toward +X), pushed out by grow along the ellipse normal."""

    def __init__(self, secs):
        self.s = [tuple(s) + (1.0,) * (6 - len(s)) for s in secs]

    def par(self, y):
        S = self.s
        if y <= S[0][0]:
            return S[0][1:]
        if y >= S[-1][0]:
            return S[-1][1:]
        i = 0
        while S[i + 1][0] < y:
            i += 1
        t = (y - S[i][0]) / (S[i + 1][0] - S[i][0])
        p0, p1, p2, p3 = S[max(i - 1, 0)], S[i], S[i + 1], S[min(i + 2, len(S) - 1)]
        return [0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in range(1, 6)]

    def at(self, y, a, grow=0.0):
        zt, zb, hw, kt, kb = self.par(y)
        zc, hz = (zt + zb) / 2, (zt - zb) / 2
        sa, ca = math.sin(a), math.cos(a)
        k = kt if ca > 0 else kb
        x = hw * sa * (1 + (k - 1) * abs(ca))
        z = zc + hz * ca
        n = Vector((x / max(hw, 1e-4) ** 2, 0.0, (z - zc) / max(hz, 1e-4) ** 2))
        if n.length > 1e-6:
            n.normalize()
        return Vector((x, y, z)) + n * grow


def airfoil(Lp, Tp, th, cam, up, cs=(0.0, 0.08, 0.3, 0.65, 1.0)):
    """Closed feather/wing section from the leading point to the trailing point:
    top surface then bottom.  Returns [(point, chord fraction)]."""
    Lp, Tp, up = Vector(Lp), Vector(Tp), Vector(up)
    out = []

    def z(c, s):
        t = th * 2.6 * math.sqrt(c) * (1 - c)
        return up * (cam * 4 * c * (1 - c) + s * t * 0.5)
    for c in cs:
        out.append((Lp.lerp(Tp, c) + z(c, 1), c))
    for c in reversed(cs[1:-1]):
        out.append((Lp.lerp(Tp, c) + z(c, -1), c))
    return out


def sheet(bm, stations, cs=(0.0, 0.08, 0.3, 0.65, 1.0), up=(0, 0, 1)):
    """Loft airfoil sections: stations = [(Lp, Tp, thick, camber, u)];
    UV 'PUV' = (u, chord fraction)."""
    rings, prm = [], []
    for (Lp, Tp, th, cam, u) in stations:
        sec = airfoil(Lp, Tp, th, cam, up, cs)
        rings.append([p for p, c in sec])
        prm.append([(u, c) for p, c in sec])
    return loft(bm, rings, prm)


def wing(bm, sx, plan, feathers, th, cam, span, scallop, z0=0.0):
    """Arm + inner hand of a spread wing, built flat.  plan: [(x, y_lead, y_trail)]
    outward; feathers: trailing-edge feather widths from the root, each a
    rounded tip (the scalloped secondaries).  th/cam: (x) -> metres."""
    xs = [p[0] for p in plan]

    def at(x, k):
        for i in range(len(plan) - 1):
            if plan[i][0] <= x <= plan[i + 1][0] + 1e-6:
                t = (x - plan[i][0]) / (plan[i + 1][0] - plan[i][0])
                return plan[i][k] + (plan[i + 1][k] - plan[i][k]) * t
        return plan[-1][k]
    st = [(xs[0], 0.0)]
    x = xs[0]
    for w in feathers:
        st.append((x + w * 0.3, scallop * 0.8))
        st.append((x + w * 0.7, scallop * 0.8))
        x += w
        st.append((min(x, xs[-1]), -scallop * 0.4))
    stations = []
    for (x, sc) in st:
        stations.append(((sx * x, at(x, 1), z0), (sx * x, at(x, 2) + sc, z0), th(x), cam(x), x / span))
    sheet(bm, stations)


def blade(bm, base, tip, wb, th, u0, u1, curl=0.0, lead=0.38, widths=(1.0, 1.0, 0.80, 0.64, 0.46, 0.14),
          ss=(0.0, 0.42, 0.62, 0.82, 0.94, 1.0)):
    """One separated flight feather ("finger"): narrow outer vane, emarginated
    toward the rounded tip, curling up at the end like a soaring primary."""
    base, tip = Vector(base), Vector(tip)
    d = (tip - base).normalized()
    fwd = Vector((0, -1, 0))
    fwd = (fwd - d * fwd.dot(d)).normalized()
    up = d.cross(fwd).normalized()
    if up.z < 0:
        up = -up
    stations = []
    for s, w in zip(ss, widths):
        c = base.lerp(tip, s) + up * (curl * s * s)
        ww = wb * w
        stations.append((c + fwd * ww * lead, c - fwd * ww * (1 - lead), th * (1 - 0.5 * s), 0.0,
                         u0 + (u1 - u0) * s))
    rings, prm = [], []
    for (Lp, Tp, t, cam, u) in stations:
        sec = airfoil(Lp, Tp, t, cam, up, (0.0, 0.5, 1.0))
        rings.append([p for p, c in sec])
        prm.append([(u, c) for p, c in sec])
    loft(bm, rings, prm)


def fan(bm, pivot, r0, R, half, nf, th, scallop, z=0.0, cs=(0.0, 0.3, 0.7, 1.0)):
    """A tail: nf feathers fanned about pivot (pointing +Y, backwards), their
    rounded tips scalloping the edge.  UV 'PUV' = (across, along)."""
    stations = []
    n = nf * 2
    for i in range(n + 1):
        f = i / n
        ph = -half + 2 * half * f
        sc = scallop if i % 2 else -scallop * 0.2
        d = Vector((math.sin(ph), math.cos(ph), 0.0))
        pv = Vector(pivot)
        stations.append((pv + d * r0 + Vector((0, 0, z)), pv + d * (R + sc) + Vector((0, 0, z)),
                         th, 0.0, f))
    sheet(bm, stations, cs)


def hoof2(bm, c, w, l, h):
    """Cloven hoof: two toes with a cleft between, pointed toes forward."""
    for s in (1, -1):
        rings = []
        for (z, k, dy) in ((h, 0.80, 0.012), (h * 0.55, 0.94, 0.004), (0.004, 1.0, 0.0)):
            ring = []
            for i in range(10):
                a = 2 * math.pi * i / 10
                x = math.sin(a) * w * 0.25 * k
                y = math.cos(a) * l * 0.5 * k
                if y < 0:                       # toe point, turned in a little
                    y *= 1.15
                    x *= 1.0 - 0.35 * (-math.cos(a))
                if s * x < 0:                   # flat inner wall at the cleft
                    x *= 0.45
                ring.append((c[0] + s * w * 0.26 + x, c[1] + y + dy, z))
            rings.append(ring)
        loft(bm, rings)
    for s in (1, -1):                           # dewclaws
        blob(bm, (c[0] + s * w * 0.28, c[1] + l * 0.55, h + 0.03), (0.014, 0.012, 0.016))


def axial(P0, P1, secs, n, power=2.0):
    """Rings along the axis P0->P1 (a head held at any angle).  secs =
    [(t, half_width, half_depth[, offset])]; a = 0 is the forehead side."""
    P0, P1 = Vector(P0), Vector(P1)
    d = (P1 - P0).normalized()
    xa = Vector((1, 0, 0))
    na = d.cross(xa).normalized()
    if na.z < 0:
        na = -na
    rings = []
    e = 2.0 / power
    for s in secs:
        t, w, h = s[0], s[1], s[2]
        off = s[3] if len(s) > 3 else 0.0
        c = P0.lerp(P1, t) + na * off
        ring = []
        for i in range(n):
            a = 2 * math.pi * i / n
            sa, ca = math.sin(a), math.cos(a)
            ring.append(c + xa * (w * math.copysign(abs(sa) ** e, sa)) + na * (h * math.copysign(abs(ca) ** e, ca)))
        rings.append(ring)
    return rings, d, na


def rot_bm(bm, ang, axis='X', cent=(0, 0, 0)):
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=cent, matrix=Matrix.Rotation(ang, 3, axis))


# ============================================================================
# BUFFALO — American plains bison bull.  3.1 m nose to rump, 1.85 m at the
# hump.  Silhouette: a front-heavy wedge — the rounded hump peaks right over the
# forelegs, the head hangs low with the forehead in line with the hump, and the
# long tawny cape stops in a hard ragged line behind the shoulders; behind it
# the narrow hindquarters are short-haired dark chocolate.  Chaps on the
# forelegs, a beard, a forelock mop that hides the eyes, a thin tufted tail.
# ============================================================================
log('buffalo')
A = 'Buffalo'
BUF_NECK = (0.0, -0.80, 1.30)
BODY = Prof([
    (-1.04, 1.50, 0.96, 0.25, 0.70, 0.80),
    (-0.88, 1.68, 0.80, 0.35, 0.55, 0.78),
    (-0.70, 1.73, 0.67, 0.42, 0.50, 0.72),
    (-0.50, 1.795, 0.63, 0.45, 0.50, 0.80),
    (-0.30, 1.765, 0.62, 0.46, 0.56, 0.90),
    (-0.10, 1.665, 0.63, 0.45, 0.66, 0.95),
    (0.10, 1.565, 0.66, 0.43, 0.80, 0.97),
    (0.35, 1.51, 0.72, 0.40, 0.88, 1.00),
    (0.60, 1.48, 0.76, 0.37, 0.92, 1.00),
    (0.82, 1.47, 0.80, 0.34, 0.95, 1.00),
    (1.02, 1.45, 0.90, 0.30, 0.95, 1.00),
    (1.18, 1.40, 1.01, 0.22, 1.00, 1.00),
    (1.28, 1.33, 1.06, 0.14, 1.00, 1.00),
    (1.335, 1.26, 1.10, 0.05, 1.00, 1.00),
])

# short-haired body (the part under the cape never shows)
bm = bmesh.new()
NB = 22
ys = [-1.04 + (1.335 + 1.04) * i / 27 for i in range(28)]
loft(bm, [[BODY.at(y, 2 * math.pi * i / NB) for i in range(NB)] for y in ys])
lumps(bm, 0.010, 7.0, 1.0)
P('buf_body', bm, M['bis_rear'], A, smooth=70)

# the cape: long woolly hair over hump, shoulders and brisket, ending in a
# ragged backward-pointing fringe that stands proud of the short coat
NC = 32


def cape_rim(i):
    a = 2 * math.pi * i / NC
    jag = (0.055 if i % 2 else -0.012) * (0.55 + 0.9 * hsh(i, 3.1))
    if min(i, NC - i) <= 2:             # no flap standing up off the topline
        jag = min(jag, 0.0)
    return -0.07 + 0.16 * math.cos(a) + jag


rings = []
for t in (0.0, 0.06, 0.13, 0.21, 0.30, 0.39, 0.48, 0.57, 0.66, 0.74, 0.82, 0.89, 0.95, 1.0):
    ring = []
    for i in range(NC):
        a = 2 * math.pi * i / NC
        y = -1.02 + (cape_rim(i) + 1.02) * t
        ca = math.cos(a)
        g = 0.07 + 0.025 * max(0.0, ca) + 0.10 * max(0.0, -ca) ** 2
        e = min(1.0, t / 0.35)                  # grows out from under the neck shield
        g = -0.03 + (g + 0.03) * e * e * (3 - 2 * e)
        k = max(0.0, (t - 0.75) / 0.25)         # thins to ~1.5 cm at the rim
        g = g + (0.015 - g) * k * k * (3 - 2 * k)
        ring.append(BODY.at(y, a, grow=g))
    rings.append(ring)
rings.append([BODY.at(cape_rim(i) - 0.02, 2 * math.pi * i / NC, grow=0.002) for i in range(NC)])
bm = bmesh.new()
vr, _ = loft(bm, rings)
rim = set(vr[-1]) | set(vr[-2])
fade = {v: 1.0 for v in bm.verts}
for j, ring in enumerate(vr):           # no lumps where it thins toward the rim
    for v in ring:
        fade[v] = min(1.0, max(0.0, (len(vr) - 3 - j) / 3.0))
lumps(bm, 0.030, 3.6, 2.0, (1, 1, 0.55), mask=None, verts=[v for v in bm.verts if fade[v] > 0.99])
lumps(bm, 0.014, 11.0, 3.0, verts=[v for v in bm.verts if fade[v] > 0.3])
# stop at the elbow over the forelegs so the dark chaps show; brisket still hangs
arm = [v for v in bm.verts if abs(v.co.x) > 0.18 and v.co.y < -0.25]
for v in arm:
    if v.co.z < 0.95:
        v.co.z = 0.95 - (0.95 - v.co.z) * 0.12
drip(bm, 0.11, nz=-0.45, verts=[v for v in bm.verts if v.co.y < 0.0 and v not in set(arm)], seed=1.0)
P('buf_cape', bm, M['bis_cape'], A, smooth=75, prio=1.05)

# --- head + neck (one child node, pivot at the base of the neck)
NECK = Prof([
    (-0.75, 1.64, 0.78, 0.31, 0.60, 0.80),
    (-0.86, 1.72, 0.72, 0.35, 0.55, 0.75),
    (-1.00, 1.63, 0.70, 0.33, 0.62, 0.75),
    (-1.14, 1.50, 0.76, 0.28, 0.70, 0.80),
    (-1.24, 1.42, 0.90, 0.22, 0.80, 0.85),
    (-1.32, 1.36, 1.02, 0.11, 0.90, 0.90),
])
bm = bmesh.new()
ys = [-0.75 - 0.57 * i / 10 for i in range(11)]
loft(bm, [[NECK.at(y, 2 * math.pi * i / 26) for i in range(26)] for y in ys])
lumps(bm, 0.030, 3.4, 4.0, (1, 1, 0.55))
lumps(bm, 0.010, 10.0, 5.0)
drip(bm, 0.10, nz=-0.45, seed=2.0)
P('buf_neck', bm, M['bis_cape'], A, sub='Head', smooth=75, prio=1.05)

# the head hangs low, the forehead nearly in line with the slope of the hump
HP0, HP1 = (0.0, -1.28, 1.27), (0.0, -1.60, 0.84)


def hp(t, x=0.0, n=0.0):
    """A point on the head frame: t along the face, x sideways, n off the forehead."""
    return Vector(HP0).lerp(Vector(HP1), t) + Vector((x, 0, 0)) + HN * n


# lower face: short dark hair, then a broad, square, glossy black muzzle
face, HD, HN = axial(HP0, HP1, [
    (0.28, 0.200, 0.150), (0.42, 0.188, 0.142), (0.58, 0.160, 0.128),
    (0.72, 0.145, 0.116), (0.84, 0.148, 0.108), (0.93, 0.146, 0.102),
    (0.975, 0.134, 0.092)], 18, 2.4)
bm = bmesh.new()
loft(bm, face)
P('buf_face', bm, M['bis_face'], A, sub='Head', smooth=70, prio=1.1)
muz, _, _ = axial(HP0, HP1, [
    (0.955, 0.138, 0.095), (0.99, 0.128, 0.087), (1.02, 0.104, 0.070), (1.04, 0.060, 0.040)], 18, 2.4)
bm = bmesh.new()
loft(bm, muz)
P('buf_muzzle', bm, M['bis_nose'], A, sub='Head', smooth=70, prio=0.9)
bm = bmesh.new()   # nostrils
for sx in (1, -1):
    blob(bm, hp(1.025, sx * 0.052, 0.010), (0.024, 0.016, 0.030))
P('buf_nostril', bm, M['eye'], A, sub='Head', smooth=50, prio=0.3)
bm = bmesh.new()   # eyes, just under the hem of the mop
for sx in (1, -1):
    blob(bm, hp(0.55, sx * 0.168, 0.044), (0.024, 0.022, 0.020), 2)
P('buf_eye', bm, M['bis_eye'], A, sub='Head', smooth=60, prio=0.5)

# the mop: a thick curly mass over poll, forehead and cheeks that swallows the
# horn bases and hangs down over the eyes
mop, _, _ = axial(HP0, HP1, [
    (-0.24, 0.16, 0.16, -0.04), (-0.14, 0.25, 0.23, -0.01), (-0.02, 0.30, 0.27, 0.03),
    (0.12, 0.32, 0.30, 0.06),
    (0.28, 0.31, 0.26, 0.05), (0.44, 0.27, 0.22, 0.035), (0.58, 0.225, 0.175, 0.02),
    (0.68, 0.185, 0.145, 0.008), (0.74, 0.150, 0.124, 0.0)], 24, 2.0)
bm = bmesh.new()
vr, _ = loft(bm, mop)
hem = set(vr[-1])
lumps(bm, 0.034, 6.0, 6.0, (1, 1, 0.7), verts=[v for v in bm.verts if v not in hem])
lumps(bm, 0.012, 18.0, 7.0, verts=[v for v in bm.verts if v not in hem])
for i, v in enumerate(vr[-2]):          # ragged fringe over the eyes
    v.co += HD * (0.035 * hsh(i, 5.5))
P('buf_mop', bm, M['bis_dark'], A, sub='Head', smooth=80, prio=1.1)

bm = bmesh.new()   # beard and throat mane, hanging below the jaw
body(bm, [
    (-1.49, 0.90, 0.70, 0.050, 0.9, 0.5),
    (-1.41, 0.94, 0.57, 0.085, 0.9, 0.45),
    (-1.31, 0.99, 0.53, 0.100, 0.9, 0.45),
    (-1.20, 1.02, 0.55, 0.120, 0.9, 0.5),
    (-1.06, 1.08, 0.60, 0.150, 0.9, 0.55),
    (-0.92, 1.12, 0.64, 0.180, 0.9, 0.6),
], 16)
lumps(bm, 0.020, 6.0, 8.0, (1, 1, 0.4))
drip(bm, 0.10, nz=-0.3, seed=4.0)
P('buf_beard', bm, M['bis_dark'], A, sub='Beard', smooth=80, prio=0.9)
PIVOTS[(A, 'Beard')] = (0.0, -1.30, 0.98)
PARENT[(A, 'Beard')] = 'Head'

bm = bmesh.new()   # small ears low under the horns, poking out of the hair
for sx in (1, -1):
    ear(bm, hp(0.14, sx * 0.24, -0.06), hp(0.20, sx * 0.37, -0.13), 0.045, 0.012, 7)
P('buf_ear', bm, M['bis_dark'], A, sub='Head', smooth=50, prio=0.6)
PIVOTS[(A, 'Head')] = BUF_NECK

# horns: a bull's short thick hooks, sideways then up; a cow's slender ones,
# more curved and turning in at the tips.  Half buried in the mop.  Two child
# nodes, code shows one.
for tag, pts, rad in (
        ('HornBull', [(0.14, -1.33, 1.285), (0.25, -1.345, 1.295), (0.315, -1.35, 1.325),
                      (0.345, -1.345, 1.385), (0.335, -1.33, 1.445), (0.305, -1.32, 1.48)],
         [0.060, 0.056, 0.047, 0.035, 0.023, 0.012]),
        ('HornCow', [(0.14, -1.33, 1.285), (0.23, -1.34, 1.30), (0.285, -1.35, 1.35),
                     (0.292, -1.345, 1.42), (0.262, -1.33, 1.475), (0.215, -1.325, 1.495)],
         [0.040, 0.036, 0.028, 0.020, 0.013, 0.006])):
    bm = bmesh.new()
    for sx in (1, -1):
        tube(bm, [(sx * p[0], p[1], p[2]) for p in pts], rad, 8, 2)
    P('buf_%s' % tag, bm, M['bis_horn'], A, sub=tag, smooth=50, prio=0.7)
    PIVOTS[(A, tag)] = BUF_NECK
    PARENT[(A, tag)] = 'Head'

# --- legs: short and slim for the mass, the forelegs in shaggy chaps
for tag, (py, pz, px, fore) in (('LegFL', (-0.50, 1.05, 0.24, 1)),
                                ('LegFR', (-0.50, 1.05, -0.24, 1)),
                                ('LegRL', (0.80, 1.12, 0.22, 0)),
                                ('LegRR', (0.80, 1.12, -0.22, 0))):
    bm = bmesh.new()
    if fore:
        pts = [(px * 0.70, py + 0.02, pz + 0.05), (px * 0.95, py + 0.06, 0.78),
               (px * 0.93, py + 0.03, 0.60), (px * 0.92, py + 0.01, 0.42),
               (px * 0.92, py + 0.01, 0.25), (px * 0.92, py + 0.02, 0.14),
               (px * 0.92, py, 0.09)]
        rad = [0.150, 0.120, 0.086, 0.070, 0.050, 0.056, 0.050]
    else:
        pts = [(px * 0.75, py, pz + 0.06), (px * 1.0, py - 0.10, 0.88),
               (px * 0.95, py + 0.06, 0.62), (px * 0.93, py + 0.13, 0.44),
               (px * 0.92, py + 0.08, 0.25), (px * 0.92, py + 0.05, 0.14),
               (px * 0.92, py + 0.03, 0.09)]
        rad = [0.200, 0.170, 0.100, 0.068, 0.048, 0.052, 0.047]
    limb(bm, pts, rad, 10)
    lumps(bm, 0.006, 12.0, 9.0)
    P('buf_%s' % tag, bm, M['bis_rear'] if not fore else M['bis_dark'], A, sub=tag,
      smooth=70, prio=0.85)
    if fore:   # chaps: long hair from the elbow to the knee, ragged at the hem
        bm = bmesh.new()
        zs = [1.02, 0.94, 0.86, 0.78, 0.70, 0.62, 0.54, 0.47, 0.42]
        limb(bm, [(px * (0.97 - 0.03 * (1.02 - z)), py + 0.04, z) for z in zs],
             [0.17 - 0.07 * (1.02 - z) for z in zs], 18)
        lumps(bm, 0.020, 9.0, 10.0 + px, (1, 1, 0.35))
        drip(bm, 0.10, nz=-0.2, seed=5.0 + px)
        P('buf_%s_chaps' % tag, bm, M['bis_dark'], A, sub=tag, smooth=80, prio=0.85)
    bm = bmesh.new()
    hoof2(bm, (pts[-1][0], pts[-1][1] - 0.01), 0.125, 0.13, 0.095)
    P('buf_%s_hoof' % tag, bm, M['bis_hoof'], A, sub=tag, smooth=45, prio=0.45)
    PIVOTS[(A, tag)] = (px, py, pz)

# --- tail: a thin short-haired rope ending in a black tuft
bm = bmesh.new()
limb(bm, [(0, 1.27, 1.34), (0, 1.335, 1.26), (0, 1.36, 1.12), (0, 1.355, 0.98),
          (0, 1.35, 0.90)], [0.040, 0.034, 0.028, 0.024, 0.022], 8)
P('buf_tail', bm, M['bis_rear'], A, sub='Tail', smooth=70, prio=0.6)
bm = bmesh.new()
blob(bm, (0.0, 1.352, 0.84), (0.050, 0.046, 0.12), 2)
lumps(bm, 0.018, 18.0, 11.0, (1, 1, 0.3))
drip(bm, 0.08, nz=-0.2, seed=6.0)
P('buf_tuft', bm, M['bis_dark'], A, sub='Tail', smooth=80, prio=0.6)
PIVOTS[(A, 'Tail')] = (0.0, 1.27, 1.34)

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
# HAWK — red-tailed hawk, western light morph: 1.25 m span, 0.55 m long,
# soaring.  Broad rounded wings with five separated finger primaries, a short
# broad fanned tail.  Origin at the body centre (it is never on the ground),
# head at -Y so it flies the way it faces.  Wings built flat.
# ============================================================================
log('hawk')
A = 'Hawk'
HAWK_SPAN = 0.625

bm = bmesh.new()   # body: head, breast, belly, vent
HAWK_BODY = [
    (-0.197, 0.026, 0.000, 0.012),
    (-0.188, 0.036, -0.010, 0.022),
    (-0.172, 0.046, -0.018, 0.031),
    (-0.150, 0.050, -0.024, 0.036),
    (-0.128, 0.050, -0.030, 0.038),
    (-0.105, 0.048, -0.040, 0.043),
    (-0.075, 0.050, -0.052, 0.055),
    (-0.035, 0.050, -0.060, 0.062),
    (0.005, 0.047, -0.060, 0.062),
    (0.045, 0.042, -0.054, 0.055),
    (0.085, 0.034, -0.044, 0.045),
    (0.120, 0.025, -0.032, 0.033),
    (0.150, 0.017, -0.020, 0.023),
    (0.175, 0.011, -0.011, 0.014),
]
body(bm, [(y, zt, zb, hw * (1.0 if y < -0.12 else 1.15)) for (y, zt, zb, hw) in HAWK_BODY], 14)
for sx in (1, -1):   # brow ridge that gives a hawk its frown; feathered trousers
    blob(bm, (sx * 0.024, -0.162, 0.040), (0.013, 0.020, 0.007))
    blob(bm, (sx * 0.021, 0.062, -0.046), (0.017, 0.032, 0.014))
lumps(bm, 0.0025, 90.0, 12.0)
P('hawk_body', bm, M['rt_body'], A, smooth=70, prio=2.4)

bm = bmesh.new()   # hooked bill, dark grey, bluish at the base
tube(bm, [(0, -0.189, 0.017), (0, -0.203, 0.019), (0, -0.213, 0.014), (0, -0.218, 0.004),
          (0, -0.2155, -0.005)], [0.0100, 0.0085, 0.0064, 0.0040, 0.0012], 8, 2, aspect=1.3)
tube(bm, [(0, -0.190, 0.004), (0, -0.203, 0.006), (0, -0.2105, 0.0075)],
     [0.0080, 0.0055, 0.0018], 6, 2, aspect=0.8)
P('hawk_beak', bm, M['rt_beak'], A, smooth=50, prio=1.4)
bm = bmesh.new()   # yellow cere over the bill base
blob(bm, (0, -0.1935, 0.0185), (0.0125, 0.009, 0.0115), 2)
P('hawk_cere', bm, M['rt_cere'], A, smooth=50, prio=1.0)
bm = bmesh.new()   # dark brown adult eye
for sx in (1, -1):
    blob(bm, (sx * 0.0295, -0.163, 0.0285), (0.0085, 0.008, 0.0085), 2)
P('hawk_eye', bm, M['rt_eye'], A, smooth=60, prio=1.0)

bm = bmesh.new()   # yellow feet drawn up under the belly, black talons
bmt = bmesh.new()
for sx in (1, -1):
    c = Vector((sx * 0.019, 0.086, -0.050))
    for dx, ln in ((-0.006, 0.020), (0.0, 0.024), (0.006, 0.019)):
        t1 = c + Vector((sx * dx, -ln * 0.6, -0.003))
        t2 = c + Vector((sx * dx * 1.5, -ln, -0.011))
        limb(bm, [c, t1, t2], [0.0048, 0.0042, 0.0036], 5)
        limb(bmt, [t2, t2 + Vector((0, -0.003, -0.007))], [0.0030, 0.0006], 4)
    t2 = c + Vector((0, 0.013, -0.007))
    limb(bm, [c, t2], [0.0048, 0.0038], 5)
    limb(bmt, [t2, t2 + Vector((0, 0.002, -0.007))], [0.0030, 0.0006], 4)
P('hawk_feet', bm, M['rt_foot'], A, smooth=60, prio=1.0)
P('hawk_talons', bmt, M['claw'], A, smooth=40, prio=0.5)

bm = bmesh.new()   # brick-red tail: twelve rectrices fanned, scalloped tips
fan(bm, (0.0, 0.06, 0.0), 0.085, 0.288, 0.50, 12, 0.006, 0.005, z=-0.002)
P('hawk_tail', bm, M['rt_tail'], A, smooth=60, prio=2.4)

HAWK_PLAN = [(0.030, -0.080, 0.140), (0.08, -0.090, 0.172), (0.14, -0.098, 0.198),
             (0.20, -0.103, 0.205), (0.26, -0.106, 0.196), (0.31, -0.104, 0.172),
             (0.36, -0.094, 0.146), (0.40, -0.082, 0.122), (0.44, -0.068, 0.080)]
HAWK_FINGERS = [   # p10 .. p6: base (inside the hand), tip, width — fanned
    ((0.370, -0.078), (0.552, -0.078), 0.040),
    ((0.372, -0.052), (0.602, -0.036), 0.044),
    ((0.372, -0.024), (0.625, 0.012), 0.046),
    ((0.370, 0.004), (0.614, 0.060), 0.046),
    ((0.366, 0.032), (0.584, 0.104), 0.044),
]
for tag, sx in (('WingL', 1), ('WingR', -1)):
    bm = bmesh.new()
    wing(bm, sx, HAWK_PLAN, [0.028] * 10 + [0.026] * 5,
         lambda x: max(0.009, 0.030 - 0.043 * (x - 0.03)),
         lambda x: 0.010 - 0.010 * (x - 0.03), HAWK_SPAN, 0.006, z0=0.008)
    for k, ((bx, by), (tx, ty), wb) in enumerate(HAWK_FINGERS):
        zz = 0.008 + 0.0016 * (k - 2)
        blade(bm, (sx * bx, by, zz), (sx * tx, ty, zz), wb, 0.004, 0.70, 1.0, curl=0.020, lead=0.32)
    P('hawk_%s' % tag, bm, M['rt_wing'], A, sub=tag, smooth=70, prio=2.4)
    PIVOTS[(A, tag)] = (sx * 0.035, -0.050, 0.012)

# ============================================================================
# VULTURE — turkey vulture: 1.75 m span, 0.72 m long.  Long wings with six
# fingers, a long rounded tail past the feet, a tiny bare red head with an
# ivory bill.  Built in flight attitude; origin on the ground under the feet
# (see the docstring for the perched pitch).
# ============================================================================
log('vulture')
A = 'Vulture'
TV_SPAN = 0.875
TV_NECK = (0.0, -0.312, 0.318)
TV_DROP = 0.07      # the body sits this much lower than it is written below

bm = bmesh.new()   # body with the feathered ruff the bare neck sinks into
body(bm, [
    (-0.318, 0.345, 0.285, 0.030),
    (-0.298, 0.374, 0.256, 0.060),
    (-0.270, 0.387, 0.230, 0.074),
    (-0.230, 0.389, 0.212, 0.081),
    (-0.180, 0.387, 0.202, 0.085),
    (-0.120, 0.381, 0.205, 0.083),
    (-0.060, 0.371, 0.220, 0.075),
    (-0.010, 0.359, 0.240, 0.061),
    (0.025, 0.349, 0.262, 0.047),
    (0.050, 0.339, 0.282, 0.033),
    (0.065, 0.331, 0.298, 0.019),
], 16)
lumps(bm, 0.009, 38.0, 13.0, mask=lambda co: 1.0 if co.y < -0.24 else 0.0)
lumps(bm, 0.003, 60.0, 14.0)
P('tv_body', bm, M['tv_body'], A, smooth=70, prio=1.6)

bm = bmesh.new()   # long rounded tail, silvery below
fan(bm, (0.0, -0.25, 0.316), 0.28, 0.512, 0.17, 12, 0.007, 0.007)
P('tv_tail', bm, M['tv_tail'], A, smooth=60, prio=1.8)

# --- head node: bare wrinkled neck and head, ivory bill (pivot at the neck base)
bm = bmesh.new()
body(bm, [
    (-0.441, 0.330, 0.307, 0.010),
    (-0.428, 0.340, 0.298, 0.017),
    (-0.410, 0.347, 0.293, 0.022),
    (-0.390, 0.350, 0.292, 0.024),
    (-0.370, 0.347, 0.292, 0.022),
    (-0.350, 0.340, 0.290, 0.019),
    (-0.325, 0.338, 0.286, 0.020),
    (-0.290, 0.342, 0.280, 0.026),
], 12)
lumps(bm, 0.0015, 160.0, 15.0)
P('tv_head', bm, M['tv_head'], A, sub='Head', smooth=70, prio=3.0)
bm = bmesh.new()
tube(bm, [(0, -0.433, 0.321), (0, -0.448, 0.323), (0, -0.460, 0.319), (0, -0.467, 0.309),
          (0, -0.4655, 0.300)], [0.0085, 0.0072, 0.0058, 0.0038, 0.0014], 8, 2, aspect=1.35)
tube(bm, [(0, -0.433, 0.307), (0, -0.447, 0.309), (0, -0.455, 0.310)],
     [0.0070, 0.0052, 0.0020], 6, 2, aspect=0.8)
P('tv_bill', bm, M['tv_bill'], A, sub='Head', smooth=50, prio=1.6)
bm = bmesh.new()   # perforate nostril slot + brown eyes
for sx in (1, -1):
    blob(bm, (sx * 0.0062, -0.443, 0.3255), (0.0026, 0.0072, 0.0032))
P('tv_nostril', bm, M['eye'], A, sub='Head', smooth=50, prio=0.4)
bm = bmesh.new()
for sx in (1, -1):
    blob(bm, (sx * 0.0215, -0.405, 0.3315), (0.0056, 0.0056, 0.0056), 2)
P('tv_eye', bm, M['tv_eye'], A, sub='Head', smooth=60, prio=0.6)
PIVOTS[(A, 'Head')] = TV_NECK

# --- spread wings: two-tone below, six fingers
TV_PLAN = [(0.050, -0.300, -0.005), (0.12, -0.312, 0.000), (0.22, -0.318, -0.004),
           (0.32, -0.320, -0.008), (0.40, -0.320, -0.012), (0.46, -0.316, -0.020),
           (0.51, -0.308, -0.040), (0.55, -0.298, -0.075)]
TV_FINGERS = [   # p10 .. p5: base (inside the hand), tip, width — fanned
    ((0.480, -0.296), (0.795, -0.304), 0.056),
    ((0.482, -0.258), (0.860, -0.262), 0.058),
    ((0.484, -0.220), (0.875, -0.208), 0.060),
    ((0.484, -0.182), (0.866, -0.154), 0.060),
    ((0.482, -0.144), (0.836, -0.100), 0.058),
    ((0.478, -0.106), (0.790, -0.050), 0.056),
]
for tag, sx in (('WingL', 1), ('WingR', -1)):
    bm = bmesh.new()
    wing(bm, sx, TV_PLAN, [0.0373] * 11 + [0.023] * 4,
         lambda x: max(0.012, 0.036 - 0.040 * (x - 0.05)),
         lambda x: 0.012 - 0.010 * (x - 0.05), TV_SPAN, 0.008, z0=0.335)
    for k, ((bx, by), (tx, ty), wb) in enumerate(TV_FINGERS):
        zz = 0.335 + 0.0018 * (k - 2.5)
        blade(bm, (sx * bx, by, zz), (sx * tx, ty, zz), wb, 0.005, 0.66, 1.0, curl=0.022, lead=0.30,
              widths=(1.0, 0.92, 0.70, 0.58, 0.42, 0.14), ss=(0.0, 0.26, 0.46, 0.74, 0.92, 1.0))
    P('tv_%s' % tag, bm, M['tv_wing'], A, sub=tag, smooth=70, prio=1.6)
    PIVOTS[(A, tag)] = (sx * 0.060, -0.290, 0.340)

# --- folded wings (perched): brown pale-fringed coverts over the shoulder,
#     long blackish flight feathers, tips crossed over the tail
FOLD = [   # u, x, h, thick
    (0.0, 0.058, 0.030, 0.018), (0.08, 0.080, 0.090, 0.030), (0.22, 0.090, 0.112, 0.036),
    (0.40, 0.086, 0.104, 0.030), (0.58, 0.070, 0.082, 0.020), (0.74, 0.052, 0.058, 0.012),
    (0.88, 0.036, 0.034, 0.007), (1.0, 0.024, 0.010, 0.003)]
bm = bmesh.new()
for sx in (1, -1):
    rings, prm = [], []
    for (u, x, h, t) in FOLD:
        y = -0.275 + 0.505 * u
        top = 0.391 - 0.040 * u - 0.012 * u * u
        top_p = Vector((sx * x, y, top))
        bot_p = Vector((sx * (x + 0.012), y, top - h))
        mid = (top_p + bot_p) * 0.5
        along = (top_p - bot_p)
        out = Vector((sx, 0, 0))
        ring, pr = [], []
        for i in range(10):
            a = 2 * math.pi * i / 10
            ca, sa = math.cos(a), math.sin(a)
            bulge = t * 0.5 * sa * sx * (1.0 if sa > 0 else 0.4)    # convex outside, flat against the body
            ring.append(mid + along * (0.5 * ca) + out * bulge)
            pr.append((u, 0.5 - 0.5 * ca))
        rings.append(ring)
        prm.append(pr)
    loft(bm, rings, prm)
lumps(bm, 0.003, 50.0, 16.0)
P('tv_fold', bm, M['tv_fold'], A, sub='Folded', smooth=70, prio=1.4)
PIVOTS[(A, 'Folded')] = (0.0, -0.14, 0.30)

# --- legs (perched): built standing in the perched frame, then turned into the
#     flight frame so that code's PERCH pitch stands them up again
bm, bmt, bmc = bmesh.new(), bmesh.new(), bmesh.new()
for sx in (1, -1):
    x = sx * 0.042
    limb(bmt, [(x * 1.1, -0.010, 0.185), (x * 1.05, 0.0, 0.130), (x, 0.018, 0.088)],
         [0.030, 0.024, 0.012], 8)                                  # feathered tibia
    limb(bm, [(x, 0.018, 0.090), (x, 0.012, 0.050), (x, 0.004, 0.013)],
         [0.0090, 0.0080, 0.0085], 7)                               # bare tarsus
    for ang, ln in ((-0.38, 0.052), (0.0, 0.064), (0.38, 0.050)):
        d = Vector((math.sin(ang) * sx, -math.cos(ang), 0.0))
        c0 = Vector((x, 0.0, 0.008))
        c1 = c0 + d * (ln * 0.5) + Vector((0, 0, 0.002))
        c2 = c0 + d * ln + Vector((0, 0, -0.002))
        limb(bm, [c0, c1, c2], [0.0060, 0.0050, 0.0040], 6)
        limb(bmc, [c2, c2 + d * 0.010 + Vector((0, 0, -0.004))], [0.0034, 0.0010], 4)
    c0 = Vector((x, 0.004, 0.008))
    limb(bm, [c0, c0 + Vector((0, 0.026, -0.003))], [0.0055, 0.0040], 6)
for b in (bm, bmt, bmc):
    rot_bm(b, PERCH, 'X')
P('tv_legs', bm, M['tv_leg'], A, sub='Legs', smooth=60, prio=1.0)
P('tv_thigh', bmt, M['tv_body'], A, sub='Legs', smooth=60, prio=0.8)
P('tv_claws', bmc, M['claw'], A, sub='Legs', smooth=40, prio=0.4)
PIVOTS[(A, 'Legs')] = tuple(Matrix.Rotation(PERCH, 3, 'X') @ Vector((0.0, 0.0, 0.15)))
TV_BACK = 0.025                       # the head sits this much further into the ruff
for o in PARTS:                       # lower everything but the legs onto them
    if o['animal'] == A and o['sub'] != 'Legs':
        o.data.transform(Matrix.Translation((0, TV_BACK if o['sub'] == 'Head' else 0.0, -TV_DROP)))
for k in list(PIVOTS):
    if k[0] == A and k[1] != 'Legs':
        PIVOTS[k] = (PIVOTS[k][0], PIVOTS[k][1], PIVOTS[k][2] - TV_DROP)

# ============================================================================
# CARCASS — a dead horse beside the stage road, weeks old.  Lies on its right
# side, legs stiff and out; the dry dust-caked hide shrunk tight over the ribs;
# the upper flank opened by scavengers onto curved ivory ribs and a dark, dry
# cavity; the front of the face gone to bare skull.  Scattered bones and hair.
# Lying frame: spine toward -X, legs toward +X, left flank up.
# ============================================================================
log('carcass')
A = 'Carcass'
CS = [   # (y, x_spine, x_belly, z_top)
    (-1.06, -0.20, 0.03, 0.24),
    (-0.86, -0.27, 0.08, 0.29),
    (-0.66, -0.37, 0.20, 0.37),
    (-0.46, -0.42, 0.31, 0.45),
    (-0.22, -0.43, 0.36, 0.49),
    (0.04, -0.42, 0.36, 0.49),
    (0.30, -0.41, 0.33, 0.46),
    (0.52, -0.41, 0.30, 0.48),
    (0.72, -0.39, 0.25, 0.45),
    (0.87, -0.31, 0.15, 0.38),
    (0.96, -0.19, 0.05, 0.28),
    (1.00, -0.08, -0.02, 0.17),
]
CPROF = Prof([(s[0], s[1], s[2], s[3], 0.0) for s in CS])   # reuse the Catmull fit


def gauss(v, c, w):
    return math.exp(-((v - c) / w) ** 2)


def carc_at(y, a, grow=0.0, detail=True):
    xs, xb, zt, _, _ = CPROF.par(y)
    xc, hx = (xs + xb) / 2, (xb - xs) / 2
    hz = zt / 2
    sa, ca = math.sin(a), math.cos(a)
    cz = ca if ca > 0 else -(abs(ca) ** 0.6)           # flattened where it lies
    p = Vector((xc + hx * sa, y, hz + hz * cz))
    n = Vector((sa / hx, 0.0, ca / hz)).normalized()
    d = grow
    if detail:
        up = max(0.0, ca)
        if -0.46 < y < 0.26:                            # hide drawn tight over the ribs
            d -= 0.011 * up * (0.5 - 0.5 * math.cos(2 * math.pi * (y + 0.46) / 0.084))
        d -= 0.045 * up * gauss(y, 0.37, 0.09)          # sunken flank
        d += 0.038 * up * gauss(y, 0.55, 0.07) * gauss(sa, -0.3, 0.4)    # point of the hip
        d += 0.022 * up * gauss(y, -0.50, 0.08) * gauss(sa, -0.45, 0.4)  # shoulder blade
        d += 0.012 * gauss(sa, -1.0, 0.25) * up                          # spine ridge
    return p + n * d


def carc_angle(co):
    xs, xb, zt, _, _ = CPROF.par(co.y)
    return math.atan2(co.x - (xs + xb) / 2, co.z - zt / 2)


HOLE = (-0.10, 0.27, 0.50, 0.60)    # y, y radius, angle, angle radius
bm = bmesh.new()
NH = 30
ys = [-1.06 + 2.06 * i / 33 for i in range(34)]
loft(bm, [[carc_at(y, 2 * math.pi * i / NH) for i in range(NH)] for y in ys])
lumps(bm, 0.006, 9.0, 17.0)


def hole_r(y, a):
    """Torn-edge radius of the opening at (y, angle), in hole units."""
    return 1.0 + 0.30 * NZ.noise(Vector((y * 7.0, a * 2.5, 3.3))) + 0.10 * NZ.noise(Vector((y * 30.0, a * 11.0, 1.7)))


kill = []
for f in bm.faces:
    c = f.calc_center_median()
    a = carc_angle(c)
    dy, da = (c.y - HOLE[0]) / HOLE[1], (a - HOLE[2]) / HOLE[3]
    if math.hypot(dy, da) < hole_r(c.y, a):
        kill.append(f)
bmesh.ops.delete(bm, geom=kill, context='FACES')
bnd = [e for e in bm.edges if len(e.link_faces) == 1]
for v in {v for e in bnd for v in e.verts}:     # snap the stair-stepped edge onto the tear
    a = carc_angle(v.co)
    dy, da = (v.co.y - HOLE[0]) / HOLE[1], (a - HOLE[2]) / HOLE[3]
    r = max(math.hypot(dy, da), 1e-3)
    for _ in range(3):
        k = hole_r(HOLE[0] + dy * HOLE[1], HOLE[2] + da * HOLE[3]) / r
        dy, da, r = dy * k, da * k, r * k
    v.co = carc_at(HOLE[0] + dy * HOLE[1], HOLE[2] + da * HOLE[3])
ret = bmesh.ops.extrude_edge_only(bm, edges=bnd)
for v in [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]:
    xs, xb, zt, _, _ = CPROF.par(v.co.y)
    ax = Vector(((xs + xb) / 2, v.co.y, zt / 2))
    v.co += (ax - v.co).normalized() * 0.065
P('carc_hide', bm, M['carc_hide'], A, smooth=70, prio=1.0)

bm = bmesh.new()   # the cavity: an inward-facing shell under the opening
ys = [-0.48 + 0.77 * i / 11 for i in range(12)]
loft(bm, [[carc_at(y, 2 * math.pi * i / 20, grow=-0.075, detail=False) for i in range(20)]
          for y in ys])
bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
lumps(bm, 0.012, 14.0, 18.0)
P('carc_cavity', bm, M['cavity'], A, smooth=60, prio=0.5)

bm = bmesh.new()   # ribs arching across the opening, sloping back; two broken
for k in range(7):
    y = -0.38 + 0.084 * k + 0.034 * (hsh(k, 2.0) - 0.5)
    a0, a1 = -0.45, (0.55 if k == 2 else 0.85 if k == 5 else 1.35)
    pts = []
    for j in range(8):
        f = j / 7
        a = a0 + (a1 - a0) * f
        p = carc_at(y + 0.05 * f, a, grow=-0.018 - 0.01 * math.sin(f * math.pi), detail=False)
        pts.append(p)
    tube(bm, pts, [0.009, 0.010, 0.0105, 0.0105, 0.010, 0.0095, 0.009, 0.007 if a1 < 1 else 0.008],
         6, 1, aspect=1.9, up=(0, 1, 0))
P('carc_ribs', bm, M['bone'], A, smooth=50, prio=0.9)

# --- head: hide over the jowl, bare skull in front
HEAD_HIDE = [(-0.99, -0.08, 0.17, 0.12, 0.12), (-1.08, -0.07, 0.19, 0.115, 0.115),
             (-1.16, -0.07, 0.18, 0.11, 0.106), (-1.24, -0.075, 0.15, 0.10, 0.096)]
SKULL = [(-1.13, -0.07, 0.17, 0.11, 0.100), (-1.22, -0.08, 0.155, 0.108, 0.098),
         (-1.32, -0.08, 0.130, 0.098, 0.080), (-1.42, -0.078, 0.112, 0.088, 0.068),
         (-1.52, -0.075, 0.096, 0.078, 0.058), (-1.60, -0.072, 0.078, 0.068, 0.050),
         (-1.645, -0.072, 0.040, 0.065, 0.026)]


def ellrings(secs, n):
    return [[(xc + hx * math.sin(2 * math.pi * i / n), y, zc + hz * math.cos(2 * math.pi * i / n))
             for i in range(n)] for (y, xc, hx, zc, hz) in secs]


bm = bmesh.new()
vr, _ = loft(bm, ellrings(HEAD_HIDE, 16))
for i, v in enumerate(vr[-1]):          # ragged front edge of the hide
    v.co.y += 0.045 * (hsh(i, 9.0) - 0.3)
# dried ears at the poll
ear(bm, (-0.21, -0.985, 0.15), (-0.37, -0.935, 0.11), 0.040, 0.010, 6)
ear(bm, (-0.20, -0.995, 0.05), (-0.34, -0.955, 0.02), 0.040, 0.010, 6)
P('carc_head', bm, M['carc_hide'], A, smooth=60, prio=0.9)
bm = bmesh.new()
loft(bm, ellrings(SKULL, 14))
for i in range(5):                      # incisors
    blob(bm, (-0.035, -1.648, 0.030 + 0.018 * i), (0.012, 0.009, 0.008))
for i in range(5):                      # cheek teeth showing along the jaw
    blob(bm, (-0.020, -1.30 - 0.036 * i, 0.155 - 0.012 * i), (0.012, 0.016, 0.008))
P('carc_skull', bm, M['skull'], A, smooth=55, prio=0.9)
bm = bmesh.new()   # tongues of dried hide lapping onto the bone
for (x, y, z, sx, sy, rz) in ((-0.13, -1.285, 0.19, 0.045, 0.075, 0.3), (-0.19, -1.30, 0.10, 0.03, 0.09, -0.2),
                              (-0.06, -1.27, 0.205, 0.035, 0.06, -0.5)):
    vs = blob(bm, (0, 0, 0), (sx, sy, 0.012), 2)
    for v in vs:
        v.co = Matrix.Rotation(rz, 3, 'Z') @ v.co + Vector((x, y, z))
lumps(bm, 0.004, 40.0, 21.0)
P('carc_tongue', bm, M['carc_hide'], A, smooth=60, prio=0.5)
bm = bmesh.new()   # dark orbit and nasal notch
blob(bm, (-0.150, -1.215, 0.196), (0.050, 0.052, 0.030), 2)
blob(bm, (-0.020, -1.47, 0.158), (0.016, 0.10, 0.010), 1)
blob(bm, (-0.090, -1.465, 0.140), (0.020, 0.060, 0.012), 1)
P('carc_orbit', bm, M['cavity'], A, smooth=60, prio=0.4)

# --- legs, stiff and out; the upper pair held clear of the ground
LEGS = [
    ([(0.10, -0.45, 0.33), (0.35, -0.52, 0.33), (0.62, -0.62, 0.30), (0.90, -0.69, 0.27),
      (0.99, -0.71, 0.26)], [0.11, 0.085, 0.056, 0.045, 0.050]),
    ([(0.10, -0.40, 0.15), (0.34, -0.45, 0.10), (0.60, -0.50, 0.08), (0.88, -0.54, 0.07),
      (0.97, -0.55, 0.07)], [0.11, 0.085, 0.056, 0.045, 0.050]),
    ([(0.10, 0.55, 0.34), (0.36, 0.52, 0.34), (0.55, 0.66, 0.31), (0.86, 0.78, 0.28),
      (0.95, 0.80, 0.27)], [0.13, 0.10, 0.060, 0.045, 0.050]),
    ([(0.10, 0.58, 0.15), (0.36, 0.60, 0.10), (0.55, 0.74, 0.08), (0.85, 0.88, 0.07),
      (0.94, 0.90, 0.07)], [0.13, 0.10, 0.060, 0.045, 0.050]),
]
bm, bmh = bmesh.new(), bmesh.new()
for pts, rad in LEGS:
    limb(bm, pts, rad, 9)
    a, b = Vector(pts[-2]), Vector(pts[-1])
    d = (b - a).normalized()
    limb(bmh, [b - d * 0.01, b + d * 0.05, b + d * 0.10], [0.050, 0.060, 0.064], 9)
lumps(bm, 0.005, 12.0, 19.0)
P('carc_legs', bm, M['carc_hide'], A, smooth=60, prio=0.8)
P('carc_hooves', bmh, M['carc_hoof'], A, smooth=45, prio=0.4)

# --- the last of the mane and tail, and scattered bones and hair
bm = bmesh.new()
for k in range(6):
    y = -0.95 + 0.065 * k
    vs = blob(bm, (-0.30 - 0.02 * hsh(k, 1), y, 0.08 + 0.02 * hsh(k, 2)),
              (0.08, 0.030, 0.028), 2)
limb(bm, [(-0.12, 0.95, 0.17), (-0.10, 1.05, 0.10), (-0.08, 1.12, 0.05)], [0.05, 0.04, 0.03], 8)
blob(bm, (-0.03, 1.31, 0.025), (0.075, 0.21, 0.022), 2)
rng = random.Random(4)
for k in range(6):                       # tufts of shed hair
    a = rng.uniform(0, 2 * math.pi)
    r = rng.uniform(1.05, 1.6)
    blob(bm, (0.25 + math.cos(a) * r * 0.8, math.sin(a) * r, 0.012),
         (rng.uniform(0.04, 0.07), rng.uniform(0.03, 0.06), 0.012), 1)
lumps(bm, 0.012, 30.0, 20.0, (1, 0.4, 1))
P('carc_hair', bm, M['carc_hair'], A, smooth=70, prio=0.6)

bm = bmesh.new()
tube(bm, [(1.00, 0.05, 0.012), (1.10, 0.18, 0.022), (1.14, 0.33, 0.018), (1.12, 0.46, 0.010)],
     [0.016, 0.015, 0.013, 0.009], 6, 2, aspect=0.5)
tube(bm, [(-0.62, 0.95, 0.010), (-0.75, 0.86, 0.020), (-0.86, 0.72, 0.016), (-0.90, 0.58, 0.010)],
     [0.016, 0.015, 0.013, 0.009], 6, 2, aspect=0.5)
limb(bm, [(-0.80, -0.60, 0.026), (-0.74, -0.66, 0.021), (-0.60, -0.80, 0.019),
          (-0.55, -0.85, 0.026)], [0.030, 0.020, 0.018, 0.028], 8)
blob(bm, (-0.81, -0.59, 0.03), (0.035, 0.03, 0.028), 1)
blob(bm, (-0.54, -0.86, 0.03), (0.032, 0.03, 0.026), 1)
blob(bm, (0.62, 1.22, 0.035), (0.05, 0.035, 0.034), 1)             # a vertebra
limb(bm, [(0.62, 1.22, 0.05), (0.60, 1.225, 0.115)], [0.013, 0.006], 5)
limb(bm, [(0.55, 1.22, 0.035), (0.69, 1.22, 0.035)], [0.011, 0.008], 5)
P('carc_bones', bm, M['bone'], A, smooth=50, prio=0.7)

# where the vultures go: a perch on the hip, three places to feed
EMPTIES += [
    (A, 'Carcass_Perch', tuple(carc_at(0.54, -0.25)), math.pi / 2),
    (A, 'Carcass_Feed1', tuple(carc_at(-0.12, -0.62)), math.pi / 2),
    (A, 'Carcass_Feed2', (0.44, -1.34, 0.0), math.atan2(-0.46, 0.0)),
    (A, 'Carcass_Feed3', (0.06, 1.20, 0.0), math.atan2(-0.10, 0.26)),
]

# ----------------------------------------------------------------------------
# lay the animals apart in X so ambient occlusion does not bleed between them
# ----------------------------------------------------------------------------
OFFS = {'Buffalo': 0.0, 'Bear': 3.4, 'Goat': 6.0, 'Hawk': 7.9, 'Vulture': 9.8, 'Carcass': 13.0}
for o in PARTS:
    o.location.x = OFFS[o['animal']]
bpy.context.view_layer.update()

tot = {}
for o in PARTS:
    tot[o['animal']] = tot.get(o['animal'], 0) + L.tri_count(o)
    log('  %-18s %5d  %s' % (o.name, L.tri_count(o), o['sub'] or '-'))
log('tris per animal', tot)

if GEOM:
    for a in ANIMALS:
        objs = [o for o in PARTS if o['animal'] == a]
        pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
        log('%-9s tris %5d  L %.3f m  W %.3f  H %.3f  (y %.3f..%.3f, z %.3f..%.3f)'
            % (a, sum(L.tri_count(o) for o in objs),
               max(p.y for p in pts) - min(p.y for p in pts),
               max(p.x for p in pts) - min(p.x for p in pts),
               max(p.z for p in pts) - min(p.z for p in pts),
               min(p.y for p in pts), max(p.y for p in pts),
               min(p.z for p in pts), max(p.z for p in pts)))
    if '--save' in ARGS:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'animals_geom.blend'))
    log('geometry only — stopping before bake')
    sys.exit(0)

# ----------------------------------------------------------------------------
# bake one shared atlas
# ----------------------------------------------------------------------------
def atlas(objs, margin, angle=60):
    """Like sch_lib.uv_atlas, but most parts arrive unwrapped (see loft/limb/
    blob): smart-project only the faces without bake UVs, then equalise texel
    density, weight by priority and pack.  Keeps the island count low."""
    import numpy as np
    sc = bpy.context.scene
    sc.tool_settings.use_uv_select_sync = True
    sc.tool_settings.mesh_select_mode = (False, False, True)
    for o in objs:
        me = o.data
        lay = L.ensure_bake_uv(o)
        uv = np.zeros(len(lay.data) * 2, np.float32)
        lay.data.foreach_get('uv', uv)
        uv = uv.reshape(-1, 2)
        vsel = np.zeros(len(me.vertices), bool)
        for p in me.polygons:
            u = uv[list(p.loop_indices)]
            a = 0.5 * abs(np.dot(u[:, 0], np.roll(u[:, 1], 1)) - np.dot(u[:, 1], np.roll(u[:, 0], 1)))
            p.select = bool(a < 1e-9)
            if p.select:
                vsel[list(p.vertices)] = True
        for v, s_ in zip(me.vertices, vsel):
            v.select = bool(s_)
        for e in me.edges:
            e.select = bool(vsel[e.vertices[0]] and vsel[e.vertices[1]])
    L.select_only(objs)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=0.002,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in objs:
        lay = o.data.uv_layers['BakeUV']
        a = np.zeros(len(lay.data) * 2, np.float32)
        lay.data.foreach_get('uv', a)
        lay.data.foreach_set('uv', a * o.get('prio', 1.0))
    L.select_only(objs)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin, shape_method='CONCAVE',
                            margin_method='FRACTION')
    bpy.ops.object.mode_set(mode='OBJECT')


atlas(PARTS, 0.004 if TEX >= 1024 else 0.010)
IMGS = {}
for kind in ('color', 'orm', 'normal'):
    img = L.new_image('anim_%s' % kind, TEX, non_color=(kind != 'color'))
    log('bake', kind)
    L.bake_pass(PARTS, img, kind)
    L.save_image(img, os.path.join(BUILD, 'animals_%s.png' % kind))
    IMGS[kind] = img
conv = []
for kind in IMGS:
    q = {'color': 88, 'orm': 82, 'normal': 86}[kind]
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
# join into root + animated child nodes (a sub may hang from another sub)
# ----------------------------------------------------------------------------
GROUPS = {}
for o in PARTS:
    GROUPS.setdefault(o['animal'], []).append(o)

for a in ANIMALS:
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
    nodes = {}
    for tag in sorted(subs, key=lambda t: ((a, t) in PARENT, t)):
        sob = L.join(subs[tag], '%s_%s' % (a, tag))
        for key in list(sob.keys()):
            del sob[key]
        bpy.context.view_layer.update()
        L.set_origin(sob, Vector(PIVOTS[(a, tag)]))
        L.parent_keep(sob, nodes[PARENT[(a, tag)]] if (a, tag) in PARENT else root)
        nodes[tag] = sob
        log('  node %-16s %5d tris  pivot (%.3f %.3f %.3f)'
            % (sob.name, L.tri_count(sob), *PIVOTS[(a, tag)]))
    for (an, name, loc, rz) in EMPTIES:
        if an == a:
            e = L.empty(name, loc, size=0.1)
            e.rotation_euler = (0.0, 0.0, rz)
            bpy.context.view_layer.update()
            L.parent_keep(e, root)
    bpy.context.view_layer.update()
    kids = [c for c in root.children_recursive if c.type == 'MESH']
    pts = [o.matrix_world @ Vector(c) for o in [root] + kids for c in o.bound_box]
    log('%-9s root %5d tris, total %5d  L %.2f m  H %.2f m'
        % (a, L.tri_count(root), L.tri_count(root) + sum(L.tri_count(k) for k in kids),
           max(p.y for p in pts) - min(p.y for p in pts),
           max(p.z for p in pts) - min(p.z for p in pts)))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'animals.blend'), compress=True)
L.export_glb(OUT)
log('exported', OUT, '%.0f KB' % (os.path.getsize(OUT) / 1024))
