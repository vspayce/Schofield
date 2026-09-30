// Wildlife: the herd that crosses the road and makes you haul on the reins, plus
// the odd buffalo, bear, goat and hawk scattered along the route, and now and then
// a dead horse by the road with turkey vultures working it.
//
// Animals live in road space (s, d) like the riders do, so they follow a winding
// road. They are not enemies — they never shoot, they don't chase, and they are
// kept out of Enemies so the threat chevrons and Dead Eye ignore them. Combat
// checks them separately (see combat.js). Birds (hawk, vulture) fly in world
// space around an anchor instead; they share the same interface.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { assets, findNode } from '../core/assets.js';
import { ROAD_HALF } from '../world/route.js';
import { clamp, damp } from '../core/noise.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3();
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _up = new THREE.Vector3(0, 1, 0);

// meat: health restored when you drop one. hide: dollars.
// cy: height of the hit sphere above the origin (birds); graze: head dip [base, swing]
export const SPECIES = {
  buffalo: { node: 'Buffalo', hp: 260, r: 1.15, headR: 0.42, long: 3.1, tall: 1.85, meat: 25, hide: 20, mass: 1, walk: 2.4, graze: [0.30, 0.35] },
  bear: { node: 'Bear', hp: 200, r: 0.8, headR: 0.34, long: 2.0, tall: 1.1, meat: 18, hide: 30, mass: 0.7, walk: 1.8 },
  goat: { node: 'Goat', hp: 70, r: 0.45, headR: 0.22, long: 1.2, tall: 0.9, meat: 10, hide: 12, mass: 0.15, walk: 2.0 },
  hawk: { node: 'Hawk', hp: 25, r: 0.35, headR: 0, long: 0.55, tall: 0.3, meat: 5, hide: 25, mass: 0, walk: 0, cy: 0, dihedral: 0.10 },
  vulture: { node: 'Vulture', hp: 25, r: 0.4, headR: 0, long: 0.72, tall: 0.5, meat: 2, hide: 4, mass: 0, walk: 0, cy: 0.24, dihedral: 0.30 },
};

// Vulture model: built in flight attitude, origin under the feet; standing,
// the root pitches nose-up by PERCH about that origin (build_animals.py).
const PERCH = 0.45;
// Carcass empties if the model is missing (Blender x, y, z -> three x, z, -y)
const CARCASS_SPOTS = {
  Carcass_Perch: [-0.1, 0.47, -0.54, Math.PI / 2],
  Carcass_Feed1: [-0.25, 0.44, 0.12, Math.PI / 2],
  Carcass_Feed2: [0.44, 0, 1.34, -Math.PI / 2],
  Carcass_Feed3: [0.06, 0, -1.2, -0.37],
};

// Drawn larger than life so they read from the coach roof at a gallop. The
// hit spheres, markers and carcass sites all scale with it.
export const SHOW = 1.4;

const FAR = 60 * 60;   // beyond 60 m a quadruped is one merged, unanimated mesh

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
    this.rig = built.root;
    this.root = new THREE.Group(); this.root.add(this.rig);
    this.legs = built.legs; this.head = built.head; this.tail = built.nodes.Tail || null;
    // bison: a bull's thick horns or a cow's slender ones, a cow's smaller beard,
    // and a cow is smaller
    const bull = opts.bull ?? Math.random() < 0.3;
    if (built.nodes.HornBull) built.nodes.HornBull.visible = bull;
    if (built.nodes.HornCow) built.nodes.HornCow.visible = !bull;
    if (built.nodes.Beard && !bull) built.nodes.Beard.scale.set(0.8, 0.6, 0.6);
    this.far = built.real ? baked(kind + (bull ? '' : '_cow'), () => this.rig) : null;
    if (this.far) { this.far.visible = false; this.root.add(this.far); }
    const size = kind !== 'buffalo' ? 0.9 + Math.random() * 0.2 : bull ? 0.96 + Math.random() * 0.09 : 0.79 + Math.random() * 0.07;
    this.scale = (opts.scale ?? size) * SHOW;
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
    this.root.position.copy(this.pos);

    // face along travel for a crosser, otherwise idle facing
    const f = R.frame(this.s, {});
    const roadYaw = Math.atan2(f.tx, f.tz);
    const want = this.crossing ? roadYaw + (this.speed > 0 ? -Math.PI / 2 : Math.PI / 2) : roadYaw + this.heading;
    this.root.rotation.set(0, want, this.alive ? 0 : this.fallT * 1.5, 'YXZ');

    // far off: one merged mesh, no leg swing to pay for
    const far = !!this.far && this.pos.distanceToSquared(g.player.camPos) > FAR;
    if (this.far && far !== this.far.visible) { this.far.visible = far; this.rig.visible = !far; }
    if (!far) this._animate(dt);
    this.spheres[0].c.copy(this.pos).add(_v.set(0, this.cfg.tall * 0.55 * this.scale, 0));
    if (!this.alive && this.removeAt === Infinity && g.coach.s - this.s > 120) this.removeAt = 0;
    if (this.alive && g.coach.s - this.s > 160) this.removeAt = 0;
  }

  _animate(dt) {
    const moving = this.alive && (this.crossing || this.spooked > 0);
    this.phase += dt * (moving ? 5.5 : 0.8);
    if (this.tail) {
      // a slow swish; straight up when alarmed
      const up = this.spooked > 0 ? 1.3 : moving ? 0.25 : 0;
      this.tail.rotation.x = damp(this.tail.rotation.x, up, 3, dt);
      this.tail.rotation.z = Math.sin(this.phase * 0.9) * (this.alive ? 0.18 : 0);
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
      // the models are rigid, not skinned: past ~35 deg the neck starts to
      // intersect the body, so keep the dip inside that
      const [b, a] = this.cfg.graze || [0.30, 0.28];
      if (this.head) this.head.rotation.x = b + Math.sin(this.graze) * a;
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

// ---------------------------------------------------------------- birds
// A hawk on a thermal or a turkey vulture, in world space. Hawks only soar.
// Vultures stand about a carcass (feed / stand / spread), flush when the coach
// comes close, climb into a kettle over the site, teeter on a strong V and
// finally drift off. Shot, a bird drops to the ground.
class Bird {
  constructor(game, kind, pos, opts = {}) {
    this.g = game; this.id = ++_id;
    this.kind = kind; this.cfg = SPECIES[kind];
    this.alive = true; this.removeAt = Infinity;
    this.hp = this.cfg.hp;
    this.site = opts.site || null;
    this.s = opts.s ?? game.coach.s;          // for tidying up behind the coach
    this.d = 99;                              // never on the road
    this.pos = new THREE.Vector3().copy(pos);
    this.yaw = opts.yaw ?? Math.random() * Math.PI * 2;
    this.t = Math.random() * 10;
    this.state = opts.state || 'kettle';
    this.stateT = 0;
    this.delay = 0;
    this.vy = 0;

    const built = buildAnimal(kind);
    this.rig = built.root;
    this.root = new THREE.Group(); this.root.add(this.rig);
    this.head = built.head; this.wings = built.wings;
    this.folded = built.nodes.Folded || null; this.legs = built.nodes.Legs || null;
    this.headP0 = this.head ? this.head.position.clone() : null;
    // A vulture draws as one merged mesh per pose (+ its head on the ground)
    // rather than six nodes; the jointed rig is only used to hop, flap and fall.
    this.v = null; this.mode = null;
    if (built.real && kind === 'vulture') {
      this.v = {};
      for (const k of ['hunch', 'feed', 'spread', 'flight']) { this.v[k] = tvVariant(k); this.root.add(this.v[k]); }
      this.v.flight.castShadow = false;
      this.headMesh = baked('tv_head', () => buildAnimal('vulture').head);
      this.headMesh.position.copy(this.headP0);
      this.root.add(this.headMesh);
    }
    if (kind === 'hawk') this.rig.traverse((o) => { o.castShadow = false; });   // always far overhead
    this.floor = this.state === 'kettle' ? null : this.pos.clone();          // what a shot bird drops onto
    this.scale = (opts.scale ?? (0.92 + Math.random() * 0.16)) * SHOW;
    this.root.scale.setScalar(this.scale);
    game.scene.add(this.root);
    this.spheres = [{ part: 'body', c: new THREE.Vector3(), r: this.cfg.r * this.scale }];

    // flight: a circle about an anchor. r, angular speed (sign = turning side)
    this.anchor = new THREE.Vector3().copy(opts.anchor || pos);
    this.circR = opts.r ?? 8 + Math.random() * 10;
    this.circW = (Math.random() < 0.5 ? -1 : 1) * (opts.speed ?? 8.5) / this.circR;
    this.circA = Math.random() * Math.PI * 2;
    this.alt = opts.alt ?? pos.y - this.anchor.y;
    this.altWant = opts.altWant ?? this.alt;
    this.leaveAt = 25 + Math.random() * 25;
    this.update(0);
  }

  hitPoint() { return this.spheres[0].c.clone(); }

  get airborne() { return this.state === 'kettle' || this.state === 'flush' || this.state === 'leave'; }

  flush(delay) {
    if (!this.alive || this.airborne) return;
    this.state = 'flush'; this.stateT = 0; this.delay = delay;
    // climb away from the coach and into the circle over the carcass
    const c = this.g.coach.pos;
    this.flushDir = Math.atan2(this.pos.x - c.x, this.pos.z - c.z) + (Math.random() - 0.5) * 1.2;
    this.alt = 0;
    this.altWant = 16 + Math.random() * 22;
  }

  update(dt) {
    const g = this.g;
    this.t += dt; this.stateT += dt;
    if (!this.alive) this._dead(dt);
    else if (this.airborne) this._fly(dt);
    else this._ground(dt);
    this.root.position.copy(this.pos);
    this.spheres[0].c.copy(this.pos).y += this.cfg.cy * this.scale;
    const behind = g.coach.s - this.s;
    if (behind > 220 || (this.state === 'leave' && this.pos.distanceTo(g.player.camPos) > 240)) this.removeAt = 0;
  }

  _show(spread) {
    const w = this.wings;
    if (w) w[0].visible = w[1].visible = spread;
    if (this.folded) this.folded.visible = !spread;
  }

  _pose(pitch, roll = 0) {
    this.root.rotation.set(pitch, this.yaw, roll, 'YXZ');
    if (this.legs) this.legs.rotation.x = -(pitch + PERCH);    // stand upright under a tipped body
  }

  // which mesh draws: 'rig' or one of the merged poses
  _use(mode) {
    if (!this.v) mode = 'rig';
    if (mode === this.mode) return;
    this.mode = mode;
    this.rig.visible = mode === 'rig';
    if (!this.v) return;
    for (const k in this.v) this.v[k].visible = k === mode;
    this.headMesh.visible = mode !== 'rig' && mode !== 'flight';
    const air = this.airborne;
    this.rig.traverse((o) => { if (o.isMesh) o.castShadow = !air; });
  }

  _wings(ax, ay, az) {
    const w = this.wings; if (!w) return;
    w[0].rotation.set(ax, ay, az); w[1].rotation.set(ax, -ay, -az);
  }

  _headPose(x, back = 0, down = 0, yaw = 0) {
    for (const h of [this.head, this.headMesh]) {
      if (!h) continue;
      h.rotation.set(x, yaw, 0);
      h.position.copy(this.headP0); h.position.z -= back; h.position.y -= down;
    }
  }

  // --- on the ground (vultures)
  _ground(dt) {
    const t = this.t;
    if (this.legs) this.legs.visible = true;
    if (this.state === 'feed') {
      // head down in the carcass, tugging, now and then up to look round
      this._show(false); this._use('feed');
      this._pose(-PERCH + 0.6);
      const look = Math.sin(t * 0.45) > 0.85;
      const tug = Math.max(0, Math.sin(t * 5.5)) ** 3;
      this._headPose(look ? 0.05 : 0.5 + tug * 0.28, look ? 0 : -0.02 - tug * 0.03, 0, look ? Math.sin(t * 2) * 0.5 : 0);
    } else if (this.state === 'spread') {
      // horaltic pose: wings held wide to the sun, a slow breath in them
      this._show(true); this._use('spread');
      this._pose(-PERCH - 0.3);
      const b = Math.sin(t * 0.8) * 0.04;
      this._wings(0, 0.10, -0.12 + b);
      this._headPose(0.45, 0, 0, Math.sin(t * 0.3) * 0.4);
    } else if (this.state === 'hop') {
      // a wing-assisted sideways bound, half-open wings, then back to hunching
      const k = clamp(this.stateT / 0.7, 0, 1);
      this._show(true); this._use('rig');
      this._wings(0, 0.85, 0.30 + Math.sin(this.stateT * 18) * 0.25);
      this._pose(-PERCH + 0.12);
      this._headPose(0.1, -0.02);
      this.pos.lerpVectors(this.hopFrom, this.hopTo, k);
      this.pos.y += Math.sin(k * Math.PI) * 0.35 * SHOW;
      if (k >= 1) { this.state = 'stand'; this.stateT = 0; this.floor = this.hopTo.clone(); }
    } else {
      // hunched: body upright, head pulled back into the ruff; looks about, the odd hop
      this._show(false); this._use('hunch');
      this._pose(-PERCH - 0.25);
      this._headPose(0.9, 0.09, 0.05, Math.sin(t * 0.37 + this.id) * 0.6);
      if (this.stateT > 3 && Math.random() < dt * 0.12) this._hop();
    }
  }

  _hop() {
    const R = this.g.route, a = this.yaw + (Math.random() < 0.5 ? 1 : -1) * Math.PI / 2;
    const dist = (0.6 + Math.random() * 0.6) * SHOW;
    this.hopFrom = this.pos.clone();
    this.hopTo = this.pos.clone().add(_v.set(Math.sin(a) * dist, 0, Math.cos(a) * dist));
    // stay in the loose ring round the carcass
    if (this.site && this.hopTo.distanceTo(this.site.pos) > 8 * SHOW) this.hopTo.lerp(this.site.pos, 0.3);
    this.hopTo.y = R.height(this.hopTo.x, this.hopTo.z);
    this.state = 'hop'; this.stateT = 0;
  }

  // --- in the air
  _fly(dt) {
    const c = this.cfg, t = this.t;
    let flap = 0, pitch = 0, roll = 0;
    if (this.state === 'flush') {
      if (this.stateT < this.delay) { this._ground(0); return; }
      const k = this.stateT - this.delay;
      // heavy, laboured beats low over the ground, then out into the circle
      this._show(true); this._use('rig');
      if (this.legs) this.legs.visible = k < 0.4;
      flap = Math.sin(k * 17) * 0.75;
      this.yaw = damp(this.yaw, this.flushDir, 2, dt);
      const sp = Math.min(6, 2 + k * 3);
      this.pos.x += Math.sin(this.yaw) * sp * dt; this.pos.z += Math.cos(this.yaw) * sp * dt;
      this.pos.y += (k < 2.2 ? 2.6 : 1.2) * dt;
      pitch = -PERCH * Math.max(0, 1 - k * 1.5);
      if (k > 2.6) {
        // join the kettle from wherever it is
        this.state = 'kettle'; this.stateT = 0;
        const dx = this.pos.x - this.anchor.x, dz = this.pos.z - this.anchor.z;
        this.circA = Math.atan2(dz, dx);
        this.circR = clamp(Math.hypot(dx, dz), 7, 18);
        this.alt = this.pos.y - this.anchor.y;
      }
    } else {
      // soaring: a wide circle, climbing to height, the V rocking side to side
      if (this.legs) this.legs.visible = false;
      this._show(true); this._use('flight');
      if (this.state === 'kettle' && this.site && this.stateT > this.leaveAt) { this.state = 'leave'; this.stateT = 0; }
      if (this.state === 'leave') {
        // drift off down the wind, still circling, higher and higher
        this.anchor.x += this.driftX * dt; this.anchor.z += this.driftZ * dt;
        this.altWant += 1.5 * dt;
      }
      this.alt = damp(this.alt, this.altWant, 0.35, dt);
      this.circA += this.circW * dt;
      this.pos.set(this.anchor.x + Math.cos(this.circA) * this.circR, this.anchor.y + this.alt,
        this.anchor.z + Math.sin(this.circA) * this.circR);
      // heading along the circle; bank into it
      const s = Math.sign(this.circW);
      this.yaw = Math.atan2(-Math.sin(this.circA) * s, Math.cos(this.circA) * s);
      const teeter = this.kind === 'vulture' ? 0.16 : 0.05;
      roll = s * 0.22 + Math.sin(t * 2.1 + this.id) * teeter + Math.sin(t * 5.3) * teeter * 0.3;
      // a hawk flaps a few times now and then; a vulture hardly ever
      const every = this.kind === 'vulture' ? 19 : 9;
      const ph = (t + this.id * 3.7) % every;
      if (ph < 1.1 && !this.v) flap = Math.sin(ph * 14) * 0.45 * Math.sin(ph / 1.1 * Math.PI);
    }
    this._wings(0, 0, c.dihedral + flap);
    if (this.head) this._headPose(0, 0, 0, 0);
    this._pose(pitch, roll);
  }

  _dead(dt) {
    const R = this.g.route, f = this.floor;
    this._use('rig');
    let gy = R.height(this.pos.x, this.pos.z);
    // shot on the carcass: it drops onto the carcass, not through it
    if (f && Math.hypot(this.pos.x - f.x, this.pos.z - f.z) < 0.6 * SHOW) gy = Math.max(gy, f.y);
    if (this.pos.y > gy + 0.01) {
      // tumble out of the sky
      this.vy -= 9.8 * dt;
      this.pos.y = Math.max(gy, this.pos.y + this.vy * dt);
      this.root.rotation.x += dt * 3; this.root.rotation.z += dt * 5;
      this._wings(0, 0, -0.3);
      return;
    }
    // on its side, wings sprawled
    this.pos.y = gy;
    this._show(true);
    if (this.legs) this.legs.visible = true;
    this._wings(0, 0.2, -0.15);
    this.root.rotation.set(damp(this.root.rotation.x % 6.283, 0, 6, dt), this.yaw, damp(this.root.rotation.z % 6.283, 1.45, 6, dt), 'YXZ');
  }

  damage(amount, dir) {
    if (!this.alive) return false;
    this.hp -= amount;
    if (this.site) this.site.flush(this.g);
    if (this.hp > 0) return false;
    this.alive = false;
    this.vy = 0;
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
    const nodes = {};
    for (const n of ['Tail', 'HornBull', 'HornCow', 'Beard', 'Folded', 'Legs']) {
      const o = findNode(root, cfg.node + '_' + n);
      if (o) nodes[n] = o;
    }
    return {
      root, legs, nodes, real: true,
      head: findNode(root, cfg.node + '_Head'),
      wings: wings[0] && wings[1] ? wings : null,
    };
  }
  return fallbackAnimal(cfg, kind);
}

// Merge the visible meshes under `rig`, as posed, into one geometry in rig
// space (gltfpack's quantized attributes come out as plain floats). Cached per
// key and shared, so a whole herd or flock costs one merge.
const _baked = {};
function mergeRig(rig) {
  rig.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(rig.matrixWorld).invert(), m = new THREE.Matrix4();
  const geos = [];
  let mat = null;
  rig.traverseVisible((o) => {
    if (!o.isMesh) return;
    mat = mat || o.material;
    const g = new THREE.BufferGeometry(), src = o.geometry;
    for (const k of ['position', 'normal', 'uv']) {
      const a = src.attributes[k], n = a.itemSize, arr = new Float32Array(a.count * n);
      for (let i = 0; i < a.count; i++) for (let j = 0; j < n; j++) arr[i * n + j] = a.getComponent(i, j);
      g.setAttribute(k, new THREE.BufferAttribute(arr, n));
    }
    g.setIndex(new THREE.BufferAttribute(Uint32Array.from(src.index.array), 1));
    geos.push(g.applyMatrix4(m.multiplyMatrices(inv, o.matrixWorld)));
  });
  return { geo: mergeGeometries(geos), mat };
}

function baked(key, make) {
  const c = _baked[key] || (_baked[key] = mergeRig(make()));
  const mesh = new THREE.Mesh(c.geo, c.mat);
  mesh.castShadow = true; mesh.receiveShadow = true;
  return mesh;
}

// the vulture's poses, each one mesh: legs counter-rotated so they stand
// upright under the tipped body (see Bird._pose), wings posed as in _ground/_fly
function tvVariant(pose) {
  return baked('tv_' + pose, () => {
    const b = buildAnimal('vulture'), n = b.nodes, [wl, wr] = b.wings, dh = SPECIES.vulture.dihedral;
    b.head.visible = pose === 'flight';
    if (pose === 'flight') {
      n.Folded.visible = n.Legs.visible = false;
      wl.rotation.z = dh; wr.rotation.z = -dh;
    } else if (pose === 'spread') {
      n.Folded.visible = false;
      wl.rotation.set(0, 0.10, -0.12); wr.rotation.set(0, -0.10, 0.12);
      n.Legs.rotation.x = 0.3;
    } else {
      wl.visible = wr.visible = false;
      if (pose === 'hunch') { n.Folded.position.y -= 0.02; n.Legs.rotation.x = 0.25; } else n.Legs.rotation.x = -0.6;
    }
    return b.root;
  });
}

function fallbackAnimal(cfg, kind) {
  const root = new THREE.Group();
  const hide = new THREE.MeshStandardMaterial({
    color: kind === 'buffalo' ? 0x4a3728 : kind === 'bear' ? 0x3a2a1e : kind === 'goat' ? 0xb8a488 : kind === 'vulture' ? 0x2a211c : 0x6a5038,
    roughness: 0.9,
  });
  if (kind === 'hawk') {
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.3, 3, 6).rotateX(Math.PI / 2), hide);
    root.add(body);
    const wings = [1, -1].map((sx) => {
      const w = new THREE.Group();
      const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.02, 0.18), hide);
      m.position.x = sx * 0.3; w.add(m); root.add(w);
      return w;
    });
    return { root, legs: [], head: null, wings, nodes: {} };
  }
  if (kind === 'vulture') {
    // same pivots as the model: origin under the feet, flight attitude
    const Y = 0.23;
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.3, 3, 6).rotateX(Math.PI / 2), hide);
    body.position.set(0, Y, 0.12); root.add(body);
    const tail = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.012, 0.24), hide);
    tail.position.set(0, Y, -0.12); root.add(tail);
    const grey = new THREE.MeshStandardMaterial({ color: 0x8f8d88, roughness: 0.8 });
    const wings = [1, -1].map((sx) => {
      const w = new THREE.Group();
      w.position.set(sx * 0.06, Y + 0.03, 0.22);
      const a = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.02, 0.17), hide);
      a.position.set(sx * 0.41, 0, 0.0);
      const b = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.015, 0.17), grey);
      b.position.set(sx * 0.41, -0.004, -0.16);
      w.add(a, b); root.add(w);
      return w;
    });
    const head = new THREE.Group();
    head.position.set(0, Y + 0.02, 0.31); root.add(head);
    const skin = new THREE.Mesh(new THREE.SphereGeometry(0.03, 8, 6), new THREE.MeshStandardMaterial({ color: 0xb8403a, roughness: 0.6 }));
    skin.scale.set(0.8, 0.8, 1.6); skin.position.z = 0.09; head.add(skin);
    const bill = new THREE.Mesh(new THREE.ConeGeometry(0.01, 0.04, 5).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0xe6dec6 }));
    bill.position.z = 0.15; head.add(bill);
    const folded = new THREE.Group(); root.add(folded);
    for (const sx of [1, -1]) {
      const f = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.1, 0.5), hide);
      f.position.set(sx * 0.09, Y + 0.1, 0.0); folded.add(f);
    }
    const legs = new THREE.Group(); root.add(legs);
    const pale = new THREE.MeshStandardMaterial({ color: 0xd6c3b6 });
    for (const sx of [1, -1]) {
      const l = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.16, 5), pale);
      l.position.set(sx * 0.045, 0.08, 0.04); l.rotation.x = -PERCH; legs.add(l);
    }
    root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    return { root, legs: [], head, wings, nodes: { Folded: folded, Legs: legs } };
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
  return { root, legs, head, wings: null, nodes: {} };
}

// the carcass and where the birds go on it
function buildCarcass() {
  const g = assets.models.animals;
  const src = g && findNode(g.scene, 'Carcass');
  if (src) {
    const root = src.clone(true);
    root.position.set(0, 0, 0);
    root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    return root;
  }
  // a dry hide over a barrel, a few ribs, stiff legs
  const root = new THREE.Group();
  const hide = new THREE.MeshStandardMaterial({ color: 0x8a7560, roughness: 0.95 });
  const bone = new THREE.MeshStandardMaterial({ color: 0xd8cdb4, roughness: 0.8 });
  const barrel = new THREE.Mesh(new THREE.CapsuleGeometry(0.26, 1.3, 4, 10).rotateX(Math.PI / 2), hide);
  barrel.scale.set(1.4, 0.95, 1); barrel.position.set(-0.03, 0.25, -0.05); root.add(barrel);
  const neck = new THREE.Mesh(new THREE.CapsuleGeometry(0.13, 0.6, 3, 8).rotateX(Math.PI / 2), hide);
  neck.position.set(-0.1, 0.13, 0.95); root.add(neck);
  const skull = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.5, 6).rotateX(Math.PI / 2), bone);
  skull.position.set(-0.08, 0.1, 1.4); root.add(skull);
  for (let i = 0; i < 6; i++) {
    const r = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.012, 4, 10, 1.6), bone);
    r.position.set(0.02, 0.2, 0.3 - i * 0.085); r.rotation.set(0, Math.PI / 2, 0.9); root.add(r);
  }
  for (const [x, z, y] of [[0.55, 0.62, 0.3], [0.55, 0.45, 0.1], [0.55, -0.6, 0.3], [0.55, -0.7, 0.1]]) {
    const l = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.8, 3, 6).rotateZ(Math.PI / 2), hide);
    l.position.set(x, y, z); root.add(l);
  }
  for (const [name, [x, y, z, ry]] of Object.entries(CARCASS_SPOTS)) {
    const e = new THREE.Object3D(); e.name = name; e.position.set(x, y, z); e.rotation.y = ry; root.add(e);
  }
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return root;
}

// A dead horse by the road and the vultures on it. The carcass is scenery; the
// birds are Birds in the wildlife list.
class CarcassSite {
  constructor(game, s, d, list) {
    const g = game, R = g.route;
    this.g = g; this.s = s; this.flushed = false;
    this.pos = R.worldAt(s, d, new THREE.Vector3());
    const f = R.frame(s, {});
    this.yaw = Math.atan2(f.tx, f.tz) + (Math.random() - 0.5) * 1.4 + (Math.random() < 0.5 ? Math.PI : 0);
    // lie on the slope, not through it
    const p = this.pos, h = (x, z) => R.height(x, z);
    const n = _v.set(h(p.x - 1, p.z) - h(p.x + 1, p.z), 2, h(p.x, p.z - 1) - h(p.x, p.z + 1)).normalize();
    this.root = buildCarcass();
    this.root.quaternion.multiplyQuaternions(_q.setFromUnitVectors(_up, n), _q2.setFromAxisAngle(_up, this.yaw));
    this.root.position.copy(p).y -= 0.03;
    this.root.scale.setScalar(SHOW);
    g.scene.add(this.root);
    this.root.updateMatrixWorld(true);

    // 3-12 birds: one or two on the perch spread to the sun, one to three
    // feeding, the rest hunched round it in a loose ring
    const spot = (name) => {
      const e = findNode(this.root, name);
      const q = CARCASS_SPOTS[name];
      if (!e) return { p: _v2.set(q[0], q[1], q[2]).applyMatrix4(this.root.matrixWorld).clone(), yaw: this.yaw + q[3] };
      return { p: e.getWorldPosition(new THREE.Vector3()), yaw: this.yaw + 2 * Math.atan2(e.quaternion.y, e.quaternion.w) };
    };
    const n0 = 3 + Math.floor(Math.random() * 10);
    const feeders = ['Carcass_Feed1', 'Carcass_Feed2', 'Carcass_Feed3'].sort(() => Math.random() - 0.5)
      .slice(0, Math.min(n0 - 1, 1 + Math.floor(Math.random() * 3)));
    const spreads = Math.min(n0 - feeders.length, n0 > 6 && Math.random() < 0.5 ? 2 : 1);
    this.birds = [];
    const add = (pos, yaw, state) => {
      const b = new Bird(g, 'vulture', pos, { yaw, state, site: this, s, anchor: this.pos, alt: 0 });
      this.birds.push(b); list.push(b);
    };
    for (const name of feeders) { const sp = spot(name); add(sp.p, sp.yaw, 'feed'); }
    for (let i = 0; i < spreads; i++) {
      if (i === 0) { const sp = spot('Carcass_Perch'); add(sp.p, sp.yaw + (Math.random() - 0.5), 'spread'); continue; }
      const a = Math.random() * 6.28, r = (3 + Math.random() * 3) * SHOW;
      const q = new THREE.Vector3(p.x + Math.cos(a) * r, 0, p.z + Math.sin(a) * r);
      q.y = R.height(q.x, q.z);
      add(q, Math.random() * 6.28, 'spread');
    }
    for (let i = this.birds.length; i < n0; i++) {
      const a = Math.random() * 6.28, r = (2 + Math.random() * 6) * SHOW;
      const q = new THREE.Vector3(p.x + Math.cos(a) * r, 0, p.z + Math.sin(a) * r);
      q.y = R.height(q.x, q.z);
      // facing the carcass, more or less
      add(q, Math.atan2(p.x - q.x, p.z - q.z) + (Math.random() - 0.5) * 1.6, 'stand');
    }
    // the kettle you see first: a couple already turning high over it
    for (let i = 0; i < Math.floor(Math.random() * 3); i++) {
      const b = new Bird(g, 'vulture', p, { state: 'kettle', site: this, s, anchor: this.pos, alt: 25 + Math.random() * 15, r: (10 + Math.random() * 10) * SHOW });
      this.birds.push(b); list.push(b);
    }
    const drift = Math.random() * 6.28;
    for (const b of this.birds) { b.driftX = Math.cos(drift) * 3; b.driftZ = Math.sin(drift) * 3; }
  }

  flush(g) {
    if (this.flushed) return;
    this.flushed = true;
    for (const b of this.birds) b.flush(Math.random() * 1.2);
  }

  update() {
    const g = this.g;
    // the coach within ~30 m puts them all up
    if (!this.flushed && g.coach.pos.distanceToSquared(this.pos) < 30 * 30) this.flush(g);
    return g.coach.s - this.s > 220;
  }

  dispose() { this.g.scene.remove(this.root); }
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
    // a couple of carcass sites per route (wildlife.carcass overrides; 0 = none)
    this.sites = [];
    const n = this.cfg ? (this.cfg.carcass ?? 2) : 0;
    this.carcassAt = [];
    for (let i = 0; i < n; i++) this.carcassAt.push(0.14 + (0.72 * (i + 0.2 + Math.random() * 0.6)) / n);
  }

  update(dt) {
    const g = this.g, coach = g.coach;
    const prog = coach.s / g.route.len;
    for (const h of this.herds) {
      if (!h.done && prog >= h.at) { h.done = true; this._startHerd(h); }
    }
    if (this.cfg) this._ambient(dt);
    this._carcass();
    for (const a of this.list) a.update(dt);
    this._herdWarning();
    this._collide(dt);
    for (let i = this.list.length - 1; i >= 0; i--) {
      const a = this.list[i];
      if (g.time >= a.removeAt || a.removeAt === 0) { a.dispose(); this.list.splice(i, 1); }
    }
    for (let i = this.sites.length - 1; i >= 0; i--) {
      if (this.sites[i].update()) { this.sites[i].dispose(); this.sites.splice(i, 1); }
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
    const taken = [], gap = 3.8 * SHOW / 1.4;
    for (let i = 0; i < n; i++) {
      // a loose column: spread along the road and staggered across it, never
      // two animals in the same spot
      let s, d;
      for (let k = 0; k < 14; k++) {
        s = s0 + (Math.random() - 0.5) * 34 * SHOW;
        d = side * (d0 + ((Math.random() - 0.5) * 26 + (i % 5) * 2.2) * SHOW);
        if (taken.every(([ts, td]) => Math.hypot(ts - s, td - d) > gap)) break;
      }
      taken.push([s, d]);
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
    if (away > 380 || away < 0) return;
    this._warned = true;
    this.g.hud.banner('BUFFALO HERD AHEAD', 'Rein in now — they are crossing the road', 4.2);
    audio.play('horse_neigh', { volume: 1, pitch: 0.78 });
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
      g.damageCoach(dmg);
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
  // Animals dotted along the route, spawned ahead of the coach as it travels.
  // They come in small groups, because one lone goat on an empty plain reads as
  // a glitch while three grazing together reads as wildlife.
  _ambient(dt) {
    const g = this.g, R = g.route;
    if (g.coach.s < this._ambientAt) return;
    const c = this.cfg;
    this._ambientAt = g.coach.s + (c.every || 110) * (0.7 + Math.random() * 0.6);
    const kinds = c.kinds || ['goat'];
    const kind = kinds[Math.floor(Math.random() * kinds.length)];
    const s = g.coach.s + 120 + Math.random() * 110;
    if (s > R.len - 60) return;
    if (kind === 'hawk') {
      // a pair on the same thermal, low enough to actually notice
      const d = (Math.random() < 0.5 ? -1 : 1) * (14 + Math.random() * 30);
      const at = R.worldAt(s, d, new THREE.Vector3());
      for (let i = 0; i < 1 + (Math.random() < 0.5 ? 1 : 0); i++) {
        const alt = 13 + Math.random() * 10;
        this.list.push(new Bird(g, 'hawk', _v2.copy(at).setY(at.y + alt), { s, anchor: at, alt, r: 6 + Math.random() * 9, speed: 7 }));
      }
      return;
    }
    // a small group on ground that isn't a cliff
    const want = kind === 'buffalo' ? 2 + Math.floor(Math.random() * 3) : 1 + Math.floor(Math.random() * 3);
    const sideSign = Math.random() < 0.5 ? -1 : 1;
    let placed = 0;
    for (let k = 0; k < 24 && placed < want; k++) {
      const d = sideSign * (8 + Math.random() * 20);   // near enough to see and to shoot
      const ss = s + (Math.random() - 0.5) * 16;
      const p = R.worldAt(ss, d, _v2);
      const slope = Math.hypot(R.height(p.x + 2, p.z) - p.y, R.height(p.x, p.z + 2) - p.y) / 2;
      if (slope > 0.55) continue;
      this.list.push(new Animal(g, kind, ss, d, { heading: Math.random() * 6.3 }));
      placed++;
    }
  }

  // a carcass comes into view ~250 m out, on flat ground a few metres off the road
  _carcass() {
    const g = this.g, R = g.route;
    const next = this.carcassAt[0];
    if (next === undefined || g.coach.s < next * R.len - 250) return;
    this.carcassAt.shift();
    const s = next * R.len;
    if (s > R.len - 60 || (R.inTown && R.inTown(s))) return;
    const side = Math.random() < 0.5 ? -1 : 1;
    for (let k = 0; k < 10; k++) {
      const d = (k % 2 ? -side : side) * (9 + Math.random() * 8);
      const p = R.worldAt(s, d, _v2);
      const slope = Math.hypot(R.height(p.x + 2, p.z) - p.y, R.height(p.x, p.z + 2) - p.y) / 2;
      if (slope > 0.28) continue;
      this.sites.push(new CarcassSite(g, s, d, this.list));
      return;
    }
  }

  // ------------------------------------------------------------- hits
  pick(origin, dir, tolerance) {
    let best = null, bestAngle = tolerance;
    for (const animal of this.list) {
      if (!animal.alive) continue;
      const sphere = animal.spheres[0];
      const to = _v.subVectors(sphere.c, origin);
      const dist = to.length();
      if (dist > 260 || dist < 0.001) continue;
      const angle = Math.acos(clamp(to.dot(dir) / dist, -1, 1)) - Math.atan(sphere.r / dist);
      if (angle < bestAngle) {
        bestAngle = angle;
        best = { animal, aimPoint: sphere.c, dist };
      }
    }
    return best;
  }

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

  dispose() {
    this.list.forEach((a) => a.dispose()); this.list = [];
    this.sites.forEach((s) => s.dispose()); this.sites = [];
  }
}
