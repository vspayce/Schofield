"""Previews of the coach driver (and the player / a bandit, to show they're unchanged).

  Blender --background --factory-startup --python tools/blender/preview_driver.py -- [outdir]

Writes driver_front.png, driver_34.png, driver_head.png, driver_seated.png,
driver_seated_close.png, driver_check_player.png, driver_check_bandit.png into
tools/blender/previews (and outdir, if given).
"""
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import common as C  # noqa: E402
from preview import at, load  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
EXTRA = argv[0] if argv else None

SHOW = {
    "driver": ["Body_Driver", "Coat_Driver", "Hat_Driver", "Moustache_Walrus", "Neckerchief_Driver", "Watch_Driver"],
    "player": ["Body", "Hat_Wide", "Duster"],
    "bandit": ["Body", "Hat_Wide", "Bandana", "Duster"],
}


def show(objs, variant):
    for o in objs:
        if o.type == "MESH":
            o.hide_render = o.name.split(".")[0] not in SHOW[variant]


def out(name):
    p = os.path.join(C.PREVIEWS, name)
    C.render_to(p)
    if EXTRA:
        shutil.copy(p, os.path.join(EXTRA, name))
    return p


def res(w, h):
    bpy.context.scene.render.resolution_x = w
    bpy.context.scene.render.resolution_y = h


def main():
    C.reset_scene()
    C.setup_preview_scene((640, 900))
    arm, objs = load(os.path.join(C.MODELS, "rider.glb"))
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 64

    # standing, framed like the photograph (full length, slight 3/4 from his right)
    show(objs, "driver")
    at(arm, "StandIdle", 0.3)
    arm.animation_data.action = None
    bpy.context.view_layer.update()
    at(arm, "StandIdle", 0.3)
    C.camera("front", (0.0, -5.2, 1.0), (0, 0, 0.93), lens=85)
    out("driver_front.png")
    C.camera("c34", (-2.8, -4.4, 1.1), (0, 0, 0.93), lens=85)
    out("driver_34.png")
    # head close-up
    res(800, 800)
    head = arm.pose.bones["head"]
    hp = arm.matrix_world @ head.head
    C.camera("head", hp + Vector((-0.28, -0.62, 0.14)), hp + Vector((0, 0, 0.1)), lens=85)
    out("driver_head.png")
    C.camera("headf", hp + Vector((0.0, -0.68, 0.10)), hp + Vector((0, 0, 0.1)), lens=85)
    out("driver_head_front.png")

    # player and bandit, same framing as the driver 3/4 (unchanged meshes)
    res(640, 900)
    for v in ("player", "bandit"):
        show(objs, v)
        C.camera("cv", (-2.8, -4.4, 1.1), (0, 0, 0.93), lens=85)
        out(f"driver_check_{v}.png")

    # seated on the coach box with the Drive clip
    show(objs, "driver")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(C.MODELS, "stagecoach.glb"))
    coach = [o for o in bpy.data.objects if o not in before]
    seat = next(o for o in coach if o.name.startswith("Seat_Driver"))
    bpy.context.view_layer.update()
    arm.parent = None
    arm.matrix_world = seat.matrix_world.copy()
    at(arm, "Drive", 0.4)
    res(1100, 800)
    sp = seat.matrix_world.translation
    C.camera("seat34", sp + Vector((2.2, -3.0, 0.4)), sp + Vector((0, -0.1, -0.05)), lens=50)
    out("driver_seated.png")
    C.camera("seatside", sp + Vector((2.6, -0.3, 0.05)), sp + Vector((0, -0.2, -0.1)), lens=50)
    out("driver_seated_side.png")
    C.camera("seatrear", sp + Vector((-1.2, 3.2, 1.1)), sp + Vector((0, -0.4, 0.2)), lens=40)
    out("driver_seated_game.png")


main()
