"""Render EEVEE previews of animals.glb, posed the way wildlife.js poses it.

  Blender --background --factory-startup --python tools/blender/preview_animals.py -- \
      [--glb PATH] [--out DIR] [shots...]

shots: bison_side bison_34 hawk_above hawk_below vulture_flight vulture_perched
       carcass (default: all).  Writes <out>/animals_<shot>.png
Rotations are given as three.js Euler angles on the node (x pitch, y yaw,
z roll/dihedral) and converted here, so the numbers match the game code.
"""
import bpy
import math
import os
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
GLB = os.path.join(ROOT, 'public', 'assets', 'models', 'animals.glb')
OUT = os.path.join(HERE, 'previews')
if '--glb' in argv:
    GLB = argv[argv.index('--glb') + 1]
if '--out' in argv:
    OUT = argv[argv.index('--out') + 1]
SHOTS = [a for a in argv if not a.startswith('--') and a not in (GLB, OUT)]
ALL = ['bison_side', 'bison_34', 'hawk_above', 'hawk_below', 'vulture_flight',
       'vulture_perched', 'carcass']
SHOTS = SHOTS or ALL
PERCH = 0.45
os.makedirs(OUT, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=GLB)
    lib = bpy.data.collections.new('LIB')
    bpy.context.scene.collection.children.link(lib)
    for o in list(bpy.context.scene.collection.objects):
        bpy.context.scene.collection.objects.unlink(o)
        lib.objects.link(o)
    lib.hide_render = True
    lib.hide_viewport = True


def clone(name, loc=(0, 0, 0), yaw=0.0, scale=1.0, hide=(), pitch=0.0, roll=0.0):
    """Copy the node tree <name>; yaw/pitch/roll are three.js root angles ('YXZ')."""
    src = bpy.data.objects[name]
    made = {}

    def rec(o, parent):
        c = o.copy()
        bpy.context.scene.collection.objects.link(c)
        c.parent = parent
        made[o.name] = c
        for k in o.children:
            rec(k, c)
    rec(src, None)
    root = made[name]
    root.location = loc
    root.scale = (scale, scale, scale)
    pose(root, pitch, yaw, roll, 'YXZ')
    for h in hide:
        for k, v in made.items():
            if k.startswith(h):
                hide_all(v)
    return made


def hide_all(o, on=True):
    """hide_render on a node and everything under it (gltfpack nests meshes)."""
    o.hide_render = on
    for c in o.children_recursive:
        c.hide_render = on


def R3(ax, ay, az, order='XYZ'):
    """three.js Euler -> Blender rotation matrix (three X = X, Y = Z, Z = -Y)."""
    m = {'X': Matrix.Rotation(ax, 4, 'X'), 'Y': Matrix.Rotation(ay, 4, 'Z'),
         'Z': Matrix.Rotation(-az, 4, 'Y')}
    return m[order[0]] @ m[order[1]] @ m[order[2]]


def pose(o, x=0.0, y=0.0, z=0.0, order='XYZ', dz=0.0, dy=0.0):
    if '_base' not in o:
        o['_base'] = tuple(o.location)
    loc = Vector(o['_base'])
    s = o.scale.copy()
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = R3(x, y, z, order).to_quaternion()
    o.location = loc + Vector((0, -dz, dy))     # three +Z forward = Blender -Y
    o.scale = s


def node(made, n):
    return made[n]


def setup(res=(1600, 900), sun_el=24, sun_az=215, fill=True, ground=True, gcol=(0.40, 0.30, 0.19)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.eevee.taa_render_samples = 64
    try:
        sc.eevee.use_shadows = True
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
        sky.sun_elevation = math.radians(sun_el)
        sky.sun_rotation = math.radians(sun_az - 90)
    except Exception:
        pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.28
    sd = bpy.data.lights.new('Sun', 'SUN')
    sd.energy = 4.6
    sd.color = (1.0, 0.82, 0.62)
    sd.angle = math.radians(2.0)
    sun = bpy.data.objects.new('Sun', sd)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(90 - sun_el), 0, math.radians(sun_az))
    if fill:   # warm bounce off the dry ground: what lights an underwing
        fd = bpy.data.lights.new('Fill', 'SUN')
        fd.energy = 1.3
        fd.color = (1.0, 0.86, 0.68)
        f = bpy.data.objects.new('Fill', fd)
        sc.collection.objects.link(f)
        f.rotation_euler = (math.radians(180), 0, 0)
        fd.use_shadow = False
    if ground:
        me = bpy.data.meshes.new('ground')
        s = 60
        me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new('ground', me)
        sc.collection.objects.link(g)
        gm = bpy.data.materials.new('dirt')
        gm.use_nodes = True
        p = gm.node_tree.nodes['Principled BSDF']
        tex = gm.node_tree.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 3.0
        ramp = gm.node_tree.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = (gcol[0] * 0.8, gcol[1] * 0.8, gcol[2] * 0.8, 1)
        ramp.color_ramp.elements[1].color = (gcol[0] * 1.1, gcol[1] * 1.1, gcol[2] * 1.1, 1)
        gm.node_tree.links.new(tex.outputs['Fac'], ramp.inputs[0])
        gm.node_tree.links.new(ramp.outputs[0], p.inputs['Base Color'])
        p.inputs['Roughness'].default_value = 0.95
        me.materials.append(gm)
    cam_d = bpy.data.cameras.new('Cam')
    cam = bpy.data.objects.new('Cam', cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def look(cam, loc, tgt, lens=50, ortho=None):
    cam.location = loc
    d = Vector(tgt) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    if ortho:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = ortho
    cam.data.clip_start = 0.02


def render(name):
    p = os.path.join(OUT, 'animals_%s.png' % name)
    bpy.context.scene.render.filepath = p
    bpy.ops.render.render(write_still=True)
    print('wrote', p)


def vulture(pose_, loc, yaw=0.0, ground=0.0):
    """pose_: flight | stand | hunch | feed | spread | squabble"""
    m = clone('Vulture', (loc[0], loc[1], ground), yaw)
    r = m['Vulture']
    wl, wr, hd = m['Vulture_WingL'], m['Vulture_WingR'], m['Vulture_Head']
    fold, legs = m['Vulture_Folded'], m['Vulture_Legs']
    if pose_ == 'flight':
        hide_all(fold); hide_all(legs)
        pose(wl, 0, 0, 0.30)
        pose(wr, 0, 0, -0.30)
        pose(r, 0, yaw, 0.0, 'YXZ')
        return m
    if pose_ in ('stand', 'hunch', 'feed'):
        hide_all(wl); hide_all(wr)
    else:
        hide_all(fold)
    pitch = {'stand': -PERCH - 0.25, 'hunch': -PERCH - 0.25, 'feed': -PERCH + 0.6,
             'spread': -PERCH - 0.30, 'squabble': -PERCH + 0.12}[pose_]
    pose(r, pitch, yaw, 0.0, 'YXZ')
    pose(legs, -(pitch + PERCH))          # legs stay upright under a tipped body
    if pose_ in ('stand', 'hunch'):
        pose(hd, 0.9, dz=-0.09, dy=-0.05, y=0.4 if pose_ == 'stand' else -0.3)
        pose(fold, 0.0, dy=-0.02)
    elif pose_ == 'feed':
        pose(hd, 0.55, dz=0.03)
    elif pose_ == 'spread':
        pose(hd, 0.45)
        pose(wl, 0.0, 0.10, -0.12)
        pose(wr, 0.0, -0.10, 0.12)
    elif pose_ == 'squabble':
        pose(hd, 0.10, dz=0.02)
        pose(wl, 0.0, 0.85, 0.30)
        pose(wr, 0.0, -0.85, -0.30)
    return m


def empty_local(name):
    e = bpy.data.objects[name]
    return e.matrix_world.translation.copy(), e.matrix_world.to_euler().z


for shot in SHOTS:
    reset()
    if shot == 'bison_side':
        cam = setup(sun_el=28, sun_az=160)
        clone('Buffalo', hide=('Buffalo_HornCow',))
        look(cam, (7.5, -0.2, 1.1), (0.0, -0.2, 0.95), ortho=3.9)
        render(shot)
    elif shot == 'bison_34':
        cam = setup(sun_el=24, sun_az=200)
        m = clone('Buffalo', hide=('Buffalo_HornCow',))
        pose(m['Buffalo_Head'], 0.12)
        c = clone('Buffalo', (-2.4, -0.6, 0), 0.9, 0.82, hide=('Buffalo_HornBull',))
        pose(c['Buffalo_Head'], 0.65)                     # grazing
        c['Buffalo_Beard'].scale = (0.8, 0.6, 0.6)
        look(cam, (4.6, -5.2, 1.7), (-0.8, 0.0, 0.9), 42)
        render(shot)
    elif shot in ('hawk_above', 'hawk_below'):
        cam = setup(ground=False, sun_el=55, sun_az=200)
        m = clone('Hawk')
        pose(m['Hawk_WingL'], 0, 0, 0.10)
        pose(m['Hawk_WingR'], 0, 0, -0.10)
        if shot == 'hawk_above':
            look(cam, (0.0, 0.05, 1.6), (0.0, 0.05, 0.0), ortho=1.45)
        else:
            look(cam, (0.0, 0.05, -1.6), (0.0, 0.05, 0.0), ortho=1.45)
            cam.rotation_euler = (math.pi, 0, math.pi)
        render(shot)
    elif shot == 'vulture_flight':
        cam = setup(ground=False, sun_el=55, sun_az=200)
        vulture('flight', (0, 0), 0.0)
        look(cam, (0.0, -0.1, -2.0), (0.0, -0.1, 0.3), ortho=2.0)
        cam.rotation_euler = (math.pi, 0, math.pi)
        render(shot)
        # and a low three-quarter view from behind: the V and the teeter
        bpy.data.objects['Cam'].data.type = 'PERSP'
        look(cam, (-1.6, 3.2, 0.05), (0.0, -0.05, 0.32), 55)
        render('vulture_flight_v')
    elif shot == 'vulture_perched':
        cam = setup(sun_el=26, sun_az=205)
        vulture('stand', (0.0, 0.0), -0.5)
        vulture('spread', (1.1, 0.8), 2.4)
        vulture('hunch', (-0.9, 0.7), 0.8)
        look(cam, (2.6, -3.2, 0.9), (0.1, 0.3, 0.35), 50)
        render(shot)
        look(cam, (1.25, -0.2, 0.40), (0.0, 0.0, 0.32), 50)
        render('vulture_head')
    elif shot == 'carcass':
        cam = setup(sun_el=22, sun_az=210, gcol=(0.46, 0.36, 0.22))
        clone('Carcass')
        bpy.context.view_layer.update()
        p, rz = empty_local('Carcass_Feed1')
        vulture('feed', (p.x, p.y), rz, p.z)
        p, rz = empty_local('Carcass_Feed2')
        vulture('feed', (p.x, p.y), rz, p.z)
        p, rz = empty_local('Carcass_Perch')
        vulture('spread', (p.x, p.y), rz + 0.4, p.z)
        vulture('hunch', (-1.6, 1.2), 2.2)
        vulture('stand', (1.9, -0.6), -2.0)
        vulture('squabble', (1.5, 1.6), -2.6)
        vulture('hunch', (-1.9, -1.4), 0.9)
        f = vulture('flight', (0.4, 2.8), 2.8, 2.2)
        look(cam, (4.6, -4.6, 2.3), (0.1, 0.1, 0.25), 38)
        render(shot)
        look(cam, (1.8, -1.9, 1.3), (0.1, -0.2, 0.25), 40)
        render('carcass_close')
