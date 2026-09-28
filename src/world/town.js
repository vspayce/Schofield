// Places town buildings along the road (start town, end town, ghost town),
// collects gunman spawn points from the kit's Spawn_* empties, and puts
// townsfolk on the boardwalks of the two living towns.
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { createRider } from '../game/characters.js';
import { mulberry32, damp } from '../core/noise.js';

// hats and coats for people who aren't outlaws
const FOLK = ['driver', 'player', 'bandit2', 'driver', 'player'];
const FOLK_TINT = [
  new THREE.Color(1, 1, 1), new THREE.Color(0.72, 0.74, 0.8), new THREE.Color(0.95, 0.88, 0.72),
  new THREE.Color(0.6, 0.62, 0.58), new THREE.Color(1.05, 0.95, 0.85), new THREE.Color(0.8, 0.7, 0.66),
];

const KIT = ['Saloon', 'GeneralStore', 'Sheriff', 'Bank', 'Hotel', 'Livery', 'Shack'];
// footprint width (along the street) and depth, metres — from town.glb
const WIDTH = { Saloon: 10.5, GeneralStore: 9.7, Sheriff: 8.1, Bank: 8.5, Hotel: 12.5, Livery: 12.8, Shack: 5.2, Church: 8.8, WaterTower: 5.3, Gallows: 6.7 };
const DEPTH = { Saloon: 16.6, GeneralStore: 15.7, Sheriff: 13.4, Bank: 13.2, Hotel: 15.6, Livery: 17.4, Shack: 5.3, Church: 16.6, WaterTower: 5.8, Gallows: 3.1 };

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

export class Towns {
  constructor(route, scene) {
    this.route = route; this.scene = scene;
    this.group = new THREE.Group(); scene.add(this.group);
    this.spawns = []; // { pos: Vector3, face: Vector3 (toward road), s, kind }
    this.folk = [];   // townsfolk in the living towns
    this.solids = []; // AABBs for bullet blocking
    const rnd = mulberry32(route.def.seed + 5);
    // start and end towns
    this._street(20, 110, rnd, 0.8, false);
    this._street(route.len - 130, route.len - 10, rnd, 0.8, false);
    this._folk(24, 108, rnd);
    this._folk(route.len - 126, route.len - 14, rnd);
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
    return w * 2;
  }

  _street(s0, s1, rnd, fill, ghost) {
    const placed = { '-1': [], '1': [] };
    for (const side of [-1, 1]) {
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
        this._place(name, s + w / 2, side, rnd, ghost);
        placed[side].push({ s, name }); last = name;
        // street clutter in front of the boardwalk
        if (ghost || rnd() < 0.5) this._clutter(s + w * (0.2 + rnd() * 0.6), side, rnd);
        s += w + 1.5 + rnd() * 4;
      }
      // a ragged back row so the town doesn't end at one wall
      if (ghost) for (let t = s0 + 10; t < s1 - 10; t += 16 + rnd() * 14) this._place('Shack', t, side, rnd, false, 24 + rnd() * 10);
    }
    // landmarks
    const mid = (s0 + s1) / 2;
    this._place(ghost ? 'Church' : 'WaterTower', mid + 30, rnd() < 0.5 ? -1 : 1, rnd, ghost, 14);
    if (ghost) this._place('Gallows', s0 + 40, -1, rnd, ghost, 2);
  }

  // People on the boardwalks: mostly standing in twos and threes, clear of the
  // road. They turn to watch the stage come in.
  _folk(s0, s1, rnd) {
    const r = this.route;
    let s = s0 + 4 + rnd() * 8;
    while (s < s1) {
      const side = rnd() < 0.5 ? -1 : 1;
      const group = 1 + Math.floor(rnd() * 2.6);      // singles, pairs, the odd trio
      for (let i = 0; i < group; i++) {
        const p = createRider({ variant: FOLK[Math.floor(rnd() * FOLK.length)],
          tint: FOLK_TINT[Math.floor(rnd() * FOLK_TINT.length)] });
        const ps = s + i * (0.7 + rnd() * 0.5);
        const off = 5.8 + rnd() * 2.4;                 // boardwalk, not the roadway
        const f = r.frame(ps, {});
        const x = f.x + f.rx * off * side, z = f.z + f.rz * off * side;
        p.root.position.set(x, r.height(x, z), z);
        // facing the street, give or take — a trio turns in on itself
        const toStreet = Math.atan2(-f.rx * side, -f.rz * side);
        p.baseYaw = toStreet + (group > 2 ? (i - 1) * 0.8 : (rnd() - 0.5) * 1.1);
        p.root.rotation.y = p.baseYaw;
        p.s = ps;
        if (p.has('StandIdle')) p.play('StandIdle');
        this.scene.add(p.root);
        this.folk.push(p);
      }
      s += 9 + rnd() * 15;
    }
  }

  // Rider meshes are built with frustumCulled off (skinned bounds are
  // unreliable), so a townsful of them would draw every frame from anywhere on
  // the route. Show and animate only the ones you're near.
  update(dt, coach) {
    const cs = coach ? coach.s : 0;
    for (const p of this.folk) {
      const away = Math.abs(p.s - cs);
      const near = away < 150;
      if (p.root.visible !== near) p.root.visible = near;
      if (!near) continue;
      p.update(dt);
      // watch the stage go past
      if (away < 26 && coach) {
        const dx = coach.pos.x - p.root.position.x, dz = coach.pos.z - p.root.position.z;
        let want = Math.atan2(dx, dz) - p.baseYaw;
        while (want > Math.PI) want -= Math.PI * 2;
        while (want < -Math.PI) want += Math.PI * 2;
        p.root.rotation.y = damp(p.root.rotation.y, p.baseYaw + want, 3, dt);
      } else {
        p.root.rotation.y = damp(p.root.rotation.y, p.baseYaw, 2, dt);
      }
    }
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
    this.folk.forEach((p) => this.scene.remove(p.root));
    this.folk = [];
  }
}
