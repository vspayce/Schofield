// A freight train on the crossing line: an 1870s American 4-4-0, its tender,
// a string of boxcars and a caboose. Built entirely in code — boxes, lathes and
// extrusions merged per car and per material — with the lettering, lining and
// board grain painted into one canvas atlas.
//
// Coordinates: every car is built in its own frame with +Z toward the front of
// the train, +Y up, and y = 0 at the top of the rail. The locomotive's origin is
// its rear driving axle; every other car's origin is its middle.
//
// Draw calls: ~5 per car (one per material) + one instanced mesh for every small
// wheelset + one for the drivers + six rods + a few odds and ends. The two
// cab crew are rider models.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { mulberry32 } from '../core/noise.js';
import { smokePuff, flashTex } from './textures.js';
import { Pool } from '../game/fx.js';
import { createRider } from '../game/characters.js';

export const RAIL_TOP = 0.366;         // rail head above the graded line (railroad.js)
const GAUGE_X = 0.75;                  // wheel tread centres either side
const DRIVER_R = 0.8, WHEEL_R = 0.42;  // 63" drivers, 33" car wheels
const CRANK = 0.3;                     // 24" stroke
const MAIN_ROD = 3.1;
const CYL_Y = 1.0, CYL_X = 1.05, CYL_Z = 4.85;
const DRIVER_Z = [0, 2.45];

const _m = new THREE.Matrix4(), _m2 = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler();
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _one = new THREE.Vector3(1, 1, 1);
const _c = new THREE.Color(), _ray = new THREE.Ray(), _inv = new THREE.Matrix4();
const Z = new THREE.Vector3(0, 0, 1), Y = new THREE.Vector3(0, 1, 0);

// Palette. Russia-iron boiler, black smokebox, red running gear, a green tender
// with gold lining, brass everywhere a fireman could polish it.
const P = {
  black: 0x1c1b1a, iron: 0x2c2a28, steel: 0x8f8b85, bright: 0xc9c4ba,
  jacket: 0x4f5d66, red: 0x7e1f16, deepRed: 0x5e1710, green: 0x1f3d2b,
  gold: 0xc79a3e, brass: 0xd9b163, copper: 0xb8734a,
  cabWood: 0x6e4222, wood: 0x6b4c30, woodDark: 0x3a2818, roof: 0x3e3833,
  bark: 0x5b4330, barkDark: 0x3f2d20, glass: 0x141a1f,
};

// ---------------------------------------------------------------- materials
let MATS = null;
function mats() {
  if (MATS) return MATS;
  const atlas = liveryAtlas();
  MATS = {
    paint: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.08, side: THREE.DoubleSide }),
    wood: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0 }),
    iron: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.42, metalness: 0.7, side: THREE.DoubleSide }),
    brass: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.26, metalness: 1, side: THREE.DoubleSide }),
    glass: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.08, metalness: 0.9 }),
    livery: new THREE.MeshStandardMaterial({ map: atlas, roughness: 0.62, metalness: 0.05 }),
    wheel: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.45, side: THREE.DoubleSide }),
    lens: new THREE.MeshBasicMaterial({ color: new THREE.Color(1.0, 0.82, 0.5).multiplyScalar(2.2), toneMapped: false, fog: true }),
    fire: new THREE.MeshBasicMaterial({ color: new THREE.Color(1.0, 0.45, 0.12).multiplyScalar(2.0), toneMapped: false }),
    marker: new THREE.MeshBasicMaterial({ color: new THREE.Color(1.0, 0.12, 0.05).multiplyScalar(1.6), toneMapped: false }),
  };
  return MATS;
}

// ------------------------------------------------------------ livery atlas
// One 2048x1024 canvas holds every painted face on the train. Rects are pixel
// boxes [x0, y0, x1, y1].
const AW = 2048, AH = 1024;
const RECT = {
  box: [[0, 0, 1024, 256], [1024, 0, 2048, 256], [0, 256, 1024, 512]],
  tender: [1024, 256, 2048, 512],
  caboose: [0, 512, 1024, 896],
  boxEnd: [1024, 512, 1536, 768],
  cab: [1536, 512, 2048, 768],
  lamp: [1024, 768, 1280, 1024],
  cabooseEnd: [1280, 768, 1536, 1024],
};
const ROAD = 'TERRITORIAL PACIFIC';
export const BOXCARS = [
  { base: '#8a3a22', ink: '#efe4c8', num: '1147', init: 'T.P.R.R.' },
  { base: '#a8813e', ink: '#2a1d12', num: '862', init: 'T.P.R.R.' },
  { base: '#6e4630', ink: '#eadfc4', num: '2215', init: 'K.&W.' },
];

function liveryAtlas() {
  const c = document.createElement('canvas');
  c.width = AW; c.height = AH;
  const x = c.getContext('2d');
  const rnd = mulberry32(1869);
  BOXCARS.forEach((b, i) => boxcarSide(x, RECT.box[i], b, rnd));
  tenderSide(x, RECT.tender, rnd);
  cabooseSide(x, RECT.caboose, rnd);
  boards(x, RECT.boxEnd, '#7a3a24', rnd, 12, true);
  cabSide(x, RECT.cab, rnd);
  lampSide(x, RECT.lamp);
  boards(x, RECT.cabooseEnd, '#8a2a1c', rnd, 9, false);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

const shade = (hex, k) => { _c.set(hex); _c.multiplyScalar(k); return '#' + _c.getHexString(); };

// vertical boards with grain, seams and the grime of a few thousand miles
function boards(x, [x0, y0, x1, y1], base, rnd, n, grime = true) {
  const w = x1 - x0, h = y1 - y0, bw = w / n;
  for (let i = 0; i < n; i++) {
    x.fillStyle = shade(base, 0.86 + rnd() * 0.24);
    x.fillRect(x0 + i * bw, y0, bw, h);
    // grain
    for (let g = 0; g < 7; g++) {
      x.strokeStyle = `rgba(30,18,10,${0.05 + rnd() * 0.08})`;
      x.lineWidth = 0.6 + rnd() * 1.2;
      const gx = x0 + i * bw + rnd() * bw;
      x.beginPath(); x.moveTo(gx, y0);
      x.bezierCurveTo(gx + (rnd() - 0.5) * 6, y0 + h * 0.3, gx + (rnd() - 0.5) * 6, y0 + h * 0.7, gx + (rnd() - 0.5) * 4, y1);
      x.stroke();
    }
    // knots
    if (rnd() < 0.35) {
      x.fillStyle = 'rgba(40,24,14,0.35)';
      x.beginPath(); x.ellipse(x0 + i * bw + rnd() * bw, y0 + rnd() * h, 2 + rnd() * 3, 4 + rnd() * 5, 0, 0, 6.3); x.fill();
    }
    x.fillStyle = 'rgba(15,8,4,0.55)';
    x.fillRect(x0 + i * bw, y0, 1.5, h);
  }
  if (!grime) return;
  weather(x, [x0, y0, x1, y1], rnd);
}

function weather(x, [x0, y0, x1, y1], rnd) {
  const w = x1 - x0, h = y1 - y0;
  // sun-bleached blotches
  for (let i = 0; i < 26; i++) {
    x.fillStyle = `rgba(235,215,180,${0.03 + rnd() * 0.05})`;
    x.beginPath(); x.ellipse(x0 + rnd() * w, y0 + rnd() * h * 0.7, 20 + rnd() * 80, 10 + rnd() * 40, 0, 0, 6.3); x.fill();
  }
  // rust and grime runs from the roof line and the hardware
  for (let i = 0; i < 60; i++) {
    const rx = x0 + rnd() * w, len = h * (0.15 + rnd() * 0.6);
    const g = x.createLinearGradient(0, y0, 0, y0 + len);
    g.addColorStop(0, `rgba(60,34,18,${0.16 + rnd() * 0.18})`); g.addColorStop(1, 'rgba(60,34,18,0)');
    x.fillStyle = g; x.fillRect(rx, y0, 1 + rnd() * 3, len);
  }
  // road dust thrown up along the bottom
  const g = x.createLinearGradient(0, y1 - h * 0.35, 0, y1);
  g.addColorStop(0, 'rgba(120,96,70,0)'); g.addColorStop(1, 'rgba(120,96,70,0.5)');
  x.fillStyle = g; x.fillRect(x0, y1 - h * 0.35, w, h * 0.35);
  // chipped paint
  for (let i = 0; i < 90; i++) {
    x.fillStyle = `rgba(${70 + rnd() * 40 | 0},${50 + rnd() * 30 | 0},30,${0.25 + rnd() * 0.3})`;
    x.fillRect(x0 + rnd() * w, y0 + rnd() * h, 1 + rnd() * 4, 1 + rnd() * 3);
  }
}

// stencilled lettering, worn: drawn then scuffed back with the base colour
function letter(x, text, px, py, size, color, { align = 'left', font = 'bold', spacing = 0, scuff = 0.25, rnd, base } = {}) {
  x.save();
  x.font = `${font} ${size}px Georgia, "Times New Roman", serif`;
  x.textAlign = align; x.textBaseline = 'middle';
  if ('letterSpacing' in x) x.letterSpacing = spacing + 'px';
  x.fillStyle = color;
  x.fillText(text, px, py);
  const wdt = x.measureText(text).width;
  x.restore();
  if (!rnd || !base) return;
  const x0 = align === 'center' ? px - wdt / 2 : align === 'right' ? px - wdt : px;
  for (let i = 0; i < 60 * scuff * (wdt / 100); i++) {
    x.fillStyle = base;
    x.globalAlpha = 0.3 + rnd() * 0.5;
    x.fillRect(x0 + rnd() * wdt, py - size / 2 + rnd() * size, 1 + rnd() * 4, 1 + rnd() * 3);
  }
  x.globalAlpha = 1;
}

function boxcarSide(x, r, b, rnd) {
  const [x0, y0, x1, y1] = r, w = x1 - x0, h = y1 - y0;
  boards(x, r, b.base, rnd, 20, false);
  // lettering left of the door: road initials and number; stencils lower left;
  // the right-hand end carries the road name small
  const cx = x0 + w * 0.24;
  letter(x, b.init, cx, y0 + h * 0.3, 44, b.ink, { align: 'center', spacing: 3, rnd, base: b.base });
  letter(x, 'No ' + b.num, cx, y0 + h * 0.55, 50, b.ink, { align: 'center', spacing: 2, rnd, base: b.base });
  letter(x, 'CAPY 20000 LBS', x0 + w * 0.05, y0 + h * 0.85, 14, b.ink, { font: '', spacing: 1, rnd, base: b.base });
  letter(x, 'WT 16800', x0 + w * 0.05, y0 + h * 0.92, 14, b.ink, { font: '', spacing: 1 });
  letter(x, ROAD, x0 + w * 0.76, y0 + h * 0.36, 22, b.ink, { align: 'center', spacing: 2, rnd, base: b.base });
  letter(x, b.num, x0 + w * 0.76, y0 + h * 0.56, 38, b.ink, { align: 'center', spacing: 2, rnd, base: b.base });
  weather(x, r, rnd);
}

// gold-lined panel with incurved corners, as the 1870s shops liked them
function linedPanel(x, px, py, pw, ph, color, width = 3, notch = 14) {
  x.strokeStyle = color; x.lineWidth = width;
  x.beginPath();
  x.moveTo(px + notch, py);
  x.lineTo(px + pw - notch, py); x.arc(px + pw, py, notch, Math.PI, Math.PI / 2, true);
  x.lineTo(px + pw, py + ph - notch); x.arc(px + pw, py + ph, notch, -Math.PI / 2, Math.PI, true);
  x.lineTo(px + notch, py + ph); x.arc(px, py + ph, notch, 0, -Math.PI / 2, true);
  x.lineTo(px, py + notch); x.arc(px, py, notch, Math.PI / 2, 0, true);
  x.closePath(); x.stroke();
}

function goldText(x, text, px, py, size, spacing = 4) {
  x.save();
  x.font = `bold ${size}px Georgia, "Times New Roman", serif`;
  x.textAlign = 'center'; x.textBaseline = 'middle';
  if ('letterSpacing' in x) x.letterSpacing = spacing + 'px';
  x.fillStyle = 'rgba(20,10,4,0.75)'; x.fillText(text, px + 3, py + 3);   // shade
  const g = x.createLinearGradient(0, py - size / 2, 0, py + size / 2);
  g.addColorStop(0, '#f6dc8e'); g.addColorStop(0.5, '#c99a3e'); g.addColorStop(1, '#8a6224');
  x.fillStyle = g; x.fillText(text, px, py);
  x.strokeStyle = 'rgba(60,30,8,0.6)'; x.lineWidth = 1; x.strokeText(text, px, py);
  x.restore();
}

function tenderSide(x, r, rnd) {
  const [x0, y0, x1, y1] = r, w = x1 - x0, h = y1 - y0;
  const g = x.createLinearGradient(0, y0, 0, y1);
  g.addColorStop(0, '#2a4c36'); g.addColorStop(1, '#173022');
  x.fillStyle = g; x.fillRect(x0, y0, w, h);
  // rivet rows at the plate seams
  x.fillStyle = 'rgba(0,0,0,0.35)';
  for (const sy of [y0 + 8, y1 - 8]) for (let k = x0 + 6; k < x1; k += 11) { x.beginPath(); x.arc(k, sy, 1.8, 0, 6.3); x.fill(); }
  for (const sx of [x0 + w * 0.34, x0 + w * 0.67]) for (let k = y0 + 8; k < y1; k += 11) { x.beginPath(); x.arc(sx, k, 1.8, 0, 6.3); x.fill(); }
  linedPanel(x, x0 + 22, y0 + 22, w - 44, h - 44, '#c99a3e', 4, 16);
  linedPanel(x, x0 + 32, y0 + 32, w - 64, h - 64, '#8a2a1c', 2, 12);
  goldText(x, ROAD, x0 + w / 2, y0 + h * 0.52, 62, 8);
  weather(x, r, rnd);
}

function cabSide(x, r, rnd) {
  const [x0, y0, x1, y1] = r, w = x1 - x0, h = y1 - y0;
  // varnished walnut panels
  boards(x, r, '#6a3e1e', rnd, 10, false);
  x.fillStyle = 'rgba(120,60,20,0.25)'; x.fillRect(x0, y0, w, h);
  linedPanel(x, x0 + 18, y0 + 18, w - 36, h - 36, '#c99a3e', 4, 14);
  linedPanel(x, x0 + 28, y0 + 28, w - 56, h - 56, '#1f3d2b', 3, 10);
  goldText(x, '9', x0 + w / 2, y0 + h * 0.52, 150, 0);
}

function lampSide(x, [x0, y0, x1, y1]) {
  const w = x1 - x0, h = y1 - y0;
  x.fillStyle = '#1f3d2b'; x.fillRect(x0, y0, w, h);
  linedPanel(x, x0 + 14, y0 + 14, w - 28, h - 28, '#c99a3e', 5, 18);
  x.fillStyle = '#7e1f16';
  x.beginPath(); x.arc(x0 + w / 2, y0 + h / 2, w * 0.3, 0, 6.3); x.fill();
  goldText(x, '9', x0 + w / 2, y0 + h * 0.53, 110, 0);
}

function cabooseSide(x, r, rnd) {
  const [x0, y0, x1, y1] = r, w = x1 - x0, h = y1 - y0;
  boards(x, r, '#8a2a1c', rnd, 22, false);
  letter(x, ROAD, x0 + w / 2, y0 + h * 0.13, 34, '#efe4c8', { align: 'center', spacing: 4, rnd, base: '#8a2a1c' });
  letter(x, 'No 07', x0 + w / 2, y0 + h * 0.9, 38, '#efe4c8', { align: 'center', spacing: 3, rnd, base: '#8a2a1c' });
  weather(x, r, rnd);
}

// ------------------------------------------------------------------ builder
// Collects primitives per material key, painted with a flat vertex colour, and
// merges each key into one mesh.
class Kit {
  constructor() { this.parts = {}; }

  _put(key, geo, col, matrix) {
    let g = geo.index ? geo.toNonIndexed() : geo;
    for (const k of Object.keys(g.attributes)) if (k !== 'position' && k !== 'normal' && k !== 'uv') g.deleteAttribute(k);
    if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    if (!g.attributes.normal) g.computeVertexNormals();
    g.morphAttributes = {};
    g.clearGroups();
    if (matrix) g.applyMatrix4(matrix);
    _c.set(col ?? 0xffffff);
    const n = g.attributes.position.count, a = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { a[i * 3] = _c.r; a[i * 3 + 1] = _c.g; a[i * 3 + 2] = _c.b; }
    g.setAttribute('color', new THREE.BufferAttribute(a, 3));
    (this.parts[key] ||= []).push(g);
    return g;
  }

  add(key, geo, col, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
    _e.set(rx, ry, rz);
    _m.compose(_v.set(x, y, z), _q.setFromEuler(_e), _one);
    return this._put(key, geo, col, _m);
  }

  // a square-section member between two points
  beam(key, a, b, w, h, col) {
    const d = _v2.subVectors(b, a), L = d.length();
    _q.setFromUnitVectors(Z, d.divideScalar(L));
    _m.compose(_v3.addVectors(a, b).multiplyScalar(0.5), _q, _one);
    return this._put(key, new THREE.BoxGeometry(w, h, L), col, _m);
  }

  // a round rod between two points
  rod(key, a, b, r, col, seg = 6) {
    const d = _v2.subVectors(b, a), L = d.length();
    _q.setFromUnitVectors(Y, d.divideScalar(L));
    _m.compose(_v3.addVectors(a, b).multiplyScalar(0.5), _q, _one);
    return this._put(key, new THREE.CylinderGeometry(r, r, L, seg), col, _m);
  }

  // a flat face textured from an atlas rect, facing +Z before rotation
  panel(w, h, rect, x, y, z, ry = 0, flip = false) {
    const g = new THREE.PlaneGeometry(w, h);
    const uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) {
      let u = uv.getX(i); const v = uv.getY(i);
      if (flip) u = 1 - u;
      uv.setXY(i, (rect[0] + u * (rect[2] - rect[0])) / AW, 1 - (rect[3] - v * (rect[3] - rect[1])) / AH);
    }
    return this.add('livery', g, 0xffffff, x, y, z, 0, ry, 0);
  }

  build(group) {
    const M = mats();
    const meshes = [];
    for (const [key, list] of Object.entries(this.parts)) {
      const geo = mergeGeometries(list, false);
      list.forEach((g) => g.dispose());
      const mesh = new THREE.Mesh(geo, M[key]);
      mesh.castShadow = key !== 'glass' && key !== 'lens' && key !== 'fire' && key !== 'marker';
      mesh.receiveShadow = true;
      group.add(mesh);
      meshes.push(mesh);
    }
    this.parts = {};
    return meshes;
  }
}

const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
// cylinder lying along Z
const cylZ = (r, len, seg = 16, r2 = r) => new THREE.CylinderGeometry(r2, r, len, seg).rotateX(Math.PI / 2);
// cylinder lying along X
const cylX = (r, len, seg = 12) => new THREE.CylinderGeometry(r, r, len, seg).rotateZ(Math.PI / 2);
const V = (x, y, z) => new THREE.Vector3(x, y, z);

// a solid made by extruding a 2D outline (in X/Y) through `depth` along Z
function extrude(pts, depth, curveSegs = 1) {
  const s = new THREE.Shape(pts.map(([a, b]) => new THREE.Vector2(a, b)));
  const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false, curveSegments: curveSegs });
  g.translate(0, 0, -depth / 2);
  return g;
}

// an arched roof: a thick circular arc spanning `span`, rising `rise`, `len` long
function archRoof(span, rise, thick, len, seg = 10) {
  const R = (span * span / 4 + rise * rise) / (2 * rise);
  const half = Math.asin(span / 2 / R);
  const pts = [];
  for (let i = 0; i <= seg; i++) { const a = -half + (2 * half * i) / seg; pts.push([R * Math.sin(a), R * Math.cos(a) - R]); }
  for (let i = seg; i >= 0; i--) { const a = -half + (2 * half * i) / seg; pts.push([(R - thick) * Math.sin(a), (R - thick) * Math.cos(a) - R]); }
  return extrude(pts, len);
}

// -------------------------------------------------------------- wheelsets
// Built at the axle: axis along X, y/z the wheel plane.
// A tyre: tread, coned, with the flange on the inner side (inner = -1 puts it
// toward -X). Profile (radius, axial) revolved around Y, then laid on its side.
function tyreLathe(r, rim, flange, width, inner) {
  const h = width / 2;
  let pts = [[rim, -h], [flange, -h], [flange, -h + 0.022], [r, -h + 0.05], [r * 0.985, h], [rim, h], [rim, -h]];
  if (inner > 0) pts = pts.map(([a, b]) => [a, -b]);
  const g = new THREE.LatheGeometry(pts.map(([rr, a]) => new THREE.Vector2(rr, a)), 28);
  g.rotateZ(-Math.PI / 2);      // lathe axis Y -> +X
  return g;
}

function smallWheelset() {
  const k = new Kit();
  for (const sx of [-1, 1]) {
    const x = sx * GAUGE_X;
    k.add('wheel', tyreLathe(WHEEL_R, WHEEL_R - 0.06, WHEEL_R + 0.035, 0.12, -sx), 0x2b2927, x);
    // dished cast-iron plate and hub
    k.add('wheel', cylX(WHEEL_R - 0.05, 0.05, 20), 0x34302c, x - sx * 0.01);
    k.add('wheel', cylX(0.1, 0.16, 10), 0x2a2724, x);
    // cast ribs on the plate
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      k.add('wheel', box(0.07, 0.24, 0.035), 0x2e2a27, x + sx * 0.02, Math.cos(a) * 0.23, Math.sin(a) * 0.23, a);
    }
  }
  k.add('wheel', cylX(0.065, GAUGE_X * 2 + 0.4, 8), 0x3a3633);
  return k;
}

// The driving wheelset: spoked centres painted red, steel tyres, counterweights
// and crankpins. Right-hand crank leads the left by a quarter turn.
export const CRANK_PHASE = [0, Math.PI / 2];   // [+X side, -X side]
function driverWheelset() {
  const k = new Kit();
  [1, -1].forEach((sx, si) => {
    const x = sx * GAUGE_X, ph = CRANK_PHASE[si];
    k.add('wheel', tyreLathe(DRIVER_R, DRIVER_R - 0.08, DRIVER_R + 0.045, 0.14, -sx), 0x3a3734, x);
    // rim (felloe) and hub
    k.add('wheel', tyreLathe(DRIVER_R - 0.08, DRIVER_R - 0.14, DRIVER_R - 0.08, 0.1, -sx), P.red, x);
    k.add('wheel', cylX(0.2, 0.18, 16), P.red, x + sx * 0.01);
    k.add('wheel', cylX(0.12, 0.24, 12), P.steel, x + sx * 0.03);
    // 14 tapered spokes
    for (let i = 0; i < 14; i++) {
      const a = (i / 14) * Math.PI * 2 + 0.11;
      const g = new THREE.CylinderGeometry(0.028, 0.04, DRIVER_R - 0.3, 6);
      g.scale(1, 1, 1.6);
      k.add('wheel', g, P.red, x, Math.cos(a) * (0.2 + (DRIVER_R - 0.3) / 2), Math.sin(a) * (0.2 + (DRIVER_R - 0.3) / 2), a);
    }
    // counterweight: a crescent opposite the pin, filling the spokes
    const cw = [], span = 1.05, c0 = ph + Math.PI;
    for (let i = 0; i <= 10; i++) { const a = c0 - span / 2 + (span * i) / 10; cw.push([Math.cos(a) * (DRIVER_R - 0.13), Math.sin(a) * (DRIVER_R - 0.13)]); }
    for (let i = 10; i >= 0; i--) { const a = c0 - span / 2 + (span * i) / 10; cw.push([Math.cos(a) * 0.32, Math.sin(a) * 0.32]); }
    const cwg = extrude(cw, 0.07);
    // shape X -> wheel y, shape Y -> wheel z, depth -> x
    _m.set(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1);
    cwg.applyMatrix4(_m);
    k.add('wheel', cwg, P.deepRed, x + sx * 0.01);
    // crank boss and pin
    const py = Math.cos(ph) * CRANK, pz = Math.sin(ph) * CRANK;
    k.add('wheel', cylX(0.1, 0.1, 12), P.red, x + sx * 0.05, py, pz);
    k.add('wheel', cylX(0.055, 0.26, 10), P.bright, x + sx * 0.16, py, pz);
  });
  k.add('wheel', cylX(0.1, GAUGE_X * 2, 10), 0x3a3633);
  return k;
}

// An arch-bar truck (side frames, journal boxes, bolster, springs, brake
// beams) centred at z = zc. The wheelsets themselves are instanced separately.
function archBarTruck(k, zc, spread = 0.76, key = 'iron') {
  const col = P.iron;
  for (const sx of [-1, 1]) {
    const x = sx * 0.97;
    for (const dz of [-spread, spread]) {
      k.add(key, box(0.2, 0.26, 0.3), col, x, WHEEL_R, zc + dz);                 // journal box
      k.add(key, box(0.22, 0.04, 0.32), col, x, WHEEL_R + 0.14, zc + dz);         // lid
    }
    // top arch bar: up from the journals, level across the bolster
    const hiA = V(x, 0.58, zc - spread), hiB = V(x, 0.74, zc - 0.35), hiC = V(x, 0.74, zc + 0.35), hiD = V(x, 0.58, zc + spread);
    k.beam(key, hiA, hiB, 0.1, 0.05, col); k.beam(key, hiB, hiC, 0.1, 0.05, col); k.beam(key, hiC, hiD, 0.1, 0.05, col);
    // inverted arch below and the tie bar
    const loA = V(x, 0.3, zc - spread), loB = V(x, 0.2, zc - 0.35), loC = V(x, 0.2, zc + 0.35), loD = V(x, 0.3, zc + spread);
    k.beam(key, loA, loB, 0.1, 0.045, col); k.beam(key, loB, loC, 0.1, 0.045, col); k.beam(key, loC, loD, 0.1, 0.045, col);
    // columns and the spring nest
    for (const dz of [-0.35, 0.35]) k.add(key, box(0.09, 0.54, 0.08), col, x, 0.47, zc + dz);
    for (const dz of [-0.12, 0.12]) k.add(key, new THREE.CylinderGeometry(0.06, 0.06, 0.26, 8), 0x3a3634, x, 0.47, zc + dz);
  }
  k.add(key, box(1.94, 0.16, 0.3), col, 0, 0.66, zc);                               // truck bolster
  for (const dz of [-spread + 0.3, spread - 0.3]) {
    k.add(key, box(1.5, 0.06, 0.07), col, 0, WHEEL_R, zc + dz);                      // brake beams
    for (const sx of [-1, 1]) k.add(key, box(0.1, 0.22, 0.07), 0x3a3634, sx * GAUGE_X, WHEEL_R, zc + dz + (dz > 0 ? 0.05 : -0.05) * 0);
  }
}

// ---------------------------------------------------------------- locomotive
function buildLoco(rnd) {
  const k = new Kit();
  const BY = 2.15;               // boiler centreline
  // -- frames, saddle, beam
  for (const sx of [-1, 1]) k.add('iron', box(0.1, 0.3, 7.4), P.black, sx * 0.52, 0.95, 1.95);
  k.add('iron', box(1.34, 0.6, 0.95), P.black, 0, 1.28, CYL_Z);
  k.add('paint', box(2.44, 0.32, 0.22), P.red, 0, 0.96, 6.02);
  k.add('brass', box(2.3, 0.025, 0.01), P.gold, 0, 1.06, 6.135);
  k.add('brass', box(2.3, 0.025, 0.01), P.gold, 0, 0.86, 6.135);
  // -- pilot: slatted V, pointing forward and raked down to the rail
  const tipTop = V(0, 0.92, 6.55), tipBot = V(0, 0.07, 7.4);
  for (const sx of [-1, 1]) {
    const outTop = V(sx * 1.16, 0.92, 6.14), outBot = V(sx * 1.06, 0.1, 6.42);
    k.beam('paint', outTop, tipTop, 0.07, 0.07, P.red);
    k.beam('paint', outBot, tipBot, 0.07, 0.06, P.red);
    for (let i = 0; i <= 8; i++) {
      const t = i / 8.6;
      const a = outTop.clone().lerp(tipTop, t), b = outBot.clone().lerp(tipBot, t);
      k.beam('paint', a, b, 0.055, 0.035, i % 2 ? P.red : P.deepRed);
    }
  }
  k.beam('paint', tipTop, tipBot, 0.08, 0.08, P.red);
  k.add('iron', box(0.24, 0.2, 0.3), P.iron, 0, 0.78, 6.66);                // coupler pocket
  k.add('iron', box(0.06, 0.06, 0.34), P.iron, 0, 0.78, 6.9);

  // -- cylinders, steam chests, guides
  for (const sx of [-1, 1]) {
    const x = sx * CYL_X;
    k.add('paint', cylZ(0.25, 0.95, 20), P.jacket, x, CYL_Y, CYL_Z);
    for (const dz of [-0.5, 0.5]) k.add('brass', cylZ(0.275, 0.07, 20), P.brass, x, CYL_Y, CYL_Z + dz);
    k.add('iron', cylZ(0.1, 0.06, 12), P.bright, x, CYL_Y, CYL_Z + 0.55);
    k.add('paint', box(0.44, 0.34, 0.86), P.jacket, sx * 1.0, CYL_Y + 0.42, CYL_Z);
    k.add('brass', box(0.47, 0.05, 0.9), P.brass, sx * 1.0, CYL_Y + 0.61, CYL_Z);
    k.add('brass', box(0.47, 0.04, 0.9), P.brass, sx * 1.0, CYL_Y + 0.25, CYL_Z);
    // cylinder cocks
    for (const dz of [-0.35, 0.35]) k.rod('iron', V(x, CYL_Y - 0.25, CYL_Z + dz), V(x, CYL_Y - 0.38, CYL_Z + dz), 0.02, P.bright);
    // crosshead guides (upper and lower bars) and the guide yoke
    for (const dy of [0.13, -0.13]) k.add('iron', box(0.07, 0.045, 1.85), P.bright, x, CYL_Y + dy, 3.45);
    k.add('iron', box(0.62, 0.8, 0.08), P.black, sx * 0.8, 1.35, 2.55);
    k.add('iron', box(0.1, 0.34, 0.1), P.black, x, CYL_Y, 2.56);
  }

  // -- boiler: smokebox, barrel, wagon-top firebox
  k.add('iron', cylZ(0.7, 1.22, 28), P.black, 0, BY, 5.16);
  k.add('iron', cylZ(0.72, 0.06, 28), P.iron, 0, BY, 5.78);
  k.add('iron', cylZ(0.5, 0.05, 24), P.black, 0, BY, 5.82);                 // door
  k.add('brass', new THREE.TorusGeometry(0.5, 0.02, 6, 28), P.brass, 0, BY, 5.845);
  k.add('iron', cylZ(0.07, 0.08, 10), P.steel, 0, BY, 5.87);                // dog
  for (const a of [0.6, -0.6, Math.PI + 0.6, Math.PI - 0.6]) k.add('iron', box(0.05, 0.05, 0.03), P.steel, Math.cos(a) * 0.46, BY + Math.sin(a) * 0.46, 5.86);
  k.add('paint', cylZ(0.62, 4.2, 28), P.jacket, 0, BY, 2.47);
  k.add('paint', cylZ(0.62, 0.35, 28, 0.66), P.jacket, 0, BY + 0.02, 0.2);   // taper course
  k.add('paint', cylZ(0.66, 1.9, 28), P.jacket, 0, BY + 0.04, -0.93);        // wagon top over the firebox
  k.add('paint', box(1.05, 1.25, 1.9), P.jacket, 0, 1.45, -0.93);            // firebox between the frames
  for (const z of [0.55, 1.6, 2.7, 3.8, 4.5]) k.add('brass', cylZ(0.632, 0.07, 28), P.brass, 0, BY, z);
  for (const z of [-0.05, -1.85]) k.add('brass', cylZ(0.672, 0.07, 28), P.brass, 0, BY + 0.04, z);
  // dome saddles and domes (steam dome polished brass, sand dome painted)
  const dome = (z, rb, h, col, key) => {
    const pts = [[0, h + 0.06], [rb * 0.55, h + 0.03], [rb * 0.86, h - 0.04], [rb, h - 0.14], [rb, 0.12], [rb * 1.12, 0.02], [rb * 1.25, -0.2]];
    k.add(key, new THREE.LatheGeometry(pts.reverse().map(([a, b]) => new THREE.Vector2(a, b)), 22), col, 0, BY + 0.6, z);
  };
  dome(1.2, 0.36, 0.62, P.brass, 'brass');
  dome(3.45, 0.3, 0.44, P.jacket, 'paint');
  k.add('brass', cylZ(0.34, 0.05, 20).rotateX(Math.PI / 2), P.brass, 0, BY + 0.6 + 0.4, 3.45);
  k.add('brass', new THREE.SphereGeometry(0.1, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2), P.brass, 0, BY + 0.6 + 0.5, 3.45);
  // whistle and safety valves on the steam dome
  const dt = BY + 0.6 + 0.68;
  k.add('brass', new THREE.CylinderGeometry(0.045, 0.045, 0.2, 10), P.brass, 0.12, dt + 0.1, 1.1);
  k.add('brass', new THREE.CylinderGeometry(0.075, 0.05, 0.22, 12), P.brass, 0.12, dt + 0.3, 1.1);
  k.add('brass', new THREE.SphereGeometry(0.06, 10, 6), P.brass, 0.12, dt + 0.44, 1.1);
  for (const sx of [-0.11, 0.0]) k.add('brass', new THREE.CylinderGeometry(0.04, 0.05, 0.28, 10), P.brass, sx - 0.02, dt + 0.12, 1.3);
  // bell yoke (the bell itself swings; see Train)
  for (const sx of [-1, 1]) k.add('iron', box(0.04, 0.46, 0.06), P.black, sx * 0.2, BY + 0.78, 2.35);
  k.add('iron', box(0.46, 0.05, 0.08), P.black, 0, BY + 1.01, 2.35);
  // stack: a balloon spark arrester on a short base
  const stack = [[0.2, -0.3], [0.21, 0.3], [0.23, 0.5], [0.3, 0.72], [0.45, 0.98], [0.57, 1.2], [0.63, 1.38], [0.62, 1.52], [0.56, 1.64], [0.42, 1.73], [0.24, 1.78], [0.16, 1.74]];
  k.add('iron', new THREE.LatheGeometry(stack.map(([a, b]) => new THREE.Vector2(a, b)), 26), P.black, 0, BY + 0.62, 5.16);
  k.add('iron', new THREE.CylinderGeometry(0.64, 0.64, 0.05, 26), P.iron, 0, BY + 0.62 + 1.45, 5.16);
  k.add('iron', new THREE.CylinderGeometry(0.3, 0.72, 0.18, 20), P.black, 0, BY + 0.62, 5.16);    // saddle
  // headlamp on its bracket, with the painted number on its sides
  k.add('iron', box(0.74, 0.05, 0.62), P.black, 0, BY + 0.72, 5.46);
  k.add('paint', box(0.56, 0.6, 0.62), P.green, 0, BY + 1.05, 5.46);
  for (const sx of [-1, 1]) k.panel(0.52, 0.52, RECT.lamp, sx * 0.282, BY + 1.05, 5.46, sx * Math.PI / 2);
  k.add('brass', box(0.6, 0.05, 0.66), P.brass, 0, BY + 1.37, 5.46);
  k.add('paint', extrude([[-0.3, 0], [0.3, 0], [0.18, 0.14], [-0.18, 0.14]], 0.6), P.green, 0, BY + 1.39, 5.46);
  k.add('iron', new THREE.CylinderGeometry(0.06, 0.07, 0.2, 10), P.black, 0, BY + 1.62, 5.4);
  k.add('iron', new THREE.CylinderGeometry(0.1, 0.06, 0.05, 10), P.black, 0, BY + 1.74, 5.4);
  k.add('brass', new THREE.TorusGeometry(0.21, 0.035, 8, 24), P.brass, 0, BY + 1.03, 5.78);
  k.add('lens', new THREE.CircleGeometry(0.2, 24), 0xffffff, 0, BY + 1.03, 5.785);

  // -- running boards with brass edging, handrails, sand pipes
  for (const sx of [-1, 1]) {
    k.add('wood', box(0.58, 0.05, 6.5), P.woodDark, sx * 0.99, 1.74, 2.35);
    k.add('brass', box(0.02, 0.08, 6.5), P.brass, sx * 1.285, 1.73, 2.35);
    k.add('iron', box(0.05, 0.14, 6.5), P.black, sx * 1.27, 1.66, 2.35);
    // boiler handrail on stanchions
    k.rod('brass', V(sx * 0.74, BY + 0.28, 0.05), V(sx * 0.74, BY + 0.28, 5.55), 0.016, P.brass);
    for (let z = 0.3; z < 5.6; z += 1.05) k.rod('brass', V(sx * 0.6, BY + 0.24, z), V(sx * 0.75, BY + 0.28, z), 0.012, P.brass);
    // sand pipe down to the front driver
    k.rod('iron', V(sx * 0.26, BY + 0.9, 3.45), V(sx * 0.66, BY + 0.2, 3.3), 0.018, P.black);
    k.rod('iron', V(sx * 0.66, BY + 0.2, 3.3), V(sx * 0.75, 0.95, 3.0), 0.018, P.black);
    // steps at the cab and at the front
    k.add('iron', box(0.35, 0.03, 0.3), P.black, sx * 1.32, 1.0, -1.25);
    k.rod('iron', V(sx * 1.25, 1.02, -1.38), V(sx * 1.25, 1.62, -1.38), 0.02, P.black);
    k.add('iron', box(0.3, 0.03, 0.25), P.black, sx * 1.1, 0.75, 5.75);
    // driver splashers: brass-beaded arcs showing above the running boards
    for (const dz of DRIVER_Z) {
      const arc = [];
      for (let i = 0; i <= 10; i++) { const a = -0.62 + 1.24 * i / 10; arc.push([Math.sin(a) * (DRIVER_R + 0.07), Math.cos(a) * (DRIVER_R + 0.07)]); }
      for (let i = 10; i >= 0; i--) { const a = -0.62 + 1.24 * i / 10; arc.push([Math.sin(a) * (DRIVER_R + 0.02), Math.cos(a) * (DRIVER_R + 0.02)]); }
      const g = extrude(arc, 0.12);
      g.rotateY(Math.PI / 2);   // outline in the z/y plane, thickness across
      k.add('brass', g, P.brass, sx * GAUGE_X, DRIVER_R, dz);
    }
  }
  // -- leading truck (outside frame, equalised)
  for (const sx of [-1, 1]) {
    const x = sx * 0.97;
    k.add('iron', box(0.1, 0.12, 1.9), P.black, x, 0.62, 4.85);
    for (const dz of [-0.6, 0.6]) k.add('iron', box(0.18, 0.24, 0.26), P.iron, x, WHEEL_R, 4.85 + dz);
    k.add('iron', box(0.09, 0.3, 0.1), P.black, x, 0.8, 4.85);
  }
  k.add('iron', box(1.94, 0.12, 0.26), P.black, 0, 0.72, 4.85);

  // -- cab: varnished wood, open windows, arched roof
  const CZ0 = -3.35, CZ1 = -1.0, CL = CZ1 - CZ0, CZ = (CZ0 + CZ1) / 2;
  k.add('wood', box(2.6, 0.1, CL + 0.2), P.woodDark, 0, 1.56, CZ - 0.1);
  for (const sx of [-1, 1]) {
    const x = sx * 1.22;
    k.add('wood', box(0.06, 1.02, CL), P.cabWood, x, 2.11, CZ);
    k.panel(CL - 0.06, 0.98, RECT.cab, sx * 1.252, 2.11, CZ, sx * Math.PI / 2);
    k.add('wood', box(0.09, 0.07, CL + 0.04), P.cabWood, x, 2.64, CZ);         // sill
    k.add('brass', box(0.1, 0.02, CL + 0.04), P.brass, x, 2.68, CZ);
    k.add('wood', box(0.08, 0.08, CL + 0.04), P.cabWood, x, 3.47, CZ);         // header
    k.add('wood', box(0.06, 0.3, CL), P.cabWood, x, 3.66, CZ);
    for (const z of [CZ0 + 0.04, CZ, CZ1 - 0.04]) k.add('wood', box(0.08, 0.84, 0.1), P.cabWood, x, 3.06, z);
    // a closed sash forward, the rear one slid open
    k.add('glass', box(0.02, 0.7, CL / 2 - 0.14), P.glass, x - sx * 0.02, 3.06, (CZ + CZ1) / 2);
    k.add('wood', box(0.05, 0.05, CL / 2 - 0.1), P.cabWood, x - sx * 0.02, 3.06, (CZ + CZ1) / 2);
    k.add('wood', box(0.05, 0.76, 0.04), P.cabWood, x - sx * 0.02, 3.06, (CZ + CZ1) / 2);
    // front wall beside the boiler, each side with a window
    const fx = sx * 0.95;
    k.add('wood', box(0.6, 1.0, 0.06), P.cabWood, fx, 2.1, CZ1);
    k.add('wood', box(0.6, 0.3, 0.06), P.cabWood, fx, 3.62, CZ1);
    k.add('wood', box(0.08, 0.9, 0.08), P.cabWood, sx * 0.69, 3.06, CZ1);
    k.add('glass', box(0.46, 0.8, 0.02), P.glass, sx * 0.96, 3.03, CZ1);
    // rear corner posts and grab irons
    k.add('wood', box(0.1, 2.2, 0.1), P.cabWood, x, 2.66, CZ0 + 0.05);
    k.rod('brass', V(sx * 1.3, 1.8, CZ1 - 0.25), V(sx * 1.3, 3.2, CZ1 - 0.25), 0.015, P.brass);
  }
  k.add('wood', box(1.28, 0.95, 0.06), P.cabWood, 0, 3.3, CZ1);
  k.add('wood', box(2.5, 0.25, 0.06), P.cabWood, 0, 3.64, CZ0);
  k.add('wood', archRoof(2.9, 0.22, 0.06, CL + 0.5, 12), P.roof, 0, 3.98, CZ);
  k.add('wood', box(3.0, 0.05, 0.08), P.cabWood, 0, 3.77, CZ1 + 0.24);
  k.add('iron', new THREE.CylinderGeometry(0.07, 0.07, 0.12, 8), P.black, 0, 4.02, CZ + 0.3);  // vent
  // backhead: firebox door glowing, gauges, reverse lever
  k.add('iron', box(1.1, 1.2, 0.05), P.iron, 0, 2.2, -1.87);
  k.add('fire', box(0.36, 0.26, 0.02), 0xffffff, 0, 1.9, -1.9);
  k.add('iron', box(0.46, 0.34, 0.03), P.black, 0, 1.9, -1.885);
  for (const sx of [-0.28, 0.28]) {
    k.add('brass', cylZ(0.08, 0.04, 14), P.brass, sx, 2.72, -1.9);
    k.add('glass', cylZ(0.065, 0.02, 14), 0xd8d2c0, sx, 2.72, -1.925);
  }
  k.rod('iron', V(-0.75, 1.6, -1.95), V(-0.72, 2.45, -2.2), 0.02, P.bright);
  k.add('wood', box(0.45, 0.06, 0.4), P.woodDark, -0.85, 2.25, -2.4);          // engineer's seat box
  k.add('wood', box(0.45, 0.06, 0.4), P.woodDark, 0.85, 2.25, -2.4);
  // drawbar to the tender, and the fall plate
  k.add('iron', box(0.3, 0.14, 0.6), P.black, 0, 1.0, -3.45);
  k.add('iron', box(1.4, 0.03, 0.5), P.iron, 0, 1.6, -3.55);
  return k;
}

// ------------------------------------------------------------------ tender
function buildTender(rnd) {
  const k = new Kit();
  const L = 6.6, TY0 = 1.24, TY1 = 2.58;
  k.add('iron', box(2.44, 0.26, L), P.black, 0, 1.1, 0);
  for (const s of [-1, 1]) k.add('paint', box(2.5, 0.3, 0.2), P.red, 0, 1.08, s * (L / 2 + 0.05));
  archBarTruck(k, -2.2); archBarTruck(k, 2.2);
  // tank: rear block and the two legs round the wood space
  k.add('paint', box(2.5, TY1 - TY0, 3.75), P.green, 0, (TY0 + TY1) / 2, -1.43);
  for (const sx of [-1, 1]) k.add('paint', box(0.42, TY1 - TY0, 2.35), P.green, sx * 1.04, (TY0 + TY1) / 2, 1.62);
  for (const sx of [-1, 1]) k.panel(6.1, TY1 - TY0, RECT.tender, sx * 1.252, (TY0 + TY1) / 2, -0.25, sx * Math.PI / 2);
  k.add('paint', box(2.52, 0.04, 6.1), P.black, 0, TY0 + 0.02, -0.25);
  // flared coping round the top
  for (const sx of [-1, 1]) {
    k.add('iron', box(0.035, 0.34, 6.1), P.black, sx * 1.33, TY1 + 0.14, -0.25, 0, 0, -sx * 0.5);
    k.add('brass', box(0.03, 0.03, 6.1), P.brass, sx * 1.415, TY1 + 0.3, -0.25);
  }
  k.add('iron', box(2.9, 0.34, 0.035), P.black, 0, TY1 + 0.14, -3.38, 0.5, 0, 0);
  // water hatch
  k.add('iron', new THREE.CylinderGeometry(0.3, 0.3, 0.12, 18), P.black, 0, TY1 + 0.06, -2.4);
  k.add('brass', new THREE.CylinderGeometry(0.26, 0.26, 0.04, 18), P.brass, 0, TY1 + 0.14, -2.4);
  // cordwood: a solid heap, dressed with logs where it shows
  k.add('wood', box(1.62, 1.3, 2.35), P.barkDark, 0, 1.9, 1.62);
  const log = (x, y, z, len, r, ry) => {
    const g = new THREE.CylinderGeometry(r, r * (0.9 + rnd() * 0.2), len, 7).rotateZ(Math.PI / 2);
    k.add('wood', g, [P.bark, P.barkDark, 0x6e5238, 0x4d3826][(rnd() * 4) | 0], x, y, z, rnd() * 3, ry, 0);
  };
  for (let layer = 0; layer < 4; layer++) {
    const y = 2.55 + layer * 0.15, zspan = 2.2 - layer * 0.35;
    for (let z = -zspan / 2; z <= zspan / 2; z += 0.16 + rnd() * 0.03) {
      log((rnd() - 0.5) * 0.25, y + (rnd() - 0.5) * 0.04, 1.62 + z + (layer ? -0.3 : 0), 1.15 + rnd() * 0.25, 0.07 + rnd() * 0.03, (rnd() - 0.5) * 0.25);
    }
  }
  // a front face of log ends toward the cab
  for (let i = 0; i < 22; i++) log(-0.7 + rnd() * 1.4, 1.35 + rnd() * 1.2, 2.82, 0.14, 0.07 + rnd() * 0.03, Math.PI / 2);
  // tool box, ladder, brake wheel, couplers
  k.add('wood', box(1.2, 0.3, 0.4), P.woodDark, 0, TY1 + 0.15, -3.0);
  for (const sx of [-0.25, 0.25]) k.rod('iron', V(sx, 1.25, -3.37), V(sx, TY1 + 0.3, -3.37), 0.015, P.black);
  for (let y = 1.4; y < TY1 + 0.2; y += 0.3) k.rod('iron', V(-0.25, y, -3.37), V(0.25, y, -3.37), 0.012, P.black);
  k.rod('iron', V(1.0, 1.2, 3.1), V(1.0, 2.9, 3.1), 0.02, P.black);
  k.add('iron', new THREE.TorusGeometry(0.22, 0.018, 6, 18).rotateX(Math.PI / 2), P.black, 1.0, 2.9, 3.1);
  k.add('iron', box(0.25, 0.22, 0.35), P.iron, 0, 0.85, -L / 2 - 0.15);
  return k;
}

// ------------------------------------------------------------------ boxcar
function buildBoxcar(i, rnd) {
  const k = new Kit(), B = BOXCARS[i % BOXCARS.length];
  const L = 9.2, W = 2.56, Y0 = 1.21, Y1 = 3.51, base = new THREE.Color(B.base).getHex();
  const dim = (h, f) => new THREE.Color(h).multiplyScalar(f).getHex();
  // underframe, end sills, queen-post truss rods
  k.add('wood', box(2.46, 0.28, L + 0.2), P.woodDark, 0, 1.07, 0);
  for (const s of [-1, 1]) k.add('wood', box(2.64, 0.3, 0.2), P.woodDark, 0, 1.07, s * (L / 2 + 0.1));
  for (const sx of [-0.62, 0.62]) {
    const a = V(sx, 0.95, -L / 2 + 0.3), b = V(sx, 0.52, -1.25), c = V(sx, 0.52, 1.25), d = V(sx, 0.95, L / 2 - 0.3);
    k.rod('iron', a, b, 0.022, P.iron); k.rod('iron', b, c, 0.022, P.iron); k.rod('iron', c, d, 0.022, P.iron);
    for (const z of [-1.25, 1.25]) k.add('iron', box(0.08, 0.42, 0.1), P.iron, sx, 0.73, z);
    k.add('iron', box(0.07, 0.07, 0.3), P.steel, sx, 0.52, 0);   // turnbuckle
  }
  archBarTruck(k, -3.25); archBarTruck(k, 3.25);
  // body and its painted board faces
  k.add('wood', box(W, Y1 - Y0, L), dim(base, 0.8), 0, (Y0 + Y1) / 2, 0);
  for (const sx of [-1, 1]) k.panel(L, Y1 - Y0, RECT.box[i % 3], sx * (W / 2 + 0.004), (Y0 + Y1) / 2, 0, sx * Math.PI / 2);
  for (const s of [-1, 1]) k.panel(W, Y1 - Y0, RECT.boxEnd, 0, (Y0 + Y1) / 2, s * (L / 2 + 0.004), s > 0 ? 0 : Math.PI);
  const batten = dim(base, 0.72);
  for (const sx of [-1, 1]) {
    const x = sx * (W / 2 + 0.018);
    for (let z = -L / 2 + 0.05; z <= L / 2 - 0.04; z += 0.46) {
      if (Math.abs(z) < 1.0) continue;                      // the door covers these
      k.add('wood', box(0.035, Y1 - Y0 - 0.12, 0.07), batten, x, (Y0 + Y1) / 2 - 0.02, z);
    }
    k.add('wood', box(0.07, 0.14, L), dim(base, 0.62), sx * (W / 2 + 0.03), Y0 + 0.05, 0);   // side sill
    k.add('wood', box(0.07, 0.12, L), dim(base, 0.62), sx * (W / 2 + 0.03), Y1 - 0.05, 0);   // plate
    for (const s of [-1, 1]) k.add('wood', box(0.1, Y1 - Y0, 0.1), dim(base, 0.6), sx * (W / 2 + 0.02), (Y0 + Y1) / 2, s * (L / 2 - 0.02));
    // sliding door: Z-braced boards on a top track
    const dx = sx * (W / 2 + 0.07), dz = sx * 0.12;
    k.add('wood', box(0.05, 2.05, 1.8), dim(base, 0.95), dx, 2.3, dz);
    for (const [yy, hh] of [[1.33, 0.1], [3.27, 0.1], [2.3, 0.1]]) k.add('wood', box(0.07, hh, 1.8), dim(base, 0.75), dx + sx * 0.01, yy, dz);
    for (const zz of [-0.86, 0.86]) k.add('wood', box(0.07, 2.05, 0.09), dim(base, 0.75), dx + sx * 0.01, 2.3, dz + zz);
    for (const hy of [1.81, 2.79]) k.beam('wood', V(dx + sx * 0.01, hy - 0.42, dz - 0.8), V(dx + sx * 0.01, hy + 0.42, dz + 0.8), 0.07, 0.09, dim(base, 0.75));
    k.add('iron', box(0.05, 0.06, 3.7), P.iron, sx * (W / 2 + 0.1), 3.38, 0.9 * sx * 0 + 0.9);
    k.add('iron', box(0.05, 0.05, 3.7), P.iron, sx * (W / 2 + 0.08), 1.26, 0.9);
    k.add('iron', box(0.04, 0.16, 0.05), P.steel, dx + sx * 0.04, 2.25, dz - 0.7);            // hasp
    // side ladder at the forward corner, grab irons at the rear
    const lz = sx > 0 ? L / 2 - 0.25 : -L / 2 + 0.25;
    for (const dzz of [-0.2, 0.2]) k.rod('iron', V(sx * (W / 2 + 0.07), Y0 + 0.1, lz + dzz), V(sx * (W / 2 + 0.07), Y1 + 0.1, lz + dzz), 0.015, P.black);
    for (let y = Y0 + 0.3; y < Y1; y += 0.38) k.rod('iron', V(sx * (W / 2 + 0.09), y, lz - 0.2), V(sx * (W / 2 + 0.09), y, lz + 0.2), 0.012, P.black);
    for (const y of [1.6, 2.1]) k.rod('iron', V(sx * (W / 2 + 0.07), y, -lz - 0.2 * Math.sign(lz)), V(sx * (W / 2 + 0.07), y, -lz + 0.2 * Math.sign(lz)), 0.012, P.black);
  }
  // roof: two shallow slopes with seam battens, walk boards on saddles
  const RS = 0.15, RH = 3.72, RW = 1.46;
  for (const sx of [-1, 1]) {
    k.add('wood', box(RW, 0.05, L + 0.3), P.roof, sx * RW / 2 * Math.cos(RS), RH - Math.sin(RS) * RW / 2, 0, 0, 0, -sx * RS);
    for (let z = -L / 2; z <= L / 2; z += 0.55) {
      k.add('wood', box(RW - 0.1, 0.035, 0.05), 0x2e2926, sx * RW / 2 * Math.cos(RS), RH - Math.sin(RS) * RW / 2 + 0.035, z, 0, 0, -sx * RS);
    }
  }
  k.add('wood', box(0.12, 0.08, L + 0.3), P.roof, 0, RH + 0.02, 0);
  for (let z = -L / 2 + 0.3; z <= L / 2; z += 1.1) k.add('wood', box(0.5, 0.08, 0.1), P.woodDark, 0, RH + 0.06, z);
  k.add('wood', box(0.52, 0.045, L + 0.5), 0x5d4a38, 0, RH + 0.12, 0);
  for (const s of [-1, 1]) k.add('wood', box(1.6, 0.045, 0.4), 0x5d4a38, 0, RH + 0.1, s * (L / 2 - 0.1));
  // brake staff and wheel at the rear end
  const bz = -L / 2 - 0.12;
  k.rod('iron', V(0.45, 1.1, bz), V(0.45, RH + 0.45, bz), 0.02, P.black);
  k.add('iron', new THREE.TorusGeometry(0.26, 0.018, 6, 20).rotateX(Math.PI / 2), P.black, 0.45, RH + 0.45, bz);
  for (let a = 0; a < 4; a++) k.add('iron', box(0.5, 0.015, 0.02), P.black, 0.45, RH + 0.45, bz, 0, a * Math.PI / 4, 0);
  // link-and-pin couplers
  for (const s of [-1, 1]) {
    k.add('iron', box(0.26, 0.22, 0.36), P.iron, 0, 0.84, s * (L / 2 + 0.3));
    if (s > 0) k.add('iron', new THREE.TorusGeometry(0.09, 0.02, 6, 12).rotateX(Math.PI / 2).scale(1, 1, 2.0), P.iron, 0, 0.84, L / 2 + 0.55);
    k.rod('iron', V(0.02, 0.92, s * (L / 2 + 0.34)), V(0.02, 1.08, s * (L / 2 + 0.34)), 0.018, P.steel);
  }
  return k;
}

// ------------------------------------------------------------------ caboose
function buildCaboose(rnd) {
  const k = new Kit();
  const BL = 5.6, W = 2.5, Y0 = 1.21, Y1 = 3.4, red = 0x8a2a1c, trim = 0x5e1c12;
  k.add('wood', box(2.46, 0.28, BL + 1.9), P.woodDark, 0, 1.07, 0);
  archBarTruck(k, -2.45, 0.7); archBarTruck(k, 2.45, 0.7);
  k.add('wood', box(W, Y1 - Y0, BL), red, 0, (Y0 + Y1) / 2, 0);
  for (const sx of [-1, 1]) {
    k.panel(BL, Y1 - Y0, RECT.caboose, sx * (W / 2 + 0.004), (Y0 + Y1) / 2, 0, sx * Math.PI / 2);
    // windows with frames and dark glass
    for (const z of [-1.5, 1.5]) {
      k.add('glass', box(0.02, 0.6, 0.55), P.glass, sx * (W / 2 + 0.01), 2.45, z);
      k.add('wood', box(0.04, 0.72, 0.07), 0xd8c9a0, sx * (W / 2 + 0.02), 2.45, z - 0.31);
      k.add('wood', box(0.04, 0.72, 0.07), 0xd8c9a0, sx * (W / 2 + 0.02), 2.45, z + 0.31);
      k.add('wood', box(0.04, 0.07, 0.69), 0xd8c9a0, sx * (W / 2 + 0.02), 2.78, z);
      k.add('wood', box(0.06, 0.06, 0.75), 0xd8c9a0, sx * (W / 2 + 0.03), 2.12, z);
    }
    k.add('wood', box(0.06, 0.12, BL), trim, sx * (W / 2 + 0.03), Y1 - 0.06, 0);
    k.add('wood', box(0.06, 0.12, BL), trim, sx * (W / 2 + 0.03), Y0 + 0.06, 0);
  }
  // ends: panelled wall with a door and window, platforms with railings
  for (const s of [-1, 1]) {
    const ez = s * (BL / 2 + 0.004);
    k.panel(W, Y1 - Y0, RECT.cabooseEnd, 0, (Y0 + Y1) / 2, ez, s > 0 ? 0 : Math.PI);
    k.add('wood', box(0.8, 1.95, 0.04), 0x6e2216, 0, 2.2, s * (BL / 2 + 0.02));
    k.add('glass', box(0.5, 0.5, 0.02), P.glass, 0, 2.7, s * (BL / 2 + 0.045));
    k.add('wood', box(2.5, 0.07, 0.95), P.woodDark, 0, 1.25, s * (BL / 2 + 0.47));
    const pz = s * (BL / 2 + 0.9);
    for (const sx of [-1, 1]) {
      k.rod('iron', V(sx * 1.2, 1.28, pz), V(sx * 1.2, 2.3, pz), 0.02, P.black);
      k.rod('iron', V(sx * 1.2, 2.3, pz), V(sx * 1.2, 2.3, s * BL / 2), 0.018, P.black);
      k.rod('iron', V(sx * 0.45, 2.3, pz), V(sx * 1.2, 2.3, pz), 0.018, P.black);
      k.rod('iron', V(sx * 0.45, 1.28, pz), V(sx * 0.45, 2.3, pz), 0.018, P.black);
      k.rod('iron', V(sx * 1.2, 1.75, pz), V(sx * 0.45, 1.75, pz), 0.014, P.black);
      // steps down at the corners
      for (const y of [0.95, 0.65]) k.add('iron', box(0.45, 0.03, 0.28), P.black, sx * 1.0, y, pz - s * 0.12);
      // marker lamps at the rear
      if (s < 0) {
        k.add('iron', box(0.16, 0.24, 0.16), P.black, sx * 1.36, 3.05, -BL / 2 + 0.1);
        k.add('marker', new THREE.CircleGeometry(0.055, 12), 0xffffff, sx * 1.36, 3.06, -BL / 2 + 0.01, 0, Math.PI, 0);
        k.add('marker', new THREE.CircleGeometry(0.055, 12), 0xffffff, sx * 1.445, 3.06, -BL / 2 + 0.1, 0, sx * Math.PI / 2, 0);
      }
    }
    k.add('iron', box(0.26, 0.22, 0.36), P.iron, 0, 0.84, s * (BL / 2 + 1.1));
  }
  // roof over the platforms, cupola, stove pipe
  for (const sx of [-1, 1]) k.add('wood', box(1.42, 0.05, BL + 2.0), P.roof, sx * 0.69, 3.55 - 0.1, 0, 0, 0, -sx * 0.14);
  k.add('wood', box(0.12, 0.07, BL + 2.0), P.roof, 0, 3.56, 0);
  const cz = -0.3, CH = 0.78;
  k.add('wood', box(1.9, CH, 1.7), red, 0, 3.55 + CH / 2, cz);
  for (const sx of [-1, 1]) {
    for (const dz of [-0.4, 0.4]) {
      k.add('glass', box(0.02, 0.36, 0.5), P.glass, sx * 0.955, 3.55 + CH / 2 + 0.03, cz + dz);
      k.add('wood', box(0.03, 0.44, 0.06), 0xd8c9a0, sx * 0.96, 3.55 + CH / 2 + 0.03, cz + dz - 0.28);
    }
    k.add('wood', box(0.03, 0.44, 0.06), 0xd8c9a0, sx * 0.96, 3.55 + CH / 2 + 0.03, cz + 0.68);
  }
  for (const s of [-1, 1]) k.add('glass', box(0.9, 0.36, 0.02), P.glass, 0, 3.55 + CH / 2 + 0.03, cz + s * 0.855);
  for (const sx of [-1, 1]) k.add('wood', box(1.1, 0.05, 2.0), P.roof, sx * 0.53, 3.55 + CH + 0.07, cz, 0, 0, -sx * 0.14);
  k.rod('iron', V(0.55, 3.5, 1.7), V(0.55, 4.35, 1.7), 0.07, P.black, 10);
  k.add('iron', new THREE.CylinderGeometry(0.14, 0.09, 0.1, 10), P.black, 0.55, 4.4, 1.7);
  k.add('wood', box(0.5, 0.045, BL + 0.6), 0x5d4a38, 0, 3.64, 0);
  return k;
}

// ------------------------------------------------------------------- train
export class Train {
  // rail: the Railroad; opts: { cars, caboose, seed, fog colour for smoke }
  constructor(scene, rail, opts = {}) {
    this.scene = scene; this.rail = rail;
    const rnd = mulberry32(opts.seed ?? 1877);
    this.root = new THREE.Group();
    this.root.visible = false;
    scene.add(this.root);
    this.cars = [];
    this.meshes = [];
    const M = mats();

    // -- cars, head to tail, each with its extents and hit box in its own frame
    const add = (kit, kind, front, back, hit, roofY = 0, slots = []) => {
      const g = new THREE.Group();
      this.meshes.push(...kit.build(g));
      this.root.add(g);
      this.cars.push({ root: g, kind, front, back, hit: new THREE.Box3(new THREE.Vector3(...hit[0]), new THREE.Vector3(...hit[1])), roofY, slots, axles: [], off: 0 });
      return this.cars[this.cars.length - 1];
    };
    const loco = add(buildLoco(rnd), 'loco', 7.4, -3.5, [[-1.32, 0.3, -3.4], [1.32, 3.95, 6.1]]);
    loco.axles.push({ z: 4.25, r: WHEEL_R }, { z: 5.45, r: WHEEL_R });
    const tender = add(buildTender(rnd), 'tender', 3.45, -3.6, [[-1.35, 0.4, -3.35], [1.35, 2.95, 3.35]]);
    tender.axles.push(...[-2.96, -1.44, 1.44, 2.96].map((z) => ({ z, r: WHEEL_R })));
    const n = opts.cars ?? 3;
    for (let i = 0; i < n; i++) {
      const c = add(buildBoxcar(i, rnd), 'boxcar', 5.05, -5.05, [[-1.36, 0.4, -4.7], [1.36, 3.86, 4.7]], 3.865, [-2.6, 2.4]);
      c.axles.push(...[-4.01, -2.49, 2.49, 4.01].map((z) => ({ z, r: WHEEL_R })));
    }
    if (opts.caboose !== false) {
      const c = add(buildCaboose(rnd), 'caboose', 4.12, -4.12, [[-1.3, 0.4, -3.8], [1.3, 3.6, 3.8]]);
      c.axles.push(...[-3.15, -1.75, 1.75, 3.15].map((z) => ({ z, r: WHEEL_R })));
    }
    // couple them up: each car's front meets the one ahead's back
    let o = 0;
    this.cars.forEach((c, i) => {
      if (i > 0) o += c.front;
      c.off = i === 0 ? c.front : o;
      o = c.off - c.back;
    });
    this.length = o;

    // -- instanced wheelsets
    const nAx = this.cars.reduce((a, c) => a + c.axles.length, 0);
    this.wheels = this._instanced(smallWheelset(), nAx);
    this.drivers = this._instanced(driverWheelset(), 2);

    // -- moving parts on the locomotive: rods, crossheads, bell
    this.rods = [];
    const L = loco.root;
    for (const [si, sx] of [[0, 1], [1, -1]]) {
      const x = sx * (GAUGE_X + 0.2);
      const cr = new Kit();
      cr.add('iron', box(0.05, 0.11, DRIVER_Z[1] + 0.2), P.bright, 0, 0, DRIVER_Z[1] / 2);
      for (const z of [0, DRIVER_Z[1]]) cr.add('iron', cylX(0.1, 0.07, 14), P.bright, 0, 0, z);
      const couple = this._part(cr, L); couple.position.x = x;
      const mr = new Kit();
      mr.add('iron', box(0.055, 0.12, MAIN_ROD - 0.2), P.bright, 0, 0, MAIN_ROD / 2);
      mr.add('iron', cylX(0.12, 0.08, 14), P.bright, 0, 0, 0);
      mr.add('iron', box(0.08, 0.2, 0.26), P.bright, 0, 0, MAIN_ROD);
      const main = this._part(mr, L); main.position.x = sx * (CYL_X);
      const xh = new Kit();
      xh.add('iron', box(0.16, 0.22, 0.3), P.steel, 0, 0, 0);
      xh.add('iron', cylZ(0.04, 1.3, 10), P.bright, 0, 0, 0.8);
      const cross = this._part(xh, L); cross.position.x = sx * CYL_X;
      this.rods.push({ si, couple, main, cross });
    }
    const bk = new Kit();
    const bellPts = [[0.02, 0.02], [0.09, 0.0], [0.12, -0.1], [0.15, -0.22], [0.2, -0.3], [0.19, -0.32], [0.0, -0.3]];
    bk.add('brass', new THREE.LatheGeometry(bellPts.map(([a, b]) => new THREE.Vector2(a, b)), 20), P.brass);
    bk.add('brass', new THREE.SphereGeometry(0.04, 8, 6), P.brass, 0, 0.04, 0);
    bk.add('iron', cylX(0.025, 0.42, 8), P.black);
    this.bell = this._part(bk, L); this.bell.position.set(0, 2.15 + 1.0, 2.35);
    this.bellSwing = 0;

    // -- the headlamp's glow (a beam would be invisible against a golden-hour sky)
    this.glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: flashTex(), color: 0xffc890, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: true }));
    this.glow.scale.setScalar(0.95);
    this.glow.position.set(0, 2.15 + 1.03, 5.86);
    L.add(this.glow);

    // -- crew
    this.crew = [];
    for (const [variant, x, z, ry] of [['driver', -0.78, -2.15, -0.5], ['bandit3', 0.62, -2.7, 0.9]]) {
      const c = createRider({ variant });
      c.root.position.set(x, 1.61, z);
      c.root.rotation.y = ry;
      if (c.has('StandIdle')) c.play('StandIdle');
      c.root.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
      L.add(c.root);
      this.crew.push(c);
    }

    // -- smoke, steam and dust: one pool, one draw call
    this.fx = new Pool(scene, 760, smokePuff(), false);
    this.fx.mesh.visible = false;
    const light = opts.light;
    const warm = light ? light.sunColor.clone() : new THREE.Color(1, 0.85, 0.7);
    this.smokeDark = new THREE.Color(0.3, 0.28, 0.26).lerp(warm, 0.12);
    this.smokeLight = new THREE.Color(0.62, 0.58, 0.54).lerp(warm, 0.25);
    this.steamCol = new THREE.Color(0.96, 0.95, 0.94);
    this.dustCol = light ? light.ground.clone().lerp(light.sunColor, 0.35).lerp(new THREE.Color(1, 1, 1), 0.25) : new THREE.Color(0.7, 0.6, 0.5);

    this.x = -1e4;          // head of the train, metres past the crossing along travel
    this.sdir = 1;          // +1: runs along rail.dir, -1: against it
    this.speed = 0;
    this.odo = 0;           // metres run, drives the wheels
    this.active = false;
    this.fwd = new THREE.Vector3();
    this.vel = new THREE.Vector3();
    this.onChuff = null;
    this._chuffPhase = 0;
    this._t = 0;
    this._sway = this.cars.map(() => ({ a: rnd() * 6.3, b: rnd() * 6.3 }));
    this._smokeAcc = 0; this._dustAcc = 0;
  }

  _instanced(kit, count) {
    const g = new THREE.Group();
    const [mesh] = kit.build(g);
    const im = new THREE.InstancedMesh(mesh.geometry, mesh.material, count);
    im.castShadow = true; im.receiveShadow = true;
    im.frustumCulled = false;
    im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.root.add(im);
    this.meshes.push(im);
    return im;
  }

  _part(kit, parent) {
    const g = new THREE.Group();
    const ms = kit.build(g);
    this.meshes.push(...ms);
    const m = ms.length === 1 ? ms[0] : g;
    parent.add(m);
    return m;
  }

  setActive(on) {
    this.active = on;
    this.root.visible = on;
    this.fx.mesh.visible = on || this.fx.p.length > 0;
  }

  // where along the line a point `back` metres behind the head sits, as u
  uAt(back) { return this.sdir * (this.x - back); }

  // Put every car on the rails for the current head position `x`
  place() {
    const R = this.rail;
    this.fwd.copy(R.dir).multiplyScalar(this.sdir);
    const yaw = Math.atan2(this.fwd.x, this.fwd.z);
    const pitch = Math.atan(R.grade * this.sdir);
    this.cars.forEach((c, i) => {
      const u = this.uAt(c.off);
      R._at(u, c.root.position);
      c.root.position.y += RAIL_TOP;
      const sw = this._sway[i];
      // a little roll and hunting from the track, more on the light cars
      const k = c.kind === 'loco' ? 0.5 : 1;
      const roll = k * (0.006 * Math.sin(this._t * 1.9 + sw.a) + 0.003 * Math.sin(this._t * 5.3 + sw.b)) * Math.min(1, this.speed / 8);
      c.root.rotation.set(-pitch + 0.0015 * Math.sin(this._t * 3.1 + sw.b) * k, yaw, roll, 'YXZ');
      c.root.updateMatrixWorld(true);
    });
  }

  update(dt, camPos) {
    if (!this.active) {
      if (this.fx.p.length) this.fx.update(dt); else this.fx.mesh.visible = false;
      return;
    }
    this._t += dt;
    this.x += this.speed * dt;
    this.odo += this.speed * dt;
    this.place();
    this.vel.copy(this.fwd).multiplyScalar(this.speed);

    // wheelsets: small wheels from the odometer, drivers too
    let n = 0;
    for (const c of this.cars) {
      for (const a of c.axles) {
        _m2.makeRotationX(this.odo / a.r).setPosition(0, a.r, a.z);
        _m.multiplyMatrices(c.root.matrixWorld, _m2);
        this.wheels.setMatrixAt(n++, _m);
      }
    }
    this.wheels.instanceMatrix.needsUpdate = true;
    const th = this.odo / DRIVER_R;
    const loco = this.cars[0];
    DRIVER_Z.forEach((z, i) => {
      _m2.makeRotationX(th).setPosition(0, DRIVER_R, z);
      _m.multiplyMatrices(loco.root.matrixWorld, _m2);
      this.drivers.setMatrixAt(i, _m);
    });
    this.drivers.instanceMatrix.needsUpdate = true;
    // rods follow the crankpins: the side rod stays level, the main rod
    // swings between the pin and the crosshead in its guides
    for (const r of this.rods) {
      const a = th + CRANK_PHASE[r.si];
      const py = DRIVER_R + Math.cos(a) * CRANK, pz = Math.sin(a) * CRANK;
      r.couple.position.set(r.couple.position.x, py, pz);
      const dy = CYL_Y - py;
      const cz = pz + Math.sqrt(MAIN_ROD * MAIN_ROD - dy * dy);
      r.main.position.set(r.main.position.x, py, pz);
      r.main.rotation.x = -Math.asin(dy / MAIN_ROD);
      r.cross.position.set(r.cross.position.x, CYL_Y, cz);
    }
    // bell rocks while it's ringing
    this.bellSwing = Math.max(0, this.bellSwing - dt * 0.35);
    this.bell.rotation.x = Math.sin(this._t * 5.2) * 0.6 * this.bellSwing;
    for (const c of this.crew) c.update(dt);

    // exhaust beats: four per turn of the drivers
    const beats = th / (Math.PI / 2);
    if (Math.floor(beats) !== Math.floor(this._chuffPhase)) this._chuff(Math.floor(beats) % 2);
    this._chuffPhase = beats;

    const near = camPos ? camPos.distanceTo(loco.root.position) : 0;
    this._smoke(dt, near);
    this._dust(dt, camPos);
    this.fx.update(dt);
  }

  _chuff(side) {
    const L = this.cars[0].root;
    // a thick puff up the stack: a dark core and lighter billows round it
    const top = L.localToWorld(_v.set(0, 4.4, 5.16));
    for (let i = 0; i < 4; i++) {
      this.fx.spawn({
        pos: top, vel: _v2.copy(this.vel).multiplyScalar(0.6).add(_v3.set((Math.random() - 0.5) * 1.6, 6 + Math.random() * 3, (Math.random() - 0.5) * 1.6)),
        life: 6.5 + Math.random() * 3.5, size: 1.0 + Math.random() * 0.4, size1: 10 + Math.random() * 5, color: i < 2 ? this.smokeDark : this.smokeLight,
        alpha: i < 2 ? 0.72 : 0.5, drag: 0.8, grav: -0.35, spin: 0.35, fadeIn: 0.015,
      });
    }
    // cylinder cocks spitting, on the side that just exhausted
    const sx = side ? -1 : 1;
    const cock = L.localToWorld(new THREE.Vector3(sx * CYL_X, CYL_Y - 0.4, CYL_Z + 0.35));
    const out = _v3.set(sx, 0, 0).transformDirection(L.matrixWorld);
    this.fx.spawn({
      pos: cock, vel: _v2.copy(this.vel).multiplyScalar(0.75).addScaledVector(out, 2 + Math.random() * 1.5).add(_v.set(0, -0.2 + Math.random() * 0.4, 0)),
      life: 0.7 + Math.random() * 0.4, size: 0.2, size1: 1.6, color: this.steamCol, alpha: 0.32, drag: 2.6, grav: -0.5, fadeIn: 0.02,
    });
    this.onChuff?.(side);
  }

  // a steady plume between the beats
  _smoke(dt, near) {
    this._smokeAcc += dt * 12;
    const L = this.cars[0].root;
    while (this._smokeAcc > 1) {
      this._smokeAcc -= 1;
      const top = L.localToWorld(_v.set((Math.random() - 0.5) * 0.4, 4.45, 5.16 + (Math.random() - 0.5) * 0.4));
      this.fx.spawn({
        pos: top, vel: _v2.copy(this.vel).multiplyScalar(0.55).add(_v3.set((Math.random() - 0.5) * 1.2, 3.5 + Math.random() * 2, (Math.random() - 0.5) * 1.2)),
        life: 7 + Math.random() * 4, size: 1.0, size1: 11 + Math.random() * 6, color: Math.random() < 0.55 ? this.smokeDark : this.smokeLight,
        alpha: 0.42, drag: 0.7, grav: -0.3, spin: 0.3, fadeIn: 0.03,
      });
    }
  }

  // dust off the ballast along the train, only when someone's close enough to see it
  _dust(dt, camPos) {
    if (!camPos) return;
    const R = this.rail;
    this._dustAcc += dt * 28;
    while (this._dustAcc > 1) {
      this._dustAcc -= 1;
      const back = Math.random() * this.length;
      const p = R._at(this.uAt(back), _v);
      if (p.distanceTo(camPos) > 70) continue;
      const sd = Math.random() < 0.5 ? -1 : 1;
      p.addScaledVector(R.side, sd * (1.1 + Math.random() * 0.6)); p.y += 0.3;
      this.fx.spawn({
        pos: p, vel: _v2.copy(this.vel).multiplyScalar(0.3).addScaledVector(R.side, sd * (1 + Math.random() * 1.5)).add(_v3.set(0, 0.4 + Math.random() * 0.6, 0)),
        life: 1.6 + Math.random(), size: 0.5, size1: 3, color: this.dustCol, alpha: 0.28, drag: 1.8, grav: 0.1, fadeIn: 0.1,
      });
    }
  }

  // metres along the train's travel occupied: [tail, head]
  span() { return [this.x - this.length, this.x]; }

  // a point on the roof walk of car i, `z` along the car
  roofPoint(i, z, out) {
    const c = this.cars[i];
    return c.root.localToWorld(out.set(0, c.roofY, z));
  }

  // nearest hit on any car body; kind is 'iron' for the engine, 'wood' otherwise
  rayHit(origin, dir, range) {
    if (!this.active) return null;
    let best = null;
    for (const c of this.cars) {
      _inv.copy(c.root.matrixWorld).invert();
      _ray.origin.copy(origin).applyMatrix4(_inv);
      _ray.direction.copy(dir).transformDirection(_inv);
      const p = _ray.intersectBox(c.hit, _v);
      if (!p) continue;
      const t = p.distanceTo(_ray.origin);
      if (t < 0.5 || t > (best ? best.t : range)) continue;
      best = { t, point: origin.clone().addScaledVector(dir, t), kind: c.kind === 'loco' ? 'iron' : 'wood', car: c };
    }
    return best;
  }

  // distance from a world point to the nearest part of the train (plan view)
  distanceTo(p) {
    const R = this.rail;
    const dx = p.x - R.centre.x, dz = p.z - R.centre.z;
    const u = dx * R.dir.x + dz * R.dir.z;
    const lat = Math.abs(dx * R.side.x + dz * R.side.z);
    const along = u * this.sdir;                  // in the train's travel frame
    const [t, h] = this.span();
    const off = along > h ? along - h : along < t ? t - along : 0;
    return Math.hypot(off, Math.max(0, lat - 1.4));
  }

  dispose() {
    this.scene.remove(this.root);
    this.scene.remove(this.fx.mesh);
    this.fx.mesh.geometry.dispose(); this.fx.mesh.material.dispose();
    for (const m of this.meshes) m.geometry.dispose();
    this.glow.material.dispose();
  }
}
