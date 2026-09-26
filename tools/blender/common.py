"""Shared helpers for SCHOFIELD character builds (Blender 5.2, run headless).

Modelling: characters are described as signed-distance fields made of simple
primitives (ellipsoids, round cones) blended with smooth-min, polygonised with
surface nets in numpy, then decimated to budget in Blender.  The same primitive
list later drives texture colouring (which part is nearest), SDF ambient
occlusion for the baked texture, and skin weights (primitive -> bones).

Animation: poses are given as rotations in the *armature rest frame* per bone
(relative to the parent) or as world-space deltas.  Everything is converted to
pose-bone basis quaternions and written straight into slotted actions.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "public", "assets", "models")
PREVIEWS = os.path.join(os.path.dirname(__file__), "previews")
FPS = 60


# ----------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.unit_settings.system = "METRIC"
    return sc


def set_active(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


# ----------------------------------------------------------------------------
# SDF primitives
# ----------------------------------------------------------------------------
def _v(a):
    return np.asarray(a, dtype=np.float64)


class Prim:
    """One SDF primitive.

    kind: 'ell' (center c, radii r) or 'cone' (a, b, ra, rb) or 'box' (c, half h, round rr)
    k:    smooth-union radius used when blending it in
    label: material/colour label
    bones: list of bone names this primitive skins to (weights split by distance
           to the bone segments)
    scale: optional anisotropic scale (sx, sy, sz) about the primitive centre,
           applied in world axes (e.g. squash a cone laterally)
    rot:  optional 3x3 rotation (world->local) about the centre (ellipsoids/boxes)
    sub:  subtract instead of union
    """

    def __init__(self, kind, label, bones, k=0.03, scale=None, rot=None, sub=False, **kw):
        self.kind = kind
        self.label = label
        self.bones = list(bones)
        self.k = k
        self.sub = sub
        self.scale = None if scale is None else _v(scale)
        self.rot = None if rot is None else np.asarray(rot, dtype=np.float64)
        for key, val in kw.items():
            setattr(self, key, _v(val) if isinstance(val, (list, tuple, np.ndarray)) else val)
        if kind == "ell":
            self.center = self.c
        elif kind == "cone":
            self.center = (self.a + self.b) * 0.5
        elif kind == "box":
            self.center = self.c
        elif kind == "fn":
            self.center = (self.lo + self.hi) * 0.5

    # bounding box (world) with margin
    def bbox(self, margin):
        if self.kind == "ell":
            r = float(np.max(self.r))
            ext = np.array([r, r, r])
            if self.scale is not None:
                ext = ext * np.maximum(self.scale, 1.0)
            lo, hi = self.c - ext, self.c + ext
        elif self.kind == "cone":
            r = max(self.ra, self.rb)
            lo = np.minimum(self.a, self.b) - r
            hi = np.maximum(self.a, self.b) + r
            if self.scale is not None:
                c = self.center
                s = np.maximum(self.scale, 1.0)
                lo = c + (lo - c) * s
                hi = c + (hi - c) * s
        elif self.kind == "fn":
            lo, hi = self.lo, self.hi
        else:
            e = float(np.linalg.norm(self.h)) + self.rr
            lo, hi = self.c - e, self.c + e
        return lo - margin, hi + margin

    def dist(self, p):
        """p: (N,3) -> (N,) signed distance (approximate for scaled prims)."""
        smin = 1.0
        if self.scale is not None:
            p = self.center + (p - self.center) / self.scale
            smin = float(np.min(self.scale))
        if self.kind == "ell":
            q = p - self.c
            if self.rot is not None:
                q = q @ self.rot.T
            r = self.r
            k0 = np.linalg.norm(q / r, axis=1)
            k1 = np.linalg.norm(q / (r * r), axis=1)
            d = k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
        elif self.kind == "cone":
            d = round_cone(p, self.a, self.b, self.ra, self.rb)
        elif self.kind == "fn":
            d = self.fn(p)
        else:
            q = p - self.c
            if self.rot is not None:
                q = q @ self.rot.T
            q = np.abs(q) - (self.h - self.rr)
            d = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(np.max(q, axis=1), 0.0) - self.rr
        return d * smin

    def seg(self):
        """Axis segment used for bone-weight splitting."""
        if self.kind == "cone":
            return self.a, self.b
        return self.center, self.center


def ell(c, r, label, bones, **kw):
    return Prim("ell", label, bones, c=c, r=r, **kw)


def cone(a, b, ra, rb, label, bones, **kw):
    return Prim("cone", label, bones, a=a, b=b, ra=float(ra), rb=float(rb), **kw)


def fnprim(fn, lo, hi, label, bones, **kw):
    return Prim("fn", label, bones, fn=fn, lo=lo, hi=hi, **kw)


def box(c, h, rr, label, bones, **kw):
    return Prim("box", label, bones, c=c, h=h, rr=float(rr), **kw)


def round_cone(p, a, b, r1, r2):
    """Inigo Quilez's exact round-cone SDF, vectorised."""
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - np.outer(y, ba)
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
    d1 = np.sqrt(x2 + z2) * il2 - r2
    d2 = np.sqrt(x2 + y2) * il2 - r1
    out = np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))
    return out


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def eval_sdf(prims, p):
    d = np.full(len(p), 10.0)
    for pr in prims:
        dp = pr.dist(p)
        d = smax(d, -dp, pr.k) if pr.sub else smin(d, dp, pr.k)
    return d


def sdf_grid(prims, lo, hi, h):
    """Evaluate SDF on a regular grid with per-primitive bbox culling."""
    lo = _v(lo)
    hi = _v(hi)
    n = np.ceil((hi - lo) / h).astype(int) + 1
    xs = [lo[i] + np.arange(n[i]) * h for i in range(3)]
    F = np.full(tuple(n), 1.0, dtype=np.float64)
    for pr in prims:
        margin = pr.k + 2 * h
        blo, bhi = pr.bbox(margin)
        i0 = np.clip(np.floor((blo - lo) / h).astype(int), 0, n - 1)
        i1 = np.clip(np.ceil((bhi - lo) / h).astype(int) + 1, 0, n)
        if np.any(i1 <= i0):
            continue
        gx, gy, gz = np.meshgrid(xs[0][i0[0]:i1[0]], xs[1][i0[1]:i1[1]], xs[2][i0[2]:i1[2]], indexing="ij")
        pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
        dp = pr.dist(pts).reshape(gx.shape)
        blk = F[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]]
        if pr.sub:
            blk[...] = smax(blk, -dp, pr.k)
        else:
            blk[...] = smin(blk, dp, pr.k)
    return F, lo, n


def surface_nets(F, lo, h):
    """Naive surface nets. Returns verts (V,3), quads (Q,4) with outward normals."""
    inside = F < 0.0
    nx, ny, nz = F.shape
    cell_shape = (nx - 1, ny - 1, nz - 1)
    acc = np.zeros(cell_shape + (3,))
    cnt = np.zeros(cell_shape)
    faces = []
    for axis in range(3):
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[axis] = slice(0, -1)
        sl1[axis] = slice(1, None)
        f0 = F[tuple(sl0)]
        f1 = F[tuple(sl1)]
        ch = inside[tuple(sl0)] != inside[tuple(sl1)]
        idx = np.argwhere(ch)  # edge start grid index
        if len(idx) == 0:
            continue
        a = f0[ch]
        b = f1[ch]
        t = a / (a - b)
        pos = lo + idx * h
        pos[:, axis] += t * h
        # the edge belongs to up to 4 cells: vary the other two axes by -1/0
        o1, o2 = [ax for ax in range(3) if ax != axis]
        for d1 in (0, -1):
            for d2 in (0, -1):
                c = idx.copy()
                c[:, o1] += d1
                c[:, o2] += d2
                ok = np.all((c >= 0) & (c < np.array(cell_shape)), axis=1)
                cc = c[ok]
                np.add.at(acc, (cc[:, 0], cc[:, 1], cc[:, 2]), pos[ok])
                np.add.at(cnt, (cc[:, 0], cc[:, 1], cc[:, 2]), 1)
        # quads: only interior edges
        ok = np.all(idx[:, [o1, o2]] >= 1, axis=1) & (idx[:, o1] < cell_shape[o1]) & (idx[:, o2] < cell_shape[o2])
        e = idx[ok]
        flip = inside[tuple(sl0)][ch][ok]  # inside at lower end -> normal +axis
        def cell(d1, d2):
            c = e.copy()
            c[:, o1] += d1
            c[:, o2] += d2
            return c
        q = [cell(-1, -1), cell(0, -1), cell(0, 0), cell(-1, 0)]
        faces.append((q, flip, axis))
    active = cnt > 0
    vid = -np.ones(cell_shape, dtype=np.int64)
    vid[active] = np.arange(int(active.sum()))
    verts = acc[active] / cnt[active][:, None]
    quads = []
    for q, flip, axis in faces:
        ids = np.stack([vid[c[:, 0], c[:, 1], c[:, 2]] for c in q], axis=1)
        # orientation: for axis x the order (y,z) CCW seen from +x is correct when
        # inside is at the low end. o1,o2 are ordered cyclically only for x and z.
        if axis == 1:
            ids = ids[:, ::-1]
        ids = np.where(flip[:, None], ids, ids[:, ::-1])
        quads.append(ids)
    quads = np.concatenate(quads)
    quads = quads[np.all(quads >= 0, axis=1)]
    return verts, quads


def mesh_from_arrays(name, verts, faces, collection=None):
    me = bpy.data.meshes.new(name)
    faces = np.asarray(faces)
    nv = len(verts)
    me.vertices.add(nv)
    me.vertices.foreach_set("co", np.asarray(verts, dtype=np.float32).ravel())
    nf = len(faces)
    fs = faces.shape[1]
    me.loops.add(nf * fs)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", (np.arange(nf) * fs).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(nf, fs, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def build_sdf_mesh(name, prims, h, target_tris, pad=0.06, smooth_iters=2, lo=None, hi=None):
    if lo is None or hi is None:
        los, his = zip(*[p.bbox(0) for p in prims if not p.sub])
        lo = np.min(los, axis=0) - pad
        hi = np.max(his, axis=0) + pad
    F, lo, n = sdf_grid(prims, lo, hi, h)
    verts, quads = surface_nets(F, lo, h)
    ob = mesh_from_arrays(name, verts, quads)
    set_active(ob)
    if smooth_iters:
        m = ob.modifiers.new("sm", "SMOOTH")
        m.factor = 0.5
        m.iterations = smooth_iters
        bpy.ops.object.modifier_apply(modifier=m.name)
    ntri = len(quads) * 2
    m = ob.modifiers.new("dec", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = min(1.0, target_tris / ntri)
    m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=m.name)
    triangulate(ob)
    shade_smooth(ob)
    print(f"[sdf] {name}: grid {tuple(n)} -> {len(quads)} quads -> {len(ob.data.polygons)} tris")
    return ob


def triangulate(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data)
    bm.free()


def shade_smooth(ob):
    ob.data.polygons.foreach_set("use_smooth", np.ones(len(ob.data.polygons), dtype=bool))
    ob.data.update()


def verts_np(ob):
    co = np.empty(len(ob.data.vertices) * 3, dtype=np.float32)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ----------------------------------------------------------------------------
# lofted / lathed helper geometry (hats, straps)
# ----------------------------------------------------------------------------
def lathe(name, profile, segments=24, scale_xy=(1.0, 1.0), squash=None, close_top=True):
    """profile: list of (radius, z). Revolved about Z. squash(theta, r, z)->(dx,dy,dz) optional."""
    verts = []
    faces = []
    n = len(profile)
    for i in range(segments):
        th = 2 * math.pi * i / segments
        for j, (r, z) in enumerate(profile):
            x = r * math.cos(th) * scale_xy[0]
            y = r * math.sin(th) * scale_xy[1]
            if squash:
                dx, dy, dz = squash(th, r, z)
                x, y, z = x + dx, y + dy, z + dz
            verts.append((x, y, z))
    for i in range(segments):
        i2 = (i + 1) % segments
        for j in range(n - 1):
            faces.append((i * n + j, i2 * n + j, i2 * n + j + 1, i * n + j + 1))
    if close_top:
        c = len(verts)
        r, z = profile[-1]
        verts.append((0, 0, z + (squash(0, 0, z)[2] if squash else 0)))
        for i in range(segments):
            i2 = (i + 1) % segments
            faces.append((i * n + n - 1, i2 * n + n - 1, c))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def tube_along(name, pts, radius, sides=6, flat=None):
    """Simple tube along a polyline. radius scalar or per-point list. flat=(w,h) makes a strap."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rs = radius if isinstance(radius, (list, tuple)) else [radius] * n
    verts, faces = [], []
    prev_side = None
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        if prev_side is None:
            up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            side = t.cross(up).normalized()
        else:
            side = (prev_side - t * prev_side.dot(t)).normalized()
        prev_side = side
        up2 = side.cross(t).normalized()
        for s in range(sides):
            a = 2 * math.pi * s / sides
            if flat:
                off = side * math.cos(a) * flat[0] + up2 * math.sin(a) * flat[1]
            else:
                off = (side * math.cos(a) + up2 * math.sin(a)) * rs[i]
            verts.append(tuple(p + off))
    for i in range(n - 1):
        for s in range(sides):
            s2 = (s + 1) % sides
            faces.append((i * sides + s, i * sides + s2, (i + 1) * sides + s2, (i + 1) * sides + s))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def join(objs, name):
    set_active(objs[0])
    for o in objs:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


# ----------------------------------------------------------------------------
# UVs + baked textures (software rasteriser; colour is a function of 3D point)
# ----------------------------------------------------------------------------
def smart_uv(ob, margin=0.004, angle=66):
    set_active(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.6)
    bpy.ops.object.mode_set(mode="OBJECT")


def rasterise(ob, size, extra_vertex_attrs=None):
    """Rasterise triangles into UV space.

    Returns dict with 'P' (S,S,3) position, 'N' normals, 'mask', and interpolated
    extra per-vertex attrs.  Gutters are filled by dilation.
    """
    me = ob.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tri_loops = np.empty(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)
    tri_verts = np.empty(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tri_verts)
    tri_loops = tri_loops.reshape(-1, 3)
    tri_verts = tri_verts.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2).astype(np.float64)
    co = verts_np(ob)
    nrm = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3).astype(np.float64)
    attrs = {"P": co, "N": nrm}
    if extra_vertex_attrs:
        attrs.update(extra_vertex_attrs)
    out = {k: np.zeros((size, size, v.shape[1] if v.ndim > 1 else 1)) for k, v in attrs.items()}
    mask = np.zeros((size, size), dtype=bool)
    S = size
    for t in range(nt):
        tuv = uv[tri_loops[t]] * S - 0.5
        x0, y0 = np.floor(tuv.min(axis=0)).astype(int)
        x1, y1 = np.ceil(tuv.max(axis=0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, S - 1), min(y1, S - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        px = xs.ravel().astype(np.float64)
        py = ys.ravel().astype(np.float64)
        (ax, ay), (bx, by), (cx, cy) = tuv
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        l1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        l2 = 1 - l0 - l1
        eps = -0.02
        ins = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
        if not ins.any():
            continue
        L = np.stack([l0[ins], l1[ins], l2[ins]], axis=1)
        L = np.clip(L, 0, None)
        L /= L.sum(axis=1, keepdims=True)
        ix = px[ins].astype(int)
        iy = py[ins].astype(int)
        vi = tri_verts[t]
        for k, v in attrs.items():
            vv = v[vi] if v.ndim > 1 else v[vi][:, None]
            out[k][iy, ix] = L @ vv
        mask[iy, ix] = True
    out["N"] /= np.maximum(np.linalg.norm(out["N"], axis=2, keepdims=True), 1e-9)
    out["mask"] = mask
    return out


def dilate(img, mask, iters=8):
    img = img.copy()
    m = mask.copy()
    for _ in range(iters):
        acc = np.zeros_like(img)
        c = np.zeros(m.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sm = np.roll(np.roll(m, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sm[..., None]
            c += sm
        fill = (~m) & (c > 0)
        img[fill] = acc[fill] / c[fill][:, None]
        m = m | fill
    return img


def sdf_ao(prims, P, N, steps=5, dist=0.035, strength=1.0):
    """IQ-style SDF ambient occlusion evaluated at points P with normals N."""
    occ = np.zeros(len(P))
    sca = 1.0
    for i in range(1, steps + 1):
        hh = dist * i
        d = eval_sdf(prims, P + N * hh)
        occ += (hh - d) * sca
        sca *= 0.7
    return np.clip(1.0 - strength * occ / (dist * 3.0), 0.0, 1.0)


def label_weights(prims, P, labels, tau=0.012):
    """Soft nearest-primitive label weights: dict label -> (N,) in [0,1]."""
    D = np.stack([pr.dist(P) for pr in prims if not pr.sub], axis=1)
    lab = [pr.label for pr in prims if not pr.sub]
    dmin = D.min(axis=1, keepdims=True)
    W = np.exp(-(D - dmin) / tau)
    W /= W.sum(axis=1, keepdims=True)
    out = {l: np.zeros(len(P)) for l in labels}
    for j, l in enumerate(lab):
        if l in out:
            out[l] += W[:, j]
    return out


def value_noise3(P, scale, seed=0):
    """Cheap smooth 3D value noise in [0,1]."""
    rng = np.random.RandomState(seed)
    perm = rng.rand(4096)
    q = P * scale
    i = np.floor(q).astype(np.int64)
    f = q - i
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        return perm[(ix * 73856093 ^ iy * 19349663 ^ iz * 83492791) % 4096]

    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * h(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


def fbm(P, scale, octaves=3, seed=0):
    tot, amp, s, norm = 0, 1.0, scale, 0
    for o in range(octaves):
        tot = tot + amp * value_noise3(P, s, seed + o)
        norm += amp
        amp *= 0.5
        s *= 2.1
    return tot / norm


def bake_texture(ob, size, color_fn, name, extra_vertex_attrs=None):
    """color_fn(P, N, extra) -> (M,3) linear-ish sRGB in [0,1] for masked texels."""
    r = rasterise(ob, size, extra_vertex_attrs)
    m = r["mask"]
    P = r["P"][m]
    N = r["N"][m]
    extra = {k: v[m] for k, v in r.items() if k not in ("P", "N", "mask")}
    col = np.clip(color_fn(P, N, extra), 0, 1)
    img = np.zeros((size, size, 3))
    img[m] = col
    img = dilate(img, m, 10)
    return make_image(name, img)


def make_image(name, rgb):
    S = rgb.shape[0]
    im = bpy.data.images.new(name, S, S, alpha=False)
    px = np.ones((S, S, 4), dtype=np.float32)
    px[..., :3] = rgb
    im.pixels.foreach_set(px.ravel())
    im.file_format = "JPEG"
    im.pack()
    return im


def image_material(name, image, roughness=0.8, metallic=0.0, sheen=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def assign_material(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


# ----------------------------------------------------------------------------
# skinning
# ----------------------------------------------------------------------------
def seg_dist(P, a, b):
    ab = b - a
    l2 = float(ab @ ab)
    if l2 < 1e-12:
        return np.linalg.norm(P - a, axis=1)
    t = np.clip(((P - a) @ ab) / l2, 0, 1)
    return np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)


def compute_weights(ob, prims, bone_segs, tau=0.02, bone_pow=4.0, smooth_iters=3, max_inf=4, overrides=None):
    """Weights from nearest primitives, split between each primitive's bones by
    inverse distance to the bone segments.  bone_segs: name -> (head, tail) np.
    overrides(P, W, names) may edit the (V,B) weight matrix before smoothing."""
    P = verts_np(ob)
    names = list(bone_segs.keys())
    bidx = {n: i for i, n in enumerate(names)}
    V = len(P)
    B = len(names)
    use = [pr for pr in prims if not pr.sub and pr.bones]
    D = np.stack([pr.dist(P) for pr in use], axis=1)
    dmin = D.min(axis=1, keepdims=True)
    PW = np.exp(-(D - dmin) / tau)
    PW /= PW.sum(axis=1, keepdims=True)
    BD = np.stack([seg_dist(P, *bone_segs[n]) for n in names], axis=1) + 0.01
    W = np.zeros((V, B))
    for j, pr in enumerate(use):
        ids = [bidx[b] for b in pr.bones]
        if len(ids) == 1:
            W[:, ids[0]] += PW[:, j]
        else:
            inv = 1.0 / BD[:, ids] ** bone_pow
            inv /= inv.sum(axis=1, keepdims=True)
            W[:, ids] += PW[:, j:j + 1] * inv
    if overrides:
        W = overrides(P, W, names)
    # laplacian smoothing on mesh graph
    me = ob.data
    ed = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    for _ in range(smooth_iters):
        acc = np.zeros_like(W)
        cnt = np.zeros(V)
        np.add.at(acc, ed[:, 0], W[ed[:, 1]])
        np.add.at(acc, ed[:, 1], W[ed[:, 0]])
        np.add.at(cnt, ed[:, 0], 1)
        np.add.at(cnt, ed[:, 1], 1)
        W = 0.5 * W + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    apply_weights(ob, W, names, max_inf)
    return W, names


def apply_weights(ob, W, names, max_inf=4):
    V, B = W.shape
    order = np.argsort(-W, axis=1)[:, :max_inf]
    top = np.take_along_axis(W, order, axis=1)
    top[top < 0.02] = 0
    top /= np.maximum(top.sum(axis=1, keepdims=True), 1e-9)
    ob.vertex_groups.clear()
    groups = {n: ob.vertex_groups.new(name=n) for n in names}
    for v in range(V):
        for k in range(max_inf):
            w = float(top[v, k])
            if w > 0:
                groups[names[order[v, k]]].add([v], w, "REPLACE")


def rigid_weights(ob, bone):
    ob.vertex_groups.clear()
    g = ob.vertex_groups.new(name=bone)
    g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")


def transfer_weights(src, dst, max_inf=4, k=4, only=None):
    """Copy weights from nearest vertices of src (already weighted) onto dst."""
    Ps = verts_np(src)
    Pd = verts_np(dst)
    names = [g.name for g in src.vertex_groups]
    Ws = np.zeros((len(Ps), len(names)))
    for v in src.data.vertices:
        for g in v.groups:
            Ws[v.index, g.group] = g.weight
    W = np.zeros((len(Pd), len(names)))
    chunk = 2000
    for s in range(0, len(Pd), chunk):
        d = np.linalg.norm(Pd[s:s + chunk, None, :] - Ps[None, :, :], axis=2)
        idx = np.argsort(d, axis=1)[:, :k]
        dd = np.take_along_axis(d, idx, axis=1) + 1e-3
        w = 1 / dd ** 2
        w /= w.sum(axis=1, keepdims=True)
        W[s:s + chunk] = np.einsum("ij,ijk->ik", w, Ws[idx])
    apply_weights(dst, W, names, max_inf)


def bind(ob, arm):
    ob.parent = arm
    ob.matrix_parent_inverse = Matrix.Identity(4)
    m = ob.modifiers.new("Armature", "ARMATURE")
    m.object = arm


# ----------------------------------------------------------------------------
# armature + posing
# ----------------------------------------------------------------------------
def build_armature(name, bones, roll_axis=None):
    """bones: list of (name, head, tail, parent, connected[, roll_z_vector])."""
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(arm)
    set_active(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for spec in bones:
        bn, head, tail, parent, conn = spec[:5]
        b = eb.new(bn)
        b.head = Vector(head)
        b.tail = Vector(tail)
        if parent:
            b.parent = eb[parent]
            b.use_connect = conn
        # consistent roll: local X toward world +X where possible
        if len(spec) > 5:
            b.align_roll(Vector(spec[5]))
        else:
            b.align_roll(Vector((0, 0, 1)) if abs((b.tail - b.head).normalized().z) < 0.7 else Vector((0, -1, 0)))
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return arm


class Rig:
    """Pure-python FK over the rest armature, producing basis transforms."""

    def __init__(self, arm):
        self.arm = arm
        self.order = []
        self.rest_q = {}
        self.head = {}
        self.tail = {}
        self.parent = {}

        def walk(b):
            self.order.append(b.name)
            for c in b.children:
                walk(c)

        for b in arm.data.bones:
            self.rest_q[b.name] = b.matrix_local.to_quaternion()
            self.head[b.name] = Vector(b.head_local)
            self.tail[b.name] = Vector(b.tail_local)
            self.parent[b.name] = b.parent.name if b.parent else None
        for b in arm.data.bones:
            if b.parent is None:
                walk(b)

    def solve(self, local=None, world=None, root_t=None):
        """local: bone -> Quaternion (rest-frame rotation relative to parent)
        world: bone -> Quaternion (rest-frame world delta, overrides local)
        Returns (D, H): world delta per bone and posed head positions."""
        local = local or {}
        world = world or {}
        D, H = {}, {}
        for b in self.order:
            p = self.parent[b]
            Dp = D[p] if p else Quaternion()
            if b in world:
                D[b] = world[b]
            else:
                D[b] = Dp @ local.get(b, Quaternion())
            if p:
                H[b] = H[p] + Dp @ (self.head[b] - self.head[p])
            else:
                H[b] = self.head[b] + (Vector(root_t) if root_t is not None else Vector())
        return D, H

    def point(self, D, H, bone, rest_point):
        """World position of a rest-space point rigidly attached to bone."""
        return H[bone] + D[bone] @ (Vector(rest_point) - self.head[bone])

    def tail_pos(self, D, H, bone):
        return self.point(D, H, bone, self.tail[bone])

    def to_basis(self, D, root_t=None):
        out = {}
        for b in self.order:
            p = self.parent[b]
            Dp = D[p] if p else Quaternion()
            R = Dp.inverted() @ D[b]
            Rr = self.rest_q[b]
            q = Rr.inverted() @ R @ Rr
            loc = Vector()
            if p is None and root_t is not None:
                loc = Rr.inverted() @ Vector(root_t)
            out[b] = (q, loc)
        return out


def rx(deg):
    return Quaternion((1, 0, 0), math.radians(deg))


def ry(deg):
    return Quaternion((0, 1, 0), math.radians(deg))


def rz(deg):
    return Quaternion((0, 0, 1), math.radians(deg))


def eul(x=0, y=0, z=0):
    return Euler((math.radians(x), math.radians(y), math.radians(z)), "XYZ").to_quaternion()


def write_action(arm, name, frames, loop=False):
    """frames: list of dict bone -> (Quaternion, Vector). Keys at 0..n-1."""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    n = len(frames)
    bones = list(frames[0].keys())
    prev = {}
    for b in bones:
        qs = []
        for f in frames:
            q = f[b][0].copy()
            if b in prev and prev[b].dot(q) < 0:
                q.negate()
            prev[b] = q
            qs.append(q)
        path = f'pose.bones["{b}"].rotation_quaternion'
        for i in range(4):
            fc = act.fcurve_ensure_for_datablock(arm, path, index=i, group_name=b)
            fc.keyframe_points.add(n)
            co = np.zeros((n, 2), dtype=np.float32)
            co[:, 0] = np.arange(n)
            co[:, 1] = [q[i] for q in qs]
            fc.keyframe_points.foreach_set("co", co.ravel())
            fc.keyframe_points.foreach_set("interpolation", np.full(n, 1, dtype=np.int32))  # LINEAR
            fc.update()
        locs = [f[b][1] for f in frames]
        if any(l.length > 1e-6 for l in locs):
            path = f'pose.bones["{b}"].location'
            for i in range(3):
                fc = act.fcurve_ensure_for_datablock(arm, path, index=i, group_name=b)
                fc.keyframe_points.add(n)
                co = np.zeros((n, 2), dtype=np.float32)
                co[:, 0] = np.arange(n)
                co[:, 1] = [l[i] for l in locs]
                fc.keyframe_points.foreach_set("co", co.ravel())
                fc.keyframe_points.foreach_set("interpolation", np.full(n, 1, dtype=np.int32))
                fc.update()
    act.frame_range = (0, n - 1)
    act.use_frame_range = True
    act.use_cyclic = loop
    return act


def apply_basis(arm, basis):
    for b, (q, loc) in basis.items():
        pb = arm.pose.bones[b]
        pb.rotation_quaternion = q
        pb.location = loc


def two_bone_2d(A, T, L1, L2, bend):
    """2D IK in (y,z). Returns angle of first and second segment (radians)."""
    d = T - A
    dist = math.hypot(d[0], d[1])
    dist = min(max(dist, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    base = math.atan2(d[1], d[0])
    ca = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
    a1 = base + bend * math.acos(max(-1, min(1, ca)))
    J = (A[0] + L1 * math.cos(a1), A[1] + L1 * math.sin(a1))
    a2 = math.atan2(T[1] - J[1], T[0] - J[0])
    return a1, a2


def ang2(v):
    """Sagittal angle of a 3D vector: atan2(z, y)."""
    return math.atan2(v[2], v[1])


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def bump(s, peak):
    """Smooth 0->1->0 bump on [0,1] peaking at `peak`, zero slope at the ends."""
    if s <= 0 or s >= 1:
        return 0.0
    w = s / (2 * peak) if s < peak else 0.5 + (s - peak) / (2 * (1 - peak))
    return math.sin(math.pi * w) ** 2


def keyposes(times, poses, t, ease=True):
    """Piecewise interpolation of pose dicts (values are tuples of floats).
    Uses Catmull-Rom through the keys for smooth motion."""
    if t <= times[0]:
        return poses[0]
    if t >= times[-1]:
        return poses[-1]
    i = max(j for j in range(len(times) - 1) if times[j] <= t)
    u = (t - times[i]) / (times[i + 1] - times[i])
    p0 = poses[max(i - 1, 0)]
    p1 = poses[i]
    p2 = poses[i + 1]
    p3 = poses[min(i + 2, len(poses) - 1)]
    keys = set(p1) | set(p2)
    out = {}
    for k in keys:
        def g(p, fallback):
            return p.get(k, fallback.get(k, (0, 0, 0)))
        a0 = np.array(g(p0, p1), dtype=float)
        a1 = np.array(g(p1, p2), dtype=float)
        a2 = np.array(g(p2, p1), dtype=float)
        a3 = np.array(g(p3, p2), dtype=float)
        u2, u3 = u * u, u * u * u
        v = 0.5 * ((2 * a1) + (-a0 + a2) * u + (2 * a0 - 5 * a1 + 4 * a2 - a3) * u2 + (-a0 + 3 * a1 - 3 * a2 + a3) * u3)
        out[k] = tuple(v)
    return out


# ----------------------------------------------------------------------------
# export / preview
# ----------------------------------------------------------------------------
def export_glb(path, objects):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_force_sampling=True,
        export_frame_range=False,
        export_skins=True,
        export_influence_nb=4,
        export_def_bones=False,
        export_reset_pose_bones=True,
        export_anim_single_armature=True,
        export_optimize_animation_size=True,
        export_image_format="JPEG",
        export_jpeg_quality=88,
        export_image_quality=88,
        export_cameras=False,
        export_lights=False,
        export_extras=False,
    )
    print(f"[export] {path} {os.path.getsize(path) / 1024:.0f} KB")


def setup_preview_scene(res=(640, 420)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.55, 0.62, 0.72, 1)
    bg.inputs[1].default_value = 0.9
    sc.world = world
    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.energy = 4.5
    sun_d.color = (1.0, 0.82, 0.6)
    sun_d.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", sun_d)
    sun.rotation_euler = Euler((math.radians(55), math.radians(0), math.radians(-35)))
    sc.collection.objects.link(sun)
    gm = bpy.data.meshes.new("Ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
    bm.to_mesh(gm)
    bm.free()
    g = bpy.data.objects.new("Ground", gm)
    mat = bpy.data.materials.new("GroundM")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.33, 0.22, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1
    gm.materials.append(mat)
    sc.collection.objects.link(g)
    return sc


def camera(name, loc, target, ortho=None, lens=50):
    cd = bpy.data.cameras.new(name)
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.lens = lens
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def render_to(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return path


def contact_sheet(paths, out, cols):
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p)
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        imgs.append(a)
        bpy.data.images.remove(im)
    h, w = imgs[0].shape[:2]
    rows = (len(imgs) + cols - 1) // cols
    sheet = np.ones((rows * h, cols * w, 4), dtype=np.float32)
    for i, a in enumerate(imgs):
        r, c = divmod(i, cols)
        # images are bottom-up; place row 0 at the top
        y0 = (rows - 1 - r) * h
        sheet[y0:y0 + h, c * w:(c + 1) * w] = a
    im = bpy.data.images.new("sheet", cols * w, rows * h, alpha=True)
    im.pixels.foreach_set(sheet.ravel())
    im.filepath_raw = out
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return out
