// Water for the river-gorge route: a river ribbon that follows the route spline,
// waterfall curtains the coach bursts through, and the spray / mist around both.
//
// Everything is custom ShaderMaterial in the style of sky.js and terrain.js —
// procedural textures (no new assets), scene fog handled through the stock fog
// chunks so the water sits in the same haze as the land, and one dispose() that
// gives every buffer back.
//
// Interface
//   const water = new Water(route, scene, renderer, {
//     river: { from: 0, to: 3000, d: -26, width: 34 },
//     falls: [{ s: 1500, d: 0, width: 26, top: 38, drop: 38 }],
//   });
//   water.update(dt, camera, coachPos);
//   water.levelAt(s)        -> river surface height at station s
//   water.throughFalls(p)   -> 0..1, how deep p is inside a falls curtain
//   water.rapidsAt(s)       -> 0..1 whitewater strength (for sound)
//   water.dispose();
//
// Falls heights: `drop` is the height of the curtain and `top` (default: `drop`)
// is how far the lip sits above the water it lands in, so the default is a fall
// that lands in the river. `s`/`d` are where the sheet crosses the ROADWAY — a
// side stream off the inland wall pours over the road there and carries on down
// to the river, so the curtain leans outward as it falls and its lip ends up
// inland of `d`. That lean is measured off the terrain; `lean: 0` makes the
// curtain vertical, and `ref: 'road'` / `lipY` / `baseY` place it by hand.
import * as THREE from 'three';
import { makeNoise2D, fbm, clamp, lerp, smoothstep } from '../core/noise.js';
import { tex, smokePuff, softDot } from './textures.js';

const LSTEP = 2;            // river level / rapids sampling step, metres

// ---------------------------------------------------------------- textures
// A tiling normal map for the surface chop. Sampled on a torus so it wraps, then
// differentiated into normals — the same trick textures.js uses for ground fills.
function waterNormalTex(size, seed) {
  const n = makeNoise2D(seed), n2 = makeNoise2D(seed * 3 + 11);
  const h = new Float32Array(size * size);
  const R1 = 3.2, R2 = 8.5;
  for (let y = 0; y < size; y++) {
    const b = (y / size) * Math.PI * 2, cb = Math.cos(b), sb = Math.sin(b);
    for (let x = 0; x < size; x++) {
      const a = (x / size) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
      h[y * size + x] =
        fbm(n, ca * R1 + cb * R1 * 0.75, sa * R1 + sb * R1 * 0.75, 4) * 1.0 +
        fbm(n2, ca * R2 - 7, sa * R2 + 3, 3) * 0.35;
    }
  }
  const d = new Uint8Array(size * size * 4);
  const str = 2.6;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const xm = (x - 1 + size) % size, xp = (x + 1) % size, ym = (y - 1 + size) % size, yp = (y + 1) % size;
    const gx = (h[y * size + xp] - h[y * size + xm]) * str;
    const gy = (h[yp * size + x] - h[ym * size + x]) * str;
    let nx = -gx, ny = -gy, nz = 1;
    const l = Math.hypot(nx, ny, nz); nx /= l; ny /= l; nz /= l;
    const k = (y * size + x) * 4;
    d[k] = (nx * 0.5 + 0.5) * 255; d[k + 1] = (ny * 0.5 + 0.5) * 255;
    d[k + 2] = (nz * 0.5 + 0.5) * 255; d[k + 3] = 255;
  }
  const t = new THREE.DataTexture(d, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true; t.anisotropy = 4;
  t.needsUpdate = true;
  return t;
}

// Falling-water streaks: noise stretched hard along V so it reads as long threads
// of water. r = broad threads, g = fine threads, b = droplet break-up.
function streakTex(w, hgt, seed) {
  const n = makeNoise2D(seed), n2 = makeNoise2D(seed + 5), n3 = makeNoise2D(seed + 9);
  const d = new Uint8Array(w * hgt * 4);
  for (let y = 0; y < hgt; y++) {
    const b = (y / hgt) * Math.PI * 2, cb = Math.cos(b), sb = Math.sin(b);
    for (let x = 0; x < w; x++) {
      const a = (x / w) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
      // high frequency across, low frequency down -> vertical streaks
      const v1 = fbm(n, ca * 7 + cb * 1.1, sa * 7 + sb * 1.1, 3) * 0.5 + 0.5;
      const v2 = fbm(n2, ca * 19 + cb * 2.2, sa * 19 + sb * 2.2, 2) * 0.5 + 0.5;
      const v3 = fbm(n3, ca * 11 + cb * 9, sa * 11 + sb * 9, 3) * 0.5 + 0.5;
      const k = (y * w + x) * 4;
      d[k] = clamp(Math.pow(v1, 1.4) * 300, 0, 255);
      d[k + 1] = clamp(Math.pow(v2, 1.7) * 320, 0, 255);
      d[k + 2] = clamp(Math.pow(v3, 2.2) * 340, 0, 255);
      d[k + 3] = 255;
    }
  }
  const t = new THREE.DataTexture(d, w, hgt, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true; t.anisotropy = 4;
  t.needsUpdate = true;
  return t;
}

// ------------------------------------------------------------------ shaders
// Shared by every water surface: the sky gradient (so reflections match sky.js)
// and the flow frame helpers.
const common = /* glsl */`
  uniform vec3 uSunDir, uSunCol, uZenith, uHorizon, uSunGlow, uHemiSky, uHemiGnd;
  uniform vec3 uShallow, uDeep, uFoamCol;
  uniform float uTime;
  vec3 skyAt(vec3 d) {
    float h = d.y;
    float sd = max(dot(d, uSunDir), 0.0);
    vec3 c = mix(uHorizon, uZenith, pow(smoothstep(-0.02, 0.6, h), 0.5));
    c += uSunGlow * 0.15 * (1.0 - clamp(h, 0.0, 1.0));
    c += uSunGlow * (pow(sd, 6.0) * 0.5 + pow(sd, 40.0) * 0.55);
    return c;
  }`;

const riverVert = /* glsl */`
  attribute vec4 aInfo;   // s, edge (0 centre .. 1 outer), depth m, rapid 0..1
  attribute vec2 aFlow;   // unit downstream direction in XZ
  varying vec3 vWPos; varying vec4 vInfo; varying vec2 vFlow;
  uniform float uTime, uSwell;
  #include <fog_pars_vertex>
  void main() {
    vec3 p = position;
    float inner = 1.0 - smoothstep(0.55, 1.0, aInfo.y);
    float sw = sin(aInfo.x * 0.42 + uTime * 1.7) * 0.6 + sin(aInfo.x * 0.15 - uTime * 1.15 + p.x * 0.07) * 0.4;
    p.y += sw * uSwell * inner * clamp(aInfo.z, 0.0, 1.0) * (1.0 + aInfo.w);
    vWPos = p; vInfo = aInfo; vFlow = aFlow;
    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const riverFrag = /* glsl */`
  ${common}
  uniform sampler2D tNorm, tFoam;
  uniform float uSpecPow, uFoam, uDetail, uOpacity;
  varying vec3 vWPos; varying vec4 vInfo; varying vec2 vFlow;
  #include <fog_pars_fragment>
  void main() {
    float edge = vInfo.y, depth = vInfo.z, rapid = vInfo.w;
    vec3 T = vec3(vFlow.x, 0.0, vFlow.y);
    vec3 R = vec3(vFlow.y, 0.0, -vFlow.x);
    // flow-space coordinates in metres: u across, v downstream
    float fu = dot(vWPos.xz, R.xz);
    float fv = dot(vWPos.xz, vFlow);
    float flowSpd = 0.55 + rapid * 1.9;

    vec2 n1 = texture2D(tNorm, vec2(fu / 9.0, fv / 13.0 - uTime * 0.075 * flowSpd)).xy * 2.0 - 1.0;
    vec2 n2 = texture2D(tNorm, vec2(fu / 2.9 + 0.37, fv / 3.6 - uTime * 0.26 * flowSpd)).xy * 2.0 - 1.0;
    vec2 pert = n1 * 0.55 + n2 * 0.9;
    if (uDetail > 0.0) {
      vec2 n3 = texture2D(tNorm, vec2(fu / 1.05 - 0.6, fv / 1.25 - uTime * 0.62 * flowSpd)).xy * 2.0 - 1.0;
      pert += n3 * 0.45 * uDetail;
    }
    // shallow water and rapids chop harder
    pert *= 1.0 + rapid * 2.4 + (1.0 - smoothstep(0.2, 1.6, depth)) * 0.9;
    vec3 N = normalize(vec3(0.0, 1.0, 0.0) + R * pert.x * 0.3 + T * pert.y * 0.3);

    vec3 V = normalize(cameraPosition - vWPos);
    float ndv = max(dot(N, V), 0.0);
    float F = 0.025 + 0.975 * pow(1.0 - ndv, 5.0);
    float lam = max(dot(N, uSunDir), 0.0);

    // depth colour: pale warm shallows, dark green-blue in the channel
    float dt = 1.0 - exp(-max(depth, 0.0) * 0.85);
    vec3 body = mix(uShallow, uDeep, dt);
    body *= mix(uHemiGnd, uHemiSky, 0.65) * 0.9 + uSunCol * lam * 0.55;
    body += uSunCol * (1.0 - dt) * 0.10 * lam;                 // light through the shallows

    vec3 refl = skyAt(reflect(-V, N));
    vec3 col = mix(body, refl, F * 0.88);

    // sun glint — sharp, and moving because N is animated
    vec3 H = normalize(uSunDir + V);
    float ndh = max(dot(N, H), 0.0);
    float spec = pow(ndh, uSpecPow) * 1.4 + pow(ndh, 24.0) * 0.06;
    col += uSunCol * spec * (2.2 + rapid * 2.0);

    // foam: a line along the true waterline (where the bed comes up through the
    // surface), a wash over the shallows, and whitewater through the rapids
    float f1 = texture2D(tFoam, vec2(fu / 6.0, fv / 7.0 - uTime * 0.2 * flowSpd)).r;
    float f2 = texture2D(tFoam, vec2(fu / 1.9 + 0.5, fv / 2.3 - uTime * 0.5 * flowSpd)).r;
    float turb = f1 * 0.5 + f2 * 0.5;
    float shore = 1.0 - smoothstep(0.03, 0.55, depth);
    float shal = 1.0 - smoothstep(0.5, 2.2, depth);
    float foam = smoothstep(0.82, 1.35, turb + shore * 0.95 + shal * 0.3 + rapid * 0.8 + smoothstep(0.6, 0.95, edge) * 0.3);
    foam = clamp(foam, 0.0, 1.0) * uFoam;
    vec3 fc = uFoamCol * (0.62 + 0.5 * lam + 0.25 * F);
    col = mix(col, fc, foam);

    float a = mix(0.44, 0.95, dt);
    a = mix(a, 1.0, rapid * 0.55);
    a = max(a, foam * 0.95);
    a *= 1.0 - smoothstep(0.8, 1.0, edge);       // the outer ring buries itself in the bank
    a *= smoothstep(-0.3, 0.06, depth);          // nothing where the bed is above the surface
    gl_FragColor = vec4(col, a * uOpacity);
    #include <fog_fragment>
  }`;

const fallsVert = /* glsl */`
  attribute vec4 aFall;   // lateral m, fall m, phi 0..1, edge 0..1
  attribute vec2 aShell;  // shell phase, shell weight
  varying vec3 vWPos; varying vec4 vF; varying vec2 vS; varying vec3 vNrm;
  #include <fog_pars_vertex>
  void main() {
    vWPos = position; vF = aFall; vS = aShell;
    vNrm = normalize(normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const fallsFrag = /* glsl */`
  ${common}
  uniform sampler2D tStreak, tFoam;
  uniform float uOpacity, uDetail;
  varying vec3 vWPos; varying vec4 vF; varying vec2 vS; varying vec3 vNrm;
  #include <fog_pars_fragment>
  void main() {
    float lat = vF.x, fall = vF.y, phi = vF.z, edge = vF.w;
    float ph = vS.x;
    // two speeds: a fast body and a faster fine layer, both stretched downward
    vec4 s1 = texture2D(tStreak, vec2(lat / 7.0 + ph, fall / 30.0 - uTime * 1.25));
    vec4 s2 = texture2D(tStreak, vec2(lat / 2.3 - ph * 1.7, fall / 11.0 - uTime * 2.3));
    float thread = s1.r * 0.62 + s2.g * 0.72;
    float brk = texture2D(tFoam, vec2(lat / 8.0 + ph * 0.5, fall / 13.0 - uTime * 1.05)).r;
    if (uDetail > 0.0) {
      vec4 s3 = texture2D(tStreak, vec2(lat / 0.9 + ph * 3.0, fall / 4.5 - uTime * 3.4));
      thread += s3.b * 0.3 * uDetail;
    }

    float lip = 1.0 - smoothstep(0.0, 0.11, max(phi, 0.0));
    float roll = phi < 0.0 ? 1.0 : 0.0;                  // the sheet rolling over the edge
    float dens = mix(1.0, 0.3, smoothstep(0.08, 1.0, max(phi, 0.0)));

    float a = dens * (0.34 + 0.8 * thread);
    // breaking up into spray toward the foot
    a *= mix(1.0, smoothstep(0.34, 0.8, brk * 0.75 + thread * 0.6), smoothstep(0.25, 1.0, max(phi, 0.0)));
    a += (lip + roll) * 0.5;
    a *= 1.0 - smoothstep(0.74, 1.0, edge);
    a *= vS.y;

    vec3 V = normalize(cameraPosition - vWPos);
    vec3 N = normalize(vNrm * (gl_FrontFacing ? 1.0 : -1.0) + vec3(0.0, 0.35, 0.0));
    float lam = max(dot(N, uSunDir), 0.0);
    // white water, greener where the sheet is thick at the lip
    vec3 glass = mix(uDeep, uShallow, 0.45);
    vec3 col = mix(glass, uFoamCol, clamp(0.35 + thread * 0.75 + lip * 0.6, 0.0, 1.0));
    col *= 0.62 + 0.55 * lam + 0.2;
    // backlight: looking toward the sun through the sheet makes it glow, which is
    // what keeps it readable from behind as the coach comes out the far side
    float tr = pow(max(dot(-V, uSunDir), 0.0), 3.0);
    col += uSunCol * tr * 0.55 * dens;
    col += uSunCol * (lip + roll) * 0.35;
    vec3 H = normalize(uSunDir + V);
    col += uSunCol * pow(max(dot(N, H), 0.0), 28.0) * 0.9;
    col += skyAt(reflect(-V, N)) * 0.12;

    gl_FragColor = vec4(col, clamp(a, 0.0, 1.0) * uOpacity);
    #include <fog_fragment>
  }`;

const poolVert = /* glsl */`
  attribute vec4 aPool;   // r 0..1, angle, downstream m, radius m
  varying vec3 vWPos; varying vec4 vP;
  uniform float uTime;
  #include <fog_pars_vertex>
  void main() {
    vec3 p = position;
    p.y += sin(aPool.y * 3.0 + uTime * 4.0 + aPool.x * 9.0) * 0.18 * (1.0 - aPool.x);
    vWPos = p; vP = aPool;
    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const poolFrag = /* glsl */`
  ${common}
  uniform sampler2D tFoam, tNorm;
  uniform float uOpacity;
  varying vec3 vWPos; varying vec4 vP;
  #include <fog_pars_fragment>
  void main() {
    float r = vP.x, ang = vP.y, down = vP.z, rad = vP.w;
    // churn boiling outward from the impact, plus foam carried downstream
    float t1 = texture2D(tFoam, vec2(ang * 1.4, rad * 0.22 - uTime * 0.85)).r;
    float t2 = texture2D(tFoam, vec2(ang * 3.1 + 0.3, rad * 0.55 - uTime * 1.6)).r;
    float t3 = texture2D(tFoam, vec2(down * 0.09 + 0.7, rad * 0.13 - uTime * 0.35)).r;
    float ring = sin(rad * 1.5 - uTime * 3.4) * 0.5 + 0.5;
    float churn = t1 * 0.55 + t2 * 0.5 + t3 * 0.35 + ring * 0.25 * (1.0 - r);
    float core = 1.0 - smoothstep(0.0, 0.55, r);
    float foam = clamp(smoothstep(0.52, 1.05, churn + core * 0.85), 0.0, 1.0);

    vec2 n1 = texture2D(tNorm, vec2(ang * 0.8, rad * 0.3 - uTime * 0.5)).xy * 2.0 - 1.0;
    vec3 N = normalize(vec3(n1.x * 0.7, 1.0, n1.y * 0.7));
    vec3 V = normalize(cameraPosition - vWPos);
    float lam = max(dot(N, uSunDir), 0.0);
    float F = 0.03 + 0.97 * pow(1.0 - max(dot(N, V), 0.0), 5.0);
    vec3 col = mix(mix(uDeep, uShallow, 0.3) * (0.6 + 0.5 * lam), skyAt(reflect(-V, N)), F * 0.8);
    col = mix(col, uFoamCol * (0.66 + 0.45 * lam), foam);
    vec3 H = normalize(uSunDir + V);
    col += uSunCol * pow(max(dot(N, H), 0.0), 90.0) * 1.6;

    float a = (0.55 + 0.45 * foam) * (1.0 - smoothstep(0.55, 1.0, r));
    gl_FragColor = vec4(col, a * uOpacity);
    #include <fog_fragment>
  }`;

// ------------------------------------------------------------ spray particles
// Same GPU-billboard pool as game/fx.js (one draw call, instanced quads, stock
// fog chunks); kept local so the water owns its own budget and lifetime.
const sprayVert = /* glsl */`
  attribute vec3 iPos; attribute vec4 iCol; attribute vec2 iSize;
  varying vec2 vUv; varying vec4 vCol;
  #include <fog_pars_vertex>
  void main() {
    vUv = uv; vCol = iCol;
    vec4 mv = modelViewMatrix * vec4(iPos, 1.0);
    float cr = cos(iSize.y), sr = sin(iSize.y);
    mv.xy += mat2(cr, -sr, sr, cr) * position.xy * iSize.x;
    gl_Position = projectionMatrix * mv;
    vec4 mvPosition = mv;
    #include <fog_vertex>
  }`;
const sprayFrag = /* glsl */`
  uniform sampler2D map; uniform float uAdd;
  varying vec2 vUv; varying vec4 vCol;
  #include <fog_pars_fragment>
  void main() {
    vec4 t = texture2D(map, vUv);
    gl_FragColor = vec4(vCol.rgb * t.rgb, t.a * vCol.a);
    if (uAdd < 0.5) {
      #include <fog_fragment>
    } else {
      gl_FragColor.rgb *= gl_FragColor.a;
    }
  }`;

class SprayPool {
  constructor(scene, max, map, additive) {
    this.max = max; this.scene = scene;
    const base = new THREE.PlaneGeometry(1, 1);
    const g = new THREE.InstancedBufferGeometry();
    g.index = base.index; g.setAttribute('position', base.attributes.position); g.setAttribute('uv', base.attributes.uv);
    this.aPos = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3).setUsage(THREE.DynamicDrawUsage);
    this.aCol = new THREE.InstancedBufferAttribute(new Float32Array(max * 4), 4).setUsage(THREE.DynamicDrawUsage);
    this.aSize = new THREE.InstancedBufferAttribute(new Float32Array(max * 2), 2).setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('iPos', this.aPos); g.setAttribute('iCol', this.aCol); g.setAttribute('iSize', this.aSize);
    g.instanceCount = 0;
    this.base = base;
    const mat = new THREE.ShaderMaterial({
      vertexShader: sprayVert, fragmentShader: sprayFrag, transparent: true, depthWrite: false, fog: true,
      uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, { map: { value: null }, uAdd: { value: additive ? 1 : 0 } }]),
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    mat.uniforms.map.value = map;
    this.mesh = new THREE.Mesh(g, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = additive ? 5 : 4;
    scene.add(this.mesh);
    this.p = [];
  }
  spawn(o) {
    if (this.p.length >= this.max) this.p.shift();
    const max = o.life || 1;
    this.p.push({
      x: o.pos.x, y: o.pos.y, z: o.pos.z,
      vx: o.vel?.x || 0, vy: o.vel?.y || 0, vz: o.vel?.z || 0,
      life: (o.age || 0) * max, max, s0: o.size || 1, s1: o.size1 ?? (o.size || 1) * 2,
      r: o.color?.r ?? 1, g: o.color?.g ?? 1, b: o.color?.b ?? 1, a: o.alpha ?? 1,
      rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * (o.spin ?? 0.6),
      drag: o.drag ?? 1.5, grav: o.grav ?? 0, fadeIn: o.fadeIn ?? 0.15,
    });
  }
  update(dt) {
    const P = this.p;
    let n = 0;
    for (let i = 0; i < P.length; i++) {
      const q = P[i];
      q.life += dt;
      if (q.life >= q.max) continue;
      const k = Math.exp(-q.drag * dt);
      q.vx *= k; q.vy = q.vy * k - q.grav * dt; q.vz *= k;
      q.x += q.vx * dt; q.y += q.vy * dt; q.z += q.vz * dt;
      q.rot += q.vr * dt;
      const t = q.life / q.max;
      const a = q.a * Math.min(1, q.life / Math.max(0.001, q.fadeIn * q.max)) * (1 - t) * (1 - t * 0.3);
      this.aPos.array.set([q.x, q.y, q.z], n * 3);
      this.aCol.array.set([q.r, q.g, q.b, a], n * 4);
      this.aSize.array.set([q.s0 + (q.s1 - q.s0) * Math.sqrt(t), q.rot], n * 2);
      P[n] = q; n++;
    }
    P.length = n;
    this.mesh.geometry.instanceCount = n;
    this.aPos.needsUpdate = this.aCol.needsUpdate = this.aSize.needsUpdate = true;
    this.aPos.clearUpdateRanges(); this.aPos.addUpdateRange(0, n * 3);
    this.aCol.clearUpdateRanges(); this.aCol.addUpdateRange(0, n * 4);
    this.aSize.clearUpdateRanges(); this.aSize.addUpdateRange(0, n * 2);
  }
  dispose() {
    this.scene.remove(this.mesh);
    this.mesh.geometry.dispose(); this.mesh.material.dispose(); this.base.dispose();
    this.p.length = 0;
  }
}

const _fr = {};
const _rc = { d: 0, s: 0 };
const _v3 = new THREE.Vector3();

export class Water {
  constructor(route, scene, renderer, opts = {}) {
    this.route = route; this.scene = scene;
    const tier = renderer?.tier || {};
    // low: no MSAA (QUALITY.low), high: bloom on. Everything scales off this.
    this.q = tier.bloom ? 2 : tier.msaa ? 1 : 0;
    const Q = this.q;
    this.drawDist = tier.drawDist || 600;

    const L = route.def.light;
    this.noise = makeNoise2D((route.def.seed || 1) * 13 + 7);
    this.time = 0;
    this.group = new THREE.Group();
    this.group.matrixAutoUpdate = false;
    scene.add(this.group);

    // ------------------------------------------------------------- river spec
    // depth: metres of water over the deepest point of the channel.
    // offset: a straight shift of the whole surface, for tuning against the gorge.
    const R = Object.assign({ from: 0, to: route.len, d: 30 * (route.riverSide ?? -1), width: 34, depth: 1.4, offset: 0 }, opts.river || {});
    R.from = Math.max(0, R.from); R.to = Math.min(route.len, R.to);
    this.river = R;
    this._buildLevel();

    // ------------------------------------------------------------- materials
    this.texNorm = waterNormalTex(Q ? 256 : 128, (route.def.seed || 1) + 3);
    this.texStreak = streakTex(Q ? 128 : 64, Q ? 256 : 128, (route.def.seed || 1) + 8);
    this.texFoam = tex('cloud_noise');

    const sunDir = new THREE.Vector3().setFromSphericalCoords(
      1, THREE.MathUtils.degToRad(90 - L.sunElev), THREE.MathUtils.degToRad(L.sunAzim));
    this.sunDir = sunDir;
    const sunCol = L.sunColor.clone().multiplyScalar(Math.min(1.6, (L.sunIntensity || 3) * 0.32));
    const C = (h) => new THREE.Color(h);
    const shallow = (opts.shallow ? C(opts.shallow) : C('#86a894')).lerp(L.sunColor, 0.3);
    const deep = opts.deep ? C(opts.deep) : C('#0b2a2e');
    const foam = (opts.foam ? C(opts.foam) : C('#eef6f6')).lerp(L.sunColor, 0.18);
    this.foamCol = foam;
    this.mistCol = foam.clone().lerp(L.hemiSky, 0.25);

    // one uniform block shared by the three surface materials
    const shared = {
      uTime: { value: 0 },
      uSunDir: { value: sunDir }, uSunCol: { value: sunCol },
      uZenith: { value: L.zenith }, uHorizon: { value: L.horizon }, uSunGlow: { value: L.sunGlow },
      uHemiSky: { value: L.hemiSky }, uHemiGnd: { value: L.hemiGround },
      uShallow: { value: shallow }, uDeep: { value: deep }, uFoamCol: { value: foam },
    };
    this.shared = shared;
    const mk = (vs, fs, extra, { order, side = THREE.FrontSide, depthWrite = false }) => {
      const m = new THREE.ShaderMaterial({
        vertexShader: vs, fragmentShader: fs, transparent: true, fog: true,
        depthWrite, side, blending: THREE.NormalBlending,
        uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {}]),
      });
      // merge() clones values, which breaks shared Colors/Textures — re-point them
      Object.assign(m.uniforms, shared, extra);
      m.renderOrder = order;
      return m;
    };

    this.riverMat = mk(riverVert, riverFrag, {
      tNorm: { value: this.texNorm }, tFoam: { value: this.texFoam },
      uSpecPow: { value: Q === 2 ? 480 : Q === 1 ? 300 : 170 },
      uFoam: { value: 1 }, uDetail: { value: Q === 2 ? 1 : 0 },
      uOpacity: { value: 1 }, uSwell: { value: Q ? 0.1 : 0 },
    }, { order: 1, depthWrite: true });

    this.fallsMat = mk(fallsVert, fallsFrag, {
      tStreak: { value: this.texStreak }, tFoam: { value: this.texFoam },
      uOpacity: { value: 1 }, uDetail: { value: Q === 2 ? 1 : 0 },
    }, { order: 3, side: THREE.DoubleSide });

    this.poolMat = mk(poolVert, poolFrag, {
      tFoam: { value: this.texFoam }, tNorm: { value: this.texNorm }, uOpacity: { value: 1 },
    }, { order: 2, side: THREE.DoubleSide });

    // --------------------------------------------------------------- geometry
    this._buildRiver();
    // with no falls given, take the one the route declares (route.fallsAt())
    let fl = opts.falls;
    if (!fl) {
      const rf = route.fallsAt?.();
      fl = rf ? [{ s: rf.s, d: 0, width: rf.width, drop: rf.drop }] : [];
    }
    this._buildFalls(fl);

    // ----------------------------------------------------------------- spray
    this.mist = new SprayPool(scene, Q === 2 ? 320 : Q === 1 ? 200 : 90, smokePuff(), false);
    this.drops = Q ? new SprayPool(scene, Q === 2 ? 180 : 110, softDot(), true) : null;
    this._prewarmMist();
    this._emitAcc = 0; this._rapidAcc = 0; this._coachAcc = 0;
  }

  // ------------------------------------------------------------- water level
  // The surface follows the terrain floor: at every station the floor is sampled
  // right across the channel and the *deepest* point taken, then smoothed within
  // each reach (so a sheer step at a falls survives) and raised by `depth`. Being
  // anchored to the bottom of the channel rather than its mean is what keeps the
  // surface under the banks while still leaving real depth in the middle.
  _buildLevel() {
    const R = this.river, route = this.route;
    const n = Math.max(2, Math.ceil((R.to - R.from) / LSTEP) + 1);
    this.lN = n;
    const floor = new Float32Array(n);
    const LAT = 7;
    for (let i = 0; i < n; i++) {
      const s = R.from + i * LSTEP;
      const fr = route.frame(s, _fr);
      let lo = Infinity;
      for (let j = 0; j < LAT; j++) {
        const dd = R.d + (j / (LAT - 1) - 0.5) * R.width * 0.8;
        const x = fr.x + fr.rx * dd, z = fr.z + fr.rz * dd;
        lo = Math.min(lo, route.height(x, z));
      }
      floor[i] = lo;
    }
    // reaches: a drop of more than 2.5 m between samples is a fall, not a slope
    const cut = new Uint8Array(n);
    for (let i = 1; i < n; i++) if (floor[i - 1] - floor[i] > 2.5) cut[i] = 1;
    // box blur (x3) that never reads across a cut
    const win = 14;
    let a = floor, b = new Float32Array(n);
    for (let pass = 0; pass < 3; pass++) {
      for (let i = 0; i < n; i++) {
        let acc = a[i], cnt = 1;
        for (let k = 1; k <= win; k++) {
          const j = i + k; if (j >= n || cut[j]) break; acc += a[j]; cnt++;
        }
        for (let k = 1; k <= win; k++) {
          const j = i - k; if (j < 0 || cut[j + 1]) break; acc += a[j]; cnt++;
        }
        b[i] = acc / cnt;
      }
      [a, b] = [b, a];
    }
    // The floor rises and falls with the road, so the surface follows it rather
    // than running strictly downhill; it is only stopped from climbing faster
    // than water plausibly could between reaches.
    for (let i = 1; i < n; i++) a[i] = Math.min(a[i], a[i - 1] + 0.04 * LSTEP);
    for (let i = 0; i < n; i++) a[i] += R.depth + R.offset;
    // the water thins and dips as it accelerates into a lip
    for (let i = 1; i < n; i++) {
      if (!cut[i]) continue;
      for (let k = 1; k <= 5; k++) {
        const j = i - k; if (j < 0) break;
        a[j] -= 0.45 * (1 - (k - 1) / 5);
      }
    }
    this.level = a;
    // rapids: surface gradient plus noise patches, so there are distinct stretches
    const rap = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const i0 = Math.max(0, i - 2), i1 = Math.min(n - 1, i + 2);
      const g = (a[i0] - a[i1]) / ((i1 - i0) * LSTEP);
      // steep reaches run white, but only in patches — a river is not one long rapid
      const patch = fbm(this.noise, (R.from + i * LSTEP) / 70, 3.3, 3) * 0.5 + 0.5;
      rap[i] = clamp(smoothstep(0.018, 0.09, g) * (0.25 + 1.05 * smoothstep(0.35, 0.8, patch)), 0, 1);
    }
    this.rapid = rap;
  }

  levelAt(s) {
    const R = this.river, n = this.lN;
    const f = clamp((s - R.from) / LSTEP, 0, n - 1);
    const i = Math.min(n - 2, f | 0);
    return lerp(this.level[i], this.level[i + 1], f - i);
  }

  rapidsAt(s) {
    const R = this.river, n = this.lN;
    const f = clamp((s - R.from) / LSTEP, 0, n - 1);
    const i = Math.min(n - 2, f | 0);
    return lerp(this.rapid[i], this.rapid[i + 1], f - i);
  }

  // ------------------------------------------------------------ river ribbon
  // One ribbon, split into ~250 m chunks so anything off screen or past the draw
  // distance costs nothing. The outer column of every chunk is dropped below the
  // surface and faded out, which buries the lateral seam in the bank.
  _buildRiver() {
    const R = this.river, route = this.route, Q = this.q;
    const step = Q === 2 ? 3 : Q === 1 ? 4 : 6;
    const COLS = Q ? 9 : 7;
    const rows = Math.max(2, Math.floor((R.to - R.from) / step) + 1);
    const pos = new Float32Array(rows * COLS * 3);
    const inf = new Float32Array(rows * COLS * 4);
    const flw = new Float32Array(rows * COLS * 2);
    const rowS = new Float32Array(rows);
    let p = 0;
    for (let i = 0; i < rows; i++) {
      const s = Math.min(R.to, R.from + i * step);
      rowS[i] = s;
      const fr = route.frame(s, _fr);
      const level = this.levelAt(s);
      const rap = this.rapidsAt(s);
      const meander = this.noise(s / 110, 1.9) * R.width * 0.12;
      const w = R.width * (1 + this.noise(s / 170 + 7, 4.4) * 0.16);
      for (let j = 0; j < COLS; j++, p++) {
        const u = j / (COLS - 1);
        const e = Math.abs(u * 2 - 1);
        const skirt = j === 0 || j === COLS - 1;
        const dd = R.d + meander + (u - 0.5) * w;
        const x = fr.x + fr.rx * dd, z = fr.z + fr.rz * dd;
        const bed = route.height(x, z);
        pos[p * 3] = x; pos[p * 3 + 1] = level - (skirt ? 0.8 : 0); pos[p * 3 + 2] = z;
        inf[p * 4] = s; inf[p * 4 + 1] = e; inf[p * 4 + 2] = level - bed; inf[p * 4 + 3] = rap;
        flw[p * 2] = fr.tx; flw[p * 2 + 1] = fr.tz;
      }
    }
    // chunk it
    const CHUNK = Math.max(8, Math.round(250 / step));
    this.chunks = [];
    for (let r0 = 0; r0 < rows - 1; r0 += CHUNK) {
      const r1 = Math.min(rows - 1, r0 + CHUNK);
      const nr = r1 - r0 + 1, nv = nr * COLS;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos.slice(r0 * COLS * 3, (r1 + 1) * COLS * 3), 3));
      g.setAttribute('aInfo', new THREE.BufferAttribute(inf.slice(r0 * COLS * 4, (r1 + 1) * COLS * 4), 4));
      g.setAttribute('aFlow', new THREE.BufferAttribute(flw.slice(r0 * COLS * 2, (r1 + 1) * COLS * 2), 2));
      const idx = new Uint16Array((nr - 1) * (COLS - 1) * 6);
      let k = 0;
      for (let b = 0; b < nr - 1; b++) for (let a2 = 0; a2 < COLS - 1; a2++) {
        // (lateral, downstream) is the opposite handedness to terrain's (x, z),
        // so the winding is flipped from the terrain grid or every face points down
        const v0 = b * COLS + a2, v1 = v0 + 1, v2 = v0 + COLS, v3 = v2 + 1;
        idx[k++] = v0; idx[k++] = v1; idx[k++] = v2;
        idx[k++] = v1; idx[k++] = v3; idx[k++] = v2;
      }
      g.setIndex(new THREE.BufferAttribute(idx, 1));
      g.computeBoundingSphere();
      const mesh = new THREE.Mesh(g, this.riverMat);
      mesh.matrixAutoUpdate = false;
      mesh.renderOrder = 1;
      this.group.add(mesh);
      this.chunks.push({ mesh, c: g.boundingSphere.center.clone(), r: g.boundingSphere.radius, s0: rowS[r0], s1: rowS[r1] });
      if (nv > 65535) console.warn('water: river chunk over 16-bit index range');
    }
  }

  // ------------------------------------------------------------- waterfalls
  _buildFalls(list) {
    const route = this.route, Q = this.q;
    this.falls = [];
    if (!list.length) { this.fallsMesh = null; this.poolMesh = null; return; }

    const SHELLS = Q ? 3 : 2;
    const ROWS = Q === 2 ? 15 : Q === 1 ? 12 : 8;
    const LIP = 2;                       // rows above the lip, for the roll-over
    const COLS = Q === 2 ? 19 : Q === 1 ? 15 : 11;
    const VR = ROWS + LIP + 1;
    const cPos = [], cFall = [], cShell = [], cIdx = [];
    const pPos = [], pInfo = [], pIdx = [];
    const RING = Q ? 6 : 4, SEG = Q ? 22 : 14;

    for (const raw of list) {
      const f = this._resolveFall(raw);
      this.falls.push(f);
      const base = cPos.length / 3;

      for (let k = 0; k < SHELLS; k++) {
        const nOff = (k - (SHELLS - 1) / 2) * 0.85;
        const phase = k * 0.41;
        const weight = k === Math.floor(SHELLS / 2) ? 1 : 0.72;
        const arc = f.arc * (1 + (k - (SHELLS - 1) / 2) * 0.12);
        const v0 = cPos.length / 3;
        for (let r = -LIP; r <= ROWS; r++) {
          const lipT = r < 0 ? -r / LIP : 0;
          const phi = r < 0 ? -0.001 * -r : r / ROWS;
          let y, along, fallM;
          if (r < 0) {
            y = f.lipY + 0.55 * Math.pow(lipT, 1.6);
            along = -4.2 * Math.pow(lipT, 1.25);
            fallM = -3.0 * lipT;
          } else {
            const pf = phi;
            y = f.lipY - f.drop * pf;
            along = arc * Math.sqrt(pf);
            fallM = f.drop * pf;
          }
          const lean = f.lat(phi);
          for (let c = 0; c <= COLS; c++) {
            const u = c / COLS;
            const e = Math.abs(u * 2 - 1);
            const spread = 1 + 0.18 * Math.max(0, phi);
            const lat = (u - 0.5) * f.halfW * 2 * spread;
            // ragged sheet: break the flatness up along both axes
            const nA = this.noise(u * 5.5 + k * 13, Math.max(0, phi) * 5 + 2.1);
            const nB = this.noise(u * 2.1 - k * 7, Math.max(0, phi) * 2.4 - 5.7);
            const yy = y + nA * 0.55 * Math.max(0, phi) - e * e * 0.6 * Math.max(0, phi);
            const aa = along + nOff + nB * 1.2 * Math.max(0, phi) + e * e * 1.6 * Math.max(0, phi);
            const ll = lat + lean;
            cPos.push(f.cx + f.ax * ll + f.nx * aa, yy, f.cz + f.az * ll + f.nz * aa);
            cFall.push(lat, fallM, phi, e);   // UV lateral stays local so the streaks don't shear
            cShell.push(phase, weight);
          }
        }
        for (let r = 0; r < VR - 1; r++) for (let c = 0; c < COLS; c++) {
          const a = v0 + r * (COLS + 1) + c, b = a + 1, d2 = a + COLS + 1, e2 = d2 + 1;
          cIdx.push(a, d2, b, b, d2, e2);
        }
      }
      f.vBase = base;

      // churning pool where the sheet lands
      const pRad = Math.max(6, f.halfW * 1.35);
      const q0 = pPos.length / 3;
      f.at(1, _v3);
      const fxx = _v3.x, fzz = _v3.z;
      for (let ri = 0; ri <= RING; ri++) {
        const r01 = ri / RING, rm = r01 * pRad;
        for (let si = 0; si <= SEG; si++) {
          const ang = (si / SEG) * Math.PI * 2;
          const lx = Math.cos(ang) * rm, lz = Math.sin(ang) * rm;
          const x = fxx + f.ax * lx + f.nx * lz, z = fzz + f.az * lx + f.nz * lz;
          pPos.push(x, f.botY + (1 - r01) * 0.35, z);
          pInfo.push(r01, ang / (Math.PI * 2), lz, rm);
        }
      }
      for (let ri = 0; ri < RING; ri++) for (let si = 0; si < SEG; si++) {
        const a = q0 + ri * (SEG + 1) + si, b = a + 1, d2 = a + SEG + 1, e2 = d2 + 1;
        pIdx.push(a, d2, b, b, d2, e2);
      }
    }

    const cg = new THREE.BufferGeometry();
    cg.setAttribute('position', new THREE.Float32BufferAttribute(cPos, 3));
    cg.setAttribute('aFall', new THREE.Float32BufferAttribute(cFall, 4));
    cg.setAttribute('aShell', new THREE.Float32BufferAttribute(cShell, 2));
    cg.setIndex(cIdx);
    cg.computeVertexNormals();
    cg.computeBoundingSphere();
    this.fallsMesh = new THREE.Mesh(cg, this.fallsMat);
    this.fallsMesh.matrixAutoUpdate = false;
    this.fallsMesh.renderOrder = 3;
    this.group.add(this.fallsMesh);

    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
    pg.setAttribute('aPool', new THREE.Float32BufferAttribute(pInfo, 4));
    pg.setIndex(pIdx);
    pg.computeBoundingSphere();
    this.poolMesh = new THREE.Mesh(pg, this.poolMat);
    this.poolMesh.matrixAutoUpdate = false;
    this.poolMesh.renderOrder = 2;
    this.group.add(this.poolMesh);
  }

  // Work out where a falls actually sits. See the header for the height rules.
  _resolveFall(o) {
    const route = this.route, R = this.river;
    const s = clamp(o.s ?? route.len * 0.5, 0, route.len);
    const d = o.d ?? 0;
    const width = o.width ?? 26;
    const fr = route.frame(s, {});
    // the pool the sheet lands in: the river right below the fall
    let poolY = Infinity;
    for (let k = -4; k <= 12; k += 2) poolY = Math.min(poolY, this.levelAt(s + k));
    const overRiver = Math.abs(d - R.d) <= R.width * 0.75;
    const roadY = route.roadHeightAt(s);
    let lipY;
    if (o.lipY !== undefined) lipY = o.lipY;
    else if (o.ref === 'road') lipY = roadY + (o.top ?? 12);
    else if (overRiver) lipY = this.levelAt(Math.max(R.from, s - 3));   // seam with the river above
    else lipY = poolY + (o.top ?? o.drop ?? 30);
    let botY = o.baseY !== undefined ? o.baseY : lipY - (o.drop ?? (lipY - poolY));
    botY = Math.max(botY, poolY - 0.5);
    const drop = Math.max(2, lipY - botY);

    // Lean: where does the sheet land? March out toward the river until the
    // ground has fallen to the foot of the fall. The curtain is then a straight
    // slant through that point and through `d` at road height, which puts its lip
    // back over the inland wall and its foot out over the water.
    const side = Math.sign(R.d - d) || 1;
    let span = 0;
    if (o.lean !== undefined) span = o.lean;
    else if (Math.abs(lipY - botY) > 4) {
      for (let k = 2; k <= 60; k += 1.5) {
        const dd = d + side * k;
        const x = fr.x + fr.rx * dd, z = fr.z + fr.rz * dd;
        if (route.height(x, z) <= botY + 0.6) { span = side * k; break; }
      }
      span = clamp(span, -44, 44);
    }
    const phiRoad = clamp((lipY - roadY) / drop, 0.03, 0.75);

    return {
      s, d, lipY, botY, drop, halfW: width * 0.5, span, phiRoad,
      cx: fr.x + fr.rx * d, cz: fr.z + fr.rz * d,
      ax: fr.rx, az: fr.rz,          // lateral axis of the curtain
      nx: fr.tx, nz: fr.tz,          // downstream / through-the-curtain axis
      arc: Math.min(5.5, 1.1 + drop * 0.075),   // how far the sheet throws downstream
      thick: 3.2, poolY,
      // lateral centre of the sheet at fall fraction phi (0 = lip, 1 = foot)
      lat(phi) { return this.span * (clamp(phi, 0, 1) - this.phiRoad) / (1 - this.phiRoad); },
      // world point on the sheet's centre line at phi
      at(phi, out) {
        const l = this.lat(phi), a = this.arc * Math.sqrt(clamp(phi, 0, 1));
        return out.set(this.cx + this.ax * l + this.nx * a, this.lipY - this.drop * clamp(phi, 0, 1), this.cz + this.az * l + this.nz * a);
      },
    };
  }

  // ----------------------------------------------------------------- spray
  _prewarmMist() {
    for (const f of this.falls) for (let i = 0; i < (this.q ? 26 : 12); i++) {
      this._mistPuff(f, Math.random());
    }
  }

  // A point on the sheet at fall fraction phi, jittered around it.
  _onSheet(f, phi, spread = 1) {
    f.at(phi, _v3);
    const a = (Math.random() - 0.5) * f.halfW * 1.9 * spread;
    const b = (Math.random() - 0.3) * f.halfW * 0.9 * spread;
    _v3.x += f.ax * a + f.nx * b; _v3.z += f.az * a + f.nz * b;
    return _v3;
  }

  _mistPuff(f, age = 0) {
    const phi = 1 - Math.random() * 0.4;
    this.mist.spawn({
      pos: this._onSheet(f, phi),
      vel: new THREE.Vector3((Math.random() - 0.5) * 2.2 + f.nx * 1.4, 1.6 + Math.random() * 2.6, (Math.random() - 0.5) * 2.2 + f.nz * 1.4),
      life: 5.5 + Math.random() * 4, size: 3 + Math.random() * 3, size1: 13 + Math.random() * 9,
      color: this.mistCol, alpha: 0.2 + Math.random() * 0.12, drag: 0.55, grav: -0.22, fadeIn: 0.3, spin: 0.25, age,
    });
  }

  _emitFalls(dt, camPos) {
    const Q = this.q;
    const rate = Q === 2 ? 30 : Q === 1 ? 18 : 8;
    for (const f of this.falls) {
      const dist = Math.hypot(camPos.x - f.cx, camPos.z - f.cz);
      if (dist > this.drawDist * 0.8) continue;
      const near = 1 - smoothstep(60, this.drawDist * 0.8, dist);
      this._emitAcc += rate * (0.35 + near) * dt;
      while (this._emitAcc >= 1) {
        this._emitAcc -= 1;
        // rising mist that catches the light
        this._mistPuff(f);
        // spray bursting off the impact
        const p = this._onSheet(f, 1 - Math.random() * 0.06, 0.9);
        p.y += 0.3 + Math.random() * 2.5;
        this.mist.spawn({
          pos: p,
          vel: new THREE.Vector3((Math.random() - 0.5) * 7 + f.nx * 3, 3.5 + Math.random() * 7, (Math.random() - 0.5) * 7 + f.nz * 3),
          life: 1.1 + Math.random() * 1.1, size: 0.5, size1: 3.4,
          color: this.foamCol, alpha: 0.55, drag: 1.9, grav: 5.5, fadeIn: 0.08,
        });
        if (this.drops && Math.random() < 0.75) {
          const p2 = this._onSheet(f, 1 - Math.random() * 0.08, 0.8);
          p2.y += 0.5 + Math.random() * 3.5;
          this.drops.spawn({
            pos: p2,
            vel: new THREE.Vector3((Math.random() - 0.5) * 11, 5 + Math.random() * 9, (Math.random() - 0.5) * 11),
            life: 0.7 + Math.random() * 0.5, size: 0.12, size1: 0.3,
            color: this.foamCol, alpha: 0.6, drag: 0.7, grav: 12, fadeIn: 0,
          });
        }
      }
      // wisps tearing off the sheet on the way down, thickest where it crosses
      // the road — that is what the coach rides into
      if (Q && Math.random() < dt * 14 * (0.2 + near)) {
        const phi = clamp(f.phiRoad + (Math.random() - 0.4) * 0.7, 0, 1);
        this.mist.spawn({
          pos: this._onSheet(f, phi, 0.7),
          vel: new THREE.Vector3(f.nx * 3 + (Math.random() - 0.5) * 2, -2 - Math.random() * 4, f.nz * 3 + (Math.random() - 0.5) * 2),
          life: 1.6 + Math.random(), size: 1.2, size1: 5.5,
          color: this.mistCol, alpha: 0.32, drag: 1.2, grav: 1.5, fadeIn: 0.15,
        });
      }
    }
  }

  // Whitewater along the rapids near the camera only — the rest of the river
  // gets its foam from the shader.
  _emitRapids(dt, camPos) {
    if (!this.q) return;
    this.route.roadCoords(camPos.x, camPos.z, _rc);
    if (_rc.s < 0) return;
    const R = this.river;
    this._rapidAcc += dt * (this.q === 2 ? 26 : 14);
    while (this._rapidAcc >= 1) {
      this._rapidAcc -= 1;
      const s = clamp(_rc.s + (Math.random() - 0.35) * 150, R.from, R.to);
      const rap = this.rapidsAt(s);
      if (rap < 0.4) continue;
      const fr = this.route.frame(s, _fr);
      const dd = R.d + (Math.random() - 0.5) * R.width * 0.8;
      const x = fr.x + fr.rx * dd, z = fr.z + fr.rz * dd;
      this.mist.spawn({
        pos: _v3.set(x, this.levelAt(s) + 0.15, z),
        vel: new THREE.Vector3(fr.tx * 2 + (Math.random() - 0.5) * 2, 1 + Math.random() * 2.5 * rap, fr.tz * 2 + (Math.random() - 0.5) * 2),
        life: 0.9 + Math.random() * 1.2, size: 0.4, size1: 2.6 + rap * 2,
        color: this.foamCol, alpha: 0.3 * rap, drag: 1.6, grav: 1.6, fadeIn: 0.12,
      });
    }
  }

  // ------------------------------------------------------------------ frame
  update(dt, camera, coachPos) {
    this.time += dt;
    this.shared.uTime.value = this.time;

    const cam = camera?.position || (coachPos || _v3);
    // chunk culling: distance first (cheap), then let three frustum-cull the rest
    const far = this.drawDist + 140;
    for (const c of this.chunks) {
      const d = Math.hypot(cam.x - c.c.x, cam.z - c.c.z) - c.r;
      c.mesh.visible = d < far;
    }

    if (this.falls.length) {
      this._emitFalls(dt, cam);
      // the coach punching through throws water everywhere
      if (coachPos) {
        const t = this.throughFalls(coachPos);
        if (t > 0.02) {
          this._coachAcc += dt * 90 * t;
          while (this._coachAcc >= 1) {
            this._coachAcc -= 1;
            this.mist.spawn({
              pos: _v3.set(coachPos.x + (Math.random() - 0.5) * 4, coachPos.y + Math.random() * 3, coachPos.z + (Math.random() - 0.5) * 4),
              vel: new THREE.Vector3((Math.random() - 0.5) * 9, 1 + Math.random() * 6, (Math.random() - 0.5) * 9),
              life: 0.7 + Math.random() * 0.7, size: 0.5, size1: 3,
              color: this.foamCol, alpha: 0.6, drag: 2.2, grav: 4, fadeIn: 0.05,
            });
          }
        }
      }
    }
    this._emitRapids(dt, cam);
    this.mist.update(dt);
    this.drops?.update(dt);
  }

  // How far inside a falls curtain a point is, 0..1. Used for the screen effect
  // and the sound as the coach bursts through.
  throughFalls(p) {
    let m = 0;
    for (const f of this.falls) {
      const dx = p.x - f.cx, dz = p.z - f.cz;
      const u = dx * f.ax + dz * f.az;          // lateral
      const nn = dx * f.nx + dz * f.nz;         // through the sheet
      const phi = clamp((f.lipY - p.y) / f.drop, 0, 1);
      const nc = f.arc * Math.sqrt(phi);        // the sheet has thrown this far downstream
      const th = f.thick + 1.4 * phi;
      const a = 1 - smoothstep(th * 0.3, th, Math.abs(nn - nc));
      if (a <= 0) continue;
      const hw = f.halfW * (1 + 0.18 * phi);
      const b = 1 - smoothstep(hw * 0.75, hw * 1.05, Math.abs(u - f.lat(phi)));
      if (b <= 0) continue;
      const v = smoothstep(f.botY - 2.5, f.botY + 0.5, p.y) * (1 - smoothstep(f.lipY - 0.2, f.lipY + 2.2, p.y));
      m = Math.max(m, a * b * v);
    }
    return m;
  }

  dispose() {
    this.scene.remove(this.group);
    for (const c of this.chunks) c.mesh.geometry.dispose();
    this.fallsMesh?.geometry.dispose();
    this.poolMesh?.geometry.dispose();
    this.riverMat.dispose(); this.fallsMat.dispose(); this.poolMat.dispose();
    this.texNorm.dispose(); this.texStreak.dispose();
    this.mist.dispose(); this.drops?.dispose();
    this.chunks = []; this.falls = [];
  }
}
