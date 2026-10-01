// DOM HUD. Updated at most a few times per frame, only when values change.
import * as THREE from 'three';

const $ = (id) => document.getElementById(id);
const _p = new THREE.Vector3();

export class HUD {
  constructor() {
    this.el = $('hud');
    this.cross = $('crosshair');
    this.hm = $('hitmarker');
    this.feed = $('feed');
    this.bannerEl = $('banner');
    this.cyl = $('ammo-cyl'); this.shells = $('ammo-shells'); this.ammoName = $('ammo-name'); this.ammoBox = $('ammo');
    this.count = $('ammo-count');
    this.scope = $('scope'); this.btnScope = $('btn-scope');
    this.reloadRing = $('reload-ring'); this.reloadFill = this.reloadRing.querySelector('i');
    this.shooterLayer = $('shooters'); this.shooterEls = [];
    this.escortEls = new Map();
    this.hp = $('hp-meter'); this.coach = $('coach-meter'); this.de = $('de-meter');
    this.routeFill = $('route-fill'); this.routeCoach = $('route-coach');
    this.bounty = $('bounty-val');
    this.dirs = $('dmg-dirs');
    this.vHit = $('vignette-hit');
    this.deOverlay = $('deadeye-overlay');
    this.btnDE = $('btn-deadeye');
    this.dynamiteCount = $('dynamite-count');
    this.touchDynamiteCount = $('btn-dynamite-count');
    this.btnDynamite = $('btn-dynamite');
    this.btnWhip = $('btn-whip');
    this.chevLayer = $('chevrons');
    this.chevs = [];
    this.coachPct = this.coach.querySelector('.pct');
    this.ring = this.cross.querySelector('u');
    this._last = {};
    this.marks = [];
    this.markLayer = document.createElement('div');
    this.markLayer.style.cssText = 'position:absolute;inset:0;pointer-events:none';
    this.el.appendChild(this.markLayer);
    // chambers
    this.cyl.innerHTML = '';
    for (let i = 0; i < 6; i++) {
      const c = document.createElement('div'); c.className = 'ch full';
      const a = (i / 6) * Math.PI * 2 - Math.PI / 2; // art: chamber centres at 76/256 of the width, first at top
      c.style.left = 37 + Math.cos(a) * 22 + 'px'; c.style.top = 37 + Math.sin(a) * 22 + 'px';
      this.cyl.appendChild(c);
    }
  }

  show(v) { this.el.classList.toggle('hidden', !v); }

  setDynamite(count) {
    this.dynamiteCount.textContent = count;
    this.touchDynamiteCount.textContent = count;
    this.btnDynamite.classList.toggle('disabled', count === 0);
  }

  setRoute(def) { $('town-from').textContent = def.from; $('town-to').textContent = def.to; }

  setWeapon(W, ammo) {
    this.weapon = W;
    this.ammoName.textContent = W.name;
    // six-shooters get the cylinder, one- and two-shot guns get cartridges, the rest a count
    this.ammoMode = W.kind === 'revolver' && W.mag === 6 ? 'cyl' : W.mag <= 2 ? 'shells' : 'count';
    this.cyl.style.display = this.ammoMode === 'cyl' ? 'block' : 'none';
    this.shells.style.display = this.ammoMode === 'shells' ? 'flex' : 'none';
    this.count.style.display = this.ammoMode === 'count' ? 'block' : 'none';
    this.cross.classList.toggle('shotgun', W.kind === 'shotgun');
    this.setAmmo(W, ammo, false);
  }

  setAmmo(W, n, reloading) {
    this.ammoBox.classList.toggle('reloading', reloading);
    if (this.ammoMode === 'cyl') {
      [...this.cyl.children].forEach((c, i) => { c.className = 'ch ' + (i < n ? 'full' : 'empty'); });
      this.cyl.style.transform = `rotate(${(6 - n) * 60}deg)`;
    } else if (this.ammoMode === 'count') {
      this.count.firstChild.textContent = n;
      this.count.lastChild.textContent = '/' + W.mag;
      this.count.classList.toggle('low', n <= Math.ceil(W.mag / 5));
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
    if (this._last.deOn !== p.deadeyeOn) { this._last.deOn = p.deadeyeOn; this.deOverlay.classList.toggle('on', p.deadeyeOn); this.btnDE.classList.toggle('active', p.deadeyeOn); if (p.deadeyeOn) this.btnDE.classList.remove('disabled'); }
    // no scope on a sidearm
    if (this._last.canScope !== p.canScope) { this._last.canScope = p.canScope; this.btnScope.classList.toggle('disabled', !p.canScope); }
    const cp = Math.max(0, Math.round(c.hp));
    if (this._last.cp !== cp) {
      if (this._last.cp !== undefined && cp < this._last.cp) { this.coach.classList.remove('flash'); void this.coach.offsetWidth; this.coach.classList.add('flash'); clearTimeout(this._cf); this._cf = setTimeout(() => this.coach.classList.remove('flash'), 400); }
      this._last.cp = cp; this.coachPct.textContent = cp + '%';
    }
    // coach-gun pattern ring sized to the real pellet cone
    if (p.weapon.kind === 'shotgun') {
      const r = Math.round(p.weapon.spread * (game.renderer.height / 2) / Math.tan(THREE.MathUtils.degToRad(game.camera.fov / 2)));
      if (this._last.ring !== r) { this._last.ring = r; Object.assign(this.ring.style, { width: r * 2 + 'px', height: r * 2 + 'px', left: -r + 'px', top: -r + 'px' }); }
    }
    this._chevrons(game);
    const stam = Math.round(c.stamina * 10);
    if (this._last.stam !== stam) { this._last.stam = stam; this.btnWhip.style.opacity = 0.4 + c.stamina * 0.5; }
    const prog = Math.min(1, c.s / game.route.len);
    const pr = Math.round(prog * 400) / 4;
    if (this._last.prog !== pr) { this._last.prog = pr; this.routeFill.style.width = pr + '%'; this.routeCoach.style.left = pr + '%'; }
    // a hit has to read instantly: a bigger, longer flash on top of the
    // standing low-health vignette
    const since = game.time - p.lastHit;
    const hitV = Math.max(0, 1 - p.hp / 100) * 0.7 + Math.max(0, 1 - since / 0.5) * 0.8;
    const hv = Math.round(hitV * 20) / 20;
    if (this._last.hv !== hv) { this._last.hv = hv; this.vHit.style.opacity = hv; game.renderer.final.uniforms.uHit.value = hv * 0.6; }
    this._marks(game);
    this._shooters(game);
    this._escorts(game);
    // reload progress, right under the crosshair where you are already looking
    const rl = p.reloading > 0;
    if (this._last.rl !== rl) { this._last.rl = rl; this.reloadRing.classList.toggle('on', rl); }
    if (rl) {
      const frac = 1 - p.reloading / Math.max(0.01, p.weapon.reload);
      this.reloadFill.style.width = Math.round(frac * 100) + '%';
    }
  }

  // the gun isn't broken, it's reloading — say so when they try to fire
  nudgeReload() {
    this.reloadRing.classList.remove('nudge');
    void this.reloadRing.offsetWidth;
    this.reloadRing.classList.add('nudge');
  }

  setScope(on) {
    this.scope.classList.toggle('on', on);
    this.cross.classList.toggle('scoped', on);
    this.btnScope.classList.toggle('active', on);
  }

  // A bracket around every rifleman / gunman who can see you. On a far ridge he
  // is only a few pixels tall, so the bracket is sized to how big he actually
  // looks: a small box on an empty hillside tells you exactly where to aim, and
  // it opens up as he gets closer. Flashes red when he's about to fire.
  _shooters(game) {
    const list = [];
    const H = game.renderer.height;
    // pixels per metre at one metre, for this camera's field of view
    const perM = H / (2 * Math.tan(THREE.MathUtils.degToRad(game.camera.fov / 2)));
    for (const e of game.enemies.list) {
      if (!e.alive || e.type === 'rider' || !e.los) continue;
      const dist = e.spheres[1].c.distanceTo(game.player.camPos);
      if (dist > (e.rifle ? 320 : 80)) continue;
      _p.copy(e.spheres[1].c).project(game.camera);
      if (_p.z > 1 || Math.abs(_p.x) > 1 || Math.abs(_p.y) > 1) continue;
      // a man is about 1.8 m; never smaller than a thumb-sized box
      const px = Math.max(30, Math.min(140, (1.9 / dist) * perM));
      list.push({ x: _p.x, y: _p.y, px, glint: e.glintT > 0, dist });
    }
    // wildlife: on screen first, then ground game ahead of birds; the vultures
    // round a carcass share one marker, and birds high overhead get none
    const wild = [], sites = new Set();
    for (const animal of game.wildlife.list) {
      if (!animal.alive || (animal.airborne && animal.alt > 15)) continue;
      let at = animal.pos, tall = animal.cfg.tall * animal.scale, kind = animal.kind;
      const site = animal.site;
      if (site) {
        if (sites.has(site)) continue;
        sites.add(site);
        const n = site.birds.filter((b) => b.alive && !(b.airborne && b.alt > 15)).length;
        at = site.pos; kind = `vultures ×${n}`;
      }
      const dist = at.distanceTo(game.player.camPos);
      if (dist > 260) continue;
      _p.copy(at);
      _p.y += tall + 0.3;
      _p.project(game.camera);
      if (_p.z > 1 || Math.abs(_p.x) > 1 || Math.abs(_p.y) > 1) continue;
      const px = Math.max(22, Math.min(100, (tall / Math.max(1, dist)) * perM));
      wild.push({ x: _p.x, y: _p.y, px, dist, kind, bird: !animal.cfg.mass });
    }
    wild.sort((a, b) => a.bird - b.bird || a.dist - b.dist);
    list.push(...wild.slice(0, 5));
    while (this.shooterEls.length < list.length) {
      const d = document.createElement('div');
      d.className = 'shooter';
      d.innerHTML = '<i></i><i></i><i></i><i></i><b></b>';
      this.shooterLayer.appendChild(d); this.shooterEls.push(d);
    }
    while (this.shooterEls.length > list.length) this.shooterEls.pop().remove();
    list.forEach((m, i) => {
      const el = this.shooterEls[i];
      el.className = 'shooter' + (m.glint ? ' glint' : '') + (m.kind ? ' wildlife' : '') + (m.px < 40 ? ' far' : '');
      el.style.left = (m.x * 0.5 + 0.5) * 100 + '%';
      el.style.top = (-m.y * 0.5 + 0.5) * 100 + '%';
      el.style.width = m.px + 'px';
      el.style.height = m.px * 1.15 + 'px';
      el.lastChild.textContent = (m.kind ? m.kind.toUpperCase() + ' ' : '') + Math.round(m.dist) + 'm';
    });
  }

  // name tag and a health pip over each hired gun, in a friendly colour
  _escorts(game) {
    const list = game.escorts?.list || [], seen = new Set();
    for (const e of list) {
      if (!e.alive) continue;
      seen.add(e);
      let el = this.escortEls.get(e);
      if (!el) {
        el = document.createElement('div');
        el.className = 'escort-tag' + (e.cfg.id === 'bill' ? ' star' : '');
        el.innerHTML = `<b>${e.tag}</b><span><i></i></span>`;
        this.shooterLayer.appendChild(el); this.escortEls.set(e, el);
      }
      const dist = e.headP.distanceTo(game.player.camPos);
      _p.copy(e.headP); _p.y += 0.45;
      _p.project(game.camera);
      const off = _p.z > 1 || Math.abs(_p.x) > 1 || Math.abs(_p.y) > 1 || dist > 110 || game.player.scopeT > 0.5;
      el.style.display = off ? 'none' : '';
      if (off) continue;
      el.style.left = (_p.x * 0.5 + 0.5) * 100 + '%';
      el.style.top = (-_p.y * 0.5 + 0.5) * 100 + '%';
      const hp = Math.max(0, e.hp / e.cfg.hp);
      const k = Math.round(hp * 50);
      if (el._k !== k) { el._k = k; el.lastChild.firstChild.style.width = hp * 100 + '%'; el.classList.toggle('low', hp < 0.35); }
      el.classList.toggle('hit', game.time - (e.hitT ?? -9) < 0.3);
    }
    for (const [e, el] of this.escortEls) if (!seen.has(e)) { el.remove(); this.escortEls.delete(e); }
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
      // percentages of the layer, which covers the canvas exactly
      el.style.left = (v.x * 0.5 + 0.5) * 100 + '%';
      el.style.top = (-v.y * 0.5 + 0.5) * 100 + '%';
    });
  }

  // edge arrows for threats you can't see (behind you, off-screen, or tiny and far)
  _chevrons(game) {
    const list = [], W = game.renderer.width, H = game.renderer.height;
    for (const e of game.enemies.list) {
      if (!e.alive) continue;
      const dist = e.spheres[1].c.distanceTo(game.player.camPos);
      const threat = e.type === 'rider' ? e.state === 'ride' && dist < 70 : e.los === true && dist < (e.rifle ? 200 : 70);
      if (!threat) continue;
      _p.copy(e.spheres[1].c).project(game.camera);
      const behind = _p.z > 1;
      const on = !behind && Math.abs(_p.x) < 0.92 && Math.abs(_p.y) < 0.88;
      if (on) continue;
      let x = behind ? -_p.x : _p.x, y = behind ? -_p.y : _p.y;
      if (behind && Math.abs(y) < 0.3) y = -0.9; // straight behind: show at the bottom
      const a = Math.atan2(y * H, x * W);
      const cls = e.glintT > 0 ? 'glint' : e.type === 'rider' ? '' : 'rifle';
      // merge threats in nearly the same direction (keep the most urgent)
      const near = list.find((c) => Math.abs(Math.atan2(Math.sin(c.a - a), Math.cos(c.a - a))) < 0.25);
      if (near) { if (cls === 'glint' || (cls === 'rifle' && near.cls === '')) near.cls = cls; continue; }
      list.push({ a, cls });
    }
    while (this.chevs.length < list.length) { const d = document.createElement('div'); d.className = 'chev'; this.chevLayer.appendChild(d); this.chevs.push(d); }
    while (this.chevs.length > list.length) this.chevs.pop().remove();
    const rx = W / 2 - 46, ry = H / 2 - 40;
    list.forEach((c, i) => {
      const el = this.chevs[i];
      const x = W / 2 + Math.cos(c.a) * rx, y = H / 2 - Math.sin(c.a) * ry;
      el.className = 'chev ' + c.cls;
      el.style.left = x + 'px'; el.style.top = y + 'px';
      el.style.transform = `rotate(${Math.PI / 2 - c.a}rad)`;
    });
  }

  crosshairEnemy(on) { if (this._last.ce !== on) { this._last.ce = on; this.cross.classList.toggle('enemy', on); } }
  crosshairWildlife(on) { if (this._last.cw !== on) { this._last.cw = on; this.cross.classList.toggle('wildlife', on); } }

  hitmarker(hit, kill, head) {
    if (!hit) return;
    this.hm.classList.remove('show', 'kill', 'head');
    void this.hm.offsetWidth;
    this.hm.classList.add('show');
    if (kill) this.hm.classList.add('kill');
    if (head) this.hm.classList.add('head');
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

  banner(title, sub = '', secs = 1.4) {
    this.bannerEl.innerHTML = title + (sub ? `<small>${sub}</small>` : '');
    this.bannerEl.classList.add('show');
    clearTimeout(this._bt);
    this._bt = setTimeout(() => this.bannerEl.classList.remove('show'), secs * 1000);
  }

  // flash the heart so you can see where the damage went
  pulseHealth(heavy) {
    this.hp.classList.remove('flash', 'heavy');
    void this.hp.offsetWidth;
    this.hp.classList.add('flash');
    if (heavy) this.hp.classList.add('heavy');
    clearTimeout(this._hpf);
    this._hpf = setTimeout(() => this.hp.classList.remove('flash', 'heavy'), heavy ? 620 : 380);
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
