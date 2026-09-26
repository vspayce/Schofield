// GPU-billboard particle pools (alpha smoke/dust + additive flashes/tracers),
// one draw call each, plus a single muzzle-flash point light.
import * as THREE from 'three';
import { smokePuff, flashTex } from '../world/textures.js';

const vert = /* glsl */`
  attribute vec3 iPos; attribute vec4 iCol; attribute vec3 iDir; attribute vec2 iSize; // size, rot
  varying vec2 vUv; varying vec4 vCol;
  #include <fog_pars_vertex>
  void main() {
    vUv = uv; vCol = iCol;
    vec4 mv = modelViewMatrix * vec4(iPos, 1.0);
    vec2 c = position.xy;
    float len = length(iDir);
    if (len > 0.0) {
      // velocity-aligned streak
      vec3 dv = (viewMatrix * vec4(iDir, 0.0)).xyz;
      vec2 ax = normalize(dv.xy + 1e-5);
      vec2 pp = vec2(-ax.y, ax.x);
      mv.xy += ax * c.x * len + pp * c.y * iSize.x;
    } else {
      float cr = cos(iSize.y), sr = sin(iSize.y);
      mv.xy += mat2(cr, -sr, sr, cr) * c * iSize.x;
    }
    gl_Position = projectionMatrix * mv;
    vec4 mvPosition = mv;
    #include <fog_vertex>
  }`;
const frag = /* glsl */`
  uniform sampler2D map; uniform float uAdd;
  varying vec2 vUv; varying vec4 vCol;
  #include <fog_pars_fragment>
  void main() {
    vec4 t = texture2D(map, vUv);
    gl_FragColor = vec4(vCol.rgb * t.rgb, t.a * vCol.a);
    if (uAdd < 0.5) {
      #include <fog_fragment>
    } else {
      gl_FragColor.rgb *= gl_FragColor.a; // premultiplied for additive
    }
  }`;

class Pool {
  constructor(scene, max, map, additive) {
    this.max = max;
    const base = new THREE.PlaneGeometry(1, 1);
    const g = new THREE.InstancedBufferGeometry();
    g.index = base.index; g.setAttribute('position', base.attributes.position); g.setAttribute('uv', base.attributes.uv);
    this.aPos = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3).setUsage(THREE.DynamicDrawUsage);
    this.aCol = new THREE.InstancedBufferAttribute(new Float32Array(max * 4), 4).setUsage(THREE.DynamicDrawUsage);
    this.aDir = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3).setUsage(THREE.DynamicDrawUsage);
    this.aSize = new THREE.InstancedBufferAttribute(new Float32Array(max * 2), 2).setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('iPos', this.aPos); g.setAttribute('iCol', this.aCol); g.setAttribute('iDir', this.aDir); g.setAttribute('iSize', this.aSize);
    g.instanceCount = 0;
    const mat = new THREE.ShaderMaterial({
      vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false, fog: true,
      uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, { map: { value: map }, uAdd: { value: additive ? 1 : 0 } }]),
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
    this.p.push({
      x: o.pos.x, y: o.pos.y, z: o.pos.z,
      vx: o.vel?.x || 0, vy: o.vel?.y || 0, vz: o.vel?.z || 0,
      life: 0, max: o.life || 1, s0: o.size || 1, s1: o.size1 ?? (o.size || 1) * 2,
      r: o.color?.r ?? 1, g: o.color?.g ?? 1, b: o.color?.b ?? 1, a: o.alpha ?? 1,
      rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * (o.spin ?? 1),
      drag: o.drag ?? 1.5, grav: o.grav ?? 0, streak: o.streak || 0, fadeIn: o.fadeIn ?? 0.1,
      dir: o.dir || null,
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
      if (q.streak) {
        const d = q.dir || { x: q.vx, y: q.vy, z: q.vz };
        const l = Math.hypot(d.x, d.y, d.z) || 1;
        const L = q.streak;
        this.aDir.array.set([d.x / l * L, d.y / l * L, d.z / l * L], n * 3);
      } else this.aDir.array.set([0, 0, 0], n * 3);
      this.aSize.array.set([q.s0 + (q.s1 - q.s0) * Math.sqrt(t), q.rot], n * 2);
      P[n] = q; n++;
    }
    P.length = n;
    const g = this.mesh.geometry;
    g.instanceCount = n;
    this.aPos.needsUpdate = this.aCol.needsUpdate = this.aDir.needsUpdate = this.aSize.needsUpdate = true;
    this.aPos.clearUpdateRanges(); this.aPos.addUpdateRange(0, n * 3);
    this.aCol.clearUpdateRanges(); this.aCol.addUpdateRange(0, n * 4);
    this.aDir.clearUpdateRanges(); this.aDir.addUpdateRange(0, n * 3);
    this.aSize.clearUpdateRanges(); this.aSize.addUpdateRange(0, n * 2);
  }
  clear() { this.p.length = 0; }
}

const _v = new THREE.Vector3();

export class FX {
  constructor(scene, route) {
    this.scene = scene;
    this.smoke = new Pool(scene, 900, smokePuff(), false);
    this.add = new Pool(scene, 300, flashTex(), true);
    this.light = new THREE.PointLight(0xffb060, 0, 6, 2);
    scene.add(this.light);
    this.lightT = 0;
    const L = route.def.light;
    // dust takes its colour from the ground + sun
    this.dustCol = L.ground.clone().lerp(L.sunColor, 0.35).lerp(new THREE.Color(1, 1, 1), 0.25);
    this.smokeCol = new THREE.Color(0.85, 0.83, 0.8);
  }

  muzzle(pos, dir, { big = false, light = false } = {}) {
    const s = big ? 1.1 : 0.6;
    this.add.spawn({ pos, life: 0.06, size: s, size1: s * 1.3, color: { r: 1, g: 0.85, b: 0.6 }, alpha: 1, spin: 0, fadeIn: 0 });
    this.add.spawn({ pos: _v.copy(pos).addScaledVector(dir, s * 0.35), life: 0.05, size: s * 0.35, streak: s * 0.9, dir, color: { r: 1, g: 0.7, b: 0.35 }, fadeIn: 0 });
    for (let i = 0; i < (big ? 7 : 4); i++) {
      const v = dir.clone().multiplyScalar(2 + Math.random() * (big ? 7 : 4)).add(new THREE.Vector3((Math.random() - 0.5) * 1.5, Math.random() * 0.8, (Math.random() - 0.5) * 1.5));
      this.smoke.spawn({ pos, vel: v, life: 1.4 + Math.random(), size: 0.25, size1: big ? 2.2 : 1.4, color: this.smokeCol, alpha: 0.5, drag: 2.4, grav: -0.25 });
    }
    if (light) { this.light.position.copy(pos); this.light.intensity = big ? 18 : 10; this.lightT = 0.05; }
  }

  tracer(from, to) {
    const d = _v.subVectors(to, from);
    const len = d.length();
    const dir = d.clone().normalize();
    const speed = 420;
    this.add.spawn({ pos: from.clone().addScaledVector(dir, 2), vel: dir.clone().multiplyScalar(speed), dir, life: Math.min(0.35, len / speed), size: 0.03, streak: 3.2, color: { r: 1, g: 0.8, b: 0.5 }, alpha: 0.7, drag: 0, fadeIn: 0 });
  }

  dust(pos, { amount = 6, size = 0.6, color = null, up = 1.5, spread = 2 } = {}) {
    for (let i = 0; i < amount; i++) {
      this.smoke.spawn({
        pos: _v.set(pos.x + (Math.random() - 0.5) * 0.3, pos.y + 0.05, pos.z + (Math.random() - 0.5) * 0.3),
        vel: new THREE.Vector3((Math.random() - 0.5) * spread, Math.random() * up + 0.3, (Math.random() - 0.5) * spread),
        life: 0.9 + Math.random() * 0.9, size, size1: size * 3.5, color: color || this.dustCol, alpha: 0.6, drag: 3, grav: 0.8,
      });
    }
    // grit
    for (let i = 0; i < amount; i++) {
      this.smoke.spawn({ pos, vel: new THREE.Vector3((Math.random() - 0.5) * 4, 3 + Math.random() * 4, (Math.random() - 0.5) * 4), life: 0.6, size: 0.06, size1: 0.05, color: { r: 0.3, g: 0.24, b: 0.18 }, alpha: 1, drag: 0.5, grav: 14 });
    }
  }

  blood(pos, dir) {
    for (let i = 0; i < 7; i++) {
      const v = dir.clone().multiplyScalar(1.5 + Math.random() * 2.5).add(new THREE.Vector3((Math.random() - 0.5) * 1.5, Math.random() * 1.2, (Math.random() - 0.5) * 1.5));
      this.smoke.spawn({ pos, vel: v, life: 0.45 + Math.random() * 0.3, size: 0.12, size1: 0.45, color: { r: 0.32, g: 0.02, b: 0.02 }, alpha: 0.85, drag: 3, grav: 6 });
    }
  }

  splinters(pos, dir) {
    for (let i = 0; i < 8; i++) {
      const v = dir.clone().multiplyScalar(-2 - Math.random() * 3).add(new THREE.Vector3((Math.random() - 0.5) * 3, Math.random() * 3, (Math.random() - 0.5) * 3));
      this.smoke.spawn({ pos, vel: v, life: 0.7, size: 0.07, size1: 0.05, color: { r: 0.45, g: 0.33, b: 0.2 }, alpha: 1, drag: 0.8, grav: 12, spin: 20 });
    }
    this.dust(pos, { amount: 2, size: 0.25, up: 0.6 });
  }

  sparks(pos) {
    for (let i = 0; i < 5; i++) {
      const v = new THREE.Vector3((Math.random() - 0.5) * 8, Math.random() * 6, (Math.random() - 0.5) * 8);
      this.add.spawn({ pos, vel: v, life: 0.25, size: 0.03, streak: 0.25, color: { r: 1, g: 0.75, b: 0.4 }, drag: 1, grav: 9.8, fadeIn: 0 });
    }
  }

  glint(pos, strength = 1) {
    this.add.spawn({ pos, life: 0.12, size: 1.6 * strength, size1: 1.6 * strength, color: { r: 1, g: 0.95, b: 0.8 }, alpha: 1, spin: 0, fadeIn: 0 });
  }

  // dust kicked up by hooves / wheels
  trail(pos, rate, dt, size = 0.9) {
    const n = rate * dt;
    let k = Math.floor(n) + (Math.random() < n % 1 ? 1 : 0);
    while (k--) {
      this.smoke.spawn({
        pos: _v.set(pos.x + (Math.random() - 0.5) * 5, pos.y + size * 0.6, pos.z + (Math.random() - 0.5) * 5),
        vel: new THREE.Vector3((Math.random() - 0.5) * 1.5, 0.2 + Math.random() * 0.4, (Math.random() - 0.5) * 1.5),
        life: 3 + Math.random() * 2, size, size1: size * 8, color: this.dustCol, alpha: 0.18, drag: 1.2, grav: -0.03, fadeIn: 0.25,
      });
    }
  }

  update(dt) {
    this.smoke.update(dt); this.add.update(dt);
    if (this.lightT > 0) { this.lightT -= dt; if (this.lightT <= 0) this.light.intensity = 0; }
  }

  dispose() {
    this.scene.remove(this.smoke.mesh, this.add.mesh, this.light);
  }
}
