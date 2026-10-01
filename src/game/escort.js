// Guns for hire: mounted escorts paid per ride. They live in road space (s, d)
// like the enemy riders, hold a slot beside the coach, peel out to fight and
// come back. Never in the enemies list, so the player's shots, aim assist,
// chevrons and Dead Eye all pass straight through them.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import * as Chars from './characters.js';
import { createHorse, createRider, createWeapon, aimBone } from './characters.js';
import { ROAD_HALF } from '../world/route.js';
import { clamp, damp } from '../core/noise.js';

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _line = new THREE.Line3(), _ray = new THREE.Ray();

// the escort's cut: his kills pay you this share of the bounty, he keeps the rest
export const ESCORT_CUT = 0.5;
// a fresh rider is the player's for this long before a hired man may take him
export const PLAYER_PRIORITY = 4;

// acc = [hit chance point blank, at full range]; interval = seconds between
// shots (Bill fires a pair, one from each Colt, then waits); rest = how long he
// holds off after a kill; react = first-shot delay on a new target.
// slot = formation [ds along the road from the coach origin, d in units of 3.6 m, right-positive].
export const HIRES = {
  bill: {
    id: 'bill', name: 'Wild Bill Hickok', tag: 'WILD BILL', price: 1500, year: 1837,
    blurb: 'Late marshal of Abilene. Two ivory-handled 1851 Navies worn butt-forward, and he aims for the head. Rides your right flank. Paid up front, win or lose.',
    variant: 'hickok', fallback: 'drifter', tint: [0.32, 0.3, 0.3], breed: 'thoroughbred', coat: [0.42, 0.36, 0.34],
    guns: 2, gun: 'Schofield', finish: [1.25, 1.05, 0.7], snd: 'schofield_shot', pitch: 1.05,
    hp: 240, range: 50, react: 0.45, interval: [1.5, 2.0], pair: 0.24, acc: [0.86, 0.5], head: 0.65,
    dmg: 60, headMult: 3, rest: 3.5, slot: [0, 1], pic: 'navy',
    stats: { Aim: 0.95, Speed: 0.9, Grit: 0.8 },
  },
  rifle: {
    id: 'rifle', name: 'Hired Rifle', tag: 'HIRED GUN', price: 400, year: 1873,
    blurb: 'A drover between herds with a Winchester and no questions. Steady at range, slow to work the lever. The first hand hired rides your left; a second takes the rear quarter.',
    variant: 'lawman', fallback: 'townsman', tint: [1.05, 0.92, 0.75], coat: [0.95, 0.7, 0.5],
    guns: 1, gun: 'Winchester', snd: 'schofield_shot', pitch: 0.8, rifle: true,
    hp: 110, range: 85, react: 1.1, interval: [2.7, 3.7], acc: [0.55, 0.22], head: 0.12,
    dmg: 55, headMult: 2.5, rest: 5, pic: 'winchester',
    stats: { Aim: 0.5, Speed: 0.35, Grit: 0.45 },
  },
  pistol: {
    id: 'pistol', name: 'Hired Pistol', tag: 'HIRED GUN', price: 400, year: 1875,
    blurb: 'A Texas gun hand who has seen the elephant once or twice. Quick enough up close; competent, not clever.',
    variant: 'lawman', fallback: 'drifter', tint: [0.8, 0.78, 0.72], coat: [0.5, 0.38, 0.3],
    guns: 1, gun: 'Schofield', snd: 'schofield_shot2', pitch: 0.95,
    hp: 110, range: 40, react: 1.0, interval: [2.1, 3.0], acc: [0.5, 0.2], head: 0.12,
    dmg: 40, headMult: 2.5, rest: 5, pic: 'schofield',
    stats: { Aim: 0.45, Speed: 0.55, Grit: 0.45 },
  },
};
export const HIRE_LIST = Object.values(HIRES);
export const hireFee = (ids) => ids.reduce((t, id) => t + (HIRES[id]?.price || 0), 0);

// ?hire=bill,gun,gun -> ['bill', 'rifle', 'pistol']
export function parseHires(q) {
  const out = [];
  for (const w of (q || '').split(',')) {
    const id = w === 'gun' ? (out.includes('rifle') ? 'pistol' : 'rifle') : w;
    if (HIRES[id] && !out.includes(id)) out.push(id);
  }
  return out;
}

const BILL_LINES = ['"That\'s one."', '"Next."', '"Stay down, friend."', '"Another for the undertaker."', '"Too slow."', '"Keep her rolling!"', '"He drew first."'];
const has = (v) => (Chars.RIDER_VARIANTS ? Chars.RIDER_VARIANTS.includes(v) : false);

// how far off the crown an escort may ride here: tight on ledges, the
// trestle and in town, so he never rides into a wall, off a drop or through a store
function laneLimit(R, s) {
  let m = 9;
  if (R.biome === 'mountain') m = ROAD_HALF + 0.5;
  else if (R.biome === 'gorge') m = ROAD_HALF + 2;
  // the trestle's railing posts stand at ±3.45 m (gorgebridge.js)
  if (R.bridge && s > R.bridge.s0 - 14 && s < R.bridge.s1 + 14) m = Math.min(m, Math.min(3.45, R.bridge.width * 0.5) - 0.65);
  const T = R.townRange;
  // town: barrels, troughs and wrecks start 6.8 m out, the fronts at 9.5
  if (s < 150 || s > R.len - 160 || (T && s > T.s0 - 30 && s < T.s1 + 30)) m = Math.min(m, 4.8);
  return m;
}

class Escort {
  constructor(game, cfg, slot) {
    this.g = game; this.cfg = cfg;
    const R = game.route, coach = game.coach;
    this.horse = createHorse({ breed: cfg.breed || null, coat: new THREE.Color(...cfg.coat), saddle: true, harness: false });
    const variant = has(cfg.variant) ? cfg.variant : cfg.fallback;
    this.man = createRider({ variant, tint: has(cfg.variant) ? null : new THREE.Color(...cfg.tint) });
    this.horse.mount.add(this.man.root);
    this.man.play('Ride');
    this.guns = [];
    // GLTFLoader strips the dot: hand.L arrives as handL
    const hands = [this.man.hand, this.man.node?.('handL') || this.man.node?.('hand.L')];
    for (let i = 0; i < cfg.guns && hands[i]; i++) {
      const w = createWeapon(cfg.gun, { finish: cfg.finish });
      hands[i].add(w.root);
      this.guns.push(w);
    }
    game.scene.add(this.horse.root);
    this.hp = cfg.hp; this.alive = true;
    this.home = { ds: slot[0], d: slot[1] * 3.6 };
    this.wantDs = this.home.ds; this.wantD = this.home.d;
    this.s = Math.max(1, coach.s + this.home.ds); this.d = this.home.d; this.speed = coach.speed;
    this.side = Math.sign(this.home.d) || 1;
    this.pos = new THREE.Vector3(); this.heading = 0;
    this.state = 'ride';
    this.target = null; this.part = 'body';
    this.fireT = 1 + Math.random(); this.reactT = 0; this.scanT = Math.random() * 0.25; this.restT = 0;
    this.blockT = 0; this.shot = 0; this.kills = 0; this.engagedT = 0;
    this.chest = new THREE.Vector3(); this.headP = new THREE.Vector3(); this._m = new THREE.Vector3();
    this.neighT = 10 + Math.random() * 15;
    this.update(0);
  }

  get tag() { return this.cfg.tag; }

  update(dt) {
    const g = this.g, R = g.route, coach = g.coach;
    this.horse.update(dt);
    if (this.state === 'ride') {
      this._think(dt);
      const err = coach.s + this.wantDs - this.s;
      let tSpeed = coach.speed + clamp(err * 0.7, -7, 9);
      if (coach.speed < 0.5 && Math.abs(err) < 2.5) tSpeed = 0;
      this.speed = Math.max(0, damp(this.speed, tSpeed, 1.6, dt));
      const prevD = this.d;
      // lane: limited by the ground here; out in the open, pulled in further if
      // something solid (the rail camp's tower and stacks) sits just ahead. Town
      // boxes are world-aligned and spill into the street, so towns use the clamp.
      let lim = laneLimit(R, this.s + 4);
      const sd = Math.sign(this.wantD || this.side);
      while (lim > 4.8 && this._solidAt(this.s + 5, sd * Math.min(Math.abs(this.wantD), lim))) lim -= 1;
      const want = clamp(this.wantD, -lim, lim);
      this.d += clamp(want - this.d, -3.6 * dt, 3.6 * dt);
      this.d = clamp(this.d, -lim - 0.3, lim + 0.3);
      // never ride through the coach or the team
      const ds = this.s - coach.s;
      const clear = Math.min(lim, R.biome === 'mountain' || lim < 4 ? 2.7 : 3.2);
      if (ds > -4.5 && ds < coach.teamFront + 1.5 && Math.abs(this.d) < clear) this.d = Math.sign(this.d || this.side) * clear;
      if (ds > -14 && ds < -4.5 && Math.abs(this.d) < clear && Math.abs(want) >= clear) this.d += Math.sign(want) * 2 * dt;
      this.s = Math.max(1, this.s + this.speed * dt);
      this._place(dt, prevD);
      this.g.fx.trail(this.pos, this.speed > 6 ? 7 : 0, dt, 0.7);
      this.neighT -= dt;
      if (this.neighT < 0) { this.neighT = 14 + Math.random() * 18; audio.play('horse_neigh', { position: this.pos, volume: 0.4 }); }
    } else if (this.state === 'riderless') {
      // the horse runs on, drifts to the edge of the lane and pulls up
      this.speed = damp(this.speed, 0, 0.35, dt);
      const lim = laneLimit(R, this.s);
      this.d = clamp(this.d + this.side * 2 * dt, -lim, lim);
      this.s += this.speed * dt;
      R.worldAt(this.s, this.d, this.pos);
      this.horse.root.position.copy(this.pos);
      const f = R.frame(this.s, {});
      this.horse.root.rotation.set(0, Math.atan2(f.tx, f.tz) + this.side * 0.3, 0, 'YXZ');
      this.horse.setSpeed(Math.max(0.4, Math.min(1.2, 0.5 + this.speed / 20)));
    }
    if (this.thrown) this._fall(dt);
    this.man.update(dt);
    if (this.state === 'ride') this._pose();
    this._points();
  }

  _place(dt, prevD) {
    const R = this.g.route;
    R.worldAt(this.s, this.d, this.pos);
    const f = R.frame(this.s, {});
    const lat = dt > 0 ? (this.d - prevD) / Math.max(0.5, this.speed * dt) : 0;
    this.heading = Math.atan2(f.tx, f.tz) - Math.atan(lat) * 0.8;
    const ahead = R.worldAt(this.s + 1.5, this.d, _v);
    this.horse.root.position.copy(this.pos);
    this.horse.root.rotation.set(-Math.atan2(ahead.y - this.pos.y, 1.5), this.heading, clamp(-lat * 2, -0.25, 0.25), 'YXZ');
    const v = this.speed, gait = v < 2 ? 'Idle' : v < 10 ? 'Canter' : 'Gallop';
    if (this.horse.has(gait)) this.horse.play(gait);
    this.horse.setSpeed(gait === 'Gallop' ? Math.min(1.32, 0.75 + v / 30) : gait === 'Canter' ? Math.min(1.3, Math.max(0.5, v / 7)) : 1);
  }

  _solidAt(s, d) {
    const p = this.g.route.worldAt(s, d, _v3); p.y += 1.2;
    for (const b of this.g.towns.solids) {
      if (p.x > b.min.x - 1.2 && p.x < b.max.x + 1.2 && p.z > b.min.z - 1.2 && p.z < b.max.z + 1.2 && p.y > b.min.y - 1 && p.y < b.max.y + 1) return true;
    }
    return false;
  }

  // ---------------------------------------------------------------- brains
  _think(dt) {
    const g = this.g, coach = g.coach, cfg = this.cfg, E = g.escorts;
    this.fireT -= dt; this.reactT -= dt; this.restT -= dt; this.scanT -= dt;
    const t = this.target;
    if (t && (!t.alive || (t.type === 'rider' && t.state !== 'ride'))) this.target = null;
    if (this.scanT <= 0) {
      this.scanT = 0.25;
      if (this.restT <= 0 && !g.over) {
        const pick = this._pick();
        if (pick && pick !== this.target) { this.target = pick; this.reactT = cfg.react * (0.8 + Math.random() * 0.4); this.engagedT = 0; }
        else if (!pick) this.target = null;
      } else this.target = null;
    }
    const tg = this.target;
    // where to ride: home slot, or level with the man he's after (never out
    // ahead of the team, never far behind)
    if (tg && tg.s !== undefined) {
      this.engagedT += dt;
      const ds = tg.s - coach.s;
      const tSide = Math.sign(tg.d ?? this.side) || this.side;
      if (this.blockT > 1.2) { this.wantDs = -11; this.wantD = this.side * 2.6; }   // the coach is in the way: drop back for an angle
      else if (tSide === this.side) { this.wantDs = clamp(ds - 3, -24, 6); this.wantD = this.side * clamp(Math.abs(tg.d ?? 6) - 3, 3.4, 8); }
      else { this.wantDs = clamp(ds - 4, -22, -6); this.wantD = this.side * 2.8; }
    } else { this.wantDs = this.home.ds; this.wantD = this.home.d; }
    if (!tg) { this.blockT = 0; return; }
    // fire
    const aim = this._aimPoint(tg);
    const muzzle = this._muzzle(this._m);
    // line of fire, a few times a second; checked again at the trigger
    this.losT = (this.losT || 0) - dt;
    if (this.losT <= 0) { this.losT = 0.15; this.clear = this._clearShot(muzzle, aim); this.blockT = this.clear ? 0 : this.blockT + 0.15; }
    if (!this.clear || this.reactT > 0 || this.fireT > 0) return;
    if (g.player.hover?.enemy === tg && !((tg.atTeam || 0) > 0.3)) return;   // the boss has him in his sights
    const gun = this.guns[this.shot % this.guns.length];
    const from = gun ? gun.muzzle.getWorldPosition(new THREE.Vector3()) : muzzle.clone();
    if (!this._clearShot(from, aim)) { this.clear = false; return; }
    const dist = muzzle.distanceTo(aim);
    const ahead = E.ahead;
    const pairShot = cfg.guns > 1 && this.shot % 2 === 0;
    this.fireT = pairShot ? cfg.pair : (cfg.interval[0] + Math.random() * (cfg.interval[1] - cfg.interval[0])) * (ahead ? 3 : 1);
    let chance = cfg.acc[0] + (cfg.acc[1] - cfg.acc[0]) * clamp(dist / cfg.range, 0, 1);
    if (coach.speed > coach.cruise + 3) chance *= 0.85;
    if (ahead) chance *= 0.5;
    this.shot++;
    const killed = g.combat.escortShot(this, from, aim.clone(), tg, this.part, Math.random() < chance);
    if (gun && gun === this.guns[1] && this.man.kickL) this.man.kickL(); else this.man.kick?.();
    if (killed) this._onKill();
  }

  // the best target he may take: a rider on the coach's flanks or tail, in
  // range and in sight, that the player has had a fair crack at first
  _pick() {
    const g = this.g, E = g.escorts, coach = g.coach, cfg = this.cfg;
    const mine = this._muzzle(this._m);
    const playerOn = g.player.hover?.enemy;
    let best = null, bestScore = Infinity;
    for (const e of g.enemies.list) {
      if (!e.alive || (e.type === 'rider' && e.state !== 'ride')) continue;
      e._seen ??= g.time;
      const c = e.spheres[1].c;
      const dist = c.distanceTo(mine);
      if (dist > cfg.range) continue;
      // a rider at the team or right on top of him is fair game straight away
      const urgent = (e.atTeam || 0) > 0.3 || dist < 6;
      if (!urgent && (g.time - e._seen < PLAYER_PRIORITY * (E.ahead ? 2.5 : 1) || e === playerOn)) continue;
      if (e.type !== 'rider' && !cfg.rifle && dist > 30) continue;      // pistols leave the ridges to you
      const taken = E.list.some((o) => o !== this && o.alive && o.target === e);
      const score = dist + (taken ? 30 : 0) - (urgent ? 25 : 0) + (e.type === 'rider' ? 0 : 10) - (e === this.target ? 6 : 0);
      if (score >= bestScore) continue;
      if (!this._sees(mine, c)) continue;
      best = e; bestScore = score;
    }
    if (best && best !== this.target) this.part = best.spheres.some((q) => q.part === 'head') && Math.random() < cfg.head ? 'head' : 'body';
    return best;
  }

  _aimPoint(e) { const s = e.spheres.find((q) => q.part === this.part) || e.spheres[1] || e.spheres[0]; return s.c; }

  _muzzle(out) { return (this.guns[0] ? this.guns[0].muzzle.getWorldPosition(out) : out.copy(this.chest)); }

  _sees(from, to) {
    const g = this.g;
    const dv = _v3.subVectors(to, from); const L = dv.length(); dv.divideScalar(L);
    if (g.terrain.raycast(from, dv, L) < L - 1.5) return false;
    _ray.set(from, dv);
    for (const b of g.towns.solids) { if (b.containsPoint(from)) continue; const p = _ray.intersectBox(b, _v); if (p && p.distanceTo(from) < L - 1) return false; }
    if (g.crossing?.train.rayHit?.(from, dv, L)) return false;
    return true;
  }

  // Hard rule: no shot whose line comes near the coach, the team, the player or
  // another escort. A bullet that misses carries on past the target, so the
  // line is checked a few metres beyond it too.
  _clearShot(from, to) {
    const g = this.g, c = g.coach;
    if (!this._sees(from, to)) return false;
    const end = _v2.subVectors(to, from).setLength(8).add(to);
    _line.set(from, end);
    const near = (p, r) => _line.closestPointToPoint(p, true, _v3).distanceToSquared(p) < r * r;
    for (const k of [-2.6, -0.8, 1.0, 2.6]) { if (near(_v.copy(c.pos).addScaledVector(c.fwd, k).setY(c.pos.y + 1.7), 2.1)) return false; }
    for (const h of c.team) { if (near(_v.copy(h.root.position).setY(h.root.position.y + 1.3), 1.5)) return false; }
    if (near(g.player.headPos, 1.4)) return false;
    for (const o of g.escorts.list) { if (o !== this && o.alive && near(o.chest, 1.3)) return false; }
    return true;
  }

  _onKill() {
    const g = this.g, cfg = this.cfg;
    this.kills++;
    this.restT = cfg.rest * (this.g.escorts.ahead ? 1.6 : 1);   // calls it, reloads, gives you the next one
    this.target = null;
    this.fireT = Math.max(this.fireT, cfg.react);
  }

  _pose() {
    const tg = this.target, m = this.man, two = this.guns.length > 1;
    // Hickok: Navies in the sash in formation, both out when he fires, the left
    // one alone for a target off his left side
    let clip = 'Ride', hand = m.hand;
    if (tg) {
      clip = 'RideAim';
      if (two) {
        const lx = this.horse.root.worldToLocal(_v.copy(this._aimPoint(tg))).normalize().x;
        if (lx > 0.55 && m.has('RideAimL') && m.handL) { clip = 'RideAimL'; hand = m.handL; } else if (m.has('RideAimDual')) clip = 'RideAimDual';
      }
    } else if (two && m.has('RideHolstered')) clip = 'RideHolstered';
    if (m.has(clip)) m.play(clip, { fade: 0.3 });
    this.aimHand = hand;
    if (two) {
      const drawn = clip !== 'RideHolstered';
      this.guns.forEach((g) => { g.root.visible = drawn; });
      const sash = m.node?.('Colts_Hickok'); if (sash) sash.visible = !drawn;
    }
    if (tg && m.kind === 'glb' && m.bones.chest) {
      const hp = hand.getWorldPosition(_v3);
      aimBone(m.bones.chest, hand, _v2.subVectors(this._aimPoint(tg), hp).normalize(), 0.9);
    }
  }

  _points() {
    const b = this.man.bones;
    if (b.head) b.head.getWorldPosition(this.headP); else this.man.root.localToWorld(this.headP.set(0, 1.0, 0));
    if (b.chest) b.chest.getWorldPosition(this.chest); else this.man.root.localToWorld(this.chest.set(0, 0.5, 0));
    if (this.thrown) { this.chest.copy(this.thrown.o.position); this.headP.copy(this.chest); }
  }

  // ---------------------------------------------------------------- hits
  damage(amount, from) {
    if (!this.alive || this.g.over) return;
    this.hp -= amount;
    this.hitT = this.g.time;
    if (this.hp > 0) return;
    const g = this.g;
    this.alive = false;
    this.state = 'riderless';
    this.target = null;
    const dir = _v.subVectors(this.chest, from).setY(0).normalize();
    this._throw(new THREE.Vector3(Math.sin(this.heading), 0, Math.cos(this.heading)).multiplyScalar(this.speed * 0.8).addScaledVector(dir, 3).add(_v2.set(0, 2.5, 0)));
    audio.play('horse_neigh', { position: this.pos, volume: 0.8, pitch: 1.1 });
    if (this.cfg.id === 'bill') g.hud.banner('Wild Bill is down!', "You're on your own on the right", 2.2);
    else g.hud.feedMsg('Your hired gun is down', false);
    this.removeAt = g.time + 25;
  }

  _throw(vel) {
    const o = this.man.root;
    const wp = o.getWorldPosition(new THREE.Vector3());
    const wq = o.getWorldQuaternion(new THREE.Quaternion());
    this.g.scene.add(o);
    o.position.copy(wp); o.quaternion.copy(wq);
    const animated = this.man.kind === 'glb' && this.man.has('FallOff');
    this.man.play(animated ? 'FallOff' : 'Ride', { once: true, fade: 0.08 });
    o.rotation.set(0, this.heading, 0);
    const seatH = wp.y - this.g.route.height(wp.x, wp.z);
    this.thrown = { o, vel, landed: false, seatH, age: 0 };
  }

  _fall(dt) {
    const t = this.thrown, R = this.g.route;
    // the FallOff clip carries the drop; we only add the momentum, bleeding off fast
    t.vel.multiplyScalar(Math.exp(-2.2 * dt));
    t.o.position.x += t.vel.x * dt; t.o.position.z += t.vel.z * dt;
    t.o.position.y = R.height(t.o.position.x, t.o.position.z) + t.seatH;
    if (!t.landed && t.age > 0.9) { t.landed = true; this.g.fx.dust(_v.copy(t.o.position).setY(t.o.position.y - t.seatH), { amount: 8, size: 0.6 }); }
    t.age += dt;
  }

  dispose() { this.g.scene.remove(this.horse.root); if (this.thrown) this.g.scene.remove(this.thrown.o); }
}

// ------------------------------------------------------------------ manager
export class Escorts {
  constructor(game, ids = []) {
    this.g = game;
    this.ids = ids;
    this.kills = 0; this.bounty = 0;
    // Bill always takes the right; the first hired gun the left, the second the rear quarter
    let hired = 0;
    this.list = ids.map((id) => {
      const cfg = HIRES[id];
      const slot = cfg.id === 'bill' ? cfg.slot : hired++ === 0 ? [1, -1] : [-9, -0.75];
      return new Escort(game, cfg, slot);
    });
    if (this.list.length) game.hud.feedMsg(this.list.length > 1 ? `${this.list.length} guns ride with you` : `${this.list[0].cfg.name} rides with you`, false);
  }

  get alive() { return this.list.filter((e) => e.alive); }

  // they aren't here to win the fight for you: once the hired men are
  // out-scoring the player they slow right down and leave more to him
  get ahead() { return this.kills > this.g.player.stats.kills * 0.8 + 2; }

  // back into formation round the coach (debug jumps)
  snap() { const c = this.g.coach; for (const e of this.list) { e.s = Math.max(1, c.s + e.home.ds); e.d = e.home.d; e.speed = c.speed; } }

  update(dt) {
    for (const e of this.list) e.update(dt);
    for (let i = this.list.length - 1; i >= 0; i--) {
      const e = this.list[i];
      if (!e.alive && (this.g.time > e.removeAt || e.s < this.g.coach.s - 160)) { e.dispose(); this.list.splice(i, 1); }
    }
  }

  // a kill by one of ours: half the bounty to the player, Bill says something
  credit(esc, bounty, head) {
    const g = this.g;
    const pay = Math.round(bounty * ESCORT_CUT);
    this.kills++; this.bounty += pay;
    const line = esc.cfg.id === 'bill' ? `${BILL_LINES[Math.floor(Math.random() * BILL_LINES.length)]} Wild Bill` : head ? 'Hired gun, headshot' : 'Hired gun';
    g.addBounty(pay, `${line} +$${pay}`, false);
  }

  // an enemy about to fire may pick one of us instead of the coach: only an
  // escort nearer to him than the player is, and not every time
  pickTarget(enemy, muzzle, rifle) {
    const g = this.g;
    let best = null, bestD = rifle ? 160 : 45;
    const toPlayer = muzzle.distanceTo(g.player.headPos);
    for (const e of this.list) {
      if (!e.alive) continue;
      const d = muzzle.distanceTo(e.chest);
      if (d < bestD && d < toPlayer + 4) { best = e; bestD = d; }
    }
    return best && Math.random() < (best.cfg.id === 'bill' ? 0.35 : 0.3) ? best : null;
  }

  dispose() { this.list.forEach((e) => e.dispose()); this.list = []; }
}
