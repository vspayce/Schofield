"""Build public/assets/models/horse.glb  (SCHOFIELD)

Run:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
      --python tools/blender/build_horse.py

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


def saddle_prims(bodyf, seat):
    """seat: z of the back surface at the seat."""
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
            C.box((0.325 * s, -0.24, 1.20), (0.013, 0.075, 0.19), 0.01, "leather", bs, k=0.0, rot=rot),  # fender
            C.box((0.345 * s, -0.33, 0.965), (0.055, 0.045, 0.038), 0.014, "stirrup", bs, k=0.0),
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


def rear_clip(A, n=120):
    """Rear up on the hind legs (hind hooves planted by IK), paw the air, come down."""
    front_rest = (0, 0, 0, 0, 0)
    keys_t = [0.0, 0.35, 0.8, 1.15, 1.45, 2.0]
    pitch = [0, 6, -40, -44, -38, 0]
    tuck = [0, 0.1, 1.0, 1.0, 0.9, 0]
    neck = [0, 8, -14, -10, -12, 0]
    frames = []
    pivot = np.array([0.62, 0.55])  # y,z pivot near the hocks
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
    main()
