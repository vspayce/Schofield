// Six-horse hitch gear drawn between the coach and the team: the pole run out
// to its head, swing bar and lead bar with their singletrees, the lead chain,
// every horse's traces, the wheelers' pole straps and the driver's six lines.
// The team follows the road on its own (not parented to the coach), so all of
// it is rebuilt in world space every frame as flat straps in one draw call.
// Attachment points come from empties in the breed GLBs (Trace_L, Terret_L,
// HameTerret_L, Bit_L, HeadRing_L, PoleStrap ...), with rough fallbacks.
import * as THREE from 'three';

const UP = new THREE.Vector3(0, 1, 0);
// horse-local fallbacks (three.js: x left, y up, z forward) for GLBs without the empties
const FALLBACK = {
  Trace: [0.3, 1.0, -0.6], Terret: [0.085, 1.7, 0.2], HameTerret: [0.2, 1.55, 0.7],
  Bit: [0.085, 1.6, 1.45], HeadRing: [0.06, 2.0, 1.1], PoleStrap: [0, 1.25, 0.9],
};
const LEATHER = new THREE.Color(0x221c17), WOOD = new THREE.Color(0xa8843a), IRON = new THREE.Color(0x3a3a3c);
// the coach's own singletrees on the splinter bar (coach-local), where the wheelers' traces hook on
const SINGLETREES = [new THREE.Vector3(0.55, 0.655, 1.88), new THREE.Vector3(-0.55, 0.655, 1.88)];

class Straps {
  constructor(maxSeg) {
    this.max = maxSeg;
    this.pos = new Float32Array(maxSeg * 48);
    this.nrm = new Float32Array(maxSeg * 48);
    this.col = new Float32Array(maxSeg * 48);
    const idx = new Uint16Array(maxSeg * 24);
    for (let i = 0; i < maxSeg * 4; i++) idx.set([i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3], i * 6);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('normal', new THREE.BufferAttribute(this.nrm, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('color', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage));
    g.setIndex(new THREE.BufferAttribute(idx, 1));
    this.mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0.05, side: THREE.DoubleSide }));
    this.mesh.frustumCulled = false;
    this.mesh.castShadow = true;
    this.n = 0;
    this._t = new THREE.Vector3(); this._s = new THREE.Vector3(); this._u = new THREE.Vector3();
    this._c = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  }
  begin() { this.n = 0; }
  // a strap w wide, t thick along pts; its width lies across `up` (default: flat, facing up)
  line(pts, w, t, col, up = UP) {
    const { _t: T, _s: S, _u: U, _c: c } = this;
    for (let i = 0; i + 1 < pts.length && this.n < this.max; i++) {
      const a = pts[i], b = pts[i + 1];
      T.subVectors(b, a); if (T.lengthSq() < 1e-8) continue; T.normalize();
      S.crossVectors(T, up); if (S.lengthSq() < 1e-6) S.set(1, 0, 0); S.normalize();
      U.crossVectors(S, T);
      c[0].copy(S).multiplyScalar(w / 2).addScaledVector(U, t / 2);
      c[1].copy(S).multiplyScalar(-w / 2).addScaledVector(U, t / 2);
      c[2].copy(S).multiplyScalar(-w / 2).addScaledVector(U, -t / 2);
      c[3].copy(S).multiplyScalar(w / 2).addScaledVector(U, -t / 2);
      const o = this.n * 48, P = this.pos, Nm = this.nrm, Cl = this.col;
      for (let k = 0; k < 4; k++) {
        const p = c[k], q = c[(k + 1) % 4];
        const nv = k === 0 || k === 2 ? U : S, sg = k === 0 || k === 3 ? 1 : -1;
        const base = o + k * 12;
        const ends = [a, a, b, b], offs = [p, q, q, p];
        for (let j = 0; j < 4; j++) {
          const i3 = base + j * 3, e = ends[j], f = offs[j];
          P[i3] = e.x + f.x; P[i3 + 1] = e.y + f.y; P[i3 + 2] = e.z + f.z;
          Nm[i3] = nv.x * sg; Nm[i3 + 1] = nv.y * sg; Nm[i3 + 2] = nv.z * sg;
          Cl[i3] = col.r; Cl[i3 + 1] = col.g; Cl[i3 + 2] = col.b;
        }
      }
      this.n++;
    }
  }
  end() {
    const g = this.mesh.geometry;
    g.setDrawRange(0, this.n * 24);
    g.attributes.position.needsUpdate = g.attributes.normal.needsUpdate = g.attributes.color.needsUpdate = true;
  }
}

export class Hitch {
  constructor(coach, scene) {
    this.coach = coach;
    this.straps = new Straps(320);
    scene.add(this.straps.mesh);
    const hz = coach.hitch ? coach.hitch.position : new THREE.Vector3(0, 0.92, 3.4);
    // the model's pole stops short of the Clydesdales' chests: run it on to a pole head
    const root = new THREE.Vector3(0, 0.585, 1.2), dir = new THREE.Vector3().subVectors(hz, root).normalize();
    this.poleHead = hz.clone().addScaledVector(dir, 1.15 / Math.max(0.2, dir.z));
    let gear = null;
    coach.model.traverse((o) => { if (!gear && o.isMesh && /gear/i.test(o.material?.name || '')) gear = o.material; });
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.034, hz.distanceTo(this.poleHead), 8), gear || new THREE.MeshStandardMaterial({ color: WOOD, roughness: 0.6 }));
    pole.position.copy(hz).lerp(this.poleHead, 0.5);
    pole.quaternion.setFromUnitVectors(UP, dir);
    const head = new THREE.Mesh(new THREE.CylinderGeometry(0.036, 0.03, 0.14, 8), new THREE.MeshStandardMaterial({ color: IRON, roughness: 0.5, metalness: 0.6 }));
    head.position.copy(this.poleHead); head.quaternion.copy(pole.quaternion);
    for (const m of [pole, head]) { m.castShadow = true; coach.root.add(m); }
    this.parts = [pole, head];
    this._pt = Array.from({ length: 256 }, () => new THREE.Vector3());  // per-frame scratch
    this._k = 0;
  }

  v() { return this._pt[this._k++ & 255]; }

  // world position of a named attachment on horse h ('Trace', '_L')
  at(h, name, side) {
    const key = name + side;
    h._hitch ??= {};
    if (!(key in h._hitch)) h._hitch[key] = h.node ? h.node(key) : null;
    const n = h._hitch[key], out = this.v();
    if (n) return n.getWorldPosition(out);
    const f = FALLBACK[name];
    return h.root.localToWorld(out.set(side === '_R' ? -f[0] : f[0], f[1], f[2]));
  }

  // evener centred at c across `fwd`, singletrees at its ends; each horse's traces to its singletree
  pair(pair, c, fwd, half) {
    const S = this.straps, side = this.v().crossVectors(UP, fwd).normalize();
    const eL = this.v().copy(c).addScaledVector(side, half), eR = this.v().copy(c).addScaledVector(side, -half);
    S.line([eL, eR], 0.06, 0.055, WOOD, fwd);
    [[pair[0], eL], [pair[1], eR]].forEach(([h, e]) => {
      const a = this.v().copy(e).addScaledVector(side, 0.3), b = this.v().copy(e).addScaledVector(side, -0.3);
      S.line([a, b], 0.045, 0.04, WOOD, fwd);
      this.trace(h, '_L', a); this.trace(h, '_R', b);
    });
  }

  trace(h, side, to) {
    const from = this.at(h, 'Trace', side), mid = this.v().lerpVectors(from, to, 0.5);
    mid.y -= 0.03;
    const across = this.v().subVectors(to, from).cross(UP).normalize();
    this.straps.line([from, mid, to], 0.042, 0.011, LEATHER, across);
  }

  update(hand, speed) {
    const c = this.coach, S = this.straps, team = c.team;
    if (team.length < 6) return;
    this._k = 0;
    c.root.updateMatrixWorld(true);
    for (const h of team) h.root.updateMatrixWorld(true);
    S.begin();
    const [wl, wr, sl, sr, ll, lr] = team;
    const ph = c.root.localToWorld(this.v().copy(this.poleHead));
    // wheelers: traces to the splinter-bar singletrees, pole straps to the pole head
    [wl, wr].forEach((h, i) => {
      const st = c.root.localToWorld(this.v().copy(SINGLETREES[i]));
      const fwd = this.v().copy(c.fwd);
      const side = this.v().crossVectors(UP, fwd).normalize();
      this.trace(h, '_L', this.v().copy(st).addScaledVector(side, 0.31));
      this.trace(h, '_R', this.v().copy(st).addScaledVector(side, -0.31));
      S.line([this.at(h, 'PoleStrap', ''), ph], 0.035, 0.01, LEATHER);
    });
    // swing bar hangs from the pole head; the lead chain runs on between the swings to the lead bar
    const sMid = this.v().addVectors(sl.root.position, sr.root.position).multiplyScalar(0.5);
    const sFwd = this.v().set(0, 0, 1).applyQuaternion(sl.root.quaternion).setY(0).normalize();
    const lFwd = this.v().set(0, 0, 1).applyQuaternion(ll.root.quaternion).setY(0).normalize();
    const swingBar = this.v().copy(ph).addScaledVector(c.fwd, 0.12);
    swingBar.y -= 0.03;
    this.pair([sl, sr], swingBar, this.v().subVectors(sMid, ph).setY(0).normalize(), 0.54);
    const leadBar = this.v().copy(sMid).addScaledVector(sFwd, 1.25);
    leadBar.y += 0.95;
    S.line([ph, this.v().lerpVectors(ph, leadBar, 0.5).setY((ph.y + leadBar.y) / 2 - 0.05), leadBar], 0.022, 0.022, IRON);
    this.pair([ll, lr], leadBar, lFwd, 0.52);
    // six lines, one pair per pair: through the terrets to the outside bit rings, coupling
    // reins crossing to the inside rings. Swing and lead lines pass the wheelers' rein drops,
    // lead lines the swings' as well.
    const sagK = 0.1 * Math.max(0.3, 1 - speed / 26);
    for (const [side, inner, w, s, l, ow, os, ol] of [['_L', '_R', wl, sl, ll, wr, sr, lr], ['_R', '_L', wr, sr, lr, wl, sl, ll]]) {
      for (const [h, other, via] of [[w, ow, []], [s, os, [w]], [l, ol, [w, s]]]) {
        const pts = [hand];
        // lead lines ride a little higher through the rings, so the fan rises forward
        for (const v of via) { const r = this.at(v, 'HeadRing', side); if (h === l) r.y += 0.1; pts.push(r); }
        pts.push(this.at(h, 'Terret', side), this.at(h, 'HameTerret', side), this.at(h, 'Bit', side));
        // the long first span sags a little, less the harder they pull
        const a = pts[0], b = pts[1], d = a.distanceTo(b), run = [a];
        for (let j = 1; j < 4; j++) {
          const t = j / 4, p = this.v().lerpVectors(a, b, t);
          p.y -= Math.sin(t * Math.PI) * sagK * d / 4;
          run.push(p);
        }
        S.line(run.concat(pts.slice(1)), 0.03, 0.007, LEATHER);
        S.line([this.at(h, 'HameTerret', inner), this.at(other, 'Bit', inner)], 0.025, 0.006, LEATHER);
      }
    }
    S.end();
  }

  dispose() {
    this.straps.mesh.removeFromParent();
    this.straps.mesh.geometry.dispose(); this.straps.mesh.material.dispose();
    for (const m of this.parts) { m.removeFromParent(); m.geometry.dispose(); }
  }
}
