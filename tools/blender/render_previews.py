"""Render EEVEE preview images of the exported GLBs (not part of the game build).

  Blender --background --factory-startup --python tools/blender/render_previews.py -- [names...]
names: lineup_big lineup_small forest snow desert town town_street (default: all available)
Output: tools/blender/previews/*.png
"""
import bpy, math, random, os, sys
from mathutils import Vector, Euler, noise

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(HERE, 'previews')
os.makedirs(OUT, exist_ok=True)
V = Vector
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
RES = (1600, 900)
SAMPLES = 48


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_lib(path):
    """Import a GLB and turn every root into a collection we can instance."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    lib = {}
    for o in new:
        if o.parent is None:
            col = bpy.data.collections.new('LIB_' + o.name)
            stack = [o]
            while stack:
                x = stack.pop()
                for c in list(x.users_collection):
                    c.objects.unlink(x)
                col.objects.link(x)
                stack.extend(x.children)
            lib[o.name] = col
    return lib


def inst(lib, name, loc, rz=0.0, s=1.0, tilt=(0, 0)):
    e = bpy.data.objects.new('i_' + name, None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = lib[name]
    e.location = V(loc)
    e.rotation_euler = Euler((tilt[0], tilt[1], rz))
    e.scale = (s, s, s)
    bpy.context.scene.collection.objects.link(e)
    return e


def setup_render(res=RES, samples=SAMPLES, exposure=0.0, look='AgX - Medium High Contrast'):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_shadows = True
    sc.eevee.volumetric_end = 600
    sc.eevee.volumetric_tile_size = '4'
    try:
        sc.eevee.use_raytracing = True
        sc.eevee.use_fast_gi = True
    except Exception:
        pass
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = look
    except Exception:
        pass
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = 'PNG'


def world(horizon=(1.0, 0.72, 0.45), zenith=(0.30, 0.45, 0.72), strength=1.0, haze=0.004, haze_col=(0.95, 0.8, 0.62)):
    w = bpy.data.worlds.new('W')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ramp.inputs[0])
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*[c * 0.6 for c in horizon], 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (*zenith, 1)
    e = ramp.color_ramp.elements.new(0.08)
    e.color = (*horizon, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = strength
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    if haze > 0:
        # world volumes render black in EEVEE 5.x background mode -> use a big volume box
        bpy.ops.mesh.primitive_cube_add(size=1)
        c = bpy.context.object
        c.name = 'Haze'
        c.scale = (1500, 1500, 260)
        c.location = (0, 0, 110)
        m = bpy.data.materials.new('haze')
        m.use_nodes = True
        mt = m.node_tree
        for n in list(mt.nodes):
            if n.type != 'OUTPUT_MATERIAL':
                mt.nodes.remove(n)
        vol = mt.nodes.new('ShaderNodeVolumePrincipled')
        vol.inputs['Density'].default_value = haze
        vol.inputs['Color'].default_value = (*haze_col, 1)
        vol.inputs['Anisotropy'].default_value = 0.55
        mt.links.new(vol.outputs['Volume'], mt.nodes['Material Output'].inputs['Volume'])
        c.data.materials.append(m)


def sun(elev_deg, azim_deg, energy=4.0, color=(1.0, 0.78, 0.55), angle=1.5):
    l = bpy.data.lights.new('Sun', 'SUN')
    l.energy = energy
    l.color = color
    l.angle = math.radians(angle)
    o = bpy.data.objects.new('Sun', l)
    # sun direction: light travels along -Z of the object
    o.rotation_euler = Euler((math.radians(90 - elev_deg), 0, math.radians(azim_deg)))
    bpy.context.scene.collection.objects.link(o)
    return o


def ground(size=600, colors=((0.34, 0.28, 0.15), (0.42, 0.33, 0.22)), hills=0.0, seed=0, subdiv=160, snow=False):
    me = bpy.data.meshes.new('ground')
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=subdiv, y_segments=subdiv, size=size / 2)
    off = V((seed * 13.1, seed * 7.7, 0))
    for v in bm.verts:
        p = v.co
        h = noise.fractal(p * 0.012 + off, 0.6, 2.0, 4) * hills
        v.co.z = h * min(1.0, (p.length / 30.0) ** 1.5)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new('ground', me)
    bpy.context.scene.collection.objects.link(o)
    m = bpy.data.materials.new('ground')
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.08
    nz.inputs['Detail'].default_value = 8
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 3.0
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (*colors[0], 1)
    mix.inputs['B'].default_value = (*colors[1], 1)
    mr = nt.nodes.new('ShaderNodeMath')
    mr.operation = 'MULTIPLY_ADD'
    nt.links.new(nz.outputs['Fac'], mr.inputs[0])
    mr.inputs[1].default_value = 1.0
    nt.links.new(nz2.outputs['Fac'], mr.inputs[2])
    mr2 = nt.nodes.new('ShaderNodeMapRange')
    mr2.inputs['From Min'].default_value = 0.7
    mr2.inputs['From Max'].default_value = 1.3
    nt.links.new(mr.outputs[0], mr2.inputs['Value'])
    nt.links.new(mr2.outputs['Result'], mix.inputs['Factor'])
    nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.95
    o.data.materials.append(m)
    return o


def height_at(gnd, x, y):
    # ray down onto the ground object
    from mathutils.bvhtree import BVHTree
    if not hasattr(height_at, 'bvh'):
        dg = bpy.context.evaluated_depsgraph_get()
        height_at.bvh = BVHTree.FromObject(gnd, dg)
    loc, n, i, d = height_at.bvh.ray_cast(V((x, y, 500)), V((0, 0, -1)))
    return loc.z if loc else 0.0


def camera(loc, target, lens=35):
    c = bpy.data.cameras.new('Cam')
    c.lens = lens
    c.clip_end = 2000
    o = bpy.data.objects.new('Cam', c)
    o.location = V(loc)
    d = V(target) - V(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(o)
    bpy.context.scene.camera = o
    return o


def render(name):
    p = os.path.join(OUT, name + '.png')
    bpy.context.scene.render.filepath = p
    bpy.ops.render.render(write_still=True)
    print('RENDERED', p)


PROPS = os.path.join(ROOT, 'public/assets/models/props.glb')
TOWN = os.path.join(ROOT, 'public/assets/models/town.glb')


def lineup_big():
    reset()
    lib = import_lib(PROPS)
    setup_render()
    world(haze=0.0004)
    sun(24, -35, energy=4.5)
    ground(colors=((0.36, 0.30, 0.18), (0.44, 0.35, 0.24)))
    row = ['CliffChunk', 'Pine_A', 'Pine_B', 'Pine_Snow', 'DeadTree', 'Saguaro', 'Joshua', 'Windmill', 'TelegraphPole', 'Boulder_Big']
    widths = [10, 8, 5.5, 7, 6, 3, 3.6, 3.6, 2, 4.6]
    x = 0
    for n, w in zip(row, widths):
        x += w / 2
        inst(lib, n, (x, 0, 0), rz=0.3 if n != 'Windmill' else 0.5)
        x += w / 2 + 1.0
    camera((x / 2, -62, 8.0), (x / 2, 0, 6.5), lens=30)
    render('lineup_big')


def lineup_small():
    reset()
    lib = import_lib(PROPS)
    setup_render()
    world(haze=0.0003)
    sun(28, -40, energy=4.5)
    ground(colors=((0.36, 0.30, 0.18), (0.44, 0.35, 0.24)))
    row1 = ['Rock_A', 'Rock_B', 'Rock_C', 'Sagebrush', 'Tumbleweed', 'CowSkull', 'GraveCross', 'Barrel', 'Crate']
    w1 = [1.1, 1.9, 1.6, 1.5, 1.0, 0.8, 2.0, 0.6, 0.8]
    row2 = ['Fence_Rail', 'Signpost', 'WaterTrough', 'Wagon_Wreck']
    w2 = [3.2, 2.3, 2.0, 4.7]
    x = 0
    for n, w in zip(row1, w1):
        x += w / 2
        inst(lib, n, (x, 0, 0), rz=0.0)
        x += w / 2 + 0.6
    x1 = x
    x = 0
    for n, w in zip(row2, w2):
        x += w / 2
        inst(lib, n, (x + (x1 - 14.5) / 2, 4.0, 0), rz=0.0)
        x += w / 2 + 0.8
    camera((x1 / 2 - 1, -16, 3.6), (x1 / 2 - 1, 1.5, 0.7), lens=32)
    render('lineup_small')


def forest():
    reset()
    lib = import_lib(PROPS)
    setup_render(exposure=0.2)
    world(horizon=(1.0, 0.70, 0.42), zenith=(0.35, 0.48, 0.70), haze=0.0035, haze_col=(1.0, 0.82, 0.6))
    sun(12, 160, energy=5.0, color=(1.0, 0.72, 0.45))  # low, backlit
    g = ground(colors=((0.32, 0.30, 0.14), (0.45, 0.38, 0.22)), hills=14, seed=3)
    rnd = random.Random(4)
    pts = []
    for i in range(220):
        x, y = rnd.uniform(-90, 90), rnd.uniform(8, 170)
        if abs(x - (y * 0.25 - 6)) < 5:  # keep a clearing / road
            continue
        if any((V((x, y)) - q).length < 4.0 for q in pts):
            continue
        pts.append(V((x, y)))
        r = rnd.random()
        n = 'Pine_A' if r < 0.55 else ('Pine_B' if r < 0.93 else 'DeadTree')
        inst(lib, n, (x, y, height_at(g, x, y) - 0.1), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.8, 1.2))
    for i in range(160):
        x, y = rnd.uniform(-50, 50), rnd.uniform(2, 90)
        inst(lib, 'Sagebrush', (x, y, height_at(g, x, y)), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.7, 1.3))
    for i in range(30):
        x, y = rnd.uniform(-50, 50), rnd.uniform(4, 110)
        n = rnd.choice(['Rock_A', 'Rock_B', 'Rock_C', 'Boulder_Big'])
        inst(lib, n, (x, y, height_at(g, x, y)), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.7, 1.4))
    for i, (x, y) in enumerate(((-5, 14), (-2, 30), (4, 42))):
        inst(lib, 'Fence_Rail', (x, y, height_at(g, x, y)), rz=1.2)
    cz = height_at(g, -2, 4)
    camera((-2, 4, cz + 2.0), (6, 60, cz + 6), lens=26)
    render('forest')


def snow():
    reset()
    lib = import_lib(PROPS)
    setup_render(exposure=0.0)
    world(horizon=(0.80, 0.84, 0.90), zenith=(0.45, 0.52, 0.62), strength=1.4, haze=0.006, haze_col=(0.85, 0.88, 0.95))
    sun(20, 120, energy=2.5, color=(0.95, 0.93, 0.9))
    g = ground(colors=((0.78, 0.80, 0.84), (0.55, 0.52, 0.48)), hills=18, seed=8)
    rnd = random.Random(9)
    pts = []
    for i in range(200):
        x, y = rnd.uniform(-70, 70), rnd.uniform(6, 150)
        if any((V((x, y)) - q).length < 3.5 for q in pts):
            continue
        pts.append(V((x, y)))
        n = 'Pine_Snow' if rnd.random() < 0.8 else 'Pine_B'
        inst(lib, n, (x, y, height_at(g, x, y) - 0.1), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.75, 1.3))
    for i in range(25):
        x, y = rnd.uniform(-40, 40), rnd.uniform(3, 80)
        inst(lib, rnd.choice(['Rock_A', 'Boulder_Big', 'Rock_B']), (x, y, height_at(g, x, y)), rz=rnd.uniform(0, 6.28))
    cz = height_at(g, 0, -6)
    camera((0, -6, cz + 2.5), (0, 50, cz + 7), lens=30)
    render('snow')


def desert():
    reset()
    lib = import_lib(PROPS)
    setup_render(exposure=0.1)
    world(horizon=(1.0, 0.62, 0.38), zenith=(0.32, 0.40, 0.62), haze=0.006, haze_col=(1.0, 0.7, 0.5))
    sun(10, -130, energy=5.0, color=(1.0, 0.62, 0.38))
    g = ground(colors=((0.55, 0.36, 0.22), (0.62, 0.45, 0.30)), hills=8, seed=12)
    rnd = random.Random(12)
    for i in range(10):
        x, y = rnd.uniform(-90, 90), rnd.uniform(60, 160)
        inst(lib, 'CliffChunk', (x, y, height_at(g, x, y) - 0.5), rz=rnd.uniform(0, 6.28), s=rnd.uniform(1.5, 3.0))
    for i in range(40):
        x, y = rnd.uniform(-60, 60), rnd.uniform(5, 90)
        inst(lib, rnd.choice(['Saguaro', 'Saguaro', 'Joshua']), (x, y, height_at(g, x, y)), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.7, 1.2))
    for i in range(120):
        x, y = rnd.uniform(-40, 40), rnd.uniform(2, 60)
        inst(lib, rnd.choice(['Sagebrush', 'Sagebrush', 'Rock_C', 'Rock_A', 'Rock_B', 'Tumbleweed']), (x, y, height_at(g, x, y)), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.7, 1.3))
    inst(lib, 'Wagon_Wreck', (4, 12, height_at(g, 4, 12)), rz=0.7)
    inst(lib, 'CowSkull', (1.5, 8, height_at(g, 1.5, 8)), rz=2.0)
    inst(lib, 'Windmill', (-14, 30, height_at(g, -14, 30)), rz=0.4)
    inst(lib, 'WaterTrough', (-11, 27, height_at(g, -11, 27)), rz=0.4)
    inst(lib, 'Signpost', (-2.5, 6, height_at(g, -2.5, 6)), rz=0.2)
    for i in range(6):
        x, y = 7 + i * 7, 4 + i * 9
        inst(lib, 'TelegraphPole', (x, y, height_at(g, x, y)), rz=0.65)
    inst(lib, 'GraveCross', (-5, 10, height_at(g, -5, 10)), rz=0.3)
    cz = height_at(g, 0, -2)
    camera((0, -2, cz + 1.9), (2, 40, cz + 3.5), lens=30)
    render('desert')


def town_scene(name, cam, target, lens=30, sunp=(14, -120)):
    reset()
    lib = import_lib(TOWN)
    plib = import_lib(PROPS)
    setup_render(exposure=0.15)
    world(horizon=(1.0, 0.66, 0.40), zenith=(0.33, 0.43, 0.66), haze=0.0025, haze_col=(1.0, 0.76, 0.55))
    sun(sunp[0], sunp[1], energy=5.0, color=(1.0, 0.68, 0.42))
    ground(colors=((0.50, 0.38, 0.26), (0.58, 0.46, 0.33)))
    # street along X; north side buildings face -Y... we place: north row (y=+8) facing street (-Y, default)
    north = ['Saloon', 'Boardwalk', 'GeneralStore', 'Bank', 'Hotel', 'Sheriff']
    south = ['Livery', 'Shack', 'Church', 'WaterTower', 'Gallows']
    widths = {}
    for n, col in lib.items():
        xs = []
        for o in col.all_objects:
            if o.type == 'MESH':
                xs += [(o.matrix_world @ V(c)).x for c in o.bound_box]
        widths[n] = (max(xs) - min(xs)) if xs else 4
    x = -40
    for n in north:
        if n not in lib:
            continue
        w = widths[n]
        x += w / 2
        inst(lib, n, (x, 7.5, 0))
        x += w / 2 + 1.5
    x = -38
    for n in south:
        if n not in lib:
            continue
        w = widths[n]
        x += w / 2
        inst(lib, n, (x, -7.5, 0), rz=math.pi)
        x += w / 2 + 3
    rnd = random.Random(3)
    for i in range(8):
        inst(plib, rnd.choice(['Barrel', 'Crate', 'Barrel']), (rnd.uniform(-38, 30), rnd.choice([5.2, -5.2]), 0), rz=rnd.uniform(0, 6))
    for i in range(6):
        inst(plib, 'Tumbleweed', (rnd.uniform(-30, 30), rnd.uniform(-4, 4), 0), rz=rnd.uniform(0, 6))
    inst(plib, 'WaterTrough', (-12, 5.0, 0))
    inst(plib, 'Wagon_Wreck', (22, -3.5, 0), rz=0.5)
    for i in range(10):
        inst(plib, 'Sagebrush', (rnd.uniform(-60, 60), rnd.choice([-14, 16]) + rnd.uniform(-3, 3), 0), rz=rnd.uniform(0, 6))
    camera(cam, target, lens)
    render(name)


def town():
    town_scene('town', (-50, -2, 3.2), (0, 1.0, 4.0), lens=26)


def town_street():
    town_scene('town_front', (-24, -5.5, 2.0), (-24, 8, 5.0), lens=20, sunp=(22, -150))


def closeup():
    reset()
    lib = import_lib(PROPS)
    setup_render()
    world(haze=0.0003)
    sun(30, -40, energy=4.5)
    ground(colors=((0.36, 0.30, 0.18), (0.44, 0.35, 0.24)))
    items = [('Sagebrush', 0, 0), ('Tumbleweed', 1.6, 0.2), ('CowSkull', 2.8, -0.3), ('GraveCross', 4.6, 0.3), ('Rock_A', -1.6, 0.4), ('Rock_C', -3.2, 0.8)]
    for n, x, y in items:
        inst(lib, n, (x, y, 0), rz=0.0)
    camera((0.8, -5.2, 1.9), (0.8, 0.3, 0.35), lens=35)
    render('closeup')


ALL = {'closeup': closeup, 'lineup_big': lineup_big, 'lineup_small': lineup_small, 'forest': forest, 'snow': snow,
       'desert': desert, 'town': town, 'town_street': town_street}
todo = argv or [k for k in ALL if not k.startswith('town') or os.path.exists(TOWN)]
for k in todo:
    if hasattr(height_at, 'bvh'):
        del height_at.bvh
    ALL[k]()
