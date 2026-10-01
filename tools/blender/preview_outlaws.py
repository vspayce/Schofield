"""Previews of the rider.glb looks: the gang, the guard, and the unchanged ones.

  Blender --background --factory-startup --python tools/blender/preview_outlaws.py -- [outdir] [what ...]

what: lineup clips mounted guard unchanged town hickok (default: all).  Uses the
UNPACKED rider.glb straight out of build_rider.py (meshopt-packed GLBs import
without node names), or RIDER_GLB=<unpacked copy>.  LOOKS mirrors createRider's table in src/game/characters.js.
Writes tools/blender/previews/outlaw_*.png (and copies to outdir).
"""
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common as C  # noqa: E402
from preview import at, load  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
EXTRA = argv[0] if argv and os.path.isdir(argv[0]) else None
WHAT = set(argv[1:] if EXTRA else argv) or {"lineup", "clips", "mounted", "guard", "unchanged", "town", "hickok"}

LOOKS = {
    "outlaw": (["Body_Man", "Hat_Wide", "Bandana_Man", "Coat_Guard"], {"Coat_Guard": (0.36, 0.31, 0.27), "Hat_Wide": (0.7, 0.66, 0.62)}),
    "sugarloaf": (["Body_Man", "Hat_Sugarloaf", "Bandana_Man", "Jacket"], {"Bandana_Man": (0.45, 1.6, 3.4), "Jacket": (0.92, 0.76, 0.55)}),
    "vaquero": (["Body_Man", "Hat_Sombrero", "Serape", "Moustache_Vaquero"], {"Body_Man": (0.92, 0.86, 0.8)}),
    "reb": (["Body_Man", "Hat_Slouch", "Jacket", "Gauntlets"], {"Hat_Slouch": (1.0, 0.85, 0.62), "Jacket": (0.8, 0.82, 0.88)}),
    "mountain": (["Body_Man", "Coat_Buffalo", "Beard_Long", "Hat_Wide"], {"Hat_Wide": (0.55, 0.5, 0.46)}),
    "pearl": (["Body_Female", "Hat_Slouch"], {"Hat_Slouch": (1.1, 0.96, 0.8)}),
    "bart": (["Body_Man", "Coat_Guard", "Hat_Bowler", "Mask_Sack"], {"Body_Man": (0.5, 0.5, 0.55), "Coat_Guard": (1.04, 1.04, 1.02)}),
    "player": (["Body_Man", "Coat_Guard", "Hat_Guard", "Moustache_Guard"], {}),
    "woman_slate": (["Body_Woman", "Dress", "Bonnet"], {"Dress": (0.55, 0.6, 0.72), "Bonnet": (0.9, 0.9, 0.95)}),
    "woman_plum": (["Body_Woman", "Dress", "Hat_Lady"], {"Dress": (0.72, 0.4, 0.45), "Hat_Lady": (0.55, 0.35, 0.4)}),
    "woman_calico": (["Body_Woman", "Dress", "Bonnet"], {"Dress": (0.95, 0.82, 0.62), "Bonnet": (1.0, 0.95, 0.85)}),
    "lawman": (["Body_Man", "Coat_Guard", "Hat_Lawman"], {"Coat_Guard": (0.22, 0.21, 0.21)}),
    "hickok": (["Body_Hickok", "Coat_Guard", "Hat_Hickok", "Colts_Hickok"], {"Coat_Guard": (0.09, 0.087, 0.087)}),
    "driver": (["Body_Driver", "Coat_Driver", "Hat_Driver", "Moustache_Walrus", "Neckerchief_Driver", "Watch_Driver"], {}),
    "townsman": (["Body", "Hat_Bowler", "Duster"], {}),
    "drifter": (["Body", "Hat_Wide", "Duster"], {}),
}
GANG = ["outlaw", "sugarloaf", "vaquero", "reb", "mountain", "pearl", "bart"]
RIDERS = ["outlaw", "sugarloaf", "vaquero", "reb", "mountain", "pearl"]


def out(name):
    p = os.path.join(C.PREVIEWS, name)
    C.render_to(p)
    if EXTRA:
        shutil.copy(p, os.path.join(EXTRA, name))
    return p


def res(w, h):
    bpy.context.scene.render.resolution_x = w
    bpy.context.scene.render.resolution_y = h


_base = {}


def show(objs, variant):
    meshes, cols = LOOKS[variant]
    for o in objs:
        if o.type != "MESH":
            continue
        n = o.name.split(".")[0]
        o.hide_render = n not in meshes
        mat = o.active_material
        if mat is None:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        tex = next((nd for nd in mat.node_tree.nodes if nd.type == "TEX_IMAGE"), None)
        if tex is None or bsdf is None:
            continue
        mix = mat.node_tree.nodes.get("tintmul")
        if mix is None:
            mix = mat.node_tree.nodes.new("ShaderNodeMix")
            mix.name = "tintmul"
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mat.node_tree.links.new(tex.outputs["Color"], mix.inputs["A"])
            mat.node_tree.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        c = cols.get(n, (1, 1, 1))
        mix.inputs["B"].default_value = (c[0], c[1], c[2], 1)


def sheet(paths, name, cols):
    p = os.path.join(C.PREVIEWS, name)
    C.contact_sheet(paths, p, cols)
    if EXTRA:
        shutil.copy(p, os.path.join(EXTRA, name))


def standing(arm, t=0.3):
    at(arm, "StandIdle", t)


def main():
    C.reset_scene()
    C.setup_preview_scene((420, 640))
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 48
    # RIDER_GLB: an unpacked copy, if rider.glb has already been packed
    arm, objs = load(os.environ.get("RIDER_GLB") or os.path.join(C.MODELS, "rider.glb"))

    if "lineup" in WHAT:
        for view, loc in (("front", (0.0, -5.6, 1.0)), ("34", (-3.0, -4.8, 1.1))):
            paths = []
            for v in GANG:
                show(objs, v)
                standing(arm)
                C.camera("c", loc, (0, 0, 0.93), lens=85)
                paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_{v}_{view}.png")))
            sheet(paths, f"outlaw_lineup_{view}.png", len(paths))
        # Bart and Pearl, framed for the reference images
        res(640, 900)
        for v, loc in (("bart", (-1.2, -5.0, 1.15)), ("pearl", (-1.4, -5.0, 1.1))):
            show(objs, v)
            standing(arm)
            C.camera("c", loc, (0, 0, 0.98), lens=85)
            out(f"outlaw_{v}.png")
            hp = arm.matrix_world @ arm.pose.bones["head"].head
            res(700, 700)
            C.camera("h", hp + Vector((-0.25, -0.75, 0.08)), hp + Vector((0, 0, 0.08)), lens=85)
            out(f"outlaw_{v}_head.png")
            res(640, 900)

    if "clips" in WHAT:
        res(300, 360)
        clips = [("Ride", 0.1, "seat"), ("RideAim", 0.1, "seat"), ("FallOff", 0.5, "fall"), ("StandIdle", 0.3, "stand"),
                 ("StandShoot", 0.05, "stand"), ("DieStanding", 1.0, "stand")]
        for v in GANG + ["player"]:
            show(objs, v)
            paths = []
            for clip, t, kind in clips:
                at(arm, clip, t)
                if kind == "seat":
                    C.camera("c", (-1.9, -2.4, 0.9), (0, 0, 0.25), lens=50)
                elif kind == "fall":
                    C.camera("c", (-2.6, -0.4, 0.2), (0, 0.9, -0.9), lens=35)
                else:
                    C.camera("c", (-2.2, -3.0, 1.1), (0, 0.2, 0.8), lens=45)
                paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_{v}_{clip}.png")))
            sheet(paths, f"outlaw_clips_{v}.png", len(paths))

    if "mounted" in WHAT:
        before = set(bpy.data.objects)
        harm, hobjs = load(os.path.join(C.MODELS, "horse.glb"))
        for o in hobjs:
            if o.name.startswith("Harness"):
                o.hide_render = True
        mount = next(o for o in hobjs if o.name.startswith("Mount"))
        res(560, 460)
        paths = []
        for i, v in enumerate(RIDERS):
            show(objs, v)
            at(harm, "Gallop", 0.1 + 0.07 * i)
            bpy.context.view_layer.update()
            arm.matrix_world = mount.matrix_world.copy()
            at(arm, "RideAim" if i % 2 else "Ride", 0.1 + 0.07 * i)
            C.camera("m", (3.4, -3.6, 2.0), (0, -0.2, 1.35), lens=45)
            paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_m_{v}.png")))
        sheet(paths, "outlaw_mounted.png", 3)
        for o in set(bpy.data.objects) - before:
            o.hide_render = True
        arm.matrix_world = __import__("mathutils").Matrix.Identity(4)

    if "unchanged" in WHAT:
        res(420, 640)
        paths = []
        for v in ("driver", "townsman", "drifter"):
            show(objs, v)
            standing(arm)
            C.camera("c", (-3.0, -4.8, 1.1), (0, 0, 0.93), lens=85)
            paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_u_{v}.png")))
        sheet(paths, "outlaw_unchanged.png", len(paths))

    if "town" in WHAT:
        TOWN = ["woman_slate", "woman_plum", "woman_calico", "lawman", "townsman"]
        res(420, 640)
        for view, loc in (("front", (0.0, -5.6, 1.0)), ("34", (-3.0, -4.8, 1.1))):
            paths = []
            for v in TOWN:
                show(objs, v)
                standing(arm)
                C.camera("c", loc, (0, 0, 0.93), lens=85)
                paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_t_{v}_{view}.png")))
            sheet(paths, f"town_lineup_{view}.png", len(paths))
        res(700, 700)
        show(objs, "woman_slate")
        standing(arm)
        hp = arm.matrix_world @ arm.pose.bones["head"].head
        C.camera("h", hp + Vector((-0.25, -0.75, 0.08)), hp + Vector((0, 0, 0.08)), lens=85)
        out("town_woman_head.png")
        # Walk / Run across the cycle, side on (in place)
        res(300, 420)
        for v, clip, frames in (("woman_plum", "Walk", 64), ("lawman", "Walk", 64), ("townsman", "Run", 42)):
            show(objs, v)
            paths = []
            for i in range(8):
                at(arm, clip, frames / C.FPS * i / 8)
                C.camera("w", (-4.2, 0.0, 1.0), (0, 0, 0.9), ortho=2.3)
                paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_w{i}.png")))
            sheet(paths, f"town_{clip.lower()}_{v}.png", 8)
        # Talk, Sit, LeanRail
        res(360, 460)
        paths = []
        for v, clip, t, cam, tgt in (("woman_calico", "Talk", 0.6, (-2.0, -3.4, 1.2), (0, 0, 0.95)),
                                     ("lawman", "Talk", 1.4, (-2.0, -3.4, 1.2), (0, 0, 0.95)),
                                     ("woman_slate", "Sit", 0.5, (-2.2, -2.6, 0.5), (0, -0.15, 0.1)),
                                     ("townsman", "Sit", 1.5, (-2.2, -2.6, 0.5), (0, -0.15, 0.1)),
                                     ("lawman", "LeanRail", 1.0, (-2.8, -1.4, 1.2), (0, -0.2, 0.95)),
                                     ("woman_plum", "LeanRail", 2.0, (-2.8, -1.4, 1.2), (0, -0.2, 0.95))):
            show(objs, v)
            at(arm, clip, t)
            C.camera("p", cam, tgt, lens=40)
            paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_p_{v}_{clip}.png")))
        sheet(paths, "town_poses.png", 6)

    if "hickok" in WHAT:
        show(objs, "hickok")
        res(560, 820)
        standing(arm)
        C.camera("c", (0.0, -5.6, 1.0), (0, 0, 0.93), lens=85)
        out("hickok_front.png")
        C.camera("c", (-3.0, -4.8, 1.1), (0, 0, 0.93), lens=85)
        out("hickok_34.png")
        C.camera("c", (1.6, 4.9, 1.2), (0, 0, 0.98), lens=85)
        out("hickok_back.png")
        hp = arm.matrix_world @ arm.pose.bones["head"].head
        res(700, 700)
        C.camera("h", hp + Vector((-0.3, -0.72, 0.06)), hp + Vector((0, 0, 0.06)), lens=85)
        out("hickok_head.png")
        C.camera("h", hp + Vector((0.0, -0.75, 0.04)), hp + Vector((0, 0, 0.06)), lens=85)
        out("hickok_head_front.png")
        # mounted: holstered, both Navies out, left-hand aim (two guns on Grip_R / Grip_L)
        from mathutils import Matrix
        before = set(bpy.data.objects)
        harm, hobjs = load(os.path.join(C.MODELS, "horse.glb"))
        for o in hobjs:
            if o.name.startswith("Harness"):
                o.hide_render = True
        mount = next(o for o in hobjs if o.name.startswith("Mount"))
        bw = set(bpy.data.objects)
        guns = []
        for gname in ("Grip_R", "Grip_L"):
            bpy.ops.import_scene.gltf(filepath=os.path.join(C.MODELS, "weapons.glb"))
            new = [o for o in bpy.data.objects if o not in bw]
            bw = set(bpy.data.objects)
            grip = next(o for o in objs if o.name.startswith(gname))
            for o in new:
                if o.parent is None and o.name.startswith("Schofield"):
                    o.parent = grip
                    o.matrix_parent_inverse = Matrix.Identity(4)
                    o.location = (0, 0, 0)
                    o.rotation_mode = "QUATERNION"
                    o.rotation_quaternion = (1, 0, 0, 0)
                    guns.append(o)
                elif o.parent is None:
                    o.hide_render = True
                    for ch in o.children_recursive:
                        ch.hide_render = True
        res(620, 520)
        paths = []
        for clip, t, gv in (("RideHolstered", 0.1, False), ("RideAimDual", 0.1, True), ("RideAimL", 0.1, True)):
            for gobj in guns:
                for o in [gobj] + list(gobj.children_recursive):
                    o.hide_render = not gv
            for o in objs:
                if o.name.startswith("Colts_Hickok"):
                    o.hide_render = gv
            at(harm, "Gallop", t)
            bpy.context.view_layer.update()
            arm.matrix_world = mount.matrix_world.copy()
            at(arm, clip, t)
            C.camera("m", (2.2, -4.4, 2.0), (0, -0.3, 1.45), lens=45)
            paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_hk_{clip}.png")))
        sheet(paths, "hickok_mounted.png", 3)
        for o in set(bpy.data.objects) - before:
            o.hide_render = True
        arm.matrix_world = Matrix.Identity(4)

    if "guard" in WHAT:
        show(objs, "player")
        res(560, 820)
        standing(arm)
        C.camera("c", (0.0, -5.6, 1.0), (0, 0, 0.93), lens=85)
        out("outlaw_guard_front.png")
        C.camera("c", (-3.0, -4.8, 1.1), (0, 0, 0.93), lens=85)
        out("outlaw_guard_34.png")
        C.camera("c", (1.6, 4.9, 1.2), (0, 0, 0.98), lens=85)
        out("outlaw_guard_back.png")
        hp = arm.matrix_world @ arm.pose.bones["head"].head
        res(700, 700)
        C.camera("h", hp + Vector((-0.25, -0.75, 0.08)), hp + Vector((0, 0, 0.08)), lens=85)
        out("outlaw_guard_head.png")
        # on the roof of the Abbott-Downing, SeatAim, from the game's chase camera
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(C.MODELS, "stagecoach_treasure.glb"))
        seat = next(o for o in bpy.data.objects if o not in before and o.name.startswith("Seat_Guard"))
        bpy.context.view_layer.update()
        from mathutils import Matrix
        arm.matrix_world = seat.matrix_world @ Matrix.Rotation(0.67, 4, "Z")
        at(arm, "SeatAim", 0.0)
        bpy.context.view_layer.update()
        # the coach gun in his hands, on Grip_R as createWeapon/hand.R would carry it
        before_w = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(C.MODELS, "weapons.glb"))
        wobjs = [o for o in bpy.data.objects if o not in before_w]
        grip = next(o for o in objs if o.name.startswith("Grip_R"))
        for o in wobjs:
            if o.parent is None:
                if o.name.startswith("CoachGun"):
                    o.parent = grip
                    o.matrix_parent_inverse = Matrix.Identity(4)
                    o.location = (0, 0, 0)
                    o.rotation_mode = "QUATERNION"
                    o.rotation_quaternion = (1, 0, 0, 0)
                else:
                    o.hide_render = True
                    for ch in o.children_recursive:
                        ch.hide_render = True
        head = arm.matrix_world @ arm.pose.bones["head"].head
        # player.js: pivot = head on the coach centreline, camera 9 m back along the aim, 1 m up
        pivot = Vector((0.0, head.y, head.z))
        res(1280, 720)
        sc.camera = None
        for name, yaw in (("chase", 0.0), ("chase_right", -0.6), ("chase_left", 0.7)):
            aim = Vector((-math.sin(yaw), -math.cos(yaw), 0.0))
            arm.matrix_world = seat.matrix_world @ Matrix.Rotation(0.67 + yaw, 4, "Z")
            at(arm, "SeatAim", 0.0)
            cam = C.camera("ch", pivot - aim * 9 + Vector((0, 0, 1.0)), pivot - aim * 9 + Vector((0, 0, 1.0)) + aim, lens=31.2)
            cam.data.sensor_fit = "VERTICAL"
            cam.data.sensor_height = 24
            cam.data.lens = 24 / (2 * math.tan(math.radians(30)))  # 60 deg vertical fov like the game
            out(f"outlaw_guard_{name}.png")
        arm.matrix_world = seat.matrix_world @ Matrix.Rotation(0.67, 4, "Z")
        res(900, 640)
        sp = seat.matrix_world.translation
        C.camera("s", sp + Vector((-2.4, -2.6, 0.8)), sp + Vector((0, 0, 0.4)), lens=45)
        at(arm, "SeatAim", 0.0)
        out("outlaw_guard_seated_34.png")
        C.camera("s", sp + Vector((0.4, -3.6, 0.6)), sp + Vector((0, 0, 0.4)), lens=45)
        out("outlaw_guard_seated_front.png")
        # no bob: six frames across the 3 s loop, same camera (side on)
        res(360, 360)
        C.camera("b", sp + Vector((-2.6, 0.4, 0.5)), sp + Vector((0, -0.1, 0.45)), lens=50)
        paths = []
        for i in range(6):
            at(arm, "SeatAim", 3.0 * i / 6)
            paths.append(C.render_to(os.path.join(C.PREVIEWS, f"_tmp_b{i}.png")))
        sheet(paths, "outlaw_guard_nobob.png", 6)


main()
