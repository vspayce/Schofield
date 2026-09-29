// The train at the crossing: when it runs, the whistle, the gunmen riding the
// boxcar roofs, and what happens to a coach that tries to beat it.
//
// Timing works like the buffalo herd: the train is dispatched when the coach is
// `lead` metres out and paced so the middle of it is on the crossing just as a
// coach holding cruise would reach it. Until the warning it keeps adjusting to
// the coach (whip early and it hurries too); after the warning its speed is
// fixed, so hauling on the reins lets it by. Whipping from the warning gets the
// team onto the planks just as the engine arrives — a gamble that loses by a
// length unless the whip went in early.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { makeTrainSounds } from '../core/synth.js';
import { Train } from '../world/train.js';
import { Gunman } from './enemies.js';
import { clamp, damp } from '../core/noise.js';

const _v = new THREE.Vector3();
const LANE = 1.3;        // half-width of the coach and team
const HALF = 1.5;        // half-width of the train's swept envelope

export class Crossing {
  constructor(game, rail, def = {}) {
    this.g = game; this.rail = rail; this.def = def;
    makeTrainSounds();
    this.train = new Train(game.scene, rail, {
      cars: def.cars ?? 3, caboose: def.caboose !== false,
      seed: game.route.def.seed + 5, light: game.route.def.light,
    });
    this.lead = def.lead ?? 330;
    this.baseSpeed = def.speed ?? 11;
    this.state = 'idle';
    this.gunmen = [];
    this._whistles = [];
    this._bellT = 0; this._hitCd = 0; this._hit = false;
    this.train.onChuff = () => this._sound('train_chuff', this.train.cars[0].root.position, 0.55, 26, 0.92 + Math.random() * 0.1);
    this._band();
  }

  // Where the train's envelope crosses the coach's lane, in road terms (a band
  // of road stations) and in rail terms (a span of u along the line).
  _band() {
    const R = this.rail, f = this.g.route.frame(R.s, {});
    const st = R.side.x * f.tx + R.side.z * f.tz, sr = R.side.x * f.rx + R.side.z * f.rz;
    const dr = Math.abs(R.dr) > 0.2 ? R.dr : Math.sign(R.dr || 1) * 0.2;
    let s0 = Infinity, s1 = -Infinity, u0 = Infinity, u1 = -Infinity;
    for (const d of [-LANE, LANE]) {
      for (const v of [-HALF, HALF]) {
        const u = (d - v * sr) / dr;
        const s = u * R.dt + v * st;
        s0 = Math.min(s0, s); s1 = Math.max(s1, s);
        u0 = Math.min(u0, u); u1 = Math.max(u1, u);
      }
    }
    this.b0 = R.s + s0; this.b1 = R.s + s1;       // road stations the train sweeps
    this.u0 = u0; this.u1 = u1;                   // rail span over the coach's lane
  }

  get teamFront() {
    const c = this.g.coach;
    return (c._teamFront ??= Math.max(4, ...c.team.map((h) => h.offZ)) + 1.3);
  }

  // seconds until the leaders reach the band, at `speed`
  _eta(speed) {
    const c = this.g.coach;
    return Math.max(0.5, (this.b0 - (c.s + this.teamFront)) / Math.max(4, speed));
  }

  // the part of the lane the train covers, in its own along-travel metres
  _laneX() {
    const T = this.train;
    const a = T.sdir * this.u0, b = T.sdir * this.u1;
    return [Math.min(a, b), Math.max(a, b)];
  }

  get occupied() {
    if (!this.train.active) return false;
    const [t, h] = this.train.span(), [l0, l1] = this._laneX();
    return h > l0 && t < l1;
  }

  // ------------------------------------------------------------------ run
  update(dt) {
    const g = this.g, c = g.coach, T = this.train;
    if (this.state === 'idle' && c.s >= this.rail.s - this.lead) {
      if (c.s < this.b0 - 60) this._dispatch(); else this.state = 'gone';
    }
    if (this.state === 'coming') this._pace(dt);
    if (this.state === 'coming' && this._eta(c.cruise) < 10.5) this._warn();
    T.update(dt, g.camera.position);
    if (!T.active) { c.limitS = null; return; }

    this._sounds(dt);
    this._rumble();
    this._block(dt);
    this._collide(dt);

    // gone past and away: stand the train down, and anyone still on the roofs
    // got away with it
    const [tail] = T.span();
    if (tail > this.rail.reach - 20 || T.x > this.rail.reach + T.length) {
      T.setActive(false);
      audio.stopLoop('train_clatter', 1.5);
      for (const e of this.gunmen) if (e.alive) { e.alive = false; e.escaped = true; e.removeAt = g.time; }
      c.limitS = null;
      this.state = 'gone';
    }
  }

  _dispatch() {
    const g = this.g, T = this.train, R = this.rail;
    T.sdir = this.def.from === 'left' ? 1 : this.def.from === 'right' ? -1 : (Math.random() < 0.5 ? 1 : -1);
    const L = T.length;
    const eta = this._eta(g.coach.cruise);
    let V = this.baseSpeed;
    // middle of the train on the lane at eta
    const mid = (this._laneX()[0] + this._laneX()[1]) / 2;
    let x = mid - V * eta + L / 2;
    const minX = -(R.reach - 12) + L;             // tail still on the laid track
    if (x < minX) { x = minX; V = clamp((mid + L / 2 - x) / eta, 6, 18); }
    T.x = x; T.speed = V; T.odo = 0;
    T.setActive(true);
    T.place();
    this.state = 'coming';
    this._spawnGunmen();
    audio.loop('train_clatter', { volume: 0, fade: 0.1 });
    // a long, distant blast to say it's on the line
    this._whistle(['long'], 0.6);
  }

  // Before the warning the train keeps its appointment with the coach; after
  // it, its speed is its own.
  _pace(dt) {
    const c = this.g.coach, T = this.train;
    const eta = this._eta(Math.max(c.cruise, c.speed));
    const [l0, l1] = this._laneX();
    const midNow = T.x - T.length / 2;
    const want = clamp(((l0 + l1) / 2 - midNow) / eta, 6, 18);
    T.speed = damp(T.speed, want, 0.6, dt);
  }

  _warn() {
    this.state = 'warned';
    this.g.hud.banner('Train coming!', 'Rein in and let it pass', 2.6);
    // the crossing signal: long, long, short, long
    this._whistle(['long', 'long', 'short', 'long'], 0);
    this._bellT = 0.01;
  }

  _spawnGunmen() {
    const g = this.g, T = this.train;
    const slots = [];
    T.cars.forEach((car, ci) => car.slots.forEach((z, k) => slots.push({ ci, z, k })));
    // spread along the train: first slot of each car, then the second
    slots.sort((a, b) => a.k - b.k || a.ci - b.ci);
    const n = Math.min(this.def.gunmen ?? 4, slots.length);
    const face = _v.subVectors(g.coach.pos, T.cars[0].root.position).setY(0).normalize();
    for (let i = 0; i < n; i++) {
      const { ci, z } = slots[i];
      const carrier = { place: (out) => T.roofPoint(ci, z, out), vel: T.vel };
      const e = new Gunman(g, T.roofPoint(ci, z, new THREE.Vector3()), face, { rifle: i % 2 === 0, carrier });
      e.s = this.rail.s;           // they're gone once the coach is well past the crossing
      e.fireT += 1 + Math.random() * 2;
      g.enemies.list.push(e);
      this.gunmen.push(e);
    }
  }

  // Hold a slow coach at the edge while the train is across (or about to be).
  // A coach that comes in fast gets no such help: that's the collision.
  _block(dt) {
    const g = this.g, c = g.coach, T = this.train;
    const [l0, l1] = this._laneX();
    const soon = T.x < l0 && (l0 - T.x) < T.speed * 1.6;
    const front = c.s + this.teamFront;
    const hold = (this.occupied || soon) && front <= this.b0 + 0.05 && (c.speed < 4.5 || this._hit);
    if (hold) {
      c.limitS = this.b0 - this.teamFront - 0.35;
      if (!this._held && c.speed > 0.5) { this._held = true; audio.play('horse_neigh', { volume: 0.6, pitch: 0.95 }); }
    } else {
      c.limitS = null;
      if (!this.occupied) { this._held = false; this._hit = false; }
    }
  }

  // Anything of the coach or team in the band while the train is in it.
  _collide(dt) {
    const g = this.g, c = g.coach;
    this._hitCd = Math.max(0, this._hitCd - dt);
    if (g.over || this._hitCd > 0 || !this.occupied) return;
    const back = c.s - 2.7, front = c.s + this.teamFront;
    if (front < this.b0 || back > this.b1) return;
    const v = Math.max(0, c.speed);
    // a glancing knock at a walk, ruinous at a gallop — worse than any herd
    const dmg = clamp(14 + v * 2.4, 16, 55);
    c.hp -= dmg;
    c.speed = 0;
    // knocked clear: back off the rails, or on across if mostly over already
    const mid = (back + front) / 2;
    if (mid > (this.b0 + this.b1) / 2) c.s = this.b1 + 2.9;
    else c.s = this.b0 - this.teamFront - 0.6;
    c.limitS = mid > (this.b0 + this.b1) / 2 ? null : c.s;
    this._hit = true;
    this._hitCd = 3;
    g.shake += 1.3;
    g.hitStop(0.16);
    const at = this.rail._at(0, _v).add(new THREE.Vector3(0, 1.2, 0));
    g.fx.dust(at, { amount: 34, size: 1.5, up: 3.2, spread: 7 });
    for (let i = 0; i < 4; i++) g.fx.splinters(at.clone().add(new THREE.Vector3((Math.random() - 0.5) * 2, Math.random() * 1.5, (Math.random() - 0.5) * 2)), new THREE.Vector3(0, 1, 0));
    audio.play('hit_wood_1', { volume: 1.3, pitch: 0.55 });
    audio.play('hit_wood_2', { volume: 1.1, pitch: 0.7, delay: 0.06 });
    audio.play('horse_neigh', { volume: 1, pitch: 0.8, delay: 0.1 });
    this._sound('train_whistle_short', at, 1.2, 60);
    g.hud.banner('Hit by the train!', `Coach -${Math.round(dmg)}`, 2.2);
    g.player.damage(8 + v * 0.7, at);
    g.onCoachDamage();
  }

  // ---------------------------------------------------------------- sound
  _sound(name, pos, vol, falloff = 30, pitch = 1) {
    const d = pos.distanceTo(this.g.camera.position);
    const k = 1 / (1 + Math.pow(d / falloff, 1.3));
    if (k * vol < 0.01) return;
    audio.play(name, { volume: vol * k, pitch, rand: 0 });
  }

  _whistle(pattern, delay) {
    let t = delay;
    for (const p of pattern) {
      this._whistles.push({ t, name: p === 'long' ? 'train_whistle' : 'train_whistle_short' });
      t += p === 'long' ? 2.35 : 0.95;
    }
  }

  _sounds(dt) {
    const T = this.train, loco = T.cars[0].root.position;
    for (let i = this._whistles.length - 1; i >= 0; i--) {
      const w = this._whistles[i];
      w.t -= dt;
      if (w.t <= 0) { this._whistles.splice(i, 1); this._sound(w.name, loco, 1.6, 70); }
    }
    // the bell rings from the warning until the engine is over the crossing
    if (this._bellT > 0) {
      this._bellT -= dt;
      if (this._bellT <= 0) {
        this._bellT = 0.8;
        T.bellSwing = 1;
        this._sound('train_bell', loco, 0.5, 35);
        if (T.x > this._laneX()[1] + 30) this._bellT = 0;
      }
    }
  }

  // the roar of the train and the ground shaking under the coach
  _rumble() {
    const g = this.g, T = this.train;
    const d = T.distanceTo(g.camera.position);
    audio.loopVolume('train_clatter', Math.min(1.1, 1.4 / (1 + Math.pow(d / 22, 1.4))), 0.2);
    audio.loopRate('train_clatter', clamp(T.speed / 11, 0.7, 1.4));
    const k = clamp(1 - d / 40, 0, 1);
    g.shake = Math.max(g.shake, 0.16 * k * k * Math.min(1.3, T.speed / 11));
  }

  // --------------------------------------------------------------- debug
  // Jump the coach to `before` metres short of the crossing and dispatch now.
  debugJump(before = 170) {
    const c = this.g.coach;
    c.s = this.b0 - this.teamFront - before;
    c.speed = c.cruise;
    this.state = 'idle';
    this.lead = before + 10;
  }

  dispose() {
    audio.stopLoop('train_clatter', 0.3);
    this.train.dispose();
  }
}
