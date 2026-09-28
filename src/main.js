// SCHOFIELD — boot + game state machine (attract → ride → results).
import * as THREE from 'three';
import { Renderer } from './core/renderer.js';
import { Input } from './core/input.js';
import { audio } from './core/audio.js';
import { loadAll } from './core/assets.js';
import { damp } from './core/noise.js';
import { ROUTES } from './world/routes.js';
import { Route } from './world/route.js';
import { Terrain } from './world/terrain.js';
import { Scatter, setImpostorRenderer } from './world/scatter.js';
import { Sky } from './world/sky.js';
import { Towns } from './world/town.js';
import { Railroad } from './world/railroad.js';
import { Water } from './world/water.js';
import { Coach } from './game/coach.js';
import { Player } from './game/player.js';
import { Enemies } from './game/enemies.js';
import { Wildlife } from './game/wildlife.js';
import { createRider, createWeapon } from './game/characters.js';
import { Combat } from './game/combat.js';
import { FX } from './game/fx.js';
import { HUD } from './ui/hud.js';
import { Menus, save } from './ui/menus.js';
import { WEAPONS } from './game/weapons.js';
import { MISSIONS, applyMission } from './game/missions.js';
import { fullscreen } from './core/fullscreen.js';

const DIFF = [
  { riderAcc: 0.3, rifleAcc: 0.4, fireMult: 1.15, dmgMult: 0.85, countMult: 1 },
  { riderAcc: 0.34, rifleAcc: 0.45, fireMult: 1.05, dmgMult: 0.95, countMult: 1 },
  { riderAcc: 0.37, rifleAcc: 0.48, fireMult: 1.0, dmgMult: 1.0, countMult: 1.1 },
  { riderAcc: 0.4, rifleAcc: 0.5, fireMult: 0.92, dmgMult: 1.05, countMult: 1.2 },
];

class Game {
  constructor() {
    this.canvas = document.getElementById('gl');
    this.renderer = new Renderer(this.canvas);
    this.camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 5000);
    this.scene = new THREE.Scene();
    this.renderer.setup(this.scene, this.camera);
    setImpostorRenderer(this.renderer.r);
    this.input = new Input(this.canvas);
    this.hud = new HUD();
    this.menus = new Menus(this);
    this.mode = 'boot';
    this.time = 0; this.timeScale = 1; this.targetScale = 1;
    this.shake = 0; this.bountyTotal = 0;
    this.timer = new THREE.Timer();
    this.hitStopT = 0;
    this._loadSettings();
    window.__game = this; // debug handle
  }

  _loadSettings() {
    try {
      const s = JSON.parse(localStorage.getItem('schofield.settings')) || {};
      if (s.sens) this.input.sens = s.sens;
      this.input.invertY = !!s.invertY;
      if (s.music !== undefined) audio.volumes.music = s.music;
      if (s.sfx !== undefined) audio.volumes.sfx = s.sfx;
    } catch {}
  }
  saveSettings() {
    try { localStorage.setItem('schofield.settings', JSON.stringify({ sens: this.input.sens, invertY: this.input.invertY, music: audio.volumes.music, sfx: audio.volumes.sfx })); } catch {}
  }

  async boot() {
    const fill = document.getElementById('load-fill'), msg = document.getElementById('load-msg');
    const lines = ['Loading the coach…', 'Greasing the axles…', 'Counting the strongbox…', 'Saddling the team…', 'Loading the Schofield…'];
    let li = 0;
    const iv = setInterval(() => { msg.textContent = lines[++li % lines.length]; }, 900);
    await loadAll((p) => { fill.style.width = Math.round(p * 90) + '%'; });
    await audio.init();
    clearInterval(iv);
    msg.textContent = 'Building the territory…';
    fill.style.width = '95%';
    await new Promise((r) => setTimeout(r, 30));
    this.buildWorld(0, 'attract');
    fill.style.width = '100%';
    document.getElementById('loading').classList.remove('show');
    const qs = new URLSearchParams(location.search);
    if (qs.has('route')) this.startRide(+qs.get('route') || 0, qs.get('weapon'));
    else this.menus.title();
    const unlock = () => { audio.resume(); if (this.input.touch) fullscreen.enter(); if (this.mode === 'attract') audio.loop('music_menu', { bus: 'music', volume: 1 }); };
    addEventListener('pointerdown', unlock, { capture: true }); // capture: HUD buttons stop propagation
    // pause when backgrounded or turned to portrait
    document.addEventListener('visibilitychange', () => { if (document.hidden) this.pause(); });
    const portrait = matchMedia('(orientation: portrait)');
    portrait.addEventListener?.('change', () => { if (portrait.matches && this.input.touch) this.pause(); });
    // music is big: decode it after the title is up
    audio.loadDeferred();
    this._loop();
  }

  // ------------------------------------------------------------- world
  disposeWorld() {
    if (!this.route) return;
    this.enemies?.dispose(); this.wildlife?.dispose(); this.coach?.dispose(); this.fx?.dispose(); this.scatter?.dispose(); this.towns?.dispose(); this.rail?.dispose(); this.water?.dispose();
    this.sky?.dispose();
    if (this.terrain) { this.scene.remove(this.terrain.group); this.terrain.tiles.forEach((t) => t.mesh.geometry.dispose()); }
    this.player = null; this.attractGuard = null;
    this.route = null;
  }

  // the two guns you ride with, from the save; `override` (a weapon id, e.g. the
  // ?weapon= debug flag) swaps it into its slot and puts it in hand
  loadout(override) {
    const side = save.equipped('side'), long = save.equipped('long'), o = WEAPONS[override];
    return {
      side: o?.slot === 'side' ? o.id : side,
      long: o?.slot === 'long' ? o.id : long,
      start: o ? o.id : save.start === 'long' ? long : side,
    };
  }

  buildWorld(i, mode, weapon) {
    this.disposeWorld();
    this.routeIndex = i;
    const def = ROUTES[i];
    this.mission = MISSIONS[save.mission] || MISSIONS.mail;
    this.diff = applyMission(DIFF[i] || DIFF[DIFF.length - 1], this.mission);
    this.route = new Route(def);
    this.sky = new Sky(this.scene, this.renderer, this.route);
    this.terrain = new Terrain(this.route, this.scene, this.renderer.tier);
    this.scatter = new Scatter(this.route, this.scene, this.renderer.tier);
    this.terrain.onTile = (t, c) => this.scatter.onTile(t, c);
    this.towns = new Towns(this.route, this.scene);
    // the gorge river and the falls the road runs under
    this.water = null;
    if (def.gorge) {
      const F = this.route.fallsAt();
      this.water = new Water(this.route, this.scene, this.renderer, {
        // out on the valley floor, clear of the wall: the wall occupies roughly
        // 7-34 m off the roadway, so a river inside that is half-buried in it
        // and renders as one long shoreline
        river: { from: 0, to: this.route.len, d: 48 * (this.route.riverSide || 1), width: 24, depth: 2.8 },
        // lean: left to itself the sheet slants ~23 m out toward the river as it
        // falls, so from the road you see the broad face of a slanted banner
        // rather than a wall of water to drive through. Keep it near vertical
        // where it crosses the roadway.
        falls: F ? [{ s: F.s, d: 0, width: F.width, drop: F.drop, lean: 7, ref: 'road', top: 11 }] : [],
      });
    }
    this.rail = def.railroad ? new Railroad(this.route, this.scene, def.railroad) : null;
    if (this.rail) this.rail.onJolt = (k) => { this.shake += 0.16 * k; audio.play('hit_wood_1', { volume: 0.5 * k, pitch: 0.7 }); };
    if (this.rail) this.towns.solids.push(...this.rail.solids);
    this.coach = new Coach(this.route, this.scene, this.mission.coach);
    this.coach.setLivery(this.mission.livery);
    this.fx = new FX(this.scene, this.route);
    this.combat = new Combat(this);
    this.enemies = new Enemies(this);
    this.wildlife = new Wildlife(this);
    this.mode = mode;
    this.over = false; this.arrived = false;
    this.bounty = 0; this.hud.setBounty(0);
    this.coach.s = mode === 'attract' ? 150 : 8;
    this.coach.speed = mode === 'attract' ? 12 : 0;
    this.coach.update(0.016, {});
    if (mode === 'ride') {
      this.player = new Player(this, this.loadout(weapon));
      this.enemies.planFor(this.player);
      this.hud.setRoute(def);
    } else {
      // a guard riding shotgun for the title cinematic
      const guard = createRider({ variant: 'player' });
      (this.coach.seatGuard || this.coach.body).add(guard.root);
      guard.root.rotation.y = 0.5;
      // he's the shotgun messenger — give him the coach gun and the aiming pose,
      // rather than bobbing along empty-handed
      const cg = createWeapon('CoachGun');
      guard.hand.add(cg.root);
      guard.play(guard.has('RideAim') ? 'RideAim' : 'Ride');
      this.attractGuard = guard;
    }
    this.terrain.prime(this.coach.pos.x, this.coach.pos.z);
    this.camera.position.copy(this.coach.pos).add(new THREE.Vector3(0, 4, -8));
    this.camera.lookAt(this.coach.pos);
    this.renderer.r.compile(this.scene, this.camera);
  }

  toAttract() {
    this._cancelLater();
    this.paused = false; audio.ctx?.resume();
    if (this.mode === 'attract') return;
    this.input.setEnabled(false);
    this.hud.show(false);
    audio.stopAll(0.4);
    this.setTimeScale(1); this.timeScale = 1;
    this.buildWorld(0, 'attract');
    audio.loop('music_menu', { bus: 'music', volume: 1 });
  }

  async startRide(i, weapon) {
    this._cancelLater();
    this.paused = false; audio.ctx?.resume();
    audio.stopAll(0.3);
    // show a loading card while the territory is built (can take a couple of seconds on phones)
    const ld = document.getElementById('loading');
    document.getElementById('load-msg').textContent = `${ROUTES[i].from} to ${ROUTES[i].to}…`;
    document.getElementById('load-fill').style.width = '100%';
    ld.classList.add('show');
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    this.buildWorld(i, 'ride', weapon);
    ld.classList.remove('show');
    this.hud.show(true);
    this.input.setEnabled(true);
    this.input.lock();
    this.paused = false;
    this.setTimeScale(1); this.timeScale = 1;
    this.time = 0;
    const def = ROUTES[i];
    this.hud.banner(def.name, `${this.mission.name} — ${def.from} to ${def.to}`, 3.5);
    audio.play('whip_crack', { volume: 0.9 });
    audio.play('horse_neigh', { volume: 0.5, delay: 0.3 });
    audio.loop('horse_gallop_loop', { volume: 0.5 });
    audio.loop('coach_rumble_loop', { volume: 0.45 });
    audio.loop('wind_loop', { volume: 0.25 * def.wind });
    audio.loop('music_ride_loop', { bus: 'music', volume: 0.8 });
    this._inTownMusic = false;
  }

  hitStop(t) { this.hitStopT = Math.max(this.hitStopT, t); }

  _later(ms, fn) { const id = setTimeout(fn, ms); (this._pending ||= []).push(id); }
  _cancelLater() { (this._pending || []).forEach(clearTimeout); this._pending = []; }

  setTimeScale(s) { this.targetScale = s; audio.setRate(s < 1 ? 0.6 : 1); this.renderer.final.uniforms.uDeadeye.value = s < 1 ? 1 : 0; }

  addBounty(v, label, hs) {
    this.bounty += v; this.hud.setBounty(this.bounty);
    this.hud.feedMsg(label, hs);
  }

  onCoachDamage() {
    if (this.coach.hp <= 0 && !this.over) this.fail('The coach was overrun.');
  }

  pause() {
    if (this.mode !== 'ride' || this.over) return;
    this.paused = true;
    this.input.setEnabled(false);
    audio.setRate(0.0001);
    audio.ctx?.suspend();
    this.menus.pause();
  }
  resume() {
    this.paused = false;
    audio.ctx?.resume();
    audio.setRate(this.targetScale < 1 ? 0.6 : 1);
    this.input.setEnabled(true);
    this.input.lock();
  }

  fail(reason) {
    if (this.over) return;
    this.over = true;
    this.input.setEnabled(false);
    this.setTimeScale(0.25);
    audio.stopLoop('music_ride_loop', 0.5);
    audio.stopLoop('music_town_loop', 0.5);
    audio.play('sting_death', { bus: 'music', volume: 1 });
    this.coach.stopping = true;
    // bounties collected on the road are yours even if the run fails
    const kept = this.bounty;
    save.earn(kept);
    this._later(2200, () => { this.setTimeScale(1); this.hud.show(false); this.menus.failed(reason, kept); });
  }

  arrive() {
    if (this.over) return;
    this.over = true; this.arrived = true;
    this.coach.stopping = true;
    this.input.setEnabled(false);
    if (this.player.deadeyeOn) this.player._endDeadeye();
    this.setTimeScale(1);
    this.enemies.list.forEach((e) => { if (e.alive && e.type === 'rider') e.state = 'fleeing'; });
    audio.play('bell_town', { volume: 0.8 });
    audio.stopLoop('music_ride_loop', 1.2);
    audio.stopLoop('music_town_loop', 1.2);
    audio.play(audio.buffers.music_results ? 'music_results' : 'sting_victory', { bus: 'music', volume: 1, delay: 0.6 });
    this.hud.banner(ROUTES[this.routeIndex].to, 'You made it', 3);
    const p = this.player, st = p.stats;
    const accuracy = st.shots ? Math.round((st.hits / st.shots) * 100) : 0;
    const coachPct = Math.max(0, Math.round(this.coach.hp));
    let stars = 1;
    if (coachPct >= 50 && accuracy >= 35) stars = 2;
    if (coachPct >= 75 && accuracy >= 50 && p.hp > 30) stars = 3;
    const reward = Math.round(ROUTES[this.routeIndex].reward * this.mission.pay * (0.5 + coachPct / 200));
    const r = { kills: st.kills, headshots: st.headshots, accuracy, coach: coachPct, bounty: this.bounty, reward, total: this.bounty + reward, stars, mission: this.mission.name };
    save.record(ROUTES[this.routeIndex].id, stars, r.total);
    save.earn(r.total);
    this._later(3500, () => { this.hud.show(false); this.menus.results(r); });
  }

  // ------------------------------------------------------------- loop
  _loop() {
    const tick = () => {
      requestAnimationFrame(tick);
      this.timer.update();
      const rdt = Math.min(0.05, this.timer.getDelta());
      if (this.paused) { this.renderer.render(this.time); return; }
      this.timeScale = damp(this.timeScale, this.targetScale, 8, rdt);
      let dt = rdt * this.timeScale;
      if (this.hitStopT > 0) { this.hitStopT -= rdt; dt *= 0.12; }
      this.time += dt;
      this.update(dt, rdt);
      this.renderer.render(this.time);
      this.renderer.adapt(rdt);
    };
    tick();
  }

  update(dt, rdt) {
    if (!this.route) return;
    const inp = this.input.consume();
    if (inp.pause) { this.pause(); return; }
    const coach = this.coach;
    coach.update(dt, this.mode === 'ride' && !this.over ? inp : {});
    if (this.mode === 'ride') {
      this.player.update(dt, rdt, this.over ? { dx: 0, dy: 0 } : inp);
      this.enemies.update(dt);
      this.wildlife.update(dt);
      if (!this.over && coach.s >= this.route.len - 40) this.arrive();
      // ghost town music
      const inTown = this.route.inTown(coach.s + 40);
      if (inTown !== this._inTownMusic && audio.buffers.music_town_loop && !this.over) {
        this._inTownMusic = inTown;
        if (inTown) { audio.loopVolume('music_ride_loop', 0, 1.5); audio.loop('music_town_loop', { bus: 'music', volume: 0.9 }); }
        else { audio.stopLoop('music_town_loop', 1.5); audio.loopVolume('music_ride_loop', 0.8, 1.5); }
      }
      const sp = coach.speed / 15;
      // Rate-shifting a sample moves its pitch as much as its tempo, so keep the
      // swing narrow — speed/15 outright ran from 0.53x to 1.47x, nearly an
      // octave and a half, and the team sounded like a tape being spun.
      audio.loopRate('horse_gallop_loop', Math.min(1.13, Math.max(0.92, 0.92 + (sp - 0.53) * 0.21)));
      audio.loopVolume('horse_gallop_loop', Math.min(0.6, sp * 0.5), 0.2);
      audio.loopVolume('coach_rumble_loop', Math.min(0.6, sp * 0.45), 0.2);
      if (inp.whip && coach.stamina > 0.05 && !this._whipCd) { audio.play('whip_crack', { volume: 0.7 }); this._whipCd = 1.2; }
      this._whipCd = Math.max(0, (this._whipCd || 0) - rdt) || 0;
      this.hud.update(this);
    } else {
      this._attractCam(rdt);
      this.attractGuard?.update(dt);
    }
    // dust from wheels and team
    const back = new THREE.Vector3().copy(coach.pos).addScaledVector(coach.fwd, -1.6);
    this.fx.trail(back, coach.speed > 4 ? coach.speed * 0.9 : 0, dt, 1.0);
    const team = new THREE.Vector3().copy(coach.pos).addScaledVector(coach.fwd, 5);
    this.fx.trail(team, coach.speed > 4 ? coach.speed * 0.5 : 0, dt, 0.8);
    this.fx.update(dt);
    this.shake = damp(this.shake, 0, 6, rdt);
    this.rail?.update(dt, coach);
    this.water?.update(dt, this.camera, coach.pos);
    this.towns.update(dt, coach);
    this.terrain.update(coach.pos.x, coach.pos.z, 1);
    this.camera.updateMatrixWorld();
    this.scatter.update(this.camera, coach.pos);
    this.sky.update(this.camera, coach.pos, this.time);
    audio.updateListener(this.camera);
  }

  _attractCam(rdt) {
    const c = this.coach;
    this._at = (this._at || 0) + rdt;
    if (c.s > this.route.len - 200) c.s = 150;
    const shot = Math.floor(this._at / 8) % 3;
    const t = (this._at % 8) / 8;
    const right = c.right, fwd = c.fwd;
    const target = new THREE.Vector3();
    const look = new THREE.Vector3().copy(c.pos).add(new THREE.Vector3(0, 1.8, 0));
    // coach framed in the right third, clear of the menu on the left
    if (shot === 0) { target.copy(c.pos).addScaledVector(right, 7).addScaledVector(fwd, 6 - t * 12).add(new THREE.Vector3(0, 1.4, 0)); look.addScaledVector(right, 2.6); }
    else if (shot === 1) { target.copy(c.pos).addScaledVector(fwd, -9 - t * 3).addScaledVector(right, -3).add(new THREE.Vector3(0, 4 + t * 2, 0)); look.addScaledVector(fwd, 6); }
    else { target.copy(c.pos).addScaledVector(fwd, 14 - t * 2).addScaledVector(right, -4 + t * 3).add(new THREE.Vector3(0, 1.2, 0)); look.addScaledVector(fwd, 3); }
    const gh = this.route.height(target.x, target.z) + 0.8;
    target.y = Math.max(target.y, gh);
    if (this._shot !== shot) { this._shot = shot; this.camera.position.copy(target); }
    else this.camera.position.lerp(target, 1 - Math.exp(-6 * rdt));
    this.camera.lookAt(look);
  }
}

const game = new Game();
game.boot();
