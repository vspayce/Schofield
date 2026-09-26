// Places town buildings along the road (start town, end town, ghost town) and
// collects gunman spawn points from the kit's Spawn_* empties.
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { mulberry32 } from '../core/noise.js';

const KIT = ['Saloon', 'GeneralStore', 'Sheriff', 'Bank', 'Hotel', 'Livery', 'Shack'];
const WIDTH = { Saloon: 13, GeneralStore: 10, Sheriff: 9, Bank: 10, Hotel: 12, Livery: 13, Shack: 7, Church: 11, WaterTower: 6, Gallows: 6 };

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
    this.solids = []; // AABBs for bullet blocking
    const rnd = mulberry32(route.def.seed + 5);
    // start and end towns
    this._street(20, 110, rnd, 0.8, false);
    this._street(route.len - 130, route.len - 10, rnd, 0.8, false);
    const T = route.townRange;
    if (T) this._street(T.s0, T.s1, rnd, 1, true);
  }

  _place(name, s, side, rnd, ghost, extraOffset = 0) {
    const r = this.route, f = r.frame(s, {});
    const off = 11 + extraOffset + rnd() * 1.5;
    const x = f.x + f.rx * off * side, z = f.z + f.rz * off * side;
    const b = kitBuilding(name) || fallbackBuilding(name, rnd);
    // front (+Z local) faces the road
    const yaw = Math.atan2(-f.rx * side, -f.rz * side);
    // sit on the lowest corner so it doesn't float on slopes
    const w = (WIDTH[name] || 9) / 2;
    let y = Infinity;
    for (const [a, c] of [[-w, 0], [w, 0], [-w, -10], [w, -10], [0, -5]]) {
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
    for (const side of [-1, 1]) {
      let s = s0 + rnd() * 6;
      while (s < s1) {
        if (rnd() > fill) { s += 8 + rnd() * 10; continue; }
        const name = KIT[Math.floor(rnd() * KIT.length)];
        const w = WIDTH[name] || 9;
        this._place(name, s + w / 2, side, rnd, ghost);
        s += w + 1.5 + rnd() * 4;
      }
    }
    // landmarks
    const mid = (s0 + s1) / 2;
    this._place(ghost ? 'Church' : 'WaterTower', mid + 30, rnd() < 0.5 ? -1 : 1, rnd, ghost, 14);
    if (ghost) this._place('Gallows', s0 + 40, -1, rnd, ghost, 2);
  }

  dispose() { this.scene.remove(this.group); }
}
