// Places town buildings along the road (start town, end town, ghost town),
// collects gunman spawn points from the kit's Spawn_* empties, and brings the
// two living towns to life: a court house with a clock tower, folk on the
// boardwalks and in the street, horses at the rails, a parked buckboard.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { assets, findNode } from '../core/assets.js';
import { audio } from '../core/audio.js';
import * as Chars from '../game/characters.js';
import { mulberry32, damp } from '../core/noise.js';

const { createRider, createHorse } = Chars;
// What characters.js can dress. It may export VARIANTS; until it lists
// 'woman' and 'lawman' they come out as townsmen / the guard's outfit.
const KNOWN = new Set({ ...Chars }.VARIANTS || ['bandit', 'bandit2', 'bandit3', 'townsman', 'driver', 'player', 'gunman']);
const dress = (v, alt = 'townsman') => (KNOWN.has(v) ? v : alt);
const MEN = ['townsman', 'player', 'townsman', 'bandit2'];
const FOLK_TINT = [
  new THREE.Color(1, 1, 1), new THREE.Color(0.72, 0.74, 0.8), new THREE.Color(0.95, 0.88, 0.72),
  new THREE.Color(0.6, 0.62, 0.58), new THREE.Color(1.05, 0.95, 0.85), new THREE.Color(0.8, 0.7, 0.66),
];
const COATS = [[0.62, 0.42, 0.3], [0.85, 0.55, 0.34], [0.32, 0.25, 0.22], [1.1, 1.05, 1.0], [1.15, 0.92, 0.6], [0.5, 0.36, 0.28]]
  .map((c) => new THREE.Color(...c));

const KIT = ['Saloon', 'GeneralStore', 'Sheriff', 'Bank', 'Hotel', 'Livery', 'Shack'];
// footprint width (along the street) and depth, metres — from town.glb
const WIDTH = { Saloon: 10.5, GeneralStore: 9.7, Sheriff: 8.1, Bank: 8.5, Hotel: 12.5, Livery: 12.8, Shack: 5.2, Church: 8.8, WaterTower: 5.3, Gallows: 6.7, CourtHouse: 14.0 };
const DEPTH = { Saloon: 16.6, GeneralStore: 15.7, Sheriff: 13.4, Bank: 13.2, Hotel: 15.6, Livery: 17.4, Shack: 5.3, Church: 16.6, WaterTower: 5.8, Gallows: 3.1, CourtHouse: 17.5 };
// porch depth and deck height: the boardwalk folk walk and stand on
const PORCH = { Saloon: [2.6, 0.4], GeneralStore: [2.6, 0.4], Sheriff: [2.4, 0.4], Bank: [1.2, 0.3], Hotel: [2.6, 0.4] };
// clock dials, in Clock_*_<i> order: outward normals in the building's frame
const DIAL_N = [[0, 0, 1], [1, 0, 0], [0, 0, -1], [-1, 0, 0]].map((v) => new THREE.Vector3(...v));
const WALK = 1.4;   // m/s the Walk clip is authored at (in place)

// People and horses on mobile: fewer of them. Same rule as the renderer's tier.
function busyness() {
  const touch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
  let q = null;
  try { q = localStorage.getItem('schofield.quality'); } catch {}
  const k = { low: 0.35, medium: 0.6, high: 1 }[q || (touch ? 'medium' : 'high')] ?? 0.6;
  return touch ? Math.min(k, 0.45) : k;
}

// Townsfolk hear gunfire: every shot the audio system plays is noted, and
// those near the coach run for the nearest door.
let heard = 0;
if (!audio._townEar) {
  const play = audio.play.bind(audio);
  audio.play = (name, o) => { if (/shot/.test(name)) heard++; return play(name, o); };
  audio._townEar = true;
}

const wrapA = (a) => { while (a > Math.PI) a -= Math.PI * 2; while (a < -Math.PI) a += Math.PI * 2; return a; };
const dampA = (a, b, k, dt) => a + wrapA(b - a) * (1 - Math.exp(-k * dt));

function fallbackBuilding(name, rnd) {
  const g = new THREE.Group();
  const w = (WIDTH[name] || 9) - 1, d = 10, h = name === 'Saloon' || name === 'Hotel' ? 7.5 : 4.5 + rnd() * 1.5;
  const wood = new THREE.MeshStandardMaterial({ color: new THREE.Color().setHSL(0.07, 0.25, 0.3 + rnd() * 0.15), roughness: 0.95 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x120c08, roughness: 1 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wood); body.position.set(0, h / 2, -d / 2); g.add(body);
  const front = new THREE.Mesh(new THREE.BoxGeometry(w, 2, 0.2), wood); front.position.set(0, h + 1, 0); g.add(front);
  const porch = new THREE.Mesh(new THREE.BoxGeometry(w, 0.15, 2.5), wood); porch.position.set(0, 3.2, 1.25); g.add(porch);
  for (const x of [-w / 2 + 0.2, w / 2 - 0.2]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.2, 0.2), wood); p.position.set(x, 1.6, 2.4); g.add(p); }
  const door = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 2.4), dark); door.position.set(0, 1.2, 0.01); g.add(door);
  for (const x of [-w / 4 - 0.5, w / 4 + 0.5]) { const win = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.4), dark); win.position.set(x, 1.7, 0.01); g.add(win); }
  if (h > 6) {
    for (const x of [-w / 4, w / 4]) {
      const win = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.3), dark); win.position.set(x, 5.2, 0.01); g.add(win);
      const e = new THREE.Object3D(); e.name = 'Spawn_Window_' + (x < 0 ? 1 : 2); e.position.set(x, 4.5, 0.3); g.add(e);
    }
  }
  const e = new THREE.Object3D(); e.name = 'Spawn_Roof_1'; e.position.set(0, h + 0.1, -0.6); g.add(e);
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

function kitBuilding(name) {
  const t = assets.models.town;
  if (!t) return null;
  const src = findNode(t.scene, name);
  if (!src) return null;
  const c = src.clone(true);
  c.position.set(0, 0, 0); c.rotation.set(0, 0, 0);
  c.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true; o.receiveShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => { if (m.transparent || m.alphaTest > 0) { m.alphaTest = 0.5; m.transparent = false; } });
    }
  });
  return c;
}

// gltfpack ships quantised, interleaved attributes; a plain float copy merges
function plainGeometry(g) {
  const out = new THREE.BufferGeometry();
  for (const k of ['position', 'normal', 'uv', 'color']) {
    const a = g.getAttribute(k);
    if (!a) continue;
    const n = a.itemSize, arr = new Float32Array(a.count * n);
    for (let i = 0; i < a.count; i++) {
      arr[i * n] = a.getX(i);
      if (n > 1) arr[i * n + 1] = a.getY(i);
      if (n > 2) arr[i * n + 2] = a.getZ(i);
      if (n > 3) arr[i * n + 3] = a.getW(i);
    }
    out.setAttribute(k, new THREE.BufferAttribute(arr, n));
  }
  if (g.index) out.setIndex(Array.from(g.index.array));
  return out;
}

// Set the court house clocks to `hours` (decimal, 0-24) and bake the eight
// hands into one mesh — the time never changes during a ride.
function setClock(b, hours) {
  const hands = [];
  DIAL_N.forEach((n, i) => {
    for (const [k, turns] of [['Hour', (hours % 12) / 12], ['Minute', hours % 1]]) {
      const h = findNode(b, `Clock_${k}_${i}`);
      if (!h) continue;
      h.quaternion.setFromAxisAngle(n, -turns * Math.PI * 2);
      hands.push(h);
    }
  });
  if (!hands.length) return;
  b.updateMatrixWorld(true);
  const inv = b.matrixWorld.clone().invert(), geos = [];
  let mat = null;
  for (const h of hands) h.traverse((m) => { if (m.isMesh) { geos.push(plainGeometry(m.geometry).applyMatrix4(inv.clone().multiply(m.matrixWorld))); mat = m.material; } });
  const merged = geos.length && mergeGeometries(geos);
  if (!merged) return;    // leave the separate hands
  hands.forEach((h) => h.removeFromParent());
  const mesh = new THREE.Mesh(merged, mat);
  mesh.name = 'Clock_Hands'; mesh.castShadow = true;
  b.add(mesh);
}

// 'h:mm' -> hours on the dial
function clockHours(str) {
  const [h, m] = String(str || '4:20').split(':').map(Number);
  return (h % 12) + (m || 0) / 60;
}

export class Towns {
  constructor(route, scene) {
    this.route = route; this.scene = scene;
    this.group = new THREE.Group(); scene.add(this.group);
    this.spawns = []; // { pos: Vector3, face: Vector3 (toward road), s, kind }
    this.folk = [];   // townsfolk in the living towns
    this.horses = []; // tied at the rails
    this.solids = []; // AABBs for bullet blocking
    this.landmarks = []; // { name, s, pos } — the court houses, for cameras
    this._heard = heard;
    const rnd = mulberry32(route.def.seed + 5);
    const busy = busyness();
    // start town: the court house stands on the street; end town: across the
    // head of it, so the stage pulls up in front of the clock
    const L = route.len, hours = clockHours(route.def.clock);
    const start = { s0: 20, s1: 110, lots: [] }, end = { s0: L - 130, s1: L - 10, lots: [] };
    // on a gorge ledge the river side is a drop: build on the other side only
    const wet = route.def.gorge ? route.riverSide || 1 : 0;
    const pickSide = rnd() < 0.5 ? -1 : 1, courtSide = wet ? -wet : pickSide;
    this._lots = start.lots;
    this._street(start.s0, start.s1, rnd, 0.8, false, [{ s0: 57, s1: 75, side: courtSide }], wet);
    start.lots.push(this._court(66, courtSide, false, hours, rnd));
    this._lots = end.lots;
    this._street(end.s0, end.s1, rnd, 0.8, false, [], wet);
    end.lots.push(this._court(L + 24, 0, true, hours + L / 12 / 3600, rnd));
    this._lots = null;
    this._populate(start, rnd, busy);
    this._populate(end, rnd, busy);
    const T = route.townRange;
    if (T) this._street(T.s0, T.s1, rnd, 1, true);   // ghost town stays empty
  }

  _place(name, s, side, rnd, ghost, extraOffset = 0) {
    const r = this.route, f = r.frame(s, {});
    const off = 9.5 + extraOffset + rnd() * 1.2 + (name === 'Livery' ? 1.5 : 0);
    const x = f.x + f.rx * off * side, z = f.z + f.rz * off * side;
    const b = kitBuilding(name) || fallbackBuilding(name, rnd);
    // front (+Z local) faces the road
    const yaw = Math.atan2(-f.rx * side, -f.rz * side);
    // sit on the lowest corner so it doesn't float on slopes
    const w = (WIDTH[name] || 9) / 2;
    let y = Infinity;
    const dp = DEPTH[name] || 10;
    for (const [a, c] of [[-w, 0], [w, 0], [-w, -dp], [w, -dp], [0, -dp / 2]]) {
      const lx = Math.cos(yaw) * a + Math.sin(yaw) * c, lz = -Math.sin(yaw) * a + Math.cos(yaw) * c;
      y = Math.min(y, r.height(x + lx, z + lz));
    }
    b.position.set(x, y - 0.05, z);
    b.rotation.y = yaw;
    if (ghost) b.traverse((o) => { if (o.isMesh) { o.material = o.material.clone(); o.material.color?.multiplyScalar(0.85); } });
    this.group.add(b);
    b.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(b);
    this.solids.push(box);
    if (ghost) {
      b.traverse((o) => {
        if (/^Spawn_/.test(o.name)) {
          const p = o.getWorldPosition(new THREE.Vector3());
          const face = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
          this.spawns.push({ pos: p, face, s, roof: /Roof/.test(o.name), used: false });
        }
      });
    }
    const [P, deck] = PORCH[name] || [0, 0];
    const lot = { name, s, side, off, w: w * 2, y: y - 0.05, yaw, P, deck };
    if (this._lots && !extraOffset) this._lots.push(lot);
    return lot;
  }

  // The court house: on the street like the rest, or (terminus) square across
  // the road facing the coming stage. Clocks show the route's time of day.
  _court(s, side, terminus, hours, rnd) {
    const r = this.route, f = r.frame(s, {});
    const b = kitBuilding('CourtHouse') || fallbackBuilding('CourtHouse', rnd);
    setClock(b, hours);
    const off = terminus ? 0 : 9.5;
    const x = f.x + f.rx * off * side, z = f.z + f.rz * off * side;
    const yaw = terminus ? Math.atan2(-f.tx, -f.tz) : Math.atan2(-f.rx * side, -f.rz * side);
    const w = WIDTH.CourtHouse / 2, dp = DEPTH.CourtHouse;
    let y = Infinity;
    for (const [a, c] of [[-w, 0], [w, 0], [-w, -dp], [w, -dp], [0, -dp / 2]]) {
      const lx = Math.cos(yaw) * a + Math.sin(yaw) * c, lz = -Math.sin(yaw) * a + Math.cos(yaw) * c;
      y = Math.min(y, r.height(x + lx, z + lz));
    }
    b.position.set(x, y - 0.05, z);
    b.rotation.y = yaw;
    this.group.add(b);
    b.updateMatrixWorld(true);
    this.solids.push(new THREE.Box3().setFromObject(b));
    const tower = new THREE.Vector3(0, 13, -10).applyMatrix4(b.matrixWorld);
    this.landmarks.push({ name: 'CourtHouse', s, pos: tower });
    return { name: 'CourtHouse', s, side, off, w: WIDTH.CourtHouse, y: y - 0.05, yaw, P: 0, deck: 0, terminus, b };
  }

  _street(s0, s1, rnd, fill, ghost, reserve = [], skipSide = 0) {
    const placed = { '-1': [], '1': [] };
    for (const side of [-1, 1]) {
      if (side === skipSide) continue;
      let s = s0 + rnd() * 6, last = '';
      while (s < s1) {
        if (rnd() > fill) { s += 8 + rnd() * 10; continue; }
        let name;
        // never the same facade twice in a row, or directly opposite its twin
        for (let k = 0; k < 8; k++) {
          name = KIT[Math.floor(rnd() * KIT.length)];
          const opp = placed[-side].find((b) => Math.abs(b.s - s) < 12);
          if (name !== last && (!opp || opp.name !== name)) break;
        }
        const w = WIDTH[name] || 9;
        const block = reserve.find((q) => q.side === side && s < q.s1 && s + w > q.s0);
        if (block) { s = block.s1 + 1.5 + rnd() * 2; continue; }
        this._place(name, s + w / 2, side, rnd, ghost);
        placed[side].push({ s, name }); last = name;
        // street clutter in front of the boardwalk (the living towns get
        // theirs with the horses and wagons, so they don't collide)
        if (ghost) this._clutter(s + w * (0.2 + rnd() * 0.6), side, rnd);
        s += w + 1.5 + rnd() * 4;
      }
      // a ragged back row so the town doesn't end at one wall
      if (ghost) for (let t = s0 + 10; t < s1 - 10; t += 16 + rnd() * 14) this._place('Shack', t, side, rnd, false, 24 + rnd() * 10);
    }
    // landmarks
    const mid = (s0 + s1) / 2;
    const ls = rnd() < 0.5 ? -1 : 1;
    this._place(ghost ? 'Church' : 'WaterTower', mid + 30, ls === skipSide ? -ls : ls, rnd, ghost, 14);
    if (ghost) this._place('Gallows', s0 + 40, -1, rnd, ghost, 2);
  }

  // ------------------------------------------------------------ townsfolk
  _xz(s, d, out = {}) {
    const f = this.route.frame(s, {});
    out.x = f.x + f.rx * d; out.z = f.z + f.rz * d; out.tx = f.tx; out.tz = f.tz; out.rx = f.rx; out.rz = f.rz;
    return out;
  }

  _kit(name, s, d, yaw, solid = false) {
    const t = assets.models.town, src = t && findNode(t.scene, name);
    if (!src) return null;
    const o = src.clone(true), p = this._xz(s, d);
    o.position.set(p.x, this.route.height(p.x, p.z), p.z);
    o.rotation.y = yaw;
    o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
    this.group.add(o);
    if (solid) { o.updateMatrixWorld(true); this.solids.push(new THREE.Box3().setFromObject(o)); }
    return o;
  }

  // how far out a walker on one side is at station s: along the boardwalks,
  // in front of the buildings without one, eased across the gaps
  _lane(T, side, s) {
    const lots = T.bySide[side];
    const at = (l) => (l.P > 0 ? l.off + Math.min(1.3, l.P * 0.55) : l.off - 1.0);
    let prev = null;
    for (const l of lots) {
      if (s >= l.s - l.w / 2 && s <= l.s + l.w / 2) return at(l);
      if (l.s - l.w / 2 > s) {
        if (!prev) return at(l);
        const a = prev.s + prev.w / 2, b = l.s - l.w / 2, k = (s - a) / Math.max(0.1, b - a);
        return at(prev) + (at(l) - at(prev)) * k;
      }
      prev = l;
    }
    return prev ? at(prev) : 8.5;
  }

  _person(T, variant, tint) {
    if (T.left <= 0) return null;
    T.left--;
    const p = createRider({ variant, tint });
    this.scene.add(p.root);
    return p;
  }

  _add(n) {
    n.y ??= null; n.wait ??= 0; n.acc = 0; n.yaw ??= n.baseYaw ?? 0;
    n.p.root.rotation.y = n.yaw;
    this._idle(n);
    if (n.p.actions?.[n.clip || 'StandIdle']) n.p.mixer.setTime(n.phase * 3);
    this._put(n, 0);
    this.folk.push(n);
    return n;
  }

  _idle(n) {
    const p = n.p, c = n.clip && p.has(n.clip) ? n.clip : 'StandIdle';
    if (p.has(c)) p.play(c, { fade: 0.3 });
  }

  _move(n) {
    const p = n.p, run = n.speed > 2.4;
    if (run && p.has('Run')) { p.play('Run', { fade: 0.2 }); p.setSpeed(n.speed / 3.6); }
    else if (p.has('Walk')) { p.play('Walk', { fade: 0.25 }); p.setSpeed(n.speed / WALK); }
    else if (p.has('StandIdle')) p.play('StandIdle');     // glides till the Walk clip lands
  }

  // ground or deck under (s, d), eased so stepping up onto a porch isn't a pop
  _put(n, dt) {
    const p = this._xz(n.s, n.d);
    let y = this.route.height(p.x, p.z);
    const T = n.town, side = Math.sign(n.d);
    if (T && side) {
      for (const l of T.bySide[side]) {
        if (l.P > 0 && Math.abs(n.s - l.s) < l.w / 2 - 0.05 && Math.abs(n.d) > l.off + 0.05 && Math.abs(n.d) < l.off + l.P) { y = l.y + l.deck; break; }
      }
    }
    y += n.lift || 0;
    n.y = n.y == null || !dt ? y : damp(n.y, y, 12, dt);
    const bob = n.moving && !n.p.has('Walk') ? Math.abs(Math.sin(n.t * 7)) * 0.03 : 0;
    n.p.root.position.set(p.x, n.y + bob, p.z);
  }

  _populate(T, rnd, busy) {
    const lots = T.lots.filter((l) => !l.terminus);
    T.bySide = { '-1': lots.filter((l) => l.side < 0).sort((a, b) => a.s - b.s), '1': lots.filter((l) => l.side > 0).sort((a, b) => a.s - b.s) };
    T.left = Math.round(32 * busy);   // people per town
    T.blocked = [];                   // stations with a horse or wagon at the kerb
    T.horses = Math.max(2, Math.round(7 * busy));
    const pick = (a) => a[Math.floor(rnd() * a.length)];
    const tint = () => pick(FOLK_TINT);
    const anyone = () => (rnd() < 0.42 ? dress('woman') : pick(MEN));
    const used = new Set(), leans = [], benches = [];
    const sides = [-1, 1].filter((sd) => T.bySide[sd].length);
    if (!sides.length) return;
    let wagons = busy > 0.7 ? 2 : 1;
    // horses at the rails, benches on the porches, a parked buckboard
    for (const l of lots) {
      if (l.name === 'CourtHouse') continue;
      const front = l.yaw, sx = -l.side;   // local +X runs against s on the right-hand side
      if (l.name === 'Livery') {
        // its own rail, built into the barn front
        if (T.horses > 0 && rnd() < 0.8 * busy + 0.2) this._horse(T, l.s - sx * 4.2, l, l.off - 1.6, rnd);
        used.add(l);
        continue;
      }
      if (l.P > 0 && T.horses > 0 && rnd() < 0.55 * busy + 0.15) {
        const s = l.s + (rnd() - 0.5) * Math.max(0, l.w - 4.5), rd = l.off - 2.2;
        this._kit('HitchRail', s, rd * l.side, front);
        const nh = Math.min(T.horses, 1 + (rnd() < 0.5 * busy ? 1 : 0));
        for (let i = 0; i < nh; i++) this._horse(T, s + (nh > 1 ? (i - 0.5) * 1.5 : (rnd() - 0.5) * 0.8), l, rd, rnd);
        if (rnd() < 0.5) leans.push({ s: s + (rnd() < 0.5 ? -1 : 1) * 1.6, d: (rd + 0.45) * l.side, yaw: front });
        used.add(l);
      } else if (wagons > 0 && rnd() < 0.35) {
        wagons--;
        const f = this.route.frame(l.s, {}), dir = rnd() < 0.5 ? 1 : -1;
        this._kit('Buckboard', l.s, (l.off - 3.1) * l.side, Math.atan2(f.tx * dir, f.tz * dir) + (rnd() - 0.5) * 0.1, true);
        T.blocked.push(l.s - 2.5, l.s, l.s + 2.5);
        used.add(l);
      } else if (rnd() < 0.5) {
        this._clutter(l.s + (rnd() - 0.5) * l.w * 0.6, l.side, rnd);
      }
      if (l.P >= 2.4 && rnd() < 0.3 + 0.3 * busy) {
        const s = l.s + (rnd() < 0.5 ? -1 : 1) * (l.w / 2 - 1.5), bd = l.off + l.P - 0.55;
        const bench = this._kit('Bench', s, bd * l.side, front);
        if (bench) bench.position.y = l.y + l.deck;
        benches.push({ s, bd, l, sx });
      }
    }
    // who's about, most important first (the budget runs out on the idlers)
    const nWalk = Math.round(7 * busy);
    for (let i = 0; i < nWalk; i++) {
      const side = pick(sides), len = 18 + rnd() * 30;
      const a = T.s0 + 2 + rnd() * Math.max(1, T.s1 - T.s0 - len - 4);
      this._walker(T, anyone(), 'walk', side, a, a + len, rnd);
    }
    // lawmen: patrolling by the jail (or the court house)
    const jail = lots.find((l) => l.name === 'Sheriff') || T.lots.find((l) => l.name === 'CourtHouse' && !l.terminus);
    for (let i = 0; i < (busy > 0.7 ? 2 : 1); i++) {
      const side = jail ? jail.side : 1, c = jail ? jail.s : (T.s0 + T.s1) / 2;
      this._walker(T, dress('lawman', 'player'), 'patrol', side, c - 10 - rnd() * 4, c + 10 + rnd() * 4, rnd);
    }
    const court = T.lots.find((l) => l.name === 'CourtHouse');
    if (court) {
      // by the court house gate: a lawman and whoever has business there
      const nC = Math.max(1, Math.round((court.terminus ? 3 : 2) * busy));
      for (let i = 0; i < nC; i++) {
        const p = this._person(T, i === 0 ? dress('lawman', 'player') : anyone(), tint());
        if (!p) break;
        const lx = (i - 1) * 1.6 + (rnd() - 0.5) * 0.5, lz = 1.0 + rnd() * 0.8;   // local: outside the fence
        const pos = new THREE.Vector3(lx, 0, lz).applyMatrix4(court.b.matrixWorld);
        const rc = this._roadCoords(pos.x, pos.z, court.s);
        this._add({ p, town: T, kind: 'stand', s: rc.s, d: rc.d, baseYaw: court.yaw + (rnd() - 0.5) * 1.2, phase: rnd() });
      }
    }
    // folk crossing the street when the road is clear
    for (let i = 0; i < (sides.length > 1 ? Math.round(2 * busy) : 0); i++) {
      let s = 0;
      for (let k = 0; k < 6; k++) { s = T.s0 + 10 + rnd() * (T.s1 - T.s0 - 20); if (!T.blocked.some((b) => Math.abs(b - s) < 2.5)) break; }
      const side = rnd() < 0.5 ? -1 : 1;
      const da = this._lane(T, side, s) - 2.3, db = this._lane(T, -side, s) - 2.3;
      const p = this._person(T, anyone(), tint());
      if (!p) break;
      this._add({ p, town: T, kind: 'cross', s, d: da * side, from: da * side, to: -db * side, speed: 1.2 + rnd() * 0.3, wait: 2 + rnd() * 8, baseYaw: 0, phase: rnd() });
    }
    for (const q of leans) {
      const p = this._person(T, rnd() < 0.7 ? pick(MEN) : dress('woman'), tint());
      if (!p) break;
      this._add({ p, town: T, kind: 'lean', clip: 'LeanRail', s: q.s, d: q.d, baseYaw: q.yaw, phase: rnd() });
    }
    for (const { s, bd, l, sx } of benches) {
      const ns = rnd() < 0.5 * busy ? 2 : 1;
      for (let i = 0; i < ns; i++) {
        const p = this._person(T, anyone(), tint());
        if (!p) break;
        const sit = p.has('Sit');     // until there's a Sit clip they stand by the bench
        this._add({ p, town: T, kind: sit ? 'sit' : 'stand', clip: sit ? 'Sit' : null, s: s + (ns > 1 ? (i - 0.5) * 0.9 : (rnd() - 0.5) * 0.5) * sx,
          d: (sit ? bd + 0.22 : bd - 0.35) * l.side, baseYaw: l.yaw + (sit ? 0 : (rnd() - 0.5) * 0.8), lift: sit ? 0.46 : 0, phase: rnd() });
      }
    }
    // conversation groups: mostly on the boardwalks, the bank and hotel busiest
    const weighted = lots.filter((l) => l.P > 0).flatMap((l) => (/Bank|Hotel|Saloon/.test(l.name) ? [l, l] : [l]));
    while (T.left > 1 && weighted.length) {
      const l = pick(weighted), onDeck = rnd() < 0.7 || used.has(l);
      const cs = l.s + (rnd() - 0.5) * (l.w - 2.5), cd = onDeck ? l.off + l.P * 0.5 : l.off - 1.4;
      const k = Math.min(T.left, 2 + (rnd() < 0.35 ? 1 : 0)), a0 = rnd() * Math.PI * 2;
      for (let i = 0; i < k; i++) {
        const a = a0 + (i / k) * Math.PI * 2, rr = onDeck ? Math.min(0.5, l.P * 0.3) : 0.6;
        const s = cs + Math.cos(a) * rr, d = (cd + Math.sin(a) * rr) * l.side;
        const q = this._xz(s, d), c = this._xz(cs, cd * l.side);
        this._add({ p: this._person(T, anyone(), tint()), town: T, kind: 'stand', clip: 'Talk', s, d, baseYaw: Math.atan2(c.x - q.x, c.z - q.z), phase: rnd() });
      }
    }
  }

  // nearest station to (x, z) — towns sit on straights, so a few Newton steps do
  _roadCoords(x, z, s) {
    for (let i = 0; i < 4; i++) {
      const f = this.route.frame(s, {});
      s += (x - f.x) * f.tx + (z - f.z) * f.tz;
    }
    const f = this.route.frame(s, {});
    return { s, d: (x - f.x) * f.rx + (z - f.z) * f.rz };
  }

  _walker(T, variant, kind, side, a, b, rnd) {
    const p = this._person(T, variant, FOLK_TINT[Math.floor(rnd() * FOLK_TINT.length)]);
    if (!p) return null;
    a = Math.max(T.s0, a); b = Math.min(T.s1, b);
    const s = a + rnd() * (b - a);
    const dj = (rnd() - 0.5) * 0.7;   // not all on one line
    return this._add({ p, town: T, kind, side, a, b, s, dj, d: (this._lane(T, side, s) + dj) * side, dir: rnd() < 0.5 ? 1 : -1,
      speed: (kind === 'patrol' ? 1.0 : 1.2) + rnd() * 0.3, wait: rnd() * 3, phase: rnd(), t: rnd() * 10 });
  }

  _horse(T, s, l, rd, rnd) {
    const h = createHorse({ coat: COATS[Math.floor(rnd() * COATS.length)], saddle: true });
    const d = (rd - 1.15) * l.side, q = this._xz(s, d);
    h.root.position.set(q.x, this.route.height(q.x, q.z), q.z);
    h.root.rotation.y = l.yaw + Math.PI + (rnd() - 0.5) * 0.3;    // nose to the rail
    if (h.has('Idle')) { h.play('Idle'); h.mixer?.setTime(rnd() * 4); }
    h.s = s;
    T.blocked.push(s); T.horses--;
    this.scene.add(h.root);
    this.horses.push(h);
  }

  // shots near the coach: everyone close by makes for a door
  _alarm(cs) {
    for (const n of this.folk) {
      if (n.kind === 'flee' || n.kind === 'gone' || Math.abs(n.s - cs) > 90) continue;
      const side = Math.sign(n.d) || 1, lots = n.town.bySide[side];
      let best = null;
      for (const l of lots) if (!best || Math.abs(l.s - n.s) < Math.abs(best.s - n.s)) best = l;
      if (!best) continue;
      n.kind = 'flee'; n.lift = 0; n.wait = 0.2 + Math.random() * 0.9;
      n.ts = best.s + (Math.random() - 0.5) * 1.2;
      n.td = (best.off + (best.name === 'Livery' ? 0.6 : best.P + 0.25)) * side;
      n.speed = 3.3 + Math.random() * 0.8;
    }
    for (const h of this.horses) {
      if (Math.abs(h.s - cs) < 90 && h.has('Rear') && Math.random() < 0.4) {
        h.play('Rear', { once: true, fade: 0.15 });
        h.rearT = h.actions.Rear.getClip().duration;
      }
    }
  }

  // Rider meshes are built with frustumCulled off (skinned bounds are
  // unreliable), so a townsful of them would draw every frame from anywhere on
  // the route. Show and animate only the ones near the coach, and none that
  // it has left behind.
  update(dt, coach) {
    const cs = coach ? coach.s : 0;
    if (heard !== this._heard) { this._heard = heard; if (coach) this._alarm(cs); }
    this._frame = (this._frame || 0) + 1;
    const near = (s) => s > cs - 45 && s < cs + 160;
    for (const h of this.horses) {
      const v = near(h.s);
      if (h.root.visible !== v) h.root.visible = v;
      if (!v) continue;
      this._shadow(h, h.root, Math.abs(h.s - cs) < 40);
      if (h.rearT > 0 && (h.rearT -= dt) <= 0) h.play('Idle', { fade: 0.4 });
      h.update(dt);
    }
    for (const n of this.folk) {
      const v = n.kind !== 'gone' && near(n.s);
      if (n.p.root.visible !== v) n.p.root.visible = v;
      if (!v) continue;
      const away = Math.abs(n.s - cs);
      this._shadow(n, n.p.root, away < 40);
      // the far ones animate at a third of the rate
      n.acc += dt;
      if (away > 70 && (this._frame + n.phase * 3 | 0) % 3) continue;
      const step = n.acc; n.acc = 0;
      n.t = (n.t || 0) + step;
      this._think(n, step, coach, cs, away);
      n.p.update(step);
    }
  }

  // only the ones near the coach cast shadows: the shadow pass is the other
  // half of what a townful of people costs
  _shadow(o, root, on) {
    if (o.cast === on) return;
    o.cast = on;
    root.traverse((m) => { if (m.isMesh) m.castShadow = on; });
  }

  _think(n, dt, coach, cs, away) {
    n.moving = false;
    switch (n.kind) {
      case 'walk': case 'patrol': {
        if (n.wait > 0) { n.wait -= dt; this._idle(n); break; }
        n.s += n.dir * n.speed * dt;
        if ((n.dir > 0 && n.s > n.b) || (n.dir < 0 && n.s < n.a)) {
          n.dir = -n.dir; n.wait = 1 + Math.random() * (n.kind === 'patrol' ? 5 : 3);
        } else if (Math.random() < dt * 0.04) n.wait = 2 + Math.random() * 4;   // stops to look in a window
        n.d = (this._lane(n.town, n.side, n.s) + n.dj) * n.side;
        const f = this._xz(n.s, n.d);
        n.yaw = dampA(n.yaw, Math.atan2(f.tx * n.dir, f.tz * n.dir), 8, dt);
        n.moving = true; this._move(n);
        break;
      }
      case 'cross': {
        const onRoad = Math.abs(n.d) < 5.6;
        const coming = cs < n.s + 6 && n.s - cs < 110;   // the stage is (or soon will be) here
        if (onRoad && coming && n.s - cs < 40) {
          // clear the road for the stage: run for the nearer kerb
          if (Math.sign(n.from) === Math.sign(n.d)) [n.from, n.to] = [n.to, n.from];
          n.speed = 3.4; n.wait = 0;
        }
        if (n.wait > 0) { n.wait -= dt; if (n.wait <= 0 && coming) n.wait = 1.5; this._idle(n); break; }
        const dd = n.to - n.d;
        if (Math.abs(dd) < 0.05) { [n.from, n.to] = [n.to, n.from]; n.wait = 4 + Math.random() * 10; n.speed = 1.2 + Math.random() * 0.3; break; }
        n.d += Math.sign(dd) * Math.min(Math.abs(dd), n.speed * dt);
        const f = this._xz(n.s, n.d), sg = Math.sign(dd);
        n.yaw = dampA(n.yaw, Math.atan2(f.rx * sg, f.rz * sg), 8, dt);
        n.moving = true; this._move(n);
        break;
      }
      case 'flee': {
        if (n.wait > 0) { n.wait -= dt; break; }
        const ds = n.ts - n.s, dd = n.td - n.d, L = Math.hypot(ds, dd);
        if (L < 0.3) { n.kind = 'gone'; n.p.root.visible = false; return; }
        const k = Math.min(1, (n.speed * dt) / L);
        n.s += ds * k; n.d += dd * k;
        const f = this._xz(n.s, n.d);
        n.yaw = dampA(n.yaw, Math.atan2(f.tx * ds + f.rx * dd, f.tz * ds + f.rz * dd), 10, dt);
        n.moving = true; this._move(n);
        break;
      }
      default: {
        // standing, sitting, leaning: turn to watch the stage go past
        if (n.kind !== 'sit' && away < 26 && coach) {
          const q = n.p.root.position;
          const want = Math.atan2(coach.pos.x - q.x, coach.pos.z - q.z);
          n.yaw = dampA(n.yaw, n.baseYaw + wrapA(want - n.baseYaw) * (n.kind === 'lean' ? 0.6 : 1), 3, dt);
        } else n.yaw = dampA(n.yaw, n.baseYaw, 2, dt);
      }
    }
    n.p.root.rotation.y = n.yaw;
    this._put(n, dt);
  }

  _clutter(s, side, rnd) {
    const props = assets.models.props;
    if (!props) return;
    const pick = ['Barrel', 'Crate', 'WaterTrough', 'Barrel', 'Crate', 'Wagon_Wreck'][Math.floor(rnd() * (rnd() < 0.85 ? 5 : 6))];
    const src = findNode(props.scene, pick);
    if (!src) return;
    const r = this.route, f = r.frame(s, {});
    const off = (pick === 'Wagon_Wreck' ? 7 : 6.8) + rnd() * 0.8;
    const n = pick === 'Barrel' || pick === 'Crate' ? 1 + Math.floor(rnd() * 3) : 1;
    for (let i = 0; i < n; i++) {
      const o = src.clone(true);
      const x = f.x + f.rx * off * side + f.tx * i * 0.9, z = f.z + f.rz * off * side + f.tz * i * 0.9;
      o.position.set(x, r.height(x, z), z);
      o.rotation.set(0, rnd() * Math.PI * 2, 0);
      if (pick === 'Wagon_Wreck') o.rotation.y = Math.atan2(f.tx, f.tz) + (rnd() - 0.5) * 0.6;
      o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
      this.group.add(o);
      o.updateMatrixWorld(true);
      this.solids.push(new THREE.Box3().setFromObject(o));
    }
  }

  dispose() {
    this.scene.remove(this.group);
    this.folk.forEach((n) => this.scene.remove(n.p.root));
    this.horses.forEach((h) => this.scene.remove(h.root));
    this.folk = []; this.horses = [];
  }
}
