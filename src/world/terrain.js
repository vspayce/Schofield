// Streaming terrain tiles around the coach + splat material (road / two ground
// layers / tri-planar rock on steep slopes / snow above the snow line), built on
// MeshStandardMaterial so lighting, shadows and fog stay stock.
import * as THREE from 'three';
import { ROAD_HALF } from './route.js';
import { tex, flatNormal } from './textures.js';

const TILE = 128;

export function makeTerrainMaterial(route) {
  const T = route.def.terrain;
  const mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95, metalness: 0 });
  const uniforms = {
    tG1: { value: tex(T.ground1) }, tG2: { value: tex(T.ground2) }, tRoad: { value: tex(T.road) },
    tRock: { value: tex(T.rock) }, tSnow: { value: tex(T.snow || T.ground1) }, tMacro: { value: tex('cloud_noise') },
    uTint1: { value: T.tint1 }, uTint2: { value: T.tint2 }, uRockTint: { value: T.rockTint },
    uSnowLine: { value: T.snowLine }, uRoadHalf: { value: ROAD_HALF },
    uRockSlope: { value: T.rockSlope ?? (route.biome === 'canyon' ? 0.22 : 0.3) },
    uRoadTint: { value: T.roadTint || new THREE.Color(1, 1, 1) },
    uGreenMix: { value: new THREE.Vector2(...(T.greenMix || [0.42, 0.68])) },
    tG1N: { value: tex(T.ground1 + '_n') || flatNormal() }, tG2N: { value: tex(T.ground2 + '_n') || flatNormal() },
    tRoadN: { value: tex(T.road + '_n') || flatNormal() }, tRockN: { value: tex(T.rock + '_n') || flatNormal() },
  };
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, uniforms);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec2 aRoad; attribute float aSunVis;
        varying vec2 vRoad; varying vec3 vWPos; varying vec3 vWNorm; varying float vSunVis;`)
      .replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
        vRoad = aRoad; vSunVis = aSunVis;
        vWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
        vWNorm = normalize(mat3(modelMatrix) * objectNormal);`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D tG1, tG2, tRoad, tRock, tSnow, tMacro, tG1N, tG2N, tRoadN, tRockN;
        vec3 gWN;
        uniform vec3 uTint1, uTint2, uRockTint;
        uniform float uSnowLine, uRoadHalf, uRockSlope;
        uniform vec3 uRoadTint; uniform vec2 uGreenMix;
        varying vec2 vRoad; varying vec3 vWPos; varying vec3 vWNorm; varying float vSunVis;
        float gRough;
        vec3 sampleAT(sampler2D t, vec2 uv, float m) {
          // two scales, rotated, blended by macro noise -> kills visible tiling
          vec3 a = texture2D(t, uv).rgb;
          vec3 b = texture2D(t, uv * 0.37 + vec2(0.31, 0.77)).rgb;
          return mix(a, b, smoothstep(0.35, 0.65, m));
        }`)
      .replace('#include <map_fragment>', `
        vec2 wxz = vWPos.xz;
        float m1 = texture2D(tMacro, wxz / 180.0).r;
        float m2 = texture2D(tMacro, wxz / 37.0 + 0.5).r;
        vec3 g1 = sampleAT(tG1, wxz / 4.0, m2) * uTint1;
        vec3 g2 = sampleAT(tG2, wxz / 5.0, m2) * uTint2;
        vec3 ground = mix(g1, g2, smoothstep(uGreenMix.x, uGreenMix.y, m1 + (m2 - 0.5) * 0.3));
        ground *= 0.82 + 0.36 * m2; // large-scale brightness variation

        // road: along-road UV so ruts follow the road
        float ad = abs(vRoad.x);
        vec2 ruv = vec2(vRoad.x / 4.0, vRoad.y / 4.0);
        vec3 road = texture2D(tRoad, ruv).rgb * uRoadTint;
        road *= 0.9 + 0.2 * m2; // large-scale wear variation
        float rut = smoothstep(0.55, 0.0, abs(ad - 0.82)) * 0.22 + smoothstep(0.5, 0.0, abs(ad - 1.95)) * 0.1;
        road *= 1.0 - rut;
        float edgeN = (m2 - 0.5) * 1.6;
        float roadW = 1.0 - smoothstep(uRoadHalf - 0.9, uRoadHalf + 1.2, ad + edgeN);
        // worn grass verge
        ground = mix(ground, mix(ground, road, 0.55), (1.0 - smoothstep(uRoadHalf + 0.5, uRoadHalf + 3.5, ad + edgeN)) * 0.6);

        // tri-planar rock on steep slopes
        vec3 n = normalize(vWNorm);
        float slope = 1.0 - n.y;
        vec3 bw = pow(abs(n), vec3(4.0)); bw /= (bw.x + bw.y + bw.z);
        // warp the rock UVs by the macro noise: the crack motif repeated on an
        // obvious grid on long cliff faces, and a warp breaks the lattice up
        // without paying for more texture reads
        vec2 rwarp = (vec2(m1, m2) - 0.5) * 5.0;
        vec3 rx = texture2D(tRock, (vWPos.zy + rwarp) / 11.0).rgb;
        vec3 ry = texture2D(tRock, (vWPos.xz + rwarp) / 11.0).rgb;
        vec3 rz = texture2D(tRock, (vWPos.xy + rwarp) / 11.0).rgb;
        vec3 rock = (rx * bw.x + ry * bw.y + rz * bw.z) * uRockTint;
        float rockW = smoothstep(uRockSlope, uRockSlope + 0.14, slope + (m2 - 0.5) * 0.18 + (m1 - 0.5) * 0.25);

        vec3 col = mix(ground, rock, rockW);
        col = mix(col, road, roadW * (1.0 - rockW * 0.8));

        // snow above the snow line, favouring flat ground
        float sn = smoothstep(uSnowLine - 6.0, uSnowLine + 8.0, vWPos.y + (m1 - 0.5) * 20.0) * smoothstep(0.55, 0.25, slope);
        sn *= 1.0 - roadW; // the road is kept clear
        vec3 snow = texture2D(tSnow, wxz / 6.0).rgb;
        col = mix(col, snow, sn);

        gRough = mix(mix(0.97, 0.86, rockW), 0.62, sn);

        // detail normals (UDN blend on the XZ plane; tri-planar side for rock)
        float gMix = smoothstep(uGreenMix.x, uGreenMix.y, m1 + (m2 - 0.5) * 0.3);
        vec2 ng = mix(texture2D(tG1N, wxz / 4.0).xy, texture2D(tG2N, wxz / 5.0).xy, gMix) * 2.0 - 1.0;
        vec2 nr = texture2D(tRoadN, ruv).xy * 2.0 - 1.0;
        // road UV runs across/along the road; rotate its tangent frame roughly into world by using the ground frame (subtle anyway)
        vec2 nd = mix(ng * 0.7, nr, roadW);
        vec3 wn = normalize(n + vec3(nd.x, 0.0, nd.y) * (1.0 - rockW) * (1.0 - sn * 0.6));
        vec2 nrx = texture2D(tRockN, (vWPos.zy + rwarp) / 11.0).xy * 2.0 - 1.0;
        vec2 nrz = texture2D(tRockN, (vWPos.xy + rwarp) / 11.0).xy * 2.0 - 1.0;
        vec3 rockPert = vec3(0.0, nrx.y, nrx.x) * bw.x + vec3(nrz.x, nrz.y, 0.0) * bw.z;
        gWN = normalize(wn + rockPert * rockW * 0.9);
        diffuseColor.rgb *= col;
      `)
      .replace('#include <roughnessmap_fragment>', `float roughnessFactor = gRough;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        normal = normalize((viewMatrix * vec4(gWN, 0.0)).xyz);`)
      .replace('#include <lights_fragment_end>', `#include <lights_fragment_end>
        // baked terrain self-shadow (ridges / canyon walls beyond the shadow map)
        reflectedLight.directDiffuse *= vSunVis;
        reflectedLight.directSpecular *= vSunVis;`);
  };
  mat.customProgramCacheKey = () => 'terrain-' + route.def.id;
  return mat;
}

export class Terrain {
  constructor(route, scene, quality) {
    this.route = route; this.scene = scene; this.q = quality;
    this.mat = makeTerrainMaterial(route);
    const L = route.def.light;
    this.sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - L.sunElev), THREE.MathUtils.degToRad(L.sunAzim));
    this.tiles = new Map();
    this.queue = [];
    this.radius = quality.drawDist;
    this.onTile = null;     // callback(tile, created|removed)
    this.group = new THREE.Group();
    scene.add(this.group);
  }

  _lodFor(dist) { return dist < 190 ? 64 : dist < 380 ? 32 : 16; }

  // Called every frame with the focus point (coach). Builds at most `budget` tiles.
  update(fx, fz, budget = 2) {
    const R = this.radius;
    const want = new Map();
    const i0 = Math.floor((fx - R) / TILE), i1 = Math.floor((fx + R) / TILE);
    const j0 = Math.floor((fz - R) / TILE), j1 = Math.floor((fz + R) / TILE);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const cx = (i + 0.5) * TILE, cz = (j + 0.5) * TILE;
      const d = Math.max(0, Math.hypot(cx - fx, cz - fz) - TILE * 0.7);
      if (d > R) continue;
      want.set(`${i},${j}`, { i, j, lod: this._lodFor(d), d });
    }
    for (const [k, t] of this.tiles) if (!want.has(k)) this._remove(k, t);
    const todo = [];
    for (const [k, w] of want) {
      const t = this.tiles.get(k);
      if (!t || t.lod !== w.lod) todo.push([k, w]);
    }
    todo.sort((a, b) => a[1].d - b[1].d);
    for (let n = 0; n < Math.min(budget, todo.length); n++) this._build(todo[n][0], todo[n][1]);
    return todo.length;
  }

  // synchronously build everything needed at a point (loading screen)
  prime(fx, fz) { while (this.update(fx, fz, 8) > 0); }

  _remove(k, t) {
    this.group.remove(t.mesh);
    t.mesh.geometry.dispose();
    this.tiles.delete(k);
    this.onTile?.(t, false);
  }

  _build(k, { i, j, lod }) {
    const old = this.tiles.get(k);
    const n = lod, step = TILE / n, x0 = i * TILE, z0 = j * TILE;
    const S = n + 3; // with 1-sample border for normals
    const H = new Float32Array(S * S);
    const route = this.route;
    for (let b = 0; b < S; b++) for (let a = 0; a < S; a++) H[b * S + a] = route.height(x0 + (a - 1) * step, z0 + (b - 1) * step);
    const V = n + 1;
    const edge = 4 * n;
    const vcount = V * V + edge;
    const pos = new Float32Array(vcount * 3), nor = new Float32Array(vcount * 3), road = new Float32Array(vcount * 2);
    const rc = { d: 0, s: 0 };
    let p = 0;
    for (let b = 0; b < V; b++) for (let a = 0; a < V; a++, p++) {
      const x = x0 + a * step, z = z0 + b * step;
      const h = H[(b + 1) * S + (a + 1)];
      pos[p * 3] = x; pos[p * 3 + 1] = h; pos[p * 3 + 2] = z;
      const hl = H[(b + 1) * S + a], hr = H[(b + 1) * S + a + 2], hd = H[b * S + a + 1], hu = H[(b + 2) * S + a + 1];
      let nx = hl - hr, ny = 2 * step, nz = hd - hu;
      const l = Math.hypot(nx, ny, nz); nor[p * 3] = nx / l; nor[p * 3 + 1] = ny / l; nor[p * 3 + 2] = nz / l;
      route.roadCoords(x, z, rc);
      road[p * 2] = rc.s < 0 ? 99 : Math.abs(rc.d); road[p * 2 + 1] = Math.max(0, rc.s);
    }
    // sun visibility: march toward the sun on a coarse 17x17 grid, interpolate to vertices
    const sunVis = new Float32Array(vcount);
    const SG = 16, sg = TILE / SG, vis = new Float32Array((SG + 1) * (SG + 1));
    const sd = this.sunDir;
    for (let b = 0; b <= SG; b++) for (let a = 0; a <= SG; a++) {
      const x = x0 + a * sg, z = z0 + b * sg;
      const h0 = route.height(x, z) + 0.5;
      let v = 1, t = 3;
      while (t < 520) {
        const hx = x + sd.x * t, hz = z + sd.z * t, hy = h0 + sd.y * t;
        const d = route.height(hx, hz) - hy;
        if (d > 0) { v = Math.max(0, v - Math.min(1, d / 6)); if (v <= 0) break; }
        t *= 1.18;
      }
      vis[b * (SG + 1) + a] = v;
    }
    const kk = n / SG;
    for (let b = 0; b < V; b++) for (let a = 0; a < V; a++) {
      const fa = a / kk, fb = b / kk, ia = Math.min(SG - 1, fa | 0), ib = Math.min(SG - 1, fb | 0), ta = fa - ia, tb = fb - ib;
      const r0 = vis[ib * (SG + 1) + ia] * (1 - ta) + vis[ib * (SG + 1) + ia + 1] * ta;
      const r1 = vis[(ib + 1) * (SG + 1) + ia] * (1 - ta) + vis[(ib + 1) * (SG + 1) + ia + 1] * ta;
      sunVis[b * V + a] = 0.12 + 0.88 * (r0 * (1 - tb) + r1 * tb);
    }
    const idx = [];
    for (let b = 0; b < n; b++) for (let a = 0; a < n; a++) {
      const v0 = b * V + a, v1 = v0 + 1, v2 = v0 + V, v3 = v2 + 1;
      idx.push(v0, v2, v1, v1, v2, v3);
    }
    // skirts
    const ring = [];
    for (let a = 0; a < n; a++) ring.push(a);                 // bottom row
    for (let b = 0; b < n; b++) ring.push(b * V + n);         // right col
    for (let a = n; a > 0; a--) ring.push(n * V + a);         // top row
    for (let b = n; b > 0; b--) ring.push(b * V);             // left col
    const skirt0 = V * V;
    ring.forEach((src, r) => {
      const q = skirt0 + r;
      pos[q * 3] = pos[src * 3]; pos[q * 3 + 1] = pos[src * 3 + 1] - 6; pos[q * 3 + 2] = pos[src * 3 + 2];
      nor[q * 3] = nor[src * 3]; nor[q * 3 + 1] = nor[src * 3 + 1]; nor[q * 3 + 2] = nor[src * 3 + 2];
      road[q * 2] = road[src * 2]; road[q * 2 + 1] = road[src * 2 + 1];
      sunVis[q] = sunVis[src];
    });
    for (let r = 0; r < ring.length; r++) {
      const a0 = ring[r], a1 = ring[(r + 1) % ring.length], s0 = skirt0 + r, s1 = skirt0 + ((r + 1) % ring.length);
      idx.push(a0, a1, s0, a1, s1, s0);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    g.setAttribute('aRoad', new THREE.BufferAttribute(road, 2));
    g.setAttribute('aSunVis', new THREE.BufferAttribute(sunVis, 1));
    g.setIndex(idx);
    g.computeBoundingSphere();
    const mesh = new THREE.Mesh(g, this.mat);
    mesh.receiveShadow = true;
    mesh.castShadow = lod === 64 && this.route.biome !== 'plains';
    mesh.matrixAutoUpdate = false;
    this.group.add(mesh);
    if (old) { this.group.remove(old.mesh); old.mesh.geometry.dispose(); }
    const t = { key: k, i, j, lod, mesh, x0, z0, size: TILE };
    this.tiles.set(k, t);
    if (!old) this.onTile?.(t, true);
  }

  // Ray march against the height field (for bullets hitting the ground).
  raycast(origin, dir, maxDist = 400) {
    let t = 0, prevT = 0, step = 1.5;
    const r = this.route;
    let prevDiff = origin.y - r.height(origin.x, origin.z);
    while (t < maxDist) {
      t += step;
      const x = origin.x + dir.x * t, y = origin.y + dir.y * t, z = origin.z + dir.z * t;
      const diff = y - r.height(x, z);
      if (diff < 0) {
        // bisect
        let a = prevT, b = t;
        for (let k = 0; k < 6; k++) {
          const m = (a + b) / 2;
          const dm = origin.y + dir.y * m - r.height(origin.x + dir.x * m, origin.z + dir.z * m);
          if (dm < 0) b = m; else a = m;
        }
        return b;
      }
      prevT = t; prevDiff = diff;
      step = Math.min(8, Math.max(1.5, diff * 0.5));
    }
    return Infinity;
  }
}

export { TILE };
