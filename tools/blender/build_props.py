"""SCHOFIELD — build public/assets/models/props.glb

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_props.py

Regenerates the texture atlases first (system python3 + numpy/scipy/PIL via
props_textures.py), then builds every contract prop as a ROOT object at the world origin
(origin = ground contact, model faces -Y), bakes vertex-colour AO, exports the GLB and
re-imports it to verify names / tri counts / bounds.

Materials (shared by every prop):
  Props_Atlas    opaque, props_atlas.jpg (1024², JPEG) × COLOR_0
  Props_Foliage  alphaMode MASK (cutoff 0.4), double-sided, props_foliage.png × COLOR_0
"""
import bpy, bmesh, math, random, os, sys, subprocess
from mathutils import Vector, Matrix, Euler, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib
import bl_common as C
import atlas_layout as L
importlib.reload(C)
importlib.reload(L)
V = Vector

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_GLB = os.path.join(ROOT, 'public', 'assets', 'models', 'props.glb')
BUILD = os.path.join(HERE, '_build')

CONTRACT = ['Pine_A', 'Pine_B', 'Pine_Snow', 'DeadTree', 'Saguaro', 'Joshua', 'Sagebrush',
            'Rock_A', 'Rock_B', 'Rock_C', 'Boulder_Big', 'CliffChunk', 'Fence_Rail',
            'TelegraphPole', 'Barrel', 'Crate', 'Wagon_Wreck', 'CowSkull', 'GraveCross',
            'Tumbleweed', 'Signpost', 'WaterTrough', 'Windmill']

A = C.AtlasUV(L.PROPS, L.PROPS_SIZE, inset=2.5)
FA = C.AtlasUV(L.FOLIAGE, L.FOLIAGE_SIZE, inset=1.5)
OPQ, FOL = 0, 1
MATS = {}
UP = V((0, 0, 1))


def uvq(auv, rect):
    return [auv(rect, 0, 0), auv(rect, 1, 0), auv(rect, 1, 1), auv(rect, 0, 1)]


def finish(mb, name, sharp=40, ao=None, tint=None, foliage_fn=None, occluders=()):
    used = sorted({f[2] for f in mb.faces})
    mats = [MATS['opq'] if i == OPQ else MATS['fol'] for i in used]
    remap = {m: i for i, m in enumerate(used)}
    mb.faces = [(f[0], f[1], remap[f[2]], f[3]) for f in mb.faces]
    ob = mb.build(name, mats, sharp_angle=sharp)
    ao = ao or {}
    C.bake_vertex_colors(ob, tint_fn=tint, foliage_fn=foliage_fn, occluders=occluders, **ao)
    return ob


# ============================================================================ foliage cards
def card(mb, frect, base, up, right, nrm_fn, want_normal=None, auv=FA, uv=None):
    """Quad from bottom-centre `base`, spanning ±right horizontally and `up` vertically.
    Winding is chosen so the geometric normal agrees with want_normal (or the custom
    normals), which keeps three.js' back-face normal flip consistent for double-sided cards."""
    p0, p1, p2, p3 = base - right, base + right, base + right + up, base - right + up
    uvs = uv or uvq(auv, frect)
    gn = right.cross(up)
    ns = [nrm_fn(p) for p in (p0, p1, p2, p3)]
    avg = want_normal if want_normal is not None else (ns[0] + ns[1] + ns[2] + ns[3])
    if gn.dot(avg) < 0:
        p0, p1, p2, p3 = p1, p0, p3, p2
        uvs = [uvs[1], uvs[0], uvs[3], uvs[2]]
        ns = [ns[1], ns[0], ns[3], ns[2]]
    return mb.quad([p0, p1, p2, p3], uvs, FOL, smooth=True, tag='foliage', normals=ns)


def canopy_normal_fn(axis_fn, up_bias=0.55, local_center=None, local_w=0.45):
    def fn(p):
        a = axis_fn(p.z)
        rad = V((p.x - a.x, p.y - a.y, 0))
        if rad.length < 1e-4:
            rad = V((0, 0, 0))
        else:
            rad.normalize()
        n = rad + UP * up_bias
        if local_center is not None:
            lc = p - local_center
            if lc.length > 1e-4:
                n = n + lc.normalized() * local_w
        return n.normalized()
    return fn


def clump(mb, frect, center, out, size, rnd, axis_fn, n_cards=3, up_bias=0.55, horiz=True):
    """Pine clump: crossed vertical cards + one tilted horizontal card around `center`."""
    out = V((out.x, out.y, 0)).normalized() if V((out.x, out.y, 0)).length > 1e-3 else V((1, 0, 0))
    tan = UP.cross(out).normalized()
    upd = (UP * 0.85 + out * 0.35).normalized()
    roll = rnd.uniform(-0.35, 0.35)
    q = Matrix.Rotation(roll, 3, out)
    upd = q @ upd
    tan = q @ tan
    nfn = canopy_normal_fn(axis_fn, up_bias, local_center=center - UP * size * 0.25, local_w=0.5)
    s = size
    # card A: faces outward
    card(mb, frect, center - upd * s * 0.42, upd * s, tan * s * 0.5, nfn)
    # card B: rotated 90deg about upd
    side = upd.cross(tan).normalized()
    ang = rnd.uniform(-0.3, 0.3)
    bdir = (tan * math.sin(ang) + side * math.cos(ang)).normalized()
    card(mb, frect, center - upd * s * 0.42, upd * s * 0.95, bdir * s * 0.48, nfn)
    if horiz:
        # card C: near-horizontal, bottom edge toward the trunk, tilted up
        tilt = rnd.uniform(0.25, 0.5)
        hup = (out * math.cos(tilt) + UP * math.sin(tilt)).normalized()
        card(mb, frect, center - hup * s * 0.40 + UP * s * 0.05, hup * s * 0.9, tan * s * 0.5, nfn, want_normal=UP)
    if n_cards > 3:
        hup = (out * 0.3 + UP).normalized()
        d2 = (tan + side).normalized()
        card(mb, frect, center - hup * s * 0.4, hup * s * 0.85, d2 * s * 0.45, nfn)


def trunk_path(height, n, lean, wobble, rnd, base=V((0, 0, 0))):
    pts = []
    ph = rnd.uniform(0, 10)
    for i in range(n + 1):
        t = i / n
        z = height * t
        off = lean * (t ** 1.3)
        w = V((noise.noise(V((ph, t * 2.2, 0))) * wobble, noise.noise(V((ph + 5, t * 2.2, 0))) * wobble, 0)) * min(1, t * 3)
        pts.append(base + V((off.x, off.y, z)) + w)
    return pts


def axis_from_path(pts):
    def fn(z):
        if z <= pts[0].z:
            return pts[0]
        for i in range(1, len(pts)):
            if pts[i].z >= z:
                a, b = pts[i - 1], pts[i]
                t = (z - a.z) / max(b.z - a.z, 1e-6)
                return a.lerp(b, t)
        return pts[-1]
    return fn


def point_on(pts, t):
    """Point at fraction t of arc length along polyline."""
    lens = [0.0]
    for i in range(1, len(pts)):
        lens.append(lens[-1] + (pts[i] - pts[i - 1]).length)
    T = lens[-1] * t
    for i in range(1, len(pts)):
        if lens[i] >= T:
            f = (T - lens[i - 1]) / max(lens[i] - lens[i - 1], 1e-6)
            return pts[i - 1].lerp(pts[i], f), (pts[i] - pts[i - 1]).normalized()
    return pts[-1], (pts[-1] - pts[-2]).normalized()


def foliage_shade(axis_fn, crown_z0, crown_z1, crown_r, base=(0.55, 0.62), hue=0.07, seed=0, snow=False):
    def fn(co, n):
        a = axis_fn(co.z)
        d = V((co.x - a.x, co.y - a.y)).length
        inner = min(1.0, d / max(crown_r(co.z), 0.3))
        h = min(1.0, max(0.0, (co.z - crown_z0) / max(crown_z1 - crown_z0, 0.1)))
        ao = base[0] + (1 - base[0]) * (0.55 * inner + 0.45 * h)
        ao = min(1.0, ao + 0.12 * max(0.0, n.z))
        nz = noise.noise(co * 0.35 + V((seed, seed, seed)))
        r = ao * (1 + hue * nz)
        g = ao * (1 + hue * 0.3 * nz)
        b = ao * (1 - hue * nz)
        if snow:
            r = g = b = ao
        return (min(1, r), min(1, g), min(1, b))
    return fn


# ============================================================================ pines
def pine_ponderosa(name, seed, height=17.0, frect='pond_a'):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    lean = V((rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), 0))
    pts = trunk_path(height, 9, lean, 0.18, rnd)
    rad = [0.40 * (1 - i / 9) ** 0.85 + 0.05 for i in range(10)]
    rad[0] *= 1.45
    rad[1] *= 1.08
    C.tube(mb, A, 'bark_pond', pts, rad, 8, 4.0, OPQ, u_repeat=2, jitter=0.05, seed=seed, smooth=True)
    axis = axis_from_path(pts)
    z0 = height * 0.46
    crown_r = lambda z: 0.6 + 2.9 * max(0.0, (1 - (z - z0) / (height - z0))) ** 0.55 * (0.55 + 0.45 * min(1, (z - z0) / 2.5 + 0.2)) if z > z0 else 1.5
    # dead stubs on the bare trunk
    for i in range(5):
        z = rnd.uniform(2.2, z0 - 0.5)
        az = rnd.uniform(0, 2 * math.pi)
        o = V((math.cos(az), math.sin(az), 0))
        p0 = axis(z)
        Lb = rnd.uniform(0.35, 1.0)
        p1 = p0 + o * Lb + UP * rnd.uniform(-0.25, 0.05)
        C.tube(mb, A, 'deadwood', [p0, p1], [0.07, 0.02], 4, 2.0, OPQ, seed=seed + i)
    # primary branches: drooping low in the crown, sweeping up near the top
    nb = 20
    ga = rnd.uniform(0, 6)
    for i in range(nb):
        t = (i + rnd.uniform(0.1, 0.9)) / nb
        z = z0 + (height - z0 - 0.8) * t ** 0.85
        az = ga + i * 2.399 + rnd.uniform(-0.3, 0.3)
        o = V((math.cos(az), math.sin(az), 0))
        Lb = crown_r(z) * rnd.uniform(0.8, 1.1)
        p0 = axis(z)
        pitch = -0.3 + 0.75 * t + rnd.uniform(-0.1, 0.1)
        p1 = p0 + o * Lb * 0.40 + UP * Lb * pitch * 0.4
        p2 = p1 + o * Lb * 0.35 + UP * Lb * pitch * 0.25
        p3 = p2 + o * Lb * 0.25 + UP * Lb * rnd.uniform(0.18, 0.32)
        br = [0.13 * (1 - t * 0.5), 0.07, 0.045, 0.02]
        C.tube(mb, A, 'bark_pond', [p0, p1, p2, p3], br, 4, 8.0, OPQ, seed=seed + 100 + i)
        for k, (tt, sz) in enumerate([(0.32, 1.6), (0.55, 1.9), (0.76, 2.2), (0.96, 2.3)]):
            if k == 0 and rnd.random() < 0.4:
                continue
            c, d = point_on([p0, p1, p2, p3], tt)
            s = sz * rnd.uniform(0.85, 1.15) * (0.8 + 0.3 * (1 - t))
            clump(mb, frect, c + UP * s * 0.22, o, s, rnd, axis, horiz=(k > 0))
    # leader / top clumps
    top = pts[-1]
    for k in range(5):
        az = k * 1.3 + rnd.uniform(0, 0.6)
        o = V((math.cos(az), math.sin(az), 0))
        c = top + o * rnd.uniform(0.2, 0.8) - UP * rnd.uniform(0.0, 1.6)
        clump(mb, frect, c, o, rnd.uniform(1.6, 2.1), rnd, axis)
    fshade = foliage_shade(axis, z0, height + 1, crown_r, base=(0.5, 0.6), seed=seed)
    tint = lambda co, n: (1.0, 0.97, 0.94) if co.z > 0.6 else (0.85, 0.8, 0.76)
    return finish(mb, name, ao=dict(rays=20, max_dist=2.5, strength=0.8), tint=tint, foliage_fn=fshade)


def pine_lodgepole(name, seed, height=15.0, frect='pond_b'):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    lean = V((rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0))
    pts = trunk_path(height, 8, lean, 0.08, rnd)
    rad = [0.26 * (1 - i / 8) ** 0.9 + 0.03 for i in range(9)]
    rad[0] *= 1.35
    C.tube(mb, A, 'bark_fir', pts, rad, 7, 4.0, OPQ, jitter=0.04, seed=seed, smooth=True)
    axis = axis_from_path(pts)
    z0 = height * 0.36
    crown_r = lambda z: 0.35 + 1.7 * max(0.0, 1 - (z - z0) / (height - z0)) ** 0.75 if z > z0 else 0.8
    for i in range(6):
        z = rnd.uniform(1.8, z0)
        az = rnd.uniform(0, 2 * math.pi)
        o = V((math.cos(az), math.sin(az), 0))
        p0 = axis(z)
        C.tube(mb, A, 'deadwood', [p0, p0 + o * rnd.uniform(0.3, 0.7) - UP * 0.15], [0.04, 0.012], 3, 2.0, OPQ, cap_end=False, seed=seed + i)
    nb = 34
    ga = rnd.uniform(0, 6)
    for i in range(nb):
        t = (i + rnd.uniform(0.1, 0.9)) / nb
        z = z0 + (height - z0 - 0.6) * t
        az = ga + i * 2.399 + rnd.uniform(-0.3, 0.3)
        o = V((math.cos(az), math.sin(az), 0))
        Lb = crown_r(z) * rnd.uniform(0.8, 1.1)
        p0 = axis(z)
        p1 = p0 + o * Lb * 0.6 - UP * Lb * 0.15
        p2 = p1 + o * Lb * 0.4 + UP * Lb * 0.12
        C.tube(mb, A, 'bark_fir', [p0, p1, p2], [0.06, 0.035, 0.015], 3, 8.0, OPQ, cap_end=False, seed=seed + 50 + i)
        for tt, sz in ((0.35, 1.2), (0.68, 1.4), (0.97, 1.5)):
            if tt < 0.5 and rnd.random() < 0.4:
                continue
            c, d = point_on([p0, p1, p2], tt)
            s = sz * rnd.uniform(0.85, 1.15) * (0.8 + 0.3 * (1 - t))
            clump(mb, frect, c + UP * s * 0.2, o, s, rnd, axis, horiz=(tt > 0.9))
    top = pts[-1]
    for k in range(3):
        az = k * 2.1 + rnd.uniform(0, 1)
        o = V((math.cos(az), math.sin(az), 0))
        clump(mb, frect, top - UP * (0.2 + k * 0.5) + o * 0.15, o, rnd.uniform(1.0, 1.3), rnd, axis, horiz=False)
    fshade = foliage_shade(axis, z0, height + 0.5, crown_r, base=(0.5, 0.6), seed=seed)
    tint = lambda co, n: (0.95, 0.93, 0.9) if co.z > 0.5 else (0.8, 0.76, 0.72)
    return finish(mb, name, ao=dict(rays=20, max_dist=2.0, strength=0.8), tint=tint, foliage_fn=fshade)


def pine_snow(name, seed, height=12.5):
    """Snow-laden spruce/fir: whorls of drooping fir-spray cards, snow on the upward cards."""
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    pts = trunk_path(height, 7, V((rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), 0)), 0.05, rnd)
    rad = [0.28 * (1 - i / 7) ** 0.9 + 0.03 for i in range(8)]
    rad[0] *= 1.3
    C.tube(mb, A, 'bark_fir', pts, rad, 7, 4.0, OPQ, jitter=0.04, seed=seed, smooth=True)
    axis = axis_from_path(pts)
    z0 = 1.4
    crown_r = lambda z: 0.25 + 3.1 * max(0.0, 1 - (z - z0) / (height - z0)) ** 1.0
    nw = 20
    ga = rnd.uniform(0, 6)
    for w in range(nw):
        t = w / (nw - 1)
        z = z0 + (height - z0 - 0.9) * (t ** 0.92)
        nbr = 7 if t < 0.5 else (6 if t < 0.8 else 4)
        for b in range(nbr):
            az = ga + w * 0.9 + b * 2 * math.pi / nbr + rnd.uniform(-0.25, 0.25)
            o = V((math.cos(az), math.sin(az), 0))
            tan = UP.cross(o)
            Lb = crown_r(z) * rnd.uniform(0.85, 1.12) + 0.3
            droop = rnd.uniform(0.2, 0.42) * (0.5 + t * 0.2)
            dirv = (o * math.cos(droop) - UP * math.sin(droop)).normalized()
            base = axis(z) - dirv * 0.1
            wdt = Lb * 0.52
            nfn = canopy_normal_fn(axis, 0.8)
            # u along the branch (stem at left edge u=0 -> trunk), v across
            # folded "tent" card: 2 segments along the branch (tip droops more) x 2 halves
            # hinged on the stem, so it never collapses to a razor line when seen edge-on
            fr = 'fir_snow'
            rq = Matrix.Rotation(rnd.uniform(-0.2, 0.2), 3, dirv)
            tn = rq @ tan
            dir2 = (dirv * math.cos(0.22) - UP * math.sin(0.22)).normalized()
            fold = rnd.uniform(0.28, 0.42)
            mids = [base, base + dirv * Lb * 0.5, base + dirv * Lb * 0.5 + dir2 * Lb * 0.5]
            rows = []
            for m in mids:
                rows.append([m - tn * wdt * 0.5 - UP * wdt * 0.5 * fold, m, m + tn * wdt * 0.5 - UP * wdt * 0.5 * fold])
            for i in range(2):
                for j in range(2):
                    q = [rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]]
                    uvs = [FA(fr, i * 0.5, j * 0.5), FA(fr, (i + 1) * 0.5, j * 0.5), FA(fr, (i + 1) * 0.5, (j + 1) * 0.5), FA(fr, i * 0.5, (j + 1) * 0.5)]
                    ns = [nfn(p) for p in q]
                    gn = (q[1] - q[0]).cross(q[3] - q[0])
                    if gn.z < 0:
                        q = [q[3], q[2], q[1], q[0]]
                        uvs = [uvs[3], uvs[2], uvs[1], uvs[0]]
                        ns = [ns[3], ns[2], ns[1], ns[0]]
                    mb.quad(q, uvs, FOL, smooth=True, tag='foliage', normals=ns)
            # second, steeper card (plain spray) for side silhouette
            if t < 0.92 and rnd.random() < 0.85:
                rq2 = Matrix.Rotation(rnd.choice([-1, 1]) * rnd.uniform(0.9, 1.25), 3, dirv)
                q = [base + rq2 @ (p - base) for p in (base - tan * wdt * 0.42, base + dirv * Lb * 0.92 - tan * wdt * 0.42,
                                                     base + dirv * Lb * 0.92 + tan * wdt * 0.42, base + tan * wdt * 0.42)]
                fr2 = 'fir'
                uvs2 = [FA(fr2, 0, 0), FA(fr2, 1, 0), FA(fr2, 1, 1), FA(fr2, 0, 1)]
                ns2 = [nfn(p) for p in q]
                gn = (q[1] - q[0]).cross(q[3] - q[0])
                if gn.dot(ns2[0] + ns2[2]) < 0:
                    q = [q[3], q[2], q[1], q[0]]
                    uvs2 = [uvs2[3], uvs2[2], uvs2[1], uvs2[0]]
                    ns2 = [ns2[3], ns2[2], ns2[1], ns2[0]]
                mb.quad(q, uvs2, FOL, smooth=True, tag='foliage', normals=ns2)
    # leader: small vertical sprays at the top (stem along v -> rotated uv)
    top = pts[-1]
    for k in range(2):
        az = k * math.pi / 2 + 0.3
        rgt = V((math.cos(az), math.sin(az), 0)) * 0.3
        fr = 'fir'
        uv = [FA(fr, 0, 1), FA(fr, 0, 0), FA(fr, 1, 0), FA(fr, 1, 1)]
        card(mb, fr, top - UP * 0.9, UP * 1.4, rgt, canopy_normal_fn(axis, 0.8), uv=uv)
    fshade = foliage_shade(axis, z0, height + 0.5, crown_r, base=(0.45, 0.6), hue=0.05, seed=seed)
    tint = lambda co, n: (0.9, 0.88, 0.86)
    return finish(mb, name, ao=dict(rays=16, max_dist=2.0, strength=0.8), tint=tint, foliage_fn=fshade)


# ============================================================================ other plants
def dead_tree(name, seed=7):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    pts = trunk_path(4.2, 5, V((0.5, 0.2, 0)), 0.25, rnd)
    rad = [0.42, 0.30, 0.26, 0.22, 0.19, 0.16]
    C.tube(mb, A, 'deadwood', pts, rad, 7, 2.5, OPQ, jitter=0.1, seed=seed, cap_end=True)
    tips = []

    def limb(p, d, Lb, r, depth, sd):
        r2 = random.Random(sd)
        segs = [p]
        dd = d.normalized()
        for k in range(3):
            dd = (dd + V((r2.uniform(-0.35, 0.35), r2.uniform(-0.35, 0.35), r2.uniform(-0.1, 0.25)))).normalized()
            segs.append(segs[-1] + dd * Lb / 3)
        C.tube(mb, A, 'deadwood', segs, [r, r * 0.8, r * 0.6, r * 0.35], 5 if depth > 1 else 4, 2.5, OPQ, seed=sd, cap_end=True)
        if depth > 0:
            nkids = 2
            for kk in range(nkids):
                t = r2.uniform(0.55, 0.95)
                pp, dir_ = point_on(segs, t)
                nd = (dir_ + V((r2.uniform(-1, 1), r2.uniform(-1, 1), r2.uniform(0.0, 0.8))) * 0.9).normalized()
                limb(pp, nd, Lb * r2.uniform(0.5, 0.7), r * 0.55, depth - 1, sd * 7 + kk + 1)
        else:
            tips.append((segs[-1], dd))
    top = pts[-1]
    for i in range(3):
        az = i * 2.2 + rnd.uniform(-0.3, 0.3)
        d = V((math.cos(az), math.sin(az), 1.1))
        limb(top - UP * 0.2, d, rnd.uniform(2.4, 3.4), 0.17, 2, seed * 13 + i)
    # one broken low limb
    p, _ = point_on(pts, 0.45)
    limb(p, V((-1, 0.4, 0.5)), 1.6, 0.12, 1, 999)
    axis = lambda z: V((0, 0, z))
    for (p, d) in tips:
        s = rnd.uniform(1.4, 2.0)
        side = d.cross(UP)
        if side.length < 1e-3:
            side = V((1, 0, 0))
        side.normalize()
        nfn = lambda q: (q - V((0, 0, 4))).normalized()
        card(mb, 'twigs', p - d * s * 0.15, d * s, side * s * 0.5, nfn)
        card(mb, 'twigs', p - d * s * 0.15, d * s, d.cross(side).normalized() * s * 0.5, nfn)
    fshade = lambda co, n: (0.85, 0.85, 0.85)
    tint = lambda co, n: (0.95, 0.92, 0.88) if co.z > 0.4 else (0.75, 0.7, 0.65)
    return finish(mb, name, ao=dict(rays=18, max_dist=1.5, strength=0.8), tint=tint, foliage_fn=fshade)


def saguaro(name, seed=11):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    ribs = 12

    def prof(nrib, valley=0.85):
        p = []
        for k in range(nrib * 2):
            p.append((2 * math.pi * k / (nrib * 2), 1.0 if k % 2 == 0 else valley))
        return p, [k / 2 for k in range(nrib * 2 + 1)]
    pr, pu = prof(ribs)
    H = 6.6
    zs = [0, 0.4, 1.2, 2.2, 3.2, 4.2, 5.2, 5.9, 6.25, 6.48, 6.6]
    rs = [0.33, 0.31, 0.30, 0.30, 0.295, 0.29, 0.28, 0.26, 0.21, 0.13, 0.03]
    pts = [V((noise.noise(V((z * 0.3, 1, 2))) * 0.05, 0, z)) for z in zs]
    C.tube(mb, A, 'saguaro', pts, rs, ribs * 2, 2.6, OPQ, profile=pr, prof_u=pu, u_repeat=ribs, cap_end=True, smooth=True)
    arms = [(2.4, 0.3, 1.0, 2.3), (3.3, math.pi + 0.35, 0.9, 1.9), (4.4, math.pi * 0.55, 0.55, 0.9)]
    pr2, pu2 = prof(9)
    for (za, az, reach, rise) in arms:
        o = V((math.cos(az), math.sin(az), 0))
        c0 = V((0, 0, za))
        pts = [c0 + o * 0.05, c0 + o * (0.25 + reach * 0.45) + UP * 0.02, c0 + o * (0.25 + reach * 0.8) + UP * 0.18,
               c0 + o * (0.25 + reach) + UP * 0.5]
        top = pts[-1]
        for k in range(1, 4):
            pts.append(top + UP * rise * k / 3 + o * 0.03 * k)
        pts += [pts[-1] + UP * 0.22, pts[-1] + UP * 0.34]
        r = 0.2 if reach > 0.6 else 0.16
        rr = [r * 0.95, r, r, r, r, r * 0.97, r * 0.93, r * 0.6, r * 0.12]
        C.tube(mb, A, 'saguaro', pts, rr, 18, 2.6, OPQ, profile=pr2, prof_u=pu2, u_repeat=9, cap_end=True, smooth=True)

    def tint(co, n):
        base = min(1.0, co.z / 0.8)
        top = max(0.0, (co.z - 6.0) / 0.6)
        r = 0.78 + 0.22 * base + 0.05 * top
        g = 0.72 + 0.28 * base + 0.05 * top
        b = 0.65 + 0.35 * base
        return (r, g, b)
    return finish(mb, name, sharp=70, ao=dict(rays=18, max_dist=1.2, strength=0.75), tint=tint)


def joshua(name, seed=5):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    tips = []

    def limb(p, d, Lb, r, depth, sd):
        r2 = random.Random(sd)
        segs = [p]
        dd = d.normalized()
        for k in range(2):
            dd = (dd + V((r2.uniform(-0.4, 0.4), r2.uniform(-0.4, 0.4), 0.15))).normalized()
            segs.append(segs[-1] + dd * Lb / 2)
        C.tube(mb, A, 'bark_fir', segs, [r, r * 0.9, r * 0.8], 6, 2.0, OPQ, seed=sd, cap_end=depth == 0, jitter=0.12)
        if depth > 0:
            n = 2 if r2.random() < 0.7 else 3
            for k in range(n):
                az = r2.uniform(0, 2 * math.pi)
                nd = V((math.cos(az), math.sin(az), r2.uniform(0.6, 1.4)))
                limb(segs[-1], nd, Lb * r2.uniform(0.6, 0.85), r * 0.75, depth - 1, sd * 5 + k + 1)
        else:
            tips.append((segs[-1], dd))
    trunk = [V((0, 0, 0)), V((0.05, 0.02, 1.0)), V((0.12, 0.0, 2.0))]
    C.tube(mb, A, 'bark_fir', trunk, [0.32, 0.24, 0.21], 7, 2.0, OPQ, seed=seed, cap_end=False, jitter=0.12)
    for k in range(3):
        az = k * 2.1 + 0.4
        limb(trunk[-1], V((math.cos(az), math.sin(az), 1.2)), 1.5, 0.17, 1 if k < 2 else 0, 70 + k)
    for (p, d) in tips:
        s = rnd.uniform(0.95, 1.2)
        nfn = lambda q, p=p: ((q - p) * 0.6 + UP * 0.4).normalized()
        for k in range(3):
            az = k * math.pi / 3 + rnd.uniform(0, 0.4)
            rgt = V((math.cos(az), math.sin(az), 0)) * s * 0.5
            card(mb, 'joshua', p - UP * s * 0.5, UP * s, rgt, nfn)
        hz = V((1, 0, 0)) * s * 0.5
        card(mb, 'joshua', p - V((0, 1, 0)) * s * 0.5 + UP * 0.05, V((0, 1, 0)) * s, hz, nfn, want_normal=UP)
    tint = lambda co, n: (0.82, 0.74, 0.62)
    fshade = lambda co, n: (0.8 + 0.2 * max(0, n.z),) * 3
    return finish(mb, name, ao=dict(rays=16, max_dist=1.0, strength=0.7), tint=tint, foliage_fn=fshade)


def sagebrush(name, seed=3):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    ctr = V((0, 0, 0.3))
    nfn = lambda q: ((q - ctr) * V((1, 1, 0.8)) + UP * 0.3).normalized()
    # outer ring: cards leaning outward (a loose mound), inner: upright crossed cards
    n = 7
    for i in range(n):
        az = i * 2 * math.pi / n + rnd.uniform(-0.2, 0.2)
        o = V((math.cos(az), math.sin(az), 0))
        tan = UP.cross(o)
        s = rnd.uniform(0.8, 1.1)
        lean = rnd.uniform(0.35, 0.6)
        up = (UP * math.cos(lean) + o * math.sin(lean)).normalized()
        card(mb, 'sage', o * 0.12 - UP * 0.05, up * s * 0.9, tan * s * 0.5, nfn, want_normal=(o + UP * 0.5))
    for i in range(3):
        az = i * math.pi / 3 + rnd.uniform(-0.2, 0.2)
        rgt = V((math.cos(az), math.sin(az), 0))
        s = rnd.uniform(1.05, 1.25)
        card(mb, 'sage', -UP * 0.04, UP * s, rgt * s * 0.55, nfn)

    def fshade(co, n):
        h = min(1.0, max(0.0, co.z / 0.9))
        a = 0.5 + 0.5 * h
        nz = noise.noise(co * 2.0)
        return (a * (1 + 0.04 * nz), a, a * (1 - 0.04 * nz))
    return finish(mb, name, foliage_fn=fshade)


# ============================================================================ rocks
def make_rock(name, size, seed, rect, tile, subdiv=4, planes=6, plane_depth=(0.62, 0.85), terr=None,
              amp=0.18, freq=1.6, target=760, sink=0.12, tint=None, flat_bottom=0.55, sharp=38, horiz_planes=False):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    off = V((rnd.uniform(0, 100), rnd.uniform(0, 100), rnd.uniform(0, 100)))
    pls = []
    for k in range(planes):
        if horiz_planes and k % 2 == 0:
            nrm = V((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.15, 0.15))).normalized()
        else:
            nrm = V((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.3, 1.0))).normalized()
        pls.append((nrm, rnd.uniform(*plane_depth)))
    for v in bm.verts:
        p = v.co.copy()
        d = noise.fractal(p * freq + off, 0.7, 2.1, 4) * amp + noise.noise(p * freq * 3.5 + off) * amp * 0.25
        p = p * (1 + d)
        for nrm, dd in pls:
            h = p.dot(nrm)
            if h > dd:
                p -= nrm * (h - dd) * 0.92
        p = V((p.x * sx, p.y * sy, p.z * sz))
        v.co = p
    # terraces (sandstone ledges)
    if terr:
        for v in bm.verts:
            z = v.co.z
            q = round(z / terr) * terr
            v.co.z = z + (q - z) * 0.45
    # flat bottom
    zb = -sz * flat_bottom
    for v in bm.verts:
        if v.co.z < zb:
            v.co.z = zb + (v.co.z - zb) * 0.08
    # small detail noise
    for v in bm.verts:
        v.co += V((noise.noise(v.co * 3.1 + off), noise.noise(v.co * 3.1 + off + V((9, 0, 0))), noise.noise(v.co * 3.1 + off + V((0, 9, 0))))) * min(size) * 0.025
    minz = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.co.z -= minz + sink * size[2]
    me = bpy.data.meshes.new(name + '_tmp')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name + '_tmp', me)
    bpy.context.scene.collection.objects.link(ob)
    ntri = len(me.polygons)
    if ntri > target:
        mod = ob.modifiers.new('dec', 'DECIMATE')
        mod.ratio = target / ntri
        mod.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    me2.name = name
    # UVs: per-face dominant-axis box projection into the rock rect
    bm = bmesh.new()
    bm.from_mesh(me2)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    uvl = bm.loops.layers.uv.new('UVMap')
    xs = [v.co for v in bm.verts]
    mn = V((min(p.x for p in xs), min(p.y for p in xs), min(p.z for p in xs)))
    ext = max(max(p.x for p in xs) - mn.x, max(p.y for p in xs) - mn.y, max(p.z for p in xs) - mn.z)
    T = max(tile, ext * 1.01)
    ou, ov = rnd.uniform(0, max(0, 1 - ext / T)), rnd.uniform(0, max(0, 1 - ext / T))
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co - mn
            if ax == 0:
                a, b = (p.y if n.x > 0 else ext - p.y), p.z
            elif ax == 1:
                a, b = (ext - p.x if n.y > 0 else p.x), p.z
            else:
                a, b = p.x, p.y
            lp[uvl].uv = A(rect, ou + a / T, ov + b / T)
    bm.to_mesh(me2)
    bm.free()
    me2.materials.append(MATS['opq'])
    me2.polygons.foreach_set('use_smooth', [True] * len(me2.polygons))
    me2.set_sharp_from_angle(angle=math.radians(sharp))
    ob = bpy.data.objects.new(name, me2)
    bpy.context.scene.collection.objects.link(ob)
    hmax = max(size[2] * (1 - sink), 0.1)

    def default_tint(co, n):
        h = max(0.0, min(1.0, co.z / hmax))
        dust = 0.08 * max(0.0, n.z)
        k = 0.8 + 0.2 * h ** 0.6
        return (k + dust, k + dust * 0.9, k + dust * 0.7)
    C.bake_vertex_colors(ob, rays=24, max_dist=max(size) * 0.35, strength=0.9, tint_fn=tint or default_tint)
    return ob


# ============================================================================ man-made props
def fence_rail(name, seed=21):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    # post at x=-1.5 (next section supplies the one at +1.5)
    C.tube(mb, A, 'wood_grey', [V((-1.5, 0, -0.3)), V((-1.52, 0.02, 1.35))], [0.08, 0.07], 6, 2.0, OPQ, u_repeat=1, jitter=0.12, seed=seed)
    for k, z in enumerate((0.45, 0.85, 1.22)):
        sag = rnd.uniform(0.02, 0.06)
        a = V((-1.55, rnd.uniform(-0.1, -0.08), z + rnd.uniform(-0.03, 0.03)))
        b = V((1.55, rnd.uniform(-0.1, -0.08), z + rnd.uniform(-0.05, 0.03)))
        m = (a + b) / 2 - UP * sag
        C.tube(mb, A, 'wood_grey', [a, m, b], [0.055, 0.05, 0.055], 5, 1.6, OPQ, cap_start=True, jitter=0.15, seed=seed + k)
    return finish(mb, name, sharp=50, ao=dict(rays=12, max_dist=0.6))


def telegraph_pole(name, seed=23):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    C.tube(mb, A, 'deadwood', [V((0, 0, -0.3)), V((0.03, 0.02, 3.5)), V((0.05, 0.03, 7.2))], [0.15, 0.13, 0.11], 7, 2.5, OPQ, jitter=0.05, seed=seed)
    top = V((0.05, 0.03, 6.85))
    rr = random.Random(1)
    C.box(mb, A, 'wood_brown', top, (1.7, 0.11, 0.1), mat=OPQ, tile=(0.25, 1.0), rnd=rr)
    for sgn in (-1, 1):
        C.box(mb, A, 'wood_brown', top + V((sgn * 0.28, -0.07, -0.28)), (0.04, 0.03, 0.62),
              rot=Matrix.Rotation(sgn * -0.75, 4, 'Y'), mat=OPQ, tile=(0.25, 1.0), rnd=rr)
    wires = []
    for k, x in enumerate((-0.75, -0.4, 0.4, 0.75)):
        p = top + V((x, 0, 0.05))
        C.tube(mb, A, 'bone', [p, p + UP * 0.14, p + UP * 0.2], [0.04, 0.04, 0.025], 5, 1.0, OPQ, cap_end=True, cap_start=True, seed=k)
        wires.append(p + UP * 0.16)
    glass = lambda co, n: (0.45, 0.72, 0.68) if co.z > 6.9 else (0.9, 0.88, 0.84)
    ob = finish(mb, name, sharp=45, ao=dict(rays=12, max_dist=0.6), tint=glass)
    for k, w in enumerate(wires):
        C.empty('Wire_%d' % (k + 1), w, parent=ob, size=0.1)
    return ob


def barrel(name, seed=31):
    mb = C.MeshBuilder()
    H, R = 0.9, 0.29
    zs = [0, 0.12, 0.3, 0.45, 0.6, 0.78, 0.9]
    rs = [R * (0.86 + 0.14 * math.sin(math.pi * z / H)) for z in zs]
    C.tube(mb, A, 'planks', [V((0, 0, z)) for z in zs], rs, 12, 1.0, OPQ, u_repeat=2, cap_end=False, smooth=True)
    # lid (slightly recessed) and chime
    lid = V((0, 0, H - 0.03))
    ring = []
    cz = mb.v(lid)
    for s in range(12):
        a = 2 * math.pi * s / 12
        ring.append(mb.v(lid + V((math.cos(a), math.sin(a), 0)) * rs[-1] * 0.96))
    for s in range(12):
        s2 = (s + 1) % 12
        a0, a1 = 2 * math.pi * s / 12, 2 * math.pi * s2 / 12
        mb.face([ring[s], ring[s2], cz], [A('planks', 0.5 + 0.48 * math.cos(a0), 0.5 + 0.48 * math.sin(a0)),
                                          A('planks', 0.5 + 0.48 * math.cos(a1), 0.5 + 0.48 * math.sin(a1)), A('planks', 0.5, 0.5)], OPQ)
    for s in range(12):  # inner wall of chime
        s2 = (s + 1) % 12
        top_ring_idx = len(mb.verts)
    # hoops
    for zc in (0.1, 0.3, 0.6, 0.8):
        rr = R * (0.86 + 0.14 * math.sin(math.pi * zc / H)) + 0.008
        C.tube(mb, A, 'metal_rust', [V((0, 0, zc - 0.025)), V((0, 0, zc + 0.025))], [rr, rr], 12, 1.0, OPQ, cap_end=False, smooth=True)
    return finish(mb, name, sharp=50, ao=dict(rays=14, max_dist=0.5))


def crate(name, seed=33):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    s = 0.8
    fr = {'-y': ('full', 'planks_stencil'), '+y': ('full', 'planks_stencil')}
    C.box(mb, A, 'planks', V((0, 0, s / 2)), (s, s * 0.98, s), mat=OPQ, tile=(1.0, 1.0), rnd=rnd, faces_rect=fr, grain_axis=0)
    # battens along the edges
    t = 0.07
    for x in (-1, 1):
        for y in (-1, 1):
            C.box(mb, A, 'wood_brown', V((x * (s / 2 - t / 2 + 0.01), y * (s * 0.49 - t / 2 + 0.01), s / 2)), (t, t, s + 0.01), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    for z in (0.035, s - 0.035):
        for y in (-1, 1):
            C.box(mb, A, 'wood_brown', V((0, y * (s * 0.49 - t / 2 + 0.012), z)), (s - 0.02, t, t), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
        for x in (-1, 1):
            C.box(mb, A, 'wood_brown', V((x * (s / 2 - t / 2 + 0.012), 0, z)), (t, s * 0.98 - 0.02, t), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    return finish(mb, name, sharp=40, ao=dict(rays=14, max_dist=0.4))


def wheel(mb, center, radius, axis_rot, spokes=12, rnd=None, broken=0):
    """Wagon wheel in its local XZ plane (axle along local Y), transformed by axis_rot (Matrix 3x3)."""
    rnd = rnd or random.Random(0)
    R = axis_rot
    segs = 14
    # rim as a square-section torus
    rim_pts = []
    w, t = 0.07, 0.06
    rings = []
    for s in range(segs):
        a = 2 * math.pi * s / segs
        c = V((math.cos(a), 0, math.sin(a)))
        quad = [c * (radius - t) + V((0, -w / 2, 0)), c * radius + V((0, -w / 2, 0)), c * radius + V((0, w / 2, 0)), c * (radius - t) + V((0, w / 2, 0))]
        rings.append([mb.v(center + R @ q) for q in quad])
    for s in range(segs):
        s2 = (s + 1) % segs
        if broken and s in range(broken):
            continue
        for k in range(4):
            k2 = (k + 1) % 4
            rect = 'wood_brown' if k != 1 else 'metal_rust'
            mb.face([rings[s][k], rings[s2][k], rings[s2][k2], rings[s][k2]],
                    [A(rect, 0.1 + 0.2 * k, 0), A(rect, 0.1 + 0.2 * k, 1), A(rect, 0.3 + 0.2 * k, 1), A(rect, 0.3 + 0.2 * k, 0)], OPQ)
    # hub
    C.tube(mb, A, 'wood_brown', [center + R @ V((0, -0.12, 0)), center + R @ V((0, 0.12, 0))], [0.09, 0.09], 8, 1.0, OPQ, cap_end=True, cap_start=True)
    for k in range(spokes):
        a = 2 * math.pi * (k + 0.5) / spokes
        if broken and rnd.random() < 0.35:
            continue
        d = V((math.cos(a), 0, math.sin(a)))
        mid = d * (radius * 0.5)
        rot = R.to_4x4() @ Matrix.Rotation(-a + math.pi / 2, 4, 'Y')
        C.box(mb, A, 'wood_grey', center + R @ mid, (0.035, 0.035, radius - 0.1), rot=rot, mat=OPQ, tile=(0.2, 1.0), rnd=rnd, skip=('+z', '-z'))


def wagon_wreck(name, seed=41):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    sub = C.MeshBuilder()
    # bed in local coords: length along X (3.2 m), width 1.2
    Lx, Wy, Hb = 3.2, 1.15, 0.9
    C.box(sub, A, 'planks', V((0, 0, Hb)), (Lx, Wy, 0.06), mat=OPQ, tile=(1.0, 1.2), rnd=rnd, grain_axis=0)
    # side boards (one side partly missing)
    for y in (-1, 1):
        for k, z in enumerate((Hb + 0.15, Hb + 0.38)):
            if y == 1 and k == 1:
                continue
            ln = Lx if not (y == -1 and k == 1) else Lx * 0.55
            xo = 0 if ln == Lx else -Lx * 0.22
            C.box(sub, A, 'wood_grey', V((xo, y * Wy / 2, z)), (ln, 0.04, 0.2), mat=OPQ, tile=(0.3, 1.2), rnd=rnd, grain_axis=0)
    C.box(sub, A, 'wood_grey', V((-Lx / 2, 0, Hb + 0.26)), (0.04, Wy, 0.45), mat=OPQ, tile=(0.3, 1.2), rnd=rnd, grain_axis=1)
    for x in (-1.4, -0.5, 0.5, 1.4):
        for y in (-1, 1):
            C.box(sub, A, 'wood_brown', V((x, y * (Wy / 2 + 0.03), Hb + 0.25)), (0.06, 0.04, 0.55), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    # axles
    for x in (-1.1, 1.1):
        C.box(sub, A, 'wood_brown', V((x, 0, Hb - 0.12)), (0.1, 1.7, 0.1), mat=OPQ, tile=(0.3, 1.2), rnd=rnd)
    # 2 wheels on the bed (rear pair + one front), local coordinates
    wheel(sub, V((-1.1, -0.82, 0.62)), 0.62, Matrix.Identity(3), rnd=rnd)
    wheel(sub, V((-1.1, 0.82, 0.62)), 0.62, Matrix.Identity(3), rnd=rnd, broken=3)
    wheel(sub, V((1.1, -0.8, 0.52)), 0.5, Matrix.Identity(3), rnd=rnd)
    # broken tongue
    C.box(sub, A, 'wood_brown', V((2.3, 0, Hb - 0.3)), (1.4, 0.08, 0.08), rot=Matrix.Rotation(0.35, 4, 'Y'), mat=OPQ, tile=(0.3, 1.5), rnd=rnd)
    # tilt: front-right wheel missing -> that corner drops to the ground
    tilt = Matrix.Translation(V((0, 0, -0.08))) @ Matrix.Rotation(0.2, 4, 'X') @ Matrix.Rotation(-0.1, 4, 'Y')
    mb.merge(sub, tilt)
    # loose wheel lying on the ground and a fallen side board
    wheel(mb, V((1.9, 1.5, 0.05)), 0.5, Matrix.Rotation(math.pi / 2, 3, 'X') @ Matrix.Rotation(0.3, 3, 'Z'), rnd=rnd, broken=2)
    C.box(mb, A, 'wood_grey', V((-0.3, 1.3, 0.03)), (1.8, 0.2, 0.04), rot=Matrix.Rotation(0.25, 4, 'Z'), mat=OPQ, tile=(0.3, 1.2), rnd=rnd, grain_axis=0)
    # re-centre so the footprint is centred and base on the ground
    xs = [v.x for v in mb.verts]
    ys = [v.y for v in mb.verts]
    zs = [v.z for v in mb.verts]
    cx, cy, mz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)
    mb.verts = [v - V((cx, cy, mz + 0.02)) for v in mb.verts]
    return finish(mb, name, sharp=40, ao=dict(rays=14, max_dist=0.9))


def cow_skull(name, seed=51):
    """Longhorn skull lying on the ground: lofted elliptical sections (cranium -> snout),
    orbit bulges, dark sockets/nostrils via vertex colour, swept horns."""
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    # (y, half-width, half-height, z-centre)  front of the animal = -Y
    secs = [(0.22, 0.05, 0.04, 0.10), (0.20, 0.10, 0.075, 0.11), (0.15, 0.15, 0.10, 0.11), (0.08, 0.17, 0.10, 0.10),
            (0.02, 0.13, 0.09, 0.09), (-0.07, 0.10, 0.075, 0.08), (-0.17, 0.085, 0.065, 0.07), (-0.27, 0.075, 0.055, 0.06),
            (-0.34, 0.06, 0.04, 0.05), (-0.37, 0.02, 0.02, 0.05)]
    ns = 12
    rings = []
    for (y, hw, hh, zc) in secs:
        ring = []
        for k in range(ns):
            a_ = 2 * math.pi * k / ns
            x = math.cos(a_) * hw
            z = math.sin(a_) * hh
            if z < 0:
                z *= 0.7  # flatter underside
            ring.append(mb.v(V((x, y, zc + z))))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(ns):
            k2 = (k + 1) % ns
            u0, u1 = k / ns, (k + 1) / ns
            v0, v1 = i / (len(rings) - 1), (i + 1) / (len(rings) - 1)
            mb.face([rings[i][k], rings[i + 1][k], rings[i + 1][k2], rings[i][k2]],
                    [A('bone', u0, v0), A('bone', u0, v1), A('bone', u1, v1), A('bone', u1, v0)], OPQ, smooth=True)
    c = mb.v(V((0, 0.23, 0.10)))
    for k in range(ns):
        mb.face([rings[0][(k + 1) % ns], rings[0][k], c], [A('bone', 0.1, 0.1), A('bone', 0.2, 0.1), A('bone', 0.15, 0.0)], OPQ, smooth=True)
    # horns: from the poll, out sideways, then forward & up (longhorn sweep)
    for sx in (-1, 1):
        pts = [V((sx * 0.08, 0.17, 0.15))]
        d = V((sx, 0.15, 0.1)).normalized()
        for k in range(6):
            d = (d + V((0, -0.10, 0.20))).normalized()
            pts.append(pts[-1] + d * 0.075)
        rs = [0.045, 0.042, 0.036, 0.03, 0.024, 0.016, 0.005]
        C.tube(mb, A, 'bone', pts, rs, 6, 0.6, OPQ, cap_end=True, smooth=True)
    R = Matrix.Rotation(0.1, 4, 'Y') @ Matrix.Rotation(0.4, 4, 'Z')
    sockets = [R @ V((sx * 0.14, 0.09, 0.14)) for sx in (-1, 1)]
    nostr = [R @ V((sx * 0.03, -0.33, 0.08)) for sx in (-1, 1)]
    mb.verts = [R @ v for v in mb.verts]
    mz = min(v.z for v in mb.verts)
    mb.verts = [v - V((0, 0, mz + 0.01)) for v in mb.verts]
    sockets = [p - V((0, 0, mz + 0.01)) for p in sockets]
    nostr = [p - V((0, 0, mz + 0.01)) for p in nostr]

    def tint(co, n):
        k = 1.0
        for p in sockets:
            d = (co - p).length
            k = min(k, 0.25 + 0.75 * min(1.0, max(0.0, (d - 0.03) / 0.05)))
        for p in nostr:
            d = (co - p).length
            k = min(k, 0.35 + 0.65 * min(1.0, max(0.0, (d - 0.015) / 0.04)))
        dirt = 0.72 if n.z < -0.3 else 1.0
        return (0.97 * k * dirt, 0.94 * k * dirt, 0.88 * k * dirt)
    return finish(mb, name, sharp=70, ao=dict(rays=20, max_dist=0.2, strength=0.8), tint=tint)


def grave_cross(name, seed=61):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    R = Matrix.Rotation(0.08, 4, 'Y') @ Matrix.Rotation(-0.05, 4, 'X')
    C.box(mb, A, 'wood_grey', R @ V((0, 0.1, 0.55)), (0.12, 0.06, 1.45), rot=R, mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    R2 = R @ Matrix.Rotation(0.1, 4, 'Y')
    C.box(mb, A, 'wood_grey', R @ V((0, 0.05, 0.98)), (0.72, 0.05, 0.11), rot=R2, mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    ob_c = finish(mb, name + '_c', sharp=40, ao=dict(rays=10, max_dist=0.3))
    # mound + stones (like the Outlaws grave)
    mound = make_rock(name + '_m', (2.0, 1.0, 0.5), seed + 1, 'rock_sand', 2.0, subdiv=3, planes=0, amp=0.12, target=160, sink=0.45,
                      tint=lambda co, n: (0.55, 0.42, 0.33))
    stones = []
    spots = []
    for i in range(9):
        a = i / 9 * 2 * math.pi + rnd.uniform(-0.2, 0.2)
        spots.append((math.cos(a) * 0.82, math.sin(a) * 0.42, 0.0))
    for i in range(5):
        spots.append((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.2, 0.2), 0.12))
    for i, (x, y, z) in enumerate(spots):
        s = rnd.uniform(0.2, 0.34)
        st = make_rock(name + '_s%d' % i, (s * 1.3, s, s * 0.75), seed + 10 + i, 'rock_granite', 1.0, subdiv=2, planes=3, amp=0.15, target=44, sink=0.15)
        st.location = V((x, y, z))
        st.rotation_euler = (rnd.uniform(-0.2, 0.2), rnd.uniform(-0.2, 0.2), rnd.uniform(0, 6))
        stones.append(st)
    return join_objects(name, [ob_c, mound] + stones)


def join_objects(name, obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    with bpy.context.temp_override(active_object=obs[0], selected_editable_objects=obs, object=obs[0]):
        bpy.ops.object.join()
    ob = obs[0]
    ob.name = name
    ob.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # merge material slots with the same material
    return ob


def tumbleweed(name, seed=71):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    R = 0.42
    ctr = V((0, 0, R * 0.95))
    nfn = lambda q: (q - ctr).normalized()
    dirs = [V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1)), V((1, 1, 0)), V((1, -1, 0)), V((1, 0, 1)), V((0, 1, 1)), V((-1, 0, 1)), V((0, -1, 1))]
    for d in dirs:
        d = (d.normalized() + V((rnd.uniform(-0.1, 0.1),) * 3)).normalized()
        a, b, _ = C.frame_from_dir(d)
        s = R * rnd.uniform(0.9, 1.1)
        card(mb, 'tumble', ctr - b * s, b * 2 * s, a * s, nfn, want_normal=d)
    fshade = lambda co, n: (0.75 + 0.25 * max(0.0, n.z),) * 3
    return finish(mb, name, foliage_fn=fshade)


def signpost(name, seed=81):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    C.box(mb, A, 'wood_grey', V((0, 0, 1.2)), (0.12, 0.12, 2.9), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    C.box(mb, A, 'wood_brown', V((0, 0, 2.66)), (0.18, 0.18, 0.04), mat=OPQ, tile=(0.3, 0.3), rnd=rnd)
    cw = L.PROPS['signs'][2] / len(L.SIGN_TEXTS)
    sx, sy, sw, sh = L.PROPS['signs']
    boards = [(2.3, -0.25, 0), (1.95, 0.55, 1), (1.6, math.pi + 0.35, 2)]
    for (z, az, col) in boards:
        rect = (sx + col * cw, sy, cw, sh)
        Lb, Hb, T = 1.15, 0.24, 0.035
        R = Matrix.Rotation(az + rnd.uniform(-0.05, 0.05), 3, 'Z') @ Matrix.Rotation(rnd.uniform(-0.06, 0.06), 3, 'Y')
        o = V((0, 0, z))
        x0, x1 = 0.02, Lb
        # front (-y) face with text: left->right = v 0->1, top->bottom = u 0->1
        def P(x, y, zz):
            return o + R @ V((x, y, zz))
        f = [P(x0, -0.07, -Hb / 2), P(x1, -0.07, -Hb / 2), P(x1, -0.07, Hb / 2), P(x0, -0.07, Hb / 2)]
        mb.quad(f, [A(rect, 1, 0), A(rect, 1, 1), A(rect, 0, 1), A(rect, 0, 0)], OPQ)
        b = [P(x1, -0.07 + T, -Hb / 2), P(x0, -0.07 + T, -Hb / 2), P(x0, -0.07 + T, Hb / 2), P(x1, -0.07 + T, Hb / 2)]
        mb.quad(b, [A('wood_grey', 0, 0), A('wood_grey', 0, 1), A('wood_grey', 0.25, 1), A('wood_grey', 0.25, 0)], OPQ)
        # edges
        for (p0, p1, p2, p3) in ((f[3], f[2], b[0], b[3]) if False else (f[2], f[3], b[2], b[3]),):
            pass
        top = [f[3], f[2], b[3], b[2]]
        mb.quad([f[3], f[2], b[3], b[2]], [A('wood_grey', 0, 0), A('wood_grey', 0, 1), A('wood_grey', 0.05, 1), A('wood_grey', 0.05, 0)], OPQ)
        mb.quad([f[1], f[0], b[1], b[0]], [A('wood_grey', 0, 0), A('wood_grey', 0, 1), A('wood_grey', 0.05, 1), A('wood_grey', 0.05, 0)], OPQ)
        mb.quad([f[0], f[3], b[2], b[1]], [A('wood_grey', 0, 0), A('wood_grey', 0.05, 0), A('wood_grey', 0.05, 0.1), A('wood_grey', 0, 0.1)], OPQ)
        mb.quad([f[2], f[1], b[0], b[3]], [A('wood_grey', 0, 0), A('wood_grey', 0.05, 0), A('wood_grey', 0.05, 0.1), A('wood_grey', 0, 0.1)], OPQ)
    # small rock pile at base
    ob = finish(mb, name + '_p', sharp=40, ao=dict(rays=12, max_dist=0.4))
    rocks = []
    for i in range(4):
        a = i * 1.7
        s = rnd.uniform(0.18, 0.28)
        st = make_rock(name + '_s%d' % i, (s * 1.2, s, s * 0.8), seed + 5 + i, 'rock_granite', 1.0, subdiv=2, planes=3, amp=0.15, target=50, sink=0.2)
        st.location = V((math.cos(a) * 0.2, math.sin(a) * 0.2, 0))
        rocks.append(st)
    return join_objects(name, [ob] + rocks)


def water_trough(name, seed=91):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    Lx, Wy, H, t = 2.0, 0.62, 0.55, 0.05
    z0 = 0.1
    # outer walls (planks run along X)
    C.box(mb, A, 'planks', V((0, -Wy / 2 + t / 2, z0 + H / 2)), (Lx, t, H), mat=OPQ, tile=(0.9, 2.0), rnd=rnd, grain_axis=0)
    C.box(mb, A, 'planks', V((0, Wy / 2 - t / 2, z0 + H / 2)), (Lx, t, H), mat=OPQ, tile=(0.9, 2.0), rnd=rnd, grain_axis=0)
    for x in (-1, 1):
        C.box(mb, A, 'planks', V((x * (Lx / 2 - t / 2), 0, z0 + H / 2)), (t, Wy - 2 * t, H), mat=OPQ, tile=(0.9, 1.0), rnd=rnd, grain_axis=1)
    C.box(mb, A, 'planks', V((0, 0, z0 + t / 2)), (Lx - 2 * t, Wy - 2 * t, t), mat=OPQ, tile=(0.9, 2.0), rnd=rnd, grain_axis=0)
    # legs / skids
    for x in (-0.8, 0.8):
        C.box(mb, A, 'wood_brown', V((x, 0, z0 / 2)), (0.12, Wy + 0.1, z0 + 0.02), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    # iron bands
    for x in (-0.55, 0.55):
        C.box(mb, A, 'metal_rust', V((x, 0, z0 + H / 2)), (0.05, Wy + 0.012, H + 0.012), mat=OPQ, tile=(1, 1), rnd=rnd, skip=('-z',))
    # murky water surface
    wz = z0 + H * 0.78
    w = [V((-Lx / 2 + t, -Wy / 2 + t, wz)), V((Lx / 2 - t, -Wy / 2 + t, wz)), V((Lx / 2 - t, Wy / 2 - t, wz)), V((-Lx / 2 + t, Wy / 2 - t, wz))]
    mb.quad(w, [A('metal_rust', 0.1, 0.1), A('metal_rust', 0.9, 0.1), A('metal_rust', 0.9, 0.3), A('metal_rust', 0.1, 0.3)], OPQ, tag='water')

    def tint(co, n):
        if abs(co.z - wz) < 1e-3 and n.z > 0.9 and abs(co.x) < Lx / 2 - t + 1e-3 and abs(co.y) < Wy / 2 - t + 1e-3:
            return (0.28, 0.42, 0.40)
        return (1, 1, 1)
    return finish(mb, name, sharp=40, ao=dict(rays=14, max_dist=0.5), tint=tint)


def windmill(name, seed=101):
    rnd = random.Random(seed)
    mb = C.MeshBuilder()
    Ht = 8.0
    b0, b1 = 1.3, 0.35  # half-width at base / top
    legs = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p0 = V((sx * b0, sy * b0, -0.2))
        p1 = V((sx * b1, sy * b1, Ht))
        legs.append((p0, p1))
        C.tube(mb, A, 'wood_grey', [p0, p1], [0.08, 0.06], 4, 3.0, OPQ, seed=len(legs))
    lvl = [0.4, 2.8, 5.2, 7.6]

    def at(i, z):
        p0, p1 = legs[i]
        t = (z + 0.2) / (Ht + 0.2)
        return p0.lerp(p1, t)
    for z in lvl:
        for i in range(4):
            a, b = at(i, z), at((i + 1) % 4, z)
            C.tube(mb, A, 'wood_grey', [a, b], [0.04, 0.04], 4, 3.0, OPQ, cap_end=False)
    for k in range(len(lvl) - 1):
        for i in range(4):
            a, b = at(i, lvl[k]), at((i + 1) % 4, lvl[k + 1])
            C.tube(mb, A, 'wood_brown', [a, b], [0.03, 0.03], 4, 3.0, OPQ, cap_end=False)
            a, b = at((i + 1) % 4, lvl[k]), at(i, lvl[k + 1])
            C.tube(mb, A, 'wood_brown', [a, b], [0.03, 0.03], 4, 3.0, OPQ, cap_end=False)
    # platform
    C.box(mb, A, 'planks', V((0, 0, Ht)), (1.2, 1.2, 0.08), mat=OPQ, tile=(1, 1), rnd=rnd, grain_axis=0)
    # pump rod / pipe
    C.tube(mb, A, 'metal_rust', [V((0, 0, 0)), V((0, 0, Ht + 0.3))], [0.03, 0.03], 5, 3.0, OPQ, cap_end=False)
    # head: gearbox + mast + tail vane
    hub = V((0, -0.55, Ht + 1.0))
    C.tube(mb, A, 'metal_rust', [V((0, 0, Ht)), V((0, 0, Ht + 0.95))], [0.09, 0.08], 6, 2.0, OPQ)
    C.box(mb, A, 'metal_rust', V((0, -0.2, Ht + 1.0)), (0.3, 0.6, 0.3), mat=OPQ, tile=(1, 1), rnd=rnd)
    C.box(mb, A, 'wood_grey', V((0, 0.9, Ht + 1.02)), (0.07, 1.9, 0.07), mat=OPQ, tile=(0.3, 1.0), rnd=rnd)
    vane = [V((0.0, 1.35, Ht + 0.72)), V((0.0, 2.15, Ht + 0.62)), V((0.0, 2.15, Ht + 1.55)), V((0.0, 1.35, Ht + 1.3))]
    C.box(mb, A, 'metal_rust', V((0, 1.75, Ht + 1.06)), (0.03, 0.85, 0.72), mat=OPQ, tile=(1, 1), rnd=rnd)
    ob = finish(mb, name, sharp=40, ao=dict(rays=12, max_dist=1.0))
    # fan as a separate child (origin at hub, spins about local Y in Blender = local Z in three.js)
    fb = C.MeshBuilder()
    nbl = 16
    Rf = 1.25
    for k in range(nbl):
        a = 2 * math.pi * k / nbl
        d = V((math.cos(a), 0, math.sin(a)))
        side = V((-math.sin(a), 0, math.cos(a)))
        twist = Matrix.Rotation(0.5, 3, d)
        r0, r1 = 0.3, Rf
        w0, w1 = 0.08, 0.17
        pts = [d * r0 - twist @ side * w0, d * r1 - twist @ side * w1, d * r1 + twist @ side * w1, d * r0 + twist @ side * w0]
        uvs = [A('metal_rust', 0.1, 0.1), A('metal_rust', 0.9, 0.1), A('metal_rust', 0.9, 0.4), A('metal_rust', 0.1, 0.4)]
        fb.quad(pts, uvs, OPQ)
        fb.quad([pts[3], pts[2], pts[1], pts[0]], uvs[::-1], OPQ)
    for rr in (0.55, Rf - 0.05):
        ring = [V((math.cos(2 * math.pi * s / 16), 0, math.sin(2 * math.pi * s / 16))) * rr for s in range(17)]
        C.tube(fb, A, 'metal_rust', ring, [0.02] * 17, 3, 3.0, OPQ, cap_end=False)
    C.tube(fb, A, 'metal_rust', [V((0, -0.12, 0)), V((0, 0.35, 0))], [0.1, 0.08], 6, 1.0, OPQ, cap_start=True)
    fan = finish(fb, 'Windmill_Fan', sharp=40, ao=dict(rays=8, max_dist=0.3, ground=False))
    fan.parent = ob
    fan.location = hub
    return ob


# ============================================================================ main
def build():
    C.reset_scene()
    subprocess.run(['python3', os.path.join(HERE, 'props_textures.py')], check=True)
    img = C.load_image(os.path.join(BUILD, 'props_atlas.jpg'))
    fimg = C.load_image(os.path.join(BUILD, 'props_foliage.png'))
    MATS['opq'] = C.make_material('Props_Atlas', img, roughness=0.92)
    MATS['fol'] = C.make_material('Props_Foliage', fimg, alpha_clip=0.4, roughness=0.85, double_sided=True)

    objs = []
    objs.append(pine_ponderosa('Pine_A', 1))
    objs.append(pine_lodgepole('Pine_B', 2))
    objs.append(pine_snow('Pine_Snow', 3))
    objs.append(dead_tree('DeadTree'))
    objs.append(saguaro('Saguaro'))
    objs.append(joshua('Joshua'))
    objs.append(sagebrush('Sagebrush'))
    objs.append(make_rock('Rock_A', (1.1, 0.95, 0.8), 101, 'rock_granite', 2.0, planes=5, amp=0.2, target=600))
    objs.append(make_rock('Rock_B', (1.9, 1.4, 1.3), 202, 'rock_sand', 2.5, planes=7, terr=0.22, amp=0.16, target=700, horiz_planes=True))
    objs.append(make_rock('Rock_C', (1.5, 1.1, 0.45), 303, 'rock_sand', 2.0, planes=4, amp=0.12, target=400, sink=0.2))
    objs.append(make_rock('Boulder_Big', (4.6, 3.6, 3.2), 404, 'rock_granite', 4.0, planes=8, amp=0.2, target=800))
    objs.append(make_rock('CliffChunk', (10.0, 5.5, 8.0), 505, 'rock_sand', 6.0, planes=10, terr=0.8, amp=0.2, target=1400,
                          horiz_planes=True, plane_depth=(0.55, 0.8), sink=0.05))
    objs.append(fence_rail('Fence_Rail'))
    objs.append(telegraph_pole('TelegraphPole'))
    objs.append(barrel('Barrel'))
    objs.append(crate('Crate'))
    objs.append(wagon_wreck('Wagon_Wreck'))
    objs.append(cow_skull('CowSkull'))
    objs.append(grave_cross('GraveCross'))
    objs.append(tumbleweed('Tumbleweed'))
    objs.append(signpost('Signpost'))
    objs.append(water_trough('WaterTrough'))
    objs.append(windmill('Windmill'))
    for o in objs:
        print('%-14s tris %5d' % (o.name, C.tri_count(o) + sum(C.tri_count(c) for c in o.children)))
    # save a .blend for inspection / previews
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'props.blend'))
    C.export_glb(OUT_GLB)
    C.verify_glb(OUT_GLB, CONTRACT)


if __name__ == '__main__':
    build()
