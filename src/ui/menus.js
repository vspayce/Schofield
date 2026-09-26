// Title / route select / loadout / pause / results / settings screens.
import { ROUTES } from '../world/routes.js';
import { WEAPONS } from '../game/player.js';
import { audio } from '../core/audio.js';

const el = document.getElementById('menu');
const UI = import.meta.env.BASE_URL + 'assets/ui/';

export const save = {
  data: (() => { try { return JSON.parse(localStorage.getItem('schofield.save')) || {}; } catch { return {}; } })(),
  get unlocked() { return this.data.unlocked ?? 0; },
  stars(id) { return (this.data.stars || {})[id] || 0; },
  best(id) { return (this.data.best || {})[id] || 0; },
  record(i, id, stars, bounty) {
    const d = this.data;
    d.stars = d.stars || {}; d.best = d.best || {};
    d.stars[id] = Math.max(d.stars[id] || 0, stars);
    d.best[id] = Math.max(d.best[id] || 0, bounty);
    if (stars > 0) d.unlocked = Math.max(d.unlocked || 0, Math.min(ROUTES.length - 1, i + 1));
    try { localStorage.setItem('schofield.save', JSON.stringify(d)); } catch {}
  },
  get weapon() { return this.data.weapon || 'schofield'; },
  set weapon(v) { this.data.weapon = v; try { localStorage.setItem('schofield.save', JSON.stringify(this.data)); } catch {} },
};

function click() { audio.play('ui_click', { volume: 0.6 }); }
function stars(n) { return '★'.repeat(n) + '☆'.repeat(3 - n); }

function logo() {
  return `<img class="m-logo" src="${UI}logo.png" alt="SCHOFIELD" onerror="this.outerHTML='<h1 class=&quot;logo-text&quot;>SCHOFIELD</h1>'"/>`;
}

export class Menus {
  constructor(game) { this.g = game; }

  hide() { el.classList.remove('show', 'dim', 'title-screen'); el.innerHTML = ''; }

  _show(html, dim = true, cls = '') {
    el.innerHTML = `<div class="m-wrap">${html}</div>`;
    el.classList.add('show'); el.classList.toggle('dim', dim);
    el.classList.toggle('title-screen', cls === 'title');
    el.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', (e) => { click(); this._act(b.dataset.act, b.dataset.arg, e); }));
  }

  title() {
    this._show(`
      ${logo()}
      <div class="m-tag">Ride shotgun on the Overland Mail. Keep the strongbox. Keep your scalp.</div>
      <button class="m-btn" data-act="routes">Ride Out</button>
      <div class="m-row" style="margin-top:6px">
        <button class="m-btn ghost" data-act="settings">Settings</button>
        <button class="m-btn ghost" data-act="how">How to Play</button>
      </div>`, false, 'title');
  }

  routes() {
    const posters = ROUTES.map((r, i) => {
      const locked = i > save.unlocked;
      return `<div class="poster ${locked ? 'locked' : ''}" data-act="${locked ? '' : 'pick'}" data-arg="${i}"><div class="pin">
        <div><h3>${r.name}</h3><div class="sub">${r.from} → ${r.to}</div></div>
        <div class="sub">${r.blurb}</div>
        <div><div class="stars">${stars(save.stars(r.id))}</div><div class="reward">REWARD $${r.reward}</div></div></div>
        ${locked ? '<div class="lock">LOCKED</div>' : ''}
      </div>`;
    }).join('');
    this._show(`<h2 class="m-title">Choose Your Route</h2><div class="m-row">${posters}</div>
      <button class="m-btn ghost" style="margin-top:14px" data-act="title">Back</button>`);
  }

  loadout(i) {
    this.routeIndex = i;
    const cur = save.weapon;
    const card = (W) => `<div class="gun-card ${cur === W.id ? 'sel' : ''}" data-act="gun" data-arg="${W.id}">
        <img src="${UI}weapon_${W.id}.png" alt="" onerror="this.style.visibility='hidden'"/>
        <h3>${W.name}</h3><p>${W.blurb}</p>
        ${Object.entries(W.stats).map(([k, v]) => `<div class="stat"><span>${k}</span><div class="b"><i style="width:${v * 100}%"></i></div></div>`).join('')}
      </div>`;
    this._show(`<h2 class="m-title">${ROUTES[i].name}</h2>
      <div class="m-tag" style="margin:-6px 0 12px">Pick your iron. You can swap on the coach.</div>
      <div class="m-row">${card(WEAPONS.schofield)}${card(WEAPONS.shotgun)}</div>
      <div class="m-row" style="margin-top:12px"><button class="m-btn ghost" data-act="routes">Back</button><button class="m-btn" data-act="go">All Aboard</button></div>`);
  }

  pause() {
    this._show(`<div class="paper"><h2>Paused</h2>
      <div style="margin:10px 0"><button class="m-btn" data-act="resume">Resume</button></div>
      <div><button class="m-btn ghost" data-act="settings-pause">Settings</button> <button class="m-btn ghost" data-act="restart">Restart</button> <button class="m-btn ghost" data-act="quit">Quit</button></div></div>`);
  }

  results(r) {
    const i = this.g.routeIndex;
    const next = i + 1 < ROUTES.length && i + 1 <= save.unlocked;
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
      <div class="m-row" style="margin-top:10px">
        <button class="m-btn ghost" data-act="routes">Routes</button>
        <button class="m-btn ghost" data-act="restart">Ride Again</button>
        ${next ? `<button class="m-btn" data-act="next">Next Route</button>` : ''}
      </div></div>`);
  }

  failed(reason) {
    this._show(`<div class="paper"><h2>Dead &amp; Buried</h2>
      <div style="font-style:italic;margin:6px 0 14px">${reason}</div>
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
      case 'routes':
        if (g.input.touch && !document.fullscreenElement) {
          document.documentElement.requestFullscreen?.({ navigationUI: 'hide' }).then(() => screen.orientation?.lock?.('landscape')).catch(() => {});
        }
        g.toAttract(); this.routes(); break;
      case 'pick': this.loadout(+arg); break;
      case 'gun': save.weapon = arg; this.loadout(this.routeIndex); break;
      case 'go': this.hide(); g.startRide(this.routeIndex, save.weapon); break;
      case 'resume': this.hide(); g.resume(); break;
      case 'pause': this.pause(); break;
      case 'restart': this.hide(); g.startRide(g.routeIndex, save.weapon); break;
      case 'next': this.hide(); g.startRide(g.routeIndex + 1, save.weapon); break;
      case 'quit': g.toAttract(); this.title(); break;
      case 'settings': this.settings('title'); break;
      case 'settings-pause': this.settings('pause'); break;
      case 'how': this.how(); break;
    }
  }
}
