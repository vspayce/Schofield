// Sky dome (gradient + sun disc/glow + two cloud layers), far mountain
// silhouette rings, sun/hemisphere lights with a shadow frustum that follows the
// coach, and a PMREM environment map baked from the sky for PBR reflections.
import * as THREE from 'three';
import { assets } from '../core/assets.js';
import { tex } from './textures.js';
import { makeNoise2D, fbm } from '../core/noise.js';

const skyVert = /* glsl */`
  varying vec3 vDir;
  void main() {
    vDir = normalize(position);
    vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    gl_Position = p.xyww; // at far plane
  }`;
const skyFrag = /* glsl */`
  uniform vec3 uZenith, uHorizon, uGround, uSunGlow, uSunColor, uSunDir;
  uniform float uClouds, uTime;
  uniform sampler2D tCloud;
  varying vec3 vDir;
  void main() {
    vec3 d = normalize(vDir);
    float h = d.y;
    float sd = max(dot(d, uSunDir), 0.0);
    vec3 col = mix(uHorizon, uZenith, pow(smoothstep(-0.02, 0.6, h), 0.5));
    col += uSunGlow * 0.15 * (1.0 - clamp(h, 0.0, 1.0)); // warm mid band, no grey
    col = mix(col, uGround, smoothstep(0.0, -0.08, h));
    // sun glow in the haze
    col += uSunGlow * (pow(sd, 6.0) * 0.55 + pow(sd, 40.0) * 0.6) * (1.0 - smoothstep(0.1, 0.8, h) * 0.5);
    // clouds (planar projection)
    if (h > 0.0) {
      vec2 cp = d.xz / (h + 0.12);
      float c1 = texture2D(tCloud, cp * 0.18 + vec2(uTime * 0.0015, 0.0)).r;
      float c2 = texture2D(tCloud, cp * 0.45 + vec2(uTime * 0.003, 0.2)).r;
      float c = smoothstep(1.0 - uClouds, 1.15 - uClouds * 0.55, c1 * 0.7 + c2 * 0.35);
      c *= smoothstep(0.0, 0.18, h);
      vec3 lit = mix(uHorizon, uSunColor, 0.3) * mix(0.75, 1.1, smoothstep(0.0, 0.35, h)) + uSunGlow * pow(sd, 4.0) * 0.9;
      vec3 shade = mix(uZenith, uHorizon, 0.45) * 0.6;
      vec3 cc = mix(shade, lit, smoothstep(0.2, 1.0, c2 + sd * 0.4));
      col = mix(col, cc, c * 0.9);
    }
    // sun disc
    col += uSunColor * smoothstep(0.9993, 0.9997, sd) * 8.0;
    gl_FragColor = vec4(col, 1.0);
  }`;

function silhouetteTexture(seed) {
  if (assets.textures.mountain_silhouette) {
    const t = assets.textures.mountain_silhouette;
    t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.ClampToEdgeWrapping;
    return t;
  }
  const W = 1024, H = 256;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d');
  const n = makeNoise2D(seed);
  g.fillStyle = '#fff';
  g.beginPath(); g.moveTo(0, H);
  for (let x = 0; x <= W; x++) {
    const a = (x / W) * Math.PI * 2;
    const v = fbm(n, Math.cos(a) * 3, Math.sin(a) * 3, 5) * 0.5 + 0.5;
    const r = Math.abs(fbm(n, Math.cos(a) * 9 + 5, Math.sin(a) * 9, 3));
    g.lineTo(x, H - (0.25 + v * 0.55 + r * 0.2) * H);
  }
  g.lineTo(W, H); g.fill();
  const t = new THREE.CanvasTexture(c);
  t.wrapS = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Sky {
  constructor(scene, renderer, route) {
    const L = route.def.light;
    this.scene = scene; this.L = L;
    const sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - L.sunElev), THREE.MathUtils.degToRad(L.sunAzim));
    this.sunDir = sunDir;
    this.uniforms = {
      uZenith: { value: L.zenith }, uHorizon: { value: L.horizon }, uGround: { value: L.ground },
      uSunGlow: { value: L.sunGlow }, uSunColor: { value: L.sunColor }, uSunDir: { value: sunDir },
      uClouds: { value: L.clouds }, uTime: { value: 0 }, tCloud: { value: tex('cloud_noise') },
    };
    const skyMat = new THREE.ShaderMaterial({ vertexShader: skyVert, fragmentShader: skyFrag, uniforms: this.uniforms, side: THREE.BackSide, depthWrite: false, fog: false });
    this.dome = new THREE.Mesh(new THREE.SphereGeometry(4000, 32, 16), skyMat);
    this.dome.renderOrder = -10;
    this.dome.frustumCulled = false;
    scene.add(this.dome);

    // far ridge rings (two layers, atmospheric perspective)
    this.rings = [];
    const sil = silhouetteTexture(route.def.seed);
    const layers = route.biome === 'mountain'
      ? [{ r: 2400, h: 520, off: 0, mix: 0.55, rep: 3 }, { r: 1700, h: 300, off: 0.37, mix: 0.3, rep: 4 }]
      : route.biome === 'plains'
        ? [{ r: 2600, h: 200, off: 0, mix: 0.6, rep: 3 }, { r: 1900, h: 90, off: 0.5, mix: 0.4, rep: 5 }]
        : [{ r: 2500, h: 260, off: 0.2, mix: 0.55, rep: 3 }, { r: 1800, h: 140, off: 0.7, mix: 0.35, rep: 4 }];
    for (const ly of layers) {
      const t = sil.clone(); t.needsUpdate = true; t.repeat.set(ly.rep, 1); t.offset.set(ly.off, 0);
      const col = L.fog.clone().lerp(L.hemiGround.clone().multiplyScalar(0.8), 1 - ly.mix);
      const m = new THREE.MeshBasicMaterial({ map: t, color: col, transparent: true, depthWrite: false, fog: false, side: THREE.BackSide, alphaTest: 0.02 });
      const geo = new THREE.CylinderGeometry(ly.r, ly.r, ly.h, 96, 1, true);
      geo.translate(0, ly.h / 2 - 25, 0);
      const mesh = new THREE.Mesh(geo, m);
      mesh.renderOrder = -9; mesh.frustumCulled = false;
      // silhouettes are white-with-alpha: tint via color; if texture has no alpha, it's the canvas version
      this.rings.push(mesh); scene.add(mesh);
    }

    // lights
    this.sun = new THREE.DirectionalLight(L.sunColor, L.sunIntensity);
    this.sun.castShadow = true;
    const q = renderer.tier;
    this.sun.shadow.mapSize.set(q.shadowSize, q.shadowSize);
    const sc = this.sun.shadow.camera;
    this.shadowHalf = q.shadowSize >= 2048 ? 60 : 45;
    sc.left = -this.shadowHalf; sc.right = this.shadowHalf; sc.top = this.shadowHalf; sc.bottom = -this.shadowHalf; sc.near = 1; sc.far = 400;
    this.sun.shadow.bias = -0.0004; this.sun.shadow.normalBias = 0.04;
    this.sun.shadow.radius = 2;
    scene.add(this.sun, this.sun.target);
    this.hemi = new THREE.HemisphereLight(L.hemiSky, L.hemiGround, L.hemiIntensity);
    scene.add(this.hemi);

    scene.fog = new THREE.FogExp2(L.fog, L.fogDensity);
    scene.background = null;

    // environment from sky
    const pm = new THREE.PMREMGenerator(renderer.r);
    const envScene = new THREE.Scene();
    const envDome = new THREE.Mesh(new THREE.SphereGeometry(100, 32, 16), skyMat.clone());
    envDome.material.uniforms = this.uniforms;
    envScene.add(envDome);
    const gnd = new THREE.Mesh(new THREE.CircleGeometry(90, 16).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: L.ground }));
    gnd.position.y = -5; envScene.add(gnd);
    this.env = pm.fromScene(envScene, 0.04).texture;
    scene.environment = this.env;
    scene.environmentIntensity = L.env ?? 0.55;
    pm.dispose();

    // grade
    const g = L.grade, fu = renderer.final.uniforms;
    fu.uSat.value = g.sat; fu.uContrast.value = g.contrast;
    fu.uGain.value.set(...g.gain); fu.uLift.value.set(...g.lift);
    fu.uExposure.value = L.exposure;
    fu.uTintShadow.value.set(...(L.tintShadow || [0.9, 0.95, 1.05]));
  }

  update(camera, focus, t) {
    this.uniforms.uTime.value = t;
    this.dome.position.copy(camera.position);
    for (const r of this.rings) r.position.set(camera.position.x, camera.position.y - 30, camera.position.z);
    // shadow box follows focus, snapped to whole shadow texels in LIGHT space (no shimmer)
    const texel = (this.shadowHalf * 2) / this.sun.shadow.mapSize.x;
    const m = this._lm || (this._lm = new THREE.Matrix4().lookAt(new THREE.Vector3(), this.sunDir.clone().negate(), new THREE.Vector3(0, 1, 0)));
    const inv = this._lmi || (this._lmi = m.clone().invert());
    const p = this._fp || (this._fp = new THREE.Vector3());
    p.copy(focus).applyMatrix4(inv);
    p.x = Math.round(p.x / texel) * texel; p.y = Math.round(p.y / texel) * texel;
    p.applyMatrix4(m);
    this.sun.target.position.copy(p);
    this.sun.position.copy(p).addScaledVector(this.sunDir, 200);
    this.sun.target.updateMatrixWorld();
  }

  dispose() {
    this.scene.remove(this.dome, this.sun, this.sun.target, this.hemi, ...this.rings);
    this.env.dispose();
  }
}
