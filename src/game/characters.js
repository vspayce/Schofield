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
    this.recoils = {};
    for (const clip of gltf.animations) {
      if (clip.name === 'Shoot' || clip.name === 'SeatShoot' || clip.name === 'ShootL') {
        // recoil layered on top of whatever pose is playing (SeatShoot is the
        // seated guard's, made against SeatAim; ShootL the left hand's)
        const add = THREE.AnimationUtils.makeClipAdditive(clip.clone());
        const a = this.recoils[clip.name] = this.mixer.clipAction(add);
        a.blendMode = THREE.AdditiveAnimationBlendMode;
        a.setLoop(THREE.LoopOnce, 1);
        continue;
      }
      this.actions[clip.name] = this.mixer.clipAction(clip);
    }
    this.recoil = this.recoils.Shoot;
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
  kick() {
    const rc = (this.current?.getClip().name === 'SeatAim' && this.recoils.SeatShoot) || this.recoil;
    if (rc) { rc.reset(); rc.weight = 1; rc.play(); }
  }
  kickL() { const rc = this.recoils.ShootL; if (rc) { rc.reset(); rc.weight = 1; rc.play(); } }
  update(dt) { this.mixer.update(dt); }
  node(name) { return findNode(this.root, name); }
}

// ------------------------------------------------------------------- horse
// `breed` picks horse_<breed>.glb (the coach team: clydesdale, clevelandbay,
// thoroughbred), falling back to the plain horse the riders use.
export function createHorse({ coat = new THREE.Color(1, 1, 1), saddle = true, harness = false, breed = null } = {}) {
  const g = (breed && assets.models['horse_' + breed]) || assets.models.horse;
  if (g) {
    const h = new Animated(g, coat);
    h.breed = g === assets.models.horse ? null : breed;
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
  handL: ['handL', 'hand.L', 'hand_L', 'Hand.L', 'mixamorigLeftHand'],
  forearmL: ['forearmL', 'forearm.L', 'forearm_L', 'mixamorigLeftForeArm'],
  upperarmL: ['upperarmL', 'upperarm.L', 'upper_arm.L', 'upperarm_L', 'mixamorigLeftArm'],
};

// Each look: the meshes it shows, and colour multiplied into shared pieces so
// one mesh can be several garments.  A caller's `tint` still multiplies the
// body and coat materials on top.  `townsman` and `drifter` keep the old Body;
// the old bandit names (townsfolk, rail hands, train crew) are rebuilt on
// Body_Man; the gang that robs the coach uses the outlaw looks.
const LOOKS = {
  townsman: { show: ['Body', 'Hat_Bowler', 'Duster'] },
  drifter: { show: ['Body', 'Hat_Wide', 'Duster'] }, // what the guard used to wear
  driver: { show: ['Body_Driver', 'Coat_Driver', 'Hat_Driver', 'Moustache_Walrus', 'Neckerchief_Driver', 'Watch_Driver'] },
  // Wells Fargo shotgun messenger: linen duster, dark creased hat, dark vest
  player: { show: ['Body_Man', 'Coat_Guard', 'Hat_Guard', 'Moustache_Guard'] },
  // the old bandit looks, now on the new body (townsfolk, rail hands, train crew)
  bandit: { show: ['Body_Man', 'Hat_Wide', 'Bandana_Man', 'Coat_Guard'], color: { Coat_Guard: [0.36, 0.31, 0.27] } },
  bandit2: { show: ['Body_Man', 'Hat_Bowler', 'Bandana_Man', 'Serape'] },
  bandit3: { show: ['Body_Man', 'Hat_Wide', 'Serape'] },
  gunman: { show: ['Body_Man', 'Hat_Wide', 'Coat_Guard', 'Bandana_Man'], color: { Coat_Guard: [0.5, 0.44, 0.38] } },
  // the gang
  outlaw: { show: ['Body_Man', 'Hat_Wide', 'Bandana_Man', 'Coat_Guard'], color: { Coat_Guard: [0.36, 0.31, 0.27], Hat_Wide: [0.7, 0.66, 0.62] } },
  sugarloaf: { show: ['Body_Man', 'Hat_Sugarloaf', 'Bandana_Man', 'Jacket'], color: { Bandana_Man: [0.45, 1.6, 3.4], Jacket: [0.92, 0.76, 0.55] } },
  vaquero: { show: ['Body_Man', 'Hat_Sombrero', 'Serape', 'Moustache_Vaquero'], color: { Body_Man: [0.92, 0.86, 0.8] } },
  reb: { show: ['Body_Man', 'Hat_Slouch', 'Jacket', 'Gauntlets'], color: { Hat_Slouch: [1.0, 0.85, 0.62], Jacket: [0.8, 0.82, 0.88] } },
  mountain: { show: ['Body_Man', 'Coat_Buffalo', 'Beard_Long', 'Hat_Wide'], color: { Hat_Wide: [0.55, 0.5, 0.46] } },
  pearl: { show: ['Body_Female', 'Hat_Slouch'], color: { Hat_Slouch: [1.1, 0.96, 0.8] } },
  // Black Bart (Charles Boles): flour sack, derby, linen duster over a dark suit
  bart: { show: ['Body_Man', 'Coat_Guard', 'Hat_Bowler', 'Mask_Sack'], color: { Body_Man: [0.5, 0.5, 0.55], Coat_Guard: [1.04, 1.04, 1.02] } },
  // townsfolk: 1880s day dresses (one of three at random), the marshal
  woman: { pick: ['woman_slate', 'woman_plum', 'woman_calico'] },
  woman_slate: { show: ['Body_Woman', 'Dress', 'Bonnet'], color: { Dress: [0.55, 0.6, 0.72], Bonnet: [0.9, 0.9, 0.95] } },
  woman_plum: { show: ['Body_Woman', 'Dress', 'Hat_Lady'], color: { Dress: [0.72, 0.4, 0.45], Hat_Lady: [0.55, 0.35, 0.4] } },
  woman_calico: { show: ['Body_Woman', 'Dress', 'Bonnet'], color: { Dress: [0.95, 0.82, 0.62], Bonnet: [1.0, 0.95, 0.85] } },
  lawman: { show: ['Body_Man', 'Coat_Guard', 'Hat_Lawman'], color: { Coat_Guard: [0.22, 0.21, 0.21] } },
  // Wild Bill: own body and face, black frock coat, flat hat, Navies in a red sash
  hickok: { show: ['Body_Hickok', 'Coat_Guard', 'Hat_Hickok', 'Colts_Hickok'], color: { Coat_Guard: [0.09, 0.087, 0.087] } },
};
// every look createRider knows (town.js reads VARIANTS, escort.js RIDER_VARIANTS)
export const RIDER_VARIANTS = Object.keys(LOOKS);
export const VARIANTS = RIDER_VARIANTS;

export function createRider({ variant = 'bandit', tint = null } = {}) {
  const g = assets.models.rider;
  if (g) {
    let look = LOOKS[variant] || { show: ['Body'] };
    if (look.pick) look = LOOKS[look.pick[Math.floor(Math.random() * look.pick.length)]];
    const r = new Animated(g, tint);
    r.root.traverse((o) => { if (o.isMesh) o.visible = look.show.includes(o.name); });
    for (const [n, c] of Object.entries(look.color || {})) {
      const o = r.node(n);
      if (o?.material) { o.material = o.material.clone(); o.material.color.multiply(new THREE.Color(...c)); }
    }
    r.bones = {};
    for (const [k, names] of Object.entries(BONE_ALIASES)) {
      for (const n of names) { const b = r.node(n); if (b) { r.bones[k] = b; break; } }
    }
    r.hand = r.bones.handR || r.root;
    r.handL = r.bones.handL || null;
    r.variant = variant;
    r.kind = 'glb';
    return r;
  }
  return fallbackRider(variant, tint);
}

function fallbackRider(variant, tint) {
  const root = new THREE.Group();
  const cloth = new THREE.MeshStandardMaterial({ color: variant === 'player' ? 0x5a4632 : variant === 'driver' ? 0x33302b : 0x4a3a2c, roughness: 0.9 });
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
// finish: RGB multiplier over the gun (weapons.glb is one texture atlas), so
// one revolver model can pass for blued, nickel or brass-framed guns.
export function createWeapon(name, { finish = null } = {}) {
  const g = assets.models.weapons;
  if (g) {
    const src = findNode(g.scene, name);
    if (src) {
      const c = src.clone(true);
      c.position.set(0, 0, 0);
      c.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = true;
        if (finish) {
          o.material = o.material.clone(); o.material.color.multiply(new THREE.Color(...finish));
        }
      });
      const muzzle = findNode(c, 'Muzzle_' + name) || c;
      // a gun may ship a moving sub-node (the Gatling's barrel cluster, whose
      // origin the exporter puts on the bore axis) — spin it about its own Z
      const barrels = findNode(c, name + '_Barrels');
      return { root: c, muzzle, spin: barrels ? (a) => { barrels.rotation.z += a; } : undefined };
    }
  }
  // no GLB (or no node by that name): primitive stand-ins, as elsewhere here
  if (name === 'Gatling') return gatling();
  const root = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0x2a2b2e, metalness: 0.8, roughness: 0.35 });
  if (finish) metal.color.multiply(new THREE.Color(...finish));
  const wood = new THREE.MeshStandardMaterial({ color: 0x5a3219, roughness: 0.6 });
  const len = name === 'Schofield' ? 0.3 : 0.9;
  const barrel = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.05, len), metal); barrel.position.set(0, 0.06, len / 2); root.add(barrel);
  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, name === 'Schofield' ? 0.05 : 0.35), wood); grip.position.set(0, 0, name === 'Schofield' ? 0 : -0.1); root.add(grip);
  const muzzle = new THREE.Object3D(); muzzle.position.set(0, 0.06, len); root.add(muzzle);
  return { root, muzzle };
}

// Six-barrel Gatling, held at the grip like the other guns (+Z = muzzle).
// `spin` turns the barrel cluster; the player calls it while firing.
function gatling() {
  const root = new THREE.Group();
  const brass = new THREE.MeshStandardMaterial({ color: 0xb08a3e, metalness: 0.85, roughness: 0.35 });
  const steel = new THREE.MeshStandardMaterial({ color: 0x2b2c30, metalness: 0.8, roughness: 0.4 });
  const wood = new THREE.MeshStandardMaterial({ color: 0x5a3219, roughness: 0.7 });
  const cyl = (r, h, m, seg = 12) => new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg).rotateX(Math.PI / 2), m);
  const housing = cyl(0.09, 0.3, brass); housing.position.set(0, 0.08, 0.1); root.add(housing);
  const barrels = new THREE.Group(); barrels.position.set(0, 0.08, 0.25); root.add(barrels);
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    const b = cyl(0.014, 0.75, steel, 6); b.position.set(Math.cos(a) * 0.05, Math.sin(a) * 0.05, 0.37); barrels.add(b);
  }
  for (const z of [0.2, 0.5, 0.72]) { const band = cyl(0.07, 0.03, brass); band.position.z = z; barrels.add(band); }
  const hopper = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.14, 0.08), brass); hopper.position.set(0, 0.2, 0.08); root.add(hopper);
  const crank = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.02, 0.12), steel); crank.position.set(0.11, 0.08, 0.02); root.add(crank);
  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, 0.06), wood); grip.position.set(0, 0, -0.02); root.add(grip);
  root.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  const muzzle = new THREE.Object3D(); muzzle.position.set(0, 0.08, 1.0); root.add(muzzle);
  return { root, muzzle, spin: (a) => { barrels.rotation.z += a; } };
}
