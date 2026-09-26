"""Build public/assets/models/rider.glb  (SCHOFIELD)

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_rider.py

Seated riding pose is the bind pose.  Origin = the saddle seat contact point:
parent the rider to the horse's `Mount` empty with an identity transform and
the hips sit in the saddle.  The standing clips (StandIdle, StandShoot,
DieStanding) lift the root so the FEET are at the origin -> place the rider at
ground level for those.

Meshes (toggle in code): Body, Duster, Poncho, Hat_Wide, Hat_Bowler, Bandana
Empty:  Grip_R (child of bone hand.R) - weapon grip; -Y = barrel, +Z = up
Clips:  Ride, RideAim, Shoot, FallOff, StandIdle, StandShoot, DieStanding
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import common as C  # noqa: E402

OUT = os.path.join(C.MODELS, "rider.glb")


# ----------------------------------------------------------------------------
# skeleton (seated).  +x = rider's left.  z=0 is the seat contact.
# ----------------------------------------------------------------------------
def J(s):
    return {
        "sho": (0.035 * s, 0.03, 0.57),
        "arm": (0.185 * s, 0.035, 0.575),
        "elb": (0.215 * s, 0.03, 0.31),
        "wri": (0.085 * s, -0.24, 0.285),
        "hnd": (0.06 * s, -0.33, 0.28),
        "hip": (0.095 * s, 0.0, 0.10),
        "kne": (0.31 * s, -0.33, -0.18),
        "ank": (0.35 * s, -0.12, -0.585),
        "toe": (0.36 * s, -0.30, -0.655),
    }


def bone_list():
    B = [
        ("root", (0, 0, 0), (0, 0, 0.10), None, False),
        ("hips", (0, 0.02, 0.10), (0, 0.02, 0.21), "root", False),
        ("spine", (0, 0.02, 0.21), (0, 0.035, 0.38), "hips", True),
        ("chest", (0, 0.035, 0.38), (0, 0.03, 0.60), "spine", True),
        ("neck", (0, 0.03, 0.60), (0, 0.01, 0.72), "chest", True),
        ("head", (0, 0.01, 0.72), (0, 0.0, 0.93), "neck", True),
        ("coat.B", (0, 0.13, 0.13), (0, 0.27, -0.10), "hips", False),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = J(s)
        B += [
            ("shoulder" + sfx, j["sho"], j["arm"], "chest", False),
            ("upperarm" + sfx, j["arm"], j["elb"], "shoulder" + sfx, True),
            ("forearm" + sfx, j["elb"], j["wri"], "upperarm" + sfx, True),
            ("hand" + sfx, j["wri"], j["hnd"], "forearm" + sfx, True),
            ("thigh" + sfx, j["hip"], j["kne"], "hips", False),
            ("shin" + sfx, j["kne"], j["ank"], "thigh" + sfx, True),
            ("foot" + sfx, j["ank"], j["toe"], "shin" + sfx, True),
        ]
    return B


# ----------------------------------------------------------------------------
# body SDF
# ----------------------------------------------------------------------------
def body_prims():
    E, K = C.ell, C.cone
    P = [
        # head
        E((0, 0.0, 0.835), (0.078, 0.095, 0.105), "skin", ["head"], k=0.02),
        E((0, -0.03, 0.765), (0.062, 0.07, 0.055), "skin", ["head"], k=0.04),  # jaw
        K((0, -0.09, 0.83), (0, -0.105, 0.795), 0.014, 0.018, "skin", ["head"], k=0.02),  # nose
        E((0, 0.012, 0.865), (0.083, 0.095, 0.085), "hair", ["head"], k=0.015),  # hair cap
        K((0, 0.02, 0.60), (0, 0.0, 0.77), 0.056, 0.05, "skin", ["neck", "head"], k=0.03),  # neck
        # torso
        E((0, 0.035, 0.49), (0.165, 0.115, 0.14), "shirt", ["chest"], k=0.06),
        E((0, 0.03, 0.315), (0.145, 0.105, 0.12), "shirt", ["spine", "chest"], k=0.07),
        E((0, 0.035, 0.14), (0.165, 0.12, 0.10), "pants", ["hips"], k=0.06),
        E((0, 0.08, 0.06), (0.14, 0.09, 0.07), "pants", ["hips"], k=0.05),  # seat
        # gunbelt (flattened torus)
        C.fnprim(lambda p: _torus(p, (0, 0.035, 0.165), 0.172, 0.125, 0.018, 0.028), (-0.2, -0.12, 0.12), (0.2, 0.19, 0.21),
                 "belt", ["hips"], k=0.01),
        K((-0.19, 0.0, 0.16), (-0.24, -0.07, 0.02), 0.03, 0.026, "holster", ["hips", "thigh.R"], k=0.01),
        E((-0.19, 0.03, 0.19), (0.018, 0.035, 0.03), "gun", ["hips"], k=0.005),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P += [
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), j["elb"], 0.058, 0.045, "shirt", ["upperarm" + sfx, "shoulder" + sfx], k=0.03),
            K((0.07 * s, 0.035, 0.56), j["arm"], 0.07, 0.06, "shirt", ["shoulder" + sfx, "chest"], k=0.05),
            K(j["elb"], j["wri"], 0.045, 0.036, "shirt", ["forearm" + sfx], k=0.02),
            E(j["wri"] + (j["hnd"] - j["wri"]) * 0.45, (0.035, 0.05, 0.042), "glove", ["hand" + sfx], k=0.015),
            K(j["hip"] + np.array([0.0, 0.0, -0.01]), j["kne"], 0.088, 0.058, "pants", ["thigh" + sfx, "hips"], k=0.05),
            E(j["kne"], (0.058, 0.06, 0.06), "pants", ["thigh" + sfx, "shin" + sfx], k=0.02),
            K(j["kne"] + (j["ank"] - j["kne"]) * 0.12, j["ank"], 0.058, 0.047, "boot", ["shin" + sfx], k=0.02),
            K(j["ank"] + np.array([0, 0.025, -0.03]), j["toe"] + np.array([0, 0, 0.0]), 0.048, 0.036, "boot", ["foot" + sfx], k=0.02),
            E(j["ank"] + np.array([0, 0.03, -0.055]), (0.035, 0.035, 0.02), "heel", ["foot" + sfx], k=0.005),
            E((0.03 * s, -0.083, 0.845), (0.012, 0.008, 0.008), "eye", ["head"], k=0.004),
            E((0.082 * s, 0.005, 0.82), (0.014, 0.022, 0.03), "skin", ["head"], k=0.01),  # ear
        ]
    return P


def _torus(p, c, rx, ry, tube_r, tube_h):
    q = p - np.asarray(c)
    # ellipse radius approx
    ang = np.arctan2(q[:, 1] / ry, q[:, 0] / rx)
    ex = rx * np.cos(ang)
    ey = ry * np.sin(ang)
    dxy = np.sqrt((q[:, 0] - ex) ** 2 + (q[:, 1] - ey) ** 2)
    return np.sqrt((dxy / tube_r) ** 2 + (q[:, 2] / tube_h) ** 2) * min(tube_r, tube_h) - min(tube_r, tube_h)


def inflate(prims, off, keep_labels=None, label=None):
    out = []
    for p in prims:
        if p.sub or p.kind == "fn":
            continue
        if keep_labels and p.label not in keep_labels:
            continue
        lab = label or p.label
        if p.kind == "ell":
            out.append(C.ell(p.c, p.r + off, lab, p.bones, k=p.k + off * 0.5, scale=p.scale, rot=p.rot))
        elif p.kind == "cone":
            out.append(C.cone(p.a, p.b, p.ra + off, p.rb + off, lab, p.bones, k=p.k + off * 0.5, scale=p.scale))
    return out


def duster_prims(bp):
    torso = inflate(bp, 0.028, ["shirt"], "coat")
    E, K = C.ell, C.cone
    P = torso + [
        E((0, 0.035, 0.15), (0.195, 0.15, 0.11), "coat", ["hips"], k=0.06),
        E((0, 0.03, 0.62), (0.085, 0.075, 0.04), "collar", ["chest", "neck"], k=0.02),  # collar
        # back panel draping over the cantle / croup
        C.box((0, 0.20, -0.03), (0.19, 0.016, 0.17), 0.012, "coat", ["hips", "coat.B"], k=0.05,
              rot=_rotx(-38)),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P += [
            K(j["hip"] + np.array([0.02 * s, 0.02, 0.03]), j["kne"] + np.array([0.0, 0.08, 0.02]), 0.12, 0.085, "coat",
              ["thigh" + sfx, "hips"], k=0.05),
            # side skirt hanging down the horse's flank
            C.box((0.30 * s, -0.08, -0.22), (0.014, 0.16, 0.20), 0.01, "coat", ["thigh" + sfx], k=0.05, rot=_roty(-8 * s)),
        ]
    # no coat below the skirt hem, keep wrists/hands out of the sleeves
    P += [C.box((0, 0, -1.0), (1, 1, 0.58), 0.0, "cut", [], sub=True, k=0.02)]
    for s in (1, -1):
        j = J(s)
        P.append(C.ell(j["hnd"], (0.07, 0.10, 0.07), "cut", [], sub=True, k=0.01))
    return P


def _rotx(deg):
    a = math.radians(deg)
    return np.array([[1, 0, 0], [0, math.cos(a), math.sin(a)], [0, -math.sin(a), math.cos(a)]])


def _roty(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), 0, -math.sin(a)], [0, 1, 0], [math.sin(a), 0, math.cos(a)]])


def poncho_prims(bp):
    P = inflate(bp, 0.045, ["shirt"], "poncho")
    P = [p for p in P if p.kind == "ell" or "forearm" not in p.bones[0]]
    P += [C.ell((0, 0.03, 0.47), (0.30, 0.2, 0.16), "poncho", ["chest"], k=0.08, scale=(1, 1, 1))]
    P += [C.box((0, 0, -0.5), (1, 1, 0.78), 0.0, "cut", [], sub=True, k=0.03)]
    P += [C.ell((0, 0.01, 0.75), (0.06, 0.06, 0.12), "cut", [], sub=True, k=0.02)]  # neck hole
    return P


def bandana_prims(bp):
    head = [p for p in bp if p.label == "skin" and p.bones and p.bones[0] in ("head", "neck")]
    P = inflate(head, 0.012, None, "bandana")
    P += [C.cone((0, -0.06, 0.73), (0, -0.075, 0.64), 0.05, 0.012, "bandana", ["neck", "head"], k=0.03, scale=(1.3, 0.6, 1))]
    P += [
        C.box((0, 0, 1.3), (1, 1, 0.48), 0.0, "cut", [], sub=True, k=0.01),  # above the nose bridge
        C.box((0, 0, -0.3), (1, 1, 0.93), 0.0, "cut", [], sub=True, k=0.01),
    ]
    return P


# ----------------------------------------------------------------------------
# colours
# ----------------------------------------------------------------------------
def body_color(prims):
    labs = ["skin", "hair", "shirt", "pants", "belt", "holster", "gun", "glove", "boot", "heel", "eye"]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        n = C.fbm(P, 30.0, 3, seed=2)
        cols = {
            "skin": np.array([0.62, 0.43, 0.32]),
            "hair": np.array([0.16, 0.11, 0.08]),
            "shirt": np.array([0.62, 0.58, 0.50]),
            "pants": np.array([0.33, 0.29, 0.24]),
            "belt": np.array([0.26, 0.16, 0.09]),
            "holster": np.array([0.30, 0.18, 0.10]),
            "gun": np.array([0.35, 0.33, 0.30]),
            "glove": np.array([0.40, 0.28, 0.17]),
            "boot": np.array([0.17, 0.11, 0.07]),
            "heel": np.array([0.10, 0.07, 0.05]),
            "eye": np.array([0.05, 0.04, 0.04]),
        }
        c = sum(lw[k][:, None] * cols[k] for k in labs)
        # vest over the shirt torso (not the arms)
        torso = lw["shirt"] * (np.abs(P[:, 0]) < 0.16) * (P[:, 2] > 0.2) * (P[:, 2] < 0.57)
        opening = np.abs(P[:, 0]) < 0.018 + 0.05 * np.clip((P[:, 2] - 0.42) / 0.15, 0, 1)
        vest = torso * (~(opening & (P[:, 1] < 0))).astype(float)
        c = c * (1 - vest[:, None]) + np.array([0.20, 0.17, 0.14]) * vest[:, None]
        # buckle + cartridge loops
        buckle = lw["belt"] * (np.abs(P[:, 0]) < 0.03) * (P[:, 1] < -0.05)
        c = c * (1 - buckle[:, None]) + np.array([0.70, 0.56, 0.30]) * buckle[:, None]
        loops = lw["belt"] * (np.sin(np.arctan2(P[:, 1] - 0.035, P[:, 0]) * 60) > 0.2) * (P[:, 1] > -0.02)
        c = c * (1 - 0.6 * loops[:, None]) + np.array([0.72, 0.58, 0.33]) * 0.6 * loops[:, None]
        # face: brows, moustache/stubble
        face = lw["skin"] * (P[:, 1] < -0.04) * (P[:, 2] > 0.7)
        brow = face * (np.abs(P[:, 2] - 0.868) < 0.008) * (np.abs(np.abs(P[:, 0]) - 0.032) < 0.025)
        mous = face * (np.abs(P[:, 2] - 0.777) < 0.012) * (np.abs(P[:, 0]) < 0.04)
        stub = face * (P[:, 2] < 0.79)
        c = c * (1 - 0.35 * stub[:, None])
        hairc = cols["hair"]
        for m in (brow, mous):
            c = c * (1 - m[:, None]) + hairc * m[:, None]
        c *= (0.9 + 0.2 * n)[:, None]
        ao = C.sdf_ao([p for p in prims if not p.sub], P, N, steps=4, dist=0.02)
        c *= (0.45 + 0.55 * ao)[:, None]
        return c

    return fn


def cloth_color(prims, base, pattern=None, ao_dist=0.03):
    def fn(P, N, ex):
        n = C.fbm(P, 25.0, 3, seed=4)
        c = np.tile(np.array(base), (len(P), 1)) * (0.85 + 0.3 * n)[:, None]
        if pattern:
            c = pattern(P, N, c)
        ao = C.sdf_ao([p for p in prims if not p.sub], P, N, steps=4, dist=ao_dist)
        return c * (0.5 + 0.5 * ao)[:, None]

    return fn


def duster_pattern(P, N, c):
    # darker hem and weathered dust toward the bottom, front seam
    dust = np.clip((0.1 - P[:, 2]) / 0.6, 0, 1)
    c = c * (1 - 0.25 * dust[:, None]) + np.array([0.55, 0.47, 0.36]) * 0.25 * dust[:, None]
    seam = (np.abs(P[:, 0]) < 0.012) & (P[:, 1] < 0) & (P[:, 2] > 0.18)
    c[seam] *= 0.45
    return c


def poncho_pattern(P, N, c):
    band = np.sin(P[:, 2] * 70)
    red = (band > 0.6)[:, None]
    cream = (band < -0.75)[:, None]
    c = np.where(red, np.array([0.45, 0.14, 0.08]), c)
    c = np.where(cream, np.array([0.72, 0.64, 0.50]), c)
    return c


def hat_pattern(P, N, c):
    band = (P[:, 2] > 0.885) & (P[:, 2] < 0.905) & (np.hypot(P[:, 0], P[:, 1]) < 0.11)
    c[band] = np.array([0.12, 0.08, 0.06])
    return c


def bandana_pattern(P, N, c):
    dots = C.value_noise3(P, 180.0, 9) > 0.8
    c[dots] = np.array([0.75, 0.68, 0.58])
    return c


# ----------------------------------------------------------------------------
# hats (lathe)
# ----------------------------------------------------------------------------
HAT_C = Vector((0, 0.005, 0.878))


def make_hat_wide():
    prof = [(0.001, -0.004), (0.10, -0.004), (0.17, -0.002), (0.225, 0.004), (0.232, 0.012), (0.17, 0.010), (0.104, 0.014),
            (0.102, 0.06), (0.096, 0.11), (0.08, 0.135), (0.04, 0.14)]

    def sq(th, r, z):
        curl = 0.05 * (math.cos(th) ** 2) * max(0.0, (r - 0.11) / 0.12) ** 2
        # crease: pinch front and dent the crown top
        pinch = 0.0
        if z > 0.03 and r > 0.0:
            pinch = -0.012 * max(0.0, -math.sin(th)) ** 3 * (z / 0.14)
        dent = -0.03 * (1 - min(1.0, r / 0.07)) if z > 0.12 else 0.0
        sx = pinch * math.cos(th)
        sy = pinch * math.sin(th) * 0
        return sx, sy, curl + dent - 0.02 * max(0.0, -math.sin(th)) * max(0.0, (r - 0.11) / 0.12)

    ob = C.lathe("Hat_Wide", prof, segments=28, scale_xy=(0.95, 1.08), squash=sq)
    ob.location = HAT_C
    return ob


def make_hat_bowler():
    prof = [(0.001, -0.002), (0.10, -0.002), (0.13, 0.0), (0.137, 0.012), (0.10, 0.016), (0.102, 0.06), (0.097, 0.10),
            (0.08, 0.13), (0.045, 0.145)]

    def sq(th, r, z):
        return 0.0, 0.0, 0.03 * (math.cos(th) ** 2) * max(0.0, (r - 0.10) / 0.035) ** 1.5 if z < 0.02 else 0.0

    ob = C.lathe("Hat_Bowler", prof, segments=24, scale_xy=(0.92, 1.06), squash=sq)
    ob.location = HAT_C + Vector((0, 0, 0.002))
    return ob


def finish_lathe(ob):
    C.set_active(ob)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data)
    bm.free()
    C.shade_smooth(ob)


# ----------------------------------------------------------------------------
# animation
# ----------------------------------------------------------------------------
def frame_mat(d, s):
    d = Vector(d).normalized()
    s = (Vector(s) - d * Vector(s).dot(d)).normalized()
    u = d.cross(s)
    return Matrix((s, d, u)).transposed()  # columns: side, dir, up


def aim_q(rig, bone, direction, side=(1, 0, 0)):
    """World delta that points bone along `direction` keeping its side axis near `side`."""
    rd = rig.tail[bone] - rig.head[bone]
    Mr = frame_mat(rd, (1, 0, 0))
    Mt = frame_mat(direction, side)
    return (Mt @ Mr.transposed()).to_quaternion()


class RiderAnim:
    def __init__(self, rig):
        self.rig = rig
        L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731
        self.leg = L("thigh.L") + L("shin.L")
        self.stand_root_z = self.leg + 0.078 - 0.10

    def frames(self, n, pose_fn, bones=None):
        out = []
        for fi in range(n + 1):
            t = fi / C.FPS
            loc, world, rt = pose_fn(t, fi / n)
            D, Hh = self.rig.solve(local=loc, world=world, root_t=rt)
            b = self.rig.to_basis(D, rt)
            if bones:
                b = {k: v for k, v in b.items() if k in bones}
            out.append(b)
        return out


def E(x=0, y=0, z=0):
    return C.eul(x, y, z)


def ride_base(phi, lean=10.0):
    """Seated gallop: rider absorbs the horse's bounce through hips/knees, torso rocks."""
    tau = 2 * math.pi
    c = math.cos(tau * (phi - 0.86))
    loc = {
        "root": E(1.5 * math.cos(tau * (phi - 0.1))),
        "hips": E(3 + 3 * c),
        "spine": E(lean * 0.5 + 3 * math.cos(tau * (phi - 0.02))),
        "chest": E(lean * 0.5 + 2 * math.cos(tau * (phi - 0.1))),
        "neck": E(-5 - 2 * math.cos(tau * (phi - 0.15))),
        "head": E(-4 - 3 * math.cos(tau * (phi - 0.2))),
        "coat.B": E(-12 + 8 * math.sin(tau * (phi - 0.2))),
    }
    for sfx, s in ((".L", 1), (".R", -1)):
        loc["thigh" + sfx] = E(-2 * c)
        loc["shin" + sfx] = E(-4 * c)
        loc["foot" + sfx] = E(4 * c)
        # reins hands follow the horse's head pump
        loc["upperarm" + sfx] = E(-4 + 4 * math.cos(tau * (phi - 0.55)))
        loc["forearm" + sfx] = E(-3 + 5 * math.cos(tau * (phi - 0.6)))
        loc["hand" + sfx] = E(10)
    rt = (0, 0.0, 0.018 * c + 0.01)
    return loc, rt


AIM_DIR = Vector((-0.62, -0.78, 0.06)).normalized()  # forward-right (rider's right = -X)


def aim_upper(rig, loc, rt, direction, turn=-22.0):
    loc = dict(loc)
    loc["chest"] = loc.get("chest", Quaternion()) @ E(0, 0, turn * 0.6)
    loc["spine"] = loc.get("spine", Quaternion()) @ E(0, 0, turn * 0.4)
    loc["neck"] = loc.get("neck", Quaternion()) @ E(0, 0, turn * 0.5)
    loc["head"] = E(-2, 0, turn * 0.6)
    loc["shoulder.R"] = E(0, 0, -8)
    world = {}
    q = aim_q(rig, "upperarm.R", direction)
    world["upperarm.R"] = q
    world["forearm.R"] = aim_q(rig, "forearm.R", direction)
    world["hand.R"] = aim_q(rig, "hand.R", direction)
    return loc, world, rt


def ride_clip(A, n=32):
    def pose(t, phi):
        loc, rt = ride_base(phi)
        return loc, {}, rt
    return A.frames(n, pose)


def rideaim_clip(A, n=32):
    tau = 2 * math.pi

    def pose(t, phi):
        loc, rt = ride_base(phi, lean=6.0)
        d = (AIM_DIR + Vector((0, 0, 0.012 * math.cos(tau * (phi - 0.9))))).normalized()
        loc["upperarm.L"] = E(-8)
        return aim_upper(A.rig, loc, rt, d)
    return A.frames(n, pose)


UPPER = ["spine", "chest", "neck", "head", "shoulder.R", "upperarm.R", "forearm.R", "hand.R"]


def shoot_clip(A, n=15):
    """Short recoil on the aimed arm (0.25 s).  Frame 0 == RideAim reference, so
    three.js AnimationUtils.makeClipAdditive(clip) works directly."""
    def pose(t, u):
        loc, rt = ride_base(0.0, lean=6.0)
        k = (t / 0.04) if t < 0.04 else math.exp(-(t - 0.04) / 0.06)
        k = max(0.0, k) * (1 - C.smoothstep((t - 0.18) / 0.07))
        up = Vector((0, 0, 0.35 * k))
        d = (AIM_DIR + up).normalized()
        loc2, world, rt = aim_upper(A.rig, loc, rt, d)
        world["hand.R"] = world["hand.R"].copy()
        world["hand.R"] = aim_q(A.rig, "hand.R", (AIM_DIR + Vector((0, 0, 0.8 * k))).normalized())
        loc2["chest"] = loc2["chest"] @ E(-4 * k)
        loc2["head"] = loc2["head"] @ E(-3 * k)
        return loc2, world, rt
    return A.frames(n, pose, bones=UPPER)


def falloff_clip(A):
    """Thrown backwards over the croup and lands on his back ~1.6 m behind the seat
    (ground = z -1.64 relative to the seat).  Detach from the horse on trigger."""
    G = -1.64
    keys = [0.0, 0.14, 0.42, 0.72, 0.9, 1.4]
    P = [
        dict(_t=(0, 0, 0.01), _r=(0, 0, 0), spine=(5, 0, 0), chest=(5, 0, 0), neck=(-5, 0, 0), head=(-4, 0, 0),
             thigh=(0, 0, 0), shin=(0, 0, 0), ua=(-4, 0, 0), fa=(-3, 0, 0)),
        dict(_t=(0, 0.10, 0.18), _r=(-35, 0, 8), spine=(-15, 0, 0), chest=(-12, 0, 0), neck=(15, 0, 0), head=(20, 0, 0),
             thigh=(-10, 0, 0), shin=(-20, 0, 0), ua=(-120, 0, 30), fa=(-20, 0, 0)),
        dict(_t=(0, 0.80, 0.05), _r=(-95, 0, 25), spine=(-10, 0, 0), chest=(-10, 0, 0), neck=(10, 0, 0), head=(10, 0, 0),
             thigh=(-20, 0, 10), shin=(20, 0, 0), ua=(-150, 0, 40), fa=(-10, 0, 0)),
        dict(_t=(0, 1.45, G + 0.16), _r=(-100, 0, 30), spine=(0, 0, 0), chest=(-5, 0, 0), neck=(-10, 0, 0), head=(-15, 0, 0),
             thigh=(-40, 0, 10), shin=(40, 0, 0), ua=(-110, 0, 50), fa=(-20, 0, 0)),
        dict(_t=(0, 1.60, G + 0.20), _r=(-85, 0, 35), spine=(8, 0, 0), chest=(6, 0, 0), neck=(-5, 0, 0), head=(-5, 0, 0),
             thigh=(-55, 0, 12), shin=(35, 0, 0), ua=(-95, 0, 55), fa=(-15, 0, 0)),
        dict(_t=(0, 1.65, G + 0.12), _r=(-92, 0, 32), spine=(0, 0, 0), chest=(0, 0, 0), neck=(-12, 0, 0), head=(-18, 0, 10),
             thigh=(-72, 0, 8), shin=(20, 0, 0), ua=(-80, 0, 60), fa=(-25, 0, 0)),
    ]
    return keyed_clip(A, 84, keys, P)


def keyed_clip(A, n, keys, P, stand=False):
    def pose(t, u):
        p = C.keyposes(keys, P, t)
        loc = {}
        for b in ("spine", "chest", "neck", "head", "hips", "coat.B"):
            if b in p:
                loc[b] = C.eul(*p[b])
        for sfx, s in ((".L", 1), (".R", -1)):
            def m(v):
                return (v[0], v[1] * s, v[2] * s)
            if "thigh" in p:
                loc["thigh" + sfx] = C.eul(*m(p["thigh"]))
            if "shin" in p:
                loc["shin" + sfx] = C.eul(*m(p["shin"]))
            if "foot" in p:
                loc["foot" + sfx] = C.eul(*m(p["foot"]))
            if "ua" in p:
                loc["upperarm" + sfx] = C.eul(*m(p["ua"]))
            if "fa" in p:
                loc["forearm" + sfx] = C.eul(*m(p["fa"]))
        r = p["_r"]
        loc["root"] = C.rz(r[2]) @ C.ry(r[1]) @ C.rx(r[0])
        return loc, {}, p["_t"]
    return A.frames(n, pose)


def stand_legs(rig, spread=0.04, knee=4.0, lean=0.0):
    w = {}
    for sfx, s in ((".L", 1), (".R", -1)):
        d = Vector((spread * s, -math.sin(math.radians(knee)) * 0.3, -1))
        w["thigh" + sfx] = aim_q(rig, "thigh" + sfx, d)
        w["shin" + sfx] = aim_q(rig, "shin" + sfx, Vector((spread * s * 0.3, 0.06, -1)))
        w["foot" + sfx] = aim_q(rig, "foot" + sfx, Vector((0.12 * s, -1, -0.42)))
    return w


def stand_arms(rig, w, sway=0.0):
    for sfx, s in ((".L", 1), (".R", -1)):
        w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, Vector((0.16 * s, 0.02 + sway, -1)))
        w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, Vector((0.08 * s, -0.22 + sway, -1)))
        w["hand" + sfx] = aim_q(rig, "hand" + sfx, Vector((0.04 * s, -0.12, -1)))
    return w


def standidle_clip(A, n=180):
    tau = 2 * math.pi

    def pose(t, u):
        b = math.sin(tau * u)
        loc = {
            "hips": E(-4, 0, 2 * b),
            "spine": E(-2 + 0.8 * math.sin(tau * u * 2), 0, -1 * b),
            "chest": E(-1 + 0.8 * math.sin(tau * u * 2)),
            "neck": E(2),
            "head": E(0, 0, 8 * math.sin(tau * (u - 0.1))),
            "coat.B": E(0),
        }
        w = stand_legs(A.rig)
        w = stand_arms(A.rig, w, 0.02 * b)
        w["coat.B"] = aim_q(A.rig, "coat.B", Vector((0, 0.12, -1)))
        rt = (0.008 * b, 0, A.stand_root_z - 0.012)
        return loc, w, rt
    return A.frames(n, pose)


def standshoot_clip(A, n=36):
    """Aim forward (-Y), fire at t=0, recoil, settle back on aim (0.6 s)."""
    def pose(t, u):
        k = (t / 0.04) if t < 0.04 else math.exp(-(t - 0.04) / 0.07)
        loc = {"hips": E(-4, 0, -12), "spine": E(-2, 0, 6), "chest": E(-2 - 4 * k, 0, 8), "neck": E(0, 0, -6),
               "head": E(2 - 3 * k, 0, -8)}
        w = stand_legs(A.rig, spread=0.09)
        w = stand_arms(A.rig, w)
        d = Vector((-0.10, -1, 0.02)).normalized()
        w["upperarm.R"] = aim_q(A.rig, "upperarm.R", d)
        w["forearm.R"] = aim_q(A.rig, "forearm.R", (d + Vector((0, 0, 0.25 * k))).normalized())
        w["hand.R"] = aim_q(A.rig, "hand.R", (d + Vector((0, 0, 0.7 * k))).normalized())
        w["coat.B"] = aim_q(A.rig, "coat.B", Vector((0, 0.12, -1)))
        return loc, w, (0, 0, A.stand_root_z - 0.02)
    return A.frames(n, pose)


def die_clip(A, n=108):
    """Standing death: hit in the chest, stagger back, knees buckle, fall on his back."""
    Z = A.stand_root_z
    keys = [0.0, 0.18, 0.55, 0.95, 1.2, 1.8]
    tl = [(0, 0, Z - 0.012), (0, 0.06, Z - 0.02), (0, 0.18, Z - 0.38), (0, 0.55, 0.12 - 0.10 + 0.02), (0, 0.6, 0.06), (0, 0.62, 0.02)]
    rl = [(0, 0, 0), (-12, 0, 5), (-18, 0, 12), (-88, 0, 15), (-86, 0, 16), (-90, 0, 16)]
    sp = [(-2, 0, 0), (-18, 0, 0), (12, 0, 0), (-4, 0, 0), (4, 0, 0), (0, 0, 0)]
    hd = [(0, 0, 0), (25, 0, 0), (-15, 0, 0), (-10, 0, 20), (-20, 0, 25), (-22, 0, 30)]
    legs = [0, 0.1, 1.0, 0.6, 0.4, 0.3]  # knee buckle amount
    arms = [0, 0.8, 0.5, 1.0, 1.0, 1.0]

    def pose(t, u):
        p = C.keyposes(keys, [dict(t=a, r=b, s=c, h=d, l=(e,), a=(f,)) for a, b, c, d, e, f in zip(tl, rl, sp, hd, legs, arms)], t)
        lb = p["l"][0]
        ab = p["a"][0]
        loc = {"spine": E(*p["s"]), "chest": E(p["s"][0] * 0.6), "neck": E(p["h"][0] * 0.5), "head": E(*p["h"])}
        w = {}
        root_q = C.rz(p["r"][2]) @ C.rx(p["r"][0])
        for sfx, s in ((".L", 1), (".R", -1)):
            # blend legs between standing and buckled (thigh forward, shin back)
            th = Vector((0.05 * s, -0.9 * lb, -1 + 0.4 * lb))
            sh = Vector((0.03 * s, 0.9 * lb, -1 + 0.2 * lb))
            w["thigh" + sfx] = root_q @ aim_q(A.rig, "thigh" + sfx, th)
            w["shin" + sfx] = root_q @ aim_q(A.rig, "shin" + sfx, sh)
            w["foot" + sfx] = root_q @ aim_q(A.rig, "foot" + sfx, Vector((0.1 * s, -1, -0.4 + 0.5 * lb)))
            ua = Vector((0.5 * s * ab + 0.15 * s, -0.3 * ab, -1 + 1.2 * ab))
            w["upperarm" + sfx] = root_q @ aim_q(A.rig, "upperarm" + sfx, ua)
            w["forearm" + sfx] = root_q @ aim_q(A.rig, "forearm" + sfx, ua + Vector((0, -0.4, 0.2)))
        loc["root"] = root_q
        return loc, w, p["t"]
    return A.frames(n, pose)


# ----------------------------------------------------------------------------
def build_mesh(name, prims, h, tris, color_fn, tex, rough=0.85):
    ob = C.build_sdf_mesh(name, prims, h, tris)
    C.smart_uv(ob)
    img = C.bake_texture(ob, tex, color_fn, name + "_tex")
    C.assign_material(ob, C.image_material(name + "_mat", img, roughness=rough))
    return ob


def main():
    C.reset_scene()
    bp = body_prims()
    body = build_mesh("Body", bp, 0.0065, 4700, body_color(bp), 1024)
    dp = duster_prims(bp)
    duster = build_mesh("Duster", dp, 0.008, 3000, cloth_color(dp, (0.50, 0.41, 0.30), duster_pattern), 512)
    pp = poncho_prims(bp)
    poncho = build_mesh("Poncho", pp, 0.009, 900, cloth_color(pp, (0.55, 0.45, 0.30), poncho_pattern), 256)
    bdp = bandana_prims(bp)
    bandana = build_mesh("Bandana", bdp, 0.005, 360, cloth_color(bdp, (0.50, 0.10, 0.07), bandana_pattern, 0.015), 128)

    hats = []
    for mk, base in ((make_hat_wide, (0.36, 0.28, 0.20)), (make_hat_bowler, (0.14, 0.12, 0.11))):
        ob = mk()
        finish_lathe(ob)
        C.smart_uv(ob)
        def hat_fn(P, N, ex, b=base):
            c = np.tile(np.array(b), (len(P), 1)) * (0.85 + 0.3 * C.fbm(P, 30, 2))[:, None]
            return hat_pattern(P, N, c)
        img = C.bake_texture(ob, 256, hat_fn, ob.name + "_tex")
        C.assign_material(ob, C.image_material(ob.name + "_mat", img, roughness=0.9))
        hats.append(ob)

    arm = C.build_armature("RiderRig", bone_list())
    rig = C.Rig(arm)
    segs = {b: (np.array(rig.head[b]), np.array(rig.tail[b])) for b in rig.order}
    C.compute_weights(body, bp, segs, tau=0.012, smooth_iters=3)
    C.compute_weights(duster, dp, segs, tau=0.02, smooth_iters=4)
    C.compute_weights(poncho, pp, segs, tau=0.02, smooth_iters=3)
    C.compute_weights(bandana, bdp, segs, tau=0.01, smooth_iters=2)
    for h in hats:
        C.rigid_weights(h, "head")
    meshes = [body, duster, poncho, bandana] + hats
    for ob in meshes:
        C.bind(ob, arm)

    # weapon grip empty on hand.R: in the palm, -Y along the hand, +Z up
    g = bpy.data.objects.new("Grip_R", None)
    g.empty_display_type = "ARROWS"
    g.empty_display_size = 0.1
    bpy.context.scene.collection.objects.link(g)
    g.parent = arm
    g.parent_type = "BONE"
    g.parent_bone = "hand.R"
    bpy.context.view_layer.update()
    hd = (rig.tail["hand.R"] - rig.head["hand.R"]).normalized()
    Mg = frame_mat(hd, (1, 0, 0))  # columns side, dir, up ; want -Y = dir
    rot = Matrix((Mg.col[0], -Mg.col[1], Mg.col[2])).transposed()
    palm = rig.head["hand.R"] + (rig.tail["hand.R"] - rig.head["hand.R"]) * 0.45 + Vector((0, 0, -0.012))
    g.matrix_world = Matrix.Translation(palm) @ rot.to_4x4()

    A = RiderAnim(rig)
    C.write_action(arm, "Ride", ride_clip(A), loop=True)
    C.write_action(arm, "RideAim", rideaim_clip(A), loop=True)
    C.write_action(arm, "Shoot", shoot_clip(A))
    C.write_action(arm, "FallOff", falloff_clip(A))
    C.write_action(arm, "StandIdle", standidle_clip(A), loop=True)
    C.write_action(arm, "StandShoot", standshoot_clip(A))
    C.write_action(arm, "DieStanding", die_clip(A))
    arm.animation_data.action = bpy.data.actions["Ride"]

    tot = 0
    for ob in meshes:
        print(f"[rider] {ob.name}: {C.tri_count(ob)} tris")
        tot += C.tri_count(ob)
    print("[rider] total tris", tot, "stand_root_z", A.stand_root_z)
    C.export_glb(OUT, [arm, g] + meshes)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.PREVIEWS, "rider_build.blend"))


if __name__ == "__main__":
    main()
