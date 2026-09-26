"""Standalone GLB inspector (python3 + numpy): evaluates animation clips exactly as
three.js would (node TRS, LINEAR / slerp) and reports world axes of named nodes.

  python3 tools/blender/gltf_check.py public/assets/models/rider.glb hand.R RideAim 0.1
"""
import json
import struct
import sys

import numpy as np

CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load(path):
    b = open(path, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + jl])
    bl = struct.unpack("<I", b[20 + jl:24 + jl])[0]
    bin_ = b[28 + jl:28 + jl + bl]
    return js, bin_


def acc(js, bin_, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    n = NC[a["type"]]
    dt = CT[a["componentType"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    arr = np.frombuffer(bin_, dtype=dt, count=a["count"] * n, offset=off)
    return arr.reshape(a["count"], n).astype(np.float64)


def qmat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def slerp(a, b, t):
    d = np.dot(a, b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + (b - a) * t
        return r / np.linalg.norm(r)
    th = np.arccos(d)
    return (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)


def world(js, bin_, clip=None, t=0.0):
    nodes = js["nodes"]
    trs = []
    for n in nodes:
        trs.append([np.array(n.get("translation", [0, 0, 0]), float), np.array(n.get("rotation", [0, 0, 0, 1]), float),
                    np.array(n.get("scale", [1, 1, 1]), float)])
    if clip:
        an = next(a for a in js["animations"] if a["name"] == clip)
        for ch in an["channels"]:
            s = an["samplers"][ch["sampler"]]
            ti = acc(js, bin_, s["input"])[:, 0]
            vo = acc(js, bin_, s["output"])
            k = int(np.clip(np.searchsorted(ti, t) - 1, 0, len(ti) - 2)) if len(ti) > 1 else 0
            u = 0.0 if len(ti) == 1 else float(np.clip((t - ti[k]) / (ti[k + 1] - ti[k]), 0, 1))
            p = ch["target"]["path"]
            idx = {"translation": 0, "rotation": 1, "scale": 2}[p]
            if len(ti) == 1:
                v = vo[0]
            elif p == "rotation":
                v = slerp(vo[k], vo[k + 1], u)
            else:
                v = vo[k] * (1 - u) + vo[k + 1] * u
            trs[ch["target"]["node"]][idx] = v
    local = []
    for t_, r, s in trs:
        M = np.eye(4)
        M[:3, :3] = qmat(r) * s
        M[:3, 3] = t_
        local.append(M)
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    W = [None] * len(nodes)

    def get(i):
        if W[i] is None:
            W[i] = local[i] if i not in parent else get(parent[i]) @ local[i]
        return W[i]

    return {nodes[i].get("name", str(i)): get(i) for i in range(len(nodes))}


if __name__ == "__main__":
    path, node = sys.argv[1], sys.argv[2]
    clip = sys.argv[3] if len(sys.argv) > 3 else None
    t = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    js, b = load(path)
    W = world(js, b, clip, t)
    M = W[node]
    np.set_printoptions(precision=3, suppress=True)
    print(f"{node} @ {clip} t={t}: pos {M[:3, 3]}  +X {M[:3, 0]}  +Y {M[:3, 1]}  +Z {M[:3, 2]}")
