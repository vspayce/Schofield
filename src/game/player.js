// The shotgun messenger: over-the-shoulder camera that orbits the roof seat,
// Schofield revolver / coach gun, hit-scan shooting with aim assist, recoil,
// reloads, health regen and Dead Eye target painting.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { createRider, createWeapon, rotateBoneWorld } from './characters.js';
import { clamp, damp } from '../core/noise.js';

export const WEAPONS = {
  schofield: {
    id: 'schofield', name: 'Schofield Revolver', model: 'Schofield', mag: 6, interval: 0.26, reload: 1.6,
    pellets: 1, spread: 0.0045, damage: 60, headMult: 3, range: 220, falloff: [60, 220], kick: 0.028,
    snd: ['schofield_shot', 'schofield_shot2'], reloadSnd: 'schofield_reload',
    stats: { power: 0.55, range: 0.85, rate: 0.8, spread: 0.9 },
    blurb: 'Smith & Wesson top-break .45. Six quick, true shots and a fast reload.',
  },
  shotgun: {
    id: 'shotgun', name: 'Coach Gun', model: 'CoachGun', mag: 2, interval: 0.32, reload: 1.8,
    pellets: 9, spread: 0.055, damage: 26, headMult: 1.6, range: 70, falloff: [14, 55], kick: 0.075,
    snd: ['shotgun_shot'], reloadSnd: 'shotgun_reload',
    stats: { power: 1, range: 0.35, rate: 0.45, spread: 0.3 },
    blurb: 'Double-barrel 10 gauge. Knocks a man clean out of the saddle up close.',
  },
};

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _q = new THREE.Quaternion(), _e = new THREE.Euler();

export class Player {
  constructor(game, weaponId) {
    this.g = game;
    this.camera = game.camera;
    this.yaw = 0;       // relative to coach heading
    this.pitch = -0.06;
    this.recoil = 0; this.recoilV = 0; this.recoilYaw = 0;
    this.hp = 100; this.lastHit = -10;
    this.deadeye = 0.35; this.deadeyeOn = false; this.marks = []; this.executing = false;
    this.ammo = {};
    for (const k in WEAPONS) this.ammo[k] = WEAPONS[k].mag;
    this.weapon = WEAPONS[weaponId] || WEAPONS.schofield;
    this.cool = 0; this.reloading = 0; this.swapT = 0;
    this.stats = { shots: 0, hits: 0, kills: 0, headshots: 0 };

    this.model = createRider({ variant: 'player' });
    const seat = game.coach.seatGuard || game.coach.body;
    seat.add(this.model.root);
    this.model.play(this.model.has('RideAim') ? 'RideAim' : 'Ride');
    this.guns = {};
    for (const k in WEAPONS) {
      const w = createWeapon(WEAPONS[k].model);
      w.root.visible = false;
      this.model.hand.add(w.root);
      this.guns[k] = w;
    }
    this._showGun();
    this.camPos = new THREE.Vector3();
    this.aimDir = new THREE.Vector3(0, 0, 1);
    this.fov = 60;
    this.shoulder = 1; // 1 = right shoulder
    this.hover = null;
  }

  _showGun() {
    for (const k in this.guns) this.guns[k].root.visible = k === this.weapon.id;
    this.g.hud.setWeapon(this.weapon, this.ammo[this.weapon.id]);
  }

  get headPos() {
    const seat = this.g.coach.seatGuard || this.g.coach.body;
    return seat.getWorldPosition(_v2).add(_v.set(0, 0.95, 0));
  }

  update(dt, rdt, inp) {
    const g = this.g;
    // ---------------------------------------------------------------- aim
    const sens = this.deadeyeOn ? 0.75 : 1;
    let dx = inp.dx * sens, dy = inp.dy * sens;
    // touch aim assist: slow down over targets + gentle pull
    if (g.input.touch && this.hover) { dx *= 0.55; dy *= 0.55; }
    this.yaw -= dx; this.pitch = clamp(this.pitch - dy, -1.05, 0.5);
    if (g.input.touch && this.hover && (Math.abs(inp.dx) + Math.abs(inp.dy)) > 0) {
      const want = this._anglesTo(this.hover.aimPoint);
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
    const head = this.headPos;
    const right = _v.set(-Math.cos(yawW), 0, Math.sin(yawW));
    const back = 3.3, side = 1.2 * this.shoulder, up = 0.55;
    const target = new THREE.Vector3().copy(head)
      .addScaledVector(this.aimDir, -back)
      .addScaledVector(right, side)
      .add(new THREE.Vector3(0, up + Math.max(0, -this.pitch) * 0.8, 0));
    // shake
    const sh = coach.shake + g.shake;
    target.x += (Math.random() - 0.5) * sh; target.y += (Math.random() - 0.5) * sh;
    // keep camera above ground
    const gh = g.route.height(target.x, target.z) + 0.6;
    if (target.y < gh) target.y = gh;
    this.camPos.copy(target);
    this.camera.position.copy(this.camPos);
    const look = _v2.copy(this.camPos).add(this.aimDir);
    this.camera.lookAt(look);
    const wantFov = this.deadeyeOn ? 52 : 60;
    this.fov = damp(this.fov, wantFov, 6, rdt);
    if (Math.abs(this.camera.fov - this.fov) > 0.01) { this.camera.fov = this.fov; this.camera.updateProjectionMatrix(); }
    this.camera.updateMatrixWorld();

    // ------------------------------------------------------ body follows aim
    const seat = coach.seatGuard || coach.body;
    const root = this.model.root;
    // the model's parent (seat) carries coach yaw; rotate model yaw by relative aim
    root.rotation.set(0, this.yaw, 0);
    this.model.update(dt);
    const b = this.model.bones;
    if (b.chest && this.model.kind === 'glb') {
      const q = new THREE.Quaternion().setFromAxisAngle(right.clone().negate(), pitchW * 0.8);
      rotateBoneWorld(b.chest, q);
    } else if (b.chest) {
      b.chest.rotation.x = -pitchW;
    }

    // ---------------------------------------------------------- targeting
    this.hover = g.enemies.pick(this.camPos, this.aimDir, g.input.touch ? 0.05 : 0.02);
    g.hud.crosshairEnemy(!!this.hover);

    // ------------------------------------------------------------ weapons
    const W = this.weapon;
    this.cool -= dt; this.swapT -= dt;
    if (this.reloading > 0) {
      this.reloading -= dt;
      if (this.reloading <= 0) { this.ammo[W.id] = W.mag; g.hud.setAmmo(W, this.ammo[W.id], false); }
    }
    if (inp.swap && this.swapT <= 0 && !this.executing) {
      this.weapon = this.weapon.id === 'schofield' ? WEAPONS.shotgun : WEAPONS.schofield;
      this.reloading = 0; this.cool = 0.3; this.swapT = 0.35;
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
      if (this.hover && this.marks.length < this.ammo[W.id] + (W.id === 'schofield' ? 0 : 0)) {
        const already = this.marks.find((m) => m.enemy === this.hover.enemy);
        if (!already && this.hover.part !== 'horse') {
          this.marks.push({ enemy: this.hover.enemy, part: this.hover.part });
          audio.play('ui_click', { volume: 0.5, pitch: 1.4 });
        }
      }
      if (this.deadeye <= 0) this._endDeadeye();
    }

    if (!this.executing) {
      const wantsFire = W.id === 'schofield' ? inp.firePressed || (inp.fire && g.input.touch) : inp.firePressed;
      if (wantsFire && this.cool <= 0 && this.reloading <= 0) {
        if (this.deadeyeOn && this.marks.length) this._endDeadeye();
        else if (this.ammo[W.id] > 0) this._fire();
        else { audio.play('schofield_cock', { volume: 0.5, pitch: 1.6 }); this._reload(); }
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
    this.reloading = W.reload;
    audio.play(W.reloadSnd, { volume: 0.9 });
    this.g.hud.setAmmo(W, this.ammo[W.id], true);
  }

  muzzleWorld(out) {
    const gun = this.guns[this.weapon.id];
    return gun.muzzle.getWorldPosition(out);
  }

  _fire(forced = null) {
    const g = this.g, W = this.weapon;
    this.ammo[W.id]--;
    this.cool = W.interval;
    this.stats.shots++;
    const muzzle = this.muzzleWorld(new THREE.Vector3());
    // gun fires from the muzzle; direction toward what's under the crosshair
    let aimPoint;
    if (forced) aimPoint = forced;
    else {
      const hit = g.enemies.raycast(this.camPos, this.aimDir, W.range, g.input.touch ? 0.035 : 0.012);
      aimPoint = hit ? hit.point : _v2.copy(this.camPos).addScaledVector(this.aimDir, 120).clone();
    }
    const baseDir = new THREE.Vector3().subVectors(aimPoint, this.camPos).normalize();
    let anyHit = false, killed = false;
    for (let p = 0; p < W.pellets; p++) {
      const dir = baseDir.clone();
      if (!forced) {
        const s = W.spread * (p === 0 && W.pellets === 1 ? 1 : 1);
        dir.x += (Math.random() - 0.5) * 2 * s; dir.y += (Math.random() - 0.5) * 2 * s; dir.z += (Math.random() - 0.5) * 2 * s;
        dir.normalize();
      }
      const res = g.combat.playerShot(this.camPos, dir, W, muzzle, !!forced);
      if (res.hit) anyHit = true;
      if (res.killed) killed = true;
    }
    if (anyHit) this.stats.hits++;
    g.hud.hitmarker(anyHit, killed);
    // feedback
    const dirOut = baseDir;
    g.fx.muzzle(muzzle, dirOut, { big: W.id === 'shotgun', light: true });
    audio.play(W.snd[Math.floor(Math.random() * W.snd.length)], { volume: W.id === 'shotgun' ? 1 : 0.9 });
    if (W.id === 'schofield') audio.play('schofield_cock', { volume: 0.25, delay: 0.14 });
    this.recoilV += W.kick * 60;
    g.shake += W.id === 'shotgun' ? 0.05 : 0.02;
    if (this.model.has('Shoot') && this.model.actions?.Shoot) {
      const a = this.model.actions.Shoot; a.reset(); a.setLoop(THREE.LoopOnce, 1); a.weight = 1; a.play();
    }
    g.hud.setAmmo(W, this.ammo[W.id], false);
    if (this.ammo[W.id] <= 0) setTimeout(() => { if (this.ammo[W.id] <= 0 && this.reloading <= 0 && !this.g.over) this._reload(); }, 350);
  }

  _startDeadeye() {
    this.deadeyeOn = true; this.marks = [];
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
      setTimeout(next, 170);
    };
    next();
  }

  addDeadeye(v) { if (!this.deadeyeOn) this.deadeye = Math.min(1, this.deadeye + v); }

  damage(amount, fromPos) {
    if (this.g.over) return;
    this.hp -= amount; this.lastHit = this.g.time;
    this.g.hud.damage(fromPos, this.camPos, this.aimDir);
    this.g.shake += 0.06;
    audio.play('hit_flesh_' + (1 + Math.floor(Math.random() * 2)), { volume: 0.8 });
    if (this.hp <= 0) this.g.fail('You were shot dead.');
  }
}

function angDiff(a, b) { let d = a - b; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return d; }
