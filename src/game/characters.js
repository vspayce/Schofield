// Horse / human / weapon instancing from the GLBs (skinned, animated), with
// primitive fallbacks that animate procedurally so the game is playable before
// (or without) the art.
import * as THREE from 'three';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { assets, findNode } from '../core/assets.js';

const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _v = new THREE.Vector3();

// Turn `bone` (usually the chest) so the hand's +Z (the gun barrel) points along
// worldDir. Call after the mixer update. weight < 1 aims partially.
const _hz = new THREE.Vector3(), _aq = new THREE.Quaternion(), _iq = new THREE.Quaternion();
export function aimBone(bone, hand, worldDir, weight = 1) {
  if (!bone || !hand) return;
  hand.updateWorldMatrix(true, false);
  _hz.set(0, 0, 1).applyQuaternion(hand.getWorldQuaternion(_aq));
  _aq.setFromUnitVectors(_hz, worldDir);
  if (weight < 1) _aq.slerp(_iq.identity(), 1 - weight);
  rotateBoneWorld(bone, _aq);
}

// Rotate a bone by a world-space rotation R (applied after the animation pose).
export function rotateBoneWorld(bone, R) {
  if (!bone) return;
  bone.updateWorldMatrix(true, false);
  bone.getWorldQuaternion(_q);
  _q.premultiply(R);
  bone.parent.getWorldQuaternion(_q2).invert();
  bone.quaternion.copy(_q2.multiply(_q));
  bone.updateMatrixWorld(true);
}

function prepMaterials(root, tint) {
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true; o.receiveShadow = true;
    o.frustumCulled = false; // skinned bounds are unreliable
    if (tint && /coat|body|horse/i.test(o.material?.name || o.name)) {
      o.material = o.material.clone(); o.material.color.multiply(tint);
    }
  });
}

class Animated {
  constructor(gltf, tint) {
    this.root = SkeletonUtils.clone(gltf.scene);
    prepMaterials(this.root, tint);
    this.mixer = new THREE.AnimationMixer(this.root);
    this.actions = {};
    for (const clip of gltf.animations) {
      if (clip.name === 'Shoot') {
        // recoil layered on top of whatever pose is playing
        const add = THREE.AnimationUtils.makeClipAdditive(clip.clone());
        this.recoil = this.mixer.clipAction(add);
        this.recoil.blendMode = THREE.AdditiveAnimationBlendMode;
        this.recoil.setLoop(THREE.LoopOnce, 1);
        continue;
      }
      this.actions[clip.name] = this.mixer.clipAction(clip);
    }
    this.current = null;
  }
  has(name) { return !!this.actions[name]; }
  play(name, { fade = 0.25, once = false, timeScale = 1 } = {}) {
    const a = this.actions[name];
    if (!a || this.current === a) return a;
    a.reset();
    a.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    a.clampWhenFinished = once;
    a.timeScale = timeScale;
    a.enabled = true;
    if (this.current) a.crossFadeFrom(this.current, fade, false);
    a.play();
    this.current = a;
    return a;
  }
  setSpeed(s) { if (this.current) this.current.timeScale = s; }
  kick() { if (this.recoil) { this.recoil.reset(); this.recoil.weight = 1; this.recoil.play(); } }
  update(dt) { this.mixer.update(dt); }
  node(name) { return findNode(this.root, name); }
}

// ------------------------------------------------------------------- horse
export function createHorse({ coat = new THREE.Color(1, 1, 1), saddle = true, harness = false } = {}) {
  const g = assets.models.horse;
  if (g) {
    const h = new Animated(g, coat);
    const sd = h.node('Saddle'); if (sd) sd.visible = saddle;
    const hn = h.node('Harness'); if (hn) hn.visible = harness;
    h.mount = h.node('Mount') || (() => { const o = new THREE.Object3D(); o.position.set(0, 1.45, 0); h.root.add(o); return o; })();
    h.play(h.has('Gallop') ? 'Gallop' : Object.keys(h.actions)[0]);
    h.kind = 'glb';
    h.gallopPhase = () => (h.actions.Gallop ? (h.actions.Gallop.time / h.actions.Gallop.getClip().duration) : 0);
    return h;
  }
  return fallbackHorse(coat, saddle);
}

function fallbackHorse(coat, saddle) {
  const root = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(0x6b4428).multiply(coat), roughness: 0.7 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1c130d, roughness: 0.8 });
  const body = new THREE.Group(); body.position.y = 1.25; root.add(body);
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.38, 1.3, 4, 10).rotateX(Math.PI / 2), mat); body.add(torso);
  const neck = new THREE.Group(); neck.position.set(0, 0.2, 0.75); body.add(neck);
  const nk = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.7, 4, 8), mat); nk.rotation.x = -0.75; nk.position.set(0, 0.3, 0.25); neck.add(nk);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.26, 0.6), mat); head.position.set(0, 0.62, 0.62); head.rotation.x = 0.5; neck.add(head);
  const tail = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.8, 5), dark); tail.position.set(0, 0.1, -0.95); tail.rotation.x = -2.4; body.add(tail);
  const legs = [];
  for (const [x, z] of [[-0.2, 0.55], [0.2, 0.55], [-0.2, -0.55], [0.2, -0.55]]) {
    const hip = new THREE.Group(); hip.position.set(x, -0.15, z); body.add(hip);
    const up = new THREE.Mesh(new THREE.CapsuleGeometry(0.09, 0.5, 3, 6), mat); up.position.y = -0.35; hip.add(up);
    const knee = new THREE.Group(); knee.position.y = -0.62; hip.add(knee);
    const lo = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.45, 3, 6), dark); lo.position.y = -0.25; knee.add(lo);
    legs.push({ hip, knee });
  }
  if (saddle) { const s = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.12, 0.6), dark); s.position.set(0, 0.4, 0.1); body.add(s); }
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  const mount = new THREE.Object3D(); mount.position.set(0, 0.45, 0.05); body.add(mount);
  let t = 0, speed = 1, mode = 'Gallop', fallT = 0;
  const offs = [0, 0.1, 0.55, 0.65];
  return {
    kind: 'fallback', root, mount,
    play(name) { mode = name; if (name === 'Fall') fallT = 0; },
    has: () => true,
    setSpeed(s) { speed = s; },
    gallopPhase: () => t % 1,
    update(dt) {
      if (mode === 'Fall') {
        fallT = Math.min(1, fallT + dt * 1.6);
        body.rotation.z = fallT * 1.4; body.position.y = 1.25 - fallT * 0.85;
        return;
      }
      t += dt * speed * 1.9;
      legs.forEach((l, i) => {
        const p = (t + offs[i]) * Math.PI * 2;
        l.hip.rotation.x = Math.sin(p) * 0.7;
        l.knee.rotation.x = Math.max(0, Math.cos(p)) * (i < 2 ? -1.1 : 1.1);
      });
      body.position.y = 1.25 + Math.abs(Math.sin(t * Math.PI * 2)) * 0.08;
      body.rotation.x = Math.sin(t * Math.PI * 2) * 0.05;
      neck.rotation.x = Math.sin(t * Math.PI * 2 + 1) * 0.15;
    },
  };
}

// ------------------------------------------------------------------- human
const BONE_ALIASES = {
  spine: ['spine', 'Spine', 'spine.001', 'mixamorigSpine'],
  chest: ['chest', 'Chest', 'spine.003', 'mixamorigSpine2'],
  head: ['head', 'Head', 'mixamorigHead'],
  handR: ['handR', 'hand.R', 'hand_R', 'Hand.R', 'mixamorigRightHand'],
  upperarmR: ['upperarmR', 'upperarm.R', 'upper_arm.R', 'upperarm_R', 'mixamorigRightArm'],
};

export function createRider({ variant = 'bandit', tint = null } = {}) {
  const g = assets.models.rider;
  if (g) {
    const r = new Animated(g, tint);
    const show = {
      bandit: ['Body', 'Hat_Wide', 'Bandana', 'Duster'],
      bandit2: ['Body', 'Hat_Bowler', 'Bandana', 'Poncho'],
      bandit3: ['Body', 'Hat_Wide', 'Poncho'],
      driver: ['Body', 'Hat_Bowler', 'Duster'],
      player: ['Body', 'Hat_Wide', 'Duster'],
      gunman: ['Body', 'Hat_Wide', 'Duster', 'Bandana'],
    }[variant] || ['Body'];
    for (const n of ['Hat_Wide', 'Hat_Bowler', 'Bandana', 'Duster', 'Poncho']) {
      const o = r.node(n); if (o) o.visible = show.includes(n);
    }
    r.bones = {};
    for (const [k, names] of Object.entries(BONE_ALIASES)) {
      for (const n of names) { const b = r.node(n); if (b) { r.bones[k] = b; break; } }
    }
    r.hand = r.bones.handR || r.root;
    r.kind = 'glb';
    return r;
  }
  return fallbackRider(variant, tint);
}

function fallbackRider(variant, tint) {
  const root = new THREE.Group();
  const cloth = new THREE.MeshStandardMaterial({ color: variant === 'player' ? 0x5a4632 : variant === 'driver' ? 0x3a3a44 : 0x4a3a2c, roughness: 0.9 });
  if (tint) cloth.color.multiply(tint);
  const skin = new THREE.MeshStandardMaterial({ color: 0xc08a64, roughness: 0.7 });
  const hatM = new THREE.MeshStandardMaterial({ color: variant === 'bandit' ? 0x1e1712 : 0x6b5238, roughness: 0.85 });
  const hips = new THREE.Group(); root.add(hips);
  const spine = new THREE.Group(); spine.name = 'spine'; spine.position.y = 0.1; hips.add(spine);
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.45, 4, 8), cloth); torso.position.y = 0.35; spine.add(torso);
  const chest = new THREE.Group(); chest.name = 'chest'; chest.position.y = 0.5; spine.add(chest);
  const head = new THREE.Group(); head.name = 'head'; head.position.y = 0.3; chest.add(head);
  head.add(new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), skin));
  const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.03, 12), hatM); brim.position.y = 0.08; head.add(brim);
  const crown = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.16, 10), hatM); crown.position.y = 0.16; head.add(crown);
  const arm = new THREE.Group(); arm.name = 'upperarm.R'; arm.position.set(-0.24, 0.15, 0); chest.add(arm);
  const ua = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.5, 3, 6), cloth); ua.rotation.x = Math.PI / 2; ua.position.z = 0.28; arm.add(ua);
  const hand = new THREE.Group(); hand.name = 'hand.R'; hand.position.z = 0.6; arm.add(hand);
  const armL = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.45, 3, 6), cloth); armL.position.set(0.24, 0.0, 0.12); armL.rotation.x = 1; chest.add(armL);
  for (const x of [-0.12, 0.12]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.7, 3, 6), cloth);
    leg.position.set(x * 2.2, -0.2, 0.15); leg.rotation.x = 1.2; leg.rotation.z = x > 0 ? -0.5 : 0.5; hips.add(leg);
  }
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; } });
  let mode = 'Ride', t = 0, fallT = 0;
  return {
    kind: 'fallback', root, hand, bones: { spine, chest, head, handR: hand, upperarmR: arm },
    play(name) { mode = name; if (name === 'FallOff' || name === 'DieStanding') fallT = 0; },
    has: () => true,
    setSpeed() {},
    kick() {},
    update(dt) {
      t += dt;
      if (mode === 'FallOff' || mode === 'DieStanding') {
        fallT = Math.min(1, fallT + dt * 2);
        spine.rotation.x = -fallT * 1.3;
        return;
      }
      spine.rotation.x = 0;
      hips.position.y = Math.abs(Math.sin(t * 6)) * 0.05;
      arm.rotation.x = mode === 'RideAim' || mode === 'StandShoot' ? 0 : 1.2;
    },
  };
}

// ----------------------------------------------------------------- weapons
export function createWeapon(name) {
  const g = assets.models.weapons;
  if (g) {
    const src = findNode(g.scene, name);
    if (src) {
      const c = src.clone(true);
      c.position.set(0, 0, 0);
      c.traverse((o) => { if (o.isMesh) o.castShadow = true; });
      const muzzle = findNode(c, 'Muzzle_' + name) || c;
      return { root: c, muzzle };
    }
  }
  const root = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0x2a2b2e, metalness: 0.8, roughness: 0.35 });
  const wood = new THREE.MeshStandardMaterial({ color: 0x5a3219, roughness: 0.6 });
  const len = name === 'Schofield' ? 0.3 : 0.9;
  const barrel = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.05, len), metal); barrel.position.set(0, 0.06, len / 2); root.add(barrel);
  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, name === 'Schofield' ? 0.05 : 0.35), wood); grip.position.set(0, 0, name === 'Schofield' ? 0 : -0.1); root.add(grip);
  const muzzle = new THREE.Object3D(); muzzle.position.set(0, 0.06, len); root.add(muzzle);
  return { root, muzzle };
}
