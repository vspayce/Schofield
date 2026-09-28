// Wildlife: the herd that crosses the road and makes you haul on the reins, plus
// the odd buffalo, bear, goat and hawk scattered along the route.
//
// Animals live in road space (s, d) like the riders do, so they follow a winding
// road. They are not enemies — they never shoot, they don't chase, and they are
// kept out of Enemies so the threat chevrons and Dead Eye ignore them. Combat
// checks them separately (see combat.js).
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { assets, findNode } from '../core/assets.js';
import { ROAD_HALF } from '../world/route.js';
import { clamp, damp } from '../core/noise.js';

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3();

// meat: health restored when you drop one. hide: dollars.
export const SPECIES = {
  buffalo: { node: 'Buffalo', hp: 260, r: 1.1, headR: 0.42, long: 2.8, tall: 1.7, meat: 25, hide: 20, mass: 1, walk: 2.4 },
  bear: { node: 'Bear', hp: 200, r: 0.8, headR: 0.34, long: 2.0, tall: 1.1, meat: 18, hide: 30, mass: 0.7, walk: 1.8 },
  goat: { node: 'Goat', hp: 70, r: 0.45, headR: 0.22, long: 1.2, tall: 0.9, meat: 10, hide: 12, mass: 0.15, walk: 2.0 },
  hawk: { node: 'Hawk', hp: 25, r: 0.35, headR: 0, long: 1.1, tall: 0.3, meat: 0, hide: 25, mass: 0, walk: 0 },
};

let _id = 0;

// A four-legged animal, animated by swinging the leg and head nodes the model
// ships (no skinning — see DESIGN.md). Falls on its side when killed.
class Animal {
  constructor(game, kind, s, d, opts = {}) {
    this.g = game; this.id = ++_id;
    this.kind = kind; this.cfg = SPECIES[kind];
    this.alive = true; this.removeAt = Infinity;
    this.s = s; this.d = d;
    this.heading = opts.heading ?? 0;
    this.speed = opts.speed ?? 0;
    this.crossing = !!opts.crossing;
    this.phase = Math.random() * Math.PI * 2;
    this.graze = Math.random();
    this.pos = new THREE.Vector3();
    this.hp = this.cfg.hp;
    this.fallT = 0;
    this.spooked = 0;

    const built = buildAnimal(kind);
    this.root = built.root;
    this.legs = built.legs; this.head = built.head; this.wings = built.wings;
    this.scale = opts.scale ?? (0.9 + Math.random() * 0.2);
    this.root.scale.setScalar(this.scale);
    game.scene.add(this.root);
    // one sphere is enough for a hit test at the sizes these are shot from
    this.spheres = [{ part: 'body', c: new THREE.Vector3(), r: this.cfg.r * this.scale }];
    this.update(0);
  }

  hitPoint() { return this.spheres[0].c.clone(); }

  update(dt) {
    const g = this.g, R = g.route;
    if (this.alive) {
      if (this.crossing) {
        // walk steadily across the road; nothing hurries a buffalo
        this.d += this.speed * dt;
        if (Math.abs(this.d) > 70) { this.removeAt = 0; }
      } else if (this.spooked > 0) {
        // bolt away from the road for a few seconds after a near miss
        this.spooked -= dt;
        this.d += Math.sign(this.d || 1) * this.cfg.walk * 1.8 * dt;
      }
    } else {
      this.fallT = Math.min(1, this.fallT + dt * 2.2);
    }
    R.worldAt(this.s, this.d, this.pos);
    if (this.flyH) this.pos.y += this.flyH;        // hawks ride high
    this.root.position.copy(this.pos);

    // face along travel for a crosser, otherwise idle facing
    const f = R.frame(this.s, {});
    const roadYaw = Math.atan2(f.tx, f.tz);
    const want = this.crossing ? roadYaw + (this.speed > 0 ? -Math.PI / 2 : Math.PI / 2) : roadYaw + this.heading;
    this.root.rotation.set(0, want, this.alive ? 0 : this.fallT * 1.5, 'YXZ');

    this._animate(dt);
    this.spheres[0].c.copy(this.pos).add(_v.set(0, this.cfg.tall * 0.55 * this.scale, 0));
    if (!this.alive && this.removeAt === Infinity && g.coach.s - this.s > 120) this.removeAt = 0;
    if (this.alive && g.coach.s - this.s > 160) this.removeAt = 0;
  }

  _animate(dt) {
    const moving = this.alive && (this.crossing || this.spooked > 0);
    this.phase += dt * (moving ? 5.5 : 0.8);
    if (this.wings) {
      // a hawk on a thermal: slow flap, wings held out
      const a = Math.sin(this.phase * 0.7) * 0.35;
      this.wings[0].rotation.z = a; this.wings[1].rotation.z = -a;
      return;
    }
    if (!this.alive) {
      for (const l of this.legs) l.rotation.x = damp(l.rotation.x, 0.5, 4, dt);
      if (this.head) this.head.rotation.x = damp(this.head.rotation.x, 0.3, 4, dt);
      return;
    }
    if (moving) {
      this.legs.forEach((l, i) => { l.rotation.x = Math.sin(this.phase + (i < 2 ? 0 : Math.PI) + (i % 2) * Math.PI) * 0.5; });
      if (this.head) this.head.rotation.x = Math.sin(this.phase * 0.5) * 0.06;
    } else {
      // grazing: head dips, the odd shuffle
      for (const l of this.legs) l.rotation.x = damp(l.rotation.x, 0, 3, dt);
      this.graze += dt * 0.12;
      if (this.head) this.head.rotation.x = 0.5 + Math.sin(this.graze) * 0.35;
    }
  }

  damage(amount, dir) {
    if (!this.alive) return false;
    this.hp -= amount;
    this.spooked = 4;
    if (this.hp > 0) return false;
    this.alive = false;
    this.removeAt = this.g.time + 25;
    return true;
  }

  dispose() { this.g.scene.remove(this.root); }
}

// ---------------------------------------------------------------- model
// Clone from animals.glb and pick up the nodes the game animates. If the model
// is missing, fall back to blocks so the game still plays (as elsewhere here).
function buildAnimal(kind) {
  const cfg = SPECIES[kind];
  const g = assets.models.animals;
  const src = g && findNode(g.scene, cfg.node);
  if (src) {
    const root = src.clone(true);
    root.position.set(0, 0, 0);
    root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    const legs = ['LegFL', 'LegFR', 'LegRL', 'LegRR'].map((n) => findNode(root, cfg.node + '_' + n)).filter(Boolean);
    const wings = [findNode(root, cfg.node + '_WingL'), findNode(root, cfg.node + '_WingR')];
    return {
      root, legs,
      head: findNode(root, cfg.node + '_Head'),
      wings: wings[0] && wings[1] ? wings : null,
    };
  }
  return fallbackAnimal(cfg, kind);
}

function fallbackAnimal(cfg, kind) {
  const root = new THREE.Group();
  const hide = new THREE.MeshStandardMaterial({
    color: kind === 'buffalo' ? 0x4a3728 : kind === 'bear' ? 0x3a2a1e : kind === 'goat' ? 0xb8a488 : 0x6a5038,
    roughness: 0.9,
  });
  if (kind === 'hawk') {
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.3, 3, 6).rotateX(Math.PI / 2), hide);
    root.add(body);
    const wings = [-1, 1].map((sx) => {
      const w = new THREE.Group();
      const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.02, 0.18), hide);
      m.position.x = sx * 0.25; w.add(m); root.add(w);
      return w;
    });
    return { root, legs: [], head: null, wings };
  }
  const L = cfg.long, H = cfg.tall;
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(H * 0.3, L * 0.5, 4, 8).rotateX(Math.PI / 2), hide);
  body.position.y = H * 0.72; root.add(body);
  if (kind === 'buffalo') { // the hump is the whole silhouette
    const hump = new THREE.Mesh(new THREE.SphereGeometry(H * 0.34, 8, 6), hide);
    hump.position.set(0, H * 0.92, L * 0.18); hump.scale.set(1, 0.8, 1.2); root.add(hump);
  }
  const head = new THREE.Group();
  head.position.set(0, H * 0.72, L * 0.34); root.add(head);
  const skull = new THREE.Mesh(new THREE.BoxGeometry(H * 0.3, H * 0.28, L * 0.22), hide);
  skull.position.set(0, -H * 0.1, L * 0.1); head.add(skull);
  const legs = [];
  for (const [sx, sz] of [[-1, 1], [1, 1], [-1, -1], [1, -1]]) {
    const leg = new THREE.Group();
    leg.position.set(sx * H * 0.2, H * 0.62, sz * L * 0.24); root.add(leg);
    const m = new THREE.Mesh(new THREE.CapsuleGeometry(H * 0.055, H * 0.5, 3, 6), hide);
    m.position.y = -H * 0.3; leg.add(m);
    legs.push(leg);
  }
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return { root, legs, head, wings: null };
}

// ------------------------------------------------------------- manager
export class Wildlife {
  constructor(game) {
    this.g = game;
    this.list = [];
    const def = game.route.def;
    this.cfg = def.wildlife || null;
    this.herds = (def.waves || []).filter((w) => w.type === 'herd').map((w) => ({ ...w, done: false }));
    this._ambientAt = 0;
    this._warned = false;
    this.herdActive = null;
  }

  update(dt) {
    const g = this.g, coach = g.coach;
    const prog = coach.s / g.route.len;
    for (const h of this.herds) {
      if (!h.done && prog >= h.at) { h.done = true; this._startHerd(h); }
    }
    if (this.cfg) this._ambient(dt);
    for (const a of this.list) a.update(dt);
    this._herdWarning();
    this._collide(dt);
    for (let i = this.list.length - 1; i >= 0; i--) {
      const a = this.list[i];
      if (g.time >= a.removeAt || a.removeAt === 0) { a.dispose(); this.list.splice(i, 1); }
    }
  }

  // ------------------------------------------------------------- herd
  _startHerd(h) {
    const g = this.g, R = g.route;
    // far enough ahead that you see them long before you reach them
    const s0 = g.coach.s + (h.lead || 300);
    if (s0 > R.len - 80) return;
    const side = Math.random() < 0.5 ? -1 : 1;
    const n = h.count || 14;
    const kind = h.kind || 'buffalo';
    const walk = SPECIES[kind].walk;
    // Start them far enough out that the herd is astride the road exactly when a
    // coach at cruise would get here — so holding the reins is what saves you and
    // braking lets them pass. Anchored to arrival time, not to a fixed distance.
    const arrive = (h.lead || 300) / Math.max(6, g.coach.cruise);
    const d0 = walk * arrive;
    for (let i = 0; i < n; i++) {
      // a loose column: spread along the road and staggered across it
      const s = s0 + (Math.random() - 0.5) * 34;
      const d = side * (d0 + (Math.random() - 0.5) * 26 + (i % 5) * 2.2);
      this.list.push(new Animal(g, kind, s, d, { crossing: true, speed: -side * walk * (0.9 + Math.random() * 0.2) }));
    }
    this.herdActive = { s: s0, kind, n };
    this._warned = false;
  }

  // shout once when the herd is close enough to matter
  _herdWarning() {
    const H = this.herdActive;
    if (!H || this._warned) return;
    const away = H.s - this.g.coach.s;
    if (away > 170 || away < 0) return;
    this._warned = true;
    this.g.hud.banner('Buffalo on the road!', 'Rein them in', 2.2);
    audio.play('horse_neigh', { volume: 0.7, pitch: 0.8 });
  }

  // anything of size standing on the road when the coach arrives is a crash
  _collide(dt) {
    const g = this.g, coach = g.coach;
    if (g.over) return;
    this._hitCd = Math.max(0, (this._hitCd || 0) - dt);
    if (this._hitCd > 0) return;
    for (const a of this.list) {
      if (!a.alive || a.cfg.mass < 0.3) continue;
      if (Math.abs(a.d) > ROAD_HALF - 0.4) continue;
      const ds = a.s - coach.s;
      if (ds < -1.5 || ds > 5.5) continue;
      // glancing at a crawl, ruinous at a gallop
      const v = Math.max(0, coach.speed);
      const dmg = clamp(v * 1.5 * a.cfg.mass, 4, 26);
      coach.hp -= dmg;
      coach.speed = Math.max(2, coach.speed * 0.45);
      g.shake += 0.5;
      g.hitStop(0.09);
      this._hitCd = 2.0;   // one impact reads clearly; four in a row is a pile-up
      a.alive = false; a.removeAt = g.time + 20;
      audio.play('hit_flesh_1', { volume: 1, pitch: 0.7 });
      audio.play('horse_neigh', { volume: 0.9, pitch: 0.85 });
      g.fx.dust(a.pos, { amount: 20, size: 1.3, up: 2.5, spread: 4 });
      g.hud.feedMsg('Ran down a ' + a.kind + '!', false);
      g.player.damage(6, a.pos);
      g.onCoachDamage();
      break;
    }
  }

  // ---------------------------------------------------------- ambient
  // a few animals dotted along the route, spawned just ahead as you travel
  _ambient(dt) {
    const g = this.g, R = g.route;
    if (g.coach.s < this._ambientAt) return;
    const c = this.cfg;
    this._ambientAt = g.coach.s + (c.every || 260) * (0.6 + Math.random() * 0.8);
    const kinds = c.kinds || ['goat'];
    const kind = kinds[Math.floor(Math.random() * kinds.length)];
    const s = g.coach.s + 130 + Math.random() * 90;
    if (s > R.len - 60) return;
    if (kind === 'hawk') {
      const d = (Math.random() < 0.5 ? -1 : 1) * (20 + Math.random() * 40);
      const a = new Animal(g, 'hawk', s, d, { heading: Math.random() * 6.3 });
      a.flyH = 22 + Math.random() * 14;
      this.list.push(a);
      return;
    }
    // off the road, on ground that isn't a cliff
    for (let k = 0; k < 10; k++) {
      const d = (Math.random() < 0.5 ? -1 : 1) * (12 + Math.random() * 30);
      const p = R.worldAt(s, d, _v2);
      const slope = Math.hypot(R.height(p.x + 2, p.z) - p.y, R.height(p.x, p.z + 2) - p.y) / 2;
      if (slope > 0.55) continue;
      this.list.push(new Animal(g, kind, s, d, { heading: Math.random() * 6.3 }));
      return;
    }
  }

  // ------------------------------------------------------------- hits
  rayHit(origin, dir, range) {
    let best = null, bestT = range;
    for (const a of this.list) {
      if (!a.alive) continue;
      const sp = a.spheres[0];
      const oc = _v.subVectors(origin, sp.c);
      const b = oc.dot(dir), c = oc.lengthSq() - sp.r * sp.r;
      const h = b * b - c;
      if (h < 0) continue;
      const t = -b - Math.sqrt(h);
      if (t > 0 && t < bestT) { bestT = t; best = { animal: a, t, point: origin.clone().addScaledVector(dir, t) }; }
    }
    return best;
  }

  dispose() { this.list.forEach((a) => a.dispose()); this.list = []; }
}
