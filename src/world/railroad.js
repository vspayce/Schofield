// A railroad crossing being built: graded ballast, ties, rail, a water tower and
// a gang of workers still laying track. Rail runs through the crossing and stops
// at the railhead just past it, where the gang is working. No trains yet.
//
// All of it is procedural except the water tower, which is the town kit's, and
// the workers, who are rider models posed with a sledge.
import * as THREE from 'three';
import { assets, findNode } from '../core/assets.js';
import { createRider } from '../game/characters.js';
import { mulberry32 } from '../core/noise.js';

const _v = new THREE.Vector3();

// how far the line runs either side of the road before it fades out
const REACH = 150;
const TIE_GAP = 0.62;

export class Railroad {
  constructor(route, scene, def) {
    this.route = route; this.scene = scene;
    this.group = new THREE.Group(); scene.add(this.group);
    this.workers = [];
    this.solids = [];
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

    // Track is laid from one side, through the crossing, and the gang is still
    // working at the railhead just past the road. Beyond that, only graded bed.
    this.built = 24 + rnd() * 18;
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
    let best = null;
    for (let k = 0; k < 26; k++) {
      const s = Math.round(THREE.MathUtils.clamp(want + (rnd() - 0.5) * 2 * span, 140, R.len - 200));
      const f = R.frame(s, {});
      const ang = Math.atan2(f.rx, f.rz) + (rnd() - 0.5) * 0.45;
      const dir = new THREE.Vector3(Math.sin(ang), 0, Math.cos(ang));
      // sample terrain along the corridor and fit a line through it
      const us = [], ys = [];
      for (let u = -90; u <= 90; u += 10) {
        const x = f.x + dir.x * u, z = f.z + dir.z * u;
        us.push(u); ys.push(R.height(x, z));
      }
      const n = us.length, my = ys.reduce((a, b) => a + b, 0) / n;
      let num = 0, den = 0;
      for (let i = 0; i < n; i++) { num += us[i] * (ys[i] - my); den += us[i] * us[i]; }
      const slope = num / den;
      // residual off that best-fit line = how much cut and fill the line needs
      let resid = 0;
      for (let i = 0; i < n; i++) resid += Math.abs(ys[i] - (my + slope * us[i]));
      const score = -resid / n - Math.abs(slope) * 40;
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

  // The graded bed: a level top at rail height with embankment shoulders sloping
  // down to meet the ground. Where the ground falls away the fill gets deeper and
  // the shoulders wider, which is what makes a railroad read as engineered
  // rather than draped over the landscape.
  _ballast(rnd) {
    const R = this.route;
    const segs = Math.floor((REACH * 2) / 3);
    const pos = [], idx = [], uvs = [];
    const side = new THREE.Vector3(this.dir.z, 0, -this.dir.x);
    const TOP = 2.5;          // half-width of the ballast top
    const SLOPE = 1.7;        // embankment run per unit rise
    const at = (u, off, y) => {
      const x = this.centre.x + this.dir.x * u + side.x * off;
      const z = this.centre.z + this.dir.z * u + side.z * off;
      return [x, y === undefined ? R.height(x, z) : y, z];
    };
    for (let i = 0; i <= segs; i++) {
      const u = -REACH + (i / segs) * REACH * 2;
      const gy = this._gradeY(u);
      const fade = Math.min(1, (REACH - Math.abs(u)) / 30);
      // how far the bed stands proud of the ground here
      const gnd = R.height(this.centre.x + this.dir.x * u, this.centre.z + this.dir.z * u);
      const fill = Math.max(0, (gy - gnd)) * fade;
      const top = TOP * fade;
      const toe = top + fill * SLOPE + 0.4;
      const topY = gnd + fill;     // = gy where there is fill, ground where cut
      for (const [off, y] of [[-toe, undefined], [-top, topY], [top, topY], [toe, undefined]]) {
        const v = at(u, off, y);
        pos.push(v[0], v[1], v[2]);
        uvs.push((off / 5) + 0.5, u / 5);
      }
      if (i < segs) {
        const b0 = i * 4;
        for (let q = 0; q < 3; q++) {
          idx.push(b0 + q, b0 + q + 1, b0 + q + 4, b0 + q + 1, b0 + q + 5, b0 + q + 4);
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
    m.receiveShadow = true; m.castShadow = true;
    this.group.add(m);
  }

  // sleepers, laid from the far side through the crossing to the railhead
  _ties(rnd) {
    const n = Math.floor((REACH + this.built) / TIE_GAP);
    if (n <= 0) return;
    const geo = new THREE.BoxGeometry(0.22, 0.14, 2.4);
    const mat = new THREE.MeshStandardMaterial({ color: 0x3a2a1c, roughness: 0.95 });
    const im = new THREE.InstancedMesh(geo, mat, n);
    im.castShadow = true; im.receiveShadow = true;
    const q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), mtx = new THREE.Matrix4();
    const yaw = Math.atan2(this.dir.x, this.dir.z);
    let k = 0;
    for (let i = 0; i < n; i++) {
      const u = -REACH + i * TIE_GAP;
      if (u > this.built) break;
      const p = this._at(u, _v.clone());
      p.y += 0.2;
      // the last few are dropped in loose and crooked
      const near = u > this.built - 9;
      q.setFromEuler(new THREE.Euler(0, yaw + (near ? (rnd() - 0.5) * 0.35 : (rnd() - 0.5) * 0.03), near ? (rnd() - 0.5) * 0.12 : 0, 'YXZ'));
      mtx.compose(p, q, sc);
      im.setMatrixAt(k++, mtx);
    }
    im.count = k;
    im.instanceMatrix.needsUpdate = true;
    this.group.add(im);
  }

  // two rails, ending where the gang got to
  _rails() {
    const mat = new THREE.MeshStandardMaterial({ color: 0x6b5a4a, roughness: 0.55, metalness: 0.7 });
    const side = new THREE.Vector3(this.dir.z, 0, -this.dir.x);
    for (const k of [-0.717, 0.717]) {          // standard gauge, near enough
      const pts = [];
      for (let u = -REACH; u <= this.built; u += 3) {
        const c = this._at(u, _v.clone());
        pts.push(new THREE.Vector3(c.x + side.x * k, c.y + 0.31, c.z + side.z * k));
      }
      if (pts.length < 2) continue;
      const curve = new THREE.CatmullRomCurve3(pts);
      const geo = new THREE.TubeGeometry(curve, pts.length, 0.055, 4, false);
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = true;
      this.group.add(m);
    }
  }

  // water tower, material stacks and the gang itself
  _camp(rnd, def) {
    const side = new THREE.Vector3(this.dir.z, 0, -this.dir.x);
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
      const base = this._at(this.built - 6 - st * 5, new THREE.Vector3()).addScaledVector(side, (rnd() < 0.5 ? -1 : 1) * (3.6 + rnd() * 1.6));
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
          const p = this._at(this.built - 2 - rnd() * 18, new THREE.Vector3())
            .addScaledVector(side, (rnd() < 0.5 ? -1 : 1) * (3 + rnd() * 5));
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
      const w = createRider({ variant: i % 3 === 0 ? 'driver' : 'gunman' });
      const u = this.built - 1 - rnd() * 12;
      const p = this._at(u, new THREE.Vector3()).addScaledVector(side, (i % 2 ? 1 : -1) * (1.4 + rnd() * 2.6));
      p.y = this.route.height(p.x, p.z);
      w.root.position.copy(p);
      // face the rails
      w.root.rotation.y = Math.atan2(this.dir.x, this.dir.z) + (i % 2 ? -Math.PI / 2 : Math.PI / 2) + (rnd() - 0.5) * 0.4;
      if (w.has('StandIdle')) w.play('StandIdle');
      // a sledge in the near hand for the ones actually working
      const swings = i < n - 2;
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
