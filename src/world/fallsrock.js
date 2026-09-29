// The rock the gorge falls pour off: a natural arch over the road. The stream
// runs across its top and spills off the downstream edge, so the curtain has a
// lip of stone to fall from instead of a straight line in the sky, and both of
// its sides end against rock — the inland abutment on one side, a pier standing
// out of the drop on the other.
//
// Built from a few dozen lumpy boulders merged into one mesh. Merged boulders
// read as fractured stone from every side, which a single extruded arch profile
// can't do without big flat caps. One draw call, shadows on.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { makeNoise2D, mulberry32, clamp } from '../core/noise.js';
import { tex } from './textures.js';

const _v = new THREE.Vector3(), _n = new THREE.Vector3(), _q = new THREE.Quaternion(), _e = new THREE.Euler();

// `f` is a resolved fall from Water._resolveFall. Local frame: `d` across the
// road (along f.ax), `n` downstream through the curtain (along f.nx), y up.
// The lip is at n = 0; the arch sits upstream of it (n < 0).
export function buildFallsArch(route, f, { q = 1, seed = 1, tint } = {}) {
  const rnd = mulberry32(seed * 31 + 5);
  const noise = makeNoise2D(seed * 7 + 3);
  const roadY = route.roadHeightAt(f.s);
  const lip = f.lipY - roadY;                  // lip height over the road
  const lipL = f.lat(0) - f.halfW, lipR = f.lat(0) + f.halfW;
  const side = Math.sign(f.span) || 1;        // + toward the river
  // outer = river side, inner = the wall. Keep the maths in "outer-positive" d.
  const inner = side > 0 ? lipL : -lipR, outer = side > 0 ? lipR : -lipL;
  const world = (d, y, n, out) => out.set(
    f.cx + f.ax * d * side + f.nx * n, roadY + y, f.cz + f.az * d * side + f.nz * n);
  const ground = (d, n = -4) => { world(d, 0, n, _v); return route.height(_v.x, _v.z) - roadY; };

  const rocks = [];
  const add = (d, y, n, r, sy = 1) => rocks.push({ d, y, n, r, sy });

  // the stream bed: its crown sits just under the water, so the flow is what
  // you see on top and the stone is what you see from underneath
  for (let d = inner - 1; d <= outer + 1; d += 2.2 + rnd() * 0.5) {
    for (const [n, lift] of [[-2.6, 0], [-5.4, 0.25], [-8.3, 0.6]]) {
      const r = 2.3 + rnd() * 0.7, sy = 0.72;
      add(d + (rnd() - 0.5) * 0.8, lip - 0.2 + lift - r * sy * 0.97, n + (rnd() - 0.5) * 0.6, r, sy);
    }
    // a ragged underside, kept high over the roadway itself
    if (rnd() < 0.7) {
      const r = 1.4 + rnd() * 0.8;
      const y = lip - 3.2 - rnd() * 0.8;
      if (Math.abs(d) > 6 || y - r * 0.8 > 5.6) add(d, y, -3.5 - rnd() * 4, r, 0.8);
    }
  }
  // banks either side of the channel, standing proud of the water
  for (const [d0, d1] of [[inner - 6, inner - 1.5], [outer + 1.5, outer + 5]]) {
    for (let d = d0; d <= d1; d += 1.8) {
      for (const n of [-2.4, -5.6, -8.8]) {
        const r = 2.4 + rnd() * 0.9;
        add(d, lip + 0.6 + rnd() * 1.4 - r * 0.4, n + (rnd() - 0.5), r, 0.85);
      }
    }
  }
  // inland abutment: from the shoulder back until the wall itself is higher
  // than the arch — that's where the arch has grown out of the wall
  for (let d = inner - 1.5; d > inner - 26; d -= 2.4) {
    const g = ground(d);
    const top = Math.max(lip + 1.2, g + 1.5);
    if (g > lip + 3) break;
    for (let y = g - 1.2; y < top; y += 2.3) {
      for (const n of [-2.5, -5.6, -8.7]) add(d + (rnd() - 0.5) * 1.2, y, n + (rnd() - 0.5), 2.4 + rnd() * 0.9, 0.9);
    }
  }
  // outer pier, standing up out of the drop
  const pierD = outer + 5.5;
  let foot = Infinity;
  for (let d = pierD - 4; d <= pierD + 4; d += 1) foot = Math.min(foot, ground(d));
  foot = Math.max(foot, f.botY - roadY + 1);
  for (let y = foot - 1.5; y < lip + 1.5; y += 2.2) {
    const taper = 1 - 0.18 * clamp((lip - y) / (lip - foot), 0, 1);
    for (const n of [-2.8, -6.2]) {
      add(pierD + (rnd() - 0.5) * 2.2, y, n + (rnd() - 0.5), (2.6 + rnd() * 0.8) * (0.8 + 0.3 * taper), 0.9);
    }
    if (rnd() < 0.5) add(pierD + 2.5 + rnd() * 1.5, y, -4.5, 2 + rnd(), 0.9);
  }

  // --- geometry: displaced icosahedra, oriented randomly, merged
  const detail = q ? 2 : 1;
  const base = mergeVertices(new THREE.IcosahedronGeometry(1, detail).deleteAttribute('normal').deleteAttribute('uv'));
  const geos = [];
  const wetCol = new THREE.Color(0.66, 0.7, 0.72), moss = new THREE.Color(0.72, 0.86, 0.56);
  const k = rocks.length;
  for (let i = 0; i < k; i++) {
    const R = rocks[i];
    const g = base.clone();
    const pos = g.attributes.position;
    const ox = rnd() * 50, oy = rnd() * 50;
    _q.setFromEuler(_e.set(rnd() * 6.3, rnd() * 6.3, rnd() * 6.3));
    for (let j = 0; j < pos.count; j++) {
      _v.fromBufferAttribute(pos, j);
      // big facets plus a finer chip, so it breaks like stone rather than blobs
      const a = noise(_v.x * 1.1 + ox, _v.y * 1.1 + _v.z * 0.7 + oy);
      const b = noise(_v.z * 2.7 - oy, _v.x * 2.7 + _v.y * 1.3 + ox);
      const facet = Math.round(a * 3) / 3;
      _v.multiplyScalar(1 + facet * 0.15 + a * 0.1 + b * 0.07);
      _v.applyQuaternion(_q);
      _v.set(_v.x * R.r, _v.y * R.r * R.sy, _v.z * R.r);
      world(R.d, R.y, R.n, _n).add(_v.set(
        (f.ax * _v.x * side + f.nx * _v.z),
        _v.y,
        (f.az * _v.x * side + f.nz * _v.z)));
      pos.setXYZ(j, _n.x, _n.y, _n.z);
    }
    g.computeVertexNormals();
    // triplanar-ish UVs by dominant normal, and colour: wet where the water
    // runs, moss on top, darker underneath
    const nrm = g.attributes.normal;
    const uv = new Float32Array(pos.count * 2), col = new Float32Array(pos.count * 3);
    const c = new THREE.Color();
    for (let j = 0; j < pos.count; j++) {
      const x = pos.getX(j), y = pos.getY(j), z = pos.getZ(j);
      const nx = nrm.getX(j), ny = nrm.getY(j), nz = nrm.getZ(j);
      const ax = Math.abs(nx), ay = Math.abs(ny), az = Math.abs(nz);
      if (ay > ax && ay > az) { uv[j * 2] = x / 5; uv[j * 2 + 1] = z / 5; }
      else if (ax > az) { uv[j * 2] = z / 5; uv[j * 2 + 1] = y / 5; }
      else { uv[j * 2] = x / 5; uv[j * 2 + 1] = y / 5; }
      c.setRGB(1, 1, 1);
      // local coords back out for the wet test
      const dx = x - f.cx, dz = z - f.cz;
      const ld = (dx * f.ax + dz * f.az) * side, ln = dx * f.nx + dz * f.nz;
      const yRel = y - roadY;
      const inChannel = ld > inner - 0.5 && ld < outer + 0.5;
      const wet = (inChannel && yRel > lip - 1.2 && ln > -9) || (inChannel && ln > -1.2)
        || Math.abs(ld - inner) < 1.2 || Math.abs(ld - outer) < 1.2;
      if (ny > 0.55 && !wet) c.lerp(moss, 0.55 * (ny - 0.55) / 0.45 + 0.2);
      if (wet) c.multiply(wetCol);
      if (ny < -0.3) c.multiplyScalar(0.72 + 0.28 * (1 + ny));
      const grime = 0.86 + noise(x * 0.35, z * 0.35 + y * 0.2) * 0.14;
      c.multiplyScalar(grime);
      col.set([c.r, c.g, c.b], j * 3);
    }
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geos.push(g);
  }
  base.dispose();
  const geo = mergeGeometries(geos, false);
  geos.forEach((g) => g.dispose());
  geo.computeBoundingSphere();

  const map = tex('rock'), nmap = tex('rock_n');
  for (const t of [map, nmap]) if (t) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  const mat = new THREE.MeshStandardMaterial({
    map, normalMap: nmap || null, color: new THREE.Color(tint || 0xb8bcb4).lerp(new THREE.Color(1, 1, 1), 0.55), vertexColors: true, roughness: 0.92,
  });
  if (nmap) mat.normalScale.set(1.2, 1.2);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = true; mesh.receiveShadow = true;

  // where water drips off the underside onto the road, for the spray pool
  const drips = rocks.filter((r) => r.y < lip - 1.5 && r.d > inner && r.d < outer)
    .map((r) => world(r.d, r.y - r.r * r.sy * 0.8, r.n, new THREE.Vector3()));
  return { mesh, drips, tris: geo.index ? geo.index.count / 3 : geo.attributes.position.count / 3 };
}
