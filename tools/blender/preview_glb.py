"""Render EEVEE preview PNGs of an exported GLB (what the game actually loads).

  Blender --background --factory-startup --python tools/blender/preview_glb.py -- \
      <file.glb> <out_prefix> [coach|weapons]

Warm low sun + sky ambient, dusty ground. Writes <out_prefix>_<view>.png.
"""
import bpy
import math
import sys
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
GLB, PREFIX = args[0], args[1]
MODE = args[2] if len(args) > 2 else 'coach'

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=GLB)

sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'
try:
    sc.eevee.taa_render_samples = 64
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
    sky.sun_elevation = math.radians(14)
    sky.sun_rotation = math.radians(120)
except Exception:
    pass
nt.links.new(sky.outputs[0], bg.inputs[0])
bg.inputs[1].default_value = 0.35

sun_d = bpy.data.lights.new('Sun', 'SUN')
sun_d.energy = 4.5
sun_d.color = (1.0, 0.78, 0.55)
sun_d.angle = math.radians(1.5)
sun = bpy.data.objects.new('Sun', sun_d)
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(68), 0, math.radians(215))

if MODE == 'coach':
    me = bpy.data.meshes.new('ground')
    s = 40
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new('ground', me)
    sc.collection.objects.link(g)
    gm = bpy.data.materials.new('dirt')
    gm.use_nodes = True
    p = gm.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (0.32, 0.22, 0.13, 1)
    p.inputs['Roughness'].default_value = 0.95
    me.materials.append(gm)
    views = {
        'game': ((-2.2, 8.2, 3.6), (0.0, -0.6, 1.6), 45),
        'front34': ((5.2, -6.5, 2.1), (0.0, -0.7, 1.3), 45),
        'side': ((9.5, -0.9, 1.4), (0.0, -0.9, 1.3), 40),
        'rear_low': ((-2.2, 5.0, 1.3), (0.0, 0.3, 1.2), 45),
        'top': ((-3.0, 3.5, 6.0), (0.0, -0.3, 1.9), 45),
    }
else:
    views = {
        'side': ((0.0, 0.0, 0.0), None, 0),
    }

cam_d = bpy.data.cameras.new('Cam')
cam = bpy.data.objects.new('Cam', cam_d)
sc.collection.objects.link(cam)
sc.camera = cam


def look(loc, tgt, lens):
    cam.location = loc
    d = Vector(tgt) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam_d.lens = lens


if MODE == 'coach':
    for name, (loc, tgt, lens) in views.items():
        look(loc, tgt, lens)
        sc.render.filepath = '%s_%s.png' % (PREFIX, name)
        bpy.ops.render.render(write_still=True)
else:
    # weapons: lay each root object out side by side, orthographic side + 3/4 views
    roots = [o for o in bpy.data.objects if o.parent is None and o.type in ('MESH', 'EMPTY')
             and o.name not in ('Cam', 'Sun')]
    roots.sort(key=lambda o: o.name)
    y = 0.0
    for o in roots:
        o.location = (0, 0, y)
        y += 0.3
    sun.rotation_euler = (math.radians(50), 0, math.radians(150))
    bg.inputs[1].default_value = 0.6
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = 1.6
    cam.location = (3.0, -0.2, 0.3)
    cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    sc.render.filepath = PREFIX + '_side.png'
    bpy.ops.render.render(write_still=True)
    cam_d.type = 'PERSP'
    for o in roots:
        pass
    look((1.1, -0.9, y / 2 + 0.25), (0, -0.25, y / 2 - 0.15), 50)
    sc.render.filepath = PREFIX + '_34.png'
    bpy.ops.render.render(write_still=True)
