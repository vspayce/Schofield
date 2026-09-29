// The train: a 4-4-0 American with its tender and a string of boxcars, built
// here from primitives rather than shipped as a GLB (like the billboards and
// the railroad itself). It runs the finished line through the road crossing,
// timed the way the buffalo herd is — so it's across the road just as a coach
// at cruise would get there, and hauling on the reins is the answer.
//
// Gunmen ride the boxcar roofs. They are the ordinary Gunman from enemies.js,
// carried by their car, so chevrons, Dead Eye and bounties all just work.
// Drive onto the crossing while it's going by and the coach is thrown back
// off the rails, much as the herd collision in wildlife.js.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { audio } from '../core/audio.js';
import { Gunman } from './enemies.js';
import { clamp, mulberry32 } from '../core/noise.js';

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _m = new THREE.Matrix4(), _ray = new THREE.Ray();
const _Z = new THREE.Vector3(0, 0, 1);

// rail head is this far above the graded bed line (see Railroad._rails)
const RAIL_TOP = 0.365;
// half the width of the widest car, for the crossing test
const HALF_W = 1.45;
// where the coach and its team sit relative to coach.s, front to back: the lead
// pair's noses are ~7.5 m ahead of the body
const COACH_PTS = [7.6, 6, 4, 2, 0, -2];
const COACH_HALF = 0.9;

function std(color, roughness = 0.8, metalness = 0) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

// Collects primitives by material and bakes them into one mesh per material, so
// a car costs a handful of draw calls rather than a hundred.
class Parts {
  constructor() { this.by = new Map(); }
  add(geo, mat, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
    const g = geo.index ? geo.toNonIndexed() : geo;
    g.applyMatrix4(_m.compose(_v.set(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), _v2.set(1, 1, 1)));
    if (!this.by.has(mat)) this.by.set(mat, []);
    this.by.get(mat).push(g);
    return this;
  }
  box(w, h, l, mat, x, y, z, rx, ry, rz) { return this.add(new THREE.BoxGeometry(w, h, l), mat, x, y, z, rx, ry, rz); }
  // a cylinder lying along Z
  tube(r0, r1, len, mat, x, y, z, seg = 16) { return this.add(new THREE.CylinderGeometry(r0, r1, len, seg), mat, x, y, z, Math.PI / 2); }
  bake(into) {
    const box = new THREE.Box3();
    for (const [mat, geos] of this.by) {
      const m = new THREE.Mesh(mergeGeometries(geos, false), mat);
      m.castShadow = true; m.receiveShadow = true;
      m.geometry.computeBoundingBox();
      box.union(m.geometry.boundingBox);
      into.add(m);
      geos.forEach((g) => g.dispose());
    }
    this.by.clear();
    return box;
  }
}

// ------------------------------------------------------------- materials
function sideTexture(num, rnd) {
  const W = 1024, H = 256;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const x = c.getContext('2d');
  x.fillStyle = '#6e2c1c'; x.fillRect(0, 0, W, H);           // oxide red
  // board seams and a sun-faded top edge
  for (let i = 0; i < W; i += 21) {
    x.fillStyle = `rgba(30,10,5,${0.25 + rnd() * 0.2})`; x.fillRect(i, 0, 2, H);
    x.fillStyle = `rgba(160,90,60,${rnd() * 0.08})`; x.fillRect(i + 2, 0, 19, H);
  }
  const fade = x.createLinearGradient(0, 0, 0, H);
  fade.addColorStop(0, 'rgba(210,160,120,0.22)'); fade.addColorStop(0.5, 'rgba(0,0,0,0)'); fade.addColorStop(1, 'rgba(30,15,5,0.3)');
  x.fillStyle = fade; x.fillRect(0, 0, W, H);
  for (let i = 0; i < 50; i++) {
    x.fillStyle = `rgba(${90 + rnd() * 60 | 0},${60 + rnd() * 40 | 0},40,${0.03 + rnd() * 0.05})`;
    x.beginPath(); x.arc(rnd() * W, rnd() * H, 10 + rnd() * 50, 0, 6.3); x.fill();
  }
  // lettering either side of the door
  x.fillStyle = '#e6dcc4'; x.textAlign = 'center';
  x.font = 'bold 34px Georgia, serif';
  x.fillText('MERCY SPRINGS', W * 0.19, 92);
  x.fillText('& RED MESA', W * 0.19, 134);
  x.font = '22px Georgia, serif';
  x.fillText('RAIL ROAD', W * 0.19, 170);
  x.font = 'bold 48px Georgia, serif';
  x.fillText('No. ' + num, W * 0.81, 120);
  x.font = '20px Georgia, serif';
  x.fillText('CAPY 40000 LBS', W * 0.81, 160);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

function materials() {
  return {
    iron: std(0x1c1d1f, 0.55, 0.6),
    boiler: std(0x22302a, 0.42, 0.4),       // Russia-iron green-black
    brass: std(0x9c7b3a, 0.32, 0.85),
    red: std(0x7a2418, 0.6, 0.05),
    wood: std(0x5e3522, 0.9),
    board: std(0x7a6a55, 0.95),
    roof: std(0x2e2824, 0.95),
    coal: std(0x121212, 0.9),
    lamp: new THREE.MeshStandardMaterial({ color: 0xfff0c0, emissive: 0xffc070, emissiveIntensity: 2.2 }),
  };
}

// ----------------------------------------------------------------- wheels
// A wheelset: both wheels and the axle in one mesh, spun about X. Drivers and
// the engine truck get spokes; freight cars ride on plain cast-iron discs.
function wheelset(M, r, spokes) {
  const P = new Parts();
  for (const sx of [-1, 1]) {
    const x = sx * 0.76;
    if (spokes) {
      P.add(new THREE.TorusGeometry(r - 0.05, 0.065, 6, 24), M.iron, x, 0, 0, 0, Math.PI / 2);
      for (let k = 0; k < spokes; k++) P.box(0.05, r * 2 - 0.14, 0.06, M.red, x, 0, 0, (k / spokes) * Math.PI);
      P.add(new THREE.CylinderGeometry(0.15, 0.15, 0.16, 10), M.red, x, 0, 0, 0, 0, Math.PI / 2);
      // counterweight on the drivers
      if (r > 0.6) P.box(0.08, r * 0.45, r * 0.7, M.red, x, -r * 0.55, 0);
    } else {
      P.add(new THREE.CylinderGeometry(r, r, 0.12, 16), M.iron, x, 0, 0, 0, 0, Math.PI / 2);
      P.add(new THREE.CylinderGeometry(r * 0.45, r * 0.45, 0.16, 10), M.iron, x, 0, 0, 0, 0, Math.PI / 2);
    }
  }
  P.add(new THREE.CylinderGeometry(0.06, 0.06, 1.5, 6), M.iron, 0, 0, 0, 0, 0, Math.PI / 2);
  const g = new THREE.Group();
  P.bake(g);
  return g;
}

// ------------------------------------------------------------------- cars
// Each builder returns { root, front, back, wheels: [{o, r}], box, roof? }.
// Local frame: +Z forward, +Y up, y = 0 on the rail head, origin mid-car.

function buildLoco(M) {
  const root = new THREE.Group(), P = new Parts();
  // frame, pilot beam and cowcatcher
  P.box(1.3, 0.3, 8.6, M.iron, 0, 1.05, 0.6);
  P.box(2.3, 0.35, 0.3, M.red, 0, 0.95, 4.8);
  {
    const BL = [-1.1, 0.12, 4.95], BF = [0, 0.12, 5.9], BR = [1.1, 0.12, 4.95];
    const TL = [-1.1, 0.8, 4.9], TF = [0, 0.8, 5.05], TR = [1.1, 0.8, 4.9];
    const tri = [TL, BL, BF, TL, BF, TF, TF, BF, BR, TF, BR, TR, TL, TF, TR].flat();
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(tri, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(new Array(tri.length / 3 * 2).fill(0), 2));
    g.computeVertexNormals();
    P.add(g, M.red);
    // slats down the faces of the plough
    for (let i = 0; i < 5; i++) {
      const t = (i + 0.5) / 5;
      for (const sx of [-1, 1]) {
        const x = sx * 1.1 * (1 - t), z = 4.93 + (5.5 - 4.93) * t;
        P.box(0.05, 0.75, 0.05, M.iron, x, 0.46, z + 0.04, -0.75, 0, 0);
      }
    }
  }
  // cylinders and steam chests
  for (const sx of [-1, 1]) {
    P.tube(0.32, 0.32, 1.1, M.iron, sx * 0.98, 1.2, 3.3);
    P.box(0.5, 0.45, 0.9, M.boiler, sx * 0.85, 1.65, 3.3);
    P.box(0.34, 0.05, 5.4, M.iron, sx * 0.98, 1.66, 1.2);      // running board
  }
  // smokebox, boiler, bands
  P.tube(0.8, 0.8, 1.1, M.iron, 0, 2.05, 4.1, 20);
  P.tube(0.62, 0.62, 0.06, M.iron, 0, 2.05, 4.68, 20);
  P.tube(0.72, 0.72, 4.1, M.boiler, 0, 2.05, 1.55, 20);
  for (const z of [0.1, 1.1, 2.1, 3.1]) P.tube(0.735, 0.735, 0.08, M.brass, 0, 2.05, z, 20);
  P.box(1.3, 1.3, 1.5, M.boiler, 0, 1.75, -0.95);              // firebox
  // balloon stack
  P.add(new THREE.CylinderGeometry(0.24, 0.26, 0.7, 12), M.iron, 0, 3.12, 4.05);
  P.add(new THREE.CylinderGeometry(0.64, 0.26, 0.85, 14), M.iron, 0, 3.87, 4.05);
  P.add(new THREE.CylinderGeometry(0.68, 0.64, 0.12, 14), M.iron, 0, 4.35, 4.05);
  // domes and bell
  P.add(new THREE.CylinderGeometry(0.3, 0.36, 0.55, 12), M.brass, 0, 2.95, 0.8);
  P.add(new THREE.SphereGeometry(0.3, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2), M.brass, 0, 3.22, 0.8);
  P.add(new THREE.CylinderGeometry(0.26, 0.32, 0.45, 12), M.brass, 0, 2.9, 2.5);
  P.add(new THREE.SphereGeometry(0.26, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2), M.brass, 0, 3.12, 2.5);
  P.add(new THREE.CylinderGeometry(0.1, 0.19, 0.26, 10), M.brass, 0, 2.98, 1.65);
  // headlamp, a big square box on the smokebox with a lit face
  P.box(0.62, 0.62, 0.62, M.red, 0, 3.15, 4.62);
  P.box(0.7, 0.08, 0.7, M.brass, 0, 3.5, 4.62);
  P.add(new THREE.CircleGeometry(0.24, 16), M.lamp, 0, 3.15, 4.94);
  // cab: walls, window openings, overhanging roof
  P.box(2.3, 2.1, 2.0, M.red, 0, 2.45, -2.3);
  for (const sx of [-1, 1]) {
    P.box(0.03, 0.62, 0.7, M.iron, sx * 1.16, 2.9, -1.95);
    P.box(0.03, 0.62, 0.5, M.iron, sx * 1.16, 2.9, -2.8);
  }
  P.box(2.6, 0.12, 2.6, M.roof, 0, 3.56, -2.3);
  P.box(2.3, 0.3, 0.9, M.iron, 0, 1.3, -3.1);                   // deck
  const box = P.bake(root);

  const wheels = [];
  for (const [z, r, sp] of [[4.0, 0.42, 8], [3.0, 0.42, 8], [1.1, 0.8, 14], [-0.7, 0.8, 14]]) {
    const w = wheelset(M, r, sp);
    w.position.set(0, r, z); root.add(w);
    wheels.push({ o: w, r });
  }
  // side rods couple the drivers; main rods run back from the crossheads
  const rods = [];
  for (const sx of [-1, 1]) {
    const side = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.12, 1.8 + 0.2), M.iron);
    const main = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.14, 1), M.iron);
    const xh = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.22, 0.3), M.iron);
    for (const m of [side, main, xh]) { m.castShadow = true; root.add(m); }
    rods.push({ sx, side, main, xh });
  }
  return { root, front: 5.9, back: -3.4, wheels, box, rods, stack: new THREE.Vector3(0, 4.45, 4.05) };
}

function truck(M, root, z, wheels) {
  const P = new Parts();
  for (const sx of [-1, 1]) P.box(0.12, 0.3, 2.0, M.iron, sx * 0.86, 0.5, z);
  P.box(1.9, 0.18, 0.3, M.iron, 0, 0.75, z);
  P.bake(root);
  for (const dz of [-0.72, 0.72]) {
    const w = wheelset(M, 0.42, 0);
    w.position.set(0, 0.42, z + dz); root.add(w);
    wheels.push({ o: w, r: 0.42 });
  }
}

function buildTender(M) {
  const root = new THREE.Group(), P = new Parts();
  P.box(2.3, 0.25, 6.0, M.iron, 0, 1.0, 0);
  P.box(2.4, 1.3, 4.4, M.boiler, 0, 1.8, -0.7);                  // water tank
  P.box(2.46, 0.08, 4.46, M.brass, 0, 2.45, -0.7);
  P.box(2.4, 0.8, 1.6, M.boiler, 0, 1.55, 2.1);                  // coal bunker walls
  P.add(new THREE.SphereGeometry(1, 10, 6).scale(1.05, 0.42, 0.9), M.coal, 0, 2.05, 1.9);
  P.box(0.5, 0.2, 0.5, M.iron, 0, 2.55, -2.3);                   // tank hatch
  P.box(0.3, 0.25, 0.5, M.iron, 0, 1.0, 3.15);
  const box = P.bake(root);
  const wheels = [];
  truck(M, root, 1.9, wheels);
  truck(M, root, -1.9, wheels);
  return { root, front: 3.2, back: -3.1, wheels, box };
}

function buildBoxcar(M, num, rnd) {
  const root = new THREE.Group(), P = new Parts();
  const L = 9.6, W = 2.7, H = 2.5, base = 1.1;
  P.box(2.3, 0.3, L + 0.2, M.iron, 0, 0.98, 0);                   // underframe
  P.box(W, H, L, M.wood, 0, base + H / 2, 0);
  P.box(W + 0.2, 0.12, L + 0.3, M.roof, 0, base + H + 0.06, 0);
  P.box(0.55, 0.06, L + 0.3, M.board, 0, base + H + 0.15, 0);     // running board
  for (const sx of [-1, 1]) {
    P.box(0.07, 2.15, 1.9, M.wood, sx * (W / 2 + 0.04), base + 1.1, 0);   // sliding door
    P.box(0.05, 0.06, 4.2, M.iron, sx * (W / 2 + 0.06), base + 2.2, 0);   // door track
    P.box(0.05, 0.06, 4.2, M.iron, sx * (W / 2 + 0.06), base + 0.05, 0);
  }
  // ladder up one corner at each end, brake wheel at the front
  for (const sz of [-1, 1]) {
    const z = sz * (L / 2 + 0.05), x = sz * 0.9;
    for (const dx of [-0.2, 0.2]) P.box(0.04, H, 0.04, M.iron, x + dx, base + H / 2, z + sz * 0.06);
    for (let i = 0; i < 7; i++) P.box(0.44, 0.03, 0.03, M.iron, x, base + 0.2 + i * 0.34, z + sz * 0.06);
    P.box(0.3, 0.25, 0.5, M.iron, 0, 1.0, sz * (L / 2 + 0.25));  // coupler
  }
  P.add(new THREE.TorusGeometry(0.22, 0.025, 4, 12), M.iron, -0.6, base + H + 0.45, L / 2 - 0.1);
  P.box(0.04, 0.4, 0.04, M.iron, -0.6, base + H + 0.2, L / 2 - 0.1);
  const box = P.bake(root);
  // painted sides
  const side = new THREE.MeshStandardMaterial({ map: sideTexture(num, rnd), roughness: 0.92 });
  for (const sx of [-1, 1]) {
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(L, H), side);
    pl.position.set(sx * (W / 2 + 0.005), base + H / 2, 0);
    pl.rotation.y = sx * Math.PI / 2;
    pl.receiveShadow = true;
    root.add(pl);
  }
  const wheels = [];
  truck(M, root, 3.4, wheels);
  truck(M, root, -3.4, wheels);
  return { root, front: L / 2 + 0.5, back: -L / 2 - 0.5, wheels, box, roof: base + H + 0.18, mats: [side] };
}

// ------------------------------------------------------------------ sound
// No samples for this: the whistle and the exhaust beat are synthesised on the
// same WebAudio graph the sampled sounds use, and fall off with distance the
// same way (see audio.play).
let _noise = null;
function noise(ctx) {
  if (_noise && _noise.sampleRate === ctx.sampleRate) return _noise;
  _noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
  const d = _noise.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return _noise;
}

function heard(pos, maxDist) {
  if (!audio.ctx || !audio._inv) return null;
  const rel = _v.copy(pos).applyMatrix4(audio._inv);
  const d = rel.length();
  if (d > maxDist) return null;
  return { vol: 1 / (1 + (d / 12) ** 1.3), pan: clamp(rel.x / Math.max(4, d), -0.85, 0.85) };
}

function out(ctx, h) {
  const g = ctx.createGain(); g.gain.value = 0;
  let o = g;
  if (ctx.createStereoPanner) { const p = ctx.createStereoPanner(); p.pan.value = h.pan; g.connect(p); o = p; }
  o.connect(audio.muffle);
  return g;
}

function chuff(pos, volume) {
  const h = heard(pos, 500); if (!h) return;
  const ctx = audio.ctx, t = ctx.currentTime;
  const src = ctx.createBufferSource();
  src.buffer = noise(ctx); src.playbackRate.value = 0.7 + Math.random() * 0.2;
  const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 280 + Math.random() * 60; f.Q.value = 0.9;
  const g = out(ctx, h);
  const v = volume * h.vol * 3;
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(v, t + 0.015); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
  src.connect(f).connect(g);
  src.start(t, Math.random() * 0.5); src.stop(t + 0.3);
}

// the crossing signal: long, long, short, long, on a three-chime whistle
function whistle(pos, volume = 1) {
  const h = heard(pos, 1200); if (!h) return;
  const ctx = audio.ctx;
  const g = out(ctx, h);
  const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2400;
  lp.connect(g);
  const oscs = [311, 370, 466].map((f) => {
    const o = ctx.createOscillator(); o.type = 'triangle'; o.frequency.value = f * audio.rate;
    o.connect(lp); return o;
  });
  const air = ctx.createBufferSource(); air.buffer = noise(ctx); air.loop = true;
  const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 1300; bp.Q.value = 1.5;
  const ag = ctx.createGain(); ag.gain.value = 0.35;
  air.connect(bp).connect(ag).connect(lp);
  let t = ctx.currentTime + 0.05;
  const v = volume * h.vol * 0.9;
  g.gain.setValueAtTime(0, t);
  for (const len of [1.2, 1.2, 0.4, 1.7]) {
    g.gain.setTargetAtTime(v, t, 0.05);
    // a real whistle sags as the valve opens and the steam catches up
    oscs.forEach((o) => { o.frequency.setValueAtTime(o.frequency.value * 0.97, t); o.frequency.linearRampToValueAtTime(o.frequency.value, t + 0.2); });
    g.gain.setTargetAtTime(0, t + len, 0.06);
    t += len + 0.28;
  }
  oscs.forEach((o) => { o.start(); o.stop(t + 0.5); });
  air.start(); air.stop(t + 0.5);
}

// ------------------------------------------------------------------- train
export class Train {
  constructor(game, rail, def = {}) {
    this.g = game; this.rail = rail; this.def = def;
    const rnd = mulberry32(game.route.def.seed + 29);
    this.M = materials();
    this.group = new THREE.Group();
    this.group.visible = false;
    game.scene.add(this.group);

    this.cars = [buildLoco(this.M), buildTender(this.M)];
    const n = def.cars ?? 4;
    for (let i = 0; i < n; i++) this.cars.push(buildBoxcar(this.M, 1100 + Math.floor(rnd() * 800), rnd));
    // lay out the consist nose to tail: offset = distance from the nose to each car's origin
    let at = 0;
    for (const c of this.cars) {
      c.offset = at + c.front;
      at += c.front - c.back + 0.25;
      this.group.add(c.root);
    }
    this.length = at;
    this.mats = [...Object.values(this.M), ...this.cars.flatMap((c) => c.mats || [])];

    this.speed = def.speed ?? 9;
    // it comes in from whichever side has the longer run of track, so it's in
    // view for as long as possible before it reaches the road
    this.sign = rail.ends.neg >= rail.ends.pos ? 1 : -1;
    this.entry = (this.sign > 0 ? rail.ends.neg : rail.ends.pos) - 4;
    this.exit = (this.sign > 0 ? rail.ends.pos : rail.ends.neg) - 4;
    // where the nose starts: the whole train just on the far end of the track
    this.run0 = Math.max(20, this.entry - this.length);
    this.state = 'wait';
    this.head = 0;
    this.gunmen = [];
    this.fade = 0;
    this.wheelAngle = 0;
    this.chuffT = 0;
    this._hitCd = 0;
    this._warned = false; this._signalled = false;
    this.side = new THREE.Vector3(rail.dir.z, 0, -rail.dir.x);
  }

  get active() { return this.state === 'run'; }

  update(dt) {
    const g = this.g, coach = g.coach, rail = this.rail;
    if (this.state === 'wait') {
      // Anchor to arrival time like the herd: the nose reaches the road a couple
      // of seconds before a coach at cruise would, so the coach meets it
      // mid-train. It starts at the end of the track, so leave when a coach at
      // cruise is that far out.
      const lead = Math.max(6, coach.cruise) * (this.run0 / this.speed + (this.def.early ?? 4));
      if (rail.s - coach.s <= lead) this._start(Math.max(0, rail.s - coach.s));
      return;
    }
    if (this.state === 'gone') return;

    this.head += this.sign * this.speed * dt;
    this.wheelAngle += this.speed * dt;
    // Fade in as the tail comes onto the track, out as the nose runs off the far
    // end: the line fades out into the landscape and so does the train.
    const a = this.sign * this.head;
    this.fade = clamp(Math.min((a - this.length + this.entry) / 20, (this.exit - a) / 20), 0, 1);
    this._place();
    this._setFade(this.fade);
    this._effects(dt);
    this._collide(dt);
    this._hold();
    if (this.fade <= 0 && a > 0) this._finish();
  }

  _start(dist) {
    const g = this.g, rail = this.rail;
    const arrive = dist / Math.max(6, g.coach.cruise);
    const early = this.def.early ?? 4;
    const run = clamp(this.speed * (arrive - early), 20, this.run0);
    this.head = -this.sign * run;
    this.state = 'run';
    this.group.visible = true;
    this.fade = 0;
    this._place();
    this._riders();
    this._place();
    whistle(this.cars[0].root.localToWorld(_v2.copy(this.cars[0].stack)), 0.8);
  }

  // every car sits on the straight graded line, nose first
  _place() {
    const rail = this.rail, s = this.sign;
    const yaw = Math.atan2(rail.dir.x * s, rail.dir.z * s);
    const pitch = -Math.atan(rail.grade * s);
    for (const c of this.cars) {
      const u = this.head - s * c.offset;
      rail._at(u, c.root.position);
      c.root.position.y += RAIL_TOP;
      c.root.rotation.set(pitch, yaw, 0, 'YXZ');
      for (const w of c.wheels) w.o.rotation.x = this.wheelAngle / w.r;
      if (c.rods) this._rods(c);
    }
    this.group.visible = this.fade > 0.01;
    this.group.updateMatrixWorld(true);
    // men on a train you can't see yet would be standing on air
    for (const e of this.gunmen) e.root.visible = this.fade > 0.3;
    // the span of track the train covers, for the crossing test
    const a = this.head, b = this.head - s * this.length;
    this.uMin = Math.min(a, b); this.uMax = Math.max(a, b);
  }

  // crank pins at 0.36 m on the drivers, 90 degrees apart side to side
  _rods(c) {
    const a = this.wheelAngle / 0.8;
    for (const r of c.rods) {
      const ph = a + (r.sx > 0 ? 0 : Math.PI / 2);
      const py = 0.8 + Math.cos(ph) * 0.36, pz = Math.sin(ph) * 0.36;
      r.side.position.set(r.sx * 0.9, py, 0.2 + pz);
      const pin = _v.set(r.sx * 0.9, py, 1.1 + pz);
      const xh = _v2.set(r.sx * 0.98, 1.2, 1.1 + 1.55 + pz * 0.9);
      r.xh.position.copy(xh);
      r.main.position.addVectors(pin, xh).multiplyScalar(0.5);
      const d = xh.sub(pin);
      r.main.scale.z = d.length();
      r.main.quaternion.setFromUnitVectors(_Z, d.normalize());
    }
  }

  _setFade(f) {
    const see = f < 0.999;
    if (see === this._faded && !see) return;
    this._faded = see;
    for (const m of this.mats) { m.transparent = see; m.opacity = f; m.depthWrite = !see || f > 0.6; }
  }

  // gunmen stood on the boxcar roofs, riflemen among them
  _riders() {
    const g = this.g;
    const boxcars = this.cars.filter((c) => c.roof);
    const n = Math.min(this.def.gunmen ?? 4, boxcars.length * 2);
    for (let i = 0; i < n; i++) {
      const car = boxcars[i % boxcars.length];
      const k = Math.floor(i / boxcars.length);
      const seat = new THREE.Vector3((Math.random() - 0.5) * 0.5, car.roof, (k ? -2.6 : 2.2) + (Math.random() - 0.5) * 1.2);
      const pos = car.root.localToWorld(seat.clone());
      const face = _v.copy(g.coach.pos).sub(pos).setY(0).normalize();
      const e = new Gunman(g, pos, face, { rifle: i % 3 === 1, carrier: car.root, seat });
      e.s = this.rail.s;
      g.enemies.list.push(e);
      this.gunmen.push(e);
    }
  }

  _effects(dt) {
    const g = this.g, loco = this.cars[0];
    const stack = loco.root.localToWorld(_v2.copy(loco.stack));
    // two exhausts per driver turn per cylinder: four beats a revolution
    this.chuffT -= dt * (this.speed / (Math.PI * 1.6)) * 4;
    if (this.chuffT <= 0) {
      this.chuffT += 1;
      chuff(stack, 0.55 * this.fade);
      if (this.fade > 0.2) {
        g.fx.smoke.spawn({
          pos: stack, vel: new THREE.Vector3((Math.random() - 0.5) * 0.8, 4 + Math.random() * 2, (Math.random() - 0.5) * 0.8),
          life: 3.5 + Math.random() * 1.5, size: 0.7, size1: 5, color: { r: 0.2, g: 0.19, b: 0.18 }, alpha: 0.55 * this.fade, drag: 0.9, grav: -0.35, fadeIn: 0.05,
        });
      }
    }
    // the crossing signal as the nose comes up on the road
    const toRoad = -this.sign * this.head;
    if (!this._signalled && toRoad < 130) { this._signalled = true; whistle(stack, 1); }
    // shout once, when there's still room to stop
    const away = this.rail.s - g.coach.s;
    if (!this._warned && away < 240 && away > 25 && this.sign * this.head < this.length) {
      this._warned = true;
      g.hud.banner('Train at the crossing!', 'Rein in and let it pass', 2.6);
      audio.play('horse_neigh', { volume: 0.6, pitch: 0.9 });
    }
  }

  // Hauling on the reins with the train across the road brings the team right
  // down to a stand, not the usual walk (see Coach.update).
  _hold() {
    const c = this.g.coach, away = this.rail.s - c.s;
    const by = this.sign * this.head > this.length + 12;
    c.hold = away > -2 && away < 90 && !by;
    if (by) c.halt = false;
  }

  // is a world point on the road standing where the train is?
  _on(p) {
    const C = this.rail.centre, dir = this.rail.dir, sd = this.side;
    const dx = p.x - C.x, dz = p.z - C.z;
    const u = dx * dir.x + dz * dir.z, w = dx * sd.x + dz * sd.z;
    return Math.abs(w) < HALF_W + COACH_HALF && u > this.uMin - 0.4 && u < this.uMax + 0.4;
  }

  _touching(s) {
    const R = this.g.route;
    for (const k of COACH_PTS) if (this._on(R.worldAt(s + k, 0, _v))) return true;
    return false;
  }

  _collide(dt) {
    const g = this.g, coach = g.coach;
    this._hitCd = Math.max(0, this._hitCd - dt);
    if (g.over || this.fade < 0.5) return;
    if (Math.abs(coach.s - this.rail.s) > 20 || !this._touching(coach.s)) return;
    // Thrown back the way it came (or on across, if the train only caught the
    // boot). Never let the coach into the train, even between impacts.
    const back = coach.s + 3 < this.rail.s;
    const v = Math.max(0, coach.speed);
    for (let i = 0; i < 60 && this._touching(coach.s); i++) coach.s += back ? -0.35 : 0.35;
    coach.s += back ? -1 : 1;
    coach.speed = 0;
    // and the driver won't try that twice: he holds the team until it's by
    coach.halt = true;
    if (this._hitCd > 0) return;
    const dmg = clamp(6 + v * 1.6, 10, 32);
    coach.hp -= dmg;
    g.shake += 0.8;
    g.hitStop(0.12);
    this._hitCd = 1.5;
    const at = g.route.worldAt(this.rail.s, 0, new THREE.Vector3()).add(_v2.set(0, 1.2, 0));
    audio.play('hit_wood_1', { volume: 1.2, pitch: 0.6 });
    audio.play('hit_wood_2', { volume: 1, pitch: 0.75, delay: 0.05 });
    audio.play('horse_neigh', { volume: 1, pitch: 0.8 });
    g.fx.dust(at, { amount: 22, size: 1.3, up: 2.5, spread: 4 });
    g.fx.splinters(at, _v2.copy(coach.fwd).negate());
    g.hud.banner('Hit the train!', v > 6 ? 'Rein in at the crossing' : '', 1.8);
    g.player.damage(8, at);
    g.onCoachDamage();
  }

  // nearest car along a ray, for shots at the roof men (wood splinters, not
  // a clean kill through the side of a boxcar)
  raycast(origin, dir, range) {
    if (!this.active || this.fade < 0.5) return range;
    let best = range;
    for (const c of this.cars) {
      _m.copy(c.root.matrixWorld).invert();
      _ray.set(origin, dir).applyMatrix4(_m);
      const p = _ray.intersectBox(c.box, _v);
      if (!p) continue;
      const t = p.applyMatrix4(c.root.matrixWorld).distanceTo(origin);
      if (t < best) best = t;
    }
    return best;
  }

  _finish() {
    this.state = 'gone';
    this.group.visible = false;
    this.g.coach.hold = this.g.coach.halt = false;
    // anyone still aboard rode off with it
    for (const e of this.gunmen) {
      if (e.alive) { e.alive = false; e.escaped = true; e.removeAt = 0; }
      else e.removeAt = Math.min(e.removeAt, this.g.time);
    }
  }

  dispose() {
    this.g.scene.remove(this.group);
    this.group.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
    this.mats.forEach((m) => { m.map?.dispose(); m.dispose(); });
    if (this.g.coach) this.g.coach.hold = this.g.coach.halt = false;
  }
}
