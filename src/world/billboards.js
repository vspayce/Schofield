// Roadside billboards you can shoot for a wagon repair.
//
// Two advertisers along the Overland roads — Greeley's Saloon and Minnie's
// Haberdashery. Put a round through the sign and the driver takes the hint:
// the coach is patched up on the spot. One repair per board, and they are
// spaced out, so this is a reward for noticing and shooting well rather than a
// tap you can lean on.
import * as THREE from 'three';
import { audio } from '../core/audio.js';
import { mulberry32 } from '../core/noise.js';

const _v = new THREE.Vector3();

// Board faces are drawn to a canvas rather than shipped as textures, so adding
// an advertiser costs nothing but a few lines here.
const ADS = [
  {
    id: 'greeley', repair: 18,
    top: "GREELEY'S", mid: 'SALOON', low: 'WHISKEY · BEER · BEDS',
    paper: '#e8d7a8', ink: '#5a1a12', accent: '#8a6a22',
  },
  {
    id: 'minnie', repair: 14,
    top: "MINNIE'S", mid: 'HABERDASHERY', low: 'HATS · CLOTH · NOTIONS',
    paper: '#dfe6dc', ink: '#2c4a3a', accent: '#8a2f4a',
  },
];

function adTexture(ad) {
  const W = 512, H = 256;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const x = c.getContext('2d');
  x.fillStyle = ad.paper; x.fillRect(0, 0, W, H);
  // sun-bleached blotches and a few boards' worth of grain
  for (let i = 0; i < 90; i++) {
    x.fillStyle = `rgba(${120 + Math.random() * 90 | 0},${100 + Math.random() * 80 | 0},70,${0.02 + Math.random() * 0.05})`;
    const r = 18 + Math.random() * 70;
    x.beginPath(); x.arc(Math.random() * W, Math.random() * H, r, 0, 6.3); x.fill();
  }
  x.strokeStyle = 'rgba(70,50,30,0.18)'; x.lineWidth = 2;
  for (let i = 1; i < 6; i++) { x.beginPath(); x.moveTo(0, i * H / 6); x.lineTo(W, i * H / 6); x.stroke(); }
  x.strokeStyle = ad.accent; x.lineWidth = 7;
  x.strokeRect(13, 13, W - 26, H - 26);
  x.textAlign = 'center';
  // shrink to fit rather than run off the board — HABERDASHERY is a long word
  const fit = (text, want, weight, maxW) => {
    let px = want;
    do { x.font = `${weight}${px}px Georgia, serif`; px -= 2; }
    while (px > 12 && x.measureText(text).width > maxW);
  };
  const inner = W - 66;
  x.fillStyle = ad.ink;
  fit(ad.top, 54, 'bold ', inner);
  x.fillText(ad.top, W / 2, 78);
  fit(ad.mid, 66, 'bold ', inner);
  x.fillText(ad.mid, W / 2, 150);
  x.fillStyle = ad.accent;
  fit(ad.low, 30, '', inner);
  x.fillText(ad.low, W / 2, 200);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

class Board {
  constructor(route, scene, ad, s, side) {
    this.route = route; this.scene = scene; this.ad = ad; this.s = s;
    this.used = false;
    const f = route.frame(s, {});
    const off = 13 + Math.random() * 5;
    const x = f.x + f.rx * off * side, z = f.z + f.rz * off * side;
    const y = route.height(x, z);
    this.root = new THREE.Group();
    this.root.position.set(x, y, z);
    // Face the coming coach, not straight across the road: square-on to the
    // road the board is edge-on the whole way in and only reads as you pass.
    // Aim at the road a good way back, which angles it like a real roadside sign.
    const toward = route.frame(Math.max(0, s - 45), {});
    this.root.rotation.y = Math.atan2(toward.x - x, toward.z - z);
    scene.add(this.root);

    const post = new THREE.MeshStandardMaterial({ color: 0x4a3524, roughness: 0.95 });
    const back = new THREE.MeshStandardMaterial({ color: 0x6b5336, roughness: 1 });
    const W = 7.4, H = 3.7, base = 2.6;
    for (const px of [-W / 2 + 0.5, W / 2 - 0.5]) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.28, base + H, 0.28), post);
      p.position.set(px, (base + H) / 2, 0);
      p.castShadow = true; this.root.add(p);
    }
    // bracing
    for (const sx of [-1, 1]) {
      const br = new THREE.Mesh(new THREE.BoxGeometry(0.18, 3.2, 0.18), post);
      br.position.set(sx * (W / 2 - 0.9), base * 0.8, -0.9);
      br.rotation.x = 0.5; br.castShadow = true; this.root.add(br);
    }
    const panel = new THREE.Mesh(new THREE.BoxGeometry(W, H, 0.16), [
      back, back, back, back,
      new THREE.MeshStandardMaterial({ map: adTexture(ad), roughness: 0.92 }), back,
    ]);
    panel.position.set(0, base + H / 2, 0.02);
    panel.castShadow = true; panel.receiveShadow = true;
    this.root.add(panel);
    this.panel = panel;

    // hit sphere over the face
    this.centre = new THREE.Vector3(0, base + H / 2, 0.1).applyEuler(this.root.rotation).add(this.root.position);
    this.radius = Math.max(W, H) * 0.42;
  }

  // ray/sphere against the sign face
  hit(origin, dir, range) {
    if (this.used) return null;
    const oc = _v.subVectors(origin, this.centre);
    const b = oc.dot(dir), c = oc.lengthSq() - this.radius * this.radius;
    const h = b * b - c;
    if (h < 0) return null;
    const t = -b - Math.sqrt(h);
    if (t <= 0 || t > range) return null;
    return { board: this, t, point: origin.clone().addScaledVector(dir, t) };
  }

  strike(game, point) {
    this.used = true;
    const before = game.coach.hp;
    game.coach.hp = Math.min(100, game.coach.hp + this.ad.repair);
    const got = Math.round(game.coach.hp - before);
    audio.play('hit_wood_1', { position: point, volume: 1, pitch: 0.85 });
    audio.play('bell_town', { volume: 0.35, pitch: 1.5, delay: 0.1 });
    game.fx.splinters(point, _v.set(0, 0, 1));
    game.hud.banner(this.ad.mid, got > 0 ? `Wagon patched +${got}` : 'Wagon already sound', 1.8);
    // a shot-out board reads as shot out
    this.panel.material[4].color.setScalar(0.55);
  }

  dispose() { this.scene.remove(this.root); }
}

export class Billboards {
  constructor(route, scene, def) {
    this.route = route; this.scene = scene;
    this.list = [];
    const rnd = mulberry32((route.def.seed || 1) + 41);
    const n = def.count ?? 3;
    this.adOffset = rnd() < 0.5 ? 0 : 1;
    const first = def.from ?? 0.16, last = def.to ?? 0.9;
    for (let i = 0; i < n; i++) {
      const t = first + (last - first) * ((i + 0.5) / n) + (rnd() - 0.5) * 0.05;
      const s = route.len * t;
      if (s < 80 || s > route.len - 120) continue;
      const ad = ADS[(i + this.adOffset) % ADS.length];   // alternate, offset per route
      this.list.push(new Board(route, scene, ad, s, rnd() < 0.5 ? -1 : 1));
    }
  }

  // nearest board along the ray, for combat to compare against enemies
  rayHit(origin, dir, range) {
    let best = null;
    for (const b of this.list) {
      const h = b.hit(origin, dir, best ? best.t : range);
      if (h) best = h;
    }
    return best;
  }

  dispose() { this.list.forEach((b) => b.dispose()); this.list = []; }
}
