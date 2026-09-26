// Renderer + post chain + quality tiers + dynamic resolution.
// Post: scene (HDR, MSAA) -> [bloom] -> final grade pass (ACES, sRGB, colour
// grade, vignette, grain, Dead Eye look, hit flash). One fullscreen pass on low.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';

const FinalShader = {
  uniforms: {
    tDiffuse: { value: null },
    uTime: { value: 0 },
    uExposure: { value: 1.0 },
    uDeadeye: { value: 0 },
    uHit: { value: 0 },
    uVignette: { value: 0.55 },
    uGrain: { value: 0.035 },
    uSat: { value: 1.08 },
    uContrast: { value: 1.06 },
    uLift: { value: new THREE.Vector3(0.012, 0.008, 0.0) },
    uGain: { value: new THREE.Vector3(1.03, 1.0, 0.94) },
    uTintShadow: { value: new THREE.Vector3(0.9, 0.95, 1.05) },
    uAspect: { value: 1.7 },
  },
  vertexShader: /* glsl */`
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse;
    uniform float uTime, uExposure, uDeadeye, uHit, uVignette, uGrain, uSat, uContrast, uAspect;
    uniform vec3 uLift, uGain, uTintShadow;
    varying vec2 vUv;

    vec3 aces(vec3 x) {
      // Narkowicz ACES fit
      const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
      return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
    }
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

    void main() {
      vec2 uv = vUv;
      vec2 cc = uv - 0.5;
      // Dead Eye: slight barrel + chromatic split toward the edges
      float de = uDeadeye;
      vec3 hdr;
      if (de > 0.001) {
        float r2 = dot(cc, cc);
        vec2 off = cc * r2 * 0.035 * de;
        hdr.r = texture2D(tDiffuse, uv + off).r;
        hdr.g = texture2D(tDiffuse, uv).g;
        hdr.b = texture2D(tDiffuse, uv - off).b;
      } else {
        hdr = texture2D(tDiffuse, uv).rgb;
      }
      vec3 col = aces(hdr * uExposure);
      col = pow(col, vec3(1.0 / 2.2)); // to display gamma

      // grade: lift / gain, split-tone shadows cool, contrast, saturation
      float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = mix(col * uTintShadow, col, smoothstep(0.0, 0.55, l));
      col = col * uGain + uLift * (1.0 - col);
      col = (col - 0.5) * uContrast + 0.5;
      l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = mix(vec3(l), col, uSat);

      // Dead Eye: sepia/orange wash, crushed blues, red edges
      if (de > 0.001) {
        vec3 sep = vec3(l * 1.25, l * 0.92, l * 0.62);
        col = mix(col, sep, 0.72 * de);
        col = mix(col, col * vec3(1.15, 0.9, 0.75), de);
      }

      // vignette (stronger in Dead Eye / when hit)
      vec2 vc = cc * vec2(uAspect, 1.0) / uAspect * 1.9;
      float v = smoothstep(0.35, 1.25, length(vc));
      col *= 1.0 - v * (uVignette + 0.35 * de + 0.3 * uHit);
      col = mix(col, col * vec3(1.35, 0.35, 0.3), v * uHit * 0.9);

      // film grain
      float g = hash(uv * vec2(1920.0, 1080.0) + fract(uTime * 13.7)) - 0.5;
      col += g * uGrain * (1.0 + de);
      gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
    }`,
};

export const QUALITY = {
  low: { pixelRatio: 1.0, shadowSize: 1024, shadows: true, bloom: false, msaa: 0, grass: 0.3, drawDist: 420, scatter: 0.55 },
  medium: { pixelRatio: 1.5, shadowSize: 2048, shadows: true, bloom: false, msaa: 4, grass: 0.6, drawDist: 560, scatter: 0.8 },
  high: { pixelRatio: 1.75, shadowSize: 2048, shadows: true, bloom: true, msaa: 4, grass: 1, drawDist: 700, scatter: 1 },
};

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    const r = (this.r = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', stencil: false }));
    r.outputColorSpace = THREE.LinearSRGBColorSpace; // final pass does its own tonemap + gamma
    r.toneMapping = THREE.NoToneMapping;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    this.tierName = localStorage.getItem('schofield.quality') || (matchMedia('(pointer: coarse)').matches ? 'medium' : 'high');
    this.tier = QUALITY[this.tierName] || QUALITY.medium;
    this.dynScale = 1;
    this._ft = [];
    this.final = new ShaderPass(FinalShader);
  }

  setup(scene, camera) {
    this.scene = scene; this.camera = camera;
    const size = this._size();
    const rt = new THREE.WebGLRenderTarget(size.w, size.h, { type: THREE.HalfFloatType, samples: this.tier.msaa });
    this.composer = new EffectComposer(this.r, rt);
    this.composer.renderToScreen = true;
    this.renderPass = new RenderPass(scene, camera);
    this.composer.addPass(this.renderPass);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(size.w / 2, size.h / 2), 0.35, 0.6, 0.92);
    this.bloom.enabled = this.tier.bloom;
    this.composer.addPass(this.bloom);
    this.composer.addPass(this.final);
    this.resize();
    addEventListener('resize', () => this.resize());
    new ResizeObserver(() => this.resize()).observe(this.canvas);
  }

  setQuality(name) {
    this.tierName = name; this.tier = QUALITY[name];
    try { localStorage.setItem('schofield.quality', name); } catch {}
    if (this.bloom) this.bloom.enabled = this.tier.bloom;
    this.resize();
  }

  // The canvas's real on-screen size. On phones window.innerWidth/innerHeight can
  // disagree with it while the browser's toolbars slide in and out, which
  // stretches the picture away from the HUD drawn over it.
  get width() { return this.canvas.clientWidth || innerWidth; }
  get height() { return this.canvas.clientHeight || innerHeight; }

  _size() {
    const dpr = Math.min(devicePixelRatio || 1, this.tier.pixelRatio) * this.dynScale;
    return { w: Math.floor(this.width * dpr), h: Math.floor(this.height * dpr), dpr };
  }

  resize() {
    const { dpr } = this._size();
    const w = this.width, h = this.height;
    this.r.setPixelRatio(dpr);
    this.r.setSize(w, h, false);
    if (this.composer) { this.composer.setPixelRatio(dpr); this.composer.setSize(w, h); }
    if (this.camera) { this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); }
    this.final.uniforms.uAspect.value = w / h;
  }

  // Dynamic resolution: keep ~55+ fps on phones by trading pixels.
  adapt(dtReal) {
    this._ft.push(dtReal);
    if (this._ft.length < 45) return;
    const avg = this._ft.reduce((a, b) => a + b, 0) / this._ft.length;
    this._ft.length = 0;
    const prev = this.dynScale;
    if (avg > 1 / 50 && this.dynScale > 0.6) this.dynScale = Math.max(0.6, this.dynScale - 0.1);
    else if (avg < 1 / 58 && this.dynScale < 1) this.dynScale = Math.min(1, this.dynScale + 0.05);
    if (prev !== this.dynScale) this.resize();
  }

  render(time) {
    this.final.uniforms.uTime.value = time;
    this.composer.render();
  }
}
