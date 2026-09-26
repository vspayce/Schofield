"""Shared Blender helpers for SCHOFIELD asset scripts.

Geometry builders (bmesh), a small procedural-material builder whose channels
(colour / roughness / metallic / normal) get baked to image atlases in Cycles,
and GLB export helpers.  Everything here is plain bpy/bmesh — run through
Blender --background --factory-startup.
"""
import bpy
import bmesh
import math
import os
from mathutils import Vector, Matrix

# ----------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    return sc


def setup_cycles(samples=32):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = 'GPU'
    except Exception as e:  # pragma: no cover
        print('GPU setup failed, using CPU:', e)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 8
    sc.render.bake.margin_type = 'EXTEND'
    return sc


def link(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def srgb(r, g, b, a=1.0):
    """0-255 sRGB -> linear RGBA tuple for node defaults."""
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b), a)


# ----------------------------------------------------------------------------
# geometry
# ----------------------------------------------------------------------------


def uv_layer(bm, name='SweepUV'):
    return bm.loops.layers.uv.get(name) or bm.loops.layers.uv.new(name)


def obj_from_bm(name, bm, mat=None, smooth=None, props=None):
    """smooth: None=flat, float=smooth with sharp edges above that angle (deg)."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    if mat is not None:
        for m_ in (mat if isinstance(mat, (list, tuple)) else [mat]):
            me.materials.append(m_)
    if smooth is not None:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
    else:
        me.shade_flat()
    for k, v in (props or {}).items():
        ob[k] = v
    return ob


def mat_trs(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    from mathutils import Euler
    return (Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
            @ Matrix.Diagonal(Vector((*scale, 1.0))))


def _bevel_new(bm, verts, offset, segs):
    if offset <= 0:
        return
    edges = list({e for v in verts for e in v.link_edges})
    bmesh.ops.bevel(bm, geom=list(verts) + edges, offset=offset, segments=segs,
                    profile=0.5, affect='EDGES', clamp_overlap=True)


def add_box(bm, size, loc=(0, 0, 0), rot=(0, 0, 0), bevel=0.0, segs=1, matrix=None):
    M = (matrix or Matrix()) @ mat_trs(loc, rot, size)
    r = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
    _bevel_new(bm, r['verts'], bevel, segs)
    return r['verts']


def add_cyl(bm, r1, r2, depth, segs, loc=(0, 0, 0), rot=(0, 0, 0), caps=True, matrix=None,
            bevel=0.0):
    """Cylinder/cone along local Z."""
    M = (matrix or Matrix()) @ mat_trs(loc, rot)
    r = bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs,
                              radius1=r1, radius2=r2, depth=depth, matrix=M)
    _bevel_new(bm, r['verts'], bevel, 1)
    return r['verts']


def add_lathe(bm, profile, segs, matrix=None, cap0=False, cap1=False, phase=0.0,
              uv=None, closed=False):
    """profile: [(radius, axial)] revolved about local Z (axial). Outward normals when
    the outer surface is walked towards +axial. Returns (rings, faces_by_segment)."""
    M = matrix or Matrix()
    rings = []
    for (rad, ax) in profile:
        ring = []
        for i in range(segs):
            a = phase + 2 * math.pi * i / segs
            ring.append(bm.verts.new(M @ Vector((rad * math.cos(a), rad * math.sin(a), ax))))
        rings.append(ring)
    uvl = uv_layer(bm, uv) if uv else None
    nseg = len(rings) if closed else len(rings) - 1
    by_seg = []
    for j in range(nseg):
        j2 = (j + 1) % len(rings)
        fs = []
        for i in range(segs):
            i2 = (i + 1) % segs
            f = bm.faces.new((rings[j][i], rings[j][i2], rings[j2][i2], rings[j2][i]))
            fs.append(f)
            if uvl:
                us = (i / segs, (i + 1) / segs, (i + 1) / segs, i / segs)
                vs = (j, j, j + 1, j + 1)
                for lp, u, v in zip(f.loops, us, vs):
                    lp[uvl].uv = (u, v / max(1, nseg))
        by_seg.append(fs)
    if cap0 and profile[0][0] > 1e-6:
        by_seg.append([bm.faces.new(list(reversed(rings[0])))])
    if cap1 and profile[-1][0] > 1e-6:
        by_seg.append([bm.faces.new(rings[-1])])
    return rings, by_seg


def catmull(points, n=6, closed=False):
    pts = [Vector(p) for p in points]
    if len(pts) < 3:
        return pts
    out = []
    N = len(pts)
    segs = N if closed else N - 1
    for i in range(segs):
        p0 = pts[(i - 1) % N] if (closed or i > 0) else pts[0] * 2 - pts[1]
        p1 = pts[i]
        p2 = pts[(i + 1) % N]
        p3 = pts[(i + 2) % N] if (closed or i + 2 < N) else pts[-1] * 2 - pts[-2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(pts[-1])
    return out


def add_sweep(bm, path, profile, closed_path=False, caps=True, scales=None, up=(0, 0, 1),
              uv='SweepUV', twist=0.0):
    """Sweep a closed 2D profile [(x, y)] along a 3D path. Profile x -> side, y -> up.
    Writes a UV layer (u = metres along path, v = 0..1 around profile)."""
    path = [Vector(p) for p in path]
    n = len(path)
    up = Vector(up)
    tans = []
    for i in range(n):
        if closed_path:
            t = path[(i + 1) % n] - path[(i - 1) % n]
        else:
            t = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
        tans.append(t.normalized())
    # initial frame
    side = tans[0].cross(up)
    if side.length < 1e-4:
        side = tans[0].cross(Vector((1, 0, 0)))
    side.normalize()
    frames = []
    for i in range(n):
        if i > 0:  # parallel transport
            axis = tans[i - 1].cross(tans[i])
            if axis.length > 1e-6:
                ang = tans[i - 1].angle(tans[i])
                side = Matrix.Rotation(ang, 3, axis.normalized()) @ side
            side = (side - tans[i] * side.dot(tans[i])).normalized()
        upv = side.cross(tans[i]).normalized()
        frames.append((side.copy(), upv))
    rings = []
    m = len(profile)
    dist = [0.0]
    for i in range(1, n):
        dist.append(dist[-1] + (path[i] - path[i - 1]).length)
    for i in range(n):
        s = scales[i] if scales else 1.0
        sd, uu = frames[i]
        tw = twist * dist[i]
        ring = []
        for (px, py) in profile:
            if tw:
                c, si = math.cos(tw), math.sin(tw)
                px, py = px * c - py * si, px * si + py * c
            ring.append(bm.verts.new(path[i] + sd * (px * s) + uu * (py * s)))
        rings.append(ring)
    uvl = uv_layer(bm, uv) if uv else None
    per = [0.0]
    for k in range(m):
        a, b = Vector(profile[k]), Vector(profile[(k + 1) % m])
        per.append(per[-1] + (b - a).length)
    tot = per[-1] or 1
    segs = n if closed_path else n - 1
    faces = []
    for i in range(segs):
        i2 = (i + 1) % n
        for k in range(m):
            k2 = (k + 1) % m
            f = bm.faces.new((rings[i][k], rings[i2][k], rings[i2][k2], rings[i][k2]))
            faces.append(f)
            if uvl:
                d2 = dist[i2] if i2 else dist[-1] + (path[0] - path[-1]).length
                for lp, (u, v) in zip(f.loops, ((dist[i], per[k]), (d2, per[k]),
                                                (d2, per[k + 1]), (dist[i], per[k + 1]))):
                    lp[uvl].uv = (u, v / tot)
    if caps and not closed_path:
        faces.append(bm.faces.new(rings[0]))
        faces.append(bm.faces.new(list(reversed(rings[-1]))))
    return rings, faces


def add_loft(bm, rings, cap0=True, cap1=True):
    vrings = [[bm.verts.new(Vector(p)) for p in r] for r in rings]
    m = len(rings[0])
    faces = []
    for j in range(len(vrings) - 1):
        for i in range(m):
            i2 = (i + 1) % m
            faces.append(bm.faces.new((vrings[j][i], vrings[j][i2], vrings[j + 1][i2],
                                       vrings[j + 1][i])))
    if cap0:
        faces.append(bm.faces.new(list(reversed(vrings[0]))))
    if cap1:
        faces.append(bm.faces.new(vrings[-1]))
    return vrings, faces


def rect_profile(w, h, bevel=0.0):
    """Closed rectangle profile centred at 0 (w along x, h along y), optional chamfer."""
    hw, hh = w / 2, h / 2
    if bevel <= 0:
        return [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    b = min(bevel, hw * 0.9, hh * 0.9)
    return [(-hw + b, -hh), (hw - b, -hh), (hw, -hh + b), (hw, hh - b), (hw - b, hh),
            (-hw + b, hh), (-hw, hh - b), (-hw, -hh + b)]


def circle_profile(r, n=6, phase=None):
    ph = math.pi / n if phase is None else phase
    return [(r * math.cos(ph + 2 * math.pi * i / n), r * math.sin(ph + 2 * math.pi * i / n))
            for i in range(n)]


def tri_count(ob):
    me = ob.data
    return sum(len(p.vertices) - 2 for p in me.polygons)


# ----------------------------------------------------------------------------
# procedural material builder
# ----------------------------------------------------------------------------

CHANNELS = {}   # material name -> {'color': (node, out), 'rough':..., 'metal':..., 'normal':...}


class MB:
    """Tiny node-graph builder. Every helper takes sockets or constants."""

    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.nt = self.mat.node_tree
        self.nt.nodes.clear()
        self.geo = self.n('ShaderNodeNewGeometry')
        self.tc = self.n('ShaderNodeTexCoord')

    # -- plumbing
    def n(self, typ, **props):
        nd = self.nt.nodes.new(typ)
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def _sock(self, nd, key, inputs=True):
        coll = nd.inputs if inputs else nd.outputs
        if isinstance(key, int):
            return coll[key]
        for s in coll:
            if s.identifier == key and s.enabled:
                return s
        for s in coll:
            if s.identifier == key:
                return s
        for s in coll:
            if s.name == key and s.enabled:
                return s
        return coll[key]

    def put(self, nd, key, val):
        s = self._sock(nd, key)
        if isinstance(val, bpy.types.NodeSocket):
            self.nt.links.new(val, s)
        elif val is not None:
            if isinstance(val, (tuple, list)) and s.type == 'RGBA' and len(val) == 3:
                val = (*val, 1.0)
            s.default_value = val

    @property
    def pos(self):
        return self.geo.outputs['Position']

    @property
    def nrm(self):
        return self.geo.outputs['Normal']

    def xyz(self, v):
        nd = self.n('ShaderNodeSeparateXYZ')
        self.put(nd, 0, v)
        return nd.outputs[0], nd.outputs[1], nd.outputs[2]

    def comb(self, x, y, z):
        nd = self.n('ShaderNodeCombineXYZ')
        self.put(nd, 0, x); self.put(nd, 1, y); self.put(nd, 2, z)
        return nd.outputs[0]

    def m(self, op, a, b=None, c=None, clamp=False):
        nd = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.put(nd, 0, a)
        if b is not None:
            self.put(nd, 1, b)
        if c is not None:
            self.put(nd, 2, c)
        return nd.outputs[0]

    def v(self, op, a, b=None, scale=None):
        nd = self.n('ShaderNodeVectorMath', operation=op)
        self.put(nd, 0, a)
        if b is not None:
            self.put(nd, 1, b)
        if scale is not None:
            self.put(nd, 'Scale', scale)
        out = 'Value' if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE') else 'Vector'
        return nd.outputs[out]

    def mixc(self, fac, a, b, blend='MIX'):
        nd = self.n('ShaderNodeMix', data_type='RGBA', blend_type=blend, clamp_factor=True)
        self.put(nd, 'Factor_Float', fac)
        self.put(nd, 'A_Color', a)
        self.put(nd, 'B_Color', b)
        return self._sock(nd, 'Result_Color', False)

    def mixf(self, fac, a, b):
        nd = self.n('ShaderNodeMix', data_type='FLOAT', clamp_factor=True)
        self.put(nd, 'Factor_Float', fac)
        self.put(nd, 'A_Float', a)
        self.put(nd, 'B_Float', b)
        return self._sock(nd, 'Result_Float', False)

    def mapr(self, val, a, b, c=0.0, d=1.0, clamp=True, interp='LINEAR'):
        nd = self.n('ShaderNodeMapRange', clamp=clamp, interpolation_type=interp)
        self.put(nd, 'Value', val)
        self.put(nd, 'From Min', a); self.put(nd, 'From Max', b)
        self.put(nd, 'To Min', c); self.put(nd, 'To Max', d)
        return nd.outputs['Result']

    def noise(self, vec, scale, detail=4.0, rough=0.55, dist=0.0, out='Fac'):
        nd = self.n('ShaderNodeTexNoise')
        self.put(nd, 'Vector', vec)
        self.put(nd, 'Scale', scale)
        self.put(nd, 'Detail', detail)
        self.put(nd, 'Roughness', rough)
        self.put(nd, 'Distortion', dist)
        return nd.outputs[out]

    def voronoi(self, vec, scale, feature='F1', out='Distance', rand=1.0):
        nd = self.n('ShaderNodeTexVoronoi', feature=feature)
        self.put(nd, 'Vector', vec)
        self.put(nd, 'Scale', scale)
        self.put(nd, 'Randomness', rand)
        return nd.outputs[out]

    def aniso(self, vec, sx, sy, sz):
        return self.v('MULTIPLY', vec, (sx, sy, sz))

    def image(self, img, vec, interp='Linear', ext='CLIP'):
        nd = self.n('ShaderNodeTexImage', image=img, interpolation=interp, extension=ext)
        self.put(nd, 'Vector', vec)
        return nd.outputs['Color'], nd.outputs['Alpha']

    def uv(self, name):
        nd = self.n('ShaderNodeUVMap', uv_map=name)
        return nd.outputs['UV']

    def bevel_normal(self, radius, samples=8):
        nd = self.n('ShaderNodeBevel', samples=samples)
        self.put(nd, 'Radius', radius)
        return nd.outputs['Normal']

    def ao(self, dist, samples=16, only_local=False):
        nd = self.n('ShaderNodeAmbientOcclusion', samples=samples, only_local=only_local)
        self.put(nd, 'Distance', dist)
        return nd.outputs['AO']

    def bump(self, height, strength, normal=None, distance=1.0):
        nd = self.n('ShaderNodeBump')
        self.put(nd, 'Strength', strength)
        self.put(nd, 'Distance', distance)
        self.put(nd, 'Height', height)
        if normal is not None:
            self.put(nd, 'Normal', normal)
        return nd.outputs['Normal']

    def smooth(self, x, e0, e1):
        return self.mapr(x, e0, e1, 0, 1, True, 'SMOOTHSTEP')

    def finish(self, color, rough, metal, normal):
        p = self.n('ShaderNodeBsdfPrincipled')
        self.put(p, 'Base Color', color)
        self.put(p, 'Roughness', rough)
        self.put(p, 'Metallic', metal)
        if normal is not None:
            self.put(p, 'Normal', normal)
        out = self.n('ShaderNodeOutputMaterial')
        self.nt.links.new(p.outputs[0], out.inputs['Surface'])
        p.name = 'PBSDF'
        out.name = 'MATOUT'

        def ref(s):
            if isinstance(s, bpy.types.NodeSocket):
                return (s.node.name, s.identifier)
            return s
        CHANNELS[self.mat.name] = dict(color=ref(color), rough=ref(rough), metal=ref(metal),
                                       normal=ref(normal))
        return self.mat


def _resolve(nt, ref):
    if isinstance(ref, tuple) and len(ref) == 2 and isinstance(ref[0], str):
        nd = nt.nodes[ref[0]]
        for s in nd.outputs:
            if s.identifier == ref[1]:
                return s
    return ref


# ----------------------------------------------------------------------------
# UV atlas + bake
# ----------------------------------------------------------------------------


def select_only(objs, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def ensure_bake_uv(ob, name='BakeUV'):
    me = ob.data
    lay = me.uv_layers.get(name) or me.uv_layers.new(name=name)
    me.uv_layers.active = lay
    lay.active_render = True
    return lay


def uv_atlas(objs, priority=None, margin=0.004, angle=55):
    """Smart-project all objs together, equalise texel density, scale by
    per-object priority, then pack into one 0..1 atlas."""
    import numpy as np
    priority = priority or {}
    for o in objs:
        ensure_bake_uv(o)
    sc = bpy.context.scene
    sc.tool_settings.use_uv_select_sync = True
    select_only(objs)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=0.002,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in objs:
        f = priority.get(o.name, o.get('prio', 1.0))
        lay = o.data.uv_layers['BakeUV']
        a = np.zeros(len(lay.data) * 2, np.float32)
        lay.data.foreach_get('uv', a)
        lay.data.foreach_set('uv', a * f)
    select_only(objs)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin, shape_method='CONCAVE',
                            margin_method='FRACTION')
    bpy.ops.object.mode_set(mode='OBJECT')


def new_image(name, size, non_color=False):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


def _materials_of(objs):
    out = []
    for o in objs:
        for s in o.material_slots:
            if s.material and s.material not in out:
                out.append(s.material)
    return out


def bake_pass(objs, img, kind):
    """kind: 'color' | 'orm' | 'normal'"""
    mats = _materials_of(objs)
    for mat in mats:
        nt = mat.node_tree
        ch = CHANNELS[mat.name]
        tgt = nt.nodes.get('BAKE_TGT') or nt.nodes.new('ShaderNodeTexImage')
        tgt.name = 'BAKE_TGT'
        tgt.image = img
        nt.nodes.active = tgt
        out = nt.nodes['MATOUT']
        if kind in ('color', 'orm'):
            em = nt.nodes.get('BAKE_EM') or nt.nodes.new('ShaderNodeEmission')
            em.name = 'BAKE_EM'
            em.inputs['Strength'].default_value = 1.0
            if kind == 'color':
                src = _resolve(nt, ch['color'])
            else:
                cc = nt.nodes.get('BAKE_ORM') or nt.nodes.new('ShaderNodeCombineColor')
                cc.name = 'BAKE_ORM'
                cc.inputs[0].default_value = 1.0
                for idx, key in ((1, 'rough'), (2, 'metal')):
                    s = _resolve(nt, ch[key])
                    if isinstance(s, bpy.types.NodeSocket):
                        nt.links.new(s, cc.inputs[idx])
                    else:
                        cc.inputs[idx].default_value = s
                src = cc.outputs[0]
            if isinstance(src, bpy.types.NodeSocket):
                nt.links.new(src, em.inputs['Color'])
            else:
                em.inputs['Color'].default_value = src if len(src) == 4 else (*src, 1)
            nt.links.new(em.outputs[0], out.inputs['Surface'])
        else:
            nt.links.new(nt.nodes['PBSDF'].outputs[0], out.inputs['Surface'])
    select_only(objs)
    if kind == 'normal':
        bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', use_clear=True,
                            margin=bpy.context.scene.render.bake.margin)
    else:
        bpy.ops.object.bake(type='EMIT', use_clear=True,
                            margin=bpy.context.scene.render.bake.margin)
    # restore
    for mat in mats:
        nt = mat.node_tree
        nt.links.new(nt.nodes['PBSDF'].outputs[0], nt.nodes['MATOUT'].inputs['Surface'])


def save_image(img, path, quality=90):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ext = os.path.splitext(path)[1].lower()
    img.file_format = 'JPEG' if ext in ('.jpg', '.jpeg') else 'PNG'
    img.filepath_raw = path
    if img.file_format == 'JPEG':
        img.save(filepath=path, quality=quality)
    else:
        img.save(filepath=path)


def final_material(name, col, orm, nrm, normal_strength=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(p.outputs[0], out.inputs['Surface'])
    tc = nt.nodes.new('ShaderNodeTexImage'); tc.image = col
    nt.links.new(tc.outputs['Color'], p.inputs['Base Color'])
    to = nt.nodes.new('ShaderNodeTexImage'); to.image = orm
    orm.colorspace_settings.name = 'Non-Color'
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(to.outputs['Color'], sep.inputs[0])
    nt.links.new(sep.outputs[1], p.inputs['Roughness'])
    nt.links.new(sep.outputs[2], p.inputs['Metallic'])
    if nrm is not None:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = nrm
        nrm.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normal_strength
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], p.inputs['Normal'])
    return mat


def assign_single_material(ob, mat):
    me = ob.data
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0


def strip_uvs(ob, keep='BakeUV', rename='UVMap'):
    me = ob.data
    for lay in list(me.uv_layers):
        if lay.name != keep:
            me.uv_layers.remove(lay)
    if keep in me.uv_layers:
        me.uv_layers[keep].name = rename


def join(objs, name):
    select_only(objs)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def set_origin(ob, point):
    """Move object origin to world `point` without moving the geometry."""
    point = Vector(point)
    d = point - ob.matrix_world.translation
    ob.data.transform(Matrix.Translation(-d))
    ob.matrix_world.translation = point


def parent_keep(child, parent):
    mw = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = Matrix()
    child.matrix_world = mw


def empty(name, loc, parent=None, size=0.1, typ='PLAIN_AXES'):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = typ
    e.empty_display_size = size
    link(e)
    e.location = loc
    if parent:
        bpy.context.view_layer.update()
        parent_keep(e, parent)
    return e


def export_glb(path, objs=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if objs is not None:
        select_only(objs)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', export_yup=True, export_apply=True,
        use_selection=objs is not None, export_image_format='AUTO', export_jpeg_quality=88,
        export_materials='EXPORT', export_cameras=False, export_lights=False,
        export_animations=False, export_extras=False, export_tangents=False)


# ----------------------------------------------------------------------------
# generic weathered surface
# ----------------------------------------------------------------------------

DUST = srgb(164, 140, 108)


def _scale_col(c, k):
    return (min(c[0] * k, 1), min(c[1] * k, 1), min(c[2] * k, 1), 1.0)


def surface(name, base, var=0.12, var_scale=2.5, rough=0.6, rough_var=0.12, metal=0.0,
            wear_col=None, wear=0.0, wear_rough=None, wear_metal=None, edge_r=0.012,
            edge_w=(0.02, 0.14), wear_scale=14.0, scratches=0.0,
            dust=0.5, dust_col=None, dust_z=(0.15, 2.4), dust_up=0.5, dust_scale=3.0,
            ao=0.6, ao_dist=0.3, bump=0.2, bump_scale=90.0, bump_dist=0.002,
            grain=None, grain_amt=0.0, grain_freq=1.0, extra=None, streaks=0.0,
            bevel_normal=True, blotch=0.0):
    """Weathered PBR surface. Returns the Blender material.

    extra(mb, st) may edit st = {'col','rough','metal','height','nocolwear'} before
    wear/AO/dust layers are applied."""
    mb = MB(name)
    P = mb.pos
    N = mb.nrm
    base = base if len(base) == 4 else (*base, 1.0)
    lf = mb.noise(P, var_scale, 3.0, 0.5)
    col = mb.mixc(mb.smooth(lf, 0.3, 0.7), _scale_col(base, 1 - var), _scale_col(base, 1 + var))
    if blotch > 0:
        bl = mb.smooth(mb.noise(P, 7.0, 4, 0.6), 0.45, 0.75)
        col = mb.mixc(mb.m('MULTIPLY', bl, blotch), col, _scale_col(base, 0.6))
    rough_s = mb.m('ADD', rough, mb.m('MULTIPLY', mb.m('SUBTRACT', mb.noise(P, 6.0, 3), 0.5),
                                      rough_var * 2))
    height = mb.noise(P, bump_scale, 6.0, 0.6)
    st = dict(col=col, rough=rough_s, metal=metal, height=height, mb=mb)

    if grain:
        ax = {'X': (grain_freq * 0.35, 30, 30), 'Y': (30, grain_freq * 0.35, 30),
              'Z': (30, 30, grain_freq * 0.35)}[grain]
        g = mb.noise(mb.aniso(P, *ax), 1.0, 6.0, 0.65, dist=0.6)
        g2 = mb.smooth(g, 0.35, 0.75)
        st['col'] = mb.mixc(mb.m('MULTIPLY', g2, grain_amt), st['col'], _scale_col(base, 0.55))
        st['height'] = mb.m('ADD', mb.m('MULTIPLY', st['height'], 0.4), mb.m('MULTIPLY', g2, 0.8))

    if extra:
        extra(mb, st)

    bn = mb.bevel_normal(edge_r, 8) if (bevel_normal or wear > 0) else None
    if wear > 0:
        e = mb.m('SUBTRACT', 1.0, mb.v('DOT_PRODUCT', bn, N))
        em = mb.smooth(e, edge_w[0], edge_w[1])
        wn = mb.noise(P, wear_scale, 6.0, 0.7)
        wm = mb.smooth(mb.m('MULTIPLY', em, mb.m('ADD', wn, 0.15)), 0.30, 0.55)
        wm = mb.m('MULTIPLY', wm, wear)
        if scratches > 0:
            sn = mb.noise(mb.aniso(P, 5.0, 5.0, 60.0), 1.0, 2.0, 0.5)
            line = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', sn, 0.5)),
                                                    0.0, 0.012))
            patch = mb.smooth(mb.noise(P, 3.0, 2), 0.5, 0.65)
            sc = mb.m('MULTIPLY', mb.m('MULTIPLY', line, patch), scratches)
            sn2 = mb.noise(mb.aniso(P, 60.0, 5.0, 5.0), 1.0, 2.0, 0.5)
            line2 = mb.m('SUBTRACT', 1.0, mb.smooth(mb.m('ABSOLUTE', mb.m('SUBTRACT', sn2, 0.5)),
                                                     0.0, 0.01))
            sc = mb.m('MAXIMUM', sc, mb.m('MULTIPLY', mb.m('MULTIPLY', line2, patch),
                                          scratches * 0.7))
            wm = mb.m('MAXIMUM', wm, sc)
        wcol = wear_col if wear_col is not None else _scale_col(base, 1.6)
        st['col'] = mb.mixc(wm, st['col'], wcol)
        if wear_rough is not None:
            st['rough'] = mb.mixf(wm, st['rough'], wear_rough)
        if wear_metal is not None:
            st['metal'] = mb.mixf(wm, st['metal'], wear_metal)
        st['height'] = mb.m('SUBTRACT', st['height'], mb.m('MULTIPLY', wm, 0.3))

    a = mb.ao(ao_dist, 16)
    if ao > 0:
        aof = mb.mixf(ao, 1.0, a)
        st['col'] = mb.mixc(1.0, st['col'], mb.comb(aof, aof, aof), 'MULTIPLY')

    if streaks > 0:
        s1 = mb.noise(mb.aniso(P, 14.0, 14.0, 0.6), 1.0, 3.0, 0.5)
        sm = mb.m('MULTIPLY', mb.smooth(s1, 0.55, 0.8), streaks)
        st['col'] = mb.mixc(sm, st['col'], _scale_col(base, 0.55))

    if dust > 0:
        x, y, z = mb.xyz(P)
        nx, ny, nz = mb.xyz(N)
        hz = mb.mapr(z, dust_z[0], dust_z[1], 1.0, 0.0)
        hz = mb.m('POWER', hz, 1.6)
        up = mb.smooth(nz, 0.35, 0.9)
        cav = mb.m('SUBTRACT', 1.0, a)
        dn = mb.noise(P, dust_scale, 5.0, 0.62)
        dm = mb.m('ADD', mb.m('ADD', hz, mb.m('MULTIPLY', up, dust_up)),
                  mb.m('MULTIPLY', cav, 0.9))
        dm = mb.m('MULTIPLY', dm, mb.m('MULTIPLY', mb.m('SUBTRACT', mb.m('MULTIPLY', dn, 1.8), 0.35),
                                       dust))
        dm = mb.smooth(dm, 0.15, 0.95)
        dm = mb.m('MULTIPLY', dm, 0.9)
        dc = dust_col or DUST
        st['col'] = mb.mixc(dm, st['col'], dc)
        st['rough'] = mb.mixf(dm, st['rough'], 0.95)
        if not isinstance(st['metal'], (int, float)) or st['metal'] > 0:
            st['metal'] = mb.mixf(dm, st['metal'], 0.0)

    nrm = mb.bump(st['height'], bump, bn, bump_dist) if bump > 0 else bn
    rough_c = mb.m('MINIMUM', mb.m('MAXIMUM', st['rough'], 0.05), 1.0)
    return mb.finish(st['col'], rough_c, st['metal'], nrm)


def add_beam(bm, p0, p1, w, h, up=(0, 0, 1), bevel=0.0, caps=True):
    return add_sweep(bm, [p0, p1], rect_profile(w, h, bevel), up=up, uv=None, caps=caps)


def add_rod(bm, pts, r, n=6, up=(0, 0, 1), caps=True, scales=None, uv=None):
    return add_sweep(bm, pts, circle_profile(r, n), up=up, uv=uv, caps=caps, scales=scales)
