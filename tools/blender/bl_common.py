"""Shared Blender helpers for the SCHOFIELD asset builders (runs inside Blender 5.x).

- MeshBuilder: accumulate verts/faces with per-corner UVs, material index, smoothing,
  optional per-corner colour and custom normals -> real mesh object.
- Atlas UV helpers (rects in pixels, y down, like atlas_layout.py).
- Vertex-colour AO bake (BVH ray casts + ground plane) into a 'Color' corner attribute.
- Shared Principled materials (image atlas × vertex colour, optional alpha clip).
- GLB export + verification.
"""
import bpy, bmesh, math, random, os, sys
from mathutils import Vector, Matrix, Quaternion, noise
from mathutils.bvhtree import BVHTree

V = Vector


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


# ----------------------------------------------------------------------------- atlas uv
class AtlasUV:
    def __init__(self, rects, size, inset=2.0):
        self.rects = rects
        self.W, self.H = size
        self.inset = inset

    def rect(self, name):
        return self.rects[name] if isinstance(name, str) else name

    def __call__(self, name, u, v):
        x, y, w, h = self.rect(name)
        i = self.inset
        x0, x1 = (x + i) / self.W, (x + w - i) / self.W
        yb, yt = (y + h - i), (y + i)
        U = x0 + (x1 - x0) * u
        Vv = 1.0 - (yb - (yb - yt) * v) / self.H
        return (U, Vv)

    def sub(self, name, fx0, fy0, fx1, fy1):
        """Sub-rectangle in fractional coords of a rect (fy measured from the BOTTOM)."""
        x, y, w, h = self.rect(name)
        return (x + w * fx0, y + h * (1 - fy1), w * (fx1 - fx0), h * (fy1 - fy0))


# ----------------------------------------------------------------------------- mesh builder
class MeshBuilder:
    def __init__(self):
        self.verts = []
        self.faces = []   # (idx tuple, uv tuple, mat, smooth)
        self.fcols = {}   # face index -> per-corner colours
        self.fnorms = {}  # face index -> per-corner custom normals
        self.tags = []    # per-face tag (e.g. 'foliage', 'glass')

    def v(self, co):
        self.verts.append(V(co))
        return len(self.verts) - 1

    def face(self, idx, uvs, mat=0, smooth=False, cols=None, normals=None, tag=None):
        assert len(idx) == len(uvs)
        self.faces.append((tuple(idx), tuple(uvs), mat, smooth))
        fi = len(self.faces) - 1
        if cols is not None:
            self.fcols[fi] = cols
        if normals is not None:
            self.fnorms[fi] = normals
        self.tags.append(tag)
        return fi

    def quad(self, p, uvs, mat=0, smooth=False, tag=None, normals=None, cols=None):
        """p: 4 points CCW seen from the front."""
        ids = [self.v(x) for x in p]
        return self.face(ids, uvs, mat, smooth, tag=tag, normals=normals, cols=cols)

    def merge(self, other, xform=None):
        off = len(self.verts)
        for co in other.verts:
            self.verts.append(xform @ co if xform else co.copy())
        for fi, (idx, uvs, mat, sm) in enumerate(other.faces):
            nf = self.face([i + off for i in idx], uvs, mat, sm, tag=other.tags[fi])
            if fi in other.fcols:
                self.fcols[nf] = other.fcols[fi]
            if fi in other.fnorms:
                n = other.fnorms[fi]
                if xform:
                    rot = xform.to_3x3()
                    n = [(rot @ V(x)).normalized() for x in n]
                self.fnorms[nf] = n

    def ntris(self):
        return sum(len(f[0]) - 2 for f in self.faces)

    def build(self, name, materials, sharp_angle=None, collection=None):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.verts], [], [f[0] for f in self.faces])
        me.update()
        # uv
        uvl = me.uv_layers.new(name='UVMap')
        uvflat = []
        for f in self.faces:
            for uv in f[1]:
                uvflat.extend(uv)
        uvl.data.foreach_set('uv', uvflat)
        # materials
        for m in materials:
            me.materials.append(m)
        me.polygons.foreach_set('material_index', [f[2] for f in self.faces])
        me.polygons.foreach_set('use_smooth', [bool(f[3]) for f in self.faces])
        if sharp_angle is not None:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
        # custom normals
        if self.fnorms:
            me.update()
            me.polygons.foreach_set('use_smooth', [True] * len(self.faces))
            cn = []
            # default: keep the (possibly flat) computed normals for faces without custom
            corner_n = [tuple(n.vector) for n in me.corner_normals]
            li = 0
            for fi, f in enumerate(self.faces):
                n = len(f[0])
                if fi in self.fnorms:
                    cn.extend([tuple(V(x).normalized()) for x in self.fnorms[fi]])
                else:
                    if f[3]:
                        cn.extend(corner_n[li:li + n])
                    else:
                        fn = me.polygons[fi].normal
                        cn.extend([tuple(fn)] * n)
                li += n
            me.normals_split_custom_set(cn)
        me.validate(clean_customdata=False)
        me.update()
        ob = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        ob['_tags'] = [t or '' for t in self.tags]
        return ob


def frame_from_dir(d, up_hint=V((0, 0, 1))):
    d = d.normalized()
    if abs(d.dot(up_hint)) > 0.95:
        up_hint = V((1, 0, 0))
    x = d.cross(up_hint).normalized()
    y = d.cross(x).normalized()
    return x, y, d


def resample_path(pts, radii, tile):
    """Insert extra samples at every multiple of `tile` metres of arc length so no
    segment straddles a texture-tile boundary. Returns (pts, radii, lengths)."""
    out_p, out_r, out_l = [pts[0]], [radii[0]], [0.0]
    L = 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        seg = (b - a).length
        if seg < 1e-9:
            continue
        k0 = math.floor(L / tile + 1e-6)
        nextb = (k0 + 1) * tile
        while nextb < L + seg - 1e-4:
            t = (nextb - L) / seg
            if t > 1e-3:
                out_p.append(a.lerp(b, t))
                out_r.append(radii[i - 1] + (radii[i] - radii[i - 1]) * t)
                out_l.append(nextb)
            nextb += tile
        L += seg
        out_p.append(b)
        out_r.append(radii[i])
        out_l.append(L)
    return out_p, out_r, out_l


def tube(mb, auv, rect, pts, radii, sides, tile_v, mat=0, cap_end=True, cap_start=False,
         u_repeat=1, jitter=0.0, seed=0, smooth=True, profile=None, prof_u=None, tag=None):
    """Generalised cylinder along a polyline with parallel-transport frames.
    profile: optional list of (angle, radius_scale) per side (for ribbed cactus etc.);
    prof_u: optional list of u coords (len sides+1) matching the profile."""
    pts, radii, lens = resample_path([V(p) for p in pts], list(radii), tile_v)
    rnd = random.Random(seed)
    n = len(pts)
    # frames
    tangents = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i - 1])
        tangents.append(t.normalized())
    x, y, _ = frame_from_dir(tangents[0])
    frames = []
    for i in range(n):
        if i > 0:
            # parallel transport x
            t0, t1 = tangents[i - 1], tangents[i]
            ax = t0.cross(t1)
            if ax.length > 1e-6:
                ang = t0.angle(t1)
                q = Quaternion(ax.normalized(), ang)
                x = q @ x
            x = (x - t1 * x.dot(t1)).normalized()
        y = tangents[i].cross(x).normalized()
        frames.append((x.copy(), y.copy()))
    if profile is None:
        profile = [(2 * math.pi * s / sides, 1.0) for s in range(sides)]
    if prof_u is None:
        prof_u = [s / sides * u_repeat for s in range(sides + 1)]
    rings = []
    for i in range(n):
        fx, fy = frames[i]
        ring = []
        for s in range(sides):
            a, rs = profile[s]
            j = 1.0 + (rnd.uniform(-jitter, jitter) if jitter else 0)
            r = radii[i] * rs * j
            ring.append(mb.v(pts[i] + (fx * math.cos(a) + fy * math.sin(a)) * r))
        rings.append(ring)

    def uwrap(s):
        return prof_u[s] - math.floor(prof_u[s]) if prof_u[s] > 1.0 + 1e-6 else prof_u[s]
    for i in range(n - 1):
        k = math.floor((lens[i] + lens[i + 1]) * 0.5 / tile_v)
        v0 = lens[i] / tile_v - k
        v1 = lens[i + 1] / tile_v - k
        v0, v1 = max(0.0, min(1.0, v0)), max(0.0, min(1.0, v1))
        for s in range(sides):
            s2 = (s + 1) % sides
            u0 = prof_u[s]
            u1 = prof_u[s + 1]
            # keep u within the rect: fold repeats
            if u_repeat > 1:
                base = math.floor(u0 + 1e-6)
                u0 -= base
                u1 -= base
            mb.face([rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]],
                    [auv(rect, u0, v0), auv(rect, u1, v0), auv(rect, u1, v1), auv(rect, u0, v1)],
                    mat, smooth, tag=tag)
    if cap_end:
        c = mb.v(pts[-1] + tangents[-1] * radii[-1] * 0.25)
        for s in range(sides):
            s2 = (s + 1) % sides
            mb.face([rings[-1][s], rings[-1][s2], c],
                    [auv(rect, prof_u[s] % 1.0001, 0.9), auv(rect, prof_u[s + 1] % 1.0001, 0.9), auv(rect, 0.5, 1.0)], mat, smooth, tag=tag)
    if cap_start:
        c = mb.v(pts[0] - tangents[0] * radii[0] * 0.1)
        for s in range(sides):
            s2 = (s + 1) % sides
            mb.face([rings[0][s2], rings[0][s], c],
                    [auv(rect, 0.2, 0.1), auv(rect, 0.4, 0.1), auv(rect, 0.3, 0.0)], mat, smooth, tag=tag)
    return rings


def box(mb, auv, rect, center, size, rot=None, mat=0, tile=(1.0, 1.0), grain_axis=None,
        rnd=None, faces_rect=None, skip=(), tag=None, bevel_cols=None):
    """Axis box (then rotated). Each face mapped into `rect` with its long/grain axis on v.
    tile=(u metres, v metres) that the rect represents; faces smaller than the tile get a
    random crop inside the rect, larger ones are scaled to fit.
    faces_rect: optional dict face-> rect override ('+x','-x','+y','-y','+z','-z').
    skip: face keys to omit."""
    rnd = rnd or random.Random(0)
    c = V(center)
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    R = rot.to_3x3() if rot is not None else Matrix.Identity(3)
    if grain_axis is None:
        grain_axis = max(range(3), key=lambda i: size[i])
    corners = {}

    def P(ix, iy, iz):
        return c + R @ V((ix * sx, iy * sy, iz * sz))
    # face definitions: key, normal axis, sign, the 4 corners CCW from outside
    F = {
        '+x': [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)],
        '-x': [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)],
        '+y': [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)],
        '-y': [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)],
        '+z': [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        '-z': [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)],
    }
    out = []
    for key, cs in F.items():
        if key in skip:
            continue
        pts = [P(*q) for q in cs]
        axis_n = 'xyz'.index(key[1])
        # in-plane axes
        e1 = pts[1] - pts[0]
        e2 = pts[3] - pts[0]
        # which in-plane edge is along the grain axis?
        g = R @ V([1 if i == grain_axis else 0 for i in range(3)])
        if abs(e1.normalized().dot(g)) > abs(e2.normalized().dot(g)):
            # e1 along grain -> v along e1, u along e2
            lu, lv = e2.length, e1.length
            uvp = [(0, 0), (0, 1), (1, 1), (1, 0)]
        else:
            lu, lv = e1.length, e2.length
            uvp = [(0, 0), (1, 0), (1, 1), (0, 1)]
        fu, fv = min(1.0, lu / tile[0]), min(1.0, lv / tile[1])
        ou, ov = rnd.uniform(0, 1 - fu), rnd.uniform(0, 1 - fv)
        r = (faces_rect or {}).get(key, rect)
        if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], str):
            # ('full', rectname): map whole rect regardless of size
            r = r[1]
            fu = fv = 1.0
            ou = ov = 0.0
        uvs = [auv(r, ou + a * fu, ov + b * fv) for a, b in uvp]
        out.append(mb.quad(pts, uvs, mat, tag=tag))
    return out


# ----------------------------------------------------------------------------- materials
def load_image(path):
    return bpy.data.images.load(path, check_existing=True)


def make_material(name, image, alpha_clip=None, roughness=0.9, double_sided=False, vcol=True, specular=0.3):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (600, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    tex.location = (-400, 100)
    tex.interpolation = 'Linear'
    if vcol:
        ca = nt.nodes.new('ShaderNodeVertexColor')
        ca.layer_name = 'Color'
        ca.location = (-400, -150)
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        mix.location = (0, 100)
        nt.links.new(tex.outputs['Color'], mix.inputs['A'])
        nt.links.new(ca.outputs['Color'], mix.inputs['B'])
        nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    else:
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = 0.0
    try:
        bsdf.inputs['Specular IOR Level'].default_value = specular
    except Exception:
        pass
    if alpha_clip is not None:
        gt = nt.nodes.new('ShaderNodeMath')
        gt.operation = 'GREATER_THAN'
        gt.inputs[1].default_value = alpha_clip
        gt.location = (0, -200)
        nt.links.new(tex.outputs['Alpha'], gt.inputs[0])
        nt.links.new(gt.outputs[0], bsdf.inputs['Alpha'])
        m.surface_render_method = 'DITHERED'
    m.use_backface_culling = not double_sided
    return m


# ----------------------------------------------------------------------------- vertex colours
def cosine_dirs(n, count, rnd):
    t, b, _ = frame_from_dir(n)
    out = []
    for i in range(count):
        u1, u2 = rnd.random(), rnd.random()
        r = math.sqrt(u1)
        th = 2 * math.pi * u2
        x, y = r * math.cos(th), r * math.sin(th)
        z = math.sqrt(max(0.0, 1 - u1))
        out.append((t * x + b * y + n * z).normalized())
    return out


def bake_vertex_colors(ob, rays=20, max_dist=1.5, strength=0.85, ground=True, ground_z=0.0,
                       tint_fn=None, occluders=(), foliage_fn=None, seed=1, gamma=1.0):
    """Per-corner colour = AO (ray-traced against this mesh + extra occluder objects + ground plane)
    times tint_fn(co, normal) -> (r,g,b). Faces tagged 'foliage' use foliage_fn(co, corner_normal)
    instead of ray casting (cards would self-shadow as if solid)."""
    me = ob.data
    me.update()
    rnd = random.Random(seed)
    tags = list(ob.get('_tags', []))
    # BVH from non-foliage faces
    verts = [v.co.copy() for v in me.vertices]
    polys = [tuple(p.vertices) for i, p in enumerate(me.polygons) if not (i < len(tags) and tags[i] == 'foliage')]
    for o in occluders:
        off = len(verts)
        mw = o.matrix_world
        verts += [mw @ v.co for v in o.data.vertices]
        polys += [tuple(i + off for i in p.vertices) for p in o.data.polygons]
    bvh = BVHTree.FromPolygons(verts, polys, epsilon=0.0) if polys else None
    vn = [v.normal.copy() for v in me.vertices]
    ao = [1.0] * len(me.vertices)
    foliage_verts = set()
    for i, p in enumerate(me.polygons):
        if i < len(tags) and tags[i] == 'foliage':
            foliage_verts.update(p.vertices)
    for vi, v in enumerate(me.vertices):
        if vi in foliage_verts and bvh is not None:
            continue
        n = vn[vi]
        if n.length < 0.5:
            n = V((0, 0, 1))
        o = v.co + n * 0.01
        hits = 0.0
        for d in cosine_dirs(n, rays, rnd):
            hit = False
            if bvh is not None:
                loc, nor, idx, dist = bvh.ray_cast(o, d, max_dist)
                if loc is not None:
                    hits += 1.0 - 0.5 * (dist / max_dist)
                    hit = True
            if not hit and ground and d.z < -1e-4:
                t = (ground_z - o.z) / d.z
                if 0 < t < max_dist:
                    hits += 1.0 - 0.5 * (t / max_dist)
        a = 1.0 - strength * hits / rays
        ao[vi] = max(0.0, a) ** gamma
    col = me.color_attributes.get('Color') or me.color_attributes.new('Color', 'BYTE_COLOR', 'CORNER')
    cn = me.corner_normals
    data = []
    for li, loop in enumerate(me.loops):
        vi = loop.vertex_index
        co = me.vertices[vi].co
        pi = None
        data_n = V(cn[li].vector)
        # find face tag
        data.append((vi, co, data_n))
    # map loop -> polygon
    loop_poly = [0] * len(me.loops)
    for p in me.polygons:
        for li in p.loop_indices:
            loop_poly[li] = p.index
    flat = []
    for li, (vi, co, nrm) in enumerate(data):
        pi = loop_poly[li]
        if pi < len(tags) and tags[pi] == 'foliage' and foliage_fn is not None:
            r, g, b = foliage_fn(co, nrm)
        else:
            a = ao[vi]
            r = g = b = a
            if tint_fn is not None:
                t = tint_fn(co, nrm)
                r, g, b = r * t[0], g * t[1], b * t[2]
        flat.extend((min(1, max(0, r)), min(1, max(0, g)), min(1, max(0, b)), 1.0))
    col.data.foreach_set('color', flat)
    me.color_attributes.active_color = col
    try:
        me.color_attributes.render_color_index = me.color_attributes.find('Color')
    except Exception:
        pass
    return ob


# ----------------------------------------------------------------------------- empties / export / verify
def empty(name, loc, parent=None, size=0.3, rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'ARROWS'
    e.empty_display_size = size
    e.location = V(loc)
    e.rotation_euler = rot
    bpy.context.scene.collection.objects.link(e)
    if parent is not None:
        e.parent = parent
        e.matrix_parent_inverse = Matrix.Identity(4)
    return e


def export_glb(path, jpeg_quality=85):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for ob in bpy.data.objects:
        if '_tags' in ob.keys():
            del ob['_tags']
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', export_yup=True, export_apply=True,
        export_image_format='AUTO', export_jpeg_quality=jpeg_quality,
        export_vertex_color='MATERIAL', export_normals=True, export_texcoords=True,
        export_materials='EXPORT', export_cameras=False, export_lights=False,
        export_animations=False, export_extras=False, use_selection=False)
    print('EXPORTED', path, os.path.getsize(path) // 1024, 'KB')
    compact_glb(path)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons) if ob.type == 'MESH' else 0


def verify_glb(path, required):
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=path)
    roots = [o for o in bpy.data.objects if o.parent is None]
    names = {o.name for o in roots}
    print('\n==== VERIFY', os.path.basename(path), os.path.getsize(path) // 1024, 'KB ====')
    total = 0
    for o in sorted(roots, key=lambda o: o.name):
        def subtree(x):
            yield x
            for c in x.children:
                yield from subtree(c)
        tris = sum(tri_count(x) for x in subtree(o))
        total += tris
        # world bbox over meshes in subtree
        pts = []
        for x in subtree(o):
            if x.type == 'MESH':
                pts += [x.matrix_world @ V(c) for c in x.bound_box]
        if pts:
            mn = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            mx = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            sz = mx - mn
            bb = 'size %.2f x %.2f x %.2f  min(%.2f,%.2f,%.2f)' % (sz.x, sz.y, sz.z, mn.x, mn.y, mn.z)
        else:
            bb = ''
        mats = sorted({s.material.name for x in subtree(o) if x.type == 'MESH' for s in x.material_slots if s.material})
        print('ROOT %-14s tris %5d  %s  mats=%s' % (o.name, tris, bb, mats))
        for x in subtree(o):
            if x is o:
                continue
            wl = x.matrix_world.translation
            print('    child %-26s %-6s at (%.2f, %.2f, %.2f)' % (x.name, x.type, wl.x, wl.y, wl.z))
    missing = [r for r in required if r not in names]
    print('TOTAL tris', total)
    print('MISSING ROOTS:', missing if missing else 'none')
    imgs = [(i.name, i.size[0], i.size[1]) for i in bpy.data.images]
    print('IMAGES', imgs)
    print('MATERIALS', [m.name for m in bpy.data.materials])
    return missing


# ----------------------------------------------------------------------------- GLB compaction
def compact_glb(path):
    """Core-glTF-only size reduction (no extensions needed by three.js):
    COLOR_0 float -> normalized UNSIGNED_BYTE VEC4, TEXCOORD_n float -> normalized
    UNSIGNED_SHORT (when all values lie in [0,1])."""
    import json, struct
    import numpy as np
    b = open(path, 'rb').read()
    jl = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl = struct.unpack('<I', b[off:off + 4])[0]
    binc = b[off + 8: off + 8 + bl]
    CT = {5126: ('<f4', 4), 5123: ('<u2', 2), 5125: ('<u4', 4), 5121: ('u1', 1), 5122: ('<i2', 2), 5120: ('i1', 1)}
    NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}

    def read_acc(a):
        acc = j['accessors'][a]
        bv = j['bufferViews'][acc['bufferView']]
        dt, sz = CT[acc['componentType']]
        n = NC[acc['type']]
        start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = bv.get('byteStride', sz * n)
        raw = np.frombuffer(binc, dtype=np.uint8, count=stride * (acc['count'] - 1) + sz * n, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(acc['count'], sz * n), strides=(stride, 1)).copy()
        return rows.view(dt).reshape(acc['count'], n)

    new_views = {}  # accessor -> bytes
    for mesh in j['meshes']:
        for pr in mesh['primitives']:
            for k, a in pr['attributes'].items():
                acc = j['accessors'][a]
                if a in new_views or acc['componentType'] != 5126:
                    continue
                if k.startswith('COLOR_'):
                    d = read_acc(a)
                    if d.shape[1] == 3:
                        d = np.hstack([d, np.ones((len(d), 1), np.float32)])
                    q = np.clip(np.round(d * 255), 0, 255).astype(np.uint8)
                    new_views[a] = (q.tobytes(), 5121, 'VEC4')
                elif k.startswith('TEXCOORD_'):
                    d = read_acc(a)
                    if d.min() >= -1e-6 and d.max() <= 1 + 1e-6:
                        q = np.clip(np.round(d * 65535), 0, 65535).astype(np.uint16)
                        new_views[a] = (q.tobytes(), 5123, 'VEC2')
    # rebuild the binary chunk
    out = bytearray()
    views = []
    vmap = {}

    def add_view(data, target=None):
        while len(out) % 4:
            out.append(0)
        v = {'buffer': 0, 'byteOffset': len(out), 'byteLength': len(data)}
        if target:
            v['target'] = target
        out.extend(data)
        views.append(v)
        return len(views) - 1
    for ai, acc in enumerate(j['accessors']):
        if ai in new_views:
            data, ct, typ = new_views[ai]
            acc['bufferView'] = add_view(data, 34962)
            acc['componentType'] = ct
            acc['type'] = typ
            acc['normalized'] = True
            acc.pop('byteOffset', None)
            acc.pop('min', None)
            acc.pop('max', None)
        elif 'bufferView' in acc:
            ov = acc['bufferView']
            if ov not in vmap:
                bv = j['bufferViews'][ov]
                s = bv.get('byteOffset', 0)
                nv = add_view(binc[s:s + bv['byteLength']], bv.get('target'))
                if 'byteStride' in bv:
                    views[nv]['byteStride'] = bv['byteStride']
                vmap[ov] = nv
            acc['bufferView'] = vmap[ov]
    for im in j.get('images', []):
        if 'bufferView' in im:
            ov = im['bufferView']
            bv = j['bufferViews'][ov]
            s = bv.get('byteOffset', 0)
            im['bufferView'] = add_view(binc[s:s + bv['byteLength']])
    while len(out) % 4:
        out.append(0)
    j['bufferViews'] = views
    j['buffers'] = [{'byteLength': len(out)}]
    js = json.dumps(j, separators=(',', ':')).encode()
    while len(js) % 4:
        js += b' '
    total = 12 + 8 + len(js) + 8 + len(out)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack('<II', len(out), 0x004E4942))
        f.write(out)
    print('COMPACTED', path, os.path.getsize(path) // 1024, 'KB')
