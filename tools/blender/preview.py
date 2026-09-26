"""Re-import the exported GLBs into a fresh scene, verify contracts, render previews.

  Blender --background --factory-startup --python tools/blender/preview.py -- [horse|rider|mounted|verify|all]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import common as C  # noqa: E402

OUTD = C.PREVIEWS


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in objs if o.type == "ARMATURE")
    return arm, objs


def clip(arm, name):
    for a in bpy.data.actions:
        if a.name == name or a.name.startswith(name + "_") or a.name.startswith(name + "."):
            if arm.animation_data is None:
                arm.animation_data_create()
            arm.animation_data.action = a
            if a.slots:
                arm.animation_data.action_slot = a.slots[0]
            return a
    raise KeyError(name)


def at(arm, name, t):
    a = clip(arm, name)
    f = t * C.FPS
    bpy.context.scene.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
    return a


def verify(path):
    C.reset_scene()
    arm, objs = load(path)
    print(f"\n==== {os.path.basename(path)}  ({os.path.getsize(path) / 1024:.0f} KB)")
    for o in objs:
        extra = ""
        if o.type == "MESH":
            ntri = sum(len(p.vertices) - 2 for p in o.data.polygons)
            maxinf = max((len([g for g in v.groups if g.weight > 0]) for v in o.data.vertices), default=0)
            bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
            extra = f"tris={ntri} maxInfluences={maxinf} bboxZ=({min(v.z for v in bb):.2f},{max(v.z for v in bb):.2f}) bboxY=({min(v.y for v in bb):.2f},{max(v.y for v in bb):.2f})"
        if o.type == "EMPTY":
            extra = f"world={tuple(round(v, 3) for v in o.matrix_world.translation)} parent={o.parent.name if o.parent else None} bone={o.parent_bone}"
        print(f"  node {o.name:<14} {o.type:<9} {extra}")
    print(f"  bones ({len(arm.data.bones)}): {', '.join(b.name for b in arm.data.bones)}")
    for a in bpy.data.actions:
        fr = a.frame_range
        print(f"  clip {a.name:<16} {(fr[1] - fr[0]) / C.FPS:.3f}s  frames {fr[0]:.0f}-{fr[1]:.0f}")
    return arm, objs


def scene_for(res=(640, 420)):
    C.reset_scene()
    C.setup_preview_scene(res)


def horse_previews():
    path = os.path.join(C.MODELS, "horse.glb")
    scene_for((520, 400))
    arm, objs = load(path)
    # side view gallop contact sheet
    C.camera("cam", (6.0, -0.2, 1.1), (0, -0.2, 1.0), ortho=3.4)
    for clipname, n, cols in (("Gallop", 8, 4), ("Canter", 8, 4)):
        a = clip(arm, clipname)
        dur = (a.frame_range[1] - a.frame_range[0]) / C.FPS
        paths = []
        for i in range(n):
            at(arm, clipname, dur * i / n)
            paths.append(C.render_to(os.path.join(OUTD, f"_tmp_{i}.png")))
        C.contact_sheet(paths, os.path.join(OUTD, f"horse_{clipname.lower()}_side.png"), cols)
    # 3/4 hero views
    bpy.context.scene.render.resolution_x = 900
    bpy.context.scene.render.resolution_y = 600
    C.camera("cam2", (4.2, -4.6, 1.9), (0, -0.2, 0.95), lens=45)
    at(arm, "Gallop", 0.18)
    C.render_to(os.path.join(OUTD, "horse_gallop_34.png"))
    at(arm, "Idle", 0.0)
    C.render_to(os.path.join(OUTD, "horse_idle_34.png"))
    C.camera("cam3", (-3.0, -5.0, 1.4), (0, 0.0, 0.8), lens=40)
    paths = []
    for t in (0.0, 0.35, 0.72, 1.1, 1.5):
        at(arm, "Fall", t)
        paths.append(C.render_to(os.path.join(OUTD, f"_tmp_f{t}.png")))
    for t in (0.5, 1.0, 1.3):
        at(arm, "Rear", t)
        paths.append(C.render_to(os.path.join(OUTD, f"_tmp_r{t}.png")))
    bpy.context.scene.render.resolution_x = 520
    C.contact_sheet(paths, os.path.join(OUTD, "horse_fall_rear.png"), 4)


def mounted_previews():
    scene_for((900, 620))
    harm, hobjs = load(os.path.join(C.MODELS, "horse.glb"))
    rarm, robjs = load(os.path.join(C.MODELS, "rider.glb"))
    mount = next(o for o in hobjs if o.name.startswith("Mount"))
    rarm.parent = mount
    rarm.matrix_parent_inverse = Matrix.Identity(4)
    rarm.location = (0, 0, 0)
    rarm.rotation_euler = (0, 0, 0)
    rarm.rotation_mode = "QUATERNION"
    rarm.rotation_quaternion = (1, 0, 0, 0)
    for o in robjs:
        if o.name.startswith("Poncho") or o.name.startswith("Hat_Bowler"):
            o.hide_render = True
    C.camera("cam", (4.6, -4.2, 2.3), (0, -0.2, 1.4), lens=45)
    for rc, t in (("Ride", 0.1), ("RideAim", 0.1)):
        at(harm, "Gallop", t)
        at(rarm, rc, t)
        C.render_to(os.path.join(OUTD, f"mounted_{rc.lower()}_34.png"))
    # side sheet of riding through the gallop
    bpy.context.scene.render.resolution_x = 520
    bpy.context.scene.render.resolution_y = 440
    C.camera("cams", (6.0, -0.2, 1.4), (0, -0.2, 1.3), ortho=3.6)
    paths = []
    a = clip(harm, "Gallop")
    dur = (a.frame_range[1] - a.frame_range[0]) / C.FPS
    for i in range(4):
        at(harm, "Gallop", dur * i / 4)
        at(rarm, "Ride", dur * i / 4)
        paths.append(C.render_to(os.path.join(OUTD, f"_tmp_m{i}.png")))
    C.contact_sheet(paths, os.path.join(OUTD, "mounted_ride_side.png"), 4)
    # right-side view aiming (rider aims forward-right = -X side)
    C.camera("camr", (-4.2, -3.6, 2.0), (0, -0.3, 1.6), lens=45)
    bpy.context.scene.render.resolution_x = 900
    bpy.context.scene.render.resolution_y = 620
    at(harm, "Gallop", 0.2)
    at(rarm, "RideAim", 0.2)
    C.render_to(os.path.join(OUTD, "mounted_rideaim_right.png"))
    # FallOff mid frames (detach from horse, ride idle)
    rarm.parent = None
    rarm.matrix_world = Matrix.Translation(mount.matrix_world.translation)
    at(harm, "Idle", 0.0)
    C.camera("camf", (5.5, -1.0, 1.6), (0, 0.6, 1.0), lens=35)
    bpy.context.scene.render.resolution_x = 520
    bpy.context.scene.render.resolution_y = 420
    paths = []
    for t in (0.15, 0.35, 0.55, 0.8):
        at(rarm, "FallOff", t)
        paths.append(C.render_to(os.path.join(OUTD, f"_tmp_fo{t}.png")))
    C.contact_sheet(paths, os.path.join(OUTD, "rider_falloff.png"), 4)


def rider_previews():
    scene_for((520, 520))
    arm, objs = load(os.path.join(C.MODELS, "rider.glb"))
    for o in objs:
        if o.name.startswith("Poncho") or o.name.startswith("Hat_Bowler"):
            o.hide_render = True
    C.camera("cam", (3.2, -3.4, 1.5), (0, 0, 0.9), lens=45)
    paths = []
    for clipname, t in (("StandIdle", 0.3), ("StandShoot", 0.05), ("DieStanding", 0.5), ("DieStanding", 1.6)):
        at(arm, clipname, t)
        paths.append(C.render_to(os.path.join(OUTD, f"_tmp_s{clipname}{t}.png")))
    C.contact_sheet(paths, os.path.join(OUTD, "rider_standing.png"), 4)
    # variants: poncho + bowler, no hat
    for o in objs:
        if o.name.startswith("Poncho") or o.name.startswith("Hat_Bowler"):
            o.hide_render = False
        if o.name.startswith("Duster") or o.name.startswith("Hat_Wide"):
            o.hide_render = True
    at(arm, "StandIdle", 0.3)
    C.render_to(os.path.join(OUTD, "rider_variant_poncho.png"))
    # rest (bind) pose close-up
    for o in objs:
        o.hide_render = o.name.startswith("Poncho") or o.name.startswith("Hat_Bowler")
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    C.camera("camc", (1.6, -2.2, 1.9), (0, 0, 0.35), lens=50)
    C.render_to(os.path.join(OUTD, "rider_bindpose.png"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["all"]
    mode = argv[0]
    if mode in ("verify", "all"):
        for f in ("horse.glb", "rider.glb"):
            p = os.path.join(C.MODELS, f)
            if os.path.exists(p):
                verify(p)
    if mode in ("horse", "all"):
        horse_previews()
    if mode in ("rider", "all"):
        rider_previews()
    if mode in ("mounted", "all"):
        mounted_previews()
