"""Build public/assets/models/rider.glb  (SCHOFIELD)

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_rider.py

Seated riding pose is the bind pose.  Origin = the saddle seat contact point:
parent the rider to the horse's `Mount` empty with an identity transform and
the hips sit in the saddle.  The standing clips (StandIdle, StandShoot,
DieStanding) lift the root so the FEET are at the origin -> place the rider at
ground level for those.

Meshes (toggle in code): Body, Duster, Hat_Wide, Hat_Bowler (the old townsman pieces)
        Driver only: Body_Driver (replaces Body), Coat_Driver, Hat_Driver,
        Moustache_Walrus, Neckerchief_Driver, Watch_Driver
Weapons: hand.R bone head sits in the palm; its local frame (as three.js sees it)
        has +Z along the hand/barrel and +Y up, so a gun added as a child of hand.R
        with identity transform aims correctly.  Grip_R is an equivalent empty.
Clips:  Ride, RideAim, Shoot, FallOff, StandIdle, StandShoot, DieStanding,
        Drive (on the coach box: feet on the footboard, hands on the lines)
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


def palm(s):
    """Grip point in the palm (hand.X bone head)."""
    j = J(s)
    w, h = np.array(j["wri"]), np.array(j["hnd"])
    return tuple(w + (h - w) * 0.45 + np.array([0, 0, -0.012]))


HAND_FWD = {s: (Vector(J(s)["hnd"]) - Vector(J(s)["wri"])) * Vector((1, 1, 0)) for s in (1, -1)}


def hand_q(side, forward, up=(0, 0, 1)):
    """World delta for hand bone so the hand points along `forward` with back-of-hand/gun-top toward `up`."""
    f0 = HAND_FWD[side].normalized()
    Mr = frame_mat(f0, Vector((0, 0, 1)).cross(f0))
    Mt = frame_mat(Vector(forward).normalized(), Vector(up).cross(Vector(forward).normalized()))
    return (Mt @ Mr.transposed()).to_quaternion()


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
            ("hand" + sfx, palm(s), tuple(np.array(palm(s)) + np.array([0, 0, 0.08])), "forearm" + sfx, False,
             tuple((np.array(j["hnd"]) - np.array(j["wri"])) * np.array([1, 1, 0]))),
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
            E(j["wri"] + (j["hnd"] - j["wri"]) * 0.5, (0.035, 0.05, 0.042), "glove", ["hand" + sfx], k=0.015),
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
            C.box((0.285 * s, -0.08, -0.15), (0.014, 0.15, 0.14), 0.01, "coat", ["hips"], k=0.05, rot=_roty(-8 * s)),
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
# the coach driver, after a period photograph: a heavy-set older man with a
# grey walrus moustache, a pale high-crowned hat, a loose pale neckerchief, a
# long dark coat worn open over a checked wool vest and watch chain, and pale
# canvas trousers over dark boots.  Body_Driver stands in for Body (same rig,
# same clips); the rest are driver-only overlays.
# ----------------------------------------------------------------------------
def driver_body_prims():
    E, K = C.ell, C.cone
    P = [
        # head: broad and fleshy, heavy brow, jowls and a double chin
        E((0, 0.004, 0.838), (0.083, 0.097, 0.106), "skin", ["head"], k=0.02),
        E((0, -0.018, 0.768), (0.071, 0.07, 0.058), "skin", ["head"], k=0.045),  # jaw
        E((0, -0.07, 0.737), (0.028, 0.018, 0.02), "skin", ["head"], k=0.02),  # chin
        E((0, -0.042, 0.742), (0.052, 0.046, 0.03), "skin", ["neck", "head"], k=0.035),  # double chin
        E((0, -0.079, 0.866), (0.066, 0.022, 0.017), "skin", ["head"], k=0.02),  # brow ridge
        K((0, -0.092, 0.855), (0, -0.108, 0.812), 0.012, 0.016, "skin", ["head"], k=0.015),  # nose
        E((0, -0.112, 0.806), (0.019, 0.017, 0.016), "skin", ["head"], k=0.012),  # nose tip
        E((0, -0.084, 0.772), (0.026, 0.012, 0.009), "skin", ["head"], k=0.01),  # lower lip
        E((0, 0.018, 0.866), (0.087, 0.096, 0.086), "hair", ["head"], k=0.015),
        K((0, 0.025, 0.60), (0, 0.004, 0.77), 0.068, 0.06, "skin", ["neck", "head"], k=0.03),  # neck
        # torso: broad chest over a big belly (vest painted on), trousers below
        E((0, 0.035, 0.49), (0.178, 0.122, 0.145), "torso", ["chest"], k=0.06),
        E((0, -0.035, 0.29), (0.172, 0.16, 0.15), "torso", ["spine", "chest"], k=0.08),
        E((0, 0.035, 0.145), (0.178, 0.13, 0.10), "pants", ["hips"], k=0.06),
        E((0, 0.09, 0.06), (0.15, 0.10, 0.075), "pants", ["hips"], k=0.05),  # seat
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        shin = j["ank"] - j["kne"]
        P += [
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), j["elb"], 0.064, 0.05, "shirt", ["upperarm" + sfx, "shoulder" + sfx], k=0.03),
            K((0.07 * s, 0.035, 0.56), j["arm"], 0.078, 0.066, "shirt", ["shoulder" + sfx, "chest"], k=0.05),
            K(j["elb"], j["wri"], 0.05, 0.04, "shirt", ["forearm" + sfx], k=0.02),
            E(j["wri"] + (j["hnd"] - j["wri"]) * 0.5, (0.037, 0.053, 0.044), "hand", ["hand" + sfx], k=0.015),
            K(j["hip"] + np.array([0.0, 0.0, -0.01]), j["kne"], 0.108, 0.07, "pants", ["thigh" + sfx, "hips"], k=0.05),
            E(j["kne"], (0.07, 0.072, 0.072), "pants", ["thigh" + sfx, "shin" + sfx], k=0.02),
            K(j["kne"] + shin * 0.12, j["ank"] + np.array([0, 0, 0.02]), 0.075, 0.07, "pants", ["shin" + sfx], k=0.02),
            E(j["ank"] + np.array([0, 0.0, -0.005]), (0.072, 0.076, 0.045), "pants", ["shin" + sfx], k=0.02),  # bunched hem
            K(j["ank"] + np.array([0, 0.025, -0.03]), j["toe"], 0.05, 0.037, "boot", ["foot" + sfx], k=0.02),
            E(j["ank"] + np.array([0, 0.03, -0.055]), (0.036, 0.036, 0.02), "heel", ["foot" + sfx], k=0.005),
            E((0.031 * s, -0.082, 0.843), (0.011, 0.007, 0.0075), "eye", ["head"], k=0.004),
            E((0.044 * s, -0.071, 0.806), (0.03, 0.026, 0.028), "skin", ["head"], k=0.03),  # cheek
            E((0.052 * s, -0.045, 0.765), (0.028, 0.031, 0.031), "skin", ["head"], k=0.03),  # jowl
            E((0.015 * s, -0.099, 0.803), (0.012, 0.01, 0.01), "skin", ["head"], k=0.008),  # nostril wing
            E((0.086 * s, 0.008, 0.82), (0.016, 0.026, 0.034), "skin", ["head"], k=0.01),  # ear
        ]
    return P


def _mix(c, m, col):
    m = np.clip(m, 0, 1)[:, None]
    return c * (1 - m) + np.array(col) * m


def driver_body_color(prims):
    labs = ["skin", "hair", "torso", "shirt", "hand", "pants", "boot", "heel", "eye"]
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        n = C.fbm(P, 30.0, 2, seed=7)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        cols = {
            "skin": (0.56, 0.41, 0.33), "hair": (0.56, 0.54, 0.51), "torso": (0.11, 0.11, 0.12),
            "shirt": (0.70, 0.68, 0.62), "hand": (0.55, 0.40, 0.31), "pants": (0.60, 0.54, 0.42),
            "boot": (0.13, 0.095, 0.07), "heel": (0.08, 0.06, 0.05), "eye": (0.07, 0.055, 0.05),
        }
        c = sum(lw[k][:, None] * np.array(cols[k]) for k in labs)
        front = y < -0.03

        # vest: dark wool, blue-grey windowpane check with a brown overcheck
        g = 0.026
        u = np.where(np.abs(N[:, 0]) > 0.75, y, x)
        fu, fz = np.abs((u / g) % 1.0 - 0.5), np.abs((z / g) % 1.0 - 0.5)
        fu2, fz2 = np.abs(((u / g) + 0.5) % 1.0 - 0.5), np.abs(((z / g) + 0.5) % 1.0 - 0.5)
        vc = np.tile(np.array(cols["torso"]), (len(P), 1))
        seen = np.clip((0.07 - y) / 0.05, 0, 1)  # the back is under the coat: plain
        l2 = np.clip((np.maximum(fu2, fz2) - 0.44) / 0.03, 0, 1)
        l1 = np.clip((np.maximum(fu, fz) - 0.39) / 0.04, 0, 1)
        vc = _mix(vc, l2 * 0.8 * seen, (0.24, 0.16, 0.10))
        vc = _mix(vc, l1 * 0.85 * seen, (0.30, 0.33, 0.38))
        bottom = 0.205 - 0.035 * np.clip(1 - ax / 0.07, 0, 1) * front
        vest = (lw["torso"] + lw["shirt"] * (ax < 0.2) * (z > 0.40)) * (z > bottom) * (z < 0.63)
        opening = front & (ax < 0.012 + 0.075 * np.clip((z - 0.46) / 0.13, 0, 1)) & (z > 0.45)
        vest = vest * ~opening
        c = _mix(c, vest, (0, 0, 0)) + vc * np.clip(vest, 0, 1)[:, None]
        # shirt front in the V, trousers under the vest's points
        c = _mix(c, lw["torso"] * opening, cols["shirt"])
        c = _mix(c, lw["torso"] * (z <= bottom), cols["pants"])
        # vest buttons, pocket welts, a nickel badge on his left breast
        k = np.round((z - 0.235) / 0.045)
        btn = front & (k >= 0) & (k <= 5) & (np.hypot(x, z - (0.235 + k * 0.045)) < 0.0065)
        c = _mix(c, btn * 1.0, (0.52, 0.47, 0.40))
        welt = front & (np.abs(z - 0.29) < 0.003) & (np.abs(ax - 0.095) < 0.034)
        c = _mix(c, welt * 0.8, (0.30, 0.30, 0.33))
        th = np.arctan2(z - 0.47, x - 0.088)
        star = np.hypot(x - 0.088, z - 0.47) < 0.011 * (0.62 + 0.38 * np.cos(5 * th))
        c = _mix(c, (front & star) * 1.0, (0.66, 0.65, 0.62))

        # shirt collar band showing at the base of the neck
        collar = lw["skin"] * (z > 0.595) * (z < 0.635)
        c = _mix(c, collar, cols["shirt"])

        # face: ruddy nose and cheeks, heavy grey brows, lined forehead, eye shadow
        face = lw["skin"] * (y < -0.035) * (z > 0.70)
        red = np.exp(-((ax / 0.022) ** 2 + ((y + 0.11) / 0.02) ** 2 + ((z - 0.807) / 0.02) ** 2))
        red += 0.7 * np.exp(-(((ax - 0.045) / 0.024) ** 2 + ((z - 0.805) / 0.022) ** 2)) * np.clip((-0.04 - y) / 0.03, 0, 1)
        c = _mix(c, face * np.clip(red, 0, 1) * 0.6, (0.66, 0.33, 0.26))
        brow_z = 0.869 + 0.003 * np.clip((ax - 0.03) / 0.03, -1, 1)
        brow = face * (np.abs(z - brow_z) < 0.0085 * (1 - 0.3 * np.clip((ax - 0.045) / 0.02, 0, 1))) * (ax > 0.008) * (ax < 0.064)
        c = _mix(c, brow * (0.75 + 0.25 * C.fbm(P, 400.0, 2, seed=9)), (0.58, 0.56, 0.52))
        # eyes: dark slits under the lids with a glint of white
        slit = face * np.exp(-(((ax - 0.031) / 0.011) ** 2 + ((z - 0.8435) / 0.0035) ** 2))
        c = _mix(c, slit, (0.09, 0.07, 0.06))
        c = _mix(c, face * np.exp(-(((ax - 0.022) / 0.004) ** 2 + ((z - 0.8435) / 0.0025) ** 2)) * 0.6, (0.62, 0.58, 0.52))
        sock = face * np.exp(-(((ax - 0.031) / 0.015) ** 2 + ((z - 0.846) / 0.008) ** 2))
        c *= (1 - 0.2 * sock)[:, None]
        wrinkle = face * (z > 0.88) * (z < 0.925) * (np.sin(z * 2 * np.pi / 0.009 + 3 * x) > 0.75)
        c *= (1 - 0.12 * wrinkle)[:, None]
        crow = face * (ax > 0.052) * (np.abs(z - 0.842) < 0.014) * (np.sin((z - 0.842) * 900 + ax * 300) > 0.6)
        c *= (1 - 0.10 * crow)[:, None]
        # jowl line under the cheeks and a crease under the lower lip
        jowl = face * np.exp(-(((ax - 0.05) / 0.012) ** 2 + ((z - 0.782 + 0.4 * (ax - 0.05)) / 0.02) ** 2)) * (y < -0.06)
        c *= (1 - 0.18 * jowl)[:, None]
        c *= (1 - 0.2 * face * np.exp(-((ax / 0.018) ** 2 + ((z - 0.755) / 0.003) ** 2)))[:, None]
        lip = face * np.exp(-((ax / 0.022) ** 2 + ((z - 0.772) / 0.006) ** 2))
        c = _mix(c, lip * 0.6, (0.50, 0.29, 0.25))
        # grey hair: temples, short sideburns, the back of the head above the nape
        side = lw["skin"] * np.clip((ax - 0.062) / 0.008, 0, 1) * np.clip((y + 0.035) / 0.01, 0, 1) \
            * np.clip((0.012 - y) / 0.01, 0, 1) * np.clip((z - 0.80) / 0.01, 0, 1) * (z < 0.87)
        nape = lw["skin"] * np.clip((y - 0.03) / 0.015, 0, 1) * np.clip((z - 0.775) / 0.01, 0, 1) * (z < 0.87)
        hair = np.clip(lw["hair"] + side + nape, 0, 1)
        hc = np.array(cols["hair"]) * (0.8 + 0.35 * C.fbm(P * np.array([1, 1, 0.25]), 300.0, 2, seed=10))[:, None]
        c = c * (1 - hair[:, None]) + hc * hair[:, None]

        # worn pale canvas: vertical wear, grime at the knees, seat and hems
        pants = lw["pants"] + lw["torso"] * (z <= bottom)
        wear = C.fbm(P * np.array([1.0, 1.0, 0.2]), 60.0, 3, seed=11)
        grime = np.clip((-0.35 - z) / 0.25, 0, 1) + 0.5 * np.exp(-((z + 0.18) / 0.06) ** 2)
        pc = c * (0.88 + 0.2 * wear)[:, None]
        pc = _mix(pc, grime * 0.45, (0.36, 0.31, 0.24))
        c = c * (1 - pants[:, None]) + pc * pants[:, None]

        c *= (0.94 + 0.12 * n)[:, None]
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.02)
        aw = 0.55 - 0.3 * face  # the face's hollows read from the geometry; keep AO light there
        c *= (1 - aw + aw * ao)[:, None]
        return c

    return fn


def moustache_prims():
    """Thick grey walrus moustache: covers the upper lip, droops past the mouth."""
    E, K = C.ell, C.cone
    P = [E((0, -0.104, 0.785), (0.030, 0.017, 0.015), "m", ["head"], k=0.012)]
    for s in (1, -1):
        P += [
            E((0.027 * s, -0.099, 0.781), (0.025, 0.016, 0.017), "m", ["head"], k=0.012),
            K((0.037 * s, -0.094, 0.778), (0.052 * s, -0.08, 0.743), 0.016, 0.007, "m", ["head"], k=0.012),
        ]
    return P


def moustache_color(prims):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        strands = C.fbm(P * np.array([1.0, 1.0, 0.18]), 520.0, 2, seed=12)
        c = np.tile(np.array((0.66, 0.64, 0.60)), (len(P), 1)) * (0.62 + 0.55 * strands)[:, None]
        # tobacco-stained fringe over the mouth, darker roots against the face
        stain = np.exp(-((P[:, 0] / 0.02) ** 2 + ((P[:, 2] - 0.772) / 0.008) ** 2))
        c = _mix(c, stain * 0.45, (0.55, 0.48, 0.36))
        c *= (0.55 + 0.45 * np.clip((-0.088 - P[:, 1]) / 0.02, 0, 1))[:, None]
        ao = C.sdf_ao(solid, P, N, steps=3, dist=0.006)
        return c * (0.6 + 0.4 * ao)[:, None]

    return fn


def neckerchief_prims(dbp):
    """Pale neckerchief tied loosely at the throat, ends hanging over the vest."""
    E, K = C.ell, C.cone
    neck = [p for p in dbp if p.kind == "cone" and p.bones == ["neck", "head"]]
    P = inflate(neck, 0.017, None, "kerchief")
    P += [
        C.box((0, 0, 1.0), (1, 1, 0.295), 0.0, "cut", [], sub=True, k=0.01),  # above z 0.705
        C.box((0, 0, 0.0), (1, 1, 0.61), 0.0, "cut", [], sub=True, k=0.01),  # below z 0.61
        E((0, -0.079, 0.636), (0.026, 0.02, 0.021), "kerchief", ["neck", "chest"], k=0.012),  # knot
        K((0.004, -0.083, 0.628), (0.026, -0.098, 0.566), 0.018, 0.007, "kerchief", ["chest"], k=0.01, scale=(1.25, 0.5, 1)),
        K((-0.004, -0.083, 0.628), (-0.02, -0.104, 0.574), 0.016, 0.006, "kerchief", ["chest"], k=0.01, scale=(1.25, 0.5, 1)),
    ]
    return P


def kerchief_pattern(P, N, c):
    folds = np.sin(np.arctan2(P[:, 1], P[:, 0]) * 9 + P[:, 2] * 60)
    return c * (0.9 + 0.1 * folds)[:, None]


def driver_coat_prims(dbp):
    """Long dark coat worn open.  A solid offset of the body with the front
    carved away (only near the body, so the sleeves added after it survive)."""
    E, K = C.ell, C.cone
    core = [p for p in dbp if p.label == "torso" or (p.label == "pants" and p.bones == ["hips"])]
    shoulders = [p for p in dbp if p.label == "shirt" and p.bones[0].startswith("shoulder")]
    P = inflate(core + shoulders, 0.024, None, "coat")
    P += [
        E((0, 0.04, 0.15), (0.205, 0.158, 0.11), "coat", ["hips"], k=0.06),
        E((0, 0.035, 0.625), (0.098, 0.088, 0.045), "collar", ["chest", "neck"], k=0.02),
        # tail spread on the seat behind him
        C.box((0, 0.21, -0.03), (0.2, 0.016, 0.17), 0.012, "coat", ["hips", "coat.B"], k=0.05, rot=_rotx(-38)),
    ]
    thighs = []
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        td = (j["kne"] - j["hip"]) / np.linalg.norm(j["kne"] - j["hip"])
        P += [
            K(j["hip"] + np.array([0.02 * s, 0.02, 0.03]), j["kne"] + td * 0.04 + np.array([0.0, 0.04, 0.02]), 0.13, 0.1, "coat",
              ["thigh" + sfx], k=0.05),
        ]
        thighs += [p for p in dbp if p.kind == "cone" and p.bones == ["thigh" + sfx, "hips"]]
    inner = core + thighs

    def opening(p):
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        # open from the collar to the belly; the skirt over the thighs stays whole
        w = np.interp(z, [0.10, 0.17, 0.24, 0.40, 0.52, 0.60, 0.68], [0.0, 0.11, 0.16, 0.15, 0.10, 0.05, 0.035])
        strip = np.maximum(np.abs(x) - w, y + 0.01)
        d = C.eval_sdf(inner, p)
        return np.maximum(strip, np.maximum(-(d + 0.02), d - 0.07))

    P.append(C.fnprim(opening, (-0.24, -0.42, -0.4), (0.24, 0.06, 0.74), "cut", [], sub=True, k=0.008))

    def lap(p):
        # the skirt falls open over the thighs: carve the top-inner quarter of
        # each (the front-inner side when he stands) so the trousers show
        out = np.full(len(p), 1.0)
        for s in (1, -1):
            j = {k: np.array(v) for k, v in J(s).items()}
            a, b = j["hip"], j["kne"]
            t = np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1.1)
            c = a + t[:, None] * (b - a)
            quarter = np.maximum(c[:, 2] - p[:, 2] - 0.005, (p[:, 0] - c[:, 0]) * s - 0.035)
            out = np.minimum(out, np.maximum(quarter, (p[:, 0] * s < -0.02) * 1.0))
        d = C.eval_sdf(inner, p)
        return np.maximum(np.maximum(out, p[:, 2] - 0.14), np.maximum(-(d + 0.02), d - 0.07))

    P.append(C.fnprim(lap, (-0.45, -0.5, -0.35), (0.45, 0.12, 0.2), "cut", [], sub=True, k=0.008))
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P += [
            K((0.07 * s, 0.035, 0.55), j["arm"] - np.array([0, 0, 0.01]), 0.09, 0.08, "coat", ["shoulder" + sfx, "chest"], k=0.05),
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), j["elb"], 0.082, 0.07, "coat", ["upperarm" + sfx, "shoulder" + sfx], k=0.03),
            K(j["elb"], j["wri"], 0.072, 0.064, "coat", ["forearm" + sfx], k=0.02),
        ]
    P += [C.box((0, 0, -1.0), (1, 1, 0.58), 0.0, "cut", [], sub=True, k=0.02)]
    for s in (1, -1):
        P.append(C.ell(J(s)["hnd"], (0.07, 0.10, 0.07), "cut", [], sub=True, k=0.01))
    return P, inner


def driver_coat_color(prims, inner):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        nap = C.fbm(P, 45.0, 3, seed=13)
        c = np.tile(np.array((0.20, 0.18, 0.16)), (len(P), 1)) * (0.82 + 0.36 * nap)[:, None]
        lw = C.label_weights(prims, P, ["coat", "collar"], tau=0.006)
        c = _mix(c, lw["collar"] * 0.6, (0.15, 0.135, 0.12))
        # lining where the carved front edge meets the body
        d = C.eval_sdf(inner, P)
        c = _mix(c, (d < 0.014) * (y < 0) * (z > 0.15) * 1.0, (0.27, 0.21, 0.15))
        # hip pocket flaps, worn elbows, dust toward the hem
        flap = (np.abs(z - 0.17) < 0.004) & (np.abs(np.abs(x) - 0.15) < 0.045) & (y < 0)
        c = _mix(c, flap * 0.7, (0.10, 0.09, 0.08))
        dust = np.clip((0.08 - z) / 0.4, 0, 1) * (0.6 + 0.4 * C.fbm(P, 12.0, 2, seed=14))
        c = _mix(c, dust * 0.3, (0.46, 0.40, 0.31))
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.03)
        return c * (0.5 + 0.5 * ao)[:, None]

    return fn


def make_hat_driver():
    """Pale wide-brim hat: tall rounded crown with a light crease, dark band."""
    prof = [(0.001, -0.004), (0.10, -0.004), (0.16, -0.003), (0.205, 0.0), (0.216, 0.007), (0.212, 0.013), (0.16, 0.011),
            (0.108, 0.015), (0.108, 0.05), (0.105, 0.10), (0.097, 0.135), (0.078, 0.160), (0.05, 0.172), (0.02, 0.175)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.105)
        curl = 0.026 * (math.cos(th) ** 2) * brim ** 2          # sides roll up
        droop = -0.02 * max(0.0, -math.sin(th)) * brim           # snap-brim dips at the front (-Y)
        crease = 0.0
        if z > 0.1:
            crease = -0.024 * math.exp(-((r * math.cos(th)) / 0.028) ** 2) * min(1.0, (z - 0.1) / 0.06)
        pinch = -0.006 * max(0.0, -math.sin(th)) ** 3 * (z / 0.17) if z > 0.03 else 0.0
        return pinch * math.cos(th), 0.0, curl + droop + crease

    ob = C.lathe("Hat_Driver", prof, segments=22, scale_xy=(0.96, 1.08), squash=sq)
    ob.location = HAT_C + Vector((0, 0.008, 0.004))
    return ob


def driver_hat_color(P, N, ex):
    r = np.hypot(P[:, 0], P[:, 1] - 0.013)
    z = P[:, 2]
    c = np.tile(np.array((0.70, 0.66, 0.56)), (len(P), 1)) * (0.86 + 0.26 * C.fbm(P, 40, 3, seed=15))[:, None]
    crown = r < 0.118
    sweat = crown * np.exp(-((z - 0.925) / 0.012) ** 2)
    c = _mix(c, sweat * 0.5, (0.52, 0.47, 0.38))
    band = crown * np.clip((z - 0.895) / 0.004, 0, 1) * np.clip((0.921 - z) / 0.004, 0, 1)
    c = _mix(c, band, (0.10, 0.08, 0.07))
    under = (N[:, 2] < -0.5) & ~crown
    c[under] *= 0.8
    edge = np.clip((r - 0.19) / 0.03, 0, 1)
    c = _mix(c, edge * 0.35, (0.45, 0.40, 0.33))
    return c


def surface_front(prims, x, z, y0=-0.35, y1=0.02):
    """y of the body's front surface at (x, z), by bisection along +Y."""
    lo = np.full(len(x), y0)
    hi = np.full(len(x), y1)
    for _ in range(30):
        mid = (lo + hi) * 0.5
        d = C.eval_sdf(prims, np.stack([x, mid, z], axis=1))
        out = d > 0
        lo = np.where(out, mid, lo)
        hi = np.where(out, hi, mid)
    return (lo + hi) * 0.5


def make_watch_driver(dbp):
    """Brass watch chain looped across the belly: watch in his right vest pocket,
    a bar through the middle buttonhole, the second loop to the left pocket,
    and a fob hanging from the bar."""
    solid = [p for p in dbp if not p.sub]

    def loop(a, b, sag, n=16):
        t = np.linspace(0, 1, n)
        x = a[0] + (b[0] - a[0]) * t
        z = a[1] + (b[1] - a[1]) * t - sag * 4 * t * (1 - t)
        y = surface_front(solid, x, z) - 0.004
        return [Vector(v) for v in np.stack([x, y, z], axis=1)]

    bar = (0.012, 0.281)
    parts = [
        C.tube_along("chain_a", loop((-0.098, 0.300), bar, 0.05, 12), 0.0022, sides=3),
        C.tube_along("chain_b", loop(bar, (0.098, 0.298), 0.04, 12), 0.0022, sides=3),
        C.tube_along("chain_c", loop(bar, (0.016, 0.228), 0.0, n=5), 0.0018, sides=3),
    ]

    def disc(name, c, radius, thick):
        prof = [(0.001, 0.0), (radius, 0.0), (radius * 1.08, thick * 0.5), (radius, thick), (0.001, thick * 1.1)]
        ob = C.lathe(name, prof, segments=12)
        x, z = c
        y = float(surface_front(solid, np.array([x]), np.array([z]))[0])
        e = 0.003
        nx = float(C.eval_sdf(solid, np.array([[x + e, y, z]]))[0] - C.eval_sdf(solid, np.array([[x - e, y, z]]))[0])
        ny = float(C.eval_sdf(solid, np.array([[x, y + e, z]]))[0] - C.eval_sdf(solid, np.array([[x, y - e, z]]))[0])
        nz = float(C.eval_sdf(solid, np.array([[x, y, z + e]]))[0] - C.eval_sdf(solid, np.array([[x, y, z - e]]))[0])
        nrm = Vector((nx, ny, nz)).normalized()
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(nrm)
        ob.location = Vector((x, y, z)) - nrm * 0.002
        return ob

    parts += [disc("watch", (-0.104, 0.312), 0.021, 0.009), disc("fob", (0.016, 0.218), 0.011, 0.004)]
    for ob in parts:
        C.set_active(ob)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob = C.join(parts, "Watch_Driver")
    finish_lathe(ob)
    return ob


def split_smart_uv(ob, face_masks, margin, angle=80):
    """Smart-UV each face group on its own, then pack them together, so parts
    that lie on top of each other along a projection axis (an arm across the
    belly) can't share an island."""
    import bmesh
    C.set_active(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    for fm in face_masks:
        bm = bmesh.from_edit_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        for f in bm.faces:
            f.select_set(bool(fm[f.index]))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.6)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")


def driver_face_uv(ob, k=2.3, margin=0.004, arm_w=None):
    """Smart-UV with the head scaled up so the face gets ~k^2 the texel density."""
    co = C.verts_np(ob)
    head = co[:, 2] > 0.715
    big = co.copy()
    ctr = np.array([0.0, 0.0, 0.83])
    big[head] = ctr + (co[head] - ctr) * k
    ob.data.vertices.foreach_set("co", big.astype(np.float32).ravel())
    ob.data.update()
    if arm_w is None:
        C.smart_uv(ob, margin=margin, angle=80)
    else:
        fv = np.empty(len(ob.data.polygons) * 3, dtype=np.int32)
        ob.data.polygons.foreach_get("vertices", fv)
        fa = arm_w[fv.reshape(-1, 3)].mean(1) > 0.5
        split_smart_uv(ob, [fa, ~fa], margin)
    ob.data.vertices.foreach_set("co", co.astype(np.float32).ravel())
    ob.data.update()


def sdf_mesh_detail(name, prims, h, target_tris, keep, first, hidden=None, pad=0.06):
    """C.build_sdf_mesh, but the verts where keep(P) is true stop decimating at
    `first` tris' density, so the face keeps its shape inside the budget.
    Faces whose verts are all hidden(P) (always under the coat) are dropped."""
    los, his = zip(*[p.bbox(0) for p in prims if not p.sub])
    lo, hi = np.min(los, axis=0) - pad, np.max(his, axis=0) + pad
    F, lo, n = C.sdf_grid(prims, lo, hi, h)
    verts, quads = C.surface_nets(F, lo, h)
    ob = C.mesh_from_arrays(name, verts, quads)
    C.set_active(ob)
    m = ob.modifiers.new("sm", "SMOOTH")
    m.factor = 0.5
    m.iterations = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    if hidden is not None:
        import bmesh
        hid = hidden(C.verts_np(ob))
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        dead = [f for f in bm.faces if all(hid[v.index] for v in f.verts)]
        bmesh.ops.delete(bm, geom=dead, context="FACES_ONLY")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(ob.data)
        bm.free()
        nq = len(ob.data.polygons)
        print(f"[sdf] {name}: dropped {len(dead)} of {len(quads)} faces under the coat")
        quads = quads[:nq]
    # pass 1: even decimation to `first` tris; pass 2: the rest down to the
    # target with the kept region locked (decimate's group weight is all-or-nothing)
    for ratio, locked in ((first / (len(quads) * 2), False), (None, True)):
        if locked:
            keepv = np.nonzero(keep(C.verts_np(ob)))[0]
            vg = ob.vertex_groups.new(name="detail")
            vg.add([int(i) for i in keepv], 1.0, "REPLACE")
            ratio = target_tris / C.tri_count(ob)
        m = ob.modifiers.new("dec", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = min(1.0, ratio)
        m.use_collapse_triangulate = True
        if locked:
            m.vertex_group = "detail"
            m.invert_vertex_group = True
        bpy.ops.object.modifier_apply(modifier=m.name)
    ob.vertex_groups.clear()
    C.triangulate(ob)
    C.shade_smooth(ob)
    P = C.verts_np(ob)
    print(f"[sdf] {name}: {len(quads)} quads -> {C.tri_count(ob)} tris, {int((P[:, 2] > 0.70).sum())} verts in the head")
    return ob


def skirt_follow(body, coat, Wc, names, k=4, free_tail=False):
    """Below the waist the coat takes the weights of the nearest Body_Driver
    verts, so the skirt moves exactly with the thighs under it (no poke-through
    when the legs swing forward onto the footboard)."""
    Pb, Pc = C.verts_np(body), C.verts_np(coat)
    idx = {g.index: names.index(g.name) for g in body.vertex_groups}
    Wb = np.zeros((len(Pb), len(names)))
    for v in body.data.vertices:
        for g in v.groups:
            Wb[v.index, idx[g.group]] = g.weight
    f = np.clip((0.24 - Pc[:, 2]) / 0.12, 0, 1)
    W = Wc.copy()
    for s0 in np.nonzero(f > 0)[0]:
        d = np.linalg.norm(Pb - Pc[s0], axis=1)
        nn = np.argsort(d)[:k]
        if free_tail:
            f[s0] *= np.clip((0.075 - d[nn[0]]) / 0.03, 0, 1)  # not the tail hanging free behind
        w = 1 / (d[nn] + 1e-3) ** 2
        W[s0] = (1 - f[s0]) * Wc[s0] + f[s0] * (w[:, None] * Wb[nn]).sum(0) / w.sum()
    C.apply_weights(coat, W, names)


def build_driver():
    dbp = driver_body_prims()
    cp, inner = driver_coat_prims(dbp)
    coat_solid = [p for p in cp if p.label != "cut" or p.sub]
    body = sdf_mesh_detail("Body_Driver", dbp, 0.0045, 3100, lambda P: (P[:, 2] > 0.715) & (P[:, 1] < 0.02), 13000,
                           hidden=lambda P: C.eval_sdf(coat_solid, P) < -0.012)
    driver_face_uv(body)
    img = C.bake_texture(body, 512, driver_body_color(dbp), "Body_Driver_tex")
    C.assign_material(body, C.image_material("Body_Driver_mat", img, roughness=0.85))
    coat = build_mesh("Coat_Driver", cp, 0.0075, 1450, driver_coat_color(cp, inner), 256, rough=0.92, uv_angle=89)
    mp = moustache_prims()
    mous = build_mesh("Moustache_Walrus", mp, 0.0025, 340, moustache_color(mp), 64, rough=0.95)
    kp = neckerchief_prims(dbp)
    kerchief = build_mesh("Neckerchief_Driver", kp, 0.004, 300, cloth_color(kp, (0.76, 0.72, 0.63), kerchief_pattern, 0.012), 64)
    hat = make_hat_driver()
    finish_lathe(hat)
    C.smart_uv(hat)
    img = C.bake_texture(hat, 128, driver_hat_color, "Hat_Driver_tex")
    C.assign_material(hat, C.image_material("Hat_Driver_mat", img, roughness=0.9))
    watch = make_watch_driver(dbp)
    C.smart_uv(watch)
    img = C.bake_texture(watch, 32, lambda P, N, ex: np.tile(np.array((0.78, 0.60, 0.30)), (len(P), 1)), "Watch_Driver_tex")
    C.assign_material(watch, C.image_material("Watch_Driver_mat", img, roughness=0.35, metallic=0.9))
    return dict(body=(body, dbp), coat=(coat, cp), mous=mous, kerchief=(kerchief, kp), hat=hat, watch=watch)


# ----------------------------------------------------------------------------
# the gang: outlaw pieces that mix with Body / the old hats and coats.  Every
# piece is baked in a fairly neutral colour; createRider multiplies per-variant
# colours on top, so one mesh can be a tan canvas coat or a butternut shell
# jacket.  Pearl Hart gets her own body (a woman's build in men's clothes).
# ----------------------------------------------------------------------------
def female_body_prims():
    E, K = C.ell, C.cone
    P = [
        # head: smaller, finer jaw; short hair pinned up under the hat
        E((0, 0.004, 0.838), (0.072, 0.088, 0.098), "skin", ["head"], k=0.02),
        E((0, -0.026, 0.766), (0.055, 0.062, 0.052), "skin", ["head"], k=0.04),  # jaw
        K((0, -0.084, 0.835), (0, -0.097, 0.802), 0.01, 0.013, "skin", ["head"], k=0.012),  # nose
        E((0, -0.08, 0.774), (0.018, 0.009, 0.007), "lips", ["head"], k=0.006),
        E((0, 0.016, 0.862), (0.077, 0.088, 0.08), "hair", ["head"], k=0.015),
        E((0, 0.07, 0.83), (0.04, 0.03, 0.035), "hair", ["head"], k=0.02),  # knot pinned at the back
        K((0, 0.02, 0.60), (0, 0.004, 0.77), 0.052, 0.047, "skin", ["neck", "head"], k=0.03),
        # torso: narrow shoulders and waist, bust, wider hips
        E((0, 0.03, 0.49), (0.148, 0.102, 0.128), "shirt", ["chest"], k=0.06),
        E((0, 0.025, 0.325), (0.118, 0.088, 0.11), "shirt", ["spine", "chest"], k=0.07),
        E((0, 0.035, 0.145), (0.172, 0.122, 0.10), "pants", ["hips"], k=0.06),
        E((0, 0.085, 0.06), (0.158, 0.108, 0.078), "pants", ["hips"], k=0.05),  # seat
        C.fnprim(lambda p: _torus(p, (0, 0.035, 0.17), 0.168, 0.122, 0.016, 0.026), (-0.2, -0.12, 0.13), (0.2, 0.19, 0.21),
                 "belt", ["hips"], k=0.01),
        K((-0.185, 0.0, 0.16), (-0.23, -0.07, 0.03), 0.028, 0.024, "holster", ["hips", "thigh.R"], k=0.01),
        E((-0.185, 0.03, 0.19), (0.016, 0.032, 0.028), "gun", ["hips"], k=0.005),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        elb_in = j["elb"] + (j["arm"] - j["elb"]) * 0.12
        P += [
            E((0.056 * s, -0.062, 0.462), (0.054, 0.045, 0.05), "shirt", ["chest"], k=0.03),  # bust
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), elb_in, 0.05, 0.042, "shirt", ["upperarm" + sfx, "shoulder" + sfx], k=0.03),
            K((0.065 * s, 0.03, 0.56), j["arm"], 0.058, 0.05, "shirt", ["shoulder" + sfx, "chest"], k=0.05),
            E(elb_in, (0.046, 0.046, 0.04), "cuff", ["upperarm" + sfx, "forearm" + sfx], k=0.012),  # rolled sleeve
            K(j["elb"], j["wri"], 0.036, 0.029, "skin", ["forearm" + sfx], k=0.02),
            E(j["wri"] + (j["hnd"] - j["wri"]) * 0.5, (0.03, 0.045, 0.036), "skin", ["hand" + sfx], k=0.015),
            K(j["hip"] + np.array([0.0, 0.0, -0.01]), j["kne"], 0.092, 0.056, "pants", ["thigh" + sfx, "hips"], k=0.05),
            E(j["kne"], (0.056, 0.058, 0.058), "pants", ["thigh" + sfx, "shin" + sfx], k=0.02),
            K(j["kne"] + (j["ank"] - j["kne"]) * 0.18, j["ank"], 0.054, 0.043, "boot", ["shin" + sfx], k=0.02),
            K(j["ank"] + np.array([0, 0.022, -0.028]), j["toe"], 0.043, 0.032, "boot", ["foot" + sfx], k=0.02),
            E(j["ank"] + np.array([0, 0.028, -0.052]), (0.031, 0.031, 0.018), "heel", ["foot" + sfx], k=0.005),
            E((0.028 * s, -0.075, 0.842), (0.01, 0.006, 0.006), "eye", ["head"], k=0.004),
            E((0.073 * s, 0.006, 0.82), (0.011, 0.02, 0.026), "skin", ["head"], k=0.01),  # ear
        ]
    return P


def female_body_color(prims):
    labs = ["skin", "lips", "hair", "shirt", "cuff", "pants", "belt", "holster", "gun", "boot", "heel", "eye"]
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        cols = {
            "skin": (0.64, 0.46, 0.36), "lips": (0.56, 0.33, 0.30), "hair": (0.24, 0.17, 0.11),
            "shirt": (0.64, 0.61, 0.55), "cuff": (0.60, 0.57, 0.51), "pants": (0.26, 0.23, 0.20),
            "belt": (0.30, 0.20, 0.12), "holster": (0.32, 0.20, 0.11), "gun": (0.35, 0.33, 0.30),
            "boot": (0.20, 0.14, 0.09), "heel": (0.10, 0.07, 0.05), "eye": (0.07, 0.05, 0.05),
        }
        c = sum(lw[k][:, None] * np.array(cols[k]) for k in labs)
        shirt = lw["shirt"] + lw["cuff"]
        # collarless work shirt: placket, two pockets, folds; suspenders front and back
        placket = shirt * (ax < 0.012) * (y < -0.03) * (z > 0.22)
        c = _mix(c, placket * 0.5, (0.52, 0.49, 0.44))
        k = np.round((z - 0.26) / 0.06)
        btn = (shirt > 0.5) & (y < -0.03) & (np.hypot(x, z - (0.26 + k * 0.06)) < 0.005) & (k >= 0) & (k <= 5)
        c = _mix(c, btn * 1.0, (0.80, 0.78, 0.72))
        c *= (1 - 0.12 * shirt * (C.fbm(P * np.array([1, 1, 0.3]), 50.0, 2, seed=21) > 0.6))[:, None]
        sx = np.where(y < 0, 0.075 - 0.02 * np.clip((z - 0.2) / 0.4, 0, 1), 0.02 + 0.09 * np.clip((z - 0.25) / 0.33, 0, 1))
        brace = shirt * (np.abs(ax - sx) < 0.011) * (z > 0.18) * (ax < 0.16)
        c = _mix(c, brace, (0.17, 0.12, 0.08))
        # cartridge loops and buckle on the belt
        buckle = lw["belt"] * (ax < 0.025) * (y < -0.05)
        c = _mix(c, buckle, (0.62, 0.55, 0.40))
        loops = lw["belt"] * (np.sin(np.arctan2(y - 0.035, x) * 64) > 0.2)
        c = _mix(c, loops * 0.65, (0.72, 0.58, 0.33))
        # face: soft brows, cheeks, the hair at the temples and nape
        face = lw["skin"] * (y < -0.035) * (z > 0.72)
        brow = face * (np.abs(z - 0.861) < 0.004) * (ax > 0.01) * (ax < 0.05)
        c = _mix(c, brow * 0.8, cols["hair"])
        cheek = face * np.exp(-(((ax - 0.038) / 0.02) ** 2 + ((z - 0.808) / 0.016) ** 2))
        c = _mix(c, cheek * 0.25, (0.70, 0.40, 0.34))
        nape = lw["skin"] * np.clip((y - 0.03) / 0.015, 0, 1) * np.clip((z - 0.79) / 0.01, 0, 1) * (z < 0.87)
        c = _mix(c, nape, cols["hair"])
        # dust and wear on trousers and boots
        dust = np.clip((-0.25 - z) / 0.35, 0, 1) * (lw["pants"] + lw["boot"])
        c = _mix(c, dust * 0.35, (0.48, 0.40, 0.30))
        c *= (0.93 + 0.14 * C.fbm(P, 30.0, 2, seed=22))[:, None]
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.02)
        aw = 0.55 - 0.3 * face
        return c * (1 - aw + aw * ao)[:, None]

    return fn


def sack_prims(bp):
    """Black Bart's flour sack: over the head with cut eyeholes, gathered loosely
    at the neck under his collar."""
    E, K = C.ell, C.cone
    head = [p for p in bp if p.label == "skin" and p.bones and p.bones[0] == "head" and p.kind == "ell" and p.r[0] > 0.05]
    P = inflate(head, 0.013, None, "sack")
    P += [
        E((0, 0.004, 0.88), (0.088, 0.1, 0.075), "sack", ["head"], k=0.03),
        E((0, -0.074, 0.795), (0.062, 0.05, 0.075), "sack", ["head"], k=0.03),  # hangs off the nose and chin
        K((0, 0.01, 0.76), (0, 0.02, 0.645), 0.072, 0.085, "sack", ["neck", "head"], k=0.04),
        E((0, 0.02, 0.64), (0.092, 0.086, 0.028), "sack", ["neck", "chest"], k=0.03),  # bunched hem
        C.box((0, 0, 0.0), (1, 1, 0.618), 0.0, "cut", [], sub=True, k=0.01),
    ]
    for s in (1, -1):
        P.append(E((0.03 * s, -0.095, 0.846), (0.0115, 0.04, 0.0075), "cut", [], sub=True, k=0.003))
    return P


def sack_color(prims):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        c = np.tile(np.array((0.62, 0.58, 0.49)), (len(P), 1))
        weave = (np.sin(x * 2400) * np.sin(z * 2400) > 0.3) * 1.0
        c *= (0.95 - 0.06 * weave)[:, None]
        c *= (0.86 + 0.22 * C.fbm(P, 35.0, 3, seed=23))[:, None]
        # the miller's stencil, faded, on his left cheek; a top seam; grime round the eyes
        stamp = (np.abs(z - 0.81) < 0.022) & (np.abs(y - 0.015) < 0.035) & (x > 0.06)
        ring = stamp & ((np.abs(z - 0.81) > 0.016) | (np.abs(y - 0.015) > 0.028))
        c = _mix(c, stamp * 0.25 + ring * 0.35, (0.36, 0.42, 0.55))
        seam = np.abs(x) < 0.004
        c = _mix(c, (seam & (z > 0.9)) * 0.5, (0.55, 0.50, 0.42))
        eyes = np.exp(-(((np.abs(x) - 0.031) / 0.02) ** 2 + ((z - 0.846) / 0.016) ** 2)) * (y < -0.05)
        c = _mix(c, eyes * 0.15, (0.45, 0.40, 0.33))
        ao = C.sdf_ao(solid, P, N, steps=3, dist=0.015)
        return c * (0.55 + 0.45 * ao)[:, None]

    return fn


def jacket_prims(bp):
    """Waist-length coat, buttoned: a canvas work coat or a shell jacket."""
    torso = inflate(bp, 0.019, ["shirt"], "coat")
    P = torso + [
        C.ell((0, 0.03, 0.625), (0.08, 0.072, 0.03), "collar", ["chest", "neck"], k=0.015),
        C.box((0, 0, -1.0), (1, 1, 1.205), 0.0, "cut", [], sub=True, k=0.015),  # hem at the waist, above the gunbelt
    ]
    for s in (1, -1):
        P.append(C.ell(J(s)["hnd"], (0.07, 0.10, 0.07), "cut", [], sub=True, k=0.01))
    return P


def jacket_pattern(P, N, c):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    front = y < -0.04
    k = np.round((z - 0.22) / 0.06)
    btn = front & (np.hypot(x - 0.012, z - (0.22 + k * 0.06)) < 0.0065) & (k >= 0) & (k <= 6)
    c = _mix(c, btn * 1.0, (0.85, 0.80, 0.62))
    edge = front & (np.abs(x + 0.004) < 0.003) & (z > 0.12)
    c = _mix(c, edge * 0.6, (0.25, 0.22, 0.18))
    flap = front & (np.abs(z - 0.25) < 0.004) & (np.abs(ax - 0.1) < 0.04)
    c = _mix(c, flap * 0.6, (0.25, 0.22, 0.18))
    cuff = np.clip(1 - np.abs(np.linalg.norm(P - np.array([0, -0.22, 0.29]), axis=1) - 0.15) / 0.02, 0, 1) * 0
    return c + cuff[:, None]


def gauntlet_prims():
    P = []
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        fw = j["wri"] - j["elb"]
        P += [
            C.cone(j["wri"] - fw * 0.4, j["wri"] - fw * 0.02, 0.078, 0.05, "glove", ["forearm" + sfx], k=0.01),
            C.ell(j["wri"] + (j["hnd"] - j["wri"]) * 0.5, (0.04, 0.056, 0.047), "glove", ["hand" + sfx], k=0.015),
        ]
        P.append(C.cone(j["wri"] - fw * 0.5, j["wri"] - fw * 0.38, 0.054, 0.054, "cut", [], sub=True, k=0.004))
    return P


def buffalo_base(bp):
    """Knee-length buffalo-robe coat: bulky, fur collar over the shoulders."""
    torso = inflate(bp, 0.05, ["shirt"], "fur")
    E, K = C.ell, C.cone
    P = torso + [
        E((0, 0.035, 0.15), (0.225, 0.17, 0.12), "fur", ["hips"], k=0.06),
        E((0, 0.04, 0.6), (0.2, 0.15, 0.07), "collar", ["chest"], k=0.05),
        C.box((0, 0.22, -0.03), (0.21, 0.02, 0.17), 0.012, "fur", ["hips", "coat.B"], k=0.05, rot=_rotx(-38)),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P.append(K(j["hip"] + np.array([0.02 * s, 0.02, 0.03]), j["kne"] + np.array([0.0, 0.08, 0.02]), 0.14, 0.1, "fur",
                   ["thigh" + sfx, "hips"], k=0.05))
    return P


def buffalo_prims(base):
    shell = [p for p in base if not p.sub]

    def shag(p):
        return C.eval_sdf(shell, p) - 0.012 * (C.fbm(p * np.array([1, 1, 0.45]), 38.0, 2, seed=24) - 0.5)

    los, his = zip(*[p.bbox(0.02) for p in shell])
    P = [C.fnprim(shag, np.min(los, axis=0), np.max(his, axis=0), "fur", ["chest"], k=0.0)]
    P += [C.box((0, 0, -1.0), (1, 1, 0.58), 0.0, "cut", [], sub=True, k=0.02)]
    for s in (1, -1):
        P.append(C.ell(J(s)["hnd"], (0.07, 0.10, 0.07), "cut", [], sub=True, k=0.01))
    return P


def buffalo_color(prims):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        clump = C.fbm(P * np.array([1, 1, 0.4]), 70.0, 3, seed=25)
        c = np.tile(np.array((0.20, 0.13, 0.08)), (len(P), 1)) * (0.6 + 0.8 * clump)[:, None]
        tips = np.clip((clump - 0.62) / 0.2, 0, 1)
        c = _mix(c, tips * 0.6, (0.44, 0.32, 0.20))
        collar = np.clip((P[:, 2] - 0.55) / 0.05, 0, 1) * (np.abs(P[:, 0]) < 0.24)
        c = _mix(c, collar * 0.35, (0.12, 0.08, 0.05))
        ao = C.sdf_ao(solid, P, N, steps=3, dist=0.04)
        return c * (0.55 + 0.45 * ao)[:, None]

    return fn


def beard_prims():
    """Long, full beard and moustache for the mountain man (fits Body's face)."""
    E, K = C.ell, C.cone
    return [
        E((0, -0.07, 0.755), (0.06, 0.034, 0.045), "beard", ["head"], k=0.02),
        E((0, -0.085, 0.70), (0.055, 0.03, 0.05), "beard", ["head", "neck"], k=0.025),
        K((0, -0.09, 0.68), (0, -0.115, 0.585), 0.045, 0.022, "beard", ["neck", "chest"], k=0.025, scale=(1.1, 0.7, 1)),
        E((0.06, -0.035, 0.79), (0.02, 0.04, 0.05), "beard", ["head"], k=0.02),
        E((-0.06, -0.035, 0.79), (0.02, 0.04, 0.05), "beard", ["head"], k=0.02),
        E((0, -0.096, 0.781), (0.034, 0.014, 0.011), "beard", ["head"], k=0.012),  # moustache
    ]


def hair_color(base, streak_seed=26):
    def fn(P, N, ex):
        strands = C.fbm(P * np.array([1.0, 1.0, 0.15]), 380.0, 2, seed=streak_seed)
        c = np.tile(np.array(base), (len(P), 1)) * (0.6 + 0.6 * strands)[:, None]
        return c

    return fn


def vaquero_moustache_prims():
    E, K = C.ell, C.cone
    P = [E((0, -0.094, 0.781), (0.022, 0.011, 0.008), "m", ["head"], k=0.008)]
    for s in (1, -1):
        P.append(K((0.016 * s, -0.093, 0.779), (0.03 * s, -0.083, 0.754), 0.009, 0.004, "m", ["head"], k=0.008))
    return P


def make_hat_sugarloaf():
    prof = [(0.001, -0.004), (0.10, -0.004), (0.18, -0.002), (0.235, 0.004), (0.242, 0.012), (0.18, 0.010), (0.104, 0.014),
            (0.099, 0.07), (0.088, 0.13), (0.068, 0.18), (0.042, 0.207), (0.015, 0.214)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.13)
        return 0.0, 0.0, 0.018 * (math.cos(th) ** 2) * brim ** 2 - 0.01 * max(0.0, -math.sin(th)) * brim

    ob = C.lathe("Hat_Sugarloaf", prof, segments=22, scale_xy=(0.95, 1.08), squash=sq)
    ob.location = HAT_C
    return ob


def make_hat_sombrero():
    prof = [(0.001, -0.004), (0.10, -0.004), (0.20, 0.0), (0.29, 0.022), (0.335, 0.052), (0.345, 0.068), (0.33, 0.06),
            (0.28, 0.032), (0.2, 0.012), (0.104, 0.016), (0.1, 0.08), (0.086, 0.15), (0.062, 0.198), (0.03, 0.214), (0.01, 0.217)]

    def sq(th, r, z):
        return 0.0, 0.0, -0.012 * max(0.0, -math.sin(th)) * max(0.0, (r - 0.11) / 0.23)

    ob = C.lathe("Hat_Sombrero", prof, segments=22, scale_xy=(1.0, 1.04), squash=sq)
    ob.location = HAT_C + Vector((0, 0, 0.004))
    return ob


def make_hat_slouch():
    prof = [(0.001, -0.004), (0.10, -0.004), (0.16, -0.003), (0.21, 0.0), (0.218, 0.008), (0.21, 0.012), (0.16, 0.010),
            (0.104, 0.014), (0.103, 0.06), (0.098, 0.1), (0.08, 0.125), (0.04, 0.132)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.11)
        # a hat that has been slept in: brim sags unevenly, crown pushed in
        sag = -0.035 * brim ** 1.5 * (0.55 + 0.45 * math.sin(2.0 * th + 0.7)) - 0.012 * brim * math.sin(th + 2.4)
        dent = -0.022 * (1 - min(1.0, r / 0.08)) if z > 0.09 else 0.0
        push = 0.01 * math.sin(3 * th + 1.0) * (z / 0.13) if z > 0.02 and r > 0.05 else 0.0
        return push * math.cos(th), push * math.sin(th), sag + dent

    ob = C.lathe("Hat_Slouch", prof, segments=22, scale_xy=(0.95, 1.08), squash=sq)
    ob.location = HAT_C
    return ob


def felt_hat_color(base, band, band_z=(0.895, 0.912), extra=None):
    def fn(P, N, ex):
        r = np.hypot(P[:, 0], P[:, 1] - 0.005)
        z = P[:, 2]
        c = np.tile(np.array(base), (len(P), 1)) * (0.84 + 0.3 * C.fbm(P, 40, 3, seed=27))[:, None]
        crown = r < 0.112
        b = crown * np.clip((z - band_z[0]) / 0.003, 0, 1) * np.clip((band_z[1] - z) / 0.003, 0, 1)
        c = _mix(c, b, band)
        c[(N[:, 2] < -0.5) & ~crown] *= 0.8
        if extra:
            c = extra(P, N, c, b)
        return c

    return fn


def sombrero_trim(P, N, c, band):
    # braided band and a stitched rim
    th = np.arctan2(P[:, 1], P[:, 0])
    braid = band * (np.sin(th * 40 + P[:, 2] * 300) > 0)
    c = _mix(c, braid * 0.7, (0.75, 0.68, 0.50))
    r = np.hypot(P[:, 0], P[:, 1])
    rim = np.clip((r - 0.32) / 0.01, 0, 1)
    return _mix(c, rim * 0.6, (0.30, 0.20, 0.12))


def man_body_prims():
    """Body_Man: the guard's body, shared by the male outlaws.  A real face (brow,
    cheekbones, nose, jaw, chin, lips, ears) and neck; trousers tucked into
    boots with a shaped shaft and a stacked heel.  Labels follow Body's, so the
    inflate-based clothes (bandana, serape, jacket, coats) fit it too."""
    E, K = C.ell, C.cone
    P = [
        E((0, 0.0, 0.838), (0.077, 0.094, 0.104), "skin", ["head"], k=0.02),
        E((0, -0.03, 0.77), (0.06, 0.066, 0.05), "skin", ["head"], k=0.04),  # jaw
        E((0, -0.077, 0.737), (0.024, 0.018, 0.02), "skin", ["head"], k=0.022),  # chin
        E((0, -0.077, 0.866), (0.06, 0.02, 0.015), "skin", ["head"], k=0.02),  # brow ridge
        K((0, -0.088, 0.857), (0, -0.104, 0.812), 0.0095, 0.0135, "skin", ["head"], k=0.012),  # nose
        E((0, -0.106, 0.808), (0.015, 0.013, 0.013), "skin", ["head"], k=0.01),
        E((0, -0.083, 0.773), (0.02, 0.009, 0.006), "lips", ["head"], k=0.006),
        E((0, 0.016, 0.864), (0.082, 0.094, 0.084), "hair", ["head"], k=0.015),
        K((0, 0.022, 0.60), (0, 0.004, 0.77), 0.058, 0.052, "skin", ["neck", "head"], k=0.03),  # neck
        E((0, -0.044, 0.695), (0.012, 0.012, 0.016), "skin", ["neck"], k=0.012),  # Adam's apple
        # torso (vest + shirt painted), trousers, cartridge belt and holster
        E((0, 0.035, 0.49), (0.165, 0.115, 0.14), "shirt", ["chest"], k=0.06),
        E((0, 0.03, 0.32), (0.14, 0.096, 0.12), "shirt", ["spine", "chest"], k=0.06),
        E((0, 0.035, 0.145), (0.163, 0.12, 0.10), "pants", ["hips"], k=0.06),
        E((0, 0.085, 0.06), (0.142, 0.095, 0.072), "pants", ["hips"], k=0.05),  # seat
        C.fnprim(lambda p: _torus(p, (0, 0.035, 0.168), 0.17, 0.124, 0.017, 0.027), (-0.2, -0.12, 0.12), (0.2, 0.19, 0.21),
                 "belt", ["hips"], k=0.01),
        K((-0.188, 0.0, 0.16), (-0.236, -0.07, 0.02), 0.029, 0.025, "holster", ["hips", "thigh.R"], k=0.01),
        E((-0.188, 0.03, 0.19), (0.017, 0.034, 0.029), "gun", ["hips"], k=0.005),
    ]
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        shin = j["ank"] - j["kne"]
        P += [
            K((0.07 * s, 0.035, 0.56), j["arm"], 0.066, 0.058, "shirt", ["shoulder" + sfx, "chest"], k=0.05),
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), j["elb"], 0.056, 0.045, "shirt", ["upperarm" + sfx, "shoulder" + sfx], k=0.03),
            # small blend radii: in the bind pose the forearms lie close to the belly
            K(j["elb"], j["wri"], 0.045, 0.035, "shirt", ["forearm" + sfx], k=0.006),
            E(j["wri"] + (j["hnd"] - j["wri"]) * 0.5, (0.033, 0.05, 0.04), "hand", ["hand" + sfx], k=0.008),
            K(j["hip"] + np.array([0.0, 0.0, -0.01]), j["kne"], 0.088, 0.058, "pants", ["thigh" + sfx, "hips"], k=0.05),
            E(j["kne"] + np.array([0, -0.01, 0]), (0.054, 0.056, 0.054), "pants", ["thigh" + sfx, "shin" + sfx], k=0.03),
            # boot shaft (flared top, calf, ankle), foot with a sole, stacked heel
            K(j["kne"] + shin * 0.16, j["kne"] + shin * 0.55, 0.06, 0.054, "boot", ["shin" + sfx], k=0.02),
            K(j["kne"] + shin * 0.55, j["ank"], 0.054, 0.044, "boot", ["shin" + sfx], k=0.02),
            K(j["ank"] + np.array([0, 0.022, -0.03]), j["toe"], 0.046, 0.032, "boot", ["foot" + sfx], k=0.02),
            C.box(j["ank"] + np.array([0, 0.035, -0.066]), (0.026, 0.028, 0.02), 0.006, "heel", ["foot" + sfx], k=0.006),
            E((0.03 * s, -0.08, 0.843), (0.011, 0.007, 0.007), "eye", ["head"], k=0.004),
            E((0.045 * s, -0.066, 0.82), (0.025, 0.022, 0.02), "skin", ["head"], k=0.025),  # cheekbone
            E((0.05 * s, -0.022, 0.762), (0.022, 0.03, 0.028), "skin", ["head"], k=0.03),  # jaw angle
            E((0.013 * s, -0.094, 0.804), (0.01, 0.009, 0.009), "skin", ["head"], k=0.008),  # nostril wing
            E((0.08 * s, 0.006, 0.82), (0.014, 0.024, 0.032), "skin", ["head"], k=0.01),  # ear
        ]
    # keep the elbows off the waist: fused, the forearm and belly become one UV
    # island (projected on top of each other) and one skin (tearing when he stands)
    for s in (1, -1):
        P.append(E((0.161 * s, 0.03, 0.33), (0.006, 0.08, 0.11), "cut", [], sub=True, k=0.003))
    return P


def forearm_override(prims):
    """compute_weights override: in the bind pose the forearms lie a few cm off
    the belly, so belly verts pick up forearm/hand weight and tear off with the
    arm.  Only verts on the forearm/hand surface keep it."""
    arm = [p for p in prims if not p.sub and p.bones and p.bones[0].split(".")[0] in ("forearm", "hand")]

    def fn(P, W, names):
        d = np.min([p.dist(P) for p in arm], axis=0)
        far = d > 0.012
        idx = [i for i, n in enumerate(names) if n.split(".")[0] in ("forearm", "hand")]
        W = W.copy()
        W[np.ix_(far, idx)] = 0.0
        W[far] += 1e-6
        return W

    return fn


def man_body_color(prims):
    labs = ["skin", "lips", "hair", "shirt", "hand", "pants", "belt", "holster", "gun", "boot", "heel", "eye"]
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        cols = {
            "skin": (0.61, 0.43, 0.33), "lips": (0.50, 0.31, 0.27), "hair": (0.17, 0.12, 0.08),
            "shirt": (0.72, 0.69, 0.62), "hand": (0.58, 0.41, 0.31), "pants": (0.42, 0.38, 0.32),
            "belt": (0.33, 0.21, 0.12), "holster": (0.30, 0.18, 0.10), "gun": (0.35, 0.33, 0.30),
            "boot": (0.12, 0.085, 0.06), "heel": (0.07, 0.05, 0.04), "eye": (0.07, 0.05, 0.05),
        }
        c = sum(lw[k][:, None] * np.array(cols[k]) for k in labs)
        front = y < -0.03
        # dark wool vest over the shirt: V neck, six buttons, welt pockets, a back belt
        # skin weights decide what is sleeve: where the forearms fused with the
        # belly in the bind pose the surface belongs to whichever bone moves it
        on_torso = ex["arm"][:, 0] < 0.5 if "arm" in ex else np.ones(len(P), bool)
        cloth = np.clip(lw["shirt"] + lw["pants"] + lw["belt"], 0, 1)
        torso = cloth * on_torso * (ax < 0.17) * np.clip((z - 0.2) / 0.006, 0, 1) * (z < 0.6)
        opening = front & (ax < 0.014 + 0.06 * np.clip((z - 0.44) / 0.14, 0, 1)) & (z > 0.43)
        vest = torso * ~opening
        vc = np.array((0.13, 0.115, 0.10)) * (0.85 + 0.3 * C.fbm(P * np.array([1, 1, 3]), 120.0, 2, seed=31))[:, None]
        c = c * (1 - vest[:, None]) + vc * vest[:, None]
        k = np.round((z - 0.25) / 0.04)
        btn = front & (k >= 0) & (k <= 5) & (np.hypot(x, z - (0.25 + k * 0.04)) < 0.0055)
        c = _mix(c, btn * vest, (0.55, 0.48, 0.32))
        welt = front & (np.abs(z - 0.3) < 0.0025) & (np.abs(ax - 0.09) < 0.03)
        c = _mix(c, welt * vest * 0.8, (0.30, 0.27, 0.23))
        c = _mix(c, lw["skin"] * (z > 0.595) * (z < 0.632), cols["shirt"])  # shirt band collar
        # shirt folds, sleeve creases
        c *= (1 - 0.1 * lw["shirt"] * (1 - vest) * (C.fbm(P * np.array([1, 1, 0.4]), 45.0, 2, seed=32) > 0.6))[:, None]
        # cartridge loops, buckle
        buckle = lw["belt"] * (ax < 0.026) * (y < -0.05)
        c = _mix(c, buckle, (0.66, 0.56, 0.34))
        loops = lw["belt"] * (np.sin(np.arctan2(y - 0.035, x) * 64) > 0.2) * ~(ax < 0.04)
        c = _mix(c, loops * 0.7, (0.74, 0.60, 0.34))
        # face: weathered, tan line under the hat, brows, lids, stubble shadow
        face = lw["skin"] * (y < -0.035) * (z > 0.70)
        red = np.exp(-((ax / 0.02) ** 2 + ((y + 0.105) / 0.02) ** 2 + ((z - 0.809) / 0.018) ** 2))
        red += 0.6 * np.exp(-(((ax - 0.045) / 0.022) ** 2 + ((z - 0.81) / 0.02) ** 2)) * np.clip((-0.04 - y) / 0.03, 0, 1)
        c = _mix(c, face * np.clip(red, 0, 1) * 0.35, (0.66, 0.36, 0.28))
        brow_z = 0.869 - 0.003 * np.clip((ax - 0.03) / 0.03, -1, 1)
        brow = face * (np.abs(z - brow_z) < 0.0048 * (1 - 0.4 * np.clip((ax - 0.04) / 0.016, 0, 1))) * (ax > 0.008) * (ax < 0.056)
        c = _mix(c, brow * (0.6 + 0.4 * C.fbm(P, 500.0, 1, seed=40)), (0.14, 0.10, 0.07))
        slit = face * np.exp(-(((ax - 0.03) / 0.011) ** 2 + ((z - 0.8435) / 0.0035) ** 2))
        c = _mix(c, slit, (0.08, 0.06, 0.05))
        c = _mix(c, face * np.exp(-(((ax - 0.022) / 0.004) ** 2 + ((z - 0.8435) / 0.0025) ** 2)) * 0.5, (0.65, 0.6, 0.55))
        c *= (1 - 0.15 * face * np.exp(-(((ax - 0.03) / 0.015) ** 2 + ((z - 0.846) / 0.008) ** 2)))[:, None]
        # cheek hollows under the cheekbones, nasolabial folds
        hollow = face * np.exp(-(((ax - 0.047) / 0.016) ** 2 + ((z - 0.792) / 0.012) ** 2))
        c *= (1 - 0.13 * hollow)[:, None]
        t = np.clip((0.802 - z) / 0.03, 0, 1)
        fold = face * np.exp(-((ax - (0.017 + 0.016 * t)) / 0.0035) ** 2) * (z < 0.803) * (z > 0.77)
        c *= (1 - 0.16 * fold)[:, None]
        stub = face * np.clip((0.80 - z) / 0.02, 0, 1) * (1 - np.exp(-((ax / 0.02) ** 2 + ((z - 0.775) / 0.008) ** 2)))
        c = _mix(c, stub * 0.22, (0.25, 0.22, 0.22))
        c = _mix(c, face * np.exp(-((ax / 0.02) ** 2 + ((z - 0.773) / 0.005) ** 2)) * 0.5, cols["lips"])
        c *= (1 - 0.1 * face * (z > 0.885) * (np.sin(z * 2 * np.pi / 0.008 + 2 * x) > 0.8))[:, None]
        side = lw["skin"] * np.clip((ax - 0.062) / 0.008, 0, 1) * np.clip((y + 0.03) / 0.01, 0, 1) \
            * np.clip((0.012 - y) / 0.01, 0, 1) * np.clip((z - 0.80) / 0.01, 0, 1) * (z < 0.87)
        nape = lw["skin"] * np.clip((y - 0.03) / 0.015, 0, 1) * np.clip((z - 0.78) / 0.01, 0, 1) * (z < 0.87)
        hair = np.clip(lw["hair"] + side + nape, 0, 1)
        hc = np.array(cols["hair"]) * (0.8 + 0.4 * C.fbm(P * np.array([1, 1, 0.25]), 300.0, 2, seed=33))[:, None]
        c = c * (1 - hair[:, None]) + hc * hair[:, None]
        # trousers: wool wear, seat and knee shine; boots: stitched shaft tops, scuffs
        pants = lw["pants"]
        c *= (1 + pants * (0.16 * C.fbm(P * np.array([1, 1, 0.25]), 60.0, 2, seed=34) - 0.08))[:, None]
        boot = lw["boot"] + lw["heel"]
        scuff = boot * (C.fbm(P, 80.0, 2, seed=35) > 0.66)
        c = _mix(c, scuff * 0.35, (0.30, 0.22, 0.15))
        dust = np.clip((-0.42 - z) / 0.2, 0, 1) * boot
        c = _mix(c, dust * 0.4, (0.45, 0.38, 0.29))
        c *= (0.95 + 0.1 * C.fbm(P, 30.0, 2, seed=36))[:, None]
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.02)
        aw = 0.55 - 0.3 * face
        return c * (1 - aw + aw * ao)[:, None]

    return fn


def man_coat_prims(mp):
    """Coat_Guard: a linen duster fitted at the shoulders, hanging open; knee-length
    when he stands.  Same carving as the driver's coat (front opening near the
    body, then the lap), set-in sleeves added after so they survive."""
    E, K = C.ell, C.cone
    core = [p for p in mp if p.label == "shirt" and p.bones[0] in ("chest", "spine")] + \
        [p for p in mp if p.label == "pants" and p.bones == ["hips"]]
    P = inflate(core, 0.018, None, "coat")
    P += inflate([p for p in mp if p.label == "holster"], 0.02, None, "coat")
    P += [
        E((0, 0.04, 0.15), (0.188, 0.146, 0.11), "coat", ["hips"], k=0.06),
        E((0, 0.035, 0.172), (0.206, 0.158, 0.05), "coat", ["hips"], k=0.04),  # over the gunbelt
        E((0, 0.035, 0.625), (0.088, 0.08, 0.04), "collar", ["chest", "neck"], k=0.02),
        # the tail, laid along coat.B so it hangs straight when he stands
        C.box((0, 0.205, 0.0), (0.18, 0.016, 0.17), 0.012, "coat", ["coat.B"], k=0.05, rot=_rotx(31)),
    ]
    thighs = []
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        td = (j["kne"] - j["hip"]) / np.linalg.norm(j["kne"] - j["hip"])
        P.append(K(j["hip"] + np.array([0.02 * s, 0.02, 0.03]), j["kne"] + td * 0.05 + np.array([0.0, 0.04, 0.02]), 0.115, 0.085,
                   "coat", ["thigh" + sfx], k=0.05))
        thighs += [p for p in mp if p.kind == "cone" and p.bones == ["thigh" + sfx, "hips"]]
    inner = core + thighs

    def opening(p):
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        w = np.interp(z, [0.10, 0.17, 0.26, 0.42, 0.52, 0.60, 0.67], [0.0, 0.10, 0.12, 0.11, 0.08, 0.045, 0.03])
        strip = np.maximum(np.abs(x) - w, y + 0.01)
        d = C.eval_sdf(inner, p)
        return np.maximum(strip, np.maximum(-(d + 0.02), d - 0.07))

    def lap(p):
        out = np.full(len(p), 1.0)
        for s in (1, -1):
            j = {k: np.array(v) for k, v in J(s).items()}
            a, b = j["hip"], j["kne"]
            t = np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1.1)
            c = a + t[:, None] * (b - a)
            quarter = np.maximum(c[:, 2] - p[:, 2] - 0.005, (p[:, 0] - c[:, 0]) * s - 0.03)
            out = np.minimum(out, np.maximum(quarter, (p[:, 0] * s < -0.02) * 1.0))
        d = C.eval_sdf(inner, p)
        return np.maximum(np.maximum(out, p[:, 2] - 0.14), np.maximum(-(d + 0.02), d - 0.07))

    P.append(C.fnprim(opening, (-0.24, -0.42, -0.4), (0.24, 0.06, 0.74), "cut", [], sub=True, k=0.008))
    P.append(C.fnprim(lap, (-0.45, -0.5, -0.35), (0.45, 0.12, 0.2), "cut", [], sub=True, k=0.008))
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P += [
            K((0.07 * s, 0.035, 0.552), j["arm"] - np.array([0.01 * s, 0, 0.016]), 0.077, 0.07, "coat", ["shoulder" + sfx, "chest"], k=0.035),
            K(j["arm"] - np.array([0.03 * s, 0, 0.0]), j["elb"], 0.074, 0.062, "coat", ["upperarm" + sfx, "shoulder" + sfx], k=0.025),
            K(j["elb"], j["wri"], 0.062, 0.054, "coat", ["forearm" + sfx], k=0.02),
        ]
    P += [C.box((0, 0, -1.0), (1, 1, 0.58), 0.0, "cut", [], sub=True, k=0.02)]
    for s in (1, -1):
        P.append(C.ell(J(s)["hnd"], (0.07, 0.10, 0.07), "cut", [], sub=True, k=0.01))
    return P, inner


def linen_coat_color(prims, inner):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        weave = C.fbm(P * np.array([1, 1, 0.3]), 90.0, 2, seed=37)
        c = np.tile(np.array((0.63, 0.59, 0.49)), (len(P), 1)) * (0.88 + 0.22 * weave)[:, None]
        lw = C.label_weights(prims, P, ["coat", "collar"], tau=0.006)
        c = _mix(c, lw["collar"] * 0.5, (0.60, 0.56, 0.47))
        d = C.eval_sdf(inner, P)
        c = _mix(c, (d < 0.014) * (y < 0) * (z > 0.15) * 1.0, (0.55, 0.50, 0.40))  # the turned-back edge
        # set-in sleeve seams round the shoulder, a centre-back seam, hip pocket flaps
        sh = np.minimum(np.linalg.norm(P - np.array([0.185, 0.035, 0.56]), axis=1),
                        np.linalg.norm(P - np.array([-0.185, 0.035, 0.56]), axis=1))
        c = _mix(c, (np.abs(sh - 0.075) < 0.003) * 0.5, (0.45, 0.41, 0.33))
        c = _mix(c, ((ax < 0.003) & (y > 0.08) & (z > -0.1)) * 0.4, (0.45, 0.41, 0.33))
        flap = (np.abs(z - 0.17) < 0.004) & (np.abs(ax - 0.15) < 0.045) & (y < 0)
        c = _mix(c, flap * 0.6, (0.42, 0.38, 0.30))
        # creases at the elbows and the small of the back, road dust low down
        crease = C.fbm(P * np.array([1, 1, 2.5]), 30.0, 2, seed=38)
        c *= (1 - 0.12 * np.clip((crease - 0.55) / 0.2, 0, 1))[:, None]
        dust = np.clip((0.1 - z) / 0.45, 0, 1) * (0.6 + 0.4 * C.fbm(P, 12.0, 2, seed=39))
        c = _mix(c, dust * 0.3, (0.55, 0.47, 0.36))
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.03)
        return c * (0.72 + 0.28 * ao)[:, None]  # light: the arms move off the sides

    return fn


def make_hat_guard():
    """Dark felt, firm flat brim, tall crown with a sharp centre crease and front pinch."""
    prof = [(0.001, -0.004), (0.10, -0.004), (0.16, -0.003), (0.205, 0.0), (0.212, 0.006), (0.208, 0.011), (0.16, 0.009),
            (0.106, 0.013), (0.106, 0.05), (0.102, 0.095), (0.093, 0.128), (0.07, 0.145), (0.035, 0.152), (0.01, 0.153)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.1)
        curl = 0.014 * (math.cos(th) ** 2) * brim ** 2
        crease = 0.0
        if z > 0.08:
            k = min(1.0, (z - 0.08) / 0.05)
            crease = -0.038 * math.exp(-((r * math.cos(th)) / 0.024) ** 2) * k * (0.6 + 0.4 * max(0.0, -math.sin(th)))
        pinch = -0.016 * max(0.0, -math.sin(th)) ** 2 * max(0.0, (z - 0.03) / 0.12) if z > 0.03 else 0.0
        return pinch * math.cos(th) * 1.0, 0.0, curl + crease

    ob = C.lathe("Hat_Guard", prof, segments=24, scale_xy=(0.95, 1.08), squash=sq)
    ob.location = HAT_C
    return ob


def guard_moustache_prims():
    E, K = C.ell, C.cone
    P = [E((0, -0.096, 0.787), (0.024, 0.012, 0.009), "m", ["head"], k=0.01)]
    for s in (1, -1):
        P += [E((0.02 * s, -0.093, 0.783), (0.018, 0.011, 0.01), "m", ["head"], k=0.01),
              K((0.028 * s, -0.09, 0.781), (0.038 * s, -0.082, 0.768), 0.008, 0.004, "m", ["head"], k=0.008)]
    return P


def build_guard(mp):
    cp, inner = man_coat_prims(mp)
    coat = build_mesh("Coat_Guard", cp, 0.0075, 1700, linen_coat_color(cp, inner), 256, rough=0.9, uv_angle=80, arm_split=cp)
    hat = make_hat_guard()
    finish_lathe(hat)
    C.smart_uv(hat)
    img = C.bake_texture(hat, 128, felt_hat_color((0.13, 0.11, 0.10), (0.05, 0.04, 0.035)), "Hat_Guard_tex")
    C.assign_material(hat, C.image_material("Hat_Guard_mat", img, roughness=0.85))
    gm = guard_moustache_prims()
    mous = build_mesh("Moustache_Guard", gm, 0.0025, 260, hair_color((0.20, 0.14, 0.09), 29), 64, rough=0.95)
    return {"Coat_Guard": (coat, cp), "Hat_Guard": (hat, None), "Moustache_Guard": (mous, gm)}


def on_arm(ob, prims):
    """1 for verts nearer the arm primitives than anything else (for split UVs)."""
    P = C.verts_np(ob)
    armp = [p for p in prims if not p.sub and p.bones and p.bones[0].split(".")[0] in ("upperarm", "forearm", "hand")]
    rest = [p for p in prims if not p.sub and p not in armp]
    return (np.min([p.dist(P) for p in armp], axis=0) < np.min([p.dist(P) for p in rest], axis=0)).astype(float)


def build_outlaws():
    """Body_Man (+ guard pieces) and the gang's pieces.  Returns name -> (object,
    prims used for skinning or None for rigid head pieces)."""
    out = {}
    mp = man_body_prims()
    body = sdf_mesh_detail("Body_Man", mp, 0.0045, 4300, lambda P: (P[:, 2] > 0.715) & (P[:, 1] < 0.02), 19000)
    segs = {bn[0]: (np.array(bn[1], float), np.array(bn[2], float)) for bn in bone_list()}
    W, names = C.compute_weights(body, mp, segs, tau=0.012, smooth_iters=3, overrides=forearm_override(mp))
    armw = W[:, [i for i, n in enumerate(names) if n.split(".")[0] in ("shoulder", "upperarm", "forearm", "hand")]].sum(1)
    driver_face_uv(body, k=2.1, margin=0.012, arm_w=on_arm(body, mp))
    img = C.bake_texture(body, 512, man_body_color(mp), "Body_Man_tex", extra_vertex_attrs={"arm": armw[:, None]})
    C.assign_material(body, C.image_material("Body_Man_mat", img, roughness=0.85))
    out["Body_Man"] = (body, mp)
    out.update(build_guard(mp))
    fp = female_body_prims()
    fb = sdf_mesh_detail("Body_Female", fp, 0.0045, 3600, lambda P: (P[:, 2] > 0.715) & (P[:, 1] < 0.02), 15000)
    driver_face_uv(fb, k=2.1, margin=0.012, arm_w=on_arm(fb, fp))
    img = C.bake_texture(fb, 512, female_body_color(fp), "Body_Female_tex")
    C.assign_material(fb, C.image_material("Body_Female_mat", img, roughness=0.85))
    out["Body_Female"] = (fb, fp)
    sp = sack_prims(mp)
    out["Mask_Sack"] = (build_mesh("Mask_Sack", sp, 0.004, 700, sack_color(sp), 128), sp)
    bdp = bandana_prims(mp)
    out["Bandana_Man"] = (build_mesh("Bandana_Man", bdp, 0.005, 360, cloth_color(bdp, (0.50, 0.10, 0.07), bandana_pattern, 0.015), 128),
                          bdp)
    pp = poncho_prims(mp)
    out["Serape"] = (build_mesh("Serape", pp, 0.009, 900, cloth_color(pp, (0.55, 0.45, 0.30), serape_pattern), 128), pp)
    jp = jacket_prims(mp)
    out["Jacket"] = (build_mesh("Jacket", jp, 0.0075, 1400, cloth_color(jp, (0.56, 0.51, 0.42), jacket_pattern), 256, uv_angle=80,
                                 arm_split=jp), jp)
    gp = gauntlet_prims()
    out["Gauntlets"] = (build_mesh("Gauntlets", gp, 0.005, 360, cloth_color(gp, (0.17, 0.12, 0.085), gauntlet_pattern, 0.01), 64), gp)
    base = buffalo_base(mp)
    bfp = buffalo_prims(base)
    out["Coat_Buffalo"] = (build_mesh("Coat_Buffalo", bfp, 0.008, 1700, buffalo_color(bfp), 256, rough=0.98, uv_angle=80,
                                       arm_split=base), base)
    brp = beard_prims()
    out["Beard_Long"] = (build_mesh("Beard_Long", brp, 0.004, 600, hair_color((0.30, 0.22, 0.15)), 128, rough=0.95), brp)
    vmp = vaquero_moustache_prims()
    out["Moustache_Vaquero"] = (build_mesh("Moustache_Vaquero", vmp, 0.0025, 200, hair_color((0.12, 0.09, 0.07), 28), 64,
                                           rough=0.95), vmp)
    for mk, col in ((make_hat_sugarloaf, felt_hat_color((0.60, 0.54, 0.44), (0.16, 0.11, 0.08))),
                    (make_hat_sombrero, felt_hat_color((0.62, 0.50, 0.33), (0.30, 0.18, 0.10), (0.895, 0.925), sombrero_trim)),
                    (make_hat_slouch, felt_hat_color((0.40, 0.35, 0.29), (0.20, 0.16, 0.12)))):
        ob = mk()
        finish_lathe(ob)
        C.smart_uv(ob)
        img = C.bake_texture(ob, 128, col, ob.name + "_tex")
        C.assign_material(ob, C.image_material(ob.name + "_mat", img, roughness=0.9))
        out[ob.name] = (ob, None)
    return out


def serape_pattern(P, N, c):
    # saltillo-style serape: bands of red, indigo and cream with a stepped centre
    z = P[:, 2]
    band = np.sin(z * 90)
    c = np.where((band > 0.55)[:, None], np.array([0.50, 0.12, 0.08]), c)
    c = np.where((band < -0.7)[:, None], np.array([0.20, 0.22, 0.38]), c)
    c = np.where((np.abs(band) < 0.12)[:, None], np.array([0.74, 0.66, 0.52]), c)
    diamond = (np.abs(P[:, 0]) + np.abs(z - 0.47) * 0.8 < 0.06) & (P[:, 1] < 0)
    return np.where(diamond[:, None], np.array([0.62, 0.20, 0.10]), c)


def gauntlet_pattern(P, N, c):
    stitch = np.sin(np.arctan2(P[:, 2] - 0.29, P[:, 1] + 0.2) * 30) > 0.85
    return c * (1 - 0.15 * stitch)[:, None]


# ----------------------------------------------------------------------------
# townsfolk: the townswoman (1880s day dress, bustle, bonnet or small hat) and
# the lawman.  The skirt is modelled STANDING and mapped back into the seated
# bind pose by inverting its skinning, so it is a proper bell in Walk/Talk/
# StandIdle; its front and back follow the thighs and shins so a striding
# leg pushes the cloth instead of poking through it.
# ----------------------------------------------------------------------------
def woman_body_prims():
    """Pearl's head, face and hands (same primitives) on a body with no gunbelt."""
    return [p for p in female_body_prims() if p.label not in ("belt", "holster", "gun")]


def bodice_prims(wp):
    """Fitted bodice, long sleeves to the wrist, high collar."""
    core = [p for p in wp if p.label == "shirt" or p.label == "cuff"]
    P = inflate(core, 0.007, None, "bodice")
    for sfx, s in ((".L", 1), (".R", -1)):
        j = {k: np.array(v) for k, v in J(s).items()}
        P.append(C.cone(j["elb"], j["wri"] + (j["wri"] - j["elb"]) * 0.02, 0.043, 0.036, "bodice", ["forearm" + sfx], k=0.012))
    P += [
        C.ell((0, 0.02, 0.645), (0.056, 0.052, 0.04), "collar", ["neck", "chest"], k=0.01),
        C.ell((0, 0.03, 0.155), (0.178, 0.128, 0.085), "bodice", ["hips"], k=0.04),  # basque over the hips
        C.box((0, 0, -1.0), (1, 1, 1.09), 0.0, "cut", [], sub=True, k=0.01),          # skirt takes over below
    ]
    for s in (1, -1):
        P.append(C.ell(J(s)["hnd"] + np.array([0, 0.02, 0]), (0.045, 0.075, 0.05), "cut", [], sub=True, k=0.006))
    return P


def bodice_pattern(P, N, c):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    front = y < -0.03
    k = np.round((z - 0.25) / 0.035)
    btn = front & (np.hypot(x, z - (0.25 + k * 0.035)) < 0.004) & (k >= 0) & (k <= 10)
    c = _mix(c, btn * 1.0, (0.12, 0.10, 0.09))
    seam = front & (np.abs(np.abs(x) - 0.06) < 0.0025) & (z > 0.15) & (z < 0.5)  # princess seams
    c = _mix(c, seam * 0.5, (0.45, 0.43, 0.42))
    trim = np.clip((z - 0.655) / 0.01, 0, 1) * (z < 0.69)
    c = _mix(c, trim * 0.8, (0.92, 0.90, 0.85))  # white lace at the collar
    print_ = C.value_noise3(P, 260.0, 41) > 0.78
    return _mix(c, print_ * 0.35, (0.55, 0.52, 0.50))


def skirt_prims(z_top, yc):
    """Bustle-era skirt, standing space (feet at z 0): narrow front, bustle and
    a short train behind, draped overskirt."""
    E, K = C.ell, C.cone
    return [
        # walking-length: the hem clears the ground by the hips' drop in Walk/Run
        K((0, yc, z_top), (0, yc + 0.05, 0.10), 0.14, 0.32, "skirt", ["hips"], k=0.0, scale=(1.0, 0.92, 1.0)),
        E((0, yc + 0.07, 0.13), (0.32, 0.35, 0.04), "hem", ["hips"], k=0.05),
        E((0, yc + 0.15, z_top - 0.12), (0.15, 0.12, 0.12), "bustle", ["hips"], k=0.07),
        E((0, yc + 0.19, z_top - 0.30), (0.17, 0.12, 0.16), "bustle", ["hips"], k=0.08),
        E((0, yc - 0.07, z_top - 0.24), (0.18, 0.075, 0.09), "drape", ["hips"], k=0.06),
        C.box((0, 0, z_top + 1.0), (1, 1, 1.0), 0.0, "cut", [], sub=True, k=0.01),
    ]


def skirt_color(prims):
    solid = [p for p in prims if not p.sub]

    def fn(P, N, ex):
        z = P[:, 2]
        lw = C.label_weights(prims, P, ["skirt", "hem", "bustle", "drape"], tau=0.01)
        c = np.tile(np.array((0.80, 0.78, 0.74)), (len(P), 1))
        print_ = C.value_noise3(P, 230.0, 42) > 0.78
        c = _mix(c, print_ * 0.35, (0.55, 0.52, 0.50))
        pleat = np.sin(np.arctan2(P[:, 1], P[:, 0]) * 26) * np.clip((0.6 - z) / 0.5, 0, 1)
        c *= (0.93 + 0.07 * pleat)[:, None]
        c = _mix(c, np.clip((0.2 - z) / 0.02, 0, 1) * 0.7, (0.45, 0.43, 0.42))   # hem band
        c = _mix(c, lw["drape"] * 0.25, (0.62, 0.60, 0.58))
        c = _mix(c, np.clip((0.13 - z) / 0.05, 0, 1) * 0.35, (0.50, 0.42, 0.32))  # street dust
        ao = C.sdf_ao(solid, P, N, steps=3, dist=0.04)
        return c * (0.6 + 0.4 * ao)[:, None]

    return fn


def apron_prims(skirt):
    """Cotton apron over the skirt front: a thin shell offset from the skirt."""
    shell = [p for p in skirt if not p.sub]
    z_top = skirt[0].a[2]

    def fn(p):
        d = C.eval_sdf(shell, p)
        layer = np.abs(d - 0.009) - 0.0035
        region = np.maximum.reduce([np.abs(p[:, 0]) - 0.17 + 0.05 * np.clip((z_top - p[:, 2]) / 0.8, 0, 1) * 0,
                                    p[:, 1] + 0.02, p[:, 2] - (z_top - 0.01), 0.25 - p[:, 2]])
        return np.maximum(layer, region)

    return [C.fnprim(fn, (-0.3, -0.45, 0.2), (0.3, 0.05, z_top + 0.02), "apron", ["hips"], k=0.0)]


def make_bonnet():
    E, K = C.ell, C.cone
    P = [
        E((0, 0.022, 0.855), (0.092, 0.104, 0.1), "bonnet", ["head"], k=0.02),
        E((0, 0.075, 0.83), (0.06, 0.05, 0.06), "bonnet", ["head"], k=0.03),  # over the bun
        E((0, -0.035, 0.85), (0.104, 0.022, 0.118), "brim", ["head"], k=0.015),
        C.box((0, -0.25, 0.85), (0.3, 0.205, 0.3), 0.0, "cut", [], sub=True, k=0.006),      # open face
        E((0, -0.05, 0.83), (0.074, 0.06, 0.088), "cut", [], sub=True, k=0.008),
        C.box((0, 0, 0.6), (0.3, 0.3, 0.16), 0.0, "cut", [], sub=True, k=0.01),
    ]
    for s in (1, -1):  # ties, from under the brim down to the jaw
        P.append(K((0.074 * s, -0.02, 0.8), (0.058 * s, -0.04, 0.745), 0.007, 0.005, "ribbon", ["head"], k=0.005))
    return P


def bonnet_color(prims):
    def fn(P, N, ex):
        lw = C.label_weights(prims, P, ["bonnet", "brim", "ribbon"], tau=0.004)
        c = lw["bonnet"][:, None] * np.array((0.78, 0.76, 0.72)) + lw["brim"][:, None] * np.array((0.70, 0.68, 0.64)) + \
            lw["ribbon"][:, None] * np.array((0.30, 0.26, 0.30))
        quilt = (np.sin(P[:, 2] * 400) > 0.7) * lw["bonnet"]
        return c * (1 - 0.1 * quilt)[:, None] * (0.9 + 0.15 * C.fbm(P, 50.0, 2, seed=43))[:, None]

    return fn


def make_hat_lady():
    """Small 1880s hat perched forward on the hair: low crown, narrow brim, ribbon and a feather."""
    prof = [(0.001, -0.004), (0.07, -0.004), (0.11, 0.0), (0.118, 0.008), (0.11, 0.012), (0.075, 0.012), (0.074, 0.05),
            (0.068, 0.07), (0.04, 0.078), (0.01, 0.079)]

    def sq(th, r, z):
        return 0.0, 0.0, 0.01 * math.cos(th) ** 2 * max(0.0, (r - 0.075) / 0.04)

    ob = C.lathe("Hat_Lady", prof, segments=20, scale_xy=(1.0, 1.1), squash=sq)
    ob.rotation_euler = (math.radians(-14), 0, 0)
    ob.location = Vector((0, -0.005, 0.925))
    return ob


def lady_hat_color(P, N, ex):
    r = np.hypot(P[:, 0], P[:, 1])
    c = np.tile(np.array((0.62, 0.60, 0.58)), (len(P), 1))
    band = (r < 0.08) & (P[:, 2] > 0.93) & (P[:, 2] < 0.955)
    return _mix(c, band * 1.0, (0.30, 0.26, 0.30))


def woman_body_color(prims):
    labs = ["skin", "lips", "hair", "shirt", "cuff", "pants", "boot", "heel", "eye"]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        cols = {"skin": (0.68, 0.52, 0.42), "lips": (0.60, 0.35, 0.33), "hair": (0.28, 0.19, 0.12),
                "shirt": (0.5, 0.5, 0.5), "cuff": (0.5, 0.5, 0.5), "pants": (0.2, 0.2, 0.2),
                "boot": (0.08, 0.06, 0.05), "heel": (0.06, 0.05, 0.04), "eye": (0.07, 0.05, 0.05)}
        c = sum(lw[k][:, None] * np.array(cols[k]) for k in labs)
        face = lw["skin"] * (y < -0.035) * (z > 0.72)
        brow = face * (np.abs(z - 0.861) < 0.0035) * (ax > 0.01) * (ax < 0.048)
        c = _mix(c, brow * 0.8, cols["hair"])
        cheek = face * np.exp(-(((ax - 0.038) / 0.02) ** 2 + ((z - 0.808) / 0.016) ** 2))
        c = _mix(c, cheek * 0.3, (0.78, 0.45, 0.42))
        # hair parted in the middle and drawn back over the ears into the bun
        hair = np.clip(lw["hair"] + lw["skin"] * np.clip((y - 0.02) / 0.015, 0, 1) * (z > 0.79) * (z < 0.9)
                       + lw["skin"] * (ax > 0.062) * (y > -0.04) * (z > 0.83), 0, 1)
        part = (ax < 0.004) & (y < 0.02)
        hc = np.array(cols["hair"]) * (0.8 + 0.4 * C.fbm(P * np.array([1, 1, 0.3]), 280.0, 2, seed=44))[:, None]
        hc[part] *= 0.6
        c = c * (1 - hair[:, None]) + hc * hair[:, None]
        return c * (0.94 + 0.12 * C.fbm(P, 30.0, 2, seed=45))[:, None]

    return fn


def inverse_skin(P_stand, W, names, D, H, rig):
    """Bind-pose positions for verts given in a pose: invert linear blend skinning."""
    out = np.empty_like(P_stand)
    R = {b: np.array(D[b].to_matrix()) for b in names}
    hb = {b: np.array(rig.head[b]) for b in names}
    Hb = {b: np.array(H[b]) for b in names}
    for i, q in enumerate(P_stand):
        A = np.zeros((3, 3))
        c = np.zeros(3)
        for j, b in enumerate(names):
            w = W[i, j]
            if w > 0:
                A += w * R[b]
                c += w * (Hb[b] - R[b] @ hb[b])
        out[i] = np.linalg.solve(A, q - c)
    return out


def build_woman(A, segs):
    """Body_Woman, Dress (bodice + skirt, one mesh/material), Bonnet, Hat_Lady.
    Three visible meshes per woman."""
    rig = A.rig
    out = {}
    wp = woman_body_prims()
    bp = bodice_prims(wp)
    bod_solid = [p for p in bp if not p.sub or p.label == "cut"]
    legs = [p for p in wp if p.bones and p.bones[0].split(".")[0] in ("thigh", "shin")]
    ank = [np.array(J(s)["ank"]) for s in (1, -1)]

    def hidden(P):
        under = C.eval_sdf(bod_solid, P) < -0.004
        nearleg = np.min([p.dist(P) for p in legs], axis=0) < 0.02
        farank = np.min([np.linalg.norm(P - a, axis=1) for a in ank], axis=0) > 0.13
        return under | (nearleg & farank & (P[:, 2] < 0.12))

    body = sdf_mesh_detail("Body_Woman", wp, 0.0045, 1900, lambda P: (P[:, 2] > 0.715) & (P[:, 1] < 0.02), 22000, hidden=hidden)
    driver_face_uv(body, k=1.6, margin=0.01)
    img = C.bake_texture(body, 256, woman_body_color(wp), "Body_Woman_tex")
    C.assign_material(body, C.image_material("Body_Woman_mat", img, roughness=0.8))
    C.compute_weights(body, wp, segs, tau=0.012, smooth_iters=3, overrides=forearm_override(wp))
    out["Body_Woman"] = body

    # bodice, in the bind pose
    bod = C.build_sdf_mesh("Dress", bp, 0.0055, 1500)
    C.compute_weights(bod, bp, segs, tau=0.015, smooth_iters=3, overrides=forearm_override(bp))
    Qb, Nb = C.verts_np(bod), _vnormals(bod)
    # skirt, standing (StandIdle frame 0), then mapped back into the bind pose
    loc, w, rt = standidle_pose(A, 0.0)
    D, H = rig.solve(local=loc, world=w, root_t=rt)
    waist = rig.point(D, H, "spine", Vector((0, 0.025, 0.205)))
    z_hip = H["thigh.L"].z
    knee = {s: rig.point(D, H, "thigh" + s, rig.tail["thigh" + s]) for s in (".L", ".R")}
    sk = skirt_prims(waist.z, waist.y)
    names = list(segs.keys())
    bi = {n: i for i, n in enumerate(names)}
    skirt = C.build_sdf_mesh("Skirt", sk, 0.008, 1600)
    Qs, Ns = C.verts_np(skirt), _vnormals(skirt)
    W = np.zeros((len(Qs), len(names)))
    f = np.clip(np.abs(Qs[:, 1] - waist.y) / 0.12, 0, 1) * np.clip((z_hip - 0.05 - Qs[:, 2]) / 0.2, 0, 1) * 0.7
    sL = np.clip(0.5 + Qs[:, 0] / 0.12, 0, 1)
    kz = 0.5 * (knee[".L"].z + knee[".R"].z)
    ks = np.clip((kz + 0.05 - Qs[:, 2]) / 0.2, 0, 1)
    W[:, bi["hips"]] = 1 - f
    for sfx, sw in ((".L", sL), (".R", 1 - sL)):
        W[:, bi["thigh" + sfx]] = f * sw * (1 - 0.45 * ks)
        W[:, bi["shin" + sfx]] = f * sw * 0.45 * ks  # the hem only half follows the shin: it stays off the ground
    Pb = inverse_skin(Qs, W, names, D, H, rig)
    skirt.data.vertices.foreach_set("co", Pb.astype(np.float32).ravel())
    skirt.data.update()
    C.apply_weights(skirt, W, names)
    dress = C.join([bod, skirt], "Dress")
    nb = len(Qb)
    Q = np.concatenate([Qb, Qs])
    NQ = np.concatenate([Nb, Ns])
    flag = np.concatenate([np.zeros(nb), np.ones(len(Qs))])
    fv = np.empty(len(dress.data.polygons) * 3, dtype=np.int32)
    C.triangulate(dress)
    fv = np.empty(len(dress.data.polygons) * 3, dtype=np.int32)
    dress.data.polygons.foreach_get("vertices", fv)
    fv = fv.reshape(-1, 3)
    arm = on_arm(dress, bp) * (flag < 0.5)
    fa = arm[fv].mean(1) > 0.5
    fs = flag[fv].mean(1) > 0.5
    split_smart_uv(dress, [fa, fs, ~fa & ~fs], 0.008, angle=80)
    bfn, sfn = cloth_color(bp, (0.80, 0.78, 0.74), bodice_pattern, 0.02), skirt_color(sk)

    def dress_fn(P, N, ex):
        q, n, fl = ex["Q"], ex["NQ"], ex["flag"][:, 0]
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        c = np.zeros((len(P), 3))
        b = fl < 0.5
        if b.any():
            c[b] = bfn(q[b], n[b], {})
        if (~b).any():
            c[~b] = sfn(q[~b], n[~b], {})
        return c

    img = C.bake_texture(dress, 256, dress_fn, "Dress_tex", extra_vertex_attrs={"Q": Q, "NQ": NQ, "flag": flag[:, None]})
    # 'coat' in the name so a caller's tint varies the dress colour (prepMaterials)
    C.assign_material(dress, C.image_material("Dress_coat_mat", img, roughness=0.9))
    out["Dress"] = dress
    bn = make_bonnet()
    ob = build_mesh("Bonnet", bn, 0.0035, 700, bonnet_color(bn), 128)
    C.rigid_weights(ob, "head")
    out["Bonnet"] = ob
    hat = make_hat_lady()
    finish_lathe(hat)
    C.smart_uv(hat)
    img = C.bake_texture(hat, 64, lady_hat_color, "Hat_Lady_tex")
    C.assign_material(hat, C.image_material("Hat_Lady_mat", img, roughness=0.85))
    C.rigid_weights(hat, "head")
    out["Hat_Lady"] = hat
    return out


def _vnormals(ob):
    n = np.empty(len(ob.data.vertices) * 3, dtype=np.float32)
    ob.data.vertices.foreach_get("normal", n)
    return n.reshape(-1, 3).astype(np.float64)


def make_hat_lawman(mp):
    """Hat_Lawman: the marshal's pale grey hat, with his moustache and star in
    the same mesh (three draw calls a townsperson): hat + moustache on the head
    bone, the star on the chest."""
    prof = [(0.001, -0.004), (0.10, -0.004), (0.17, -0.002), (0.222, 0.003), (0.228, 0.01), (0.222, 0.014), (0.17, 0.011),
            (0.105, 0.014), (0.105, 0.06), (0.1, 0.11), (0.088, 0.14), (0.05, 0.152), (0.01, 0.153)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.12)
        crease = -0.03 * math.exp(-((r * math.cos(th)) / 0.026) ** 2) * min(1.0, max(0.0, (z - 0.09) / 0.05))
        return 0.0, 0.0, 0.03 * (math.cos(th) ** 2) * brim ** 2 + crease

    hat = C.lathe("Hat_Lawman", prof, segments=24, scale_xy=(0.95, 1.08), squash=sq)
    hat.location = HAT_C
    finish_lathe(hat)
    C.rigid_weights(hat, "head")
    E, K = C.ell, C.cone
    mprims = [E((0, -0.095, 0.786), (0.03, 0.013, 0.01), "m", ["head"], k=0.012)]
    for s in (1, -1):
        mprims.append(K((0.026 * s, -0.092, 0.782), (0.046 * s, -0.08, 0.758), 0.011, 0.005, "m", ["head"], k=0.01))
    mous = C.build_sdf_mesh("lm_mous", mprims, 0.0025, 280)
    C.rigid_weights(mous, "head")
    badge = make_badge()
    ob = C.join([hat, mous, badge], "Hat_Lawman")
    C.smart_uv(ob)

    def fn(P, N, ex):
        z, y = P[:, 2], P[:, 1]
        c = np.tile(np.array((0.62, 0.60, 0.56)), (len(P), 1)) * (0.86 + 0.26 * C.fbm(P, 40, 3, seed=46))[:, None]
        r = np.hypot(P[:, 0], P[:, 1] - 0.005)
        band = (r < 0.112) * np.clip((z - 0.893) / 0.003, 0, 1) * np.clip((0.915 - z) / 0.003, 0, 1)
        c = _mix(c, band, (0.12, 0.09, 0.07))
        must = (z < 0.81) & (z > 0.7)
        c[must] = np.array((0.16, 0.11, 0.08)) * (0.7 + 0.5 * C.fbm(P[must] * np.array([1, 1, 0.2]), 380.0, 2, seed=47))[:, None]
        star = z < 0.6
        c[star] = np.array((0.78, 0.77, 0.74))
        return c

    img = C.bake_texture(ob, 128, fn, "Hat_Lawman_tex")
    C.assign_material(ob, C.image_material("Hat_Lawman_mat", img, roughness=0.75))
    return ob


def make_badge():
    """Nickel five-point star on the lawman's vest (left breast), rigid to the chest."""
    import bmesh
    bm = bmesh.new()
    pts = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        r = 0.026 if i % 2 == 0 else 0.011
        pts.append((r * math.cos(a), r * math.sin(a)))
    top = [bm.verts.new((x, 0.0, y)) for x, y in pts]
    bot = [bm.verts.new((x, 0.004, y)) for x, y in pts]
    bm.faces.new(top[::-1])
    bm.faces.new(bot)
    for i in range(10):
        j = (i + 1) % 10
        bm.faces.new((top[i], top[j], bot[j], bot[i]))
    for i in range(5):  # ball tips
        x, y = pts[2 * i]
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.0035, matrix=Matrix.Translation((x * 1.05, -0.001, y * 1.05)))
    me = bpy.data.meshes.new("Badge_Star")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Badge_Star", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(-12), 0, 0)
    ob.location = (0.078, -0.115, 0.468)
    C.set_active(ob)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    C.triangulate(ob)
    C.rigid_weights(ob, "chest")
    return ob


# ----------------------------------------------------------------------------
# Wild Bill Hickok, c. 1869-76: shoulder-length wavy auburn-brown hair, long
# drooping moustache, aquiline nose; white shirt with a ribbon tie, an ivory
# brocade waistcoat, a black frock coat (Coat_Guard in black: the torso is
# Body_Man's so it fits), a low flat-crowned wide hat, grey trousers in tall
# boots, and two ivory-handled 1851 Navies butt-forward in a red silk sash.
# ----------------------------------------------------------------------------
def hickok_body_prims():
    E, K = C.ell, C.cone
    base = [p for p in man_body_prims() if not (p.label in ("belt", "holster", "gun", "hair", "lips") or
                                                (p.label == "skin" and p.bones and p.bones[0] == "head"))]
    P = [
        E((0, 0.0, 0.84), (0.074, 0.094, 0.106), "skin", ["head"], k=0.02),
        E((0, -0.03, 0.765), (0.054, 0.064, 0.054), "skin", ["head"], k=0.04),  # long lean jaw
        E((0, -0.074, 0.728), (0.022, 0.017, 0.02), "skin", ["head"], k=0.02),  # chin
        E((0, -0.077, 0.868), (0.058, 0.019, 0.014), "skin", ["head"], k=0.02),
        K((0, -0.087, 0.862), (0, -0.108, 0.808), 0.0095, 0.012, "skin", ["head"], k=0.01),  # long nose
        E((0, -0.099, 0.84), (0.008, 0.008, 0.012), "skin", ["head"], k=0.008),  # aquiline hump
        E((0, -0.108, 0.803), (0.013, 0.012, 0.012), "skin", ["head"], k=0.009),
        E((0, -0.082, 0.772), (0.019, 0.008, 0.006), "lips", ["head"], k=0.006),
        # long drooping moustache
        E((0, -0.097, 0.786), (0.027, 0.012, 0.009), "mous", ["head"], k=0.008),
        # hair: parted, swept back, falling in waves to the collar
        E((0, 0.016, 0.866), (0.08, 0.095, 0.086), "hair", ["head"], k=0.015),
        E((0, 0.062, 0.79), (0.085, 0.066, 0.085), "hair", ["head"], k=0.03),   # behind the ears only
        K((0, 0.075, 0.78), (0, 0.088, 0.665), 0.058, 0.066, "hair", ["head", "neck"], k=0.03),
        C.fnprim(lambda p: _torus(p, (0, 0.035, 0.18), 0.168, 0.124, 0.024, 0.034), (-0.2, -0.13, 0.13), (0.2, 0.19, 0.23),
                 "sash", ["hips"], k=0.012),
        E((0, -0.062, 0.632), (0.03, 0.012, 0.012), "tie", ["neck", "chest"], k=0.006),
    ]
    for s in (1, -1):
        P += [
            K((0.03 * s, -0.093, 0.782), (0.046 * s, -0.082, 0.738), 0.009, 0.0045, "mous", ["head"], k=0.008),
            K((0.07 * s, 0.03, 0.83), (0.092 * s, 0.05, 0.67), 0.026, 0.034, "hair", ["head", "neck"], k=0.025),
            E((0.03 * s, -0.08, 0.844), (0.011, 0.007, 0.007), "eye", ["head"], k=0.004),
            E((0.044 * s, -0.064, 0.824), (0.023, 0.02, 0.019), "skin", ["head"], k=0.022),  # high cheekbones
            E((0.078 * s, 0.006, 0.82), (0.013, 0.023, 0.031), "skin", ["head"], k=0.01),
            E((0.012 * s, -0.096, 0.802), (0.009, 0.008, 0.008), "skin", ["head"], k=0.007),
            E((-0.03 * s, -0.064, 0.618), (0.02, 0.008, 0.016), "tie", ["neck", "chest"], k=0.004),  # bow loops
        ]
    out = base + P
    # taller boots: start the shaft just under the knee
    for p in out:
        if p.label == "boot" and p.kind == "cone" and p.bones[0].startswith("shin") and abs(p.ra - 0.06) < 1e-6:
            p.a = p.a + (p.a - p.b) * 0.35
            p.ra = 0.062
    return out


def hickok_body_color(prims):
    labs = ["skin", "lips", "hair", "mous", "shirt", "hand", "pants", "sash", "tie", "boot", "heel", "eye"]

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, labs, tau=0.006)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        cols = {
            "skin": (0.66, 0.48, 0.38), "lips": (0.55, 0.33, 0.30), "hair": (0.36, 0.20, 0.11), "mous": (0.34, 0.20, 0.11),
            "shirt": (0.86, 0.85, 0.82), "hand": (0.64, 0.47, 0.37), "pants": (0.40, 0.40, 0.41), "sash": (0.62, 0.08, 0.07),
            "tie": (0.05, 0.05, 0.06), "boot": (0.06, 0.05, 0.05), "heel": (0.05, 0.04, 0.04), "eye": (0.10, 0.12, 0.14),
        }
        c = sum(lw[k][:, None] * np.array(cols[k]) for k in labs)
        front = y < -0.03
        # ivory brocade waistcoat with a gold-brown figure, over the white shirt
        on_torso = ex["arm"][:, 0] < 0.5 if "arm" in ex else np.ones(len(P), bool)
        cloth = np.clip(lw["shirt"] + lw["pants"], 0, 1)
        torso = cloth * on_torso * (ax < 0.17) * np.clip((z - 0.215) / 0.006, 0, 1) * (z < 0.6)
        opening = front & (ax < 0.012 + 0.07 * np.clip((z - 0.47) / 0.13, 0, 1)) & (z > 0.46)
        vest = torso * ~opening
        # brocade: a diamond trellis with a sprig in each lozenge
        uu = np.where(np.abs(N[:, 0]) > 0.75, y, x)
        g = 0.028
        da = np.abs(((uu + z) / g) % 1.0 - 0.5)
        db = np.abs(((uu - z) / g) % 1.0 - 0.5)
        trellis = np.clip((np.maximum(da, db) - 0.43) / 0.04, 0, 1)
        sprig = np.clip((0.16 - np.hypot(da, db)) / 0.05, 0, 1)
        motif = np.clip(trellis + sprig, 0, 1)
        vc = np.array((0.78, 0.70, 0.52)) * (1 - 0.45 * motif[:, None]) + np.array((0.36, 0.22, 0.10)) * 0.45 * motif[:, None]
        c = c * (1 - vest[:, None]) + vc * vest[:, None]
        k = np.round((z - 0.26) / 0.036)
        btn = front & (k >= 0) & (k <= 5) & (np.hypot(x, z - (0.26 + k * 0.036)) < 0.005)
        c = _mix(c, btn * vest, (0.62, 0.50, 0.26))
        c = _mix(c, lw["skin"] * (z > 0.595) * (z < 0.645), cols["shirt"])  # collar
        # silk sheen and folds on the sash; a faint check in the trousers
        c *= (1 + lw["sash"] * 0.25 * np.sin(np.arctan2(y, x) * 18 + z * 120))[:, None]
        chk = ((np.sin(x * 260) > 0.85) | (np.sin(z * 260) > 0.85)) * lw["pants"]
        c = _mix(c, chk * 0.25, (0.28, 0.28, 0.30))
        # face
        face = lw["skin"] * (y < -0.035) * (z > 0.70)
        brow = face * (np.abs(z - (0.868 - 0.004 * np.clip((ax - 0.03) / 0.025, -1, 1))) < 0.004) * (ax > 0.009) * (ax < 0.054)
        c = _mix(c, brow * 0.9, (0.30, 0.17, 0.09))
        slit = face * np.exp(-(((ax - 0.03) / 0.011) ** 2 + ((z - 0.8445) / 0.0033) ** 2))
        c = _mix(c, slit, (0.10, 0.10, 0.11))
        c = _mix(c, face * np.exp(-(((ax - 0.021) / 0.004) ** 2 + ((z - 0.8445) / 0.0024) ** 2)) * 0.55, (0.68, 0.64, 0.6))
        hollow = face * np.exp(-(((ax - 0.045) / 0.015) ** 2 + ((z - 0.795) / 0.013) ** 2))
        c *= (1 - 0.14 * hollow)[:, None]
        t = np.clip((0.80 - z) / 0.03, 0, 1)
        c *= (1 - 0.14 * face * np.exp(-((ax - (0.016 + 0.017 * t)) / 0.0035) ** 2) * (z < 0.801) * (z > 0.77))[:, None]
        # hair: waves catch the light; temples and sideburns
        hair = np.clip(lw["hair"] + lw["mous"] + lw["skin"] * np.clip((ax - 0.066) / 0.006, 0, 1) * (y > -0.01) * (z > 0.80)
                       + lw["skin"] * np.clip((y - 0.04) / 0.012, 0, 1) * (z > 0.74), 0, 1)
        wave = 0.5 + 0.5 * np.sin(z * 210 + 6 * C.fbm(P, 30.0, 2, seed=49))
        hc = np.array(cols["hair"]) * (0.75 + 0.25 * wave + 0.25 * C.fbm(P * np.array([1, 1, 0.2]), 300.0, 2, seed=50))[:, None]
        c = c * (1 - hair[:, None]) + hc * hair[:, None]
        c *= (0.95 + 0.1 * C.fbm(P, 30.0, 2, seed=51))[:, None]
        solid = [p for p in prims if not p.sub]
        ao = C.sdf_ao(solid, P, N, steps=4, dist=0.02)
        aw = 0.55 - 0.3 * face
        return c * (1 - aw + aw * ao)[:, None]

    return fn


def make_hat_hickok():
    """Wide brim, low flat crown."""
    prof = [(0.001, -0.004), (0.10, -0.004), (0.17, -0.002), (0.228, 0.003), (0.236, 0.01), (0.228, 0.014), (0.17, 0.011),
            (0.106, 0.014), (0.106, 0.06), (0.104, 0.092), (0.096, 0.101), (0.05, 0.104), (0.01, 0.104)]

    def sq(th, r, z):
        brim = max(0.0, (r - 0.11) / 0.12)
        return 0.0, 0.0, 0.012 * (math.cos(th) ** 2) * brim ** 2 - 0.012 * max(0.0, -math.sin(th)) * brim

    ob = C.lathe("Hat_Hickok", prof, segments=26, scale_xy=(0.95, 1.08), squash=sq)
    ob.location = HAT_C + Vector((0, 0.006, 0.006))
    return ob


def _navy(bm, M):
    """One 1851 Navy (simplified): octagonal barrel, cylinder, frame, brass guard,
    ivory grip.  Local: barrel along +Y from the cylinder, grip down/back at -Y.
    Returns {part: [faces]}."""
    import bmesh
    parts = {}

    def add(kind, geom):
        parts.setdefault(kind, []).extend([f for f in geom if isinstance(f, bmesh.types.BMFace)])

    def cyl(r, h, segs, mat):
        g = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h, matrix=M @ mat)
        return list({f for v in g["verts"] for f in v.link_faces})

    R = Matrix.Rotation(math.radians(-90), 4, "X")  # cone axis z -> +y
    add("steel", cyl(0.0085, 0.19, 8, Matrix.Translation((0, 0.12, 0.01)) @ R))   # barrel
    add("steel", cyl(0.006, 0.15, 6, Matrix.Translation((0, 0.105, -0.004)) @ R))  # loading lever
    add("steel", cyl(0.02, 0.05, 6, Matrix.Translation((0, 0.0, 0.0)) @ R))       # cylinder
    g = bmesh.ops.create_cube(bm, size=1.0, matrix=M @ Matrix.Translation((0, -0.035, 0.002)) @ Matrix.Diagonal((0.016, 0.03, 0.03, 1)))
    add("steel", list({f for v in g["verts"] for f in v.link_faces}))
    g = bmesh.ops.create_cube(bm, size=1.0, matrix=M @ Matrix.Translation((0, -0.03, -0.028)) @ Matrix.Diagonal((0.006, 0.03, 0.02, 1)))
    add("brass", list({f for v in g["verts"] for f in v.link_faces}))
    grip = Matrix.Translation((0, -0.07, -0.04)) @ Matrix.Rotation(math.radians(-30), 4, "X")
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.013, radius2=0.011, depth=0.09, matrix=M @ grip @ Matrix.Diagonal((0.85, 1.25, 1, 1)))
    add("ivory", list({f for v in g["verts"] for f in v.link_faces}))
    return parts


def make_colts_hickok():
    """Two Navies worn butt-forward in the sash (rigid to the hips)."""
    import bmesh
    bm = bmesh.new()
    allparts = {}
    for s in (1, -1):
        # butt forward and inward at the front of the sash, barrel back along the hip
        M = Matrix.Translation((0.095 * s, -0.135, 0.19)) @ Matrix.Rotation(math.radians(25 * s), 4, "Z") @ \
            Matrix.Rotation(math.radians(-22), 4, "X")
        for k, v in _navy(bm, M).items():
            allparts.setdefault(k, []).extend(v)
    bm.faces.ensure_lookup_table()
    kind = {}
    for k, fs in allparts.items():
        for f in fs:
            kind[f.index] = k
    me = bpy.data.meshes.new("Colts_Hickok")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Colts_Hickok", me)
    bpy.context.scene.collection.objects.link(ob)
    C.triangulate(ob)
    C.shade_smooth(ob)
    return ob


def colts_color(P, N, ex):
    # by position on the gun: ivory grips toward the front/bottom, brass guard, blued steel
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    c = np.tile(np.array((0.13, 0.14, 0.16)), (len(P), 1))
    grip = y < -0.16
    c[grip] = np.array((0.86, 0.82, 0.70))
    return c


def build_hickok(segs):
    hp = hickok_body_prims()
    body = sdf_mesh_detail("Body_Hickok", hp, 0.0045, 4400, lambda P: (P[:, 2] > 0.66) & (P[:, 1] < 0.12), 19000)
    W, names = C.compute_weights(body, hp, segs, tau=0.012, smooth_iters=3, overrides=forearm_override(hp))
    armw = W[:, [i for i, n in enumerate(names) if n.split(".")[0] in ("shoulder", "upperarm", "forearm", "hand")]].sum(1)
    driver_face_uv(body, k=2.0, margin=0.012, arm_w=on_arm(body, hp))
    img = C.bake_texture(body, 512, hickok_body_color(hp), "Body_Hickok_tex", extra_vertex_attrs={"arm": armw[:, None]})
    C.assign_material(body, C.image_material("Body_Hickok_mat", img, roughness=0.8))
    hat = make_hat_hickok()
    finish_lathe(hat)
    C.smart_uv(hat)
    img = C.bake_texture(hat, 128, felt_hat_color((0.21, 0.18, 0.16), (0.05, 0.045, 0.04), (0.893, 0.912)), "Hat_Hickok_tex")
    C.assign_material(hat, C.image_material("Hat_Hickok_mat", img, roughness=0.85))
    C.rigid_weights(hat, "head")
    colts = make_colts_hickok()
    C.smart_uv(colts)
    img = C.bake_texture(colts, 64, colts_color, "Colts_Hickok_tex")
    C.assign_material(colts, C.image_material("Colts_Hickok_mat", img, roughness=0.4, metallic=0.6))
    C.rigid_weights(colts, "hips")
    return [body, hat, colts]


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
    world["hand.R"] = hand_q(-1, direction)
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
        world["hand.R"] = hand_q(-1, (AIM_DIR + Vector((0, 0, 0.8 * k))).normalized())
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
        w["hand" + sfx] = hand_q(s, Vector((0.04 * s, -0.12, -1)), up=(0.2 * s, -1, 0))
    return w


def standidle_clip(A, n=180):
    return A.frames(n, lambda t, u: standidle_pose(A, u))


def standidle_pose(A, u):
    tau = 2 * math.pi
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
        w["hand.R"] = hand_q(-1, (d + Vector((0, 0, 0.7 * k))).normalized())
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


def _ik(A, T, L1, L2, pole):
    """Middle joint of a two-bone chain from A reaching T, bending toward pole."""
    d = T - A
    dist = min(max(d.length, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    u = d.normalized()
    a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(L1 * L1 - a * a, 0.0))
    p = Vector(pole)
    p = (p - u * p.dot(u)).normalized()
    return A + u * a + p * h


DRIVE_WRIST = (0.11, -0.37, 0.30)   # wrists ahead of the belly, lines gathered in front
DRIVE_ANKLE = (0.15, -0.42, -0.43)  # heels on the coach's footboard (0.54 m below the seat)


def drive_clip(A, n=60):
    """On the coach box: sat upright, feet braced on the footboard, both hands
    forward on the lines, rolling with the coach (1 s loop).  The coach hangs
    the six lines on hand.R, so the hands stay put while the body sways."""
    rig = A.rig
    tau = 2 * math.pi
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731

    def pose(t, u):
        sw = math.sin(tau * u)
        bob = math.sin(tau * u * 2)
        loc = {
            "root": E(0, 1.5 * sw, 0),
            "hips": E(-4 + 0.6 * bob),
            "spine": E(3 + 0.8 * math.sin(tau * (2 * u - 0.1))),
            "chest": E(2),
            "neck": E(-7),
            "head": E(-2 + 1.2 * math.sin(tau * (2 * u - 0.2)), 0, 4 * math.sin(tau * u)),
        }
        rt = (0, 0, 0.005 * bob)
        D, H = rig.solve(local=loc, root_t=rt)
        w = {"coat.B": aim_q(rig, "coat.B", Vector((0, 1, -0.2)))}
        for sfx, s in ((".L", 1), (".R", -1)):
            m = Vector((s, 1, 1))
            Tw = Vector(DRIVE_WRIST) * m + Vector((0, 0, 0.01 * bob))
            Aw = H["upperarm" + sfx]
            el = _ik(Aw, Tw, L("upperarm" + sfx), L("forearm" + sfx), Vector((0.9 * s, 0.4, -1)))
            w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, el - Aw)
            w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, Tw - el)
            w["hand" + sfx] = hand_q(s, Vector((-0.3 * s, -1, -0.15)), up=(0.5 * s, 0.2, 1))
            Ta = Vector(DRIVE_ANKLE) * m
            Ah = H["thigh" + sfx]
            kn = _ik(Ah, Ta, L("thigh" + sfx), L("shin" + sfx), Vector((0.25 * s, -1, 0.5)))
            w["thigh" + sfx] = aim_q(rig, "thigh" + sfx, kn - Ah)
            w["shin" + sfx] = aim_q(rig, "shin" + sfx, Ta - kn)
            w["foot" + sfx] = aim_q(rig, "foot" + sfx, Vector((0.08 * s, -1, -0.30)))
        return loc, w, rt
    return A.frames(n, pose)


SEAT_ANKLE = (0.2, -0.5, 0.035)  # boot heels on the roof, 5 cm under the seat contact


def seat_pose(A, u, kick=0.0):
    """The shotgun messenger on the roof: sat with knees up and heels braced,
    torso upright and still (the coach's own sway moves him), the gun shouldered
    along AIM_DIR with the left hand on the fore-end.  kick: recoil 0..1."""
    rig = A.rig
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731
    br = math.sin(2 * math.pi * u)  # one slow breath per loop
    turn = -22.0
    loc = {
        "hips": E(-4),
        "spine": E(3 + 0.5 * br, 0, turn * 0.4),
        "chest": E(2 + 0.6 * br - 4 * kick, 0, turn * 0.6),
        "neck": E(-2, 0, turn * 0.5),
        "head": E(4 - 3 * kick, 0, turn * 0.5),  # cheek down toward the stock
        "shoulder.R": E(0, 0, -6),
    }
    rt = (0, 0, 0.0015 * br)
    D, H = rig.solve(local=loc, root_t=rt)
    w = {"coat.B": aim_q(rig, "coat.B", Vector((0, 1, -0.1)))}
    d = (AIM_DIR + Vector((0, 0, 0.3 * kick))).normalized()
    # right hand (the grip) just ahead of the shoulder, left hand out on the fore-end
    sh = H["upperarm.R"]
    grip = sh + AIM_DIR * 0.26 + Vector((0.07, 0.0, 0.03)) - AIM_DIR * 0.05 * kick
    fore = grip + d * 0.30
    for sfx, s, tgt, pole in ((".R", -1, grip, Vector((-1, 0.3, -0.8))), (".L", 1, fore, Vector((0.5, 0.2, -1)))):
        Aw = H["upperarm" + sfx]
        palm_off = (Vector(palm(s)) - Vector(J(s)["wri"])).length
        wri = tgt - d * palm_off
        el = _ik(Aw, wri, L("upperarm" + sfx), L("forearm" + sfx), pole)
        w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, el - Aw)
        w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, wri - el)
    w["hand.R"] = hand_q(-1, (AIM_DIR + Vector((0, 0, 0.8 * kick))).normalized())
    w["hand.L"] = hand_q(1, d, up=(0.6, 0, -1))  # palm up under the fore-end
    for sfx, s in ((".L", 1), (".R", -1)):
        m = Vector((s, 1, 1))
        Ta = Vector(SEAT_ANKLE) * m
        Ah = H["thigh" + sfx]
        kn = _ik(Ah, Ta, L("thigh" + sfx), L("shin" + sfx), Vector((0.3 * s, -0.2, 1)))
        w["thigh" + sfx] = aim_q(rig, "thigh" + sfx, kn - Ah)
        w["shin" + sfx] = aim_q(rig, "shin" + sfx, Ta - kn)
        w["foot" + sfx] = aim_q(rig, "foot" + sfx, Vector((0.15 * s, -1, -0.15)))
    return loc, w, rt


def seataim_clip(A, n=180):
    return A.frames(n, lambda t, u: seat_pose(A, u))


SEAT_UPPER = UPPER + ["upperarm.L", "forearm.L", "hand.L"]


def seatshoot_clip(A, n=15):
    """SeatAim's recoil (0.25 s); frame 0 == SeatAim frame 0, so it is made
    additive the same way Shoot is."""
    def pose(t, u):
        k = (t / 0.04) if t < 0.04 else math.exp(-(t - 0.04) / 0.06)
        k = max(0.0, k) * (1 - C.smoothstep((t - 0.18) / 0.07))
        return seat_pose(A, 0.0, kick=k)
    return A.frames(n, pose, bones=SEAT_UPPER)


WALK_SPEED = 1.4          # m/s the code moves the root at (town.js WALK)
WALK_FRAMES = 64         # one gait cycle (two steps) = 64/60 s
WALK_STRIDE = WALK_SPEED * WALK_FRAMES / C.FPS   # 1.49 m per cycle, 0.75 m per step
RUN_SPEED = 3.6
RUN_FRAMES = 42          # 0.7 s cycle
RUN_STRIDE = RUN_SPEED * RUN_FRAMES / C.FPS      # 2.52 m per cycle


def _gait_foot(phi, speed, frames, stance, lift):
    """In-place foot path for gait phase phi: (y, lift, pitch).  Planted feet
    slide back at exactly `speed`, so a root moving at that speed never skates."""
    half = speed * stance * frames / C.FPS / 2
    phi %= 1.0
    if phi < stance:
        u = phi / stance
        return -half + 2 * half * u, 0.0, 6.0 * C.smoothstep((u - 0.75) / 0.25)  # heel peels up before toe-off
    u = (phi - stance) / (1 - stance)
    e = 0.5 - 0.5 * math.cos(math.pi * u)
    return half - 2 * half * e, lift * math.sin(math.pi * u) ** 1.3, 18.0 * (1 - u) - 14.0 * C.smoothstep((u - 0.7) / 0.3)


def gait_clip(A, speed, frames, stance, lift, lean, arm_swing, elbow, bob):
    rig = A.rig
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731
    leg = L("thigh.L") + L("shin.L")
    tau = 2 * math.pi
    n = frames
    # hips drop just enough for the planted foot to reach; in a run's flight
    # phase they ride up (smoothed round the loop)
    drops = []
    for fi in range(n):
        phi = fi / n
        d = None
        for off in (0.0, 0.5):
            y, lf, _ = _gait_foot(phi + off, speed, frames, stance, lift)
            if lf == 0.0:
                need = leg - math.sqrt(max((0.975 * leg) ** 2 - y * y, 0.0))
                d = need if d is None else max(d, need)
        drops.append(max(d, 0.02) if d is not None else 0.02 - bob)
    drops = np.array(drops)
    for _ in range(6):
        drops = (np.roll(drops, 1) + 2 * drops + np.roll(drops, -1)) / 4

    def pose(t, u):
        fi = int(round(u * n)) % n
        loc = {
            "hips": E(-2 + lean * 0.3, 0, 6 * math.sin(tau * u)),
            "spine": E(2 + lean * 0.4, 0, -4 * math.sin(tau * u)),
            "chest": E(1 + lean * 0.3 + 1.0 * math.sin(2 * tau * u), 0, -3 * math.sin(tau * u)),
            "neck": E(1 - lean * 0.4),
            "head": E(-1 - lean * 0.4 - 1.0 * math.sin(2 * tau * u), 0, 2 * math.sin(tau * u)),
        }
        rt = (0.012 * math.sin(tau * u), 0, A.stand_root_z - drops[fi])
        D, H = rig.solve(local=loc, root_t=rt)
        w = {"coat.B": aim_q(rig, "coat.B", Vector((0, 0.15 + lean * 0.01, -1)))}
        for sfx, s, off in ((".L", 1, 0.0), (".R", -1, 0.5)):
            y, lf, pitch = _gait_foot(u + off, speed, frames, stance, lift)
            Ta = Vector((0.09 * s, y, 0.078 + lf))
            Ah = H["thigh" + sfx]
            kn = _ik(Ah, Ta, L("thigh" + sfx), L("shin" + sfx), Vector((0.1 * s, -1, 0.1)))
            w["thigh" + sfx] = aim_q(rig, "thigh" + sfx, kn - Ah)
            w["shin" + sfx] = aim_q(rig, "shin" + sfx, Ta - kn)
            w["foot" + sfx] = aim_q(rig, "foot" + sfx, C.rx(-pitch) @ Vector((0.1 * s, -1, -0.42)))
            # arms swing against the legs
            sw = -math.sin(tau * (u + off))
            ua = Vector((0.17 * s, 0.03 - arm_swing * sw, -1))
            w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, ua)
            fa = Vector((0.08 * s, -0.25 - 0.45 * max(0.0, sw), -1)) if elbow == 0 else C.rx(-85 * elbow) @ ua
            w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, fa)
            w["hand" + sfx] = hand_q(s, fa + Vector((0, 0.1, 0)), up=(0.2 * s, -1, 0))
        return loc, w, rt
    return A.frames(n, pose)


def walk_clip(A):
    return gait_clip(A, WALK_SPEED, WALK_FRAMES, 0.6, 0.11, 0.0, 0.32, 0.0, 0.0)


def run_clip(A):
    return gait_clip(A, RUN_SPEED, RUN_FRAMES, 0.36, 0.26, 14.0, 0.7, 0.9, 0.05)


def talk_clip(A, n=240):
    """Standing and talking: weight shifts, a nod, the right hand making the
    point, the left resting on the hip (4 s loop)."""
    rig = A.rig
    tau = 2 * math.pi

    def pose(t, u):
        g1 = math.sin(tau * u * 2) * 0.5 + 0.5
        g2 = math.sin(tau * (u * 3 + 0.2))
        loc = {
            "hips": E(-4, 0, 3 * math.sin(tau * u)),
            "spine": E(-1, 0, -2 * math.sin(tau * u)),
            "chest": E(1 + 2 * g1, 0, 4 * math.sin(tau * u + 1)),
            "neck": E(2),
            "head": E(3 * math.sin(tau * u * 4), 0, 10 * math.sin(tau * (u + 0.1))),
        }
        w = stand_legs(rig, spread=0.06)
        w = stand_arms(rig, w)
        w["coat.B"] = aim_q(rig, "coat.B", Vector((0, 0.12, -1)))
        # right hand up and open, gesturing
        w["upperarm.R"] = aim_q(rig, "upperarm.R", Vector((-0.35, -0.35 - 0.15 * g1, -1)))
        w["forearm.R"] = aim_q(rig, "forearm.R", Vector((-0.1 + 0.2 * g2, -1, 0.35 + 0.35 * g1)))
        w["hand.R"] = hand_q(-1, Vector((-0.2 + 0.2 * g2, -1, 0.2 + 0.3 * g1)), up=(-0.6, 0.2, 0.6))
        # left hand on the hip
        w["upperarm.L"] = aim_q(rig, "upperarm.L", Vector((0.6, 0.2, -1)))
        w["forearm.L"] = aim_q(rig, "forearm.L", Vector((-0.8, -0.1, -0.35)))
        w["hand.L"] = hand_q(1, Vector((-0.6, 0.1, -1)), up=(1, 0, 0))
        rt = (0.01 * math.sin(tau * u), 0, A.stand_root_z - 0.012)
        return loc, w, rt
    return A.frames(n, pose)


SIT_DROP = 0.46   # Sit: the root is the seat surface; the feet are this far below it


def sit_clip(A, n=240):
    """Sat on a bench: ROOT AT THE SEAT SURFACE (unlike the standing clips), feet
    on the ground SIT_DROP below, hands on the knees, breathing, looking about."""
    rig = A.rig
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731
    tau = 2 * math.pi

    def pose(t, u):
        br = math.sin(tau * u * 1.5)
        loc = {
            "hips": E(-2),
            "spine": E(6 + 0.6 * br),
            "chest": E(4 + 0.6 * br),
            "neck": E(-5),
            "head": E(-3 + 3 * math.sin(tau * u * 2), 0, 20 * math.sin(tau * (u + 0.15))),
        }
        rt = (0, 0, 0)
        D, H = rig.solve(local=loc, root_t=rt)
        w = {"coat.B": aim_q(rig, "coat.B", Vector((0, 1, -0.6)))}
        for sfx, s in ((".L", 1), (".R", -1)):
            Ta = Vector((0.13 * s, -0.42, -SIT_DROP + 0.078))
            Ah = H["thigh" + sfx]
            kn = _ik(Ah, Ta, L("thigh" + sfx), L("shin" + sfx), Vector((0.15 * s, -1, 0.6)))
            w["thigh" + sfx] = aim_q(rig, "thigh" + sfx, kn - Ah)
            w["shin" + sfx] = aim_q(rig, "shin" + sfx, Ta - kn)
            w["foot" + sfx] = aim_q(rig, "foot" + sfx, Vector((0.1 * s, -1, -0.42)))
            # palms on the knees
            Aw = H["upperarm" + sfx]
            palm_off = (Vector(palm(s)) - Vector(J(s)["wri"])).length
            wri = kn + Vector((0.0, 0.07, 0.06))
            el = _ik(Aw, wri, L("upperarm" + sfx), L("forearm" + sfx), Vector((0.6 * s, 0.4, -1)))
            w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, el - Aw)
            w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, wri - el)
            w["hand" + sfx] = hand_q(s, Vector((0.0, -1, -0.5)), up=(0.0, -0.3, 1))
        return loc, w, rt
    return A.frames(n, pose)


RAIL = (1.07, 0.45)  # LeanRail: rail height above the feet, and how far in front of the root


def leanrail_clip(A, n=240):
    """Standing at a rail (bar or hitching rail): forearms on it, one knee
    cocked, weight shifting (feet at the origin like the standing clips)."""
    rig = A.rig
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731
    tau = 2 * math.pi

    def pose(t, u):
        sh = math.sin(tau * u)
        loc = {
            "hips": E(-2, 0, 4 + 2 * sh),
            "spine": E(16, 0, -3 * sh),
            "chest": E(12),
            "neck": E(-14),
            "head": E(-10 + 2 * math.sin(tau * u * 2), 0, 14 * math.sin(tau * (u + 0.3))),
        }
        w = stand_legs(rig, spread=0.07)
        w["shin.R"] = aim_q(rig, "shin.R", Vector((-0.02, 0.35, -1)))  # cocked knee
        w["foot.R"] = aim_q(rig, "foot.R", Vector((-0.1, -1, -0.9)))
        rt = (0.01 * sh, 0.06, A.stand_root_z - 0.03)
        D, H = rig.solve(local=loc, world=w, root_t=rt)
        w["coat.B"] = aim_q(rig, "coat.B", Vector((0, 0.12, -1)))
        for sfx, s in ((".L", 1), (".R", -1)):
            Aw = H["upperarm" + sfx]
            wri = Vector((0.07 * s, -RAIL[1] + 0.02, RAIL[0] + 0.05))  # forearm resting on the rail top
            el = _ik(Aw, wri, L("upperarm" + sfx), L("forearm" + sfx), Vector((0.5 * s, 0.7, -0.6)))
            w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, el - Aw)
            w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, wri - el)
            w["hand" + sfx] = hand_q(s, Vector((-0.5 * s, -1, -0.1)), up=(0, 0, 1))
        return loc, w, rt
    return A.frames(n, pose)


AIM_DIR_L = Vector((0.62, -0.78, 0.06)).normalized()  # forward-left (rider's left = +X)
UPPER_L = ["spine", "chest", "neck", "head", "shoulder.L", "upperarm.L", "forearm.L", "hand.L"]


def aim_upper_l(rig, loc, rt, direction, turn=22.0):
    """aim_upper mirrored: the left hand points a gun forward-left."""
    loc = dict(loc)
    loc["chest"] = loc.get("chest", Quaternion()) @ E(0, 0, turn * 0.6)
    loc["spine"] = loc.get("spine", Quaternion()) @ E(0, 0, turn * 0.4)
    loc["neck"] = loc.get("neck", Quaternion()) @ E(0, 0, turn * 0.5)
    loc["head"] = E(-2, 0, turn * 0.6)
    loc["shoulder.L"] = E(0, 0, 8)
    world = {"upperarm.L": aim_q(rig, "upperarm.L", direction), "forearm.L": aim_q(rig, "forearm.L", direction),
             "hand.L": hand_q(1, direction)}
    return loc, world, rt


def rideaiml_clip(A, n=32):
    tau = 2 * math.pi

    def pose(t, phi):
        loc, rt = ride_base(phi, lean=6.0)
        d = (AIM_DIR_L + Vector((0, 0, 0.012 * math.cos(tau * (phi - 0.9))))).normalized()
        loc["upperarm.R"] = E(-8)
        return aim_upper_l(A.rig, loc, rt, d)
    return A.frames(n, pose)


def shootl_clip(A, n=15):
    """ShootL: Shoot for the left hand; frame 0 == RideAimL's reference pose."""
    def pose(t, u):
        loc, rt = ride_base(0.0, lean=6.0)
        k = (t / 0.04) if t < 0.04 else math.exp(-(t - 0.04) / 0.06)
        k = max(0.0, k) * (1 - C.smoothstep((t - 0.18) / 0.07))
        d = (AIM_DIR_L + Vector((0, 0, 0.35 * k))).normalized()
        loc2, world, rt = aim_upper_l(A.rig, loc, rt, d)
        world["hand.L"] = hand_q(1, (AIM_DIR_L + Vector((0, 0, 0.8 * k))).normalized())
        loc2["chest"] = loc2["chest"] @ E(-4 * k)
        loc2["head"] = loc2["head"] @ E(-3 * k)
        return loc2, world, rt
    return A.frames(n, pose, bones=UPPER_L)


DUAL_R = Vector((-0.2, -0.98, 0.05)).normalized()
DUAL_L = Vector((0.2, -0.98, 0.05)).normalized()


def rideaimdual_clip(A, n=32):
    """Both Navies out, arms forward, square to the front (Hickok)."""
    tau = 2 * math.pi
    rig = A.rig

    def pose(t, phi):
        loc, rt = ride_base(phi, lean=6.0)
        b = Vector((0, 0, 0.012 * math.cos(tau * (phi - 0.9))))
        dr, dl = (DUAL_R + b).normalized(), (DUAL_L + b).normalized()
        loc["head"] = E(-2)
        loc["shoulder.R"] = E(0, 0, -6)
        loc["shoulder.L"] = E(0, 0, 6)
        world = {"upperarm.R": aim_q(rig, "upperarm.R", dr), "forearm.R": aim_q(rig, "forearm.R", dr), "hand.R": hand_q(-1, dr),
                 "upperarm.L": aim_q(rig, "upperarm.L", dl), "forearm.L": aim_q(rig, "forearm.L", dl), "hand.L": hand_q(1, dl)}
        return loc, world, rt
    return A.frames(n, pose)


def rideholstered_clip(A, n=32):
    """Riding in formation, guns in the sash: reins gathered in the left hand at
    the pommel, the right hand resting on the thigh by the gun butts."""
    rig = A.rig
    L = lambda b: (rig.tail[b] - rig.head[b]).length  # noqa: E731

    def pose(t, phi):
        loc, rt = ride_base(phi, lean=8.0)
        D, H = rig.solve(local=loc, root_t=rt)
        w = {}
        for sfx, s, tgt, pole in ((".L", 1, Vector((0.03, -0.30, 0.25)), Vector((0.8, 0.3, -1))),
                                  (".R", -1, Vector((-0.17, -0.24, 0.14)), Vector((-1, 0.4, -0.3)))):
            Aw = H["upperarm" + sfx]
            el = _ik(Aw, tgt, L("upperarm" + sfx), L("forearm" + sfx), pole)
            w["upperarm" + sfx] = aim_q(rig, "upperarm" + sfx, el - Aw)
            w["forearm" + sfx] = aim_q(rig, "forearm" + sfx, tgt - el)
        w["hand.L"] = hand_q(1, Vector((-0.6, -1, -0.2)), up=(0.3, 0, 1))
        w["hand.R"] = hand_q(-1, Vector((0.1, -1, -0.6)), up=(-0.5, 0, 1))
        return loc, w, rt
    return A.frames(n, pose)


# ----------------------------------------------------------------------------
def build_mesh(name, prims, h, tris, color_fn, tex, rough=0.85, uv_angle=66, arm_split=None):
    ob = C.build_sdf_mesh(name, prims, h, tris)
    if arm_split is None:
        C.smart_uv(ob, angle=uv_angle)
    else:  # sleeves unwrapped apart from the body (see split_smart_uv)
        fv = np.empty(len(ob.data.polygons) * 3, dtype=np.int32)
        ob.data.polygons.foreach_get("vertices", fv)
        fa = on_arm(ob, arm_split)[fv.reshape(-1, 3)].mean(1) > 0.5
        split_smart_uv(ob, [fa, ~fa], 0.006, angle=uv_angle)
    img = C.bake_texture(ob, tex, color_fn, name + "_tex")
    C.assign_material(ob, C.image_material(name + "_mat", img, roughness=rough))
    return ob


def main():
    C.reset_scene()
    bp = body_prims()
    body = build_mesh("Body", bp, 0.0065, 4700, body_color(bp), 1024)
    dp = duster_prims(bp)
    duster = build_mesh("Duster", dp, 0.008, 3000, cloth_color(dp, (0.34, 0.28, 0.22), duster_pattern), 512)

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
    drv = build_driver()
    ol = build_outlaws()

    arm = C.build_armature("RiderRig", bone_list())
    rig = C.Rig(arm)
    segs = {b: (np.array(rig.head[b]), np.array(rig.tail[b])) for b in rig.order}
    C.compute_weights(body, bp, segs, tau=0.012, smooth_iters=3)
    C.compute_weights(duster, dp, segs, tau=0.02, smooth_iters=4)
    for h in hats:
        C.rigid_weights(h, "head")
    dbody, dbp = drv["body"]
    C.compute_weights(dbody, dbp, segs, tau=0.012, smooth_iters=3)
    Wc, names = C.compute_weights(drv["coat"][0], drv["coat"][1], segs, tau=0.02, smooth_iters=4)
    skirt_follow(dbody, drv["coat"][0], Wc, names)
    C.compute_weights(drv["kerchief"][0], drv["kerchief"][1], segs, tau=0.01, smooth_iters=2)
    for h in (drv["hat"], drv["mous"]):
        C.rigid_weights(h, "head")
    C.rigid_weights(drv["watch"], "spine")  # (nearest-vert transfer would grab the hands resting on the belly)
    driver = [dbody, drv["coat"][0], drv["hat"], drv["mous"], drv["kerchief"][0], drv["watch"]]
    mbody = ol["Body_Man"][0]
    for name, (ob, prims) in ol.items():
        if prims is None:
            C.rigid_weights(ob, "head")
        elif name in ("Body_Man", "Body_Female"):
            C.compute_weights(ob, prims, segs, tau=0.012, smooth_iters=3, overrides=forearm_override(prims))
        elif name in ("Coat_Guard", "Coat_Buffalo"):
            Wc, names = C.compute_weights(ob, prims, segs, tau=0.02, smooth_iters=4)
            skirt_follow(mbody, ob, Wc, names, free_tail=True)
        elif name in ("Moustache_Guard", "Moustache_Vaquero"):
            C.rigid_weights(ob, "head")
        else:
            C.compute_weights(ob, prims, segs, tau=0.015, smooth_iters=3)
    outlaws = [ob for ob, _ in ol.values()]
    A = RiderAnim(rig)
    town = list(build_woman(A, segs).values()) + [make_hat_lawman(ol["Body_Man"][1])]
    hick = build_hickok(segs)
    meshes = [body, duster] + hats + driver + outlaws + town + hick
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
    fwd = HAND_FWD[-1].normalized()
    side = Vector((0, 0, 1)).cross(fwd).normalized()
    up = fwd.cross(side)
    rot = Matrix((side, -fwd, up)).transposed()  # Blender: -Y = barrel, +Z = up  (glTF: +Z barrel, +Y up)
    g.matrix_world = Matrix.Translation(Vector(palm(-1))) @ rot.to_4x4()
    # and its mirror in the left palm, for a second gun (Hickok's other Navy)
    gl = bpy.data.objects.new("Grip_L", None)
    gl.empty_display_type = "ARROWS"
    gl.empty_display_size = 0.1
    bpy.context.scene.collection.objects.link(gl)
    gl.parent = arm
    gl.parent_type = "BONE"
    gl.parent_bone = "hand.L"
    bpy.context.view_layer.update()
    fwd = HAND_FWD[1].normalized()
    side = Vector((0, 0, 1)).cross(fwd).normalized()
    up = fwd.cross(side)
    gl.matrix_world = Matrix.Translation(Vector(palm(1))) @ Matrix((side, -fwd, up)).transposed().to_4x4()

    C.write_action(arm, "Ride", ride_clip(A), loop=True)
    C.write_action(arm, "RideAim", rideaim_clip(A), loop=True)
    C.write_action(arm, "Shoot", shoot_clip(A))
    C.write_action(arm, "FallOff", falloff_clip(A))
    C.write_action(arm, "StandIdle", standidle_clip(A), loop=True)
    C.write_action(arm, "StandShoot", standshoot_clip(A))
    C.write_action(arm, "DieStanding", die_clip(A))
    C.write_action(arm, "Drive", drive_clip(A), loop=True)
    C.write_action(arm, "SeatAim", seataim_clip(A), loop=True)
    C.write_action(arm, "SeatShoot", seatshoot_clip(A))
    C.write_action(arm, "Walk", walk_clip(A), loop=True)
    C.write_action(arm, "Talk", talk_clip(A), loop=True)
    C.write_action(arm, "RideAimL", rideaiml_clip(A), loop=True)
    C.write_action(arm, "ShootL", shootl_clip(A))
    C.write_action(arm, "RideAimDual", rideaimdual_clip(A), loop=True)
    C.write_action(arm, "RideHolstered", rideholstered_clip(A), loop=True)
    C.write_action(arm, "Run", run_clip(A), loop=True)
    C.write_action(arm, "Sit", sit_clip(A), loop=True)
    C.write_action(arm, "LeanRail", leanrail_clip(A), loop=True)
    print(f"[rider] Walk: {WALK_SPEED} m/s, stride {WALK_STRIDE:.3f} m per cycle ({WALK_STRIDE / 2:.3f} m per step), "
          f"cycle {WALK_FRAMES / C.FPS:.3f} s; Run: {RUN_SPEED} m/s, stride {RUN_STRIDE:.3f} m, cycle {RUN_FRAMES / C.FPS:.3f} s")
    arm.animation_data.action = bpy.data.actions["Ride"]

    tot = 0
    for ob in meshes:
        print(f"[rider] {ob.name}: {C.tri_count(ob)} tris")
        tot += C.tri_count(ob)
    print("[rider] total tris", tot, "stand_root_z", A.stand_root_z)
    C.export_glb(OUT, [arm, g, gl] + meshes)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.PREVIEWS, "rider_build.blend"))


if __name__ == "__main__":
    main()
