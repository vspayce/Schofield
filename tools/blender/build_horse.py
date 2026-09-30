"""Build public/assets/models/horse.glb  (SCHOFIELD)

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_horse.py [-- --breed clydesdale|clevelandbay|thoroughbred]

With --breed it builds horse_<breed>.glb for the coach team instead (see BREEDS):
the same rig, clips and node names, warped to the breed, with its own coat and
markings, a draught harness (collar + hames, blinkered bridle, pad, crupper,
traces; breeching on the wheelers) and hitch empties Trace_/Terret_/HameTerret_/
Bit_/HeadRing_ L/R and PoleStrap that src/game/hitch.js hangs the gear on.

Blender space: horse faces -Y, Z up, origin on the ground under the barrel.
~2.4 m nose->buttock (+tail), 1.6 m at the withers.

Meshes:  Horse (skinned body incl. mane/tail), Saddle (skinned, hideable),
         Harness (bridle, reins, breast collar, cinch; skinned, hideable)
Empty:   Mount  (bone-parented to 'spine', at the saddle seat; rider hips go here)
Clips:   Gallop (loop), Canter (loop), Idle (loop), Fall (one-shot), Rear (one-shot)
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import common as C  # noqa: E402

OUT = os.path.join(C.MODELS, "horse.glb")
H = 0.011  # SDF voxel size (m)

# ----------------------------------------------------------------------------
# skeleton (rest pose).  (x, y, z); +x is the horse's LEFT (.L)
# ----------------------------------------------------------------------------
FRONT = ["scapula", "humerus", "radius", "fcannon", "fpastern", "fhoof"]
HIND = ["femur", "tibia", "hcannon", "hpastern", "hhoof"]


def front_joints(s):
    x = 0.13 * s
    return [
        (0.15 * s, -0.44, 1.50),  # scapula top
        (0.17 * s, -0.72, 1.17),  # shoulder joint
        (0.15 * s, -0.53, 0.97),  # elbow
        (x, -0.56, 0.50),  # knee (carpus)
        (x, -0.555, 0.165),  # fetlock
        (x, -0.605, 0.075),  # coronet
        (x, -0.665, 0.0),  # toe
    ]


def hind_joints(s):
    x = 0.13 * s
    return [
        (0.16 * s, 0.52, 1.25),  # hip joint
        (0.18 * s, 0.38, 0.96),  # stifle
        (0.14 * s, 0.73, 0.555),  # hock
        (x, 0.70, 0.165),  # fetlock
        (x, 0.645, 0.075),  # coronet
        (x, 0.59, 0.0),  # toe
    ]


def bone_list():
    B = [
        ("root", (0, -0.05, 1.20), (0, -0.05, 1.36), None, False),
        ("pelvis", (0, 0.05, 1.36), (0, 0.62, 1.40), "root", False),
        ("spine", (0, 0.05, 1.36), (0, -0.33, 1.40), "root", False),
        ("chest", (0, -0.33, 1.40), (0, -0.62, 1.36), "spine", True),
        ("neck1", (0, -0.62, 1.36), (0, -0.88, 1.66), "chest", True),
        ("neck2", (0, -0.88, 1.66), (0, -1.05, 1.96), "neck1", True),
        ("head", (0, -1.05, 1.96), (0, -1.46, 1.58), "neck2", True),
        ("tail1", (0, 0.80, 1.46), (0, 0.93, 1.33), "pelvis", False),
        ("tail2", (0, 0.93, 1.33), (0, 1.03, 1.10), "tail1", True),
        ("tail3", (0, 1.03, 1.10), (0, 1.10, 0.86), "tail2", True),
        ("tail4", (0, 1.10, 0.86), (0, 1.14, 0.62), "tail3", True),
    ]
    for side, s in ((".L", 1), (".R", -1)):
        j = front_joints(s)
        par = "chest"
        for i, n in enumerate(FRONT):
            B.append((n + side, j[i], j[i + 1], par, i > 0))
            par = n + side
        j = hind_joints(s)
        par = "pelvis"
        for i, n in enumerate(HIND):
            B.append((n + side, j[i], j[i + 1], par, i > 0))
            par = n + side
    return B


# ----------------------------------------------------------------------------
# body SDF
# ----------------------------------------------------------------------------
def body_prims():
    E, K = C.ell, C.cone
    P = []
    T = ["pelvis", "spine", "chest"]
    # trunk
    P += [
        E((0, -0.40, 1.25), (0.26, 0.40, 0.35), "coat", ["spine", "chest"], k=0.08),  # rib cage / chest
        E((0, -0.02, 1.215), (0.30, 0.50, 0.325), "coat", T, k=0.10),  # barrel
        E((0, -0.47, 1.50), (0.10, 0.26, 0.11), "coat", ["chest"], k=0.08),  # withers
        E((0, 0.18, 1.44), (0.21, 0.36, 0.13), "coat", ["spine", "pelvis"], k=0.08),  # loin
        E((0, 0.50, 1.42), (0.21, 0.30, 0.16), "coat", ["pelvis"], k=0.06),  # croup
        E((0, 0.66, 1.37), (0.16, 0.22, 0.12), "coat", ["pelvis"], k=0.06),  # rump top toward tail
        E((0, -0.12, 0.98), (0.20, 0.36, 0.12), "coat", ["spine", "chest"], k=0.10),  # belly bottom
    ]
    for s in (1, -1):
        x = s
        sfx = ".L" if s > 0 else ".R"
        P += [
            E((0.10 * x, 0.55, 1.26), (0.17, 0.30, 0.28), "coat", ["pelvis", "femur" + sfx], k=0.07),  # hindquarter
            E((0.09 * x, -0.72, 1.08), (0.10, 0.10, 0.14), "coat", ["chest", "humerus" + sfx], k=0.10),  # pectoral
            K((0.16 * x, -0.45, 1.46), (0.18 * x, -0.70, 1.17), 0.09, 0.11, "coat", ["scapula" + sfx], k=0.10, scale=(0.72, 1, 1)),  # shoulder
            E((0.16 * x, -0.60, 1.07), (0.085, 0.13, 0.10), "coat", ["humerus" + sfx, "scapula" + sfx], k=0.09),  # triceps
            E((0.145 * x, 0.40, 1.02), (0.07, 0.10, 0.10), "coat", ["femur" + sfx, "tibia" + sfx], k=0.11),  # stifle/flank
        ]
    # neck
    P += [
        K((0, -0.64, 1.34), (0, -1.00, 1.88), 0.235, 0.11, "coat", ["chest", "neck1", "neck2"], k=0.07, scale=(0.64, 1, 1)),
        E((0, -0.72, 1.70), (0.075, 0.22, 0.10), "coat", ["neck1", "chest"], k=0.08),  # crest base
        E((0, -0.90, 1.88), (0.07, 0.15, 0.09), "coat", ["neck2", "neck1"], k=0.07),  # crest top
    ]
    # head
    hb = ["head"]
    P += [
        E((0, -1.13, 1.93), (0.095, 0.12, 0.11), "coat", hb + ["neck2"], k=0.05),  # cranium / poll
        E((0, -1.15, 1.81), (0.10, 0.12, 0.11), "coat", hb, k=0.05),  # jowls
        K((0, -1.19, 1.89), (0, -1.43, 1.60), 0.095, 0.066, "coat", hb, k=0.05, scale=(0.85, 1, 1)),  # face
        E((0, -1.445, 1.575), (0.072, 0.075, 0.075), "muzzle", hb, k=0.04),  # muzzle
        E((0, -1.41, 1.515), (0.05, 0.06, 0.035), "muzzle", hb, k=0.03),  # chin
        K((0, -1.18, 1.75), (0, -1.40, 1.535), 0.07, 0.042, "coat", hb, k=0.05),  # jaw line
    ]
    for s in (1, -1):
        P += [
            K((0.055 * s, -1.075, 2.02), (0.085 * s, -1.08, 2.19), 0.032, 0.007, "ear", hb, k=0.025, scale=(1, 0.7, 1)),
            E((0.095 * s, -1.21, 1.925), (0.022, 0.03, 0.022), "eye", hb, k=0.012),
            E((0.042 * s, -1.505, 1.605), (0.022, 0.02, 0.028), "nostril", hb, k=0.015),
        ]
    # mane + forelock (laterally thin, dark)
    mb = ["neck1", "neck2", "head", "chest"]
    P += [
        K((-0.012, -1.04, 2.07), (-0.02, -0.80, 1.95), 0.04, 0.06, "mane", mb, k=0.02, scale=(0.5, 1, 1)),
        K((-0.02, -0.80, 1.95), (-0.012, -0.50, 1.66), 0.06, 0.04, "mane", mb, k=0.02, scale=(0.5, 1, 1)),
        K((0, -1.10, 2.07), (0, -1.19, 1.98), 0.028, 0.034, "mane", ["head"], k=0.02, scale=(0.9, 1, 1)),
    ]
    # tail
    tb = ["tail1", "tail2", "tail3", "tail4"]
    P += [
        K((0, 0.78, 1.46), (0, 0.92, 1.34), 0.065, 0.05, "coat", ["pelvis", "tail1"], k=0.04),  # dock
        K((0, 0.90, 1.36), (0, 1.03, 1.10), 0.055, 0.075, "tail", tb, k=0.02, scale=(0.8, 1, 1)),
        K((0, 1.03, 1.10), (0, 1.10, 0.86), 0.075, 0.085, "tail", tb, k=0.02, scale=(0.7, 1, 1)),
        K((0, 1.10, 0.86), (0, 1.14, 0.60), 0.085, 0.045, "tail", tb, k=0.02, scale=(0.7, 1, 1)),
    ]
    # legs
    for s in (1, -1):
        sfx = ".L" if s > 0 else ".R"
        f = front_joints(s)
        x = 0.13 * s
        P += [
            K((0.15 * s, -0.55, 1.00), (x, -0.565, 0.54), 0.085, 0.048, "coat", ["radius" + sfx, "humerus" + sfx], k=0.04, scale=(0.85, 1, 1)),
            E((0.135 * s, -0.60, 0.84), (0.06, 0.06, 0.14), "coat", ["radius" + sfx], k=0.04),  # forearm extensor
            E((x, -0.565, 0.50), (0.05, 0.052, 0.058), "coat", ["radius" + sfx, "fcannon" + sfx], k=0.025),  # knee
            K((x, -0.565, 0.46), (x, -0.56, 0.19), 0.04, 0.036, "lower", ["fcannon" + sfx], k=0.02, scale=(0.8, 1, 1)),
            K((x, -0.525, 0.45), (x, -0.515, 0.20), 0.022, 0.024, "lower", ["fcannon" + sfx], k=0.02),  # tendon
            E((x, -0.545, 0.16), (0.043, 0.052, 0.048), "lower", ["fcannon" + sfx, "fpastern" + sfx], k=0.02),  # fetlock
            K((x, -0.56, 0.15), (x, -0.60, 0.085), 0.037, 0.041, "lower", ["fpastern" + sfx], k=0.015),
            K((x, -0.605, 0.078), (x, -0.62, 0.02), 0.048, 0.063, "hoof", ["fhoof" + sfx], k=0.012),
        ]
        h = hind_joints(s)
        P += [
            K((0.15 * s, 0.63, 1.22), (0.145 * s, 0.70, 0.80), 0.21, 0.10, "coat", ["femur" + sfx, "pelvis", "tibia" + sfx], k=0.06, scale=(0.8, 1, 1)),  # thigh/hamstring
            K((0.15 * s, 0.56, 0.95), (0.14 * s, 0.73, 0.59), 0.095, 0.055, "coat", ["tibia" + sfx], k=0.04, scale=(0.8, 1, 1)),  # gaskin
            E((0.14 * s, 0.735, 0.55), (0.048, 0.07, 0.065), "coat", ["tibia" + sfx, "hcannon" + sfx], k=0.025),  # hock
            E((0.14 * s, 0.795, 0.60), (0.028, 0.035, 0.045), "coat", ["tibia" + sfx], k=0.03),  # point of hock
            K((x, 0.73, 0.52), (x, 0.70, 0.19), 0.043, 0.038, "lower", ["hcannon" + sfx], k=0.02, scale=(0.8, 1, 1)),
            K((x, 0.765, 0.50), (x, 0.73, 0.20), 0.02, 0.024, "lower", ["hcannon" + sfx], k=0.02),  # tendon
            E((x, 0.705, 0.16), (0.043, 0.052, 0.048), "lower", ["hcannon" + sfx, "hpastern" + sfx], k=0.02),
            K((x, 0.69, 0.15), (x, 0.645, 0.085), 0.037, 0.041, "lower", ["hpastern" + sfx], k=0.015),
            K((x, 0.645, 0.078), (x, 0.62, 0.02), 0.047, 0.061, "hoof", ["hhoof" + sfx], k=0.012),
        ]
    # flat soles
    P.append(C.box((0, 0, -0.5), (3, 3, 0.5), 0.0, "cut", [], sub=True, k=0.0))
    return P


LABELS = ["coat", "muzzle", "ear", "eye", "nostril", "mane", "tail", "lower", "hoof"]


def horse_color(prims):
    def fn(P, N, ex):
        lw = C.label_weights(prims, P, LABELS, tau=0.01)
        n1 = C.fbm(P * np.array([1.0, 0.25, 1.0]), 22.0, 3, seed=3)  # hair grain along body
        n2 = C.fbm(P, 5.0, 3, seed=7)
        coat = np.array([0.66, 0.49, 0.34])
        c = np.tile(coat, (len(P), 1))
        c *= (0.93 + 0.12 * n2)[:, None] * (0.96 + 0.08 * n1)[:, None]
        # sun-bleached topline, slightly darker lower barrel, lighter belly/inside
        top = np.clip(N[:, 2], 0, 1)
        c *= (1.0 + 0.06 * top)[:, None]
        c *= (1.0 - 0.10 * np.clip(-N[:, 2], 0, 1) * (P[:, 2] > 0.8))[:, None]
        # dark points: legs below knee/hock (bay pattern)
        leg = np.clip((0.60 - P[:, 2]) / 0.16, 0, 1)
        leg = leg * leg * (3 - 2 * leg)
        dark = np.array([0.11, 0.08, 0.065]) * (0.9 + 0.2 * n1)[:, None]
        c = c * (1 - leg[:, None]) + dark * leg[:, None]
        # muzzle / ear tips
        mz = lw["muzzle"][:, None]
        c = c * (1 - 0.75 * mz) + np.array([0.20, 0.15, 0.13]) * 0.75 * mz
        et = (lw["ear"] * np.clip((P[:, 2] - 2.08) / 0.08, 0, 1))[:, None]
        c = c * (1 - et) + dark * et
        hair = np.clip(lw["mane"] + lw["tail"], 0, 1)[:, None]
        streak = C.fbm(P * np.array([6.0, 1.0, 0.35]), 30.0, 2, seed=11)
        hc = np.array([0.075, 0.055, 0.045]) * (0.8 + 0.5 * streak)[:, None]
        c = c * (1 - hair) + hc * hair
        hv = lw["hoof"][:, None]
        c = c * (1 - hv) + np.array([0.20, 0.17, 0.14]) * hv
        ey = lw["eye"][:, None]
        c = c * (1 - ey) + np.array([0.03, 0.02, 0.02]) * ey
        ns = lw["nostril"][:, None]
        c = c * (1 - 0.9 * ns) + np.array([0.05, 0.035, 0.03]) * 0.9 * ns
        ao = C.sdf_ao([p for p in prims if not p.sub], P, N, steps=5, dist=0.03)
        c *= (0.35 + 0.65 * ao ** 1.2)[:, None]
        return c

    return fn


# ----------------------------------------------------------------------------
# saddle + harness
# ----------------------------------------------------------------------------
def body_sdf_fn(prims):
    ps = [p for p in prims if not p.sub]
    return lambda p: C.eval_sdf(ps, p)


def top_z(bodyf, y, x=0.0):
    zs = np.linspace(2.0, 1.2, 800)
    P = np.stack([np.full_like(zs, x), np.full_like(zs, y), zs], axis=1)
    d = bodyf(P)
    i = int(np.argmax(d < 0))
    return float(zs[i])


def saddle_prims(bodyf, seat, wx=1.0):
    """seat: z of the back surface at the seat. wx widens fenders/stirrups for a broader barrel."""
    E, K = C.ell, C.cone

    def rbox(p, c, h, r):
        q = np.abs(p - np.asarray(c)) - (np.asarray(h) - r)
        return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(axis=1), 0) - r

    def pad(p):  # woven blanket: 2.2 cm shell over the back
        b = bodyf(p)
        shell = np.maximum(b - 0.022, -b - 0.004)
        return np.maximum(shell, rbox(p, (0, -0.19, 1.60), (0.5, 0.33, 0.30), 0.05))

    def skirt(p):  # leather skirt on top of the pad
        b = bodyf(p)
        shell = np.maximum(b - 0.042, -b - 0.018)
        return np.maximum(shell, rbox(p, (0, -0.17, 1.66), (0.5, 0.26, 0.26), 0.06))

    bs = ["spine"]
    P = [
        C.fnprim(pad, (-0.45, -0.60, 1.20), (0.45, 0.20, 1.72), "pad", bs, k=0.0),
        C.fnprim(skirt, (-0.45, -0.48, 1.30), (0.45, 0.14, 1.78), "leather", bs, k=0.01),
        E((0, -0.15, seat + 0.05), (0.15, 0.22, 0.045), "seat", bs, k=0.03),
        E((0, 0.05, seat + 0.10), (0.15, 0.045, 0.075), "leather", bs, k=0.04),  # cantle
        E((0, -0.35, seat + 0.085), (0.12, 0.065, 0.085), "leather", bs, k=0.04),  # fork / pommel
        K((0, -0.37, seat + 0.14), (0, -0.39, seat + 0.215), 0.022, 0.024, "horn", bs, k=0.015),
        E((0, -0.39, seat + 0.225), (0.042, 0.042, 0.016), "horn", bs, k=0.01),  # horn cap
        K((-0.21, 0.13, seat + 0.07), (0.21, 0.13, seat + 0.07), 0.07, 0.07, "roll", bs, k=0.02),  # bedroll
    ]
    for s in (1, -1):
        a = math.radians(-9 * s)
        rot = np.array([[math.cos(a), 0, -math.sin(a)], [0, 1, 0], [math.sin(a), 0, math.cos(a)]])
        P += [
            C.box((0.325 * s * wx, -0.24, 1.20), (0.013, 0.075, 0.19), 0.01, "leather", bs, k=0.0, rot=rot),  # fender
            C.box((0.345 * s * wx, -0.33, 0.965), (0.055, 0.045, 0.038), 0.014, "stirrup", bs, k=0.0),
        ]
    return P


def saddle_color(prims):
    def fn(P, N, ex):
        lw = C.label_weights(prims, P, ["pad", "leather", "seat", "horn", "roll", "stirrup"], tau=0.006)
        n = C.fbm(P, 18.0, 3, seed=5)
        stripe = (np.sin(P[:, 1] * 55) > 0.55).astype(float)
        pad = np.array([0.42, 0.13, 0.08]) * (1 - stripe[:, None]) + np.array([0.75, 0.62, 0.40]) * stripe[:, None]
        pad = pad * (1 - (np.abs(P[:, 1] + 0.19) > 0.27)[:, None] * 0.5)
        leather = np.array([0.40, 0.24, 0.13])
        seat = np.array([0.30, 0.18, 0.10])
        horn = np.array([0.22, 0.14, 0.08])
        roll = np.array([0.52, 0.47, 0.36]) * (1 - 0.5 * (np.abs(np.abs(P[:, 0]) - 0.12) < 0.02))[:, None]
        stir = np.array([0.30, 0.20, 0.12])
        c = (lw["pad"][:, None] * pad + lw["leather"][:, None] * leather + lw["seat"][:, None] * seat
             + lw["horn"][:, None] * horn + lw["roll"][:, None] * roll + lw["stirrup"][:, None] * stir)
        c *= (0.85 + 0.25 * n)[:, None]
        ao = C.sdf_ao(prims, P, N, steps=4, dist=0.02)
        c *= (0.45 + 0.55 * ao)[:, None]
        return c

    return fn


def strap(name, bodyf, pts, width=0.022, thick=0.006, off=0.008, n_sub=3):
    """Flat strap lying on the body surface through approximate points."""
    # densify with Catmull-Rom
    pts = [np.array(p, float) for p in pts]
    dense = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        for k in range(n_sub):
            u = k / n_sub
            dense.append(0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    dense.append(pts[-1])
    P = np.array(dense)
    # project onto surface + offset along gradient
    for _ in range(6):
        d = bodyf(P)
        e = 1e-3
        g = np.stack([(bodyf(P + np.eye(3)[i] * e) - d) / e for i in range(3)], axis=1)
        g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        P = P - g * (d - off)[:, None]
    d = bodyf(P)
    e = 1e-3
    Nn = np.stack([(bodyf(P + np.eye(3)[i] * e) - d) / e for i in range(3)], axis=1)
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
    return ribbon(name, P, Nn, width, thick)


def ribbon(name, P, Nn, width, thick):
    verts, faces = [], []
    n = len(P)
    for i in range(n):
        t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        t /= np.linalg.norm(t) + 1e-9
        side = np.cross(t, Nn[i])
        side /= np.linalg.norm(side) + 1e-9
        up = Nn[i]
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(P[i] + side * sx * width * 0.5 + up * sz * thick * 0.5))
    for i in range(n - 1):
        for s in range(4):
            s2 = (s + 1) % 4
            faces.append((i * 4 + s, i * 4 + s2, (i + 1) * 4 + s2, (i + 1) * 4 + s))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_harness(bodyf, seat):
    parts = []
    for s in (1, -1):
        parts.append(strap("cheek", bodyf, [(0.075 * s, -1.41, 1.60), (0.095 * s, -1.31, 1.72), (0.10 * s, -1.20, 1.85),
                                            (0.085 * s, -1.10, 1.98), (0.03 * s, -1.06, 2.05)]))
        # reins: bit -> rider's hands above the horn, hanging free (not projected)
        pts = [(0.08 * s, -1.43, 1.59), (0.13 * s, -1.28, 1.66), (0.15 * s, -1.05, 1.72), (0.13 * s, -0.80, 1.80),
               (0.07 * s, -0.55, 1.88), (0.03 * s, -0.47, 1.92)]
        P = C_dense(pts, 3)
        Nn = np.tile(np.array([s, 0.0, 0.3]), (len(P), 1))
        Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
        parts.append(ribbon("rein", P, Nn, 0.016, 0.006))
        # bit ring
        parts.append(C.tube_along("bit", [(0.085 * s, -1.41, 1.575), (0.085 * s, -1.425, 1.60), (0.085 * s, -1.41, 1.62)], 0.008, sides=4))
    parts.append(strap("crown", bodyf, [(0.03, -1.06, 2.05), (0.0, -1.055, 2.07), (-0.03, -1.06, 2.05)], n_sub=2))
    parts.append(strap("brow", bodyf, [(0.085, -1.12, 1.98), (0, -1.155, 2.02), (-0.085, -1.12, 1.98)]))
    ring = [(0.1 * math.cos(a), -1.33, 1.665 + 0.1 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 13)]
    parts.append(strap("nose", bodyf, ring, n_sub=2))
    parts.append(strap("breast", bodyf, [(0.30, -0.36, 1.40), (0.26, -0.62, 1.30), (0.14, -0.80, 1.22), (0, -0.85, 1.19),
                                        (-0.14, -0.80, 1.22), (-0.26, -0.62, 1.30), (-0.30, -0.36, 1.40)], width=0.035))
    girth = [(0.36 * math.cos(a), -0.30, 1.22 + 0.36 * math.sin(a)) for a in np.linspace(math.radians(-15), math.radians(-165), 9)]
    parts.append(strap("cinch", bodyf, girth, width=0.07, thick=0.008))
    return C.join(parts, "Harness")


def C_dense(pts, n_sub):
    pts = [np.array(p, float) for p in pts]
    dense = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        for k in range(n_sub):
            u = k / n_sub
            dense.append(0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    dense.append(pts[-1])
    return np.array(dense)


# ----------------------------------------------------------------------------
# animation
# ----------------------------------------------------------------------------
class HorseAnim:
    def __init__(self, rig):
        self.rig = rig
        self.th = {}
        self.L = {}
        for b in rig.order:
            v = rig.tail[b] - rig.head[b]
            self.th[b] = math.atan2(v.z, v.y)
            self.L[b] = math.hypot(v.y, v.z)
        self.toe0 = {}
        for sfx in (".L", ".R"):
            self.toe0["F" + sfx] = rig.tail["fhoof" + sfx].y
            self.toe0["H" + sfx] = rig.tail["hhoof" + sfx].y

    @staticmethod
    def dir(a):
        return np.array([math.cos(a), math.sin(a)])

    # --- body -------------------------------------------------------------
    def body(self, local, root_t, root_q=None):
        loc = dict(local)
        if root_q is not None:
            loc["root"] = root_q
        D, Hh = self.rig.solve(local=loc, root_t=root_t)
        return D, Hh

    # --- legs ---------------------------------------------------------------
    def front_stance(self, sfx, D, Hh, chest_pitch, sc_deg, toe_y, eta_off, past_off, k_deg=0.0):
        th, L = self.th, self.L
        sc = "scapula" + sfx
        a_sc = th[sc] + chest_pitch + math.radians(sc_deg)
        top = np.array([Hh[sc].y, Hh[sc].z])
        S = top + L[sc] * self.dir(a_sc)
        eta = th["fhoof" + sfx] + math.radians(eta_off)
        pp = th["fpastern" + sfx] + math.radians(past_off)
        toe = np.array([toe_y, 0.0])
        cor = toe - L["fhoof" + sfx] * self.dir(eta)
        fet = cor - L["fpastern" + sfx] * self.dir(pp)
        krest = th["fcannon" + sfx] - th["radius" + sfx]
        krel = krest + math.radians(k_deg)
        Lr, Lc = L["radius" + sfx], L["fcannon" + sfx]
        ev = np.array([Lr + Lc * math.cos(krel), Lc * math.sin(krel)])
        Leff = float(np.linalg.norm(ev))
        psi = math.atan2(ev[1], ev[0])
        a_h, a_e = C.two_bone_2d(S, fet, L["humerus" + sfx], Leff, +1)
        a_r = a_e - psi
        return [a_sc, a_h, a_r, a_r + krel, pp, eta]

    def hind_stance(self, sfx, D, Hh, toe_y, eta_off, past_off, hflex_deg):
        th, L = self.th, self.L
        fe = "femur" + sfx
        hip = np.array([Hh[fe].y, Hh[fe].z])
        eta = th["hhoof" + sfx] + math.radians(eta_off)
        pp = th["hpastern" + sfx] + math.radians(past_off)
        toe = np.array([toe_y, 0.0])
        cor = toe - L["hhoof" + sfx] * self.dir(eta)
        fet = cor - L["hpastern" + sfx] * self.dir(pp)
        rrest = th["hcannon" + sfx] - th["tibia" + sfx]
        rel = rrest - math.radians(hflex_deg)
        Lt, Lc = L["tibia" + sfx], L["hcannon" + sfx]
        ev = np.array([Lt + Lc * math.cos(rel), Lc * math.sin(rel)])
        Leff = float(np.linalg.norm(ev))
        psi = math.atan2(ev[1], ev[0])
        a_f, a_e = C.two_bone_2d(hip, fet, L[fe], Leff, -1)
        a_t = a_e - psi
        return [a_f, a_t, a_t + rel, pp, eta]

    def leg_world(self, names, angles):
        return {n: C.rx(math.degrees(a - self.th[n])) for n, a in zip(names, angles)}

    def chain_toe(self, names, angles, top):
        p = np.array(top, float)
        for n, a in zip(names, angles):
            p = p + self.L[n] * self.dir(a)
        return p


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def gait_clip(A, name, nframes, onsets, duty, sweep, fwd, body_fn, sc_amp=10.0, swing=None):
    """Generic IK gait.  onsets: dict leg->phase of touchdown. sweep: dict F/H -> stance length.
    fwd: dict F/H -> how far ahead of the rest toe the hoof lands.
    body_fn(phi) -> (local dict, root_t, chest_pitch_rad, pelvis_pitch_rad)."""
    swing = swing or {}
    rig = A.rig
    Fn = {s: [n + s for n in FRONT] for s in (".L", ".R")}
    Hn = {s: [n + s for n in HIND] for s in (".L", ".R")}

    def stance_front(sfx, phi, u):
        loc, rt, cp, pp_ = body_fn(phi)
        D, Hh = A.body(loc, rt)
        d = duty["F"]
        r = u / d
        toe_y = A.toe0["F" + sfx] - fwd["F"] + sweep["F"] * r
        bo = C.smoothstep((r - 0.55) / 0.45)
        eta = 50.0 * bo
        past = -16.0 * math.sin(math.pi * min(r, 1.0)) + 28.0 * bo
        sc = sc_amp * math.sin(2 * math.pi * (u - 0.12))
        return A.front_stance(sfx, D, Hh, cp, sc, toe_y, eta, past), D, Hh

    def stance_hind(sfx, phi, u):
        loc, rt, cp, pp_ = body_fn(phi)
        D, Hh = A.body(loc, rt)
        d = duty["H"]
        r = u / d
        toe_y = A.toe0["H" + sfx] - fwd["H"] + sweep["H"] * r
        bo = C.smoothstep((r - 0.55) / 0.45)
        eta = 45.0 * bo
        past = -14.0 * math.sin(math.pi * min(r, 1.0)) + 25.0 * bo
        hfl = 12.0 * math.sin(math.pi * min(r, 1.0)) - 8.0 * bo
        return A.hind_stance(sfx, D, Hh, toe_y, eta, past, hfl), D, Hh, pp_

    def rel(angles, base):
        out = [wrap(angles[0] - base)]
        for i in range(1, len(angles)):
            out.append(wrap(angles[i] - angles[i - 1]))
        return out

    frames = []
    min_toe = {}
    for fi in range(nframes + 1):
        phi = (fi / nframes) % 1.0
        loc, rt, cp, pelp = body_fn(phi)
        D, Hh = A.body(loc, rt)
        world = {}
        for sfx in (".L", ".R"):
            # ---------------- front
            key = "F" + sfx
            u = (phi - onsets[key]) % 1.0
            d = duty["F"]
            if u < d:
                ang, _, _ = stance_front(sfx, phi, u)
            else:
                s = (u - d) / (1 - d)
                phl = (onsets[key] + d) % 1.0
                pht = onsets[key] % 1.0
                al, Dl, Hl = stance_front(sfx, phl, d - 1e-6)
                at, Dt, Ht = stance_front(sfx, pht, 0.0)
                _, _, cpl, _ = body_fn(phl)
                _, _, cpt, _ = body_fn(pht)
                rl = rel(al, A.th["scapula" + sfx] + cpl)
                rt_ = rel(at, A.th["scapula" + sfx] + cpt)
                sc = sc_amp * math.sin(2 * math.pi * (u - 0.12))
                e = C.smoothstep((s - 0.08) / 0.84)
                r = [a + wrap(b - a) * e for a, b in zip(rl, rt_)]
                r[0] = wrap(A.th["scapula" + sfx] + cp + math.radians(sc) - (A.th["scapula" + sfx] + cp))  # scapula FK
                fb = swing.get("F", {})
                r[2] += math.radians(fb.get("elbow", -40)) * C.bump(s, fb.get("elbow_p", 0.5))
                r[3] += math.radians(fb.get("carpus", 105)) * C.bump(s, fb.get("carpus_p", 0.38))
                r[4] += math.radians(fb.get("fetlock", 55)) * C.bump(s, 0.32)
                r[5] += math.radians(fb.get("coffin", 20)) * C.bump(s, 0.3)
                r[1] += math.radians(fb.get("shoulder", 0)) * C.bump(s, 0.5)
                ang = []
                acc = A.th["scapula" + sfx] + cp
                for v in r:
                    acc = acc + v
                    ang.append(acc)
            world.update(A.leg_world(Fn[sfx], ang))
            top = np.array([Hh["scapula" + sfx].y, Hh["scapula" + sfx].z])
            toe = A.chain_toe(Fn[sfx], ang, top)
            min_toe.setdefault(key, []).append((round(toe[1], 3), "st" if u < d else "sw"))
            # ---------------- hind
            key = "H" + sfx
            u = (phi - onsets[key]) % 1.0
            d = duty["H"]
            if u < d:
                ang, _, _, _ = stance_hind(sfx, phi, u)
            else:
                s = (u - d) / (1 - d)
                phl = (onsets[key] + d) % 1.0
                pht = onsets[key] % 1.0
                al, _, _, ppl = stance_hind(sfx, phl, d - 1e-6)
                at, _, _, ppt = stance_hind(sfx, pht, 0.0)
                rl = rel(al, A.th["femur" + sfx] + ppl)
                rt_ = rel(at, A.th["femur" + sfx] + ppt)
                e = C.smoothstep((s - 0.05) / 0.85)
                r = [a + wrap(b - a) * e for a, b in zip(rl, rt_)]
                hb = swing.get("H", {})
                r[0] += math.radians(hb.get("hip", 8)) * C.bump(s, 0.6) * -1
                r[1] += math.radians(hb.get("stifle", 35)) * C.bump(s, hb.get("p", 0.42))
                r[2] += math.radians(hb.get("hock", -60)) * C.bump(s, hb.get("p", 0.42))
                r[3] += math.radians(hb.get("fetlock", 50)) * C.bump(s, 0.33)
                r[4] += math.radians(hb.get("coffin", 18)) * C.bump(s, 0.3)
                ang = []
                acc = A.th["femur" + sfx] + pelp
                for v in r:
                    acc = acc + v
                    ang.append(acc)
            world.update(A.leg_world(Hn[sfx], ang))
            top = np.array([Hh["femur" + sfx].y, Hh["femur" + sfx].z])
            toe = A.chain_toe(Hn[sfx], ang, top)
            min_toe.setdefault(key, []).append((round(toe[1], 3), "st" if u < d else "sw"))
        D, Hh = rig.solve(local=loc, world=world, root_t=rt)
        frames.append(rig.to_basis(D, rt))
    for k, v in min_toe.items():
        sw = [z for z, t in v if t == "sw"]
        print(f"[{name}] {k} swing toe z min {min(sw):.3f} max {max(sw):.3f}")
    return frames


def gallop_body(phi):
    tau = 2 * math.pi
    bob = 0.040 * math.cos(tau * (phi - 0.86)) + 0.012 * math.cos(2 * tau * (phi - 0.86)) - 0.03
    pitch = 4.0 * math.sin(tau * (phi - 0.46))
    spine = 2.5 * math.cos(tau * (phi - 0.92))
    pelvis = -5.0 * math.cos(tau * (phi - 0.92))
    loc = {
        "root": C.rx(pitch),
        "spine": C.rx(spine),
        "chest": C.rx(-1.0),
        "pelvis": C.rx(pelvis),
        "neck1": C.rx(14 + 9.0 * math.cos(tau * (phi - 0.52))),
        "neck2": C.rx(3 + 4.0 * math.cos(tau * (phi - 0.58))),
        "head": C.rx(-10 - 6.0 * math.cos(tau * (phi - 0.62))),
        "tail1": C.rx(38 + 5 * math.sin(tau * (phi - 0.05))),
        "tail2": C.rx(20 + 7 * math.sin(tau * (phi - 0.15))),
        "tail3": C.rx(12 + 8 * math.sin(tau * (phi - 0.25))),
        "tail4": C.rx(8 + 8 * math.sin(tau * (phi - 0.35))),
    }
    chest_pitch = math.radians(pitch + spine - 1.0)
    pel_pitch = math.radians(pitch + pelvis)
    return loc, (0, 0, bob), chest_pitch, pel_pitch


def canter_body(phi):
    tau = 2 * math.pi
    bob = 0.035 * math.cos(tau * (phi - 0.95)) - 0.02
    pitch = 6.5 * math.sin(tau * (phi - 0.52))
    loc = {
        "root": C.rx(pitch),
        "spine": C.rx(1.5 * math.cos(tau * (phi - 0.9))),
        "pelvis": C.rx(-3.0 * math.cos(tau * (phi - 0.9))),
        "neck1": C.rx(8 + 8.0 * math.cos(tau * (phi - 0.62))),
        "neck2": C.rx(2 + 3.0 * math.cos(tau * (phi - 0.68))),
        "head": C.rx(-6 - 5.0 * math.cos(tau * (phi - 0.7))),
        "tail1": C.rx(24 + 4 * math.sin(tau * (phi - 0.05))),
        "tail2": C.rx(12 + 6 * math.sin(tau * (phi - 0.15))),
        "tail3": C.rx(8 + 6 * math.sin(tau * (phi - 0.25))),
        "tail4": C.rx(5 + 6 * math.sin(tau * (phi - 0.35))),
    }
    sp = 1.5 * math.cos(tau * (phi - 0.9))
    return loc, (0, 0, bob), math.radians(pitch + sp), math.radians(pitch - 3.0 * math.cos(tau * (phi - 0.9)))


def planted_legs(A, loc, rt, cp, pp, extra=None):
    """All four hooves planted at rest positions (IK), used by Idle/Rear."""
    extra = extra or {}
    D, Hh = A.body(loc, rt)
    world = {}
    for sfx in (".L", ".R"):
        if ("F" + sfx) in extra:
            world.update(extra["F" + sfx](D, Hh))
        else:
            ang = A.front_stance(sfx, D, Hh, cp, 0.0, A.toe0["F" + sfx], 0.0, 0.0)
            world.update(A.leg_world([n + sfx for n in FRONT], ang))
        if ("H" + sfx) in extra:
            world.update(extra["H" + sfx](D, Hh))
        else:
            ang = A.hind_stance(sfx, D, Hh, A.toe0["H" + sfx], 0.0, 0.0, 0.0)
            world.update(A.leg_world([n + sfx for n in HIND], ang))
    return world


def idle_clip(A, n=240):
    frames = []
    tau = 2 * math.pi
    for fi in range(n + 1):
        t = (fi / n) % 1.0
        sway = 0.012 * math.sin(tau * t)
        breathe = 0.004 * math.sin(tau * t * 4)
        graze = 0.5 - 0.5 * math.cos(tau * t)  # head lowers mid-loop
        loc = {
            "root": C.rx(0.6 * math.sin(tau * t * 4)) @ C.ry(0.8 * math.sin(tau * t)),
            "neck1": C.rx(-2 + 10 * graze + 1.0 * math.sin(tau * t * 3)),
            "neck2": C.rx(4 * graze) @ C.rz(6 * math.sin(tau * t * 2)),
            "head": C.rx(-4 + 6 * graze + 2 * math.sin(tau * (t * 5 + 0.2))) @ C.rz(4 * math.sin(tau * (t * 2 - 0.1))),
            "tail1": C.rx(4 + 2 * math.sin(tau * t * 2)) @ C.ry(10 * math.sin(tau * t * 3)),
            "tail2": C.ry(12 * math.sin(tau * (t * 3 - 0.08))),
            "tail3": C.ry(14 * math.sin(tau * (t * 3 - 0.16))),
            "tail4": C.ry(14 * math.sin(tau * (t * 3 - 0.24))),
        }
        rt = (sway, 0, breathe)
        cp = math.radians(0.6 * math.sin(tau * t * 4))
        world = planted_legs(A, loc, rt, cp, cp)
        D, Hh = A.rig.solve(local=loc, world=world, root_t=rt)
        frames.append(A.rig.to_basis(D, rt))
    return frames


def fk_frames(A, n, times, poses, root_fn):
    """Keyposed FK clip. poses: list of dict bone -> (x,y,z) degrees (rest-frame local).
    root_fn(pose) -> (root_t, root_q)."""
    frames = []
    for fi in range(n + 1):
        t = fi / C.FPS
        p = C.keyposes(times, poses, t)
        loc = {}
        for b, v in p.items():
            if b.startswith("_"):
                continue
            loc[b] = C.eul(*v)
        rt, rq = root_fn(p)
        loc["root"] = rq @ loc.get("root", Quaternion())
        D, Hh = A.rig.solve(local=loc, root_t=rt)
        frames.append(A.rig.to_basis(D, rt))
    return frames


def legs_pose(front=(0, 0, 0, 0, 0), hind=(0, 0, 0, 0), side=None, splay=0.0):
    """Relative sagittal flexions. front: shoulder(humerus), elbow(radius), carpus(cannon), fetlock, coffin.
    hind: hip(femur), stifle(tibia), hock(cannon), fetlock.  Degrees about X (rest frame)."""
    out = {}
    for sfx in ((".L", ".R") if side is None else (side,)):
        sp = splay if sfx == ".L" else -splay
        out["humerus" + sfx] = (front[0], 0, sp)
        out["radius" + sfx] = (front[1], 0, 0)
        out["fcannon" + sfx] = (front[2], 0, 0)
        out["fpastern" + sfx] = (front[3], 0, 0)
        out["fhoof" + sfx] = (front[4], 0, 0)
        out["femur" + sfx] = (hind[0], 0, sp)
        out["tibia" + sfx] = (hind[1], 0, 0)
        out["hcannon" + sfx] = (hind[2], 0, 0)
        out["hpastern" + sfx] = (hind[3], 0, 0)
    return out


def fall_clip(A):
    """Front legs buckle, nose ploughs down, body rolls onto its left side."""
    def P(d, **kw):
        out = dict(d)
        out.update(kw)
        return out

    k0 = P(legs_pose((-8, -6, 20, 10, 0), (10, 10, -15, 10)),
           _t=(0, 0, 0), _r=(0, 0, 0), neck1=(14, 0, 0), neck2=(3, 0, 0), head=(-10, 0, 0),
           tail1=(35, 0, 0), tail2=(18, 0, 0), tail3=(10, 0, 0), tail4=(6, 0, 0))
    k1 = P(legs_pose((-25, 40, 115, 60, 20), (30, 5, -20, 20)),
           _t=(0, 0.0, -0.30), _r=(24, 0, 0), neck1=(28, 0, 0), neck2=(8, 0, 0), head=(-4, 0, 0),
           tail1=(50, 0, 0), tail2=(20, 0, 0), tail3=(10, 0, 0), tail4=(8, 0, 0), spine=(4, 0, 0), pelvis=(-6, 0, 0))
    k2 = P(legs_pose((-45, 55, 120, 50, 20), (40, -10, 0, 10), splay=10),
           _t=(0.10, 0.0, -0.62), _r=(30, 40, 0), neck1=(25, 0, -15), neck2=(-5, 0, -10), head=(-25, 0, 0),
           tail1=(55, 25, 0), tail2=(25, 10, 0), tail3=(10, 0, 0), tail4=(5, 0, 0), spine=(3, 0, 0))
    k3 = P(legs_pose((-15, 15, 35, 15, 5), (15, -20, 20, 10), splay=25),
           _t=(0.30, 0.0, -0.86), _r=(4, 86, 0), neck1=(-8, 0, -12), neck2=(-10, 0, -6), head=(-18, 0, 4),
           tail1=(10, 30, 0), tail2=(0, 12, 0), tail3=(0, 0, 0), tail4=(0, 0, 0))
    k4 = P(legs_pose((-8, 10, 25, 10, 5), (10, -12, 15, 8), splay=22),
           _t=(0.31, 0.0, -0.88), _r=(2, 90, 0), neck1=(-10, 0, -10), neck2=(-10, 0, -5), head=(-18, 0, 6),
           tail1=(8, 32, 0), tail2=(0, 10, 0))

    def root_fn(p):
        t = p.get("_t", (0, 0, 0))
        r = p.get("_r", (0, 0, 0))
        return (t[0], t[1], t[2]), C.ry(r[1]) @ C.rx(r[0])

    return fk_frames(A, 90, [0.0, 0.33, 0.72, 1.12, 1.5], [k0, k1, k2, k3, k4], root_fn)


def rear_clip(A, n=120, pivot=(0.62, 0.55)):
    """Rear up on the hind legs (hind hooves planted by IK), paw the air, come down."""
    front_rest = (0, 0, 0, 0, 0)
    keys_t = [0.0, 0.35, 0.8, 1.15, 1.45, 2.0]
    pitch = [0, 6, -40, -44, -38, 0]
    tuck = [0, 0.1, 1.0, 1.0, 0.9, 0]
    neck = [0, 8, -14, -10, -12, 0]
    frames = []
    pivot = np.array(pivot)  # y,z pivot near the hocks
    for fi in range(n + 1):
        t = fi / C.FPS

        def interp(vals):
            return C.keyposes(keys_t, [{"v": (v,)} for v in vals], t)["v"][0]

        pt = interp(pitch)
        tk = min(max(interp(tuck), 0), 1)
        nk = interp(neck)
        paw = math.sin(2 * math.pi * (t - 0.8) / 0.5) if 0.8 < t < 1.45 else 0.0
        a = math.radians(pt)
        rh = np.array([A.rig.head["root"].y, A.rig.head["root"].z])
        v = rh - pivot
        rv = np.array([v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)])
        crouch = 0.12 * math.sin(math.pi * min(max(t / 0.8, 0), 1)) if t < 0.8 else 0.0
        nr = pivot + rv
        rt = (0.0, nr[0] - rh[0], nr[1] - rh[1] - crouch)
        loc = {
            "root": C.rx(pt),
            "neck1": C.rx(nk),
            "neck2": C.rx(nk * 0.4),
            "head": C.rx(-nk * 0.6 + 8 * tk),
            "tail1": C.rx(-10 * tk),
            "pelvis": C.rx(6 * tk),
        }
        for sfx, ph in ((".L", 0.0), (".R", 0.5)):
            pw = paw if sfx == ".L" else math.sin(2 * math.pi * ((t - 0.8) / 0.5 - 0.5)) * (0.8 < t < 1.45)
            loc["humerus" + sfx] = C.rx(-35 * tk - 15 * pw * tk)
            loc["radius" + sfx] = C.rx(-45 * tk + 20 * pw * tk)
            loc["fcannon" + sfx] = C.rx(110 * tk - 30 * pw * tk)
            loc["fpastern" + sfx] = C.rx(40 * tk)
        cp = math.radians(pt)
        D, Hh = A.body(loc, rt)
        world = {}
        for sfx in (".L", ".R"):
            ang = A.hind_stance(sfx, D, Hh, A.toe0["H" + sfx], 0.0, -10 * tk, 15 * tk)
            world.update(A.leg_world([nm + sfx for nm in HIND], ang))
        # blend front legs from planted (IK) at start/end to FK tuck
        if tk < 0.999:
            fw = {}
            for sfx in (".L", ".R"):
                ang = A.front_stance(sfx, D, Hh, cp, 0.0, A.toe0["F" + sfx], 0.0, 0.0)
                fw.update(A.leg_world([nm + sfx for nm in FRONT], ang))
            Dfk, _ = A.rig.solve(local=loc, world=world, root_t=rt)
            for b, q in fw.items():
                world[b] = q.slerp(Dfk[b], tk) if tk > 0 else q
            # children of blended bones must be world-specified too
        D, Hh = A.rig.solve(local=loc, world=world, root_t=rt)
        frames.append(A.rig.to_basis(D, rt))
    return frames


# ============================================================================
# breeds (the coach team): `-- --breed clydesdale|clevelandbay|thoroughbred`
# The base horse above stays as it is for horse.glb (enemy riders). A breed
# warps its skeleton and prims to the historian's proportions, then adds its
# own detail: feather, head profile, markings and a draught harness.
# ============================================================================
ZB0, ZW0, LEN0, HEAD0 = 0.86, 1.61, 1.67, 0.68  # base: belly line, withers, shoulder->buttock, poll->muzzle
CHAIN = ("neck1", "neck2", "head", "tail1", "tail2", "tail3", "tail4")
LOWER = ("fcannon", "fpastern", "hcannon", "hpastern")
BLABELS = LABELS + ["feather"]

# H: withers (m); leg: girth->ground / H; length: shoulder->buttock (m); wide/hip: barrel/hip width vs
# base; head (m); head_w: lateral; neck: length factor; nthick: (lateral, depth); nang: neck1/neck2/head
# angle change (deg, - = more upright); arm/bone/hoof: forearm, cannon, hoof size vs base (base cannon
# capsule 8 cm, hoof 12.6 cm); mane: (lateral, depth); roman/dish: head profile; tuck: belly tuck.
BREEDS = {
    "clydesdale": dict(
        H=1.672, leg=0.48, length=1.87, wide=1.25, hip=1.34, head=0.70, head_w=1.10, neck=1.04,
        nthick=(1.26, 1.28), nang=(-7, -4, 2), arm=1.45, bone=1.19, hoof=1.50, ear=1.0, eye=1.12, muzzle=1.14,
        tail=0.82, tthick=1.35, mane=(1.3, 1.12), roman=1.6, dish=0.0, tuck=0.0, feather=True, crest=0.04, withers=0.0,
        breeching=True, rough=0.74, tris=10500, vox=0.0085,
        # short, round and high: long stance, high knee, bouncy
        gait=dict(duty=(0.34, 0.36), sweep=0.9, fwd=0.42, sc=13.0, bob=1.4),
        swing={"F": {"carpus": 130, "elbow": -50, "fetlock": 72, "shoulder": 6}, "H": {"stifle": 36, "hock": -80, "fetlock": 64}},
        pal=dict(coat="5E3520", points="1B1512", mane="15100D", white="ECE6DA", feather="EEE4D0", dirt="A89679",
                 roan="8C7466", skin="C9A09A", hoof="C4B08E")),
    "clevelandbay": dict(
        H=1.625, leg=0.52, length=1.73, wide=1.03, hip=1.11, head=0.62, head_w=1.02, neck=1.05,
        nthick=(1.06, 1.05), nang=(-2, 0, 0), arm=1.06, bone=0.94, hoof=1.19, ear=1.0, eye=1.0, muzzle=1.0,
        tail=1.05, tthick=1.12, mane=(1.3, 1.1), roman=0.35, dish=0.0, tuck=0.0, feather=False, crest=0.0, withers=0.0,
        breeching=False, rough=0.66, tris=9200, vox=0.0095,
        gait=dict(duty=(0.28, 0.30), sweep=1.0, fwd=0.42, sc=11.0, bob=1.0),
        swing={"F": {"carpus": 100, "elbow": -40, "fetlock": 50}, "H": {"stifle": 30, "hock": -62, "fetlock": 55}},
        pal=dict(coat="6E3B1F", points="17120F", mane="14100D", hoof="26221F")),
    "thoroughbred": dict(
        H=1.595, leg=0.56, length=1.62, wide=0.87, hip=0.93, head=0.55, head_w=0.94, neck=1.28,
        nthick=(0.84, 0.88), nang=(8, 4, -4), arm=0.86, bone=0.78, hoof=1.0, ear=0.82, eye=1.16, muzzle=0.84,
        tail=1.0, tthick=0.78, mane=(0.7, 0.8), roman=0.0, dish=1.0, tuck=1.0, feather=False, crest=0.0, withers=0.05,
        breeching=False, rough=0.52, tris=9200, vox=0.0095,
        # long, low and reaching: short stance, long sweep, flat knee
        gait=dict(duty=(0.24, 0.26), sweep=1.15, fwd=0.50, sc=9.0, bob=0.8),
        swing={"F": {"carpus": 76, "elbow": -32, "fetlock": 52, "shoulder": 12}, "H": {"stifle": 28, "hock": -54, "fetlock": 48}},
        # a matched chestnut pair: self-coloured legs, flaxen-tinged mane
        pal=dict(coat="9A4E22", points="7A3A1A", mane="A5602E", white="EEE8DE", skin="C49A92", hoof="3A3028")),
}


def hexc(h):
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def seg_d(p, a, b):
    ab = b - a
    t = min(max(float((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0), 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


class Warp:
    """Base-horse space -> breed space. Trunk and legs by a piecewise warp (leg
    length, body depth/length/width); neck, head and tail by their bone chains."""

    def __init__(self, B):
        self.B = B
        self.lz = B["leg"] * B["H"]
        self.legf = self.lz / ZB0
        self.dep = (B["H"] - self.lz) / (ZW0 - ZB0)
        self.sy = B["length"] / LEN0
        self.sh = B["head"] / HEAD0
        base = bone_list()
        self.b0 = {n: (np.array(h, float), np.array(t, float)) for n, h, t, _, _ in base}
        self.b1 = {n: (self.warp(h), self.warp(t)) for n, h, t, _, _ in base if n not in CHAIN}
        self._chain(("neck1", "neck2", "head"), self.b1["chest"][1], (B["neck"], B["neck"], self.sh), B["nang"])
        self._chain(("tail1", "tail2", "tail3", "tail4"), self.warp(self.b0["tail1"][0]), (B["tail"],) * 4, (-15, -8, -4, 0))
        self.bones = [(n, tuple(self.b1[n][0]), tuple(self.b1[n][1]), par, con) for n, _, _, par, con in base]

    def wz(self, z):
        return z * self.legf if z < ZB0 else self.lz + (z - ZB0) * self.dep

    def fx(self, y):  # lateral scale, barrel -> hips
        return self.B["wide"] + (self.B["hip"] - self.B["wide"]) * C.smoothstep((y + 0.1) / 0.5)

    def wy(self, y, z):  # legs keep their own proportions below the belly line
        ya = -0.56 if y < 0.05 else 0.64
        t = C.smoothstep((ZB0 + 0.1 - z) / 0.25)
        return (1 - t) * self.sy * y + t * (self.sy * ya + (y - ya) * self.legf)

    def warp(self, p):
        x, y, z = (float(v) for v in p)
        return np.array([x * self.fx(y), self.wy(y, z), self.wz(z)])

    def _chain(self, names, start, scales, angs):
        p = np.array(start, float)
        for n, s, da in zip(names, scales, angs):
            h0, t0 = self.b0[n]
            d = t0 - h0
            a = math.atan2(d[2], d[1]) + math.radians(da)
            L = math.hypot(d[1], d[2]) * s
            t = p + np.array([0.0, L * math.cos(a), L * math.sin(a)])
            self.b1[n] = (p.copy(), t)
            p = t

    def chain_params(self, n):
        if n.startswith("neck"):
            return self.B["nthick"][1], self.B["nthick"][0]
        if n == "head":
            return self.sh, self.sh * self.B["head_w"]
        return self.B["tthick"], self.B["tthick"]

    @staticmethod
    def _frame(h, t):
        d = (t - h)[1:]
        L = float(np.hypot(*d))
        u = d / L
        return L, u, np.array([-u[1], u[0]])

    def map_chain(self, p, n):
        sp, lat = self.chain_params(n)
        h0, t0 = self.b0[n]
        h1, t1 = self.b1[n]
        L0, u0, v0 = self._frame(h0, t0)
        L1, u1, v1 = self._frame(h1, t1)
        q = (np.asarray(p, float) - h0)[1:]
        yz = h1[1:] + (q @ u0) * (L1 / L0) * u1 + (q @ v0) * sp * v1
        return np.array([float(p[0]) * lat, yz[0], yz[1]])

    def map_pt(self, p, bones=None):
        p = np.asarray(p, float)
        cand = [b for b in (bones or self.b0) if b in self.b0] or list(self.b0)
        best = min(cand, key=lambda b: seg_d(p, *self.b0[b]))
        return self.map_chain(p, best) if best in CHAIN else self.warp(p)

    def map_body(self, p):  # harness points: trunk, neck and head only
        return self.map_pt(p, ["root", "pelvis", "spine", "chest", "neck1", "neck2", "head", "tail1"])

    def factors(self, pr, c):
        """Per-axis radius scale (x, y, z) for a base prim."""
        B = self.B
        if pr.label == "mane":
            return B["mane"][0], B["mane"][1], B["mane"][1]
        if pr.label == "tail":
            return (B["tthick"],) * 3
        b = (pr.bones[0] if pr.bones else "root").split(".")[0]
        if b.startswith("neck"):
            lat, per = B["nthick"]
            return lat, per, per
        if b == "head":
            f = {"ear": B["ear"], "eye": B["eye"], "muzzle": B["muzzle"], "nostril": B["muzzle"]}.get(pr.label, 1.0)
            return self.sh * B["head_w"] * f, self.sh * f, self.sh * f
        if b in ("radius", "tibia"):
            return B["arm"], B["arm"], self.legf
        if b in LOWER:
            return B["bone"], B["bone"], self.legf
        if b in ("fhoof", "hhoof"):
            return B["hoof"], B["hoof"], self.legf
        return self.fx(c[1]), self.sy, self.dep


def map_prim(W, pr):
    fx, fy, fz = W.factors(pr, pr.center)
    if pr.kind == "ell":
        return C.ell(W.map_pt(pr.c, pr.bones), pr.r * np.array([fx, fy, fz]), pr.label, pr.bones, k=pr.k,
                     scale=pr.scale, rot=pr.rot)
    d = pr.b - pr.a
    d = np.abs(d / (np.linalg.norm(d) + 1e-9))
    f2 = (d[2] * fy + d[1] * fz) / max(d[1] + d[2], 1e-6)  # radius scale across the axis, in the sagittal plane
    sc = (np.ones(3) if pr.scale is None else pr.scale) * np.array([fx / f2, 1.0, 1.0])
    a, b = W.map_pt(pr.a, pr.bones), W.map_pt(pr.b, pr.bones)
    if pr.label == "ear":  # ear length follows the breed too
        b = a + (b - a) * W.B["ear"]
    return C.cone(a, b, pr.ra * f2, pr.rb * f2, pr.label, pr.bones, k=pr.k, scale=sc)


def head_frame(W):
    """Head bone (poll->muzzle) axis u, face-front direction f, length."""
    h, t = W.b1["head"]
    d = t - h
    L = float(np.linalg.norm(d))
    u = d / L
    f = np.array([0.0, u[2], -u[1]])  # forward-up: the nasal line
    return h, u, f, L


def frame_rot(u, f):
    return np.array([[1.0, 0, 0], u, f])


def feather_prims(W):
    """1870s feather: silky hair down the back of the cannon, belling over the
    fetlock and falling in locks over the coronet; the toe stays clear."""
    P = []
    rc = 0.04 * W.B["bone"]
    rh = 0.063 * W.B["hoof"]
    rng = np.random.RandomState(5)
    for sfx in (".L", ".R"):
        for can, pas, hf in (("fcannon", "fpastern", "fhoof"), ("hcannon", "hpastern", "hhoof")):
            K0 = W.b1[can + sfx][0]
            F = W.b1[pas + sfx][0]
            Co = W.b1[hf + sfx][0]
            bk = np.array([0.0, 1.0, 0.0])
            hind = can[0] == "h"
            P.append(C.cone(K0 + bk * rc * 0.5 + [0, 0, -0.05 if hind else -0.07], F + bk * rc * 1.1 + [0, 0, 0.03],
                            rc * 0.7, rc * 1.3, "feather", [can + sfx], k=0.04, scale=(1.25, 1, 1)))
            P.append(C.ell(F + bk * rc * 0.5, (rc * 1.2, rc * 1.3, rc * 1.4), "feather", [pas + sfx, can + sfx], k=0.04))
            # one continuous skirt flaring from the fetlock to just above the ground
            sk = np.array([Co[0], Co[1] + rh * 0.55, 0.02])  # set back so the toe shows
            P.append(C.cone(F + bk * rc * 0.5, sk, rc * 1.2, rh * 1.1, "feather", [pas + sfx, hf + sfx], k=0.04,
                            scale=(1.05, 1, 1)))
            # a row of locks widening as they fall, fanning over the heel and quarters; the toe stays clear
            for thd in range(-160, 161, 40):
                if abs(thd) < 62:
                    continue
                th = math.radians(thd + 8 * (rng.rand() - 0.5))
                dv = np.array([math.sin(th), -math.cos(th), 0.0])  # th=0 -> toe
                top = F + dv * rc * 1.0 + [0, 0, -0.01]
                bot = np.array([Co[0], Co[1], 0.02 + 0.02 * rng.rand()]) + dv * rh * (1.12 + 0.06 * rng.rand())
                P.append(C.cone(top, bot, 0.012, 0.022, "feather", [pas + sfx, hf + sfx], k=0.03))
    return P


def breed_prims(W):
    B = W.B
    base = body_prims()
    body = [p for p in base if not p.sub]
    cut = [p for p in base if p.sub]
    out = [map_prim(W, p) for p in body]
    h, u, f, L = head_frame(W)
    R = frame_rot(u, f)
    # fill the throatlatch where the rescaled head meets the neck
    extra = [C.ell(W.map_pt((0, -1.02, 1.80), ["neck2"]) * 0.5 + W.map_pt((0, -1.1, 1.80), ["head"]) * 0.5,
                   (0.075 * B["nthick"][0], 0.08, 0.085 * B["nthick"][1]), "coat", ["neck2", "head"], k=0.07)]
    if B["roman"]:  # slightly convex nasal line
        s = W.sh * B["roman"]
        extra.append(C.ell(h + u * 0.56 * L + f * 0.092 * W.sh, (0.052 * W.sh, 0.15 * W.sh, 0.045 * s), "coat", ["head"],
                           k=0.05, rot=R))
    # head bone structure (head frame: x lateral, u poll->muzzle, f nasal line)
    sh = W.sh
    X = np.array([1.0, 0, 0])
    MH = lambda p: W.map_pt(p, ["head"])
    cuts = []
    for s_ in (1, -1):
        eye = MH((0.095 * s_, -1.215, 1.93))
        extra.append(C.ell(h + u * 0.30 * L - f * 0.045 * sh + X * s_ * 0.07 * sh, (0.035 * sh, 0.09 * sh, 0.075 * sh),
                           "coat", ["head"], k=0.03, rot=R))  # masseter
        extra.append(C.cone(eye - f * 0.035 * sh - u * 0.01, h + u * 0.45 * L - f * 0.03 * sh + X * s_ * 0.078 * sh,
                            0.012 * sh, 0.009 * sh, "coat", ["head"], k=0.02))  # facial crest
        extra.append(C.ell(eye + f * 0.03 * sh - X * s_ * 0.012, (0.025 * sh,) * 3, "coat", ["head"], k=0.02))  # brow
        cuts.append(C.ell(eye + f * 0.055 * sh - u * 0.05 * sh + X * s_ * 0.004, (0.022 * sh, 0.03 * sh, 0.02 * sh), "cut", [],
                          sub=True, k=0.02, rot=R))  # hollow above the eye
        nos = MH((0.042 * s_, -1.505, 1.605))
        for du in (-0.014, 0.012):  # flared rims
            extra.append(C.ell(nos + u * du * sh + f * 0.006 + X * s_ * 0.006, (0.012 * sh, 0.014 * sh, 0.024 * sh) ,
                               "muzzle", ["head"], k=0.012, rot=R))
        cuts.append(C.ell(nos + X * s_ * 0.016 * sh + u * 0.004, (0.012 * sh, 0.009 * sh, 0.017 * sh), "cut", [],
                          sub=True, k=0.006, rot=R))  # the opening
        cuts.append(C.ell(W.map_pt((0.085 * s_ * B["nthick"][0], -1.07, 1.77), ["neck2"]), (0.025, 0.035, 0.07), "cut", [],
                          sub=True, k=0.03))  # groove behind the jaw
    if B["crest"]:  # arched crest along the top of the neck
        for n_, t_ in (("neck1", 0.55), ("neck2", 0.35)):
            hh, tt = W.b1[n_]
            d = tt - hh
            up = np.array([0.0, -d[2], d[1]]) / np.linalg.norm(d)
            if up[2] < 0:
                up = -up
            c = hh + d * t_ + up * (0.10 * B["nthick"][1] + B["crest"] * 0.5)
            extra.append(C.ell(c, (0.06 * B["nthick"][0], 0.2, 0.06 + B["crest"]), "coat", ["neck1", "neck2"], k=0.07))
    if B["withers"]:  # higher, sharper withers
        ch = W.b1["chest"][0]
        extra.append(C.ell((0, ch[1] - 0.09, W.wz(1.52) + B["withers"] * 0.6), (0.07, 0.22, 0.10), "coat", ["chest", "spine"], k=0.08))
    if B["feather"]:
        extra += feather_prims(W)
    dish, tuck = cuts, []
    if B["dish"]:  # a slight dish below the eyes
        dish.append(C.ell(h + u * 0.62 * L + f * (0.108 * W.sh + 0.03), (0.07, 0.11, 0.035), "cut", [], sub=True,
                          k=0.03, rot=R))
    if B["tuck"]:  # tucked-up belly toward the stifle
        tuck.append(C.ell((0, W.wy(0.34, 0.9), W.wz(0.8)), (0.22, 0.30, 0.14), "cut", [], sub=True, k=0.12))
    # the first 17 prims of body_prims() are the trunk: the tuck cuts only those
    return out[:17] + tuck + out[17:] + extra + dish + cut


# ----------------------------------------------------------------------------
# breed colour: coat, points, markings
# ----------------------------------------------------------------------------
def breed_color(prims, W, name):
    B = W.B
    pal = {k: hexc(v) for k, v in B["pal"].items()}
    kz = W.b1["fcannon.L"][0][2]
    hz = W.b1["hcannon.L"][0][2]
    fz = W.b1["fpastern.L"][0][2]
    ylegs = 0.5 * (W.b1["fcannon.L"][0][1] + W.b1["hcannon.L"][0][1])
    h, u, f, L = head_frame(W)
    nonsub = [p for p in prims if not p.sub]
    star_c = surf_pt(lambda p: C.eval_sdf([q for q in prims if not q.sub], p), h + u * 0.22 * L + f * 0.2)
    nuts = []
    for sfx, s in ((".L", 1), (".R", -1)):
        k = W.b1["fcannon" + sfx][0]
        nuts.append(np.array([k[0] - s * 0.045 * B["arm"], k[1], k[2] + 0.1 * W.legf]))
        k = W.b1["hcannon" + sfx][0]
        nuts.append(np.array([k[0] - s * 0.04 * B["bone"], k[1] - 0.02, k[2] - 0.05 * W.legf]))

    def mix(c, col, w):
        w = np.clip(w, 0, 1)[:, None]
        return c * (1 - w) + np.asarray(col) * w

    def fn(P, N, ex):
        lw = C.label_weights(prims, P, BLABELS, tau=0.01)
        n1 = C.fbm(P * np.array([1.0, 0.22, 1.0]), 24.0, 3, seed=3)  # hair grain along the body
        n2 = C.fbm(P, 5.0, 3, seed=7)
        n3 = C.fbm(P, 14.0, 2, seed=17)
        z = P[:, 2]
        c = np.tile(pal["coat"], (len(P), 1))
        c *= (0.9 + 0.16 * n2)[:, None] * (0.95 + 0.1 * n1)[:, None]
        # bays: sun-faded topline, darker lower barrel, a lighter soft belly and flank
        top = np.clip(N[:, 2], 0, 1)
        c *= (1.0 + 0.10 * top * (z > W.lz))[:, None]
        c *= (1.0 - 0.08 * np.clip(-N[:, 2], 0, 1) * (z > W.lz * 0.95))[:, None]
        # black points: lower legs to above knee/hock
        front = P[:, 1] < ylegs
        jz = np.where(front, kz, hz)
        pts = ss((jz + 0.10 + 0.05 * (n3 - 0.5) - z) / 0.16)
        pcol = pal["points"] * (0.85 + 0.3 * n1)[:, None]
        c = mix(c, pcol, pts)
        # ear rims and muzzle go dark on a bay
        et = lw["ear"] * ss((P @ np.array([0, 0.0, 1.0]) - (W.b1["head"][0][2] + 0.10 * W.sh)) / 0.08)
        c = mix(c, pal["points"], et)
        c = mix(c, pal["points"] * 1.5, lw["muzzle"] * 0.8)
        # chestnuts: small horny patches inside the forearm above the knee, and inside the hock
        for cp in nuts:
            dn = np.linalg.norm((P - cp) * np.array([1.0, 1.3, 0.75]), axis=1)
            c = mix(c, np.array([0.13, 0.11, 0.09]) * (0.8 + 0.4 * n3)[:, None], ss((0.02 - dn) / 0.006))
        # ---- face frame (for blaze, star, snip)
        q = P - h
        t = (q @ u) / L
        fr = N @ f
        radial = np.linalg.norm(q - np.outer(q @ u, u), axis=1)
        onface = ss(((q @ f) + 0.01 * W.sh) / 0.02) * ss((0.2 * W.sh - radial) / 0.04)  # front of the head only
        white = np.zeros(len(P))
        if name == "clydesdale":
            # wide blaze spilling over the nose into a bald-ish muzzle
            w = (0.035 + 0.062 * np.clip(t, 0, 1.2)) * W.sh * (0.85 + 0.35 * n3)
            face = ss((fr + 0.25) / 0.3) * ss((t - 0.02) / 0.06) * onface
            bald = ss((t - 0.92) / 0.1) * ss((fr + 0.75) / 0.3) * ss((t - 0.5) / 0.1) * (lw["muzzle"] + lw["nostril"] + onface > 0.3)
            white = np.maximum(white, ss((w - np.abs(P[:, 0])) / 0.012) * face)
            white = np.maximum(white, bald * ss((0.10 * W.sh - np.abs(P[:, 0])) / 0.03))
            # four high stockings: chrome white past the knee and hock
            st = ss((jz + np.where(front, 0.12, 0.10) * W.legf + 0.09 * (n3 - 0.5) + 0.03 * (n2 - 0.5) - z) / 0.035)
            white = np.maximum(white, st * (z < W.lz))
            # roan splashing on the belly and lower flank
            under = ss((-N[:, 2] - 0.05) / 0.4) * ss((W.lz + 0.28 - z) / 0.1) * (z > W.lz - 0.05)
            under *= ss((np.abs(P[:, 1] - W.wy(-0.1, 1.0)) < 0.55) * 1.0)
            flk = ss((C.value_noise3(P * np.array([1.0, 0.5, 1.0]), 220.0, seed=21) - 0.5) / 0.15) * (0.6 + 0.4 * n3)
            patch = ss((C.fbm(P, 7.0, 2, seed=23) - 0.35) / 0.3)
            c = mix(c, pal["roan"] * (0.85 + 0.25 * n1)[:, None], under * (0.35 + 0.45 * patch))
            c = mix(c, pal["white"] * 0.9, under * patch * flk * 0.55)
        elif name == "thoroughbred":
            # star, a snip between the nostrils and one near-hind sock
            star = ss((0.03 - np.linalg.norm((P - star_c) * np.array([1.0, 0.8, 0.8]), axis=1) * (0.85 + 0.3 * n3)) / 0.008)
            snip = ss((t - 0.9) / 0.03) * ss((1.12 - t) / 0.03) * ss((0.02 - np.abs(P[:, 0])) / 0.006) * ss((fr + 0.5) / 0.3) * onface
            sock = (P[:, 0] > 0) & (~front)
            sk = ss((fz + 0.07 * W.legf + 0.02 * (n2 - 0.5) - z) / 0.02) * sock
            white = np.maximum(np.maximum(star, snip), sk)
        wcol = pal.get("white", np.ones(3)) * (0.94 + 0.08 * n1)[:, None]
        c = mix(c, wcol, white * (lw["mane"] + lw["tail"] < 0.5))
        # pink-grey skin shows through white on the muzzle
        if "skin" in pal:
            mz = lw["muzzle"] + lw["nostril"] * 0.5
            mott = (C.value_noise3(P, 90.0, seed=9) > 0.62) * 0.5
            c = mix(c, pal["skin"] * (1 - mott)[:, None] + pal["points"] * mott[:, None], mz * white * 0.85)
        # feather: silky, whiter at the top, dirtier at the ground, streaked
        if "feather" in pal:
            fv = lw["feather"]
            streak = C.fbm(P * np.array([4.0, 4.0, 0.5]), 60.0, 2, seed=31)
            fcol = pal["feather"] * (1 - ss((0.10 - z) / 0.10))[:, None] + pal["dirt"] * ss((0.10 - z) / 0.10)[:, None]
            fcol = fcol * (0.82 + 0.3 * streak)[:, None]
            c = mix(c, fcol, fv)
        # mane and tail
        hair = np.clip(lw["mane"] + lw["tail"], 0, 1)
        streak = C.fbm(P * np.array([6.0, 1.0, 0.35]), 30.0, 2, seed=11)
        c = mix(c, pal["mane"] * (0.75 + 0.55 * streak)[:, None], hair)
        # hooves: horn with growth lines; pale under a white leg
        hv = lw["hoof"]
        rings = 0.96 + 0.04 * np.sin(z * 420.0 + 3 * n2)
        hc = pal["hoof"] * rings[:, None] * (0.9 + 0.2 * C.fbm(P * np.array([6, 6, 1.0]), 40.0, 2, seed=41))[:, None]
        if name == "thoroughbred":
            pale = ((P[:, 0] > 0) & (~front)).astype(float)
            hc = hc * (1 - pale[:, None]) + hexc("B8A07C") * rings[:, None] * pale[:, None]
        c = mix(c, hc, hv)
        c = mix(c, np.array([0.035, 0.022, 0.016]), lw["eye"])
        c = mix(c, np.array([0.05, 0.035, 0.03]), lw["nostril"] * 0.9)
        # shading baked from the fine SDF: contact AO, broad AO, and muscle definition
        ao = C.sdf_ao(nonsub, P, N, steps=5, dist=0.026)
        ao2 = C.sdf_ao(nonsub, P, N, steps=3, dist=0.07, strength=0.6)
        e = 0.018
        d0 = C.eval_sdf(nonsub, P)
        lap = sum(C.eval_sdf(nonsub, P + np.eye(3)[i] * e) + C.eval_sdf(nonsub, P - np.eye(3)[i] * e) for i in range(3))
        lap = (lap - 6 * d0) / (e * e)
        cv = np.clip((lap - 9.0) / 25.0, -1, 1) * (z > W.lz * 0.9)
        c *= (1.0 + 0.07 * cv)[:, None]
        shade = (0.45 + 0.55 * ao ** 1.2) * (0.8 + 0.2 * ao2)
        fw = np.clip(lw["feather"], 0, 1)  # silky white hair: soft occlusion only
        shade = shade * (1 - fw) + (0.72 + 0.28 * ao) * fw
        c *= shade[:, None]
        return c

    return fn


# ----------------------------------------------------------------------------
# draught harness: collar + hames, blinkered bridle, pad, crupper, traces,
# and on the wheelers breeching. Solid parts are one SDF mesh with a baked
# texture; straps and hardware use flat swatches in the same texture.
# ----------------------------------------------------------------------------
SW = {"leather": 0.125, "patent": 0.375, "brass": 0.625, "steel": 0.875}  # swatch rows (v) at u 0.94..1
HCOL = dict(leather="221C17", patent="121110", brass="9C7A3A", steel="3A3A3C", pad="C9B68F", hame="2A2A2A")


def swatch(ob, kind):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = np.tile(np.array([0.97, SW[kind]], dtype=np.float32), len(me.loops))
    me.uv_layers.active.data.foreach_set("uv", uv)
    return ob


def basis(axis):
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    t = np.array([0, 0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0, 0])
    b1 = np.cross(a, t)
    b1 /= np.linalg.norm(b1)
    return a, b1, np.cross(a, b1)


def ring(name, c, axis, r, tube=0.005, n=8):
    a, b1, b2 = basis(axis)
    pts = [tuple(np.asarray(c) + r * (math.cos(t) * b1 + math.sin(t) * b2)) for t in np.linspace(0, 2 * math.pi, n + 1)]
    return C.tube_along(name, pts, tube, sides=4)


def disc(name, c, axis, r, t, n=10):
    a, b1, b2 = basis(axis)
    c = np.asarray(c, float)
    V = [tuple(c), tuple(c + a * t)]
    F = []
    for i in range(n):
        th = 2 * math.pi * i / n
        o = r * (math.cos(th) * b1 + math.sin(th) * b2)
        V += [tuple(c + o), tuple(c + o + a * t)]
    for i in range(n):
        j = (i + 1) % n
        p0, p1, q0, q1 = 2 + 2 * i, 3 + 2 * i, 2 + 2 * j, 3 + 2 * j
        F += [(p0, q0, q1, p1), (0, q0, p0), (1, p1, q1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def plate(name, c, a1, a2, w, hgt, t, rr=0.028, n=4):
    """Rounded-rectangle plate (blinker) centred at c, spanning a1 x a2."""
    c, a1, a2 = (np.asarray(v, float) for v in (c, a1, a2))
    nrm = np.cross(a1, a2)
    nrm /= np.linalg.norm(nrm)
    out = []
    for cx, cy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for k in range(n + 1):
            th = math.radians(a0 + 90 * k / n)
            out.append((cx * (w / 2 - rr) + rr * math.cos(th), cy * (hgt / 2 - rr) + rr * math.sin(th)))
    m = len(out)
    V = [tuple(c + a1 * x + a2 * y - nrm * t / 2) for x, y in out] + [tuple(c + a1 * x + a2 * y + nrm * t / 2) for x, y in out]
    F = [tuple(range(m))[::-1], tuple(range(m, 2 * m))]
    F += [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def surf_pt(bodyf, p, off=0.0):
    """Project p onto the body surface (+off along the normal)."""
    P = np.array([p], float)
    for _ in range(8):
        d = bodyf(P)
        e = 1e-3
        g = np.stack([(bodyf(P + np.eye(3)[i] * e) - d) / e for i in range(3)], axis=1)
        g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        P = P - g * (d - off)[:, None]
    return P[0]


def collar_loop(bodyf, cen, e1, off, n=40):
    """Points where the body (no mane) is `off` away, round the neck in the plane (e1, x)."""
    ex = np.array([1.0, 0, 0])
    phis = np.linspace(0, 2 * math.pi, n, endpoint=False)
    pts = []
    for ph in phis:
        d = math.cos(ph) * e1 + math.sin(ph) * ex
        lo, hi = 0.0, 0.7
        for _ in range(28):
            m = 0.5 * (lo + hi)
            if bodyf(np.array([cen + d * m]))[0] < off:
                lo = m
            else:
                hi = m
        pts.append(cen + d * lo)
    return phis, np.array(pts)


def dstrap(name, bodyf, pts, n_sub=2, **kw):
    return strap(name, bodyf, pts, n_sub=n_sub, **kw)


def build_draft_harness(W, prims, bodyf, breeching):
    """Returns (Harness object, {empty name: (pos, bone)})."""
    B = W.B
    E, K = C.ell, C.cone
    nomane = [p for p in prims if not p.sub and p.label not in ("mane",)]
    neckf = lambda p: C.eval_sdf(nomane, p)
    M = W.map_body
    emp = {}
    # ---- collar: a stuffed roll round the neck base with the body of the collar behind it
    top, bot = M((0, -0.57, 1.645)), M((0, -0.87, 1.29))
    e1 = top - bot
    e1[0] = 0
    e1 /= np.linalg.norm(e1)
    n = np.cross(np.array([1.0, 0, 0]), e1)  # forward (toward the head)
    if n[1] > 0:
        n = -n
    cen = 0.5 * (top + bot)
    cs = B["nthick"][0] ** 0.6
    phis, roll = collar_loop(neckf, cen + n * 0.012, e1, 0.04 * cs)
    _, back = collar_loop(neckf, cen - n * 0.035, e1, 0.05 * cs)
    _, hame = collar_loop(neckf, cen + n * 0.045 * cs, e1, 0.058 * cs)
    sol = []
    nL = len(phis)
    for i in range(nL):
        j = (i + 1) % nL
        cs = B["nthick"][0] ** 0.6
        cr = lambda ph, a, b: cs * (a + b * math.sin(0.5 * ph) ** 2 * (1.25 - 0.5 * math.sin(0.5 * ph) ** 4))
        sol.append(K(roll[i], roll[j], cr(phis[i], 0.036, 0.024), cr(phis[j], 0.036, 0.024), "collar", [], k=0.01))
        sol.append(K(back[i], back[j], cr(phis[i], 0.03, 0.02), cr(phis[j], 0.03, 0.02), "collar", [], k=0.025))
    # hames: japanned bars in the collar's front groove, brass balls on top; traces hook on at the tugs
    tz = W.wz(1.13)
    side = {}
    for s, sfx in ((1, "_L"), (-1, "_R")):
        idx = [i for i in range(nL) if 0.3 < (phis[i] if s > 0 else 2 * math.pi - phis[i]) < 2.55]
        idx.sort(key=lambda i: phis[i] if s > 0 else 2 * math.pi - phis[i])
        hp = [hame[i] for i in idx]
        for a, b in zip(hp[:-1], hp[1:]):
            sol.append(K(a, b, 0.015, 0.015, "hame", [], k=0.004))
        t0 = hp[0]
        tip = t0 + e1 * 0.10 - np.array([0.012 * s, 0, 0]) + n * 0.01
        sol.append(K(t0, tip, 0.015, 0.013, "hame", [], k=0.004))
        sol.append(E(tip + e1 * 0.012, (0.024, 0.024, 0.024), "brass", [], k=0.006))
        tug = min(hp, key=lambda p: abs(p[2] - tz))
        rad = np.array([s * 1.0, 0, 0])
        sol.append(E(tug + rad * 0.012, (0.02, 0.035, 0.025), "brass", [], k=0.006))
        ter = hp[max(1, len(hp) // 7)]
        side[sfx] = dict(tug=tug + rad * 0.02, ter=ter, low=hp[-1])
    # pad (harness saddle) with a raised tree; the girth sits a hand behind the elbow
    py = W.wy(-0.22, 1.5)
    pz = top_z(bodyf, py)

    def rbox(p, c, hh, r):
        qq = np.abs(p - np.asarray(c)) - (np.asarray(hh) - r)
        return np.linalg.norm(np.maximum(qq, 0), axis=1) + np.minimum(qq.max(axis=1), 0) - r

    zl = W.wz(1.33)

    def pad(p):
        b = bodyf(p)
        shell = np.maximum(b - 0.03, -b - 0.004)
        hy = (0.055 + 0.04 * np.clip((p[:, 2] - zl) / max(pz - zl, 0.1), 0, 1)) * W.sy
        box = np.maximum(np.abs(p[:, 1] - py) - hy, zl - p[:, 2])
        return np.maximum(shell, box)

    sol.append(C.fnprim(pad, (-0.62, py - 0.2, zl - 0.05), (0.62, py + 0.2, pz + 0.08), "leather", [], k=0.0))
    sol.append(E((0, py, pz + 0.035), (0.10, 0.075, 0.035), "leather", [], k=0.02))
    for s in (1, -1):
        sol.append(E((0.085 * s, py, pz + 0.045), (0.02, 0.03, 0.02), "brass", [], k=0.01))  # terret base
    lo = np.array([-0.62, min(py - 0.25, float(roll[:, 1].min()) - 0.15), min(zl, float(roll[:, 2].min())) - 0.1])
    hi = np.array([0.62, py + 0.25, float(max(roll[:, 2].max(), hame[:, 2].max())) + 0.18])
    solid = C.build_sdf_mesh("HarnessSolid", sol, 0.0075, 1150, lo=lo, hi=hi, smooth_iters=1)
    C.smart_uv(solid)
    uv = np.empty(len(solid.data.loops) * 2, dtype=np.float32)
    solid.data.uv_layers.active.data.foreach_get("uv", uv)
    uv[0::2] *= 0.92
    solid.data.uv_layers.active.data.foreach_set("uv", uv)

    parts = {"rigid_chest": [], "rigid_spine": [], "skin": []}
    pc = {k: hexc(v) for k, v in HCOL.items()}
    solf = lambda p: C.eval_sdf([q for q in sol if q.kind != "fn"], p)

    def solid_color(P, N, ex):
        lw = C.label_weights(sol, P, ["collar", "hame", "brass", "leather"], tau=0.004)
        nz = C.fbm(P, 40.0, 3, seed=51)
        leather = pc["leather"] * (0.85 + 0.35 * nz)[:, None]
        # collar: black leather over a pale sweat-pad where it bears on the horse; stitched seam lines
        con = ss((0.016 - bodyf(P)) / 0.012)
        dplane = (P - cen) @ n
        seam = (np.abs(np.sin(dplane * 110.0)) < 0.12) * 0.35
        col = leather * (1 + seam)[:, None]
        col = col * (1 - con[:, None]) + pc["pad"] * (0.85 + 0.25 * nz)[:, None] * con[:, None]
        hm = pc["hame"] * (0.85 + 0.3 * nz)[:, None]
        br = pc["brass"] * (0.75 + 0.5 * C.fbm(P, 90.0, 2, seed=53))[:, None]
        # pad: quilted panel lines
        quilt = (np.abs(np.sin(P[:, 1] * 160.0)) < 0.1) * 0.25
        pd = leather * (1 + quilt)[:, None]
        c = lw["collar"][:, None] * col + lw["hame"][:, None] * hm + lw["brass"][:, None] * br + lw["leather"][:, None] * pd
        ao = C.sdf_ao([q for q in sol if q.kind != "fn"], P, N, steps=3, dist=0.012)
        c *= (0.6 + 0.4 * ao)[:, None]
        # scuffed, lighter on edges
        return c

    parts["solid"] = solid
    # ---- traces from the tugs along the side to behind the stifle (JS carries them on to the bars)
    for s, sfx in ((1, "_L"), (-1, "_R")):
        pts = [side[sfx]["tug"]] + [M((0.32 * s, y, z)) for y, z in ((-0.50, 1.10), (-0.25, 1.05), (0.02, 1.03), (0.28, 1.03), (0.50, 1.02))]
        tr = dstrap("trace", bodyf, pts, width=0.042, thick=0.011, off=0.02)
        parts["skin"].append(swatch(tr, "leather"))
        end = surf_pt(bodyf, M((0.30 * s, 0.62, 1.02)), 0.03)
        emp["Trace" + sfx] = (end, "pelvis")
        emp["Hame" + sfx] = (side[sfx]["tug"], "chest")
        # hame terret for the lines
        tc = side[sfx]["ter"] + np.array([0.02 * s, 0, 0]) + e1 * 0.028
        parts["rigid_chest"].append(swatch(ring("hterret", tc, n, 0.026, 0.0055), "brass"))
        emp["HameTerret" + sfx] = (tc, "chest")
        # pad terret
        pt = np.array([0.085 * s, py, pz + 0.085])
        parts["rigid_spine"].append(swatch(ring("pterret", pt, (0, 1, 0), 0.028, 0.0055), "brass"))
        emp["Terret" + sfx] = (pt, "spine")
    # hame straps top and bottom; the pole strap hangs from the bottom one
    lowc = 0.5 * (side["_L"]["low"] + side["_R"]["low"]) + n * 0.01 - e1 * 0.03
    parts["rigid_chest"].append(swatch(C.tube_along("hstrap", [side["_L"]["low"], lowc, side["_R"]["low"]], 0.0, sides=4, flat=(0.012, 0.006)), "leather"))
    t_l = side["_L"]["ter"]
    t_r = side["_R"]["ter"]
    parts["rigid_chest"].append(swatch(C.tube_along("hstrap2", [t_l + e1 * 0.07, 0.5 * (t_l + t_r) + e1 * 0.085, t_r + e1 * 0.07], 0.0, sides=4, flat=(0.012, 0.005)), "leather"))
    emp["PoleStrap"] = (lowc, "chest")
    # ---- girth (bellyband), backstrap, crupper, loin strap with trace carriers
    zc = W.wz(1.22)
    girth = [(0.5 * math.cos(a), py + 0.02, zc + 0.5 * math.sin(a)) for a in np.linspace(math.radians(-5), math.radians(-175), 11)]
    parts["skin"].append(swatch(dstrap("girth", bodyf, girth, width=0.065, thick=0.009, off=0.015), "leather"))
    back_pts = [(0, py + 0.09, 1.9)] + [M((0, y, 1.62)) for y in (0.0, 0.2, 0.4, 0.58, 0.72)]
    back_pts[0] = np.array([0, py + 0.085 * W.sy + 0.01, pz + 0.01])
    dock = W.b1["tail1"][0]
    back_pts.append(dock + np.array([0, 0.02, 0.05]))
    parts["skin"].append(swatch(dstrap("backstrap", bodyf, back_pts, width=0.034, thick=0.008, off=0.013), "leather"))
    td = W.b1["tail1"][1] - W.b1["tail1"][0]
    parts["skin"].append(swatch(ring("crupper", dock + td * 0.35, td, 0.065 * W.B["tthick"] + 0.012, 0.012, n=12), "leather"))
    ly = 0.30
    loin = [M((0.40 * s, ly, 1.02)) if abs(s) > 0.9 else M((0.4 * s, ly, 1.3 + 0.2 * (1 - abs(s)))) for s in (1, 0.5, 0, -0.5, -1)]
    loin[2] = np.array([0, W.wy(ly, 1.5), 1.9])
    parts["skin"].append(swatch(dstrap("loin", bodyf, loin, width=0.036, thick=0.008, off=0.022), "leather"))
    if breeching:
        # breeching round the quarters on hip straps, hold-backs forward to the hame bottoms
        br = [M((0.33 * s, y, 1.10)) for s, y in ((1, 0.46), (0.9, 0.66))] + [M((0.0, 0.95, 1.12))] + \
             [M((0.33 * s, y, 1.10)) for s, y in ((-0.9, 0.66), (-1, 0.46))]
        br[2] = np.array([0, W.wy(1.2, 1.2), W.wz(1.12)])
        parts["skin"].append(swatch(dstrap("breeching", bodyf, br, width=0.08, thick=0.012, off=0.010), "leather"))
        for yy in (0.46, 0.68):
            hs = [M((0.33, yy + 0.05, 1.12)), M((0.29, yy + 0.02, 1.27)), M((0.22, yy, 1.4)), np.array([0, W.wy(yy, 1.5), 1.9]),
                  M((-0.22, yy, 1.4)), M((-0.29, yy + 0.02, 1.27)), M((-0.33, yy + 0.05, 1.12))]
            parts["skin"].append(swatch(dstrap("hipstrap", bodyf, hs, width=0.034, thick=0.008, off=0.010), "leather"))
        for s, sfx in ((1, "_L"), (-1, "_R")):
            hb = [M((0.33 * s, 0.44, 1.08)), M((0.34 * s, 0.1, 0.99)), M((0.33 * s, -0.3, 0.98)), M((0.26 * s, -0.62, 1.04)),
                  side[sfx]["low"] + np.array([0.02 * s, 0, -0.01])]
            parts["skin"].append(swatch(dstrap("holdback", bodyf, hb, width=0.034, thick=0.009, off=0.017), "leather"))
    # ---- blinkered bridle
    hb = ["head"]
    h, u, f, L = head_frame(W)
    MH = lambda p: W.map_pt(p, hb)
    for s, sfx in ((1, "_L"), (-1, "_R")):
        ch = [MH(p) for p in ((0.075 * s, -1.41, 1.60), (0.095 * s, -1.31, 1.72), (0.10 * s, -1.20, 1.85), (0.085 * s, -1.10, 1.98), (0.03 * s, -1.06, 2.05))]
        parts["skin"].append(swatch(dstrap("cheek", bodyf, ch, width=0.026, thick=0.007), "leather"))
        tl = [MH(p) for p in ((0.085 * s, -1.11, 1.99), (0.095 * s, -1.06, 1.87), (0.06 * s, -1.02, 1.77), (0.0, -1.005, 1.74))]
        parts["skin"].append(swatch(dstrap("throat", bodyf, tl, width=0.018, thick=0.006), "leather"))
        bc = MH((0.085 * s, -1.41, 1.59))
        bc[0] = s * (abs(surf_pt(bodyf, bc, 0.0)[0]) + 0.012)
        parts["skin"].append(swatch(ring("bit", bc, (1, 0, 0), 0.026, 0.0055), "steel"))
        emp["Bit" + sfx] = (bc, "head")
        # blinker: square patent-leather plate standing off the eye, toed in at the front
        eye = MH((0.095 * s, -1.215, 1.93))
        ex = abs(surf_pt(bodyf, eye, 0.0)[0])
        cen_b = np.array([s * (ex + 0.03), eye[1], eye[2]]) - u * 0.012 + f * 0.006
        a1 = u - np.array([s * 0.28, 0, 0])
        a1 /= np.linalg.norm(a1)
        a2 = f
        parts["skin"].append(swatch(plate("blinker", cen_b, a1, a2, 0.105, 0.095, 0.008), "patent"))
        st = [cen_b + a2 * 0.047 - a1 * 0.01, MH((0.05 * s, -1.12, 2.02)), MH((0.0, -1.10, 2.05))]
        parts["skin"].append(swatch(dstrap("bstay", bodyf, st, width=0.016, thick=0.005, off=0.01, n_sub=2), "leather"))
        ro = MH((0.092 * s, -1.125, 1.985))
        ro = surf_pt(bodyf, ro, 0.008)
        parts["skin"].append(swatch(disc("rosette", ro, (s, 0, 0.25), 0.022, 0.008), "brass"))
        hr = surf_pt(bodyf, MH((0.06 * s, -1.075, 2.03)), 0.02)
        parts["skin"].append(swatch(ring("reindrop", hr + np.array([0.01 * s, 0, 0.01]), (0, 1, 0), 0.018, 0.004, n=8), "brass"))
        emp["HeadRing" + sfx] = (hr + np.array([0.01 * s, 0, 0.01]), "head")
    parts["skin"].append(swatch(dstrap("crown", bodyf, [MH((0.03, -1.06, 2.05)), MH((0.0, -1.055, 2.07)), MH((-0.03, -1.06, 2.05))], width=0.026, n_sub=2), "leather"))
    parts["skin"].append(swatch(dstrap("brow", bodyf, [MH(p) for p in ((0.085, -1.12, 1.98), (0, -1.155, 2.02), (-0.085, -1.12, 1.98))], width=0.024), "leather"))
    nc = h + u * 0.64 * L
    ringn = [nc + 0.2 * (math.cos(a) * f + math.sin(a) * np.array([1.0, 0, 0])) for a in np.linspace(0, 2 * math.pi, 15)]
    parts["skin"].append(swatch(dstrap("nose", bodyf, ringn, width=0.028, off=0.011), "leather"))
    return parts, solid_color, emp


def bake_swatched(ob, size, color_fn, name):
    """bake_texture plus flat swatch cells at u 0.94..1 for straps and hardware."""
    r = C.rasterise(ob, size)
    m = r["mask"]
    img = np.zeros((size, size, 3))
    img[m] = np.clip(color_fn(r["P"][m], r["N"][m], {}), 0, 1)
    img = C.dilate(img, m, 10)
    x0 = int(0.94 * size)
    for kind, v in SW.items():
        col = hexc(HCOL[kind])
        y0, y1 = int((v - 0.125) * size), int((v + 0.125) * size)
        yy = np.arange(y0, y1)[:, None]
        xx = np.arange(x0, size)[None, :]
        grain = 0.9 + 0.1 * np.sin(yy * 1.7 + xx * 0.9)
        img[y0:y1, x0:] = col * grain[..., None]
    return C.make_image(name, img)


def breed_gait(name, W, A):
    B = W.B
    G = B["gait"]
    s = W.legf * G["sweep"]
    sw = B["swing"]
    dF, dH = G["duty"]

    def bouncy(fn):  # scale the body's bob and pitch per breed
        def f(phi):
            loc, rt, cp, pp = fn(phi)
            return loc, (rt[0], rt[1], rt[2] * G["bob"]), cp, pp
        return f

    gal = gait_clip(
        A, "Gallop", 32,
        onsets={"H.L": 0.0, "H.R": 0.11, "F.L": 0.30, "F.R": 0.41},
        duty={"F": dF, "H": dH},
        sweep={"F": 1.00 * s, "H": 0.98 * s},
        fwd={"F": G["fwd"] * s, "H": 0.52 * s},
        body_fn=bouncy(gallop_body), sc_amp=G["sc"], swing=sw,
    )
    can = gait_clip(
        A, "Canter", 42,
        onsets={"H.L": 0.0, "H.R": 0.27, "F.L": 0.31, "F.R": 0.54},
        duty={"F": dF + 0.04, "H": dH + 0.04},
        sweep={"F": 0.88 * s, "H": 0.86 * s},
        fwd={"F": G["fwd"] * 0.9 * s, "H": 0.45 * s},
        body_fn=bouncy(canter_body), sc_amp=G["sc"] * 0.82,
        swing={k: {kk: vv * 0.92 for kk, vv in v.items()} for k, v in sw.items()},
    )
    return gal, can


def main_breed(name):
    B = BREEDS[name]
    W = Warp(B)
    out = os.path.join(C.MODELS, f"horse_{name}.glb")
    C.reset_scene()
    prims = breed_prims(W)
    body = C.build_sdf_mesh("Horse", prims, B["vox"], B["tris"])
    bodyf = body_sdf_fn(prims)
    skinf = body_sdf_fn([p for p in prims if p.label not in ("mane", "tail")])  # harness lies on this
    C.set_active(body)
    wn = body.modifiers.new("wn", "WEIGHTED_NORMAL")  # face-area normals: no facets on the decimated flats
    wn.weight = 65
    bpy.ops.object.modifier_apply(modifier=wn.name)
    sy = W.wy(-0.15, 1.5)
    seat_back = top_z(bodyf, sy)
    mount = Vector((0, sy, seat_back + 0.085))
    for z in (1.0, 1.2, 1.35, 1.5):
        xs = np.linspace(0.7, 0, 700)
        zz = W.wz(z)
        P = np.stack([xs, np.full_like(xs, W.wy(-0.05, 1.2)), np.full_like(xs, zz)], axis=1)
        print(f"[{name}] barrel half-width z={zz:.2f}: {xs[int(np.argmax(bodyf(P) < 0))]:.3f}")
    wy_ = W.b1["chest"][0][1] - 0.03  # behind the crest, which overlaps the withers from the front
    print(f"[{name}] withers {top_z(skinf, wy_):.3f} back {seat_back:.3f} belly {W.lz:.3f}")

    # riding saddle kept for the node contract (hidden on the team)
    sp = saddle_prims(bodyf, seat_back, wx=B["wide"])
    saddle = C.build_sdf_mesh("Saddle", sp, 0.009, 700, lo=(-0.5, -0.62, 0.85), hi=(0.5, 0.25, seat_back + 0.35), smooth_iters=1)
    parts, solid_color, emp = build_draft_harness(W, prims, skinf, B["breeching"])

    # --- textures
    C.smart_uv(body)
    img = C.bake_texture(body, 1024, breed_color(prims, W, name), "Horse_tex")
    C.assign_material(body, C.image_material("Horse_mat", img, roughness=B["rough"]))
    C.smart_uv(saddle)
    img = C.bake_texture(saddle, 256, saddle_color(sp), "Saddle_tex")
    C.assign_material(saddle, C.image_material("Saddle_mat", img, roughness=0.65))
    solid = parts["solid"]
    himg = bake_swatched(solid, 512, solid_color, "Harness_tex")

    # --- rig
    arm = C.build_armature("HorseRig", W.bones)
    rig = C.Rig(arm)
    segs = {b: (np.array(rig.head[b]), np.array(rig.tail[b])) for b in rig.order}
    C.compute_weights(body, prims, segs, tau=0.018, smooth_iters=4)
    C.rigid_weights(saddle, "spine")
    # collar and hames ride the shoulders; the pad the back; straps follow the skin
    C.transfer_weights(body, solid, k=3)
    ycut = float(W.wy(-0.45, 1.5))
    sp_i = solid.vertex_groups.find("spine")
    ch_g = solid.vertex_groups["chest"]
    sp_g = solid.vertex_groups["spine"]
    co = C.verts_np(solid)
    front = np.nonzero(co[:, 1] < ycut)[0].tolist()
    rear = np.nonzero(co[:, 1] >= ycut)[0].tolist()
    for g in list(solid.vertex_groups):
        g.remove(front)
        g.remove(rear)
    ch_g.add(front, 1.0, "REPLACE")
    sp_g.add(rear, 1.0, "REPLACE")
    for ob in parts["skin"]:
        C.transfer_weights(body, ob, k=3)
    for ob in parts["rigid_chest"]:
        C.rigid_weights(ob, "chest")
    for ob in parts["rigid_spine"]:
        C.rigid_weights(ob, "spine")
    harness = C.join([solid] + parts["skin"] + parts["rigid_chest"] + parts["rigid_spine"], "Harness")
    C.shade_smooth(harness)
    C.assign_material(harness, C.image_material("Harness_mat", himg, roughness=0.62))
    for ob in (body, saddle, harness):
        C.bind(ob, arm)

    empties = [("Mount", mount, "spine")] + [(k, Vector(tuple(p)), b) for k, (p, b) in sorted(emp.items())]
    eobs = []
    for nm, pos, bone in empties:
        m = bpy.data.objects.new(nm, None)
        m.empty_display_type = "ARROWS"
        m.empty_display_size = 0.05 if nm != "Mount" else 0.2
        bpy.context.scene.collection.objects.link(m)
        m.parent = arm
        m.parent_type = "BONE"
        m.parent_bone = bone
        bpy.context.view_layer.update()
        m.matrix_world = Matrix.Translation(pos)
        eobs.append(m)

    # --- animation
    A = HorseAnim(rig)
    gal, can = breed_gait(name, W, A)
    C.write_action(arm, "Gallop", gal, loop=True)
    C.write_action(arm, "Canter", can, loop=True)
    C.write_action(arm, "Idle", idle_clip(A), loop=True)
    C.write_action(arm, "Fall", fall_clip(A))
    C.write_action(arm, "Rear", rear_clip(A, pivot=(W.wy(0.62, 0.55), W.wz(0.55))))
    arm.animation_data.action = bpy.data.actions["Gallop"]

    for ob in (body, saddle, harness):
        print(f"[{name}] {ob.name}: {C.tri_count(ob)} tris")
    C.export_glb(out, [arm, body, saddle, harness] + eobs)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.PREVIEWS, f"horse_{name}_build.blend"))


# ----------------------------------------------------------------------------
def main():
    C.reset_scene()
    prims = body_prims()
    body = C.build_sdf_mesh("Horse", prims, H, 8600)
    bodyf = body_sdf_fn(prims)
    seat_back = top_z(bodyf, -0.15)
    mount = Vector((0, -0.15, seat_back + 0.085))
    print("[horse] back z at seat", seat_back, "mount", tuple(mount))
    for z in (1.0, 1.2, 1.35, 1.5):
        xs = np.linspace(0.6, 0, 600)
        P = np.stack([xs, np.full_like(xs, -0.25), np.full_like(xs, z)], axis=1)
        print(f"[horse] barrel half-width at y=-0.25 z={z}: {xs[int(np.argmax(bodyf(P) < 0))]:.3f}")

    sp = saddle_prims(bodyf, seat_back)
    saddle = C.build_sdf_mesh("Saddle", sp, 0.0075, 1500, lo=(-0.46, -0.62, 0.88), hi=(0.46, 0.25, 1.95), smooth_iters=1)
    harness = build_harness(bodyf, seat_back)
    C.shade_smooth(harness)

    # --- textures
    for ob, size, fn, rough in ((body, 1024, horse_color(prims), 0.72), (saddle, 512, saddle_color(sp), 0.65)):
        C.smart_uv(ob)
        img = C.bake_texture(ob, size, fn, ob.name + "_tex")
        C.assign_material(ob, C.image_material(ob.name + "_mat", img, roughness=rough))
    hm = bpy.data.materials.new("Harness_mat")
    hm.use_nodes = True
    bs = hm.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (0.045, 0.025, 0.015, 1)
    bs.inputs["Roughness"].default_value = 0.55
    C.assign_material(harness, hm)

    # --- rig
    arm = C.build_armature("HorseRig", bone_list())
    rig = C.Rig(arm)
    segs = {b: (np.array(rig.head[b]), np.array(rig.tail[b])) for b in rig.order}

    def overrides(P, W, names):
        # keep the belly/barrel off the legs; keep lower legs off the trunk
        return W

    C.compute_weights(body, prims, segs, tau=0.018, smooth_iters=4, overrides=overrides)
    C.rigid_weights(saddle, "spine")
    C.transfer_weights(body, harness, k=3)
    for ob in (body, saddle, harness):
        C.bind(ob, arm)

    m = bpy.data.objects.new("Mount", None)
    m.empty_display_type = "ARROWS"
    m.empty_display_size = 0.2
    bpy.context.scene.collection.objects.link(m)
    m.parent = arm
    m.parent_type = "BONE"
    m.parent_bone = "spine"
    bpy.context.view_layer.update()
    m.matrix_world = Matrix.Translation(mount)

    # --- animation
    A = HorseAnim(rig)
    gal = gait_clip(
        A, "Gallop", 32,
        onsets={"H.L": 0.0, "H.R": 0.11, "F.L": 0.30, "F.R": 0.41},
        duty={"F": 0.28, "H": 0.30},
        sweep={"F": 1.00, "H": 0.98},
        fwd={"F": 0.42, "H": 0.52},
        body_fn=gallop_body, sc_amp=11.0,
        swing={"F": {"carpus": 98, "elbow": -38, "fetlock": 48}, "H": {"stifle": 30, "hock": -62, "fetlock": 55}},
    )
    can = gait_clip(
        A, "Canter", 42,
        onsets={"H.L": 0.0, "H.R": 0.27, "F.L": 0.31, "F.R": 0.54},
        duty={"F": 0.32, "H": 0.34},
        sweep={"F": 0.88, "H": 0.86},
        fwd={"F": 0.38, "H": 0.45},
        body_fn=canter_body, sc_amp=9.0,
        swing={"F": {"carpus": 95, "elbow": -38, "fetlock": 50}, "H": {"stifle": 26, "hock": -52, "fetlock": 45}},
    )
    C.write_action(arm, "Gallop", gal, loop=True)
    C.write_action(arm, "Canter", can, loop=True)
    C.write_action(arm, "Idle", idle_clip(A), loop=True)
    C.write_action(arm, "Fall", fall_clip(A))
    C.write_action(arm, "Rear", rear_clip(A))
    arm.animation_data.action = bpy.data.actions["Gallop"]

    for ob in (body, saddle, harness):
        print(f"[horse] {ob.name}: {C.tri_count(ob)} tris")
    C.export_glb(OUT, [arm, body, saddle, harness, m])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.PREVIEWS, "horse_build.blend"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    breed = argv[argv.index("--breed") + 1] if "--breed" in argv else "horse"
    if breed == "horse":
        main()
    else:
        main_breed(breed)
