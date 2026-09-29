// Instanced props + grass. Placement is deterministic per terrain tile. Each
// prop kind is one InstancedMesh per material part; the visible instance list is
// rebuilt only when the set of visible tiles changes (tile-level frustum cull).
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { mulberry32, smoothstep } from '../core/noise.js';
import { ROAD_HALF } from './route.js';
import { TILE } from './terrain.js';
import { grassTex, tex } from './textures.js';

// ---------------------------------------------------------------- catalogue
function stdMat(color, rough = 0.9, extra = {}) { return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0, ...extra }); }

function fallbackKind(name) {
  const parts = [];
  const add = (geo, mat) => parts.push({ geo, mat, m: new THREE.Matrix4() });
  const bark = stdMat(0x4a3726), needles = stdMat(0x3c4a2a), rock = stdMat(0x8a7f72, 0.95, { flatShading: true });
  switch (name) {
    case 'Pine_A': case 'Pine_B': case 'Pine_Snow': {
      add(new THREE.CylinderGeometry(0.18, 0.32, 14, 6).translate(0, 7, 0), bark);
      const g = new THREE.ConeGeometry(2.6, 12, 7).translate(0, 9.5, 0);
      add(g, name === 'Pine_Snow' ? stdMat(0x7d8a7a) : needles);
      break;
    }
    case 'DeadTree': add(new THREE.CylinderGeometry(0.1, 0.35, 7, 5).translate(0, 3.5, 0), stdMat(0x6b5a48)); break;
    case 'Saguaro': {
      const m = stdMat(0x5f7a45);
      add(new THREE.CapsuleGeometry(0.35, 6, 4, 8).translate(0, 3.4, 0), m);
      add(new THREE.CapsuleGeometry(0.22, 2, 4, 6).translate(0.8, 3.8, 0), m);
      break;
    }
    case 'Joshua': add(new THREE.CylinderGeometry(0.15, 0.3, 4, 5).translate(0, 2, 0), stdMat(0x6a5a40)); break;
    case 'Sagebrush': case 'Tumbleweed': add(new THREE.IcosahedronGeometry(0.7, 0).scale(1, 0.6, 1).translate(0, 0.35, 0), stdMat(name === 'Sagebrush' ? 0x7d8468 : 0x9a7c50, 1, { flatShading: true })); break;
    case 'Rock_A': case 'Rock_B': case 'Rock_C': add(new THREE.DodecahedronGeometry(1, 0).scale(1.2, 0.7, 1).translate(0, 0.3, 0), rock); break;
    case 'Boulder_Big': case 'CliffChunk': add(new THREE.DodecahedronGeometry(4, 1).scale(1.3, 0.8, 1).translate(0, 1.5, 0), rock); break;
    case 'Fence_Rail': {
      const w = stdMat(0x6d5840);
      add(new THREE.BoxGeometry(0.12, 1.2, 0.12).translate(-1.5, 0.6, 0), w);
      add(new THREE.BoxGeometry(3.1, 0.08, 0.06).translate(0, 0.95, 0), w);
      add(new THREE.BoxGeometry(3.1, 0.08, 0.06).translate(0, 0.55, 0), w);
      break;
    }
    case 'TelegraphPole': {
      const w = stdMat(0x5a4a38);
      add(new THREE.CylinderGeometry(0.1, 0.14, 7.5, 6).translate(0, 3.75, 0), w);
      add(new THREE.BoxGeometry(1.6, 0.1, 0.1).translate(0, 7, 0), w);
      break;
    }
    case 'CowSkull': add(new THREE.SphereGeometry(0.2, 6, 4).translate(0, 0.1, 0), stdMat(0xe8e0d0)); break;
    case 'GraveCross': {
      const w = stdMat(0x5a4632);
      add(new THREE.BoxGeometry(0.1, 1.1, 0.08).translate(0, 0.55, 0), w);
      add(new THREE.BoxGeometry(0.6, 0.08, 0.08).translate(0, 0.8, 0), w);
      break;
    }
    case 'Wagon_Wreck': add(new THREE.BoxGeometry(1.6, 0.6, 3.5).translate(0, 0.4, 0).rotateZ(0.3), stdMat(0x5a4632)); break;
    default: add(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0), rock);
  }
  return { parts, radius: 4 };
}

function kindFromGLB(name) {
  const g = assets.models.props;
  if (!g) return null;
  const root = findNode(g.scene, name);
  if (!root) return null;
  root.updateWorldMatrix(true, true);
  const inv = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const parts = [];
  let radius = 1;
  root.traverse((o) => {
    if (!o.isMesh) return;
    const m = new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    mats.forEach((mat) => {
      if (mat.map) mat.map.anisotropy = 4;
      if (mat.transparent || mat.alphaTest > 0) {
        mat.alphaTest = Math.max(mat.alphaTest, 0.4); mat.transparent = false; mat.side = THREE.DoubleSide;
        // with MSAA, alpha-to-coverage keeps distant foliage cards from thinning out
        if (_msaa) mat.alphaToCoverage = true;
      }
    });
    if (mats.length > 1) {
      // split multi-material geometry by group
      o.geometry.groups.forEach((gr) => {
        const geo = o.geometry.clone();
        geo.clearGroups(); geo.setIndex(Array.from(o.geometry.index.array.slice(gr.start, gr.start + gr.count)));
        parts.push({ geo, mat: mats[gr.materialIndex], m });
      });
    } else parts.push({ geo: o.geometry, mat: mats[0], m });
    o.geometry.computeBoundingSphere();
    radius = Math.max(radius, o.geometry.boundingSphere.radius + o.geometry.boundingSphere.center.length());
  });
  return parts.length ? { parts, radius } : null;
}

const kindCache = {};
const IMPOSTOR = new Set(['Pine_A', 'Pine_B', 'Pine_Snow', 'DeadTree', 'Saguaro', 'Joshua']);
let _renderer = null;
export function setImpostorRenderer(r) { _renderer = r; }

// Bake a kind into a two-card impostor (front + side views) for distant tiles.
function buildImpostor(name) {
  const K = getKind(name);
  if (!_renderer) return K;
  const scene = new THREE.Scene();
  const box = new THREE.Box3();
  for (const p of K.parts) {
    const m = new THREE.Mesh(p.geo, p.mat); m.matrixAutoUpdate = false; m.matrix.copy(p.m); scene.add(m);
    p.geo.computeBoundingBox(); box.union(p.geo.boundingBox.clone().applyMatrix4(p.m));
  }
  scene.add(new THREE.AmbientLight(0xffffff, 1.4), new THREE.HemisphereLight(0xffffff, 0x888888, 1.2));
  const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const W = Math.max(size.x, size.z) * 1.02, H = size.y * 1.02;
  const rt = new THREE.WebGLRenderTarget(512, 512, { generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter });
  const cam = new THREE.OrthographicCamera(-W / 2, W / 2, H / 2, -H / 2, 0.1, 200);
  const r = _renderer, prevT = r.getRenderTarget(), prevC = r.getClearColor(new THREE.Color()), prevA = r.getClearAlpha();
  r.setRenderTarget(rt); r.setClearColor(0x000000, 0); r.clear();
  const views = [new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0)];
  views.forEach((v, i) => {
    cam.position.copy(c).addScaledVector(v, 100); cam.lookAt(c); cam.updateMatrixWorld();
    r.setViewport(i * 256, 0, 256, 512); r.setScissor(i * 256, 0, 256, 512); r.setScissorTest(true);
    r.render(scene, cam);
  });
  r.setScissorTest(false); r.setViewport(0, 0, r.domElement.width, r.domElement.height);
  r.setRenderTarget(prevT); r.setClearColor(prevC, prevA);
  const mat = new THREE.MeshStandardMaterial({ map: rt.texture, alphaTest: 0.5, side: THREE.DoubleSide, roughness: 0.95 });
  if (_msaa) mat.alphaToCoverage = true;
  const mk = (u0, rotY) => {
    const g = new THREE.PlaneGeometry(W, H).translate(0, c.y, 0);
    const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setX(i, u0 + uv.getX(i) * 0.5);
    g.rotateY(rotY); g.translate(c.x * 0, 0, 0);
    const nrm = g.attributes.normal; for (let i = 0; i < nrm.count; i++) nrm.setXYZ(i, 0, 1, 0);
    return g;
  };
  const parts = [{ geo: mergeSimple([mk(0, 0), mk(0.5, Math.PI / 2)]), mat, m: new THREE.Matrix4() }];
  return { parts, radius: K.radius };
}
let _msaa = false;
export function getKind(name) {
  if (!kindCache[name]) {
    if (name.endsWith('#imp')) kindCache[name] = buildImpostor(name.slice(0, -4));
    else kindCache[name] = kindFromGLB(name) || fallbackKind(name);
  }
  return kindCache[name];
}
export function resetKinds() { for (const k in kindCache) delete kindCache[k]; }

// ----------------------------------------------------------------- scatter
export class Scatter {
  constructor(route, scene, quality) {
    this.route = route; this.scene = scene; this.q = quality;
    if (_msaa !== quality.msaa > 0) { _msaa = quality.msaa > 0; resetKinds(); }
    this.rules = route.def.scatter;
    this.byTile = new Map(); // key -> { kind -> Float32Array matrices }
    this.meshes = {};        // kind -> [InstancedMesh per part]
    this.group = new THREE.Group(); scene.add(this.group);
    this._sig = '';
    this._globalByTile = new Map();
    this._frustum = new THREE.Frustum(); this._pm = new THREE.Matrix4();
    this._box = new THREE.Box3();
    this._placeAlongRoad();
    this._initGrass();
  }

  _placeAlongRoad() {
    const r = this.route, rnd = mulberry32(r.def.seed + 99);
    const push = (kind, x, z, rotY, s = 1) => {
      if (r.railDist(x, z) < 6) return;          // nothing planted on the railroad
      const key = `${Math.floor(x / TILE)},${Math.floor(z / TILE)}`;
      if (!this._globalByTile.has(key)) this._globalByTile.set(key, []);
      this._globalByTile.get(key).push({ kind, x, z, rotY, s });
    };
    const poles = this.rules.find((q) => q.poles), fence = this.rules.find((q) => q.fence);
    const f = {};
    if (poles) {
      for (let s = 30; s < r.len; s += 42) {
        if (r.inTown(s)) continue;
        r.frame(s, f);
        const x = f.x + f.rx * 9.5, z = f.z + f.rz * 9.5;
        push('TelegraphPole', x, z, Math.atan2(f.tx, f.tz) + Math.PI / 2 + (rnd() - 0.5) * 0.1);
      }
    }
    if (fence) {
      let s = 60;
      while (s < r.len - 60) {
        const run = 60 + rnd() * 140, side = rnd() < 0.5 ? -1 : 1, off = 8 + rnd() * 5;
        for (let t = s; t < Math.min(r.len - 60, s + run); t += 3) {
          if (r.inTown(t)) continue;
          r.frame(t + 1.5, f);
          push('Fence_Rail', f.x + f.rx * off * side, f.z + f.rz * off * side, Math.atan2(f.tx, f.tz) + Math.PI / 2 + (rnd() - 0.5) * 0.08);
        }
        s += run + 80 + rnd() * 250;
      }
    }
  }

  // called by Terrain when a tile is created/removed
  onTile(tile, created) {
    if (!created) { this.byTile.delete(tile.key); this._dirty = true; return; }
    const r = this.route, rc = { d: 0, s: 0 };
    const seed = (tile.i * 73856093) ^ (tile.j * 19349663) ^ r.def.seed;
    const rnd = mulberry32(seed);
    const out = {};
    const area = (TILE * TILE) / 10000;
    for (const rule of this.rules) {
      if (!rule.density) continue;
      const n = Math.round(rule.density * area * this.q.scatter * (0.8 + rnd() * 0.4));
      const arr = [];
      for (let k = 0; k < n * 2 && arr.length < n * 16; k++) {
        const x = tile.x0 + rnd() * TILE, z = tile.z0 + rnd() * TILE;
        if (rule.cluster) {
          const c = r.noise(x / 90 + 33, z / 90 - 11) * 0.5 + 0.5;
          if (rnd() > smoothstep(rule.cluster, rule.cluster + 0.35, c)) continue;
        }
        r.roadCoords(x, z, rc);
        if (rc.s >= 0 && Math.abs(rc.d) < (rule.minRoad ?? 6)) continue;
        if (r.railDist(x, z) < 7) continue;
        const town = r.inTown(rc.s) || (r.townRange && rc.s > r.townRange.s0 - 30 && rc.s < r.townRange.s1 + 30) || rc.s < 130 || rc.s > r.len - 150;
        if (rc.s >= 0 && town && Math.abs(rc.d) < (rule.far ? 32 : 40)) continue;
        const h = r.height(x, z);
        if (rule.minH !== undefined && h < rule.minH) continue;
        if (rule.maxH !== undefined && h > rule.maxH) continue;
        const hx = r.height(x + 1.5, z) - h, hz = r.height(x, z + 1.5) - h;
        const slope = Math.hypot(hx, hz) / 1.5;
        if (rule.minSlope !== undefined ? slope < rule.minSlope : slope > 0.7) continue;
        const [s0, s1] = rule.scale || [1, 1];
        const s = s0 + rnd() * (s1 - s0);
        const m = new THREE.Matrix4().compose(
          new THREE.Vector3(x, h - 0.08 * s, z),
          new THREE.Quaternion().setFromEuler(new THREE.Euler((rnd() - 0.5) * 0.08, rnd() * Math.PI * 2, (rnd() - 0.5) * 0.08)),
          new THREE.Vector3(s, s * (0.9 + rnd() * 0.2), s));
        arr.push(...m.elements);
        if (arr.length >= n * 16) break;
      }
      if (arr.length) out[rule.kind] = new Float32Array(arr);
    }
    // road-aligned globals
    for (const g of this._globalByTile.get(tile.key) || []) {
      const h = r.height(g.x, g.z);
      const m = new THREE.Matrix4().compose(new THREE.Vector3(g.x, h - 0.1, g.z), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), g.rotY), new THREE.Vector3(g.s, g.s, g.s));
      const prev = out[g.kind];
      const add = new Float32Array(m.elements);
      if (prev) { const c = new Float32Array(prev.length + 16); c.set(prev); c.set(add, prev.length); out[g.kind] = c; } else out[g.kind] = add;
    }
    this.byTile.set(tile.key, { tile, kinds: out, grass: this._grassFor(tile, rnd) });
    this._dirty = true;
  }

  _ensureMeshes(kind, need) {
    let arr = this.meshes[kind];
    if (arr && arr[0].instanceMatrix.count >= need) return arr;
    const cap = Math.max(64, Math.ceil(need * 1.5));
    if (arr) arr.forEach((m) => { this.group.remove(m); m.dispose(); });
    const K = getKind(kind);
    arr = K.parts.map((p) => {
      const im = new THREE.InstancedMesh(p.geo, p.mat, cap);
      im.castShadow = true; im.receiveShadow = true;
      im.frustumCulled = false; im.count = 0;
      im.userData.local = p.m;
      im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      const tint = /^(Rock|Boulder|Cliff)/.test(kind) && this.route.def.terrain.propRock;
      if (tint) {
        const arr = new Float32Array(cap * 3);
        for (let i = 0; i < cap; i++) { arr[i * 3] = tint.r; arr[i * 3 + 1] = tint.g; arr[i * 3 + 2] = tint.b; }
        im.instanceColor = new THREE.InstancedBufferAttribute(arr, 3);
      }
      if (kind.endsWith('#imp')) im.castShadow = false;
      this.group.add(im);
      return im;
    });
    this.meshes[kind] = arr;
    return arr;
  }

  update(camera, focus) {
    this._pm.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this._frustum.setFromProjectionMatrix(this._pm);
    const vis = [];
    for (const [key, e] of this.byTile) {
      const t = e.tile;
      this._box.min.set(t.x0 - 12, -200, t.z0 - 12);
      this._box.max.set(t.x0 + TILE + 12, 600, t.z0 + TILE + 12);
      if (!this._frustum.intersectsBox(this._box)) continue;
      const d = Math.hypot(t.x0 + TILE / 2 - focus.x, t.z0 + TILE / 2 - focus.z);
      vis.push([key, d > 300 ? 2 : d > 170 ? 1 : 0, d]);
    }
    const sig = vis.map((v) => v[0] + v[1]).join('|');
    if (sig !== this._sig || this._dirty) {
      this._sig = sig; this._dirty = false;
      this._rebuild(vis);
    }
    this._updateGrass(camera, focus);
  }

  _rebuild(vis) {
    const farOnly = new Set(this.rules.filter((r) => r.far || r.poles).map((r) => r.kind));
    const lists = {};
    for (const [key, band] of vis) {
      const e = this.byTile.get(key);
      for (const kind in e.kinds) {
        if (band === 2 && !farOnly.has(kind)) continue;
        // mid/far trees become impostor cards
        const k = band >= 1 && IMPOSTOR.has(kind) && _renderer ? kind + '#imp' : kind;
        (lists[k] ||= []).push(e.kinds[kind]);
      }
    }
    const tmp = new THREE.Matrix4(), base = new THREE.Matrix4();
    for (const kind of Object.keys(this.meshes)) if (!lists[kind]) this.meshes[kind].forEach((m) => (m.count = 0));
    for (const kind in lists) {
      const total = lists[kind].reduce((a, b) => a + b.length / 16, 0);
      const meshes = this._ensureMeshes(kind, total);
      meshes.forEach((im) => {
        const dst = im.instanceMatrix.array;
        const local = im.userData.local;
        const ident = local.equals(new THREE.Matrix4());
        let o = 0;
        for (const src of lists[kind]) {
          if (ident) { dst.set(src, o * 16); o += src.length / 16; continue; }
          for (let k = 0; k < src.length; k += 16) {
            base.fromArray(src, k); tmp.multiplyMatrices(base, local); tmp.toArray(dst, o * 16); o++;
          }
        }
        im.count = o;
        im.instanceMatrix.needsUpdate = true;
      });
    }
  }

  // ------------------------------------------------------------------ grass
  _initGrass() {
    const G = this.route.def.grass;
    this.grassOn = this.q.grass > 0 && G.density > 0;
    if (!this.grassOn) return;
    // two crossed quads per clump
    const w = 0.9, h = 1;
    const q1 = new THREE.PlaneGeometry(w, h).translate(0, h / 2, 0);
    const q2 = q1.clone().rotateY(Math.PI / 2);
    const q3 = q1.clone().rotateY(Math.PI / 4);
    const geo = mergeSimple([q1, q2, q3]);
    // normals straight up for soft, uniform lighting
    const nrm = geo.attributes.normal;
    for (let i = 0; i < nrm.count; i++) nrm.setXYZ(i, 0, 1, 0);
    const mat = new THREE.MeshStandardMaterial({ map: grassTex(), alphaTest: 0.25, side: THREE.DoubleSide, color: G.color, roughness: 1 });
    mat.alphaToCoverage = this.q.msaa > 0;
    const T = this.route.def.terrain;
    this.grassU = {
      uTime: { value: 0 }, uWind: { value: this.route.def.wind }, uFocus: { value: new THREE.Vector3() },
      tMacro: { value: tex('cloud_noise') }, uGT1: { value: T.tint1 }, uGT2: { value: T.tint2 },
      uGMix: { value: new THREE.Vector2(...(T.greenMix || [0.42, 0.68])) },
    };
    mat.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, this.grassU);
      sh.vertexShader = sh.vertexShader.replace('#include <common>', `#include <common>
        uniform float uTime, uWind; uniform vec3 uFocus; varying float vGH; varying vec2 vGXZ;`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          vec3 ip = vec3(instanceMatrix[3][0], instanceMatrix[3][1], instanceMatrix[3][2]);
          float dist = length(ip.xz - uFocus.xz);
          float fade = 1.0 - smoothstep(30.0, 60.0, dist);
          vGXZ = ip.xz;
          transformed *= fade;
          float sway = sin(uTime * 1.7 + ip.x * 0.21 + ip.z * 0.17) * 0.5 + sin(uTime * 3.1 + ip.x * 0.7) * 0.2;
          transformed.x += sway * uWind * 0.18 * position.y;
          transformed.z += cos(uTime * 1.3 + ip.z * 0.2) * uWind * 0.1 * position.y;
          vGH = position.y;`);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
        uniform sampler2D tMacro; uniform vec3 uGT1, uGT2; uniform vec2 uGMix;
        varying float vGH; varying vec2 vGXZ;`).replace('#include <map_fragment>', `#include <map_fragment>
          // match the ground layer underneath (same macro noise as the terrain)
          float gm = smoothstep(uGMix.x, uGMix.y, texture2D(tMacro, vGXZ / 180.0).r);
          diffuseColor.rgb *= mix(uGT1, uGT2, gm) * mix(0.78, 1.12, clamp(vGH, 0.0, 1.0));`);
    };
    const cap = Math.floor(26000 * this.q.grass);
    this.grass = new THREE.InstancedMesh(geo, mat, cap);
    this.grass.frustumCulled = false; this.grass.count = 0; this.grass.receiveShadow = true;
    this.grass.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.group.add(this.grass);
    this._grassKey = '';
  }

  _grassFor(tile, rnd) {
    if (!this.grassOn) return null;
    const r = this.route, G = r.def.grass, rc = { d: 0, s: 0 };
    const n = Math.floor(2600 * G.density * this.q.grass);
    const arr = new Float32Array(n * 4); // x, y, z, scale|rot packed
    let c = 0;
    for (let k = 0; k < n * 1.6 && c < n; k++) {
      const x = tile.x0 + rnd() * TILE, z = tile.z0 + rnd() * TILE;
      const patch = r.noise(x / 14, z / 14) * 0.5 + 0.5;
      if (rnd() > patch * 1.3) continue;
      r.roadCoords(x, z, rc);
      if (rc.s >= 0 && Math.abs(rc.d) < ROAD_HALF + 0.6 + rnd() * 1.5) continue;
      if (r.railDist(x, z) < 3.4 + rnd() * 1.2) continue;   // ballast, not grass
      const h = r.height(x, z);
      const hx = r.height(x + 1, z) - h, hz = r.height(x, z + 1) - h;
      if (Math.hypot(hx, hz) > 0.5) continue;
      if (h > r.def.terrain.snowLine - 5) continue;
      arr[c * 4] = x; arr[c * 4 + 1] = h; arr[c * 4 + 2] = z; arr[c * 4 + 3] = (0.6 + rnd() * 0.8) * G.height * 1.6;
      c++;
    }
    return arr.subarray(0, c * 4);
  }

  _updateGrass(camera, focus) {
    if (!this.grassOn) return;
    this.grassU.uTime.value = performance.now() / 1000;
    this.grassU.uFocus.value.copy(camera.position);
    const cx = Math.round(camera.position.x / 12), cz = Math.round(camera.position.z / 12);
    const key = cx + ',' + cz + ',' + this.byTile.size;
    if (key === this._grassKey) return;
    this._grassKey = key;
    const px = camera.position.x, pz = camera.position.z, R2 = 64 * 64;
    const dst = this.grass.instanceMatrix.array, cap = this.grass.instanceMatrix.count;
    let o = 0;
    for (const e of this.byTile.values()) {
      const g = e.grass; if (!g) continue;
      const t = e.tile;
      if (px < t.x0 - 64 || px > t.x0 + TILE + 64 || pz < t.z0 - 64 || pz > t.z0 + TILE + 64) continue;
      for (let k = 0; k < g.length && o < cap; k += 4) {
        const dx = g[k] - px, dz = g[k + 2] - pz;
        if (dx * dx + dz * dz > R2) continue;
        const s = g[k + 3], rot = (g[k] * 12.9898 + g[k + 2] * 78.233) % 6.283;
        const cs = Math.cos(rot) * s, sn = Math.sin(rot) * s;
        const j = o * 16;
        dst[j] = cs; dst[j + 1] = 0; dst[j + 2] = -sn; dst[j + 3] = 0;
        dst[j + 4] = 0; dst[j + 5] = s; dst[j + 6] = 0; dst[j + 7] = 0;
        dst[j + 8] = sn; dst[j + 9] = 0; dst[j + 10] = cs; dst[j + 11] = 0;
        dst[j + 12] = g[k]; dst[j + 13] = g[k + 1] - 0.05; dst[j + 14] = g[k + 2]; dst[j + 15] = 1;
        o++;
      }
    }
    this.grass.count = o;
    this.grass.instanceMatrix.needsUpdate = true;
  }

  dispose() {
    this.scene.remove(this.group);
    Object.values(this.meshes).flat().forEach((m) => m.dispose());
    this.grass?.dispose();
  }
}

function mergeSimple(geos) {
  const pos = [], nor = [], uv = [], idx = [];
  let off = 0;
  for (const g of geos) {
    pos.push(...g.attributes.position.array); nor.push(...g.attributes.normal.array); uv.push(...g.attributes.uv.array);
    idx.push(...Array.from(g.index.array, (i) => i + off));
    off += g.attributes.position.count;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  return g;
}
