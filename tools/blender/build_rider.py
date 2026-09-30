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


def driver_face_uv(ob, k=2.3):
    """Smart-UV with the head scaled up so the face gets ~k^2 the texel density."""
    co = C.verts_np(ob)
    head = co[:, 2] > 0.715
    big = co.copy()
    ctr = np.array([0.0, 0.0, 0.83])
    big[head] = ctr + (co[head] - ctr) * k
    ob.data.vertices.foreach_set("co", big.astype(np.float32).ravel())
    ob.data.update()
    C.smart_uv(ob, angle=80)
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


def skirt_follow(body, coat, Wc, names, k=4):
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


# ----------------------------------------------------------------------------
def build_mesh(name, prims, h, tris, color_fn, tex, rough=0.85, uv_angle=66):
    ob = C.build_sdf_mesh(name, prims, h, tris)
    C.smart_uv(ob, angle=uv_angle)
    img = C.bake_texture(ob, tex, color_fn, name + "_tex")
    C.assign_material(ob, C.image_material(name + "_mat", img, roughness=rough))
    return ob


def main():
    C.reset_scene()
    bp = body_prims()
    body = build_mesh("Body", bp, 0.0065, 4700, body_color(bp), 1024)
    dp = duster_prims(bp)
    duster = build_mesh("Duster", dp, 0.008, 3000, cloth_color(dp, (0.34, 0.28, 0.22), duster_pattern), 512)
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
    drv = build_driver()

    arm = C.build_armature("RiderRig", bone_list())
    rig = C.Rig(arm)
    segs = {b: (np.array(rig.head[b]), np.array(rig.tail[b])) for b in rig.order}
    C.compute_weights(body, bp, segs, tau=0.012, smooth_iters=3)
    C.compute_weights(duster, dp, segs, tau=0.02, smooth_iters=4)
    C.compute_weights(poncho, pp, segs, tau=0.02, smooth_iters=3)
    C.compute_weights(bandana, bdp, segs, tau=0.01, smooth_iters=2)
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
    meshes = [body, duster, poncho, bandana] + hats + driver
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

    A = RiderAnim(rig)
    C.write_action(arm, "Ride", ride_clip(A), loop=True)
    C.write_action(arm, "RideAim", rideaim_clip(A), loop=True)
    C.write_action(arm, "Shoot", shoot_clip(A))
    C.write_action(arm, "FallOff", falloff_clip(A))
    C.write_action(arm, "StandIdle", standidle_clip(A), loop=True)
    C.write_action(arm, "StandShoot", standshoot_clip(A))
    C.write_action(arm, "DieStanding", die_clip(A))
    C.write_action(arm, "Drive", drive_clip(A), loop=True)
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
