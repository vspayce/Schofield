#!/usr/bin/env python3
"""Print a GLB's node tree (name, local translation, world-space bbox in glTF axes),
triangle counts, materials and embedded image sizes.  Plain python3, no Blender.

  python3 tools/blender/inspect_glb.py public/assets/models/stagecoach.glb
"""
import json
import struct
import sys


def load(path):
    data = open(path, 'rb').read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67, 'not a GLB'
    off = 12
    js, binc = None, None
    while off < length:
        clen, ctype = struct.unpack_from('<II', data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc, len(data)


def main(path):
    g, _, size = load(path)
    nodes = g['nodes']
    acc = g['accessors']
    print('%s  %.0f KB' % (path, size / 1024))

    def tris(mi):
        t = 0
        for p in g['meshes'][mi]['primitives']:
            if 'indices' in p:
                t += acc[p['indices']]['count'] // 3
            else:
                t += acc[p['attributes']['POSITION']]['count'] // 3
        return t

    def bbox(mi, off):
        lo, hi = [1e9] * 3, [-1e9] * 3
        for p in g['meshes'][mi]['primitives']:
            a = acc[p['attributes']['POSITION']]
            for k in range(3):
                lo[k] = min(lo[k], a['min'][k] + off[k])
                hi[k] = max(hi[k], a['max'][k] + off[k])
        return lo, hi

    total = [0]

    def walk(i, depth, off):
        n = nodes[i]
        t = n.get('translation', [0, 0, 0])
        w = [off[k] + t[k] for k in range(3)]
        extra = ''
        if 'rotation' in n and any(abs(v) > 1e-6 for v in n['rotation'][:3]):
            extra += ' ROT=%s' % n['rotation']
        if 'scale' in n and any(abs(v - 1) > 1e-6 for v in n['scale']):
            extra += ' SCALE=%s' % n['scale']
        if 'mesh' in n:
            tc = tris(n['mesh'])
            total[0] += tc
            lo, hi = bbox(n['mesh'], w)
            extra += '  mesh %5d tris  bbox x[%.2f,%.2f] y[%.2f,%.2f] z[%.2f,%.2f]' % (
                tc, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
        print('%s%-14s local(%.3f, %.3f, %.3f) world(%.3f, %.3f, %.3f)%s' % (
            '  ' * depth, n.get('name'), *t, *w, extra))
        for c in n.get('children', []):
            walk(c, depth + 1, w)

    for r in g['scenes'][g.get('scene', 0)]['nodes']:
        walk(r, 0, [0, 0, 0])
    print('TOTAL tris', total[0])
    for m in g.get('materials', []):
        print('material', m['name'], list(k for k in m if k != 'name'))
    for im in g.get('images', []):
        bv = g['bufferViews'][im['bufferView']]
        print('image', im.get('name'), im.get('mimeType'), '%.0f KB' % (bv['byteLength'] / 1024))


if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)
