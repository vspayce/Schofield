"""Print a compact summary of a .glb (system python): materials, images, buffer usage by attribute."""
import json, struct, sys, collections
p = sys.argv[1]
b = open(p, 'rb').read()
jl = struct.unpack('<I', b[12:16])[0]
j = json.loads(b[20:20 + jl])
print('file', len(b) // 1024, 'KB')
for m in j.get('materials', []):
    print('MAT', m['name'], {k: m[k] for k in m if k in ('alphaMode', 'alphaCutoff', 'doubleSided')})
for im, bv in ((im, j['bufferViews'][im['bufferView']]) for im in j.get('images', [])):
    print('IMG', im.get('name'), im.get('mimeType'), bv['byteLength'] // 1024, 'KB')
use = collections.Counter()
ct = {5126: 4, 5123: 2, 5125: 4, 5121: 1, 5122: 2, 5120: 1}
nc = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
seen = set()
for mesh in j['meshes']:
    for pr in mesh['primitives']:
        for k, a in list(pr['attributes'].items()) + [('indices', pr.get('indices'))]:
            if a is None or a in seen: continue
            seen.add(a)
            acc = j['accessors'][a]
            use[k + ':' + str(acc['componentType'])] += acc['count'] * ct[acc['componentType']] * nc[acc['type']]
for k, v in use.most_common():
    print('  %-22s %6d KB' % (k, v // 1024))
