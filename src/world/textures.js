// Fallback textures generated at runtime (used until/unless the texture agent's
// files exist), plus small shared procedural sprites (smoke, flash, glint).
import * as THREE from 'three';
import { assets } from '../core/assets.js';
import { makeNoise2D, fbm } from '../core/noise.js';

const cache = {};

function canvasTex(size, draw, { srgb = true, repeat = true } = {}) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  draw(g, size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
  return t;
}

// Tiling noise fill using periodic sampling on a torus
function noiseFill(size, base, vary, seed, scale = 4) {
  const n = makeNoise2D(seed);
  return canvasTex(size, (g, S) => {
    const img = g.createImageData(S, S);
    for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
      const a = (x / S) * Math.PI * 2, b = (y / S) * Math.PI * 2;
      const u = Math.cos(a) * scale, v = Math.sin(a) * scale, w = Math.cos(b) * scale, q = Math.sin(b) * scale;
      const val = (fbm(n, u + w * 0.7, v + q * 0.7, 4) + fbm(n, w + 13, q - 7, 3)) * 0.5;
      const k = (y * S + x) * 4;
      img.data[k] = Math.max(0, Math.min(255, base[0] + val * vary));
      img.data[k + 1] = Math.max(0, Math.min(255, base[1] + val * vary));
      img.data[k + 2] = Math.max(0, Math.min(255, base[2] + val * vary * 0.8));
      img.data[k + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  });
}

const FALLBACK = {
  dirt_road: [[150, 118, 84], 60, 11],
  dry_grass: [[170, 140, 80], 70, 12],
  green_grass: [[110, 120, 64], 60, 13],
  sand: [[200, 164, 120], 40, 14],
  rock: [[128, 124, 118], 70, 15],
  red_rock: [[176, 96, 62], 60, 16],
  snow: [[235, 238, 245], 20, 17],
  gravel: [[140, 128, 112], 70, 18],
};

export function tex(name) {
  if (!name) return null;
  if (assets.textures[name]) return assets.textures[name];
  if (cache[name]) return cache[name];
  const f = FALLBACK[name];
  if (f) return (cache[name] = noiseFill(128, f[0], f[1], f[2]));
  if (name === 'cloud_noise') return (cache[name] = noiseFill(256, [128, 128, 128], 200, 99, 3));
  return null;
}

export function flatNormal() {
  if (cache._flatN) return cache._flatN;
  const d = new Uint8Array([128, 128, 255, 255]);
  const t = new THREE.DataTexture(d, 1, 1); t.needsUpdate = true;
  return (cache._flatN = t);
}

// ----------------------------------------------------------- FX sprites
export function softDot() {
  return cache._dot || (cache._dot = canvasTex(64, (g, S) => {
    const r = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.4, 'rgba(255,255,255,.5)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, S, S);
  }, { repeat: false }));
}

export function smokePuff() {
  return cache._smoke || (cache._smoke = canvasTex(128, (g, S) => {
    const n = makeNoise2D(5);
    const img = g.createImageData(S, S);
    for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
      const dx = x / S - 0.5, dy = y / S - 0.5;
      const r = Math.sqrt(dx * dx + dy * dy) * 2;
      const nn = fbm(n, x / 22, y / 22, 4) * 0.5 + 0.5;
      const a = Math.max(0, 1 - r * (1.1 - nn * 0.45)) ** 1.6;
      const k = (y * S + x) * 4;
      const c = 200 + nn * 55;
      img.data[k] = c; img.data[k + 1] = c; img.data[k + 2] = c; img.data[k + 3] = a * 255;
    }
    g.putImageData(img, 0, 0);
  }, { repeat: false }));
}

export function flashTex() {
  return cache._flash || (cache._flash = canvasTex(128, (g, S) => {
    g.translate(S / 2, S / 2);
    const r = g.createRadialGradient(0, 0, 0, 0, 0, S / 2);
    r.addColorStop(0, 'rgba(255,250,220,1)'); r.addColorStop(0.25, 'rgba(255,200,90,.9)'); r.addColorStop(0.6, 'rgba(255,120,30,.3)'); r.addColorStop(1, 'rgba(255,80,0,0)');
    g.fillStyle = r;
    for (let i = 0; i < 7; i++) {
      g.rotate((Math.PI * 2) / 7 + Math.random() * 0.3);
      g.beginPath(); g.moveTo(0, -5); g.lineTo(S * (0.3 + Math.random() * 0.2), 0); g.lineTo(0, 5); g.fill();
    }
    g.beginPath(); g.arc(0, 0, S * 0.22, 0, Math.PI * 2); g.fill();
  }, { repeat: false }));
}

export function grassTex() {
  if (assets.textures.grass_blade) return assets.textures.grass_blade;
  return cache._grass || (cache._grass = canvasTex(128, (g, S) => {
    for (let i = 0; i < 26; i++) {
      const x = S * (0.15 + Math.random() * 0.7), lean = (Math.random() - 0.5) * 40, h = S * (0.5 + Math.random() * 0.48);
      const l = 150 + Math.random() * 90;
      g.strokeStyle = `rgb(${l},${l * 0.85},${l * 0.5})`;
      g.lineWidth = 2 + Math.random() * 2;
      g.beginPath(); g.moveTo(x, S); g.quadraticCurveTo(x + lean * 0.3, S - h * 0.6, x + lean, S - h); g.stroke();
    }
  }, { repeat: false }));
}
