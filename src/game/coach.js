// The stagecoach: follows the route, sways on its thoroughbraces, spins its
// wheels and drags a four-horse team. Driver NPC up front, player on the roof.
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { createHorse, createRider } from './characters.js';
import { damp, clamp } from '../core/noise.js';

const COATS = [new THREE.Color(1, 1, 1), new THREE.Color(0.55, 0.42, 0.35), new THREE.Color(1.25, 1.15, 1.05), new THREE.Color(0.8, 0.6, 0.45)];

function fallbackCoach() {
  const root = new THREE.Group();
  const red = new THREE.MeshStandardMaterial({ color: 0x5a1a12, roughness: 0.55 });
  const ochre = new THREE.MeshStandardMaterial({ color: 0x9a6a22, roughness: 0.6 });
  const leather = new THREE.MeshStandardMaterial({ color: 0x2a1a10, roughness: 0.8 });
  const iron = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.5, metalness: 0.6 });
  const chassis = new THREE.Group(); chassis.name = 'Chassis'; root.add(chassis);
  const frame = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.12, 3.6), ochre); frame.position.y = 0.75; chassis.add(frame);
  const pole = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 2.8), ochre); pole.position.set(0, 0.8, 2.9); chassis.add(pole);
  const body = new THREE.Group(); body.name = 'Body'; root.add(body);
  const shell = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.5, 2.5), red); shell.position.set(0, 1.75, -0.2); body.add(shell);
  const boot = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.8, 0.7), leather); boot.position.set(0, 1.4, -1.75); body.add(boot);
  const box = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.6, 0.8), red); box.position.set(0, 2.1, 1.35); body.add(box);
  const lug = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.4, 1.6), leather); lug.position.set(0, 2.7, -0.3); body.add(lug);
  const wheels = {};
  for (const [n, x, z, r] of [['Wheel_FL', 0.78, 1.2, 0.5], ['Wheel_FR', -0.78, 1.2, 0.5], ['Wheel_RL', 0.8, -1.3, 0.72], ['Wheel_RR', -0.8, -1.3, 0.72]]) {
    const w = new THREE.Group(); w.name = n; w.position.set(x, r, z);
    const tyre = new THREE.Mesh(new THREE.TorusGeometry(r - 0.03, 0.035, 6, 20).rotateY(Math.PI / 2), iron); w.add(tyre);
    for (let k = 0; k < 7; k++) {
      const sp = new THREE.Mesh(new THREE.BoxGeometry(0.03, r * 2 - 0.1, 0.03), ochre); sp.rotation.x = (k / 7) * Math.PI; w.add(sp);
    }
    chassis.add(w); wheels[n] = w;
  }
  const add = (n, x, y, z) => { const o = new THREE.Object3D(); o.name = n; o.position.set(x, y, z); body.add(o); };
  add('Seat_Driver', 0.35, 2.45, 1.35); add('Seat_Guard', -0.35, 2.9, -0.6); add('Hitch', 0, 0.8, 4.3);
  add('Lamp_L', 0.8, 2.2, 1.0); add('Lamp_R', -0.8, 2.2, 1.0);
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return root;
}

export class Coach {
  constructor(route, scene) {
    this.route = route; this.scene = scene;
    this.root = new THREE.Group();
    const g = assets.models.stagecoach;
    this.model = g ? g.scene.clone(true) : fallbackCoach();
    this.model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    this.root.add(this.model);
    scene.add(this.root);
    const f = (n) => findNode(this.model, n);
    this.body = f('Body') || this.model;
    this.wheels = ['Wheel_FL', 'Wheel_FR', 'Wheel_RL', 'Wheel_RR'].map((n) => {
      const w = f(n); if (!w) return null;
      const box = new THREE.Box3().setFromObject(w); const r = Math.max(0.3, (box.max.y - box.min.y) / 2);
      return { o: w, r, base: w.quaternion.clone() };
    }).filter(Boolean);
    this.seatGuard = f('Seat_Guard'); this.seatDriver = f('Seat_Driver');
    this.hitch = f('Hitch');
    this.lamps = [f('Lamp_L'), f('Lamp_R')].filter(Boolean);
    this._bodyBase = this.body.position.clone();
    this._bodyQ = this.body.quaternion.clone();

    // team
    const hitchZ = this.hitch ? this.hitch.position.z : 4.2;
    this.team = [];
    const slots = [[0.62, hitchZ - 1.0], [-0.62, hitchZ - 1.0], [0.62, hitchZ + 1.75], [-0.62, hitchZ + 1.75]];
    slots.forEach(([x, z], i) => {
      const h = createHorse({ coat: COATS[i], saddle: false, harness: true });
      h.offX = x; h.offZ = z; h.phase = i * 0.13;
      scene.add(h.root);
      this.team.push(h);
    });

    // driver
    this.driver = createRider({ variant: 'driver' });
    (this.seatDriver || this.body).add(this.driver.root);
    if (this.driver.has('Drive')) this.driver.play('Drive'); else this.driver.play('Ride');

    this.s = 0;
    this.speed = 0;
    this.cruise = 15;
    this.stamina = 1;
    this.hp = 100;
    this.sway = { roll: 0, rollV: 0, pitch: 0, pitchV: 0, bounce: 0, bounceV: 0 };
    this.wheelAngle = 0;
    this.pos = new THREE.Vector3();
    this.fwd = new THREE.Vector3(0, 0, 1);
    this.right = new THREE.Vector3(-1, 0, 0);
    this.vel = new THREE.Vector3();
    this.shake = 0;
    this._fr = {}; this._p = new THREE.Vector3(); this._p2 = new THREE.Vector3();
  }

  update(dt, ctl) {
    const R = this.route;
    // speed control
    let target = this.cruise;
    if (ctl.whip && this.stamina > 0.02) { target = this.cruise + 7; this.stamina = Math.max(0, this.stamina - dt * 0.22); }
    else this.stamina = Math.min(1, this.stamina + dt * 0.07);
    if (ctl.brake) target = this.cruise - 7;
    if (this.stopping) target = 0;
    if (this.s < 30 && !this.stopping) target = Math.min(target, 4 + this.s * 0.5);
    this.speed = damp(this.speed, target, this.stopping ? 0.9 : 0.6, dt);
    this.s = Math.min(R.len, this.s + this.speed * dt);

    // position/orientation from road
    const fr = R.frame(this.s, this._fr);
    const back = R.worldAt(this.s - 1.4, 0, this._p), front = R.worldAt(this.s + 1.4, 0, this._p2);
    const prev = this.pos.clone();
    this.pos.set(fr.x, (back.y + front.y) / 2, fr.z);
    this.vel.subVectors(this.pos, prev).divideScalar(Math.max(dt, 1e-4));
    const pitch = Math.atan2(front.y - back.y, 2.8);
    const yaw = Math.atan2(fr.tx, fr.tz);
    const hl = R.height(fr.x + fr.rx * 0.8, fr.z + fr.rz * 0.8), hr = R.height(fr.x - fr.rx * 0.8, fr.z - fr.rz * 0.8);
    const bank = Math.atan2(hl - hr, 1.6) * 0.6;
    this.root.position.copy(this.pos);
    this.root.rotation.set(0, 0, 0);
    this.root.rotation.order = 'YXZ';
    this.root.rotation.set(-pitch, yaw, bank);
    this.fwd.set(fr.tx, 0, fr.tz);
    this.right.set(fr.rx, 0, fr.rz);

    // body sway on the thoroughbraces (springs)
    const sw = this.sway, v = this.speed;
    const rough = R.noise(this.s * 0.35, 3.3) * 0.5 + R.noise(this.s * 1.3, 7.1) * 0.25;
    const lat = fr.curv * v * v; // centripetal accel
    sw.rollV += (-lat * 0.02 - sw.roll * 26 - sw.rollV * 3.2) * dt;
    sw.roll += sw.rollV * dt;
    sw.pitchV += (rough * 0.9 * (v / 15) - sw.pitch * 20 - sw.pitchV * 2.5) * dt;
    sw.pitch += sw.pitchV * dt;
    sw.bounceV += (Math.abs(rough) * 0.35 * (v / 15) - sw.bounce * 60 - sw.bounceV * 6) * dt;
    sw.bounce += sw.bounceV * dt;
    this.body.position.copy(this._bodyBase);
    this.body.position.y += sw.bounce * 0.4;
    this.body.quaternion.copy(this._bodyQ).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(sw.pitch * 0.6, 0, clamp(sw.roll, -0.25, 0.25))));
    this.shake = Math.abs(sw.bounceV) * 0.02 + Math.abs(rough) * 0.004 * v / 15;

    // wheels
    this.wheelAngle += (v * dt);
    for (const w of this.wheels) w.o.quaternion.copy(w.base).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), this.wheelAngle / w.r));

    // team follows the road ahead of the coach
    for (const h of this.team) {
      const hs = this.s + h.offZ;
      const p = R.worldAt(hs, -h.offX, this._p);
      const f2 = R.frame(hs, {});
      h.root.position.copy(p);
      const ahead = R.worldAt(hs + 1.2, -h.offX, this._p2);
      h.root.rotation.set(-Math.atan2(ahead.y - p.y, 1.2), Math.atan2(f2.tx, f2.tz), 0, 'YXZ');
      const gait = v < 3 ? 'Idle' : v < 11 ? 'Canter' : 'Gallop';
      if (h.has(gait)) h.play(gait);
      // clips match ground speed at ~6.7 m/s (gallop); beyond ~1.3x it looks frantic
      h.setSpeed(gait === 'Gallop' ? Math.min(1.32, 0.75 + v / 30) : gait === 'Canter' ? Math.min(1.3, v / 7) : 1);
      h.update(dt);
    }
    this.driver.update(dt);
  }

  // world-space aim point for enemies (random spot on the coach)
  targetPoint(out) {
    return out.copy(this.pos).add(new THREE.Vector3((Math.random() - 0.5) * 1.4, 1.2 + Math.random() * 1.6, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.atan2(this.fwd.x, this.fwd.z)))
      .addScaledVector(this.fwd, (Math.random() - 0.5) * 3);
  }

  dispose() {
    this.scene.remove(this.root);
    this.team.forEach((h) => this.scene.remove(h.root));
  }
}
