"""Render EEVEE previews of the team-horse breed GLBs (not part of the game build).

  Blender --background --factory-startup --python tools/blender/preview_horses.py -- [views...] [--out DIR]
views: singles lineup hitch (default: all)
Writes tools/blender/previews/horse_<breed>_{side,front34,head,legs,gallop}.png,
horse_breeds_{side,front34}.png and horse_hitch_{side,game,front34}.png.

The hitch view lays the team out like src/game/coach.js does on a straight road
(same slots, bars, traces, pole straps and six lines) so it can be checked here.
"""
import bpy
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
MODELS = os.path.join(ROOT, 'public', 'assets', 'models')
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUTS = [os.path.join(HERE, 'previews')]
if '--out' in argv:
    OUTS.append(argv[argv.index('--out') + 1])
    del argv[argv.index('--out'):argv.index('--out') + 2]
BREEDS = ['clydesdale', 'clevelandbay', 'thoroughbred']
if '--breeds' in argv:
    BREEDS = argv[argv.index('--breeds') + 1].split(',')
    del argv[argv.index('--breeds'):argv.index('--breeds') + 2]
VIEWS = argv or ['singles', 'lineup', 'hitch']

# coach.js team layout (three.js coach-local: x left, y up, z forward)
SLOTS = [('clydesdale', 0.58, 3.70), ('clydesdale', -0.58, 3.70), ('clevelandbay', 0.55, 7.35),
         ('clevelandbay', -0.55, 7.35), ('thoroughbred', 0.52, 11.00), ('thoroughbred', -0.52, 11.00)]
POLE0, POLE1 = Vector((0, 0.585, 1.2)), Vector((0, 0.92, 3.4))
POLE_HEAD_Z = 4.55
SINGLETREE = [(0.55, 0.655, 1.88), (-0.55, 0.655, 1.88)]


def b3(v):  # three.js -> Blender
    return Vector((v[0], -v[2], v[1]))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.eevee.taa_render_samples = 48
    try:
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    w = bpy.data.worlds.new('W')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    sky = nt.nodes.new('ShaderNodeTexSky')
    try:
        sky.sky_type = 'NISHITA'
        sky.sun_elevation = math.radians(22)
        sky.sun_rotation = math.radians(120)
    except Exception:
        pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.4
    sd = bpy.data.lights.new('Sun', 'SUN')
    sd.energy = 4.2
    sd.color = (1.0, 0.86, 0.68)
    sd.angle = math.radians(1.5)
    sun = bpy.data.objects.new('Sun', sd)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(55), 0, math.radians(235))
    me = bpy.data.meshes.new('ground')
    s = 80
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new('ground', me)
    sc.collection.objects.link(g)
    gm = bpy.data.materials.new('dirt')
    gm.use_nodes = True
    p = gm.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (0.36, 0.27, 0.17, 1)
    p.inputs['Roughness'].default_value = 0.95
    me.materials.append(gm)
    cd = bpy.data.cameras.new('Cam')
    cam = bpy.data.objects.new('Cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def look(cam, loc, tgt, lens=50):
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens


def render(name):
    for d in OUTS:
        os.makedirs(d, exist_ok=True)
        bpy.context.scene.render.filepath = os.path.join(d, name + '.png')
        bpy.ops.render.render(write_still=True)


def load(path, loc=(0, 0, 0), action='Idle', frame=0, rz=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    for r in roots:
        r.location = Vector(loc)
        r.rotation_euler = (0, 0, rz)
    arm = next(o for o in new if o.type == 'ARMATURE')
    acts = {a.name.split('.')[0]: a for a in bpy.data.actions}
    if arm.animation_data is None:
        arm.animation_data_create()
    act = None
    for tr in arm.animation_data.nla_tracks:
        for st in tr.strips:
            if st.action and st.action.name.startswith(action):
                act = st.action
    act = act or acts.get(action)
    for tr in list(arm.animation_data.nla_tracks):
        arm.animation_data.nla_tracks.remove(tr)
    arm.animation_data.action = act
    for o in new:  # packed GLBs put the mesh under a node named Saddle
        if o.type == 'MESH' and any(m and m.name.startswith('Saddle') for m in o.data.materials):
            o.hide_render = True
    return dict(objs=new, arm=arm, act=act, frame=frame)


def pose(h, frame):
    act = h['act']
    f0 = act.frame_range[0] if act else 0
    bpy.context.scene.frame_set(int(f0 + frame))


def emp(h, name):
    for o in h['objs']:
        if o.type == 'EMPTY' and o.name.split('.')[0] == name:
            return o.matrix_world.translation.copy()
    return None


def tube(name, pts, r, col, sides=6):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = max(1, sides // 4)
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p.x, p.y, p.z, 1)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.get('m_' + name) or bpy.data.materials.new('m_' + name)
    m.use_nodes = True
    bs = m.node_tree.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value = (*col, 1)
    bs.inputs['Roughness'].default_value = 0.5
    cu.materials.append(m)
    return ob


def sag(a, b, s, n=6):
    return [a.lerp(b, i / n) - Vector((0, 0, s * math.sin(math.pi * i / n))) for i in range(n + 1)]


def singles():
    for br in BREEDS:
        cam = reset()
        h = load(os.path.join(MODELS, 'horse_%s.glb' % br))
        pose(h, 0)
        look(cam, (6.2, -0.5, 1.15), (0, -0.25, 0.95), 50)
        render('horse_%s_side' % br)
        look(cam, (3.4, -4.4, 1.9), (0, -0.4, 1.05), 50)
        render('horse_%s_front34' % br)
        hd = 0.5 * (emp(h, 'Bit_L') + emp(h, 'HeadRing_L'))
        look(cam, hd + Vector((1.25, -0.9, 0.2)), hd, 55)
        render('horse_%s_head' % br)
        look(cam, (1.8, -1.9, 0.55), (0.05, 0.0, 0.3), 45)
        render('horse_%s_legs' % br)
        look(cam, (-3.2, 4.2, 2.1), (0, 0.2, 1.05), 45)
        render('horse_%s_rear34' % br)
        cam = reset()
        h = load(os.path.join(MODELS, 'horse_%s.glb' % br), action='Gallop')
        pose(h, 10)
        look(cam, (6.2, -0.5, 1.15), (0, -0.25, 0.95), 50)
        render('horse_%s_gallop' % br)


def lineup():
    cam = reset()
    hs = []
    for i, br in enumerate(BREEDS):
        hs.append(load(os.path.join(MODELS, 'horse_%s.glb' % br), loc=(0, (i - 1) * 3.1, 0)))
    ref = load(os.path.join(MODELS, 'horse.glb'), loc=(0, 2 * 3.1 + 0.2, 0))  # enemy horse for scale
    for o in ref['objs']:
        if o.type == 'MESH' and o.name.startswith('Harness'):
            o.hide_render = True
    bpy.context.scene.frame_set(0)
    look(cam, (17.5, 0.9, 1.3), (0, 0.9, 1.0), 42)
    render('horse_breeds_side')
    look(cam, (7.5, -9.0, 2.6), (0, 0.8, 1.0), 40)
    render('horse_breeds_front34')


def hitch(action='Gallop', frame=6):
    cam = reset()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, 'stagecoach_treasure.glb'))
    team = []
    for i, (br, x, z) in enumerate(SLOTS):
        h = load(os.path.join(MODELS, 'horse_%s.glb' % br), loc=b3((x, 0, z)), action=action)
        team.append((h, x, z))
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    wood, iron, leather = (0.62, 0.45, 0.17), (0.05, 0.05, 0.055), (0.022, 0.017, 0.013)
    d = (POLE1 - POLE0).normalized()
    ph = POLE1 + d * ((POLE_HEAD_Z - POLE1.z) / d.z)
    tube('pole', [b3(POLE1), b3(ph)], 0.033, wood)
    tube('polehead', [b3(ph - d * 0.08), b3(ph + d * 0.04)], 0.04, iron)
    P = lambda h, n: emp(h, n)
    wl, wr, sl, sr, ll, lr = [t[0] for t in team]
    # wheelers: traces to the coach's singletrees, pole straps to the pole head
    for (h, x, z), st in zip(team[:2], SINGLETREE):
        c = b3(st)
        for side, dx in (('_L', 0.31), ('_R', -0.31)):
            tube('trace', sag(P(h, 'Trace' + side), c + Vector((dx, 0, 0)), 0.03), 0.012, leather)
        tube('polestrap', [P(h, 'PoleStrap'), b3(ph)], 0.01, leather)

    def bar(cen, half, n):
        a, b = cen - Vector((half, 0, 0)), cen + Vector((half, 0, 0))
        tube(n, [a, b], 0.03, wood)
        return a, b

    def pair_to(hs, cen):
        # evener at cen with singletrees at its ends; each horse's traces to its singletree
        ends = bar(cen, 0.54, 'evener')
        for h, e in zip(hs, (ends[1], ends[0])):
            tube('singletree', [e - Vector((0.3, 0, 0)), e + Vector((0.3, 0, 0))], 0.022, wood)
            for side, dx in (('_L', 0.3), ('_R', -0.3)):
                tube('trace', sag(P(h, 'Trace' + side), e + Vector((dx, 0, 0)), 0.03), 0.012, leather)

    pair_to([sl, sr], b3(ph) + Vector((0, -0.12, -0.03)))
    smid = b3((0, 0.95, 7.35 + 1.25))
    tube('leadchain', [b3(ph), smid], 0.008, iron)
    pair_to([ll, lr], smid)
    # six lines from the driver's hands (Seat_Driver + hand offset) through terrets to the bits
    hand = b3((0.33 - 0.05, 1.38 + 0.93 + 0.45, 1.3775 - 0.0675 + 0.35))
    for side, near in (('_L', True), ('_R', False)):
        w, s, l = (wl, sl, ll) if near else (wr, sr, lr)
        other = {id(wl): wr, id(wr): wl, id(sl): sr, id(sr): sl, id(ll): lr, id(lr): ll}
        inner = '_R' if near else '_L'
        for h, via in ((w, []), (s, [P(w, 'HeadRing' + side)]), (l, [P(w, 'HeadRing' + side) + Vector((0, 0, 0.1)), P(s, 'HeadRing' + side) + Vector((0, 0, 0.1))])):
            pts = [hand] + via + [P(h, 'Terret' + side), P(h, 'HameTerret' + side), P(h, 'Bit' + side)]
            tube('line', pts, 0.008, leather)
            tube('coupling', [P(h, 'HameTerret' + inner), P(other[id(h)], 'Bit' + inner)], 0.005, leather)
    look(cam, (9.5, -6.5, 2.2), (0, -6.2, 1.1), 28)
    render('horse_hitch_side')
    look(cam, (-1.6, 3.2, 4.2), (0.2, -7.0, 1.2), 35)
    render('horse_hitch_game')
    look(cam, (5.5, -16.5, 2.6), (0, -6.5, 1.2), 32)
    render('horse_hitch_front34')


if 'singles' in VIEWS:
    singles()
if 'lineup' in VIEWS:
    lineup()
if 'hitch' in VIEWS:
    hitch()
