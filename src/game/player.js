// The shotgun messenger: chase camera centred behind the coach that orbits with the aim,
// a sidearm and a long gun (see weapons.js), a scope that zooms from the guard's
// own eyes, hit-scan shooting with aim assist, recoil, reloads, health regen
// and Dead Eye target painting.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { createRider, createWeapon, rotateBoneWorld, aimBone } from './characters.js';
import { clamp, damp } from '../core/noise.js';
import { WEAPONS } from './weapons.js';

export { WEAPONS };

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _q = new THREE.Quaternion(), _e = new THREE.Euler();

export class Player {
  // loadout: { side, long, start } weapon ids
  constructor(game, { side = 'schofield', long = 'shotgun', start = side } = {}) {
    this.g = game;
    this.camera = game.camera;
    this.yaw = 0;       // relative to coach heading
    this.pitch = -0.06;
    this.recoil = 0; this.recoilV = 0; this.recoilYaw = 0;
    this.hp = 100; this.lastHit = -10;
    this.deadeye = 0.35; this.deadeyeOn = false; this.marks = []; this.executing = false;
    this.loadout = [WEAPONS[side] || WEAPONS.schofield, WEAPONS[long] || WEAPONS.shotgun];
    this.ammo = {};
    for (const W of this.loadout) this.ammo[W.id] = W.mag;
    this.weapon = this.loadout.find((W) => W.id === start) || this.loadout[0];
    this.scoped = false; this.scopeT = 0; // scopeT eases 0 -> 1 into the scope
    this.cool = 0; this.reloading = 0; this.swapT = 0; this.holsterT = 0;
    this.settle = 0; // seconds the aim has been steady (tightens revolvers)
    this.timers = []; // game-time callbacks (respect pause)
    this.stats = { shots: 0, hits: 0, kills: 0, headshots: 0 };

    this.model = createRider({ variant: 'player' });
    const seat = game.coach.seatGuard || game.coach.body;
    seat.add(this.model.root);
    // seated on the roof, gun shouldered, no gallop rock (the coach sways him)
    this.model.play(this.model.has('SeatAim') ? 'SeatAim' : this.model.has('RideAim') ? 'RideAim' : 'Ride');
    this.guns = {};
    for (const W of this.loadout) {
      const w = createWeapon(W.model, { finish: W.finish });
      w.root.visible = false;
      this.model.hand.add(w.root);
      this.guns[W.id] = w;
    }
    this._showGun();
    game.hud.setScope(false);
    this.camPos = new THREE.Vector3();
    this.aimDir = new THREE.Vector3(0, 0, 1);
    this.fov = 60;
    this.hover = null;
    this.wildlifeHover = null;
  }

  _showGun() {
    for (const k in this.guns) this.guns[k].root.visible = k === this.weapon.id;
    this.g.hud.setWeapon(this.weapon, this.ammo[this.weapon.id]);
  }

  // you sight down a long gun, not a revolver held at arm's length
  get canScope() { return this.weapon.zoom > 1; }

  // current zoom: 1 = normal view, W.zoom = fully in the scope
  get zoom() { return this.canScope ? 1 + (this.weapon.zoom - 1) * this.scopeT : 1; }

  setScope(on) {
    if (on && !this.canScope) return;
    if (on === this.scoped) return;
    this.scoped = on;
    audio.play('ui_click', { volume: 0.4, pitch: on ? 0.7 : 0.55 });
    this.g.hud.setScope(on);
  }

  get headPos() {
    const seat = this.g.coach.seatGuard || this.g.coach.body;
    return seat.getWorldPosition(_v2).add(_v.set(0, 0.95, 0));
  }

  update(dt, rdt, inp) {
    const g = this.g;
    const targetHover = this.hover || this.wildlifeHover;
    // ---------------------------------------------------------------- aim
    if (inp.scope) this.setScope(!this.scoped);
    this.scopeT = damp(this.scopeT, this.scoped ? 1 : 0, 10, rdt);
    // slower aim when magnified, so the view doesn't whip around
    const sens = (this.deadeyeOn ? 0.75 : 1) / this.zoom;
    let dx = inp.dx * sens, dy = inp.dy * sens;
    // touch aim assist: slow down over targets + gentle pull
    if (g.input.touch && targetHover) { dx *= 0.55; dy *= 0.55; }
    this.yaw -= dx; this.pitch = clamp(this.pitch - dy, -1.05, 0.5);
    this.settle = Math.abs(inp.dx) + Math.abs(inp.dy) < 0.0025 ? this.settle + rdt : 0;
    if (g.input.touch && targetHover && (Math.abs(inp.dx) + Math.abs(inp.dy)) > 0) {
      const want = this._anglesTo(targetHover.aimPoint);
      this.yaw += angDiff(want.yaw, this.yaw) * Math.min(1, rdt * 3.5);
      this.pitch += (want.pitch - this.pitch) * Math.min(1, rdt * 3.5);
    }
    // recoil spring
    this.recoilV += (-this.recoil * 140 - this.recoilV * 16) * rdt;
    this.recoil += this.recoilV * rdt;

    // ------------------------------------------------------------- camera
    const coach = g.coach;
    const heading = Math.atan2(coach.fwd.x, coach.fwd.z);
    const yawW = heading + this.yaw;
    const pitchW = this.pitch + this.recoil;
    this.aimDir.set(Math.sin(yawW) * Math.cos(pitchW), Math.sin(pitchW), Math.cos(yawW) * Math.cos(pitchW));
    // chase camera: sits dead behind the coach on its centreline and orbits
    // with the aim, so at rest you look straight down the road over the roof
    const pivot = _v3.copy(this.headPos);
    pivot.addScaledVector(coach.right, -_v.subVectors(pivot, coach.pos).dot(coach.right));
    const back = 9, up = 1.0;
    const target = new THREE.Vector3().copy(pivot)
      .addScaledVector(this.aimDir, -back)
      .add(new THREE.Vector3(0, up + Math.max(0, -this.pitch) * 1.2, 0));
    // the scope looks from the guard's own eyes (standing up a little), so the
    // coach can't block it; the driver right in front is hidden meanwhile
    if (this.scopeT > 0.001) target.lerp(_v2.copy(this.headPos).add(_v.set(0, 0.45, 0)), this.scopeT);
    if (coach.driver) coach.driver.root.visible = this.scopeT < 0.5;
    // shake
    const sh = (coach.shake + g.shake) * (1 - 0.8 * this.scopeT); // magnified shake is unplayable
    target.x += (Math.random() - 0.5) * sh; target.y += (Math.random() - 0.5) * sh;
    // keep camera above ground
    const gh = g.route.height(target.x, target.z) + 0.6;
    if (target.y < gh) target.y = gh;
    this.camPos.copy(target);
    this.camera.position.copy(this.camPos);
    const look = _v2.copy(this.camPos).add(this.aimDir);
    this.camera.lookAt(look);
    const wantFov = (this.deadeyeOn ? 52 : 60) / this.zoom;
    this.fov = this.scopeT > 0.001 ? wantFov : damp(this.fov, wantFov, 6, rdt);
    if (Math.abs(this.camera.fov - this.fov) > 0.01) { this.camera.fov = this.fov; this.camera.updateProjectionMatrix(); }
    this.camera.updateMatrixWorld();
    if (inp.dynamite) g.dynamite?.throw();

    // ------------------------------------------------------ body follows aim
    const seat = coach.seatGuard || coach.body;
    const root = this.model.root;
    // the model's parent (seat) carries coach yaw; rotate model yaw by relative aim
    // SeatAim/RideAim point the gun ~38° to the right of the body; turn the body so the gun sits on the crosshair
    root.rotation.set(0, this.yaw + (this.model.kind === 'glb' ? 0.67 : 0), 0);
    root.visible = this.scopeT < 0.5; // don't look through your own hat
    this.model.update(dt);
    const b = this.model.bones;
    if (b.chest && this.model.kind === 'glb') {
      // aim the barrel from the hand at whatever is under the crosshair
      const handP = this.model.hand.getWorldPosition(new THREE.Vector3());
      const tgt = new THREE.Vector3().copy(this.camPos).addScaledVector(this.aimDir, 40);
      aimBone(b.chest, this.model.hand, tgt.sub(handP).normalize(), 1);
    } else if (b.chest) {
      b.chest.rotation.x = -pitchW;
    }

    // ---------------------------------------------------------- targeting
    const targetTolerance = (g.input.touch ? 0.1 : 0.05) / this.zoom;
    this.hover = g.enemies.pick(this.camPos, this.aimDir, targetTolerance);
    if (this.hover && this.hover.dist > this.weapon.range) this.hover = null;
    this.wildlifeHover = this.hover ? null : g.wildlife.pick(this.camPos, this.aimDir, (g.input.touch ? 0.05 : 0.02) / this.zoom);
    g.hud.crosshairEnemy(!!this.hover);
    g.hud.crosshairWildlife(!!this.wildlifeHover);

    // ------------------------------------------------------------ weapons
    const W = this.weapon;
    this.cool -= dt; this.swapT -= dt;
    for (let i = this.timers.length - 1; i >= 0; i--) {
      const t = this.timers[i]; t.t -= rdt;
      if (t.t <= 0) { this.timers.splice(i, 1); t.fn(); }
    }
    // the holstered gun gets reloaded while you use the other one
    const other = this.loadout[0] === W ? this.loadout[1] : this.loadout[0];
    if (this.ammo[other.id] < other.mag) { this.holsterT += dt; if (this.holsterT > 2.5) { this.ammo[other.id] = other.mag; this.holsterT = 0; } }
    else this.holsterT = 0;
    if (this.reloading > 0) {
      this.reloading -= dt;
      if (this.reloading <= 0) { this.ammo[W.id] = W.mag; g.hud.setAmmo(W, this.ammo[W.id], false); }
    }
    if (inp.swap && this.swapT <= 0 && !this.executing) {
      this.weapon = other;
      this.reloading = 0; this.cool = 0.3; this.swapT = 0.35;
      if (!this.canScope) this.setScope(false);   // swapping to a pistol drops the scope
      audio.play('schofield_cock', { volume: 0.6 });
      this._showGun();
    }
    if (inp.reload && this.reloading <= 0 && this.ammo[W.id] < W.mag) this._reload();

    // Dead Eye
    if (inp.deadeye) {
      if (this.deadeyeOn) this._endDeadeye();
      else if (this.deadeye >= 0.2) this._startDeadeye();
    }
    if (this.deadeyeOn) {
      this.deadeye -= rdt * 0.2;
      if (this.hover && this.marks.length < this.ammo[W.id]) {
        const already = this.marks.find((m) => m.enemy === this.hover.enemy);
        if (!already && this.hover.part !== 'horse') {
          this.marks.push({ enemy: this.hover.enemy, part: this.hover.part });
          audio.play('ui_click', { volume: 0.5, pitch: 1.4 });
        }
      }
      if (this.deadeye <= 0) this._endDeadeye();
    }

    if (!this.executing) {
      // holding fire repeats revolvers and the Gatling on every platform
      const wantsFire = W.auto ? inp.firePressed || inp.fire : inp.firePressed;
      if (wantsFire && this.cool <= 0 && this.reloading <= 0) {
        if (this.deadeyeOn && this.marks.length) this._endDeadeye();
        else if (this.ammo[W.id] > 0) this._fire();
        else { audio.play('schofield_cock', { volume: 0.5, pitch: 1.6 }); this._reload(); }
      } else if (inp.firePressed && this.reloading > 0) {
        // pressing fire mid-reload used to do nothing at all, silently — which
        // reads as the gun being broken, especially on a single-shot long gun
        // where you spend most of the fight reloading
        this.dryT = (this.dryT || 0);
        if (g.time - this.dryT > 0.25) {
          this.dryT = g.time;
          audio.play('schofield_cock', { volume: 0.32, pitch: 1.9 });
          g.hud.nudgeReload();
        }
      }
    }
    // health regen
    if (g.time - this.lastHit > 4 && this.hp < 100) this.hp = Math.min(100, this.hp + rdt * 9);
  }

  _anglesTo(p) {
    const heading = Math.atan2(this.g.coach.fwd.x, this.g.coach.fwd.z);
    const d = _v.subVectors(p, this.camPos).normalize();
    return { yaw: Math.atan2(d.x, d.z) - heading, pitch: Math.asin(clamp(d.y, -1, 1)) };
  }

  _reload() {
    const W = this.weapon;
    if (this.reloading > 0) return;
    this.ammo[W.id] = W.mag;
    this.reloading = 0;
    audio.play(W.reloadSnd, { volume: 0.9 });
    this.g.hud.setAmmo(W, this.ammo[W.id], false);
  }

  muzzleWorld(out) {
    const gun = this.guns[this.weapon.id];
    return gun.muzzle.getWorldPosition(out);
  }

  _fire(forced = null) {
    const g = this.g, W = this.weapon;
    this.ammo[W.id]--;
    this.cool = W.interval;
    this.stats.shots += W.pellets;
    const muzzle = this.muzzleWorld(new THREE.Vector3());
    // gun fires from the muzzle; direction toward what's under the crosshair
    let aimPoint;
    if (forced) aimPoint = forced;
    else if (this.hover && this.hover.dist < W.range) aimPoint = this.hover.aimPoint;
    else {
      // assist only nudges near-misses onto the body/horse surface; headshots must be earned
      const tolerance = (g.input.touch ? 0.05 : 0.025) / this.zoom;
      const hit = g.enemies.raycast(this.camPos, this.aimDir, W.range, tolerance, g.input.touch ? 1.1 : 0.8);
      const animal = !hit ? g.wildlife.pick(this.camPos, this.aimDir, tolerance) : null;
      aimPoint = hit ? hit.point : animal && animal.dist < W.range ? animal.aimPoint : _v2.copy(this.camPos).addScaledVector(this.aimDir, 120).clone();
    }
    const baseDir = new THREE.Vector3().subVectors(aimPoint, this.camPos).normalize();
    let anyHit = false, killed = false, head = false, pelletHits = 0;
    // a steady revolver tightens up; the scope steadies everything
    const steady = (W.kind === 'revolver' && this.settle > 0.3 ? 0.3 : 1) * (this.scoped ? 0.6 : 1);
    for (let p = 0; p < W.pellets; p++) {
      const dir = baseDir.clone();
      if (!forced) {
        const s = W.spread * steady * (this.hover ? 0 : 1);
        dir.x += (Math.random() - 0.5) * 2 * s; dir.y += (Math.random() - 0.5) * 2 * s; dir.z += (Math.random() - 0.5) * 2 * s;
        dir.normalize();
      }
      const res = g.combat.playerShot(this.camPos, dir, W, muzzle, !!forced);
      if (res.hit) { anyHit = true; pelletHits++; }
      if (res.killed) killed = true;
      if (res.head) head = true;
    }
    this.stats.hits += pelletHits;
    g.hud.hitmarker(anyHit, killed, head);
    if (anyHit) {
      audio.play('ui_click', { volume: head ? 0.9 : 0.6, pitch: head ? 2.2 : 0.8, rand: 0 });
      if (killed) g.hitStop(0.06);
    }
    if (g.input.touch) navigator.vibrate?.(killed ? [12, 30, 12] : 12);
    // feedback
    const dirOut = baseDir;
    g.fx.muzzle(muzzle, dirOut, { big: W.kind === 'shotgun' || W.kind === 'rifle', light: true });
    audio.play(W.snd[Math.floor(Math.random() * W.snd.length)], { volume: W.kind === 'revolver' ? 0.9 : 1, pitch: W.pitch || 1 });
    if (W.kind === 'revolver' && W.interval > 0.2) audio.play('schofield_cock', { volume: 0.25, delay: 0.14 });
    this.guns[W.id].spin?.(1.05);
    this.recoilV += W.kick * 60;
    g.shake += W.kind === 'shotgun' ? 0.05 : W.kind === 'rifle' ? 0.035 : 0.02;
    this.model.kick?.();
    g.hud.setAmmo(W, this.ammo[W.id], false);
    if (this.ammo[W.id] <= 0) this._reload();
  }

  _startDeadeye() {
    this.deadeyeOn = true; this.marks = [];
    this.setScope(false);
    audio.play('deadeye_in', { volume: 0.9 });
    audio.loop('heartbeat_loop', { volume: 0.55 });
    this.g.setTimeScale(0.3);
  }

  _endDeadeye() {
    if (!this.deadeyeOn) return;
    this.deadeyeOn = false;
    this.deadeye = Math.max(0, this.deadeye);
    audio.stopLoop('heartbeat_loop', 0.3);
    const marks = this.marks.filter((m) => m.enemy.alive);
    this.marks = [];
    if (!marks.length) { this.g.setTimeScale(1); audio.play('deadeye_out', { volume: 0.7 }); return; }
    // execute: rapid guaranteed shots, still in slow motion
    this.executing = true;
    let i = 0;
    const next = () => {
      if (this.g.over) return;
      if (i >= marks.length || this.ammo[this.weapon.id] <= 0) {
        this.executing = false; this.g.setTimeScale(1); audio.play('deadeye_out', { volume: 0.7 });
        return;
      }
      const m = marks[i++];
      if (m.enemy.alive) this._fire(m.enemy.hitPoint(m.part));
      this.timers.push({ t: 0.17, fn: next });
    };
    next();
  }

  addDeadeye(v) { if (!this.deadeyeOn) this.deadeye = Math.min(1, this.deadeye + v); }

  damage(amount, fromPos) {
    if (this.g.over || this.g.godMode) return;
    this.hp -= amount; this.lastHit = this.g.time;
    const heavy = amount >= 15;                  // a rifle round, not a pistol
    this.g.hud.damage(fromPos, this.camPos, this.aimDir);
    this.g.hud.pulseHealth(heavy);
    this.g.shake += heavy ? 0.14 : 0.06;
    if (heavy) this.g.hitStop(0.05);
    audio.play('hit_flesh_' + (1 + Math.floor(Math.random() * 2)), { volume: heavy ? 1 : 0.8, pitch: heavy ? 0.82 : 1 });
    if (heavy) audio.play('hit_wood_1', { volume: 0.5, pitch: 0.7 });
    if (this.g.input.touch) navigator.vibrate?.(heavy ? [30, 40, 30] : 18);
    if (this.hp <= 0) this.g.fail('You were shot dead.');
  }
}

function angDiff(a, b) { let d = a - b; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return d; }
