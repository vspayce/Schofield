// WebAudio manager. Buffers come from assets.audio (ArrayBuffers). Everything
// degrades silently if a sound is missing. Positional sounds are panned and
// attenuated relative to the listener (camera) manually — cheaper than PannerNodes
// on mobile and good enough for a rail shooter.
import * as THREE from 'three';
import { assets } from './assets.js';

// authored loop lengths at 44.1 kHz (see tools/audio)
const LOOP_SAMPLES = {
  horse_gallop_loop: 194040, coach_rumble_loop: 352800, wind_loop: 705600, heartbeat_loop: 82688,
  music_ride_loop: 2822400, music_menu: 2116800, music_town_loop: 1984500,
};

class AudioSys {
  constructor() {
    this.ctx = null;
    this.buffers = {};
    this.loops = {};
    this.listener = new THREE.Object3D();
    this.rate = 1; // global playback rate (Dead Eye slows everything)
    this.volumes = { master: 0.9, sfx: 1, music: 0.55 };
    this._tmp = new THREE.Vector3();
  }

  async init() {
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = this.volumes.master;
    // gentle master compression keeps gunfire from clipping when stacked
    this.comp = this.ctx.createDynamicsCompressor();
    this.comp.threshold.value = -10; this.comp.ratio.value = 4; this.comp.attack.value = 0.003; this.comp.release.value = 0.2;
    this.master.connect(this.comp).connect(this.ctx.destination);
    this.sfx = this.ctx.createGain(); this.sfx.gain.value = this.volumes.sfx; this.sfx.connect(this.master);
    this.music = this.ctx.createGain(); this.music.gain.value = this.volumes.music; this.music.connect(this.master);
    // lowpass for Dead Eye muffling
    this.muffle = this.ctx.createBiquadFilter(); this.muffle.type = 'lowpass'; this.muffle.frequency.value = 20000;
    this.muffle.connect(this.sfx);
    const entries = Object.entries(assets.audio);
    await Promise.all(entries.map(async ([k, ab]) => {
      try { this.buffers[k] = await this.ctx.decodeAudioData(ab.slice(0)); } catch (e) { console.warn('decode', k); }
    }));
  }

  resume() { if (this.ctx && this.ctx.state !== 'running') this.ctx.resume(); }

  setVolume(kind, v) {
    this.volumes[kind] = v;
    if (this.ctx) this[kind === 'master' ? 'master' : kind].gain.value = v;
  }

  // position: THREE.Vector3 in world space (optional)
  play(name, { volume = 1, pitch = 1, position = null, bus = 'fx', delay = 0, maxDist = 400, rand = 0.04 } = {}) {
    if (!this.ctx) return null;
    const buf = this.buffers[name];
    if (!buf) return null;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = pitch * this.rate * (1 + (Math.random() * 2 - 1) * rand);
    const g = this.ctx.createGain();
    let out = g;
    let vol = volume;
    if (position) {
      const rel = this._tmp.copy(position).applyMatrix4(this._inv || new THREE.Matrix4());
      const d = rel.length();
      vol *= 1 / (1 + (d / 12) ** 1.3);
      if (d > maxDist) return null;
      const pan = this.ctx.createStereoPanner ? this.ctx.createStereoPanner() : null;
      if (pan) { pan.pan.value = THREE.MathUtils.clamp(rel.x / Math.max(4, d), -0.85, 0.85); g.connect(pan); out = pan; }
    }
    g.gain.value = vol;
    src.connect(g);
    out.connect(bus === 'music' ? this.music : this.muffle);
    src.start(this.ctx.currentTime + delay);
    return src;
  }

  loop(name, { volume = 1, bus = 'fx', fade = 0.6 } = {}) {
    if (!this.ctx || !this.buffers[name]) return;
    if (this.loops[name]) { this.loopVolume(name, volume, fade); return; }
    const src = this.ctx.createBufferSource();
    const buf = this.buffers[name];
    src.buffer = buf; src.loop = true;
    // MP3 encoder padding: trim to the exact authored loop length
    const exp = LOOP_SAMPLES[name];
    if (exp && buf.length > exp) {
      src.loopStart = (buf.length - exp * (buf.sampleRate / 44100)) / buf.sampleRate;
      src.loopEnd = src.loopStart + exp / 44100;
    }
    const g = this.ctx.createGain(); g.gain.value = 0;
    src.connect(g).connect(bus === 'music' ? this.music : this.muffle);
    src.start();
    g.gain.setTargetAtTime(volume, this.ctx.currentTime, fade / 3);
    this.loops[name] = { src, g, baseRate: 1 };
  }

  loopVolume(name, v, fade = 0.3) {
    const l = this.loops[name]; if (!l) return;
    l.g.gain.setTargetAtTime(v, this.ctx.currentTime, fade / 3);
  }

  loopRate(name, r) {
    const l = this.loops[name]; if (!l) return;
    l.baseRate = r;
    l.src.playbackRate.setTargetAtTime(r * this.rate, this.ctx.currentTime, 0.1);
  }

  stopLoop(name, fade = 0.8) {
    const l = this.loops[name]; if (!l) return;
    l.g.gain.setTargetAtTime(0, this.ctx.currentTime, fade / 3);
    l.src.stop(this.ctx.currentTime + fade * 2);
    delete this.loops[name];
  }

  stopAll(fade = 0.5) { Object.keys(this.loops).forEach((k) => this.stopLoop(k, fade)); }

  setRate(r) {
    this.rate = r;
    if (!this.ctx) return;
    for (const l of Object.values(this.loops)) l.src.playbackRate.setTargetAtTime(l.baseRate * r, this.ctx.currentTime, 0.15);
    this.muffle.frequency.setTargetAtTime(r < 1 ? 1600 : 20000, this.ctx.currentTime, 0.2);
  }

  updateListener(camera) {
    this._inv = this._inv || new THREE.Matrix4();
    this._inv.copy(camera.matrixWorld).invert();
  }
}

export const audio = new AudioSys();
