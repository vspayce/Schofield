// Train sounds, synthesised into AudioBuffers at runtime so the railroad needs
// no audio files: a chime steam whistle, the exhaust chuff, the bell and a
// rail-clatter loop. Registered into audio.buffers under train_* names, so they
// play through the ordinary audio.play / audio.loop calls.
import { audio } from './audio.js';

const SR = 44100;

function buffer(secs, fill) {
  const ctx = audio.ctx;
  const n = Math.floor(secs * SR);
  const b = ctx.createBuffer(1, n, SR);
  fill(b.getChannelData(0), n);
  return b;
}

// cheap deterministic noise
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2147483648 - 1; };
}

// two-pole resonant band-pass, run in place
function bandpass(d, f, q) {
  const w = 2 * Math.PI * f / SR, a = Math.sin(w) / (2 * q), c = Math.cos(w);
  const b0 = a, b2 = -a, a0 = 1 + a, a1 = -2 * c, a2 = 1 - a;
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  for (let i = 0; i < d.length; i++) {
    const x = d[i];
    const y = (b0 * x + b2 * x2 - a1 * y1 - a2 * y2) / a0;
    x2 = x1; x1 = x; y2 = y1; y1 = y; d[i] = y;
  }
}

function lowpass(d, f) {
  const k = 1 - Math.exp(-2 * Math.PI * f / SR);
  let y = 0;
  for (let i = 0; i < d.length; i++) { y += (d[i] - y) * k; d[i] = y; }
}

function normalise(d, peak = 0.9) {
  let m = 0;
  for (let i = 0; i < d.length; i++) m = Math.max(m, Math.abs(d[i]));
  if (m > 0) for (let i = 0; i < d.length; i++) d[i] *= peak / m;
}

// A three-chime steam whistle: a minor triad of pipes, each rich in odd
// harmonics, that slurs up to pitch as the valve cracks open, with the breath
// of steam through it and a wavering pitch from the pressure.
function whistle(secs) {
  const notes = [311, 370, 466];     // Eb4, F#4, Bb4 — the mournful chime
  const r = rng(7);
  return buffer(secs, (d, n) => {
    const breath = new Float32Array(n);
    for (let i = 0; i < n; i++) breath[i] = r();
    bandpass(breath, 1400, 0.8);
    const ph = notes.map(() => 0);
    for (let i = 0; i < n; i++) {
      const t = i / SR;
      const att = Math.min(1, t / 0.12), rel = Math.min(1, (secs - t) / 0.25);
      const env = att * att * Math.max(0, rel);
      const slur = 0.9 + 0.1 * Math.min(1, t / 0.18);
      const wob = 1 + 0.004 * Math.sin(t * 2 * Math.PI * 5.5) + 0.002 * Math.sin(t * 2 * Math.PI * 1.3);
      let v = 0;
      notes.forEach((f, k) => {
        ph[k] += 2 * Math.PI * f * slur * wob / SR;
        const p = ph[k];
        v += Math.sin(p) + 0.35 * Math.sin(3 * p) + 0.12 * Math.sin(5 * p) + 0.2 * Math.sin(2 * p);
      });
      d[i] = env * (v * 0.3 + breath[i] * 1.6 * (0.6 + 0.4 * att));
    }
    normalise(d, 0.85);
  });
}

// one exhaust beat: a short thump of low, rough noise
function chuff() {
  const r = rng(11);
  return buffer(0.34, (d, n) => {
    for (let i = 0; i < n; i++) d[i] = r();
    lowpass(d, 900); lowpass(d, 1400);
    for (let i = 0; i < n; i++) {
      const t = i / SR;
      d[i] *= Math.min(1, t / 0.008) * Math.exp(-t * 11) * 1.6 + 0.25 * Math.sin(2 * Math.PI * 62 * t) * Math.exp(-t * 18);
    }
    normalise(d, 0.8);
  });
}

// a locomotive bell: inharmonic partials, a hard strike and a long ring
function bell() {
  const parts = [[540, 1, 1.5], [1080, 0.55, 2.2], [1490, 0.35, 3.0], [2920, 0.18, 4.5], [4800, 0.08, 7]];
  return buffer(1.6, (d, n) => {
    for (let i = 0; i < n; i++) {
      const t = i / SR;
      let v = 0;
      for (const [f, a, dcy] of parts) v += a * Math.sin(2 * Math.PI * f * t) * Math.exp(-t * dcy);
      d[i] = v * Math.min(1, t / 0.002);
    }
    normalise(d, 0.7);
  });
}

// Rolling stock over jointed rail: a low rumble with the double clack of each
// truck crossing a rail joint. One bar of it, seamless when looped.
function clatter() {
  const secs = 2.4, r = rng(23);
  return buffer(secs, (d, n) => {
    const rum = new Float32Array(n);
    for (let i = 0; i < n; i++) rum[i] = r();
    lowpass(rum, 120); lowpass(rum, 160);
    const hiss = new Float32Array(n);
    for (let i = 0; i < n; i++) hiss[i] = r();
    bandpass(hiss, 2600, 0.7);
    // clacks: pairs 0.13 s apart (the two axles of a truck), four pairs a bar
    const hits = [];
    for (let k = 0; k < 4; k++) { const t0 = 0.05 + k * 0.6 + (k % 2) * 0.03; hits.push(t0, t0 + 0.13); }
    for (let i = 0; i < n; i++) {
      const t = i / SR;
      let c = 0;
      for (const h of hits) {
        const dt = t - h;
        if (dt >= 0 && dt < 0.09) c += Math.sin(2 * Math.PI * 190 * dt) * Math.exp(-dt * 60) + 0.6 * Math.sin(2 * Math.PI * 820 * dt) * Math.exp(-dt * 90);
      }
      d[i] = rum[i] * 7 + c * 0.5 + hiss[i] * 0.06;
    }
    normalise(d, 0.75);
    // crossfade the ends so the loop has no click
    const f = Math.floor(0.02 * SR);
    for (let i = 0; i < f; i++) { const k = i / f; d[i] *= k; d[n - 1 - i] *= k; }
  });
}

let made = false;
export function makeTrainSounds() {
  if (made || !audio.ctx) return;
  made = true;
  audio.buffers.train_whistle = whistle(2.1);
  audio.buffers.train_whistle_short = whistle(0.7);
  audio.buffers.train_chuff = chuff();
  audio.buffers.train_bell = bell();
  audio.buffers.train_clatter = clatter();
}
