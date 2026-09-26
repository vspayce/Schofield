// Title / route select / loadout / gunsmith / pause / results / settings screens.
import { ROUTES } from '../world/routes.js';
import { WEAPONS, STARTERS, SIDEARMS, LONG_GUNS } from '../game/weapons.js';
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
};

function click() { audio.play('ui_click', { volume: 0.6 }); }
function stars(n) { return '★'.repeat(n) + '☆'.repeat(3 - n); }

// menu art exists for the revolver and the shotgun; other guns show their year
function gunPic(W) {
  const art = W.model === 'Schofield' ? 'schofield' : W.model === 'CoachGun' ? 'shotgun' : null;
  return art ? `<img src="${UI}weapon_${art}.png" alt="" onerror="this.style.visibility='hidden'"/>` : `<div class="gun-yr">${W.year}</div>`;
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
      <div class="m-tag">Ride shotgun on the Overland Mail. Keep the strongbox. Keep your scalp.</div>
      <button class="m-btn" data-act="routes">Ride Out</button>
      <div class="m-row" style="margin-top:6px">
        <button class="m-btn ghost" data-act="settings">Settings</button>
        <button class="m-btn ghost" data-act="how">How to Play</button>
      </div>
      ${fullscreen.needsHomeScreen ? '<div class="m-hint">For full screen on iPhone: tap Share, then <b>Add to Home Screen</b>, and play from the new icon.</div>' : ''}`, false, 'title');
  }

  routes() {
    // every route is open from the start
    const posters = ROUTES.map((r, i) => {
      return `<div class="poster" data-act="pick" data-arg="${i}"><div class="pin">
        <div><h3>${r.name}</h3><div class="sub">${r.from} → ${r.to}</div></div>
        <div class="sub">${r.blurb}</div>
        <div><div class="stars">${stars(save.stars(r.id))}</div><div class="reward">REWARD $${r.reward}</div></div></div>
      </div>`;
    }).join('');
    this._show(`<h2 class="m-title">Choose Your Route</h2><div class="m-row">${posters}</div>
      <button class="m-btn ghost" style="margin-top:14px" data-act="title">Back</button>`);
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
      <div class="m-row" style="margin-top:12px"><button class="m-btn ghost" data-act="routes">Back</button><button class="m-btn ghost" data-act="shop" data-arg="loadout">Gunsmith · $${save.cash}</button><button class="m-btn" data-act="go">All Aboard</button></div>`, true, 'tall');
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
      <div><button class="m-btn ghost" data-act="settings-pause">Settings</button> <button class="m-btn ghost" data-act="restart">Restart</button> <button class="m-btn ghost" data-act="quit">Quit</button></div></div>`);
  }

  results(r = this.lastResults) {
    this.lastResults = r;
    const i = this.g.routeIndex;
    const next = i + 1 < ROUTES.length;
    this._show(`<div class="paper">
      <div style="font-family:var(--font-sc);letter-spacing:.2em">ARRIVED SAFE AT</div>
      <h2>${ROUTES[i].to}</h2>
      <div class="stars">${stars(r.stars)}</div>
      <div class="results-grid">
      <div class="line"><span>Outlaws dropped</span><span>${r.kills}</span></div>
      <div class="line"><span>Headshots</span><span>${r.headshots}</span></div>
      <div class="line"><span>Accuracy</span><span>${r.accuracy}%</span></div>
      <div class="line"><span>Coach condition</span><span>${r.coach}%</span></div>
      <div class="line"><span>Bounties</span><span>$${r.bounty}</span></div>
      <div class="line"><span>Mail contract</span><span>$${r.reward}</span></div>
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
    this._show(`<div class="paper" style="text-align:left;max-width:640px">
      <h2 style="text-align:center">How to Ride Shotgun</h2>
      ${touch ? `
      <p><b>Aim:</b> drag anywhere on the right. Dragging from the FIRE button aims while you shoot.</p>
      <p><b>Fire / Reload / Swap:</b> buttons at bottom right. Swap between the Schofield and the coach gun any time.</p>
      <p><b>Whip / Rein:</b> buttons at left. The team tires if you whip too long.</p>` : `
      <p><b>Aim:</b> mouse. <b>Fire:</b> left click. <b>Reload:</b> R. <b>Swap:</b> Q. <b>Whip:</b> W / Shift. <b>Rein:</b> S.</p>`}
      <p><b>Dead Eye:</b> ${touch ? 'the eye button' : 'E or right click'}. Time slows. Sweep across outlaws to mark them, then fire to drop every one.</p>
      <p><b>Riflemen</b> flash a glint before they shoot. Drop them first. Riders who reach the team will hurt the coach.</p>
      <div style="text-align:center"><button class="m-btn" data-act="title">Got It</button></div></div>`);
  }

  settings(back = 'title') {
    const q = this.g.renderer.tierName;
    this._show(`<div class="paper"><h2>Settings</h2>
      <div class="opts">
        <label>Graphics</label>
        <select id="opt-q">${['low', 'medium', 'high'].map((t) => `<option ${t === q ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <label>Aim sensitivity</label><input id="opt-sens" type="range" min="0.4" max="2" step="0.05" value="${this.g.input.sens}"/>
        <label>Invert Y</label><input id="opt-inv" type="checkbox" ${this.g.input.invertY ? 'checked' : ''}/>
        <label>Music</label><input id="opt-mus" type="range" min="0" max="1" step="0.05" value="${audio.volumes.music}"/>
        <label>Effects</label><input id="opt-sfx" type="range" min="0" max="1" step="0.05" value="${audio.volumes.sfx}"/>
      </div>
      <button class="m-btn" data-act="${back === 'pause' ? 'pause' : 'title'}">Done</button></div>`);
    const s = (id, fn) => document.getElementById(id).addEventListener('input', (e) => { fn(e.target); this.g.saveSettings(); });
    s('opt-q', (t) => this.g.renderer.setQuality(t.value));
    s('opt-sens', (t) => (this.g.input.sens = +t.value));
    s('opt-inv', (t) => (this.g.input.invertY = t.checked));
    s('opt-mus', (t) => audio.setVolume('music', +t.value));
    s('opt-sfx', (t) => audio.setVolume('sfx', +t.value));
  }

  _act(a, arg) {
    const g = this.g;
    switch (a) {
      case 'title': this.title(); break;
      case 'routes': g.toAttract(); this.routes(); break;
      case 'pick': this.loadout(+arg); break;
      case 'start': save.start = arg; this.loadout(this.routeIndex); break;
      case 'cycle': {
        const [slot, step] = arg.split(':');
        const owned = (slot === 'side' ? SIDEARMS : LONG_GUNS).filter((w) => save.owns(w.id));
        const k = owned.indexOf(WEAPONS[save.equipped(slot)]);
        save.equip(owned[(k + +step + owned.length) % owned.length].id);
        this.loadout(this.routeIndex); break;
      }
      case 'shop': this.gunsmith(arg); break;
      case 'buy': if (save.buy(arg)) audio.play('schofield_cock', { volume: 0.8 }); this.gunsmith(); break;
      case 'equip': save.equip(arg); this.gunsmith(); break;
      case 'shop-done': if (this.shopBack === 'results') this.results(); else this.loadout(this.routeIndex); break;
      case 'go': this.hide(); g.startRide(this.routeIndex); break;
      case 'resume': this.hide(); g.resume(); break;
      case 'pause': this.pause(); break;
      case 'restart': this.hide(); g.startRide(g.routeIndex); break;
      case 'next': this.hide(); g.startRide(g.routeIndex + 1); break;
      case 'quit': g.toAttract(); this.title(); break;
      case 'settings': this.settings('title'); break;
      case 'settings-pause': this.settings('pause'); break;
      case 'how': this.how(); break;
    }
  }
}
