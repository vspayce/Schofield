// DOM HUD. Updated at most a few times per frame, only when values change.
import * as THREE from 'three';

const $ = (id) => document.getElementById(id);

export class HUD {
  constructor() {
    this.el = $('hud');
    this.cross = $('crosshair');
    this.hm = $('hitmarker');
    this.feed = $('feed');
    this.bannerEl = $('banner');
    this.cyl = $('ammo-cyl'); this.shells = $('ammo-shells'); this.ammoName = $('ammo-name'); this.ammoBox = $('ammo');
    this.hp = $('hp-meter'); this.coach = $('coach-meter'); this.de = $('de-meter');
    this.routeFill = $('route-fill'); this.routeCoach = $('route-coach');
    this.bounty = $('bounty-val');
    this.dirs = $('dmg-dirs');
    this.vHit = $('vignette-hit');
    this.deOverlay = $('deadeye-overlay');
    this.btnDE = $('btn-deadeye');
    this.btnWhip = $('btn-whip');
    this._last = {};
    this.marks = [];
    this.markLayer = document.createElement('div');
    this.markLayer.style.cssText = 'position:absolute;inset:0;pointer-events:none';
    this.el.appendChild(this.markLayer);
    // chambers
    this.cyl.innerHTML = '';
    for (let i = 0; i < 6; i++) {
      const c = document.createElement('div'); c.className = 'ch full';
      const a = (i / 6) * Math.PI * 2 - Math.PI / 2;
      c.style.left = 37 + Math.cos(a) * 22 + 'px'; c.style.top = 37 + Math.sin(a) * 22 + 'px';
      this.cyl.appendChild(c);
    }
  }

  show(v) { this.el.classList.toggle('hidden', !v); }

  setRoute(def) { $('town-from').textContent = def.from; $('town-to').textContent = def.to; }

  setWeapon(W, ammo) {
    this.weapon = W;
    this.ammoName.textContent = W.name;
    this.cyl.style.display = W.id === 'schofield' ? 'block' : 'none';
    this.shells.style.display = W.id === 'shotgun' ? 'flex' : 'none';
    this.cross.classList.toggle('shotgun', W.id === 'shotgun');
    this.setAmmo(W, ammo, false);
  }

  setAmmo(W, n, reloading) {
    this.ammoBox.classList.toggle('reloading', reloading);
    if (W.id === 'schofield') {
      [...this.cyl.children].forEach((c, i) => { c.className = 'ch ' + (i < n ? 'full' : 'empty'); });
      this.cyl.style.transform = `rotate(${(6 - n) * 60}deg)`;
    } else {
      this.shells.innerHTML = '';
      for (let i = 0; i < W.mag; i++) { const s = document.createElement('div'); s.className = 'sh ' + (i < n ? 'full' : 'empty'); this.shells.appendChild(s); }
    }
  }

  _meter(el, v, key) {
    const r = Math.round(v * 200) / 200;
    if (this._last[key] === r) return;
    this._last[key] = r;
    el.querySelector('.fill').style.width = Math.max(0, r * 100) + '%';
    el.classList.toggle('low', r < 0.3 && key !== 'de');
  }

  update(game) {
    const p = game.player, c = game.coach;
    this._meter(this.hp, p.hp / 100, 'hp');
    this._meter(this.coach, c.hp / 100, 'coach');
    this._meter(this.de, p.deadeye, 'de');
    const ready = p.deadeye >= 0.2;
    if (this._last.deReady !== ready) { this._last.deReady = ready; this.de.classList.toggle('ready', ready); this.btnDE.classList.toggle('disabled', !ready); }
    if (this._last.deOn !== p.deadeyeOn) { this._last.deOn = p.deadeyeOn; this.deOverlay.classList.toggle('on', p.deadeyeOn); }
    const stam = Math.round(c.stamina * 10);
    if (this._last.stam !== stam) { this._last.stam = stam; this.btnWhip.style.opacity = 0.4 + c.stamina * 0.5; }
    const prog = Math.min(1, c.s / game.route.len);
    const pr = Math.round(prog * 400) / 4;
    if (this._last.prog !== pr) { this._last.prog = pr; this.routeFill.style.width = pr + '%'; this.routeCoach.style.left = pr + '%'; }
    const hitV = Math.max(0, 1 - p.hp / 100) * 0.7 + (game.time - p.lastHit < 0.3 ? 0.4 : 0);
    const hv = Math.round(hitV * 20) / 20;
    if (this._last.hv !== hv) { this._last.hv = hv; this.vHit.style.opacity = hv; game.renderer.final.uniforms.uHit.value = hv * 0.6; }
    this._marks(game);
  }

  _marks(game) {
    const p = game.player;
    const want = p.deadeyeOn ? p.marks : [];
    while (this.marks.length < want.length) {
      const m = document.createElement('div');
      m.style.cssText = 'position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;color:#ff3b2f;font:bold 22px/22px Georgia;text-align:center;text-shadow:0 0 4px #000';
      m.textContent = '✕';
      this.markLayer.appendChild(m); this.marks.push(m);
    }
    while (this.marks.length > want.length) this.marks.pop().remove();
    const v = new THREE.Vector3();
    want.forEach((mk, i) => {
      v.copy(mk.enemy.hitPoint(mk.part)).project(game.camera);
      const el = this.marks[i];
      if (v.z > 1) { el.style.display = 'none'; return; }
      el.style.display = 'block';
      el.style.left = (v.x * 0.5 + 0.5) * innerWidth + 'px';
      el.style.top = (-v.y * 0.5 + 0.5) * innerHeight + 'px';
    });
  }

  crosshairEnemy(on) { if (this._last.ce !== on) { this._last.ce = on; this.cross.classList.toggle('enemy', on); } }

  hitmarker(hit, kill) {
    if (!hit) return;
    this.hm.classList.remove('show', 'kill');
    void this.hm.offsetWidth;
    this.hm.classList.add('show');
    if (kill) this.hm.classList.add('kill');
  }

  setBounty(v) { this.bounty.textContent = '$' + v; }

  feedMsg(text, hs) {
    const d = document.createElement('div');
    d.className = 'feed-item' + (hs ? ' hs' : '');
    d.textContent = text;
    this.feed.appendChild(d);
    setTimeout(() => d.remove(), 1400);
    while (this.feed.children.length > 4) this.feed.firstChild.remove();
  }

  banner(title, sub = '', secs = 2.2) {
    this.bannerEl.innerHTML = title + (sub ? `<small>${sub}</small>` : '');
    this.bannerEl.classList.add('show');
    clearTimeout(this._bt);
    this._bt = setTimeout(() => this.bannerEl.classList.remove('show'), secs * 1000);
  }

  damage(from, camPos, aimDir) {
    // direction indicator around the crosshair
    const to = new THREE.Vector3().subVectors(from, camPos); to.y = 0; to.normalize();
    const f = aimDir.clone(); f.y = 0; f.normalize();
    const ang = Math.atan2(f.x * to.z - f.z * to.x, f.x * to.x + f.z * to.z);
    const d = document.createElement('div');
    d.className = 'dmg-dir';
    const r = Math.min(innerWidth, innerHeight) * 0.28;
    d.style.transform = `rotate(${ang}rad) translateY(${-r}px)`; // + = clockwise = to the right
    this.dirs.appendChild(d);
    setTimeout(() => d.remove(), 1100);
  }
}
