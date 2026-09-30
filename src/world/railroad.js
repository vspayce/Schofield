// A railroad crossing: graded ballast, ties, rail, a water tower and a section
// gang. On most routes the line is still being built — rail runs through the
// crossing and stops at the railhead just past it, where the gang is working.
// Where the route runs a train (`railroad.train`), the line is finished end to
// end and the gang stands well back from it; the train itself is in train.js.
//
// All of it is procedural except the water tower, which is the town kit's, and
// the workers, who are rider models posed with a sledge.
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { createRider } from '../game/characters.js';
import { ROAD_HALF } from './route.js';
import { mulberry32 } from '../core/noise.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const _v = new THREE.Vector3();

// how far the line runs either side of the road before it fades out; a line
// with traffic runs far enough that the train comes and goes in the haze
const REACH = 150, REACH_TRAIN = 360;
const TIE_GAP = 0.62;
// half-width of the land graded flat for the bed
const BED_HALF = 4;

export class Railroad {
  constructor(route, scene, def) {
    this.route = route; this.scene = scene;
    this.group = new THREE.Group(); scene.add(this.group);
    this.workers = [];
    this.solids = [];
    this.hasTrain = !!def.train;
    const REACHV = this.reach = this.hasTrain ? REACH_TRAIN : REACH;
    const rnd = mulberry32(route.def.seed + 17);
    // A railroad is graded, not draped over hills, so it wants flat ground.
    // Search near the requested point for the corridor with the least fall.
    const want = Math.round(route.len * (def.at ?? 0.6));
    const pick = this._site(want, rnd);
    const s = this.s = pick.s;
    this.dir = pick.dir;
    const f = route.frame(s, {});
    this.centre = new THREE.Vector3(f.x, route.roadHeightAt(s), f.z);
    // Grade: level through the crossing so the road meets it flush, then a
    // gentle ruling gradient away. Real track never exceeds a couple of percent.
    this.grade = THREE.MathUtils.clamp(pick.slope, -0.018, 0.018);
    // how the road meets the line: dt = along-road per metre of rail, dr =
    // across-road per metre of rail (the crossing collision works from these)
    this.dt = this.dir.x * f.tx + this.dir.z * f.tz;
    this.dr = this.dir.x * f.rx + this.dir.z * f.rz;
    this.side = new THREE.Vector3(this.dir.z, 0, -this.dir.x);
    // cut the land to grade along the line (see Route.height)
    route.setRail({ x: this.centre.x, z: this.centre.z, dx: this.dir.x, dz: this.dir.z, y: this.centre.y, grade: this.grade, reach: REACHV, half: BED_HALF });

    // Track is laid from one side, through the crossing, and the gang is still
    // working at the railhead just past the road. Beyond that, only graded bed.
    // A line with a train on it is finished; the gang's camp is near the road.
    this.built = this.hasTrain ? REACHV : 24 + rnd() * 18;
    this.campU = this.hasTrain ? 16 + rnd() * 12 : this.built;
    this._ballast(rnd);
    this._ties(rnd);
    this._rails();
    this._camp(rnd, def);
  }

  // Score candidate crossings within +/-8% of the route for how flat the rail
  // corridor is, and take the best. Returns its s, direction and best-fit slope.
  _site(want, rnd) {
    const R = this.route;
    const span = Math.min(0.08 * R.len, 260);
    const far = this.reach;
    const rc = { d: 0, s: 0 };
    let best = null;
    for (let k = 0; k < 26; k++) {
      const s = Math.round(THREE.MathUtils.clamp(want + (rnd() - 0.5) * 2 * span, 140, R.len - 200));
      const f = R.frame(s, {});
      const ang = Math.atan2(f.rx, f.rz) + (rnd() - 0.5) * 0.45;
      const dir = new THREE.Vector3(Math.sin(ang), 0, Math.cos(ang));
      // sample terrain along the corridor and fit a line through it
      const us = [], ys = [];
      let clash = 0;
      for (let u = -far; u <= far; u += 10) {
        const x = f.x + dir.x * u, z = f.z + dir.z * u;
        us.push(u); ys.push(R.height(x, z));
        // the line must not cut the road (or a town on it) a second time
        if (Math.abs(u) > 30) {
          R.roadCoords(x, z, rc);
          if (rc.s >= 0 && Math.abs(rc.d) < 30 && Math.abs(rc.s - s) > 35) clash++;
        }
      }
      if (R.inTown(s) || (R.townRange && s > R.townRange.s0 - 120 && s < R.townRange.s1 + 120)) clash += 5;
      const n = us.length, my = ys.reduce((a, b) => a + b, 0) / n;
      let num = 0, den = 0;
      for (let i = 0; i < n; i++) { num += us[i] * (ys[i] - my); den += us[i] * us[i]; }
      const slope = num / den;
      // residual off that best-fit line = how much cut and fill the line needs
      let resid = 0;
      for (let i = 0; i < n; i++) resid += Math.abs(ys[i] - (my + slope * us[i]));
      const score = -resid / n - Math.abs(slope) * 40 - clash * 50;
      if (!best || score > best.score) best = { s, dir, slope, score };
    }
    return best;
  }

  // the graded rail height `u` metres from the crossing — a straight ruling
  // gradient, NOT the terrain
  _gradeY(u) { return this.centre.y + this.grade * u; }

  // where the line is, `u` metres from the crossing point along the rails
  _at(u, out = new THREE.Vector3()) {
    out.copy(this.centre).addScaledVector(this.dir, u);
    out.y = this._gradeY(u);
    return out;
  }

  // The ballast: a raised stone bed with sloped shoulders. The land under it
  // has already been cut or filled to grade (Route.height), so this only has
  // to sit on a level formation; its toes tuck just below the ground.
  _ballast() {
    const REACHV = this.reach;
    const segs = Math.floor((REACHV * 2) / 4);
    const pos = [], idx = [], uvs = [];
    const side = this.side;
    const prof = [[-3.4, -0.5], [-2.0, 0.07], [2.0, 0.07], [3.4, -0.5]];
    for (let i = 0; i <= segs; i++) {
      const u = -REACHV + (i / segs) * REACHV * 2;
      const gy = this._gradeY(u);
      const fade = Math.min(1, (REACHV - Math.abs(u)) / 12);
      for (const [off, dy] of prof) {
        const x = this.centre.x + this.dir.x * u + side.x * off * (0.3 + 0.7 * fade);
        const z = this.centre.z + this.dir.z * u + side.z * off * (0.3 + 0.7 * fade);
        pos.push(x, gy + (dy + 0.5) * fade - 0.5, z);
        uvs.push((off / 5) + 0.5, u / 5);
      }
      if (i < segs) {
        const b0 = i * 4;
        for (let q = 0; q < 3; q++) {
          idx.push(b0 + q, b0 + q + 4, b0 + q + 1, b0 + q + 1, b0 + q + 4, b0 + q + 5);   // wound to face up
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    const tex = assets.textures.gravel;
    if (tex) tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    const mat = new THREE.MeshStandardMaterial({ color: 0x6d6459, roughness: 1, map: tex || null });
    const m = new THREE.Mesh(geo, mat);
    m.receiveShadow = true;
    this.group.add(m);
  }

  // sleepers, laid from the far side through the crossing to the railhead
  _ties(rnd) {
    const n = Math.floor((this.reach + this.built) / TIE_GAP);
    if (n <= 0) return;
    const geo = new THREE.BoxGeometry(0.22, 0.14, 2.4);
    const mat = new THREE.MeshStandardMaterial({ color: 0x3a2a1c, roughness: 0.95 });
    const im = new THREE.InstancedMesh(geo, mat, n);
    im.castShadow = false; im.receiveShadow = true;
    const q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), mtx = new THREE.Matrix4();
    const yaw = Math.atan2(this.dir.x, this.dir.z);
    let k = 0;
    for (let i = 0; i < n; i++) {
      const u = -this.reach + i * TIE_GAP;
      if (u > this.built) break;
      const p = this._at(u, _v.clone());
      p.y += 0.2;
      // the last few are dropped in loose and crooked
      const near = !this.hasTrain && u > this.built - 9;
      q.setFromEuler(new THREE.Euler(0, yaw + Math.PI / 2 + (near ? (rnd() - 0.5) * 0.35 : (rnd() - 0.5) * 0.03), near ? (rnd() - 0.5) * 0.12 : 0, 'YXZ'));
      mtx.compose(p, q, sc);
      im.setMatrixAt(k++, mtx);
    }
    im.count = k;
    im.instanceMatrix.needsUpdate = true;
    this.group.add(im);
  }

  // two rails, ending where the gang got to: a flat-bottomed rail profile run
  // straight down the grade, with the bright worn head as its own strip
  _rails() {
    const iron = new THREE.MeshStandardMaterial({ color: 0x4a3c32, roughness: 0.7, metalness: 0.6 });
    const shine = new THREE.MeshStandardMaterial({ color: 0xb8b2aa, roughness: 0.28, metalness: 0.95 });
    const u0 = -this.reach, u1 = this.built, len = u1 - u0;
    if (len < 2) return;
    const parts = { iron: [], shine: [] };
    for (const k of [-0.717, 0.717]) {
      // foot, web, head (in rail-local x, y); length along z
      for (const [w, h, y, key] of [[0.1, 0.016, 0.278, 'iron'], [0.018, 0.05, 0.31, 'iron'], [0.056, 0.024, 0.345, 'iron'], [0.044, 0.006, 0.36, 'shine']]) {
        const g = new THREE.BoxGeometry(w, h, len);
        g.translate(k, y, (u0 + u1) / 2);
        parts[key].push(g);
      }
    }
    // plank the crossing, between and outside the rails, flush with the rail heads
    const planks = [];
    const ext = (ROAD_HALF + 0.6) / Math.max(0.3, Math.abs(this.dr));
    for (const x of [-1.25, -0.95, -0.5, -0.17, 0.17, 0.5, 0.95, 1.25]) {
      const g = new THREE.BoxGeometry(0.28, 0.1, ext * 2 - Math.abs(x) * 0.1);
      g.translate(x, 0.305, 0);
      planks.push(g);
    }
    parts.wood = planks;
    const wood = new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.92 });
    const yaw = Math.atan2(this.dir.x, this.dir.z);
    for (const [key, mat] of [['iron', iron], ['shine', shine], ['wood', wood]]) {
      const geo = mergeGeometries(parts[key]);
      const m = new THREE.Mesh(geo, mat);
      m.position.set(this.centre.x, this.centre.y, this.centre.z);
      m.rotation.set(-Math.atan(this.grade), yaw, 0, 'YXZ');
      m.castShadow = key === 'iron'; m.receiveShadow = true;
      this.group.add(m);
    }
  }

  // water tower, material stacks and the gang itself
  _camp(rnd, def) {
    const side = this.side, T = this.hasTrain;
    const t = assets.models.town, pr = assets.models.props;

    // water tower, set back from the line on the far side of the road
    const tower = t && findNode(t.scene, 'WaterTower');
    if (tower) {
      const c = tower.clone(true);
      const p = this._at(-34, new THREE.Vector3()).addScaledVector(side, 9);
      p.y = this.route.height(p.x, p.z) - 0.05;
      c.position.copy(p);
      c.rotation.y = Math.atan2(this.dir.x, this.dir.z) + Math.PI / 2;
      c.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
      this.group.add(c);
      c.updateMatrixWorld(true);
      this.solids.push(new THREE.Box3().setFromObject(c));
    }

    // stacks of spare ties and a few barrels and crates near the railhead
    const tieGeo = new THREE.BoxGeometry(0.22, 0.14, 2.4);
    const tieMat = new THREE.MeshStandardMaterial({ color: 0x4a3524, roughness: 0.95 });
    for (let st = 0; st < 3; st++) {
      // with trains running, everything stands clear of the swept envelope
      // (~1.6 m either side of the rails) with a good margin
      const su = T ? this.campU + st * 5 : this.built - 6 - st * 5;
      const base = this._at(su, new THREE.Vector3()).addScaledVector(side, (rnd() < 0.5 ? -1 : 1) * ((T ? 4.8 : 3.6) + rnd() * 1.6));
      base.y = this.route.height(base.x, base.z);
      const rows = 3 + Math.floor(rnd() * 3);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < 3; c++) {
          const m = new THREE.Mesh(tieGeo, tieMat);
          m.position.set(base.x, base.y + 0.07 + r * 0.15, base.z);
          m.position.addScaledVector(this.dir, (c - 1) * 0.26 + (rnd() - 0.5) * 0.05);
          m.rotation.y = Math.atan2(this.dir.x, this.dir.z) + (r % 2 ? Math.PI / 2 : 0) + (rnd() - 0.5) * 0.06;
          m.castShadow = true; m.receiveShadow = true;
          this.group.add(m);
        }
      }
    }
    if (pr) {
      for (const [name, count] of [['Barrel', 4], ['Crate', 5]]) {
        const src = findNode(pr.scene, name);
        if (!src) continue;
        for (let i = 0; i < count; i++) {
          const o = src.clone(true);
          const p = this._at(T ? this.campU - 2 + rnd() * 18 : this.built - 2 - rnd() * 18, new THREE.Vector3())
            .addScaledVector(side, (rnd() < 0.5 ? -1 : 1) * ((T ? 4.2 : 3) + rnd() * 4.5));
          p.y = this.route.height(p.x, p.z);
          o.position.copy(p);
          o.rotation.y = rnd() * 6.3;
          o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
          this.group.add(o);
        }
      }
    }

    // the gang: a few men at the railhead swinging, a couple standing by
    const n = def.workers ?? 6;
    for (let i = 0; i < n; i++) {
      const w = createRider({ variant: i % 3 === 0 ? 'townsman' : 'gunman' });
      const u = T ? this.campU - 3 + rnd() * 14 : this.built - 1 - rnd() * 12;
      const p = this._at(u, new THREE.Vector3()).addScaledVector(side, (i % 2 ? 1 : -1) * (T ? 3.6 + rnd() * 2.4 : 1.4 + rnd() * 2.6));
      p.y = this.route.height(p.x, p.z);
      w.root.position.copy(p);
      // face the rails
      w.root.rotation.y = Math.atan2(this.dir.x, this.dir.z) + (i % 2 ? -Math.PI / 2 : Math.PI / 2) + (rnd() - 0.5) * 0.4;
      if (w.has('StandIdle')) w.play('StandIdle');
      // a sledge in the near hand for the ones actually working
      // (with a train due they've stepped off the line to let it by)
      const swings = !T && i < n - 2;
      if (swings && w.hand) {
        const sledge = new THREE.Group();
        const haft = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.026, 0.9, 6),
          new THREE.MeshStandardMaterial({ color: 0x8a6a42, roughness: 0.9 }));
        haft.rotation.x = Math.PI / 2; haft.position.z = 0.45; sledge.add(haft);
        const headM = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.09, 0.26),
          new THREE.MeshStandardMaterial({ color: 0x3a3a3e, roughness: 0.5, metalness: 0.7 }));
        headM.position.z = 0.9; headM.rotation.y = Math.PI / 2; sledge.add(headM);
        sledge.traverse((m) => { if (m.isMesh) m.castShadow = true; });
        w.hand.add(sledge);
      }
      w.swing = swings ? { phase: rnd() * 6.3, rate: 1.5 + rnd() * 0.7 } : null;
      this.scene.add(w.root);
      this.workers.push(w);
    }
  }

  // `coach` is optional: without it the gang still works, there's just no jolt
  update(dt, coach) {
    if (coach) {
      const over = Math.abs(coach.s - this.s) < 2.2;
      if (over && !this._jolted) {
        this._jolted = true;
        this.onJolt?.(Math.min(1, coach.speed / 15));
      } else if (!over && coach.s > this.s + 4) {
        this._jolted = false;                    // armed again if you come back
      }
    }
    for (const w of this.workers) {
      w.update(dt);
      const sw = w.swing, arm = w.bones?.upperarmR;
      if (!sw || !arm) continue;
      // raise slow, drive down fast — a sledge stroke, not a metronome
      sw.phase += dt * sw.rate;
      const t = (sw.phase % (Math.PI * 2)) / (Math.PI * 2);
      arm.rotation.x = t < 0.72 ? -1.5 + 1.9 * (t / 0.72) : 0.4 - 1.9 * ((t - 0.72) / 0.28);
    }
  }

  dispose() {
    this.scene.remove(this.group);
    this.workers.forEach((w) => this.scene.remove(w.root));
    this.group.traverse((o) => { if (o.isMesh) { o.geometry.dispose(); } });
    this.workers = [];
  }
}
