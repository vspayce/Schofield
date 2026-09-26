"""SCHOFIELD — build public/assets/models/town.glb (ghost-town kit)

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_town.py

Every building is a ROOT object with its origin at the FRONT-CENTRE of its footprint at
ground level; the street-facing side is -Y in Blender (+Z in three.js) and the footprint
extends toward +Y. One material (Town_Atlas: town_atlas.jpg × COLOR_0 vertex AO/grime).

Gunman spawn points are EMPTY children of each building, numbered uniquely across the
whole town so glTF/three.js names stay exact:  Spawn_Window_<n>, Spawn_Roof_<n>.
Empty origin = the gunman's FEET; identity rotation = facing the street (-Y Blender,
+Z three.js). Window spawns stand ~0.55 m inside an open/shot-out window whose interior
is a dark box (so the window never looks see-through-empty).
"""
import bpy, math, random, os, sys, subprocess, zlib
from mathutils import Vector, Matrix, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib
import bl_common as C
import atlas_layout as L
importlib.reload(C)
importlib.reload(L)
V = Vector

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_GLB = os.path.join(ROOT, 'public', 'assets', 'models', 'town.glb')
BUILD = os.path.join(HERE, '_build')
CONTRACT = ['Saloon', 'GeneralStore', 'Sheriff', 'Bank', 'Church', 'Hotel', 'Livery',
            'WaterTower', 'Gallows', 'Boardwalk', 'Shack']

T = C.AtlasUV(L.TOWN, L.TOWN_SIZE, inset=2.0)
TILE = {'siding_grey': (2.0, 3.0), 'siding_red': (2.0, 3.0), 'siding_ochre': (2.0, 3.0), 'clapboard': (2.0, 3.0),
        'shingle': (2.0, 2.0), 'tin': (2.0, 2.0), 'floor': (2.0, 2.0), 'brick': (2.0, 2.0), 'trim': (0.35, 3.0),
        'dark': (1.0, 2.0)}
MAT = {}
X, Y, Z = V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1))
SPAWN = {'Window': 0, 'Roof': 0}


def sign_rect(i):
    x, y, w, h = L.TOWN['signs']
    sh = h / len(L.TOWN_SIGNS)
    return (x, y + i * sh, w, sh)


# ============================================================================ primitives
def quad_facing(mb, pts, uvs, want, tag=None):
    gn = (pts[1] - pts[0]).cross(pts[3] - pts[0])
    if gn.dot(want) < 0:
        pts = [pts[1], pts[0], pts[3], pts[2]]
        uvs = [uvs[1], uvs[0], uvs[3], uvs[2]]
    return mb.quad(pts, uvs, 0, tag=tag)


# regions whose tiles get a random (board-aligned) u/v shift per tile column/row so
# peeling-paint patches never repeat identically along a wall
SHIFT = {'siding_grey': (11, 20), 'siding_red': (11, 20), 'siding_ochre': (11, 20), 'clapboard': (11, 20),
         'floor': (8, 13), 'tin': (24, 8)}


def panel(mb, o, ux, uy, w, h, rect, holes=(), top_fn=None, uoff=0.0, voff=0.0, tile=None):
    """Planar wall/roof grid. o = bottom-left seen from the front; normal = ux × uy.
    Cut at texture-tile boundaries and hole edges; cells inside holes are skipped.
    top_fn(x) optionally clips the top (gables); breakpoints must include its kinks."""
    tu, tv = tile or TILE[rect]
    xs = {0.0, w}
    k = 1
    while k * tu - uoff < w - 1e-4:
        if k * tu - uoff > 1e-4:
            xs.add(k * tu - uoff)
        k += 1
    zs = {0.0, h}
    k = 1
    while k * tv - voff < h - 1e-4:
        if k * tv - voff > 1e-4:
            zs.add(k * tv - voff)
        k += 1
    for (hx, hz, hw, hh) in holes:
        xs.update([hx, hx + hw])
        zs.update([hz, hz + hh])
    if top_fn is not None and hasattr(top_fn, 'kinks'):
        xs.update([x for x in top_fn.kinks if 0 < x < w])
    # per-column / per-row random shifts (quantised to board / lap spacing)
    shu, shv = {}, {}
    if rect in SHIFT:
        qu, qv = SHIFT[rect]
        hs = zlib.crc32(repr((round(o.x, 2), round(o.y, 2), round(o.z, 2), rect)).encode())
        rr = random.Random(hs)
        for ku in range(-1, int(w / tu) + 3):
            shu[ku] = rr.randrange(qu) / qu
            xw = ku * tu - uoff + (1 - shu[ku]) * tu   # where the shifted u wraps
            if shu[ku] > 0 and 1e-4 < xw < w - 1e-4:
                xs.add(xw)
        for kv in range(-1, int(h / tv) + 3):
            shv[kv] = rr.randrange(qv) / qv
            zw = kv * tv - voff + (1 - shv[kv]) * tv
            if shv[kv] > 0 and 1e-4 < zw < h - 1e-4:
                zs.add(zw)
    xs = sorted(x for x in xs if -1e-6 <= x <= w + 1e-6)
    zs = sorted(z for z in zs if -1e-6 <= z <= h + 1e-6)
    cache = {}

    def P(x, z):
        key = (round(x, 5), round(z, 5))
        if key not in cache:
            cache[key] = mb.v(o + ux * x + uy * z)
        return cache[key]
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            x0, x1, z0, z1 = xs[i], xs[i + 1], zs[j], zs[j + 1]
            cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
            if any(hx - 1e-6 <= cx <= hx + hw + 1e-6 and hz - 1e-6 <= cz <= hz + hh + 1e-6 for (hx, hz, hw, hh) in holes):
                continue
            ku = math.floor((cx + uoff) / tu)
            kv = math.floor((cz + voff) / tv)
            corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
            if top_fn is not None:
                if z0 >= top_fn(x0) - 1e-4 and z0 >= top_fn(x1) - 1e-4:
                    continue
                corners = [(x, min(z, top_fn(x))) for (x, z) in corners]
            ids = [P(x, z) for (x, z) in corners]
            su, sv = shu.get(ku, 0.0), shv.get(kv, 0.0)
            cu = (cx + uoff) / tu - ku + su
            cv = (cz + voff) / tv - kv + sv
            wu, wv = math.floor(cu), math.floor(cv)
            uvs = [T(rect, min(1, max(0, (x + uoff) / tu - ku + su - wu)), min(1, max(0, (z + voff) / tv - kv + sv - wv))) for (x, z) in corners]
            # drop degenerate tops
            if top_fn is not None and abs(corners[3][1] - corners[0][1]) < 1e-4 and abs(corners[2][1] - corners[1][1]) < 1e-4:
                continue
            if top_fn is not None and abs(corners[3][1] - corners[0][1]) < 1e-4:
                mb.face([ids[0], ids[1], ids[2]], [uvs[0], uvs[1], uvs[2]], 0)
            elif top_fn is not None and abs(corners[2][1] - corners[1][1]) < 1e-4:
                mb.face([ids[0], ids[1], ids[3]], [uvs[0], uvs[1], uvs[3]], 0)
            else:
                mb.face(ids, uvs, 0)


def frame_R(ux, n):
    """Rotation whose local X = ux, local Y = -n (into the wall), local Z = up-in-plane."""
    uy = (-n).cross(ux) * -1
    uy = n.cross(ux)
    return Matrix((ux, -n, uy)).transposed()


def tbox(mb, center, size, R=None, rect='trim', tile=None, skip=(), faces_rect=None, seed=0):
    return C.box(mb, T, rect, center, size, rot=R, mat=0, tile=tile or TILE.get(rect, (1, 1)),
                 rnd=random.Random(seed), skip=skip, faces_rect=faces_rect)


def full_quad(mb, pts, rect, want):
    uvs = [T(rect, 0, 0), T(rect, 1, 0), T(rect, 1, 1), T(rect, 0, 1)]
    return quad_facing(mb, pts, uvs, want)


class Wall:
    def __init__(self, o, ux, h, w, rect, uy=Z):
        self.o, self.ux, self.uy, self.h, self.w, self.rect = V(o), V(ux), V(uy), h, w, rect
        self.n = self.ux.cross(self.uy).normalized()
        self.ops = []

    def P(self, x, z, d=0.0):
        return self.o + self.ux * x + self.uy * z + self.n * d


def opening(mb, wall, x, z, w, h, kind, floor_z=None, depth=0.12, casing=True, spawn_parent=None, spawns=None, seed=0):
    """Cut record + reveal + pane/interior + casing. kind: glass|broken|boarded|open|door|saloon|barn|dark."""
    wall.ops.append((x, z, w, h))
    n, ux, uy = wall.n, wall.ux, wall.uy
    P = wall.P
    rev = 'trim'
    # reveals (sill up, head down, jambs inward)
    for (a, b, want) in (((x, z), (x + w, z), uy), ((x, z + h), (x + w, z + h), -uy), ((x, z), (x, z + h), ux), ((x + w, z), (x + w, z + h), -ux)):
        pts = [P(*a), P(*b), P(*b, d=-depth), P(*a, d=-depth)]
        uvs = [T(rev, 0, 0), T(rev, 0, 0.3), T(rev, 0.3, 0.3), T(rev, 0.3, 0)]
        quad_facing(mb, pts, uvs, want)
    pane_rect = {'glass': 'win_glass', 'broken': 'win_broken', 'boarded': 'win_boarded', 'door': 'door_panel',
                 'barn': 'door_barn', 'open': None, 'saloon': 'door_saloon', 'dark': None}[kind]
    if pane_rect:
        full_quad(mb, [P(x, z, -depth), P(x + w, z, -depth), P(x + w, z + h, -depth), P(x, z + h, -depth)], pane_rect, n)
    if kind in ('open', 'saloon', 'dark'):
        # interior darkness box behind the hole
        fz = floor_z if floor_z is not None else z
        m = 0.45
        D = 1.4
        bx0, bx1, bz0, bz1 = x - m, x + w + m, fz, z + h + 0.35
        d0, d1 = -depth, -depth - D
        inner = [
            ([P(bx0, bz0, d1), P(bx1, bz0, d1), P(bx1, bz1, d1), P(bx0, bz1, d1)], n),          # back
            ([P(bx0, bz0, d0), P(bx0, bz0, d1), P(bx0, bz1, d1), P(bx0, bz1, d0)], ux),         # left side
            ([P(bx1, bz0, d1), P(bx1, bz0, d0), P(bx1, bz1, d0), P(bx1, bz1, d1)], -ux),
            ([P(bx0, bz1, d0), P(bx0, bz1, d1), P(bx1, bz1, d1), P(bx1, bz1, d0)], -uy),        # ceiling
            ([P(bx0, bz0, d1), P(bx0, bz0, d0), P(bx1, bz0, d0), P(bx1, bz0, d1)], uy),         # floor
        ]
        for pts, want in inner:
            full_quad(mb, pts, 'dark', want)
        # inner face of the wall around the hole (so the hole has thickness from inside)
        for (a0, a1, b0, b1) in ((bx0, x, bz0, bz1), (x + w, bx1, bz0, bz1), (x, x + w, bz0, z), (x, x + w, z + h, bz1)):
            if a1 - a0 > 1e-3 and b1 - b0 > 1e-3:
                full_quad(mb, [P(a0, b0, d0), P(a1, b0, d0), P(a1, b1, d0), P(a0, b1, d0)], 'dark', -n)
        if kind == 'saloon':
            # batwing doors
            R = frame_R(ux, n)
            for sx in (0, 1):
                cx = x + w * (0.25 + 0.5 * sx)
                c = P(cx, z + 0.55 + 0.5, -depth - 0.05)
                tbox(mb, c, (w * 0.46, 0.04, 1.0), R, rect='door_saloon', tile=(1, 1),
                     faces_rect={'-y': ('full', (L.TOWN['door_saloon'][0] + L.TOWN['door_saloon'][2] * 0.5 * sx, L.TOWN['door_saloon'][1] + 72, L.TOWN['door_saloon'][2] * 0.5, 112)),
                                 '+y': ('full', (L.TOWN['door_saloon'][0], L.TOWN['door_saloon'][1] + 72, L.TOWN['door_saloon'][2] * 0.5, 112))})
    if casing:
        R = frame_R(ux, n)
        cw = 0.12
        tbox(mb, P(x + w / 2, z + h + cw / 2 + 0.02, 0.03), (w + 2 * cw + 0.12, 0.07, cw + 0.04), R, seed=seed)
        tbox(mb, P(x + w / 2, z + h + cw + 0.1, 0.07), (w + 2 * cw + 0.26, 0.14, 0.06), R, seed=seed + 1)  # drip cap
        if kind not in ('door', 'saloon', 'barn', 'dark'):
            tbox(mb, P(x + w / 2, z - 0.04, 0.05), (w + 2 * cw + 0.1, 0.12, 0.07), R, seed=seed + 2)  # sill
        for sx in (-1, 1):
            xx = x - cw / 2 if sx < 0 else x + w + cw / 2
            tbox(mb, P(xx, z + h / 2, 0.025), (cw, 0.05, h + 0.04), R, seed=seed + 3)
    if kind == 'open' and spawns is not None:
        fz = floor_z if floor_z is not None else z - 1.0
        spawns.append(('Window', P(x + w / 2, fz, -depth - 0.55)))


def build_wall(mb, wall, uoff=0.0, top_fn=None):
    panel(mb, wall.o, wall.ux, wall.uy, wall.w, wall.h, wall.rect, holes=wall.ops, top_fn=top_fn, uoff=uoff)


def slab(mb, a, b, c, d, rect, thick=0.08, under='trim', tile=None, edges=True):
    """Roof/awning slab: a,b = lower (eave) edge left->right, d,c = upper edge. Top faces up."""
    ux = (b - a)
    w = ux.length
    ux.normalize()
    uy = (d - a)
    h = uy.length
    uy.normalize()
    nrm = ux.cross(uy)
    if nrm.z < 0:
        a, b, c, d = b, a, d, c
        ux = -ux
        nrm = ux.cross(uy)
    panel(mb, a, ux, uy, w, h, rect, tile=tile)
    off = -nrm * thick
    panel(mb, b + off, -ux, uy, w, h, under, tile=(2.0, 2.0) if under != 'trim' else (0.35 * 4, 3.0))
    if edges:
        # eave fascia and rakes
        for (p, q) in ((a, b), (b, c), (c, d), (d, a)):
            e = q - p
            L_ = e.length
            out = e.normalized().cross(nrm)
            pts = [p, q, q + off, p + off]
            uvs = [T('trim', 0, 0), T('trim', 0, min(1, L_ / 3)), T('trim', 0.25, min(1, L_ / 3)), T('trim', 0.25, 0)]
            quad_facing(mb, pts, uvs, -out if (p - (a + c) / 2).dot(-out) > 0 else out)


def post(mb, base, top, s=0.16, seed=0):
    c = (base + top) / 2
    tbox(mb, c, (s, s, (top - base).length), seed=seed)


def sign_board(mb, center, width, height, idx, ux=X, n=-Y):
    R = frame_R(ux, n)
    tbox(mb, center, (width, 0.08, height), R, faces_rect={'-y': ('full', sign_rect(idx))})


def porch(mb, W, P, deck_z=0.4, awning_h=(3.5, 3.0), roof='tin', posts=None, deck=True, awning=True, seed=0, rail=False):
    """Boardwalk porch in front of a facade at y=P spanning x in [-W/2, W/2]."""
    if deck:
        panel(mb, V((-W / 2, 0, deck_z)), X, Y, W, P, 'floor', tile=(2.0, 2.0))
        tbox(mb, V((0, 0.04, deck_z / 2)), (W, 0.08, deck_z), rect='trim', tile=(3.0, 0.35), seed=seed)   # fascia
        for sx in (-1, 1):
            tbox(mb, V((sx * (W / 2 - 0.04), P / 2, deck_z / 2)), (0.08, P, deck_z), seed=seed + 1)
        # step
        tbox(mb, V((0, -0.35, deck_z * 0.45)), (2.4, 0.7, deck_z * 0.9), rect='floor', tile=(2, 2), seed=seed + 2)
    xs = posts or [-W / 2 + 0.25, -W / 6, W / 6, W / 2 - 0.25]
    if awning:
        hw, hf = awning_h
        for x in xs:
            post(mb, V((x, 0.25, deck_z)), V((x, 0.25, hf - 0.05)), seed=seed + 3)
        tbox(mb, V((0, 0.25, hf - 0.1)), (W, 0.16, 0.2), seed=seed + 4)  # beam
        slab(mb, V((-W / 2 - 0.1, -0.25, hf)), V((W / 2 + 0.1, -0.25, hf)), V((W / 2 + 0.1, P, hw)), V((-W / 2 - 0.1, P, hw)), roof)
        # little brackets
        for x in xs:
            tbox(mb, V((x, 0.45, hf - 0.35)), (0.08, 0.5, 0.08), R=Matrix.Rotation(-0.7, 3, 'X'), seed=seed)
    if rail:
        for x in xs:
            pass


def railing(mb, a, b, z0, h=1.0, spacing=0.28, seed=0):
    d = b - a
    L_ = d.length
    ux = d.normalized()
    n = ux.cross(Z)
    R = frame_R(ux, n)
    tbox(mb, (a + b) / 2 + Z * (z0 + h), (L_, 0.1, 0.08), R, seed=seed)
    tbox(mb, (a + b) / 2 + Z * (z0 + 0.12), (L_, 0.06, 0.06), R, seed=seed + 1)
    k = int(L_ / spacing)
    for i in range(1, k):
        p = a + d * (i / k)
        tbox(mb, p + Z * (z0 + h / 2 + 0.06), (0.05, 0.05, h - 0.1), R, seed=seed + i)


def tint_fn_for(W, D, seed):
    def fn(co, n):
        g = min(1.0, max(0.0, co.z / 0.9))
        k = 0.72 + 0.28 * g
        nz = noise.noise(co * 0.35 + V((seed, 0, 0)))
        k *= 0.95 + 0.07 * nz
        dust = 0.05 * max(0.0, n.z)
        return (k * 1.0 + dust, k * 0.97 + dust, k * 0.93 + dust * 0.8)
    return fn


def finalize(mb, name, spawns, W=10, D=10, seed=0):
    ob = mb.build(name, [MAT['town']], sharp_angle=30)
    C.bake_vertex_colors(ob, rays=12, max_dist=1.6, strength=0.85, tint_fn=tint_fn_for(W, D, seed), seed=seed)
    for kind, p in spawns:
        SPAWN[kind] += 1
        C.empty('Spawn_%s_%d' % (kind, SPAWN[kind]), p, parent=ob, size=0.4)
    return ob


# ============================================================================ false-front building
def western(name, W, D, P, floors, wall_top, front_top, front_rect, side_rect, roof_kind, roof_rect,
            front_open, side_open=(), sign=None, balcony=False, awning=(3.6, 3.1), awning_roof='tin',
            roof_spawns=(), ridge=None, seed=0, deck_z=0.4, porch_on=True, extra=None):
    mb = C.MeshBuilder()
    spawns = []
    x0, y0 = -W / 2, P
    # --- walls
    front = Wall((x0, y0, 0), X, front_top, W, front_rect)
    right = Wall((W / 2, y0, 0), Y, wall_top, D, side_rect)
    back = Wall((W / 2, y0 + D, 0), -X, wall_top, W, side_rect)
    left = Wall((x0, y0 + D, 0), -Y, wall_top, D, side_rect)
    for (x, z, w, h, kind, fz) in front_open:
        opening(mb, front, x + W / 2, z, w, h, kind, floor_z=fz, spawns=spawns, seed=seed)
    for (wall_i, x, z, w, h, kind) in side_open:
        wall = (right, left)[wall_i]
        opening(mb, wall, x, z, w, h, kind, spawns=spawns, seed=seed)
    build_wall(mb, front)
    if roof_kind == 'gable':
        # side walls straight; gable end walls are hidden (front) / built on the back
        top = lambda x, W=W, rg=ridge, wt=wall_top: wt + (rg - wt) * (1 - abs(x - W / 2) / (W / 2))
        top.kinks = [W / 2]
        back.h = ridge
        build_wall(mb, back, top_fn=top)
    else:
        build_wall(mb, back)
    build_wall(mb, right)
    build_wall(mb, left)
    # false-front side returns (thin) and cornice
    ff_depth = 0.25
    if front_top > wall_top + 0.1:
        for sx in (-1, 1):
            wx = sx * W / 2
            o = V((wx, y0, wall_top)) if sx > 0 else V((wx, y0 + ff_depth, wall_top))
            ux = Y if sx > 0 else -Y
            panel(mb, o, ux, Z, ff_depth, front_top - wall_top, side_rect, voff=wall_top % 3.0)
        # back of the false front
        panel(mb, V((W / 2, y0 + ff_depth, wall_top)), -X, Z, W, front_top - wall_top, side_rect, voff=wall_top % 3.0)
        tbox(mb, V((0, y0 + ff_depth / 2, front_top + 0.04)), (W + 0.1, ff_depth + 0.1, 0.08), seed=seed)
    # cornice
    tbox(mb, V((0, y0 - 0.1, front_top - 0.12)), (W + 0.5, 0.3, 0.24), seed=seed + 1)
    tbox(mb, V((0, y0 - 0.05, front_top - 0.38)), (W + 0.3, 0.14, 0.12), seed=seed + 2)
    for i in range(int(W / 1.2) + 1):
        bx = -W / 2 + 0.15 + i * (W - 0.3) / int(W / 1.2)
        tbox(mb, V((bx, y0 - 0.1, front_top - 0.36)), (0.1, 0.2, 0.3), seed=seed + 3)
    # corner boards
    for sx in (-1, 1):
        tbox(mb, V((sx * (W / 2 + 0.02), y0 - 0.02, front_top / 2)), (0.16, 0.08, front_top), seed=seed + 4)
        tbox(mb, V((sx * (W / 2 + 0.02), y0 + D, wall_top / 2)), (0.12, 0.12, wall_top), seed=seed + 5)
    # foundation skirt
    tbox(mb, V((0, y0 - 0.03, 0.2)), (W + 0.04, 0.06, 0.4), rect='trim', tile=(3.0, 0.35), seed=seed + 6)
    # --- roof
    if roof_kind == 'flat':
        rz = wall_top + 0.02
        slab(mb, V((-W / 2 - 0.05, y0 + D + 0.3, rz - 0.25)), V((W / 2 + 0.05, y0 + D + 0.3, rz - 0.25)),
             V((W / 2 + 0.05, y0 + ff_depth, rz)), V((-W / 2 - 0.05, y0 + ff_depth, rz)), roof_rect)
    else:
        e = 0.35
        for sx in (-1, 1):
            a = V((sx * (W / 2 + e), y0 + ff_depth, wall_top - e * 0.4))
            b = V((sx * (W / 2 + e), y0 + D + e, wall_top - e * 0.4))
            c = V((0, y0 + D + e, ridge))
            d = V((0, y0 + ff_depth, ridge))
            slab(mb, a, b, c, d, roof_rect)
        tbox(mb, V((0, y0 + D / 2, ridge + 0.05)), (0.2, D + 0.5, 0.12), seed=seed)
    # --- porch / balcony
    if porch_on:
        if balcony:
            bz = floors[1]
            porch(mb, W, P, deck_z=deck_z, awning=False, seed=seed)
            xs = [-W / 2 + 0.25, -W / 6, W / 6, W / 2 - 0.25]
            for x in xs:
                post(mb, V((x, 0.25, deck_z)), V((x, 0.25, awning[0] + 2.6)), seed=seed)
            # balcony deck (thick) + railing
            tbox(mb, V((0, P / 2, bz - 0.12)), (W + 0.1, P + 0.1, 0.24), rect='trim', tile=(3.0, 0.35), seed=seed)
            panel(mb, V((-W / 2, 0, bz)), X, Y, W, P, 'floor')
            panel(mb, V((W / 2, 0, bz - 0.24)), -X, Y, W, P, 'floor')
            railing(mb, V((-W / 2, 0.1, 0)), V((W / 2, 0.1, 0)), bz, seed=seed)
            for sx in (-1, 1):
                railing(mb, V((sx * W / 2, 0.1, 0)), V((sx * W / 2, P, 0)), bz, seed=seed + 9)
            hf, hw = bz + 2.6, bz + 3.1
            tbox(mb, V((0, 0.25, hf - 0.1)), (W, 0.16, 0.2), seed=seed + 4)
            slab(mb, V((-W / 2 - 0.1, -0.25, hf)), V((W / 2 + 0.1, -0.25, hf)), V((W / 2 + 0.1, P, hw)), V((-W / 2 - 0.1, P, hw)), awning_roof)
        else:
            porch(mb, W, P, deck_z=deck_z, awning_h=awning or (3.5, 3.0), roof=awning_roof, seed=seed, awning=awning is not None)
    if sign is not None:
        idx, cz, sw, sh = sign
        sign_board(mb, V((0, y0 - 0.06, cz)), sw, sh, idx)
    if extra:
        extra(mb, spawns)
    for p in roof_spawns:
        spawns.append(('Roof', V(p)))
    return finalize(mb, name, spawns, W, D, seed)


# ============================================================================ buildings
def saloon():
    W, D, P = 10.0, 13.0, 2.6
    f0, f1 = 0.4, 3.9
    fo = [(-4.1, 1.1, 1.6, 1.9, 'glass', f0), (-0.8, f0, 1.6, 2.5, 'saloon', f0), (2.5, 1.1, 1.6, 1.9, 'broken', f0),
          (-3.9, f1 + 0.8, 1.1, 1.7, 'open', f1), (-0.55, f1, 1.1, 2.3, 'open', f1), (2.8, f1 + 0.8, 1.1, 1.7, 'open', f1)]
    so = [(0, 3.5, 1.2, 1.1, 1.7, 'boarded'), (0, 8.0, 1.2, 1.1, 1.7, 'glass'), (0, 5.5, 4.7, 1.1, 1.6, 'broken'),
          (1, 3.0, 1.2, 1.1, 1.7, 'broken'), (1, 7.5, 4.7, 1.1, 1.6, 'boarded')]
    return western('Saloon', W, D, P, [f0, f1], 7.3, 8.55, 'siding_ochre', 'siding_grey', 'flat', 'tin', fo, so,
                   sign=(0, 7.75, 7.2, 0.9), balcony=True, awning_roof='tin',
                   roof_spawns=[(-2.6, 1.3, f1 + 0.02), (2.2, 1.3, f1 + 0.02), (-1.5, P + 0.9, 7.33)], seed=11)


def general_store():
    W, D, P = 9.0, 12.0, 2.6
    fo = [(-4.0, 0.95, 2.1, 1.9, 'glass', 0.4), (-0.6, 0.4, 1.2, 2.4, 'door', 0.4), (1.9, 0.95, 2.1, 1.9, 'open', 0.4)]
    so = [(0, 4.0, 1.3, 1.1, 1.5, 'broken'), (1, 6.0, 1.3, 1.1, 1.5, 'boarded')]
    return western('GeneralStore', W, D, P, [0.4], 4.3, 7.3, 'siding_red', 'siding_grey', 'gable', 'shingle', fo, so,
                   sign=(1, 5.2, 7.4, 0.92), ridge=6.2, awning=(3.7, 3.2), awning_roof='tin',
                   roof_spawns=[(0.0, P + 0.8, 6.2), (-2.5, 1.2, 3.5)], seed=21)


def sheriff():
    W, D, P = 7.6, 10.0, 2.4

    def bars(mb, spawns):
        # iron bars over the jail window (left)
        for i in range(5):
            x = -3.0 + 0.2 + i * 0.26
            tbox(mb, V((x, P - 0.06, 1.95)), (0.035, 0.035, 1.5), rect='iron', tile=(1, 1))
    fo = [(-3.0, 1.2, 1.2, 1.5, 'glass', 0.4), (-0.9, 0.4, 1.1, 2.3, 'door', 0.4), (1.5, 1.1, 1.3, 1.7, 'open', 0.4)]
    so = [(0, 5.0, 1.4, 1.0, 1.0, 'boarded'), (1, 5.0, 1.4, 1.0, 1.0, 'broken')]
    return western('Sheriff', W, D, P, [0.4], 4.0, 5.25, 'siding_grey', 'siding_grey', 'flat', 'tin', fo, so,
                   sign=(2, 4.55, 5.6, 0.72), awning=(3.45, 3.05), awning_roof='shingle',
                   roof_spawns=[(0.8, P + 0.8, 4.03)], extra=bars, seed=31)


def bank():
    W, D, P = 8.0, 11.0, 1.2
    f1 = 3.7
    fo = [(-3.3, 0.9, 1.1, 2.2, 'glass', 0.4), (-0.7, 0.4, 1.4, 2.6, 'door', 0.4), (2.2, 0.9, 1.1, 2.2, 'broken', 0.4),
          (-3.3, f1 + 0.7, 1.1, 1.8, 'open', f1), (-0.55, f1 + 0.7, 1.1, 1.8, 'broken', f1), (2.2, f1 + 0.7, 1.1, 1.8, 'open', f1)]
    so = [(0, 3.0, 1.2, 1.0, 1.8, 'boarded'), (1, 7.0, 4.5, 1.0, 1.6, 'broken')]
    return western('Bank', W, D, P, [0.4, f1], 7.0, 8.25, 'brick', 'siding_grey', 'flat', 'tin', fo, so,
                   sign=(3, 3.3, 4.2, 0.55), awning=None, porch_on=True, deck_z=0.3,
                   roof_spawns=[(-1.8, P + 0.8, 7.03)], seed=41,
                   extra=lambda mb, sp: _bank_extra(mb, W, P))


def _bank_extra(mb, W, P):
    pass


def hotel():
    W, D, P = 12.0, 12.0, 2.6
    f = [0.4, 3.7, 6.9]
    fo = [(-5.2, 1.1, 1.2, 1.8, 'glass', f[0]), (-2.9, 1.1, 1.2, 1.8, 'broken', f[0]), (-0.7, f[0], 1.4, 2.5, 'door', f[0]),
          (1.7, 1.1, 1.2, 1.8, 'boarded', f[0]), (4.0, 1.1, 1.2, 1.8, 'glass', f[0])]
    kinds = [['glass', 'open', 'broken', 'boarded'], ['open', 'glass', 'boarded', 'open']]
    for fi, fz in enumerate(f[1:]):
        for wi, x in enumerate((-5.0, -2.2, 1.1, 3.9)):
            fo.append((x, fz + 0.75, 1.1, 1.8, kinds[fi][wi], fz))
    so = []
    for fz in f:
        so += [(0, 3.5, fz + 0.75, 1.0, 1.7, 'glass' if fz < 3 else 'broken'), (0, 8.0, fz + 0.75, 1.0, 1.7, 'boarded'),
               (1, 4.0, fz + 0.75, 1.0, 1.7, 'broken'), (1, 8.5, fz + 0.75, 1.0, 1.7, 'glass')]
    return western('Hotel', W, D, P, f, 10.1, 11.3, 'clapboard', 'clapboard', 'flat', 'tin', fo, so,
                   sign=(4, 10.55, 6.0, 0.75), awning=(3.45, 3.05), awning_roof='shingle',
                   roof_spawns=[(-3.0, P + 0.8, 10.13), (3.0, P + 0.8, 10.13), (-4.5, 1.2, 3.35)], seed=51)


def church():
    mb = C.MeshBuilder()
    spawns = []
    W, D, y0 = 8.0, 14.0, 1.4
    wall_h, ridge = 5.0, 8.4
    tw, ty0, th = 2.8, 0.0, 9.2  # tower
    # nave walls
    front = Wall((-W / 2, y0, 0), X, ridge, W, 'clapboard')
    back = Wall((W / 2, y0 + D, 0), -X, ridge, W, 'clapboard')
    right = Wall((W / 2, y0, 0), Y, wall_h, D, 'clapboard')
    left = Wall((-W / 2, y0 + D, 0), -Y, wall_h, D, 'clapboard')
    for wall in (right, left):
        for i in range(3):
            opening(mb, wall, 3.0 + i * 4.0, 1.4, 1.0, 2.5, ['glass', 'broken', 'boarded'][(i + (wall is left)) % 3], seed=i)
    top = lambda x: wall_h + (ridge - wall_h) * (1 - abs(x - W / 2) / (W / 2))
    top.kinks = [W / 2]
    build_wall(mb, front, top_fn=top)
    build_wall(mb, back, top_fn=top)
    build_wall(mb, right)
    build_wall(mb, left)
    e = 0.4
    for sx in (-1, 1):
        a = V((sx * (W / 2 + e), y0 - e, wall_h - e * 0.8))
        b = V((sx * (W / 2 + e), y0 + D + e, wall_h - e * 0.8))
        c = V((0, y0 + D + e, ridge + 0.05))
        d = V((0, y0 - e, ridge + 0.05))
        slab(mb, a, b, c, d, 'shingle')
    # tower
    tf = Wall((-tw / 2, ty0, 0), X, th, tw, 'clapboard')
    tr = Wall((tw / 2, ty0, 0), Y, th, y0 + 0.01, 'clapboard')
    tl = Wall((-tw / 2, y0 + 0.01, 0), -Y, th, y0 + 0.01, 'clapboard')
    opening(mb, tf, 0.7, 0.3, 1.4, 2.6, 'door', seed=3)
    opening(mb, tf, 0.85, 5.0, 1.1, 1.5, 'open', floor_z=4.2, spawns=spawns, seed=4)
    build_wall(mb, tf)
    build_wall(mb, tr)
    build_wall(mb, tl)
    # tower walls above the nave ridge (sides & back) to close it
    tb = Wall((tw / 2, ty0 + tw, 0), -X, th, tw, 'clapboard')
    panel(mb, V((tw / 2, ty0 + tw, ridge - 0.6)), -X, Z, tw, th - ridge + 0.6, 'clapboard', voff=(ridge - 0.6) % 3)
    panel(mb, V((tw / 2, 0, ridge - 0.6)), Y, Z, tw, th - ridge + 0.6, 'clapboard', voff=(ridge - 0.6) % 3)
    panel(mb, V((-tw / 2, tw, ridge - 0.6)), -Y, Z, tw, th - ridge + 0.6, 'clapboard', voff=(ridge - 0.6) % 3)
    # belfry: floor, corner posts, rails, eaves, spire, cross
    bz = th
    tbox(mb, V((0, tw / 2, bz + 0.05)), (tw + 0.3, tw + 0.3, 0.14), seed=5)
    for sx in (-1, 1):
        for sy in (0, 1):
            post(mb, V((sx * (tw / 2 - 0.1), 0.1 + sy * (tw - 0.2), bz)), V((sx * (tw / 2 - 0.1), 0.1 + sy * (tw - 0.2), bz + 2.2)), s=0.2)
    for (a, b) in ((V((-tw / 2, 0.05, 0)), V((tw / 2, 0.05, 0))), (V((tw / 2, 0, 0)), V((tw / 2, tw, 0))), (V((tw / 2, tw, 0)), V((-tw / 2, tw, 0))), (V((-tw / 2, tw, 0)), V((-tw / 2, 0, 0)))):
        railing(mb, a, b, bz, h=0.8, spacing=0.3)
    # bell
    C.tube(mb, T, 'iron', [V((0, tw / 2, bz + 0.9)), V((0, tw / 2, bz + 1.5)), V((0, tw / 2, bz + 1.75))], [0.42, 0.3, 0.12], 10, 1.0, 0, cap_end=True)
    tbox(mb, V((0, tw / 2, bz + 2.2)), (tw, 0.18, 0.18), seed=6)
    sz = bz + 2.25
    tbox(mb, V((0, tw / 2, sz + 0.05)), (tw + 0.5, tw + 0.5, 0.12), seed=7)
    apex = V((0, tw / 2, sz + 5.2))
    corners = [V((-tw / 2 - 0.2, -0.2, sz + 0.1)), V((tw / 2 + 0.2, -0.2, sz + 0.1)), V((tw / 2 + 0.2, tw + 0.2, sz + 0.1)), V((-tw / 2 - 0.2, tw + 0.2, sz + 0.1))]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        mid = (a + b) / 2
        want = (mid - V((0, tw / 2, mid.z))).normalized() + Z * 0.2
        pts = [a, b, apex]
        uvs = [T('shingle', 0, 0), T('shingle', 1, 0), T('shingle', 0.5, 1)]
        gn = (b - a).cross(apex - a)
        if gn.dot(want) < 0:
            pts, uvs = [b, a, apex], [uvs[1], uvs[0], uvs[2]]
        mb.face([mb.v(p) for p in pts], uvs, 0)
    tbox(mb, apex + Z * 0.7, (0.1, 0.1, 1.5), seed=8)
    tbox(mb, apex + Z * 1.05, (0.7, 0.1, 0.1), seed=9)
    # steps
    for i in range(3):
        tbox(mb, V((0, -0.3 - i * 0.3 + 0.3, 0.1 + i * 0.0)), (2.4 - i * 0.2, 0.35, 0.2 + i * 0.0), rect='floor', tile=(2, 2), seed=i)
    tbox(mb, V((0, -0.2, 0.1)), (2.6, 0.5, 0.2), rect='floor', tile=(2, 2), seed=10)
    # corner boards
    for sx in (-1, 1):
        tbox(mb, V((sx * (W / 2 + 0.02), y0, wall_h / 2)), (0.14, 0.14, wall_h), seed=11)
        tbox(mb, V((sx * (tw / 2 + 0.02), 0.0, th / 2)), (0.14, 0.14, th), seed=12)
    spawns.append(('Roof', V((0.0, tw / 2 - 0.4, bz + 0.12))))
    return finalize(mb, 'Church', spawns, W, D, 61)


def livery():
    mb = C.MeshBuilder()
    spawns = []
    W, D = 12.0, 15.0
    eave, knee_x, knee_z, ridge = 4.5, 4.1, 7.3, 8.9

    def prof(x):  # x in [0, W] along the gable wall
        xc = abs(x - W / 2)
        if xc >= knee_x:
            return eave + (knee_z - eave) * (W / 2 - xc) / (W / 2 - knee_x)
        return knee_z + (ridge - knee_z) * (knee_x - xc) / knee_x
    prof.kinks = [W / 2 - knee_x, W / 2, W / 2 + knee_x]
    front = Wall((-W / 2, 0, 0), X, ridge, W, 'siding_grey')
    back = Wall((W / 2, D, 0), -X, ridge, W, 'siding_grey')
    right = Wall((W / 2, 0, 0), Y, eave, D, 'siding_red')
    left = Wall((-W / 2, D, 0), -Y, eave, D, 'siding_red')
    # big doorway: right leaf closed, left leaf swung open onto darkness
    dw, dh = 3.4, 3.6
    opening(mb, front, W / 2 - dw / 2, 0.0, dw, dh, 'dark', floor_z=0.0, casing=True, seed=1)
    R = frame_R(X, -Y)
    tbox(mb, V((dw / 4, -0.06, dh / 2)), (dw / 2, 0.08, dh), R, faces_rect={'-y': ('full', 'door_barn'), '+y': ('full', 'door_barn')})
    Ro = Matrix.Rotation(math.radians(-110), 3, 'Z')
    hinge = V((-dw / 2, -0.06, 0))
    ctr = hinge + Ro @ V((dw / 4, 0, 0)) + Z * dh / 2
    tbox(mb, ctr, (dw / 2, 0.08, dh), Ro, faces_rect={'-y': ('full', 'door_barn'), '+y': ('full', 'door_barn')})
    opening(mb, front, W / 2 - 0.8, 5.0, 1.6, 1.6, 'open', floor_z=4.7, spawns=spawns, seed=2)
    for wall in (right, left):
        for i in range(3):
            opening(mb, wall, 2.5 + i * 5.0, 1.8, 0.9, 0.9, ['boarded', 'broken', 'open'][i] if wall is right else ['broken', 'boarded', 'glass'][i], seed=i + 5)
    # side windows marked 'open' are dark holes (no spawn: pass no spawns list)
    build_wall(mb, front, top_fn=prof)
    build_wall(mb, back, top_fn=prof)
    build_wall(mb, right)
    build_wall(mb, left)
    e = 0.4
    for sx in (-1, 1):
        a = V((sx * (W / 2 + e), -e, eave - e * 0.7))
        b = V((sx * (W / 2 + e), D + e, eave - e * 0.7))
        c = V((sx * knee_x, D + e, knee_z))
        d = V((sx * knee_x, -e, knee_z))
        slab(mb, a, b, c, d, 'tin')
        a2 = V((sx * knee_x, -e, knee_z))
        b2 = V((sx * knee_x, D + e, knee_z))
        c2 = V((0, D + e, ridge))
        d2 = V((0, -e, ridge))
        slab(mb, a2, b2, c2, d2, 'tin')
    # hay hood + hoist beam with rope & pulley
    tbox(mb, V((0, -0.9, ridge - 0.35)), (0.22, 2.2, 0.22), seed=3)
    C.tube(mb, T, 'rope', [V((0, -1.8, ridge - 0.5)), V((0, -1.8, 5.2))], [0.025, 0.025], 5, 1.0, 0)
    C.tube(mb, T, 'iron', [V((-0.06, -1.8, ridge - 0.5)), V((0.06, -1.8, ridge - 0.5))], [0.12, 0.12], 8, 1.0, 0, cap_end=True, cap_start=True)
    sign_board(mb, V((0, -0.08, dh + 0.55)), 4.2, 0.55, 5)
    for sx in (-1, 1):
        tbox(mb, V((sx * (W / 2 + 0.02), 0, eave / 2)), (0.16, 0.16, eave), seed=4)
    # hitching rail
    for x in (-5.2, -3.2):
        post(mb, V((x, -1.6, 0)), V((x, -1.6, 1.1)), s=0.14)
    tbox(mb, V((-4.2, -1.6, 1.05)), (2.3, 0.1, 0.1), seed=6)
    return finalize(mb, 'Livery', spawns, W, D, 71)


def water_tower():
    mb = C.MeshBuilder()
    spawns = []
    cx, cy = 0.0, 2.6
    H = 6.0
    legs = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        b = V((cx + sx * 2.0, cy + sy * 2.0, 0))
        t = V((cx + sx * 1.6, cy + sy * 1.6, H))
        legs.append((b, t))
        d = t - b
        R = C.frame_from_dir(d)
        Rm = Matrix((R[0], R[1], R[2])).transposed()
        tbox(mb, (b + t) / 2, (0.26, 0.26, d.length), Rm, seed=len(legs))

    def at(i, z):
        b, t = legs[i]
        return b.lerp(t, z / H)
    for z in (0.5, 3.0, 5.6):
        for i in range(4):
            a, b = at(i, z), at((i + 1) % 4, z)
            ux = (b - a).normalized()
            tbox(mb, (a + b) / 2, ((b - a).length + 0.2, 0.12, 0.2), frame_R(ux, ux.cross(Z)), seed=i)
    for (z0, z1) in ((0.5, 3.0), (3.0, 5.6)):
        for i in range(4):
            for (p, q) in ((at(i, z0), at((i + 1) % 4, z1)), (at((i + 1) % 4, z0), at(i, z1))):
                d = q - p
                Rf = C.frame_from_dir(d)
                tbox(mb, (p + q) / 2, (0.08, 0.14, d.length), Matrix((Rf[0], Rf[1], Rf[2])).transposed(), seed=i)
    # deck / catwalk
    tbox(mb, V((cx, cy, H + 0.08)), (5.2, 5.2, 0.16), rect='floor', tile=(2, 2), faces_rect={'+z': ('full', 'floor')})
    for (a, b) in ((V((-2.6, 0.0, 0)), V((2.6, 0.0, 0))), (V((2.6, 0, 0)), V((2.6, 5.2, 0))), (V((-2.6, 5.2, 0)), V((-2.6, 0, 0)))):
        railing(mb, a, b, H + 0.16, h=0.9, spacing=0.9)
    # tank
    zt0, zt1, R = H + 0.2, H + 3.6, 2.15
    C.tube(mb, T, 'siding_grey', [V((cx, cy, zt0)), V((cx, cy, zt1))], [R, R], 24, 3.6, 0, u_repeat=6, cap_end=False, smooth=True)
    for zb in (zt0 + 0.4, zt0 + 1.5, zt0 + 2.6, zt1 - 0.25):
        C.tube(mb, T, 'iron', [V((cx, cy, zb - 0.04)), V((cx, cy, zb + 0.04))], [R + 0.03, R + 0.03], 24, 1.0, 0, cap_end=False, smooth=True)
    # conical roof
    apex = V((cx, cy, zt1 + 1.5))
    rr = R + 0.35
    ring = [mb.v(V((cx + math.cos(2 * math.pi * k / 16) * rr, cy + math.sin(2 * math.pi * k / 16) * rr, zt1 - 0.1))) for k in range(16)]
    a_ = mb.v(apex)
    for k in range(16):
        k2 = (k + 1) % 16
        mb.face([ring[k], ring[k2], a_], [T('shingle', k / 16, 0), T('shingle', (k + 1) / 16, 0), T('shingle', (k + 0.5) / 16, 1)], 0)
    ringi = [mb.v(V((cx + math.cos(2 * math.pi * k / 16) * rr, cy + math.sin(2 * math.pi * k / 16) * rr, zt1 - 0.2))) for k in range(16)]
    ci = mb.v(V((cx, cy, zt1 - 0.2)))
    for k in range(16):
        k2 = (k + 1) % 16
        mb.face([ringi[k2], ringi[k], ci], [T('dark', 0, 0), T('dark', 1, 0), T('dark', 0.5, 1)], 0)
        mb.face([ring[k], ringi[k], ringi[k2], ring[k2]], [T('trim', 0, 0), T('trim', 0, 0.1), T('trim', 0.2, 0.1), T('trim', 0.2, 0)], 0)
    # spout + ladder
    C.tube(mb, T, 'iron', [V((cx + 1.4, cy - 1.7, zt0 + 0.3)), V((cx + 1.8, cy - 2.6, zt0 - 0.4)), V((cx + 1.8, cy - 3.1, zt0 - 1.6))], [0.12, 0.12, 0.1], 8, 2.0, 0)
    for sx in (-0.25, 0.25):
        tbox(mb, V((cx + sx - 0.6, -0.1, H / 2)), (0.07, 0.07, H + 0.2), seed=1)
    for i in range(1, 20):
        tbox(mb, V((cx - 0.6, -0.1, i * 0.3)), (0.5, 0.05, 0.05), seed=i)
    spawns.append(('Roof', V((cx + 0.6, 0.6, H + 0.16))))
    return finalize(mb, 'WaterTower', spawns, 5, 5, 81)


def gallows():
    mb = C.MeshBuilder()
    spawns = []
    Wg, Dg, Hg = 3.6, 3.0, 2.6
    for sx in (-1, 1):
        for sy in (0, 1):
            post(mb, V((sx * (Wg / 2 - 0.12), 0.12 + sy * (Dg - 0.24), 0)), V((sx * (Wg / 2 - 0.12), 0.12 + sy * (Dg - 0.24), Hg)), s=0.22)
    tbox(mb, V((0, Dg / 2, Hg - 0.08)), (Wg + 0.1, Dg + 0.1, 0.16), rect='trim', tile=(3.0, 0.35))
    panel(mb, V((-Wg / 2, 0, Hg + 0.001)), X, Y, Wg, Dg, 'floor')
    # trapdoor outline
    tbox(mb, V((0.3, Dg / 2, Hg + 0.01)), (1.0, 1.0, 0.02), rect='dark', tile=(1, 1), faces_rect={'+z': ('full', 'trim')})
    # skirt boards on three sides
    panel(mb, V((-Wg / 2, 0, 0.3)), X, Z, Wg, Hg - 0.45, 'siding_grey')
    # braces
    for sx in (-1, 1):
        tbox(mb, V((sx * (Wg / 2 - 0.12), Dg / 2, Hg * 0.5)), (0.1, Dg * 1.2, 0.14), Matrix.Rotation(0.75, 3, 'X'))
    # stairs (+X side)
    n = 9
    for i in range(n):
        z = (i + 1) * Hg / (n + 1)
        tbox(mb, V((Wg / 2 + 0.35 + (n - i) * 0.26, Dg / 2, z)), (0.3, 1.0, 0.06), rect='floor', tile=(2, 2), seed=i)
    for sy in (-1, 1):
        a = V((Wg / 2 + 0.35 + n * 0.26 + 0.3, Dg / 2 + sy * 0.52, 0))
        b = V((Wg / 2 + 0.2, Dg / 2 + sy * 0.52, Hg))
        d = b - a
        Rf = C.frame_from_dir(d)
        tbox(mb, (a + b) / 2, (0.06, 0.25, d.length), Matrix((Rf[0], Rf[1], Rf[2])).transposed(), seed=sy)
    # railing on back
    railing(mb, V((-Wg / 2, Dg - 0.1, 0)), V((Wg / 2, Dg - 0.1, 0)), Hg, h=0.95, spacing=0.4)
    # beam
    for sx in (-1, 1):
        post(mb, V((sx * 1.2, Dg / 2 + 0.6, Hg)), V((sx * 1.2, Dg / 2 + 0.6, Hg + 3.2)), s=0.22)
        tbox(mb, V((sx * 0.9, Dg / 2 + 0.6, Hg + 2.8)), (0.7, 0.1, 0.1), Matrix.Rotation(sx * -0.8, 3, 'Y'))
    tbox(mb, V((0, Dg / 2 + 0.6, Hg + 3.3)), (3.0, 0.24, 0.24))
    # noose
    top = V((0.3, Dg / 2 + 0.6, Hg + 3.18))
    C.tube(mb, T, 'rope', [top, top - Z * 1.0], [0.025, 0.025], 5, 1.0, 0, cap_end=False)
    ring = [top - Z * 1.25 + V((math.sin(a) * 0.17, 0, math.cos(a) * 0.22)) for a in [2 * math.pi * k / 10 for k in range(11)]]
    C.tube(mb, T, 'rope', ring, [0.028] * 11, 5, 1.0, 0, cap_end=False)
    tbox(mb, top - Z * 1.02, (0.07, 0.07, 0.16), rect='rope', tile=(1, 1))
    spawns.append(('Roof', V((-0.8, 1.2, Hg + 0.02))))
    return finalize(mb, 'Gallows', spawns, Wg, Dg, 91)


def boardwalk():
    mb = C.MeshBuilder()
    W, P, dz = 6.0, 2.4, 0.4
    panel(mb, V((-W / 2, 0, dz)), X, Y, W, P, 'floor')
    tbox(mb, V((0, 0.04, dz / 2)), (W, 0.08, dz), rect='trim', tile=(3.0, 0.35))
    tbox(mb, V((0, P - 0.04, dz / 2)), (W, 0.08, dz), rect='trim', tile=(3.0, 0.35))
    for x in (-2.0, 0.0, 2.0):
        tbox(mb, V((x, P / 2, dz / 2 - 0.02)), (0.12, P - 0.2, dz - 0.04), seed=1)
    for x in (-1.5, 1.5):
        post(mb, V((x, 0.25, dz)), V((x, 0.25, 3.05)))
    tbox(mb, V((0, 0.25, 3.0)), (W, 0.16, 0.2))
    slab(mb, V((-W / 2, -0.25, 3.1)), V((W / 2, -0.25, 3.1)), V((W / 2, P, 3.55)), V((-W / 2, P, 3.55)), 'tin')
    # hitching rail at the street edge
    for x in (-2.6, -0.6):
        post(mb, V((x, -0.6, 0)), V((x, -0.6, 1.1)), s=0.13)
    tbox(mb, V((-1.6, -0.6, 1.05)), (2.3, 0.1, 0.1))
    return finalize(mb, 'Boardwalk', [], W, P, 101)


def shack():
    mb = C.MeshBuilder()
    spawns = []
    W, D = 4.6, 4.0
    wall_h, ridge = 2.6, 3.5
    front = Wall((-W / 2, 0, 0), X, wall_h, W, 'siding_grey')
    back = Wall((W / 2, D, 0), -X, wall_h, W, 'siding_grey')
    right = Wall((W / 2, 0, 0), Y, ridge, D, 'siding_grey')
    left = Wall((-W / 2, D, 0), -Y, ridge, D, 'siding_grey')
    opening(mb, front, 0.5, 0.0, 0.95, 2.1, 'dark', floor_z=0.0, seed=1)   # door hangs open
    opening(mb, front, 2.6, 1.0, 1.0, 0.95, 'open', floor_z=0.05, spawns=spawns, seed=2)
    opening(mb, right, 2.2, 0.9, 0.35, 1.3, 'dark', floor_z=0.0, casing=False)      # missing boards
    opening(mb, left, 1.2, 1.0, 0.9, 0.8, 'boarded')
    top = lambda x: wall_h + (ridge - wall_h) * (1 - abs(x - D / 2) / (D / 2))
    top.kinks = [D / 2]
    build_wall(mb, front)
    build_wall(mb, back)
    build_wall(mb, right, top_fn=top)
    build_wall(mb, left, top_fn=top)
    Ro = Matrix.Rotation(math.radians(-70), 3, 'Z')
    hinge = V((-W / 2 + 0.5, -0.04, 0))
    tbox(mb, hinge + Ro @ V((0.47, 0, 0)) + Z * 1.05, (0.95, 0.05, 2.1), Ro, faces_rect={'-y': ('full', 'door_panel'), '+y': ('full', 'door_panel')})
    e = 0.3
    for sy in (0, 1):
        a = V((-W / 2 - e, -e if sy == 0 else D + e, wall_h - 0.2))
        b = V((W / 2 + e, -e if sy == 0 else D + e, wall_h - 0.2))
        c = V((W / 2 + e, D / 2, ridge))
        d = V((-W / 2 - e, D / 2, ridge))
        slab(mb, a, b, c, d, 'tin')
    C.tube(mb, T, 'iron', [V((1.2, D * 0.7, 2.8)), V((1.2, D * 0.7, 4.4)), V((1.25, D * 0.7, 4.5))], [0.09, 0.09, 0.09], 8, 2.0, 0, cap_end=False)
    for sx in (-1, 1):
        tbox(mb, V((sx * (W / 2 + 0.02), 0, wall_h / 2)), (0.12, 0.12, wall_h), seed=4)
    # the whole shack sags a little
    Rl = Matrix.Rotation(0.03, 4, 'Y') @ Matrix.Rotation(-0.015, 4, 'X')
    mb.verts = [Rl @ v for v in mb.verts]
    spawns = [(k, Rl @ p) for (k, p) in spawns]
    return finalize(mb, 'Shack', spawns, W, D, 111)


def build():
    C.reset_scene()
    subprocess.run(['python3', os.path.join(HERE, 'town_textures.py')], check=True)
    img = C.load_image(os.path.join(BUILD, 'town_atlas.jpg'))
    MAT['town'] = C.make_material('Town_Atlas', img, roughness=0.9)
    objs = [saloon(), general_store(), sheriff(), bank(), church(), hotel(), livery(), water_tower(), gallows(), boardwalk(), shack()]
    for o in objs:
        print('%-14s tris %5d  spawns %s' % (o.name, C.tri_count(o), [c.name for c in o.children]))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, 'town.blend'))
    C.export_glb(OUT_GLB)
    C.verify_glb(OUT_GLB, CONTRACT)


if __name__ == '__main__':
    build()
