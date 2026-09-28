// Enemies: mounted riders (chase/flank/ambush, ride alongside and shoot, go for
// the team), ridge riflemen (lens glint telegraph), and ghost-town gunmen.
// Riders live in road space (s, d) so they follow any winding road.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { createHorse, createRider, createWeapon, rotateBoneWorld, aimBone } from './characters.js';
import { ROAD_HALF } from '../world/route.js';
import { clamp, damp, lerp } from '../core/noise.js';

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _q = new THREE.Quaternion(), _ray = new THREE.Ray();
const COATS = [new THREE.Color(1, 1, 1), new THREE.Color(0.5, 0.38, 0.3), new THREE.Color(0.3, 0.25, 0.22), new THREE.Color(1.3, 1.2, 1.1), new THREE.Color(0.95, 0.7, 0.5)];
const VARIANTS = ['bandit', 'bandit2', 'bandit3'];
const CLOTH = [new THREE.Color(1, 1, 1), new THREE.Color(0.8, 0.7, 0.6), new THREE.Color(0.6, 0.65, 0.75), new THREE.Color(1.1, 0.9, 0.7)];

let _id = 0;

class Enemy {
  constructor(game) { this.g = game; this.id = ++_id; this.alive = true; this.dead = false; this.removeAt = Infinity; this.spheres = []; }
  hitPoint(part) { const s = this.spheres.find((q) => q.part === part) || this.spheres[0]; return s.c.clone(); }
}

// -------------------------------------------------------------------- rider
class Rider extends Enemy {
  constructor(game, opts) {
    super(game);
    this.type = 'rider';
    const R = game.route, coach = game.coach;
    this.horse = createHorse({ coat: COATS[Math.floor(Math.random() * COATS.length)], saddle: true });
    this.man = createRider({ variant: VARIANTS[Math.floor(Math.random() * VARIANTS.length)], tint: CLOTH[Math.floor(Math.random() * CLOTH.length)] });
    this.horse.mount.add(this.man.root);
    this.man.play('Ride');
    this.gun = createWeapon('Schofield');
    this.man.hand.add(this.gun.root);
    game.scene.add(this.horse.root);
    this.horseHp = 110; this.hp = 100;
    this.side = opts.side ?? (Math.random() < 0.5 ? -1 : 1);
    const narrow = R.biome === 'mountain';
    this.maxD = narrow ? ROAD_HALF + 0.5 : 14;
    switch (opts.from) {
      case 'ahead': this.s = coach.s + 110 + Math.random() * 60; this.d = this.side * (narrow ? 3 : 9 + Math.random() * 6); this.speed = coach.speed * 0.4; break;
      case 'flank': this.s = coach.s - 10 - Math.random() * 25; this.d = this.side * (narrow ? 4 : 30 + Math.random() * 15); this.speed = coach.speed + 2; break;
      default: this.s = coach.s - 55 - Math.random() * 40; this.d = this.side * (2 + Math.random() * 4); this.speed = coach.speed + 4;
    }
    this.slot = opts.slot ?? 0;
    this.targetDs = narrow ? -7 - this.slot * 4 : [-5, -1, 3, -9, 6, -12][this.slot % 6] + (Math.random() - 0.5) * 2;
    this.targetD = this.side * (narrow ? (this.targetDs > -4 ? 4.2 : 2.2) : 5.5 + Math.random() * 3);
    this.fireT = 2 + Math.random() * 2;
    this.aggro = 0; this.atTeam = 0;
    this.pos = new THREE.Vector3(); this.vel = new THREE.Vector3(); this.heading = 0;
    this.state = 'ride';
    this.reposT = 6 + Math.random() * 6;
    this.spheres = [{ part: 'head', c: new THREE.Vector3(), r: 0.17 }, { part: 'body', c: new THREE.Vector3(), r: 0.34 }, { part: 'horse', c: new THREE.Vector3(), r: 0.75 }, { part: 'horse', c: new THREE.Vector3(), r: 0.4 }];
    this.dustAcc = 0;
    this.neighT = Math.random() * 10;
    this.update(0);
  }

  update(dt) {
    const g = this.g, R = g.route, coach = g.coach;
    this.horse.update(dt);
    if (this.state === 'ride' || this.state === 'fleeing') {
      if (this.state === 'ride') {
        // reposition occasionally so they don't feel on rails
        this.reposT -= dt;
        if (this.reposT < 0) {
          this.reposT = 5 + Math.random() * 6;
          const narrow = R.biome === 'mountain';
          if (!narrow) { this.targetDs = -12 + Math.random() * 18; this.targetD = this.side * (5 + Math.random() * 4); }
          if (!narrow && Math.random() < 0.2) { this.side *= -1; this.targetD *= -1; }
        }
        const want = coach.s + this.targetDs;
        const err = want - this.s;
        const tSpeed = coach.speed + clamp(err * 0.6, -6, 9);
        this.speed = damp(this.speed, tSpeed, 1.2, dt);
      } else {
        this.speed = damp(this.speed, 6, 0.5, dt);
        this.targetD = this.side * 30;
      }
      const prevD = this.d;
      const maxLat = 3.2;
      this.d += clamp(this.targetD - this.d, -maxLat * dt, maxLat * dt);
      if (this.state === 'ride') this.d = clamp(this.d, -this.maxD, this.maxD);
      // don't ride through the coach/team
      const ds = this.s - coach.s;
      const clear = R.biome === 'mountain' ? 2.6 : 3.2;
      if (ds > -4 && ds < 9.5 && Math.abs(this.d) < clear) this.d = Math.sign(this.d || this.side) * clear;
      // swing wide before overtaking
      if (ds > -14 && ds < -4 && Math.abs(this.d) < clear && Math.abs(this.targetD) >= clear) this.d += Math.sign(this.targetD) * 2 * dt;
      this.s += this.speed * dt;
      R.worldAt(this.s, this.d, this.pos);
      const f = R.frame(this.s, {});
      const lat = dt > 0 ? (this.d - prevD) / Math.max(0.5, this.speed * dt) : 0;
      this.heading = Math.atan2(f.tx, f.tz) - Math.atan(lat) * 0.8;
      const ahead = R.worldAt(this.s + 1.5, this.d, _v);
      this.horse.root.position.copy(this.pos);
      this.horse.root.rotation.set(-Math.atan2(ahead.y - this.pos.y, 1.5), this.heading, clamp(-lat * 2, -0.25, 0.25), 'YXZ');
      this.horse.setSpeed(Math.min(1.32, 0.75 + this.speed / 30));
      // dust
      this.g.fx.trail(this.pos, this.speed > 6 ? 7 : 0, dt, 0.7);

      if (this.state === 'ride') this._combat(dt);
      if (this.state === 'fleeing' && (Math.abs(this.d) > 28 || this.s < coach.s - 120)) this.removeAt = 0;
    } else if (this.state === 'riderless' || this.state === 'horsedown') {
      // horse keeps going / lies in the world; road-space advance then stop
      if (this.state === 'riderless') {
        this.speed = damp(this.speed, 5, 0.4, dt);
        this.d += this.side * 3 * dt;
        this.s += this.speed * dt;
        R.worldAt(this.s, this.d, this.pos);
        this.horse.root.position.copy(this.pos);
        const f = R.frame(this.s, {});
        this.horse.root.rotation.set(0, Math.atan2(f.tx, f.tz) + this.side * 0.5, 0, 'YXZ');
      } else {
        this.speed = damp(this.speed, 0, 2.5, dt);
        this.s += this.speed * dt;
        R.worldAt(this.s, this.d, this.pos);
        this.horse.root.position.copy(this.pos);
      }
    }
    // thrown rider (ragdoll-ish: ballistic with spin, then lies on the ground)
    if (this.thrown) {
      const t = this.thrown;
      if (t.animated) {
        // the FallOff clip carries the drop; we only add the momentum, bleeding off fast
        t.vel.multiplyScalar(Math.exp(-2.2 * dt));
        t.o.position.x += t.vel.x * dt; t.o.position.z += t.vel.z * dt;
        t.o.position.y = R.height(t.o.position.x, t.o.position.z) + t.seatH;
        if (!t.landed && t.age > 0.9) { t.landed = true; g.fx.dust(_v.copy(t.o.position).setY(t.o.position.y - t.seatH), { amount: 8, size: 0.6 }); }
        t.age += dt;
      } else if (!t.landed) {
        t.vel.y -= 16 * dt;
        t.o.position.addScaledVector(t.vel, dt);
        t.o.rotation.x += t.spin.x * dt; t.o.rotation.z += t.spin.z * dt;
        const gh = R.height(t.o.position.x, t.o.position.z);
        if (t.o.position.y < gh + 0.15) {
          t.o.position.y = gh + 0.15;
          if (Math.abs(t.vel.y) > 3) { t.vel.y *= -0.25; t.vel.x *= 0.4; t.vel.z *= 0.4; t.spin.multiplyScalar(0.3); g.fx.dust(t.o.position, { amount: 6, size: 0.5 }); }
          else { t.landed = true; t.o.rotation.x = -Math.PI / 2 * (Math.random() < 0.5 ? 1 : -1) * 0.95; t.o.rotation.z = 0; }
        }
      }
      this.man.update(dt);
    } else {
      this.man.update(dt);
      if (this.state === 'ride') this._aimPose();
    }
    this._spheres();
    if (!this.alive && this.removeAt === Infinity && this.s < coach.s - 140) this.removeAt = 0;
  }

  _aimPose() {
    const g = this.g;
    const ds = this.s - g.coach.s;
    const wantAim = this.aggro > 0.2 && ds > -40;
    const clip = wantAim ? 'RideAim' : 'Ride';
    if (this.man.has(clip)) this.man.play(clip, { fade: 0.3 });
    if (wantAim && this.man.bones.chest) {
      // twist toward the player
      const target = g.player.headPos;
      const chest = this.man.bones.chest.getWorldPosition(_v);
      const dir = _v2.subVectors(target, chest);
      const want = Math.atan2(dir.x, dir.z);
      if (this.man.kind === 'glb') {
        const hp = this.man.hand.getWorldPosition(_v3);
        aimBone(this.man.bones.chest, this.man.hand, _v2.subVectors(target, hp).normalize(), 0.9);
      } else {
        let rel = want - this.heading;
        while (rel > Math.PI) rel -= Math.PI * 2; while (rel < -Math.PI) rel += Math.PI * 2;
        this.man.bones.chest.rotation.y = clamp(rel, -1.6, 1.6);
      }
    }
  }

  _combat(dt) {
    const g = this.g, coach = g.coach;
    const ds = this.s - coach.s;
    const dist = this.pos.distanceTo(coach.pos);
    this.aggro = clamp(this.aggro + dt * (dist < 45 ? 0.6 : -0.3), 0, 1);
    this.fireT -= dt;
    if (this.fireT <= 0 && dist < 42 && this.aggro > 0.5) {
      this.fireT = (1.5 + Math.random() * 1.8) * g.diff.fireMult;
      const muzzle = this.gun.muzzle.getWorldPosition(new THREE.Vector3());
      g.combat.enemyShot(this, muzzle, { dist, acc: g.diff.riderAcc, dmgPlayer: 7 + Math.random() * 4, dmgCoach: 4 + Math.random() * 3 });
    }
    // reaching the team
    if (ds > 4 && ds < 12 && Math.abs(this.d) < 5) {
      this.atTeam += dt;
      if (this.atTeam > 1 && !this._warned) { this._warned = true; g.hud.banner("They're going for the team!", '', 1.5); }
      if (this.atTeam > 5) { this.atTeam = 0; this._warned = false; coach.hp -= 12; g.onCoachDamage(); this.targetDs = -6; }
    } else this.atTeam = Math.max(0, this.atTeam - dt);
    // riders who've been in the fight a long time peel away
    this.life = (this.life || 0) + dt;
    if (this.life > 45 && this.aggro > 0.5 && Math.random() < dt * 0.1) { this.state = 'fleeing'; this.side = Math.sign(this.d) || 1; }
    // neigh
    this.neighT -= dt;
    if (this.neighT < 0) { this.neighT = 12 + Math.random() * 15; audio.play('horse_neigh', { position: this.pos, volume: 0.5 }); }
  }

  _spheres() {
    const [head, body, horse, neck] = this.spheres;
    if (this.man.bones.head) this.man.bones.head.getWorldPosition(head.c).add(_v.set(0, 0.06, 0));
    else this.man.root.localToWorld(head.c.set(0, 1.0, 0));
    if (this.man.bones.chest) this.man.bones.chest.getWorldPosition(body.c);
    else this.man.root.localToWorld(body.c.set(0, 0.5, 0));
    if (this.thrown) { head.c.copy(this.thrown.o.position).add(_v.set(0, 0.2, 0)); body.c.copy(this.thrown.o.position); }
    this.horse.root.localToWorld(horse.c.set(0, 1.25, 0));
    this.horse.root.localToWorld(neck.c.set(0, 1.6, 1.05));
    if (this.state === 'horsedown') { horse.c.y -= 0.7; neck.c.y -= 1; }
  }

  // returns true if this hit killed the enemy
  damage(amount, part, dir) {
    if (!this.alive) return false;
    const g = this.g;
    if (part === 'horse') {
      this.horseHp -= amount;
      if (this.horseHp <= 0) {
        this.state = 'horsedown';
        this.horse.play('Fall', { once: true, fade: 0.1 });
        audio.play('horse_neigh', { position: this.pos, volume: 0.9, pitch: 0.9 });
        g.fx.dust(this.pos, { amount: 16, size: 1.1, up: 2.5, spread: 4 });
        this._throw(new THREE.Vector3().copy(this._fwdVec()).multiplyScalar(this.speed * 0.9).add(new THREE.Vector3(0, 4, 0)));
        return true;
      }
      return false;
    }
    this.hp -= amount;
    if (this.hp <= 0) {
      this.state = 'riderless';
      const push = dir.clone().multiplyScalar(g.player.weapon.knock ? 7 : 3);
      this._throw(this._fwdVec().multiplyScalar(this.speed * 0.8).add(push).add(new THREE.Vector3(0, 2.5, 0)));
      return true;
    }
    return false;
  }

  _fwdVec() { return new THREE.Vector3(Math.sin(this.heading), 0, Math.cos(this.heading)); }

  _throw(vel) {
    this.alive = false;
    const o = this.man.root;
    const wp = o.getWorldPosition(new THREE.Vector3());
    const wq = o.getWorldQuaternion(new THREE.Quaternion());
    this.g.scene.add(o);
    o.position.copy(wp); o.quaternion.copy(wq);
    o.rotation.setFromQuaternion(wq, 'YXZ');
    const animated = this.man.kind === 'glb' && this.man.has('FallOff');
    this.man.play(animated ? 'FallOff' : 'Ride', { once: true, fade: 0.08 });
    const seatH = wp.y - this.g.route.height(wp.x, wp.z);
    if (animated) o.rotation.set(0, this.heading, 0);
    this.thrown = { o, vel, spin: new THREE.Vector3(-3 - Math.random() * 3, 0, (Math.random() - 0.5) * 4), landed: false, animated, seatH, age: 0 };
  }

  dispose() { this.g.scene.remove(this.horse.root); if (this.thrown) this.g.scene.remove(this.thrown.o); }
}

// ------------------------------------------------------------ static gunman
class Gunman extends Enemy {
  constructor(game, pos, face, { rifle = true, popup = false } = {}) {
    super(game);
    this.type = rifle ? 'rifleman' : 'gunman';
    this.man = createRider({ variant: 'gunman', tint: CLOTH[Math.floor(Math.random() * CLOTH.length)] });
    this.gun = createWeapon(rifle ? 'Winchester' : 'Schofield');
    this.man.hand.add(this.gun.root);
    this.root = this.man.root;
    this.base = pos.clone();
    this.root.position.copy(pos);
    this.root.rotation.y = Math.atan2(face.x, face.z);
    game.scene.add(this.root);
    this.man.play(this.man.has('StandShoot') ? 'StandShoot' : 'StandIdle');
    this.hp = 100;
    this.rifle = rifle;
    this.fireT = (rifle ? 3 : 2) + Math.random() * 2;
    this.glintT = -1;
    this.popup = popup; this.pop = popup ? 0 : 1;
    this.spheres = [{ part: 'head', c: new THREE.Vector3(), r: 0.17 }, { part: 'body', c: new THREE.Vector3(), r: 0.36 }];
    this.update(0);
  }

  update(dt) {
    const g = this.g, coach = g.coach;
    this.man.update(dt);
    if (this.alive) {
      // face the coach
      const dir = _v.subVectors(coach.pos, this.root.position);
      this.root.rotation.y = damp(this.root.rotation.y, Math.atan2(dir.x, dir.z), 4, dt); // StandShoot aims straight ahead
      if (this.popup) {
        this.pop = Math.min(1, this.pop + dt * 2.5);
        this.root.position.copy(this.base).add(_v2.set(0, (this.pop - 1) * 1.2, 0));
      }
      const dist = dir.length();
      const range = this.rifle ? 190 : 70;
      // line of sight to the coach (throttled)
      this.losT = (this.losT || 0) - dt;
      if (this.losT <= 0 && dist < range) {
        this.losT = 0.25;
        // from the chest: if he can shoot you, his body is exposed to shoot back
        const from = this.spheres[1].c, to = _v2.copy(g.player.headPos);
        const dv = _v3.subVectors(to, from); const L = dv.length(); dv.divideScalar(L);
        let clear = g.terrain.raycast(from, dv, L - 2) >= L - 2.5;
        if (clear) {
          _ray.set(from, dv);
          for (const b of g.towns.solids) { if (b.containsPoint(from)) continue; const p = _ray.intersectBox(b, _v); if (p && p.distanceTo(from) < L - 2) { clear = false; break; } }
        }
        this.los = clear;
      }
      if (dist < range && this.los) {
        this.fireT -= dt;
        // telegraph: lens glint for riflemen, a brief glint + hammer cock for pistols
        if (this.fireT < 1.5 && this.fireT + dt >= 1.5 && this.rifle) this.glintT = 1.5;
        if (!this.rifle && this.fireT < 0.6 && this.fireT + dt >= 0.6) { this.glintT = 0.6; audio.play('schofield_cock', { position: this.root.position, volume: 0.9 }); }
        if (this.glintT > 0) {
          this.glintT -= dt;
          const hp = this.spheres[0].c;
          if (Math.floor(this.glintT * 16) % 2 === 0) g.fx.glint(_v3.copy(hp).add(_v2.set(0, -0.05, 0)), 1.5 + dist / 70);
        }
        if (this.fireT <= 0) {
          this.fireT = (this.rifle ? 2.9 : 2.2) * g.diff.fireMult + Math.random() * 1.3;
          const muzzle = this.gun.muzzle.getWorldPosition(new THREE.Vector3());
          // a man with a rifle on high ground is the most dangerous thing out
          // here; he telegraphs first, so a hit should really cost you
          g.combat.enemyShot(this, muzzle, { dist, acc: this.rifle ? g.diff.rifleAcc : g.diff.riderAcc, dmgPlayer: this.rifle ? 20 : 9, dmgCoach: this.rifle ? 11 : 5, rifle: this.rifle });
        }
      }
      if (coach.s - this.s > 70) { this.removeAt = g.time + 1; this.alive = false; this.escaped = true; }
    }
    this.root.updateMatrixWorld(true);
    if (this.alive && this.man.kind === 'glb' && this.man.bones.chest) {
      const hp = this.man.hand.getWorldPosition(_v3);
      aimBone(this.man.bones.chest, this.man.hand, _v2.subVectors(g.player.headPos, hp).normalize(), 0.85);
    }
    const [head, body] = this.spheres;
    if (this.man.bones.head) this.man.bones.head.getWorldPosition(head.c).add(_v.set(0, 0.06, 0)); else this.root.localToWorld(head.c.set(0, 1.65, 0));
    if (this.man.bones.chest) this.man.bones.chest.getWorldPosition(body.c); else this.root.localToWorld(body.c.set(0, 1.2, 0));
  }

  damage(amount, part, dir) {
    if (!this.alive) return false;
    this.hp -= amount;
    if (this.hp <= 0) {
      this.alive = false;
      if (this.man.has('DieStanding')) this.man.play('DieStanding', { once: true, fade: 0.08 });
      else this.man.play('FallOff', { once: true, fade: 0.08 });
      this.removeAt = this.g.time + 8;
      return true;
    }
    return false;
  }

  dispose() { this.g.scene.remove(this.root); }
}

// ------------------------------------------------------------------ manager
export class Enemies {
  constructor(game) {
    this.g = game;
    this.list = [];
    this.waves = game.route.def.waves.map((w) => ({ ...w, done: false }));
    this._spawnQ = [];
    this.riderCap = 5;
  }

  // Called once the player exists, since the loadout decides this: word gets
  // around that the coach is carrying a Gatling, and a marauder band comes for
  // it — which is the whole reason to own the thing.
  planFor(player) {
    // the job itself draws trouble: a bullion run brings one band, a prisoner
    // transfer brings his friends the whole way
    for (const at of this.g.mission?.bands || []) {
      this.waves.push({ at, type: 'marauders', count: 11, done: false });
    }
    if (player.loadout.some((w) => w.id === 'gatling')) {
      this.waves.push({ at: 0.46, type: 'marauders', count: 14, done: false });
    }
  }

  get aliveCount() { return this.list.filter((e) => e.alive).length; }

  update(dt) {
    const g = this.g, prog = g.coach.s / g.route.len;
    for (const w of this.waves) {
      if (!w.done && prog >= w.at) { w.done = true; this._spawnWave(w); }
    }
    // staggered spawns
    const riders = this.list.filter((e) => e.alive && e.type === 'rider' && e.state === 'ride').length;
    for (let i = this._spawnQ.length - 1; i >= 0; i--) {
      const q = this._spawnQ[i]; q.t -= dt;
      if (q.t <= 0) {
        if (q.rider && riders >= this.riderCap) { q.t = 1; continue; } // cap live riders
        this._spawnQ.splice(i, 1); q.fn();
      }
    }
    // patch the coach up a little whenever a fight is cleared
    const busy = this.aliveCount > 0 || this._spawnQ.length > 0;
    if (this._marauders && !busy) { this._marauders = false; this.riderCap = 5; }
    if (this._engaged && !busy && !g.over) {
      g.coach.hp = Math.min(100, g.coach.hp + 10);
      g.hud.feedMsg('Coach patched up +10', false);
    }
    this._engaged = busy;
    for (const e of this.list) e.update(dt);
    for (let i = this.list.length - 1; i >= 0; i--) {
      const e = this.list[i];
      if (g.time >= e.removeAt || (e.removeAt === 0)) { e.dispose(); this.list.splice(i, 1); }
    }
  }

  _spawnWave(w) {
    const g = this.g;
    const n = Math.round(w.count * g.diff.countMult);
    if (w.type === 'riders') {
      g.hud.banner(w.from === 'ahead' ? 'Riders up ahead!' : w.from === 'flank' ? 'Riders on the flank!' : 'Riders behind!', '', 1.3);
      const used = new Set(this.list.filter((e) => e.type === 'rider' && e.alive).map((e) => e.slot));
      let slot = 0;
      for (let i = 0; i < n; i++) {
        while (used.has(slot)) slot++;
        const sl = slot++;
        const side = i % 2 === 0 ? 1 : -1;
        this._spawnQ.push({ t: i * 0.9, rider: true, fn: () => this.list.push(new Rider(g, { from: w.from, slot: sl, side })) });
      }
    } else if (w.type === 'marauders') {
      g.hud.banner(g.mission?.id === 'prisoner' ? 'They want him back!' : 'Marauders!', 'All sides', 3);
      audio.play('horse_neigh', { volume: 1, pitch: 0.85 });
      this.riderCap = 10;                       // a band, not a patrol
      const froms = ['behind', 'flank', 'ahead'];
      const used = new Set(this.list.filter((e) => e.type === 'rider' && e.alive).map((e) => e.slot));
      let slot = 0;
      for (let i = 0; i < n; i++) {
        while (used.has(slot)) slot++;
        const sl = slot++;
        this._spawnQ.push({
          t: i * 0.55, rider: true,
          fn: () => this.list.push(new Rider(g, { from: froms[i % froms.length], slot: sl, side: i % 2 ? 1 : -1 })),
        });
      }
      this._marauders = true;
    } else if (w.type === 'ridge') {
      g.hud.banner('Riflemen on the ridge!', 'Watch for the glint', 1.5);
      for (let i = 0; i < n; i++) this._spawnQ.push({ t: i * 1.2, fn: () => this._spawnRidge(i) });
    } else if (w.type === 'town') {
      g.hud.banner('Perdition', 'Nobody lives here anymore', 3);
      const spawns = (g.towns.spawns || []).filter((s) => !s.used);
      spawns.sort(() => Math.random() - 0.5);
      const pick = spawns.slice(0, n);
      for (const sp of pick) {
        sp.used = true;
        this._spawnQ.push({
          t: 0, fn: () => {
            // wait until the coach approaches that building
            const watch = () => {
              if (g.over) return;
              if (g.coach.s > sp.s - 75) {
                const e = new Gunman(g, sp.pos.clone(), sp.face, { rifle: Math.random() < 0.3, popup: true }); // spawn empty = feet
                e.s = sp.s; this.list.push(e);
              } else this._spawnQ.push({ t: 0.25, fn: watch });
            };
            watch();
          },
        });
      }
    }
  }

  // A rifleman you can't see is just an unfair hit, so a spot only counts when
  // it's a real ledge above the road AND has open sight lines to the stretch the
  // coach is about to drive. Candidates that fail either test are thrown out
  // rather than scored, and if nothing qualifies we try again further along.
  _ridgeSpot(i, tries = 40) {
    const g = this.g, R = g.route, coach = g.coach;
    let best = null, bestScore = -Infinity;
    for (let k = 0; k < tries; k++) {
      // close enough that he's a readable silhouette when the bracket appears,
      // far enough that you get a few seconds before he's in rifle range
      const s = coach.s + 120 + Math.random() * 110 + i * 25;
      if (s > R.len - 60) continue;
      const side = Math.random() < 0.5 ? -1 : 1;
      const d = side * (22 + Math.random() * 48);
      const p = R.worldAt(s, d, new THREE.Vector3());
      const rise = p.y - R.roadHeightAt(s);
      if (rise < 7 || rise > 45) continue;                       // a ledge, not a ditch or a peak
      const hx = R.height(p.x + 2, p.z) - p.y, hz = R.height(p.x, p.z + 2) - p.y;
      const slope = Math.hypot(hx, hz) / 2;
      if (slope > 0.9) continue;                                 // nowhere to stand
      // he must see the coach from two points along its approach, chest high
      const chest = new THREE.Vector3().copy(p).setY(p.y + 1.2);
      let clear = true;
      for (const ahead of [-60, -20]) {
        const road = R.worldAt(s + ahead, 0, new THREE.Vector3()); road.y += 2.5;
        const dv = road.sub(chest); const L = dv.length(); dv.divideScalar(L);
        if (g.terrain.raycast(chest, dv, L) < L - 3) { clear = false; break; }
      }
      if (!clear) continue;
      // prefer a good silhouette: high and close enough to read, off the road edge
      const score = Math.min(rise, 26) * 0.8 - slope * 25 - Math.abs(Math.abs(d) - 38) * 0.25;
      if (score > bestScore) { bestScore = score; best = { p, s }; }
    }
    return best;
  }

  _spawnRidge(i) {
    const g = this.g;
    const best = this._ridgeSpot(i) || this._ridgeSpot(i + 4);
    if (!best) return;
    const face = new THREE.Vector3().subVectors(g.coach.pos, best.p).setY(0).normalize();
    const e = new Gunman(g, best.p, face, { rifle: true });
    e.los = true;
    e.s = best.s;
    this.list.push(e);
  }

  // closest enemy part to the aim ray within an angular tolerance (radians)
  pick(origin, dir, tol, noHead = false) {
    let best = null, bestA = tol;
    for (const e of this.list) {
      if (!e.alive) continue;
      for (const sp of e.spheres) {
        if (noHead && sp.part === 'head') continue;
        const to = _v.subVectors(sp.c, origin);
        const dist = to.length();
        if (dist > 260) continue;
        const ang = Math.acos(clamp(to.dot(dir) / dist, -1, 1)) - Math.atan(sp.r / dist);
        const a = ang - (sp.part === 'head' ? 0.004 : sp.part === 'body' ? 0.002 : 0);
        if (a < bestA) { bestA = a; best = { enemy: e, part: sp.part, aimPoint: sp.c, dist }; }
      }
    }
    return best;
  }

  // exact ray hit, or (with tol) the assisted aim point
  raycast(origin, dir, range, tol = 0, maxMiss = 1) {
    const hit = this.rayHit(origin, dir, range);
    if (hit) return hit;
    if (tol > 0) {
      const p = this.pick(origin, dir, tol, true);
      if (p && p.dist < range) {
        // snap to the sphere's surface nearest the ray, and only for small linear misses
        const sp = p.enemy.spheres.find((q) => q.c === p.aimPoint);
        const t = _v.subVectors(sp.c, origin).dot(dir);
        const onRay = _v2.copy(origin).addScaledVector(dir, t);
        const miss = onRay.distanceTo(sp.c) - sp.r;
        if (miss > maxMiss) return null;
        const pt = sp.c.clone().add(_v3.subVectors(onRay, sp.c).setLength(sp.r * 0.7));
        return { point: pt, enemy: p.enemy, part: p.part, t: p.dist };
      }
    }
    return null;
  }

  rayHit(origin, dir, range) {
    let best = null, bestT = range;
    for (const e of this.list) {
      if (!e.alive) continue;
      for (const sp of e.spheres) {
        const oc = _v.subVectors(origin, sp.c);
        const b = oc.dot(dir), c = oc.lengthSq() - sp.r * sp.r;
        const h = b * b - c;
        if (h < 0) continue;
        const t = -b - Math.sqrt(h);
        // prefer rider parts over the horse when overlapping
        const bias = sp.part === 'horse' ? 0.3 : 0;
        if (t > 0 && t + bias < bestT) { bestT = t + bias; best = { enemy: e, part: sp.part, t, point: origin.clone().addScaledVector(dir, t) }; }
      }
    }
    return best;
  }

  dispose() { this.list.forEach((e) => e.dispose()); this.list = []; }
}
