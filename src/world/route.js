// A route: a winding road spline sampled every metre, plus the terrain height
// function that carves the road into the land. A distance field around the road
// gives, for any world XZ, the nearest road station `s` and signed lateral `d`.
import * as THREE from 'three';
import { makeNoise2D, fbm, ridged, mulberry32, smoothstep, lerp, clamp } from '../core/noise.js';

export const ROAD_HALF = 4.2;
const CELL = 2;

export class Route {
  constructor(def) {
    this.def = def;
    this.biome = def.biome;
    if (this.biome === 'gorge') {
      const gd = def.gorge || {};
      this.riverSide = gd.side ?? 1;        // which hand the water is on
      this.gorgeDepth = gd.depth ?? 26;     // road ledge height above the water
      this.falls = gd.falls ? { s: def.length * gd.falls.at, drop: gd.falls.drop ?? 30, width: gd.falls.width ?? 26 } : null;
    }
    this.len = def.length;
    this.noise = makeNoise2D(def.seed);
    this.noise2 = makeNoise2D(def.seed * 7 + 3);
    this.rand = mulberry32(def.seed);
    this._buildPath();
    this._buildRoadHeights();
    this._buildField();
    this._town = def.ghostTown ? { s0: def.ghostTown.start * this.len, s1: def.ghostTown.start * this.len + def.ghostTown.length } : null;
  }

  // ------------------------------------------------------------------ path
  _buildPath() {
    const def = this.def, r = this.rand;
    const pts = [];
    let x = 0, z = 0, h = Math.PI; // heading: start travelling toward -Z
    const step = 60;
    const n = Math.ceil((this.len + 400) / step) + 2;
    // lead-in so the start town sits on a straight
    for (let i = 0; i < n; i++) {
      pts.push(new THREE.Vector3(x, 0, z));
      const t = i * step;
      const inTown = def.ghostTown && t > def.ghostTown.start * this.len - 120 && t < def.ghostTown.start * this.len + def.ghostTown.length + 60;
      const straight = i < 3 || t > this.len - 60 || inTown;
      if (!straight) {
        const w = def.winding;
        h += (this.noise(i * 0.23, 5.1) * 0.9 + (r() - 0.5) * 0.35) * w;
      }
      x += Math.sin(h) * step; z += Math.cos(h) * step;
    }
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal', 0.5);
    const total = curve.getLength();
    const N = Math.floor(total);
    this.samples = N;
    const P = curve.getSpacedPoints(N);
    this.px = new Float32Array(N + 1); this.pz = new Float32Array(N + 1);
    this.tx = new Float32Array(N + 1); this.tz = new Float32Array(N + 1);
    for (let i = 0; i <= N; i++) { this.px[i] = P[i].x; this.pz[i] = P[i].z; }
    // spacing = total/N ≈ 1 m
    this.ds = total / N;
    for (let i = 0; i <= N; i++) {
      const a = Math.max(0, i - 2), b = Math.min(N, i + 2);
      let dx = this.px[b] - this.px[a], dz = this.pz[b] - this.pz[a];
      const l = Math.hypot(dx, dz) || 1;
      this.tx[i] = dx / l; this.tz[i] = dz / l;
    }
    this.total = total;
    // curvature (signed) for coach body roll
    this.curv = new Float32Array(N + 1);
    for (let i = 0; i <= N; i++) {
      const a = Math.max(0, i - 6), b = Math.min(N, i + 6);
      const c = this.tx[a] * this.tz[b] - this.tz[a] * this.tx[b];
      this.curv[i] = c / ((b - a) * this.ds || 1);
    }
  }

  // ------------------------------------------------------------ natural land
  natural(x, z) {
    const n = this.noise, n2 = this.noise2;
    switch (this.biome) {
      case 'plains': {
        const big = fbm(n, x / 700, z / 700, 4) * 26;
        const mid = fbm(n2, x / 160, z / 160, 4) * 6;
        // rolling billows (no pyramid ridges); a far range of ridged hills beyond ~1 km of the start
        const hills = Math.pow(fbm(n, x / 260 + 11, z / 260, 4) * 0.5 + 0.5, 2.2) * 30;
        return big + mid + hills;
      }
      case 'mountain': {
        const r = ridged(n, x / 650, z / 650, 5) * 170;
        const m = fbm(n2, x / 220, z / 220, 4) * 38;
        const d = fbm(n, x / 60, z / 60, 3) * 4;
        return r + m + d - 40;
      }
      case 'desert': {
        const big = fbm(n, x / 800, z / 800, 3) * 18;
        const mid = fbm(n2, x / 180, z / 180, 3) * 4;
        // mesas: terraced blobs
        let mesa = smoothstep(0.35, 0.42, fbm(n2, x / 520 + 3, z / 520 - 9, 3)) * 55;
        mesa = Math.floor(mesa / 11) * 11 + (mesa % 11) * 0.15;
        return big + mid + mesa;
      }
      case 'gorge': {
        // high forested shoulders falling into a cut river valley
        const big = fbm(n, x / 520, z / 520, 4) * 70;
        const ridge = ridged(n2, x / 300 + 5, z / 300, 4) * 48;
        const mid = fbm(n2, x / 120, z / 120, 3) * 9;
        return big + ridge + mid + 20;
      }
      case 'canyon': {
        let plat = 62 + fbm(n, x / 400, z / 400, 4) * 22;
        const terr = fbm(n2, x / 90, z / 90, 3) * 10;
        plat = Math.floor(plat / 9) * 9 + (plat % 9) * 0.25; // strata terraces
        return plat + terr;
      }
    }
    return 0;
  }

  _buildRoadHeights() {
    const N = this.samples;
    const raw = new Float32Array(N + 1);
    for (let i = 0; i <= N; i++) raw[i] = this.biome === 'canyon' ? 0 : this.natural(this.px[i], this.pz[i]);
    // smooth along the road (box blur x3 ≈ gaussian)
    const win = this.biome === 'mountain' ? 70 : 110;
    let a = raw, b = new Float32Array(N + 1);
    for (let pass = 0; pass < 3; pass++) {
      let acc = 0, cnt = 0;
      for (let i = -win; i <= N + win; i++) {
        const add = i + win, rem = i - win - 1;
        if (add >= 0 && add <= N) { acc += a[add]; cnt++; }
        if (rem >= 0 && rem <= N) { acc -= a[rem]; cnt--; }
        if (i >= 0 && i <= N) b[i] = acc / cnt;
      }
      [a, b] = [b, a];
    }
    // limit grade
    const maxG = this.biome === 'mountain' ? 0.09 : 0.05;
    for (let i = 1; i <= N; i++) a[i] = clamp(a[i], a[i - 1] - maxG * this.ds, a[i - 1] + maxG * this.ds);
    for (let i = N - 1; i >= 0; i--) a[i] = clamp(a[i], a[i + 1] - maxG * this.ds, a[i + 1] + maxG * this.ds);
    this.roadH = a;
  }

  // ------------------------------------------------------ road distance field
  _buildField() {
    const R = this.biome === 'canyon' ? 110 : this.biome === 'mountain' ? 70 : 60;
    this.fieldR = R;
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (let i = 0; i <= this.samples; i++) {
      minX = Math.min(minX, this.px[i]); maxX = Math.max(maxX, this.px[i]);
      minZ = Math.min(minZ, this.pz[i]); maxZ = Math.max(maxZ, this.pz[i]);
    }
    minX -= R + 4; minZ -= R + 4; maxX += R + 4; maxZ += R + 4;
    const W = Math.ceil((maxX - minX) / CELL) + 1, H = Math.ceil((maxZ - minZ) / CELL) + 1;
    this.fx0 = minX; this.fz0 = minZ; this.fW = W; this.fH = H;
    const dist2 = new Float32Array(W * H).fill(R * R);
    const fd = new Float32Array(W * H).fill(R);
    const fs = new Float32Array(W * H).fill(-1);
    const rc = Math.ceil(R / CELL);
    for (let i = 0; i <= this.samples; i += 2) {
      const px = this.px[i], pz = this.pz[i], tx = this.tx[i], tz = this.tz[i];
      const cx = Math.round((px - minX) / CELL), cz = Math.round((pz - minZ) / CELL);
      for (let gz = Math.max(0, cz - rc); gz <= Math.min(H - 1, cz + rc); gz++) {
        const wz = minZ + gz * CELL - pz;
        for (let gx = Math.max(0, cx - rc); gx <= Math.min(W - 1, cx + rc); gx++) {
          const wx = minX + gx * CELL - px;
          const d2 = wx * wx + wz * wz;
          const k = gz * W + gx;
          if (d2 < dist2[k]) {
            dist2[k] = d2;
            // signed lateral along right = (-tz, tx) (facing +Z, right is -X)
            const lat = wx * -tz + wz * tx;
            const along = wx * tx + wz * tz;
            fd[k] = lat; // right-positive
            fs[k] = i * this.ds + along;
          }
        }
      }
    }
    this.fd = fd; this.fs = fs;
  }

  // returns {d, s} (d = R, s = -1 when far from road)
  roadCoords(x, z, out) {
    const gx = (x - this.fx0) / CELL, gz = (z - this.fz0) / CELL;
    const W = this.fW, H = this.fH;
    if (gx < 0 || gz < 0 || gx >= W - 1 || gz >= H - 1) { out.d = this.fieldR; out.s = -1; return out; }
    const ix = gx | 0, iz = gz | 0, fx = gx - ix, fz = gz - iz;
    const k = iz * W + ix;
    const s00 = this.fs[k], s10 = this.fs[k + 1], s01 = this.fs[k + W], s11 = this.fs[k + W + 1];
    // if the four corners come from very different stations (inside of a hairpin) use nearest
    const d00 = this.fd[k], d10 = this.fd[k + 1], d01 = this.fd[k + W], d11 = this.fd[k + W + 1];
    const smin = Math.min(s00, s10, s01, s11), smax = Math.max(s00, s10, s01, s11);
    if (smin < 0 || smax - smin > 12) {
      const kk = (fz < 0.5 ? iz : iz + 1) * W + (fx < 0.5 ? ix : ix + 1);
      out.d = this.fd[kk]; out.s = this.fs[kk];
      if (out.s < 0) out.d = this.fieldR;
      return out;
    }
    out.d = lerp(lerp(d00, d10, fx), lerp(d01, d11, fx), fz);
    out.s = lerp(lerp(s00, s10, fx), lerp(s01, s11, fx), fz);
    return out;
  }

  roadHeightAt(s) {
    const f = clamp(s / this.ds, 0, this.samples);
    const i = Math.min(this.samples - 1, f | 0), t = f - i;
    return lerp(this.roadH[i], this.roadH[i + 1], t);
  }

  // ------------------------------------------------------------ final height
  height(x, z) {
    const rc = this.roadCoords(x, z, _rc);
    const nat = this.natural(x, z);
    if (rc.s < 0) return nat;
    const ad = Math.abs(rc.d);
    const rh = this.roadHeightAt(rc.s);
    // road crown + ditches
    const crown = -0.012 * ad * ad * (ad < ROAD_HALF ? 1 : 0) - (ad > ROAD_HALF ? 0.25 * smoothstep(ROAD_HALF, ROAD_HALF + 1.5, ad) * (1 - smoothstep(ROAD_HALF + 2, ROAD_HALF + 5, ad)) : 0);
    let blendW = this.def.terrain.blend;
    // towns: wide flat pads
    let townFlat = 0;
    if (rc.s < 140) townFlat = 1 - smoothstep(90, 140, rc.s);
    if (rc.s > this.len - 150) townFlat = Math.max(townFlat, smoothstep(this.len - 150, this.len - 90, rc.s));
    if (this._town && rc.s > this._town.s0 - 60 && rc.s < this._town.s1 + 60)
      townFlat = Math.max(townFlat, smoothstep(this._town.s0 - 60, this._town.s0, rc.s) * (1 - smoothstep(this._town.s1, this._town.s1 + 60, rc.s)));
    if (this.biome === 'gorge') {
      // A shelf blasted into the valley side: road level out to the shoulder,
      // then the ground drops away hard on the river side and climbs on the
      // other. riverD is which side the water is on.
      const sideD = rc.d * this.riverSide;          // >0 = the river side
      const shelf = ROAD_HALF + 3.4;
      const wallGrain = fbm(this.noise2, x / 16, z / 16, 3) * 5 + Math.abs(this.noise(x / 46 + 3, z / 46)) * 4;
      if (sideD > 0) {
        // drop to the water: steep bank, then the river bed
        const t = smoothstep(shelf, shelf + 26, sideD + wallGrain * 0.5);
        const bed = this.riverBedAt(rc.s) - 1.2 + fbm(this.noise, x / 30, z / 30, 2) * 1.4;
        return lerp(rh + crown, bed, t * t * (3 - 2 * t));
      }
      // the inland side climbs into the valley wall
      const t = smoothstep(shelf, shelf + 34, -sideD + wallGrain * 0.7);
      return lerp(rh + crown, Math.max(nat, rh + 12) + wallGrain * 0.8, t * t * (3 - 2 * t));
    }
    if (this.biome === 'canyon') {
      // canyon walls: sandy floor, then steep stepped walls up to the plateau
      const floorW = 16 + 6 * this.noise(rc.s / 120, 1.7);
      // buttresses and gullies break up the walls
      const gully = fbm(this.noise2, x / 14, z / 14, 3) * 7 + Math.abs(this.noise(x / 40 + 7, z / 40)) * 6;
      let w = smoothstep(floorW, floorW + 28, ad + this.noise(x / 25, z / 25) * 4 + gully * 0.6);
      w = w * w * (3 - 2 * w);
      const flatW = 1 - townFlat * (1 - smoothstep(30, 60, ad));
      // talus: a little rubble slope at the foot of the walls
      const talus = smoothstep(floorW - 4, floorW + 6, ad) * (1 - w) * 3;
      return lerp(rh + crown + talus, nat + gully * 0.4, w * flatW);
    }
    const inner = ROAD_HALF + 2 + townFlat * 40;
    const w = smoothstep(inner, inner + blendW + townFlat * 30, ad + this.noise(x / 40, z / 40) * 3);
    return lerp(rh + crown, nat, w);
  }

  // --------------------------------------------------------------- river
  // Bed height under the river at station s — a steady fall down the valley,
  // the road ledge riding above it the whole way.
  riverBedAt(s) {
    return this.roadHeightAt(s) - this.gorgeDepth;
  }

  // The falls are a side stream off the inland wall that pours across the road
  // and on down into the river. `s` is where the curtain crosses the roadway —
  // this is the bit the coach bursts through.
  fallsAt() { return this.falls; }

  // ----------------------------------------------------------- road frames
  // world position of road station s with lateral offset d (right-positive)
  frame(s, out = {}) {
    const f = clamp(s / this.ds, 0, this.samples);
    const i = Math.min(this.samples - 1, f | 0), t = f - i;
    out.x = lerp(this.px[i], this.px[i + 1], t);
    out.z = lerp(this.pz[i], this.pz[i + 1], t);
    let tx = lerp(this.tx[i], this.tx[i + 1], t), tz = lerp(this.tz[i], this.tz[i + 1], t);
    const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    out.tx = tx; out.tz = tz;
    out.rx = -tz; out.rz = tx; // right vector: facing +Z, right is -X
    out.curv = lerp(this.curv[i], this.curv[i + 1], t);
    return out;
  }

  worldAt(s, d, target = new THREE.Vector3()) {
    const f = this.frame(s, _fr);
    const x = f.x + f.rx * d, z = f.z + f.rz * d;
    return target.set(x, this.height(x, z), z);
  }

  inTown(s) { return this._town && s > this._town.s0 && s < this._town.s1; }
  get townRange() { return this._town; }
}

const _rc = { d: 0, s: 0 };
const _fr = {};
