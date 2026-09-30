// Title / route select / loadout / gunsmith / pause / results / settings screens.
import { ROUTES } from '../world/routes.js';
import { WEAPONS, STARTERS, SIDEARMS, LONG_GUNS } from '../game/weapons.js';
import { MISSIONS, MISSION_LIST } from '../game/missions.js';
import { audio } from '../core/audio.js';
import { fullscreen } from '../core/fullscreen.js';

const el = document.getElementById('menu');
const UI = import.meta.env.BASE_URL + 'assets/ui/';

function persist(d) { try { localStorage.setItem('schofield.save', JSON.stringify(d)); } catch {} }

// Progress kept in this browser: stars, best bounties, the purse, and guns.
export const save = {
  data: (() => { try { return JSON.parse(localStorage.getItem('schofield.save')) || {}; } catch { return {}; } })(),
  stars(id) { return (this.data.stars || {})[id] || 0; },
  best(id) { return (this.data.best || {})[id] || 0; },
  record(id, stars, bounty) {
    const d = this.data;
    d.stars = d.stars || {}; d.best = d.best || {};
    d.stars[id] = Math.max(d.stars[id] || 0, stars);
    d.best[id] = Math.max(d.best[id] || 0, bounty);
    persist(d);
  },

  get cash() { return this.data.cash || 0; },
  earn(v) { this.data.cash = this.cash + Math.max(0, Math.round(v)); persist(this.data); },
  owns(id) { return STARTERS.includes(id) || (this.data.owned || []).includes(id); },
  buy(id) {
    const W = WEAPONS[id];
    if (!W || this.owns(id) || this.cash < W.price) return false;
    this.data.cash -= W.price;
    (this.data.owned ||= []).push(id);
    this.equip(id);
    return true;
  },
  // the gun carried in a slot ('side' | 'long')
  equipped(slot) {
    const id = (this.data.equip || {})[slot];
    return WEAPONS[id]?.slot === slot && this.owns(id) ? id : slot === 'side' ? 'schofield' : 'shotgun';
  },
  equip(id) { (this.data.equip ||= {})[WEAPONS[id].slot] = id; persist(this.data); },
  // which of the two is in hand when the ride starts
  get start() { return this.data.start === 'long' ? 'long' : 'side'; },
  set start(v) { this.data.start = v; persist(this.data); },
  // the job you're hauling
  get mission() { return MISSIONS[this.data.mission] ? this.data.mission : 'bank'; },
  set mission(v) { this.data.mission = v; persist(this.data); },

  // ---------------------------------------------------------- the coach
  // Damage carries between runs. The driver patches what he can for nothing
  // between towns; anything better costs money at the livery.
  FREE_PATCH: 18,
  REPAIR_RATE: 5,          // dollars per point of condition
  get coachHp() { return this.data.coachHp === undefined ? 100 : this.data.coachHp; },
  set coachHp(v) { this.data.coachHp = Math.max(0, Math.min(100, Math.round(v))); persist(this.data); },
  // called when a run ends: bank the wear, then the free patch
  wearCoach(endHp) { this.coachHp = Math.min(100, Math.max(0, endHp) + this.FREE_PATCH); },
  repairCost(to = 100) { return Math.max(0, Math.ceil((to - this.coachHp) * this.REPAIR_RATE)); },
  repair() {
    const cost = this.repairCost();
    if (cost <= 0) return 'full';
    const afford = Math.min(cost, this.cash);
    if (afford < this.REPAIR_RATE) return 'poor';
    const points = Math.floor(afford / this.REPAIR_RATE);
    this.data.cash -= points * this.REPAIR_RATE;
    this.coachHp = this.coachHp + points;
    persist(this.data);
    return points;
  },

  // start over: purse, guns, stars, coach wear. Settings are kept separately
  // (schofield.settings) and survive this.
  wipe() {
    this.data = {};
    try { localStorage.removeItem('schofield.save'); } catch {}
  },
};

function click() { audio.play('ui_click', { volume: 0.6 }); }
function stars(n) { return '★'.repeat(n) + '☆'.repeat(3 - n); }

// every gun has its own engraving in assets/ui; the year stands in if one is missing
function gunPic(W) {
  return `<img src="${UI}weapon_${W.id}.png" alt="" onerror="this.outerHTML='<div class=&quot;gun-yr&quot;>${W.year}</div>'"/>`;
}
function statBars(W) {
  return Object.entries(W.stats).map(([k, v]) => `<div class="stat"><span>${k}</span><div class="b"><i style="width:${v * 100}%"></i></div></div>`).join('');
}

function logo() {
  return `<img class="m-logo" src="${UI}logo.png" alt="SCHOFIELD" onerror="this.outerHTML='<h1 class=&quot;logo-text&quot;>SCHOFIELD</h1>'"/>`;
}

export class Menus {
  constructor(game) { this.g = game; }

  hide() { el.classList.remove('show', 'dim', 'title-screen', 'tall'); el.innerHTML = ''; }

  _show(html, dim = true, cls = '') {
    el.innerHTML = `<div class="m-wrap">${html}</div>`;
    el.classList.add('show'); el.classList.toggle('dim', dim);
    el.classList.toggle('title-screen', cls === 'title');
    el.classList.toggle('tall', cls === 'tall'); // scrolls from the top
    el.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', (e) => {
      e.stopPropagation(); // buttons inside clickable cards
      if (!b.dataset.act) return;
      click(); this._act(b.dataset.act, b.dataset.arg, e);
    }));
  }

  title() {
    this._show(`
      ${logo()}
      <div class="m-tag">Ride shotgun on a Territorial Bank transfer. Keep the strongbox. Keep your scalp.</div>
      <button class="m-btn" data-act="routes">Ride Out</button>
      <div class="m-row" style="margin-top:6px">
        <button class="m-btn ghost" data-act="settings">Settings</button>
        <button class="m-btn ghost" data-act="how">How to Play</button>
        <button class="m-btn ghost" data-act="reload">Reload</button>
      </div>
      ${fullscreen.needsHomeScreen ? '<div class="m-hint">For full screen on iPhone: tap Share, then <b>Add to Home Screen</b>, and play from the new icon.</div>' : ''}`, false, 'title');
  }

  routes() {
    // every route is open from the start
    // `wip` routes stay out of the list but keep their index, so ?route=N and
    // save data are unaffected
    const posters = ROUTES.map((r, i) => {
      if (r.wip) return '';
      return `<div class="poster" data-act="pick" data-arg="${i}"><div class="pin">
        <div><h3>${r.name}</h3><div class="sub">${r.from} → ${r.to}</div></div>
        <div class="sub">${r.blurb}</div>
        <div><div class="stars">${stars(save.stars(r.id))}</div><div class="reward">REWARD $${r.reward}</div></div></div>
      </div>`;
    }).join('');
    this._show(`<h2 class="m-title">Choose Your Route</h2><div class="m-row">${posters}</div>
      <button class="m-btn ghost" style="margin-top:14px" data-act="title">Back</button>`);
  }

  // pick what you're carrying: sets the pay, the opposition and the coach
  jobs(i) {
    this.routeIndex = i;
    const R = ROUTES[i];
    const card = (M) => {
      const pay = Math.round(R.reward * M.pay);
      const pips = (n) => '<span class="risk">' + '◆'.repeat(n) + '<i>' + '◆'.repeat(4 - n) + '</i></span>';
      return `<div class="job-card ${save.mission === M.id ? 'sel' : ''}" data-act="job" data-arg="${M.id}">
        <div class="job-head"><h3>${M.name}</h3><span class="pay">$${pay}</span></div>
        <div class="cargo">${M.cargo}</div>
        <p>${M.blurb}</p>
        <div class="job-foot"><span>risk</span>${pips(Math.round(M.risk * 4))}</div>
      </div>`;
    };
    this._show(`<h2 class="m-title">${R.name}</h2>
      <div class="m-tag" style="margin:-6px 0 12px">What are you hauling? The road pays for the risk.</div>
      <div class="m-row">${MISSION_LIST.map(card).join('')}</div>
      <div class="m-row" style="margin-top:12px"><button class="m-btn ghost" data-act="routes">Back</button></div>`, true, 'tall');
  }

  loadout(i) {
    this.routeIndex = i;
    const slot = (key, label, all) => {
      const W = WEAPONS[save.equipped(key)];
      const owned = all.filter((w) => save.owns(w.id));
      const k = owned.indexOf(W);
      return `<div class="gun-card ${save.start === key ? 'sel' : ''}" data-act="start" data-arg="${key}">
        <div class="slot-lbl">${label}${save.start === key ? ' · in hand' : ''}</div>
        ${gunPic(W)}
        <h3>${W.name}</h3>
        ${owned.length > 1 ? `<div class="cycle"><button class="m-btn ghost sm" data-act="cycle" data-arg="${key}:-1" aria-label="Previous gun">◀</button><span>${k + 1} of ${owned.length}</span><button class="m-btn ghost sm" data-act="cycle" data-arg="${key}:1" aria-label="Next gun">▶</button></div>` : ''}
        ${statBars(W)}
      </div>`;
    };
    this._show(`<h2 class="m-title">${ROUTES[i].name}</h2>
      <div class="m-tag" style="margin:-6px 0 12px">Tap the gun to start with in hand. Swap any time on the coach.</div>
      <div class="m-row">${slot('side', 'Sidearm', SIDEARMS)}${slot('long', 'Long gun', LONG_GUNS)}</div>
      <div class="coach-cond ${save.coachHp < 55 ? 'bad' : ''}">Coach condition <b>${save.coachHp}%</b>${
        save.coachHp < 100 ? ` · <button class="m-btn ghost sm" data-act="repair">Repair $${save.repairCost()}</button>` : ' · sound'}</div>
      <div class="m-row" style="margin-top:12px"><button class="m-btn ghost" data-act="jobs">${MISSIONS[save.mission].name} ▸</button><button class="m-btn ghost" data-act="shop" data-arg="loadout">Gunsmith · $${save.cash}</button><button class="m-btn" data-act="go">All Aboard</button></div>`, true, 'tall');
  }

  // buy guns with the purse; back = 'loadout' | 'results'
  gunsmith(back = this.shopBack) {
    this.shopBack = back;
    const card = (W) => {
      const own = save.owns(W.id), carried = save.equipped(W.slot) === W.id, afford = save.cash >= W.price;
      const btn = carried ? '<button class="m-btn ghost sm" disabled>Carrying</button>'
        : own ? `<button class="m-btn ghost sm" data-act="equip" data-arg="${W.id}">Carry this</button>`
          : `<button class="m-btn sm ${afford ? '' : 'poor'}" data-act="${afford ? 'buy' : ''}" data-arg="${W.id}" ${afford ? '' : 'aria-disabled="true"'}>Buy $${W.price}</button>`;
      return `<div class="shop-card ${carried ? 'sel' : ''}">
        <div class="shop-head"><h3>${W.name}</h3><span class="yr">${W.year}</span></div>
        <div class="shop-pic">${gunPic(W)}</div>
        <p>${W.blurb}</p>
        ${statBars(W)}
        <div class="shop-foot">${btn}</div>
      </div>`;
    };
    this._show(`<h2 class="m-title">Gunsmith</h2>
      <div class="purse">Your purse: <b>$${save.cash}</b></div>
      <div class="shop-sec">Sidearms</div><div class="shop-grid">${SIDEARMS.map(card).join('')}</div>
      <div class="shop-sec">Long guns</div><div class="shop-grid">${LONG_GUNS.map(card).join('')}</div>
      <button class="m-btn" style="margin-top:14px" data-act="shop-done">Done</button>`, true, 'tall');
  }

  pause() {
    this._show(`<div class="paper"><h2>Paused</h2>
      <div style="margin:10px 0"><button class="m-btn" data-act="resume">Resume</button></div>
      <div><button class="m-btn ghost" data-act="settings-pause">Settings</button> <button class="m-btn ghost" data-act="restart">Restart Run</button> <button class="m-btn ghost" data-act="quit">Quit to Title</button></div>
      <div style="margin-top:8px"><button class="m-btn ghost sm" data-act="reload">Reload Game</button></div></div>`);
  }

  results(r = this.lastResults) {
    this.lastResults = r;
    const i = this.g.routeIndex;
    const next = i + 1 < ROUTES.length;
    this._show(`<div class="paper">
      <div style="font-family:var(--font-sc);letter-spacing:.2em">${(r.mission || 'Mail Contract').toUpperCase()} — ARRIVED AT</div>
      <h2>${ROUTES[i].to}</h2>
      <div class="stars">${stars(r.stars)}</div>
      <div class="results-grid">
      <div class="line"><span>Outlaws dropped</span><span>${r.kills}</span></div>
      <div class="line"><span>Headshots</span><span>${r.headshots}</span></div>
      <div class="line"><span>Accuracy</span><span>${r.accuracy}%</span></div>
      <div class="line"><span>Coach condition</span><span>${r.coach}%</span></div>
      <div class="line"><span>Bounties</span><span>$${r.bounty}</span></div>
      <div class="line"><span>${r.mission || 'Contract'} payout</span><span>$${r.reward}</span></div>
      </div>
      <div class="total">Total $${r.total}</div>
      <div class="purse-line">Purse $${save.cash}</div>
      <div class="m-row" style="margin-top:10px">
        <button class="m-btn ghost" data-act="shop" data-arg="results">Gunsmith</button>
        <button class="m-btn ghost" data-act="routes">Routes</button>
        <button class="m-btn ghost" data-act="restart">Ride Again</button>
        ${next ? `<button class="m-btn" data-act="next">Next Route</button>` : ''}
      </div></div>`);
  }

  failed(reason, kept = 0) {
    this._show(`<div class="paper"><h2>Dead &amp; Buried</h2>
      <div style="font-style:italic;margin:6px 0 14px">${reason}</div>
      ${kept ? `<div class="purse-line" style="margin:-6px 0 12px">You keep the $${kept} in bounties. Purse $${save.cash}</div>` : ''}
      <div class="m-row"><button class="m-btn" data-act="restart">Try Again</button><button class="m-btn ghost" data-act="routes">Routes</button></div></div>`);
  }

  how() {
    const touch = this.g.input.touch;
    this._show(`<div class="paper" style="text-align:left;max-width:700px">
      <h2 style="text-align:center">How to Ride Shotgun</h2>
      ${touch ? `
      <p><b>Aim:</b> drag anywhere on the right. Dragging from the FIRE button aims while you shoot.</p>
      <p><b>Fire / Reload / Swap:</b> buttons at bottom right. Swap between your sidearm and long gun any time.</p>
      <p><b>Whip / Rein:</b> buttons at left. Hold Rein to stop; whip to pull away. The team tires if you whip too long.</p>` : `
      <p><b>Aim:</b> mouse. <b>Fire:</b> left click. <b>Reload:</b> R. <b>Swap:</b> Q. <b>Whip:</b> W / Shift. Hold <b>Rein:</b> S to stop; whip to pull away.</p>`}
      <p><b>Scope:</b> ${touch ? 'the scope button' : 'F'} — long guns only. Magnifies for the men on the ridges.</p>
      <p><b>Dead Eye:</b> ${touch ? 'the eye button' : 'E or right click'}. Time slows. Sweep across outlaws to mark them, then fire to drop every one.</p>
      <p><b>Dynamite:</b> ${touch ? 'the dynamite button' : 'G'}. Three sticks per run; throw into a group to blast riders from their horses.</p>

      <h3 class="how-h">Two things can kill you</h3>
      <p><b>Your health</b> — the heart, top left. It <u>heals itself</u> after four seconds without being hit.
      Shoot a buffalo, bear or goat and the meat restores more: a buffalo is worth 25.</p>
      <p><b>The coach</b> — the wagon meter under it. This one does <u>not</u> heal on its own, and if it reaches
      zero the run is over even at full health. It only gets patched up <b>+10 each time you clear a wave</b>,
      so leaving enemies alive is what bleeds it dry. Riders who reach the team hurt it badly, and so does
      running into anything on the road — rein in for the buffalo.</p>

      <h3 class="how-h">Watch for</h3>
      <p><b>Riflemen</b> on the ridges flash a glint before they shoot and hit far harder than riders. Drop them first.</p>
      <p><b>The bracket</b> around a shooter shows his range; it flashes red when he's about to fire.</p>
      <div style="text-align:center"><button class="m-btn" data-act="title">Got It</button></div></div>`, true, 'tall');
  }

  settings(back = 'title') {
    const q = this.g.renderer.tierName;
    this._show(`<div class="paper"><h2>Settings</h2>
      <div class="opts">
        <label>Graphics</label>
        <select id="opt-q">${['low', 'medium', 'high'].map((t) => `<option ${t === q ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <label>Aim sensitivity</label><input id="opt-sens" type="range" min="0.4" max="2" step="0.05" value="${this.g.input.sens}"/>
        <label>Invert Y</label><input id="opt-inv" type="checkbox" ${this.g.input.invertY ? 'checked' : ''}/>
        <label>God Mode</label><input id="opt-god" type="checkbox" ${this.g.godMode ? 'checked' : ''}/>
        <label>Music</label><input id="opt-mus" type="range" min="0" max="1" step="0.05" value="${audio.volumes.music}"/>
        <label>Effects</label><input id="opt-sfx" type="range" min="0" max="1" step="0.05" value="${audio.volumes.sfx}"/>
      </div>
      <button class="m-btn" data-act="${back === 'pause' ? 'pause' : 'title'}">Done</button>
      ${back === 'pause' ? '' : '<div style="margin-top:14px"><button class="m-btn ghost sm" data-act="wipe">Start Over…</button></div>'}</div>`);
    const s = (id, fn) => document.getElementById(id).addEventListener('input', (e) => { fn(e.target); this.g.saveSettings(); });
    s('opt-q', (t) => this.g.renderer.setQuality(t.value));
    s('opt-sens', (t) => (this.g.input.sens = +t.value));
    s('opt-inv', (t) => (this.g.input.invertY = t.checked));
    s('opt-god', (t) => (this.g.godMode = t.checked));
    s('opt-mus', (t) => audio.setVolume('music', +t.value));
    s('opt-sfx', (t) => audio.setVolume('sfx', +t.value));
  }

  // wiping the save can't be undone, so it asks first
  confirmWipe() {
    this._show(`<div class="paper"><h2>Start Over?</h2>
      <div style="font-style:italic;margin:6px 0 14px">Your purse ($${save.cash}), every gun you've bought, your stars and
      the coach's wear all go. Your settings stay. This can't be undone.</div>
      <div class="m-row"><button class="m-btn" data-act="wipe-yes">Start Over</button><button class="m-btn ghost" data-act="settings">Keep My Progress</button></div></div>`);
  }

  _act(a, arg) {
    const g = this.g;
    switch (a) {
      case 'title': this.title(); break;
      case 'routes': g.toAttract(); this.routes(); break;
      case 'pick': this.jobs(+arg); break;
      case 'job': {
        const changed = save.mission !== arg;
        save.mission = arg;
        if (changed) g.refreshAttractPreview();
        this.loadout(this.routeIndex);
        break;
      }
      case 'jobs': this.jobs(this.routeIndex); break;
      case 'start': save.start = arg; this.loadout(this.routeIndex); break;
      case 'cycle': {
        const [slot, step] = arg.split(':');
        const owned = (slot === 'side' ? SIDEARMS : LONG_GUNS).filter((w) => save.owns(w.id));
        const k = owned.indexOf(WEAPONS[save.equipped(slot)]);
        save.equip(owned[(k + +step + owned.length) % owned.length].id);
        this.loadout(this.routeIndex); break;
      }
      case 'repair': {
        const r = save.repair();
        if (r === 'poor') g.hud.feedMsg?.('Not enough for the livery', false);
        else audio.play('ui_click', { volume: 0.7, pitch: 0.8 });
        this.loadout(this.routeIndex); break;
      }
      case 'shop': this.gunsmith(arg); break;
      case 'buy': if (save.buy(arg)) audio.play('schofield_cock', { volume: 0.8 }); this.gunsmith(); break;
      case 'equip': save.equip(arg); this.gunsmith(); break;
      case 'shop-done': if (this.shopBack === 'results') this.results(); else this.loadout(this.routeIndex); break;
      case 'go': this.hide(); g.startRide(this.routeIndex); break;
      case 'resume': this.hide(); g.resume(); break;
      case 'pause': this.pause(); break;
      case 'restart': save.coachHp = 100; this.hide(); g.startRide(g.routeIndex); break;
      case 'next': this.hide(); g.startRide(g.routeIndex + 1); break;
      case 'quit': g.toAttract(); this.title(); break;
      // Fullscreen and home-screen launches have no address bar, so there is no
      // way to reload a wedged game from outside it.
      case 'reload': location.reload(); break;
      case 'wipe': this.confirmWipe(); break;
      // reload so nothing in memory carries the old progress over
      case 'wipe-yes': save.wipe(); location.reload(); break;
      case 'settings': this.settings('title'); break;
      case 'settings-pause': this.settings('pause'); break;
      case 'how': this.how(); break;
    }
  }
}
