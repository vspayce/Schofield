"""Synthetic instruments for the Morricone-style score (all from scratch).

Plucked strings use Karplus-Strong; winds/brass are additive with continuous
pitch tracks (glides, delayed vibrato); choir = detuned polyBLEP saw stacks through
vowel formant banks; percussion = modal synthesis.
"""
import numpy as np
from scipy import signal
from dsp import (SR, n_of, lp, hp, bp, env_exp, place, modal, reson, svf_bp, softclip,
                 mtof, peak_eq, fold_tail, circ_conv)


# =========================================================================== timing
class Grid:
    def __init__(self, bpm, bars, beats_per_bar=4):
        self.bpm, self.bars, self.bpb = bpm, bars, beats_per_bar
        self.beat = 60.0 / bpm
        self.bar = self.beat * beats_per_bar
        self.length = self.bar * bars
        self.N = n_of(self.length)

    def t(self, bar, beat=0.0):
        """bar is 1-indexed."""
        return ((bar - 1) * self.bpb + beat) * self.beat


# =========================================================================== strings
_KS_CACHE = {}


def ks(freq, dur, r, bright=0.5, pos=0.2, decay=2.5, key=None):
    """Karplus-Strong pluck with exact pitch (resampled) and pick-position comb."""
    if key is not None and key in _KS_CACHE:
        return _KS_CACHE[key]
    N = max(2, int(round(SR / freq - 0.5)))
    fa = SR / (N + 0.5)
    ratio = freq / fa
    out_len = n_of(dur)
    total = int(out_len * ratio) + N + 4
    exc = r.standard_normal(N + 1)
    # brightness: one-pole lowpass on the excitation
    a = 1 - bright
    exc = signal.lfilter([1 - a], [1, -a], exc)
    k = max(1, int(pos * N))
    exc = exc - np.roll(exc, k)
    exc -= exc.mean()
    exc /= np.max(np.abs(exc)) + 1e-9
    rho = 10 ** (-3.0 / (freq * decay))
    y = np.zeros(total)
    y[:N + 1] = exc
    s = N + 1
    while s < total:
        e = min(s + N, total)
        y[s:e] = rho * 0.5 * (y[s - N:e - N] + y[s - N - 1:e - N - 1])
        s = e
    idx = np.arange(out_len) * ratio
    out = np.interp(idx, np.arange(total), y)
    if key is not None:
        _KS_CACHE[key] = out
    return out


def pluck_note(r, midi, dur, kind='nylon', vel=1.0, ring=2.5, variant=None):
    """A single guitar note of length dur (+ short release)."""
    f = float(mtof(midi))
    v = variant if variant is not None else int(r.integers(0, 4))
    if kind == 'nylon':
        raw = ks(f, ring, r, bright=0.35 + 0.1 * v / 4, pos=0.22, decay=2.2,
                 key=('nylon', midi, v))
    elif kind == 'twang':
        raw = ks(f, ring, r, bright=0.92, pos=0.09, decay=3.5, key=('twang', midi, v))
    elif kind == 'bass':
        raw = ks(f, ring, r, bright=0.25, pos=0.3, decay=2.0, key=('bass', midi, v))
    else:
        raise ValueError(kind)
    m = min(raw.size, n_of(dur + 0.04))
    x = raw[:m].copy()
    rel = n_of(0.04)
    if m > rel and dur < ring - 0.05:
        x[-rel:] *= np.linspace(1, 0, rel) ** 2
    return x * vel


def strum(buf, r, t0, midis, dur, down=True, vel=1.0, spread=0.012, wrap=True,
          kind='nylon'):
    order = midis if down else midis[::-1]
    for i, m in enumerate(order):
        g = vel * (1.0 if i < 3 else 0.85) * r.uniform(0.85, 1.05)
        place(buf, pluck_note(r, m, dur - i * spread, kind, g), t0 + i * spread, wrap=wrap)


def chord_voicing(root_midi, quality, low=40):
    """Open-ish guitar voicing (6 strings-ish) for a triad."""
    third = 3 if quality in ('m', 'm7') else 4
    r0 = root_midi
    while r0 - 12 >= low:
        r0 -= 12
    while r0 < low:
        r0 += 12
    notes = [r0, r0 + 7, r0 + 12, r0 + 12 + third, r0 + 19]
    if quality == '7':
        notes[-1] = r0 + 22
    return notes


def spring_ir(r, dur=2.2):
    """Spring-reverb-ish IR: dispersive 'drip' chirps recurring every ~31 ms."""
    n = n_of(dur)
    t = np.arange(n) / SR
    ir = bp(r.standard_normal(n), 250, 4500) * np.exp(-t / 0.55) * 0.3
    cl = n_of(0.014)
    tc = np.arange(cl) / SR
    fch = 3800 * (400 / 3800) ** (tc / tc[-1])
    chirp = np.sin(2 * np.pi * np.cumsum(fch) / SR) * np.hanning(cl)
    k = 1
    while k * 0.031 < dur - 0.02:
        tt = k * 0.031 + r.uniform(-0.002, 0.002)
        place(ir, chirp * np.exp(-tt / 0.5) * 0.9 * (-1) ** k, tt)
        k += 1
    ir = lp(ir, 5000)
    return ir / np.sqrt(np.sum(ir ** 2))


def twang_fx(x, r, circular=True, drive=2.5, slap=0.11, spring_wet=0.35):
    """Light overdrive + slapback echo + spring reverb (the Morricone twang)."""
    y = softclip(hp(x, 70) * drive) / drive * 1.5
    y = lp(y, 5500)
    n = y.size
    d1 = int(slap * SR)
    if circular:
        e = y + 0.38 * np.roll(y, d1) + 0.16 * np.roll(y, 2 * d1) + 0.06 * np.roll(y, 3 * d1)
        sp = circ_conv(e, spring_ir(r))
    else:
        e = y.copy()
        for k, g in ((1, 0.38), (2, 0.16), (3, 0.06)):
            e[k * d1:] += g * y[:n - k * d1]
        sp = signal.fftconvolve(e, spring_ir(r))[:n]
    return e + spring_wet * sp / (np.std(sp) + 1e-9) * np.std(e)


# =========================================================================== lead tracks
def lead_track(notes, N, glide=0.035, attack=0.03, release=0.09, legato_gap=0.03,
               wrap=False):
    """notes: list of (t_start, dur, midi, vel). Returns per-sample (midi, amp, age)."""
    notes = sorted(notes, key=lambda z: z[0])
    tgt = np.full(N, float(notes[0][2]))
    amp = np.zeros(N)
    age = np.full(N, 10.0)
    for i, (t0, d, m, v) in enumerate(notes):
        s = int(t0 * SR)
        e = int((t0 + d) * SR)
        nxt = int(notes[i + 1][0] * SR) if i + 1 < len(notes) else N
        legato = i + 1 < len(notes) and notes[i + 1][0] - (t0 + d) < legato_gap
        tgt[s:max(nxt, s)] = m
        a = max(1, n_of(attack))
        if s >= N:
            continue
        seg_end = nxt if legato else e
        ln = max(1, seg_end - s)
        body = np.ones(ln) * v
        body[:min(a, ln)] *= np.sin(np.linspace(0, np.pi / 2, min(a, ln))) ** 2
        body *= np.linspace(1, 0.85, ln)  # slight natural decay over the note
        rl = max(1, n_of(release))
        tail = body[-1] * np.exp(-np.arange(rl * 5) / rl)
        env = np.concatenate([body, tail])[:N - s]
        amp[s:s + env.size] = np.maximum(amp[s:s + env.size], env)
        age[s:] = np.minimum(age[s:], np.arange(N - s) / SR)
    k = 1 - np.exp(-1 / (glide * SR))
    midi = signal.lfilter([k], [1, -(1 - k)], tgt, zi=[tgt[0] * (1 - k)])[0]
    return midi, amp, age


def _vibrato(age, t, rate=5.5, depth=0.007, delay=0.2, ramp=0.35, r=None):
    d = np.clip((age - delay) / ramp, 0, 1) * depth
    drift = 0
    if r is not None:
        drift = lp(r.standard_normal(t.size), 3) * 3
    return 1 + d * np.sin(2 * np.pi * rate * t + 0.3 * drift)


def whistle(notes, N, r):
    midi, amp, age = lead_track(notes, N, glide=0.03, attack=0.035, release=0.07)
    t = np.arange(N) / SR
    f = mtof(midi) * _vibrato(age, t, 5.7, 0.009, 0.18, 0.3, r)
    f *= 2 ** (-0.35 / 12 * np.exp(-age / 0.05))  # little upward scoop into each note
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.05 * np.sin(2 * ph) + 0.015 * np.sin(3 * ph)
    active = amp > 1e-4
    breath = np.zeros(N)
    idx = np.where(active)[0]
    if idx.size:
        a0, a1 = idx[0], idx[-1] + 1
        breath[a0:a1] = svf_bp(r.standard_normal(a1 - a0), f[a0:a1], 9)
        breath /= np.std(breath[a0:a1]) + 1e-9
    return amp * (tone + 0.09 * breath)


def ocarina(notes, N, r):
    midi, amp, age = lead_track(notes, N, glide=0.02, attack=0.04, release=0.1)
    t = np.arange(N) / SR
    f = mtof(midi) * _vibrato(age, t, 4.8, 0.004, 0.25, 0.3, r)
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.12 * np.sin(2 * ph + 0.5) + 0.06 * np.sin(3 * ph)
    breath = lp(hp(r.standard_normal(N), 800), 3500)
    chiff = np.exp(-age / 0.03)
    return amp * (tone + breath * (0.05 + 0.25 * chiff))


def trumpet(notes, N, r, bright_base=0.3, mute=False):
    midi, amp, age = lead_track(notes, N, glide=0.02, attack=0.045, release=0.12)
    t = np.arange(N) / SR
    f = mtof(midi) * _vibrato(age, t, 5.3, 0.011, 0.3, 0.4, r)
    f *= 2 ** (-0.7 / 12 * np.exp(-age / 0.035))  # lip scoop
    ph = 2 * np.pi * np.cumsum(f) / SR
    blat = np.exp(-age / 0.06)
    bright = np.clip(bright_base + 0.5 * amp + 0.25 * blat, 0, 0.93)
    out = np.zeros(N)
    fmean = float(np.median(f[amp > 0.01])) if np.any(amp > 0.01) else 600
    kmax = int(min(26, 15000 / fmean))
    for k in range(1, kmax + 1):
        fk = k * f
        form = 1 + 1.6 * np.exp(-((fk - 1250) / 450) ** 2) + 0.9 * np.exp(-((fk - 2600) / 700) ** 2)
        a = bright ** (k - 1) * form * (fk < 17000)
        out += a * np.sin(k * ph)
    out /= 3.0
    breath = bp(r.standard_normal(N), 1000, 5000) * (0.02 + 0.1 * blat)
    y = amp * (out + breath)
    if mute:
        y = peak_eq(lp(y, 3000), 1500, 1.5, 6)
    return y


def harmonica(notes, N, r, chord=(0,)):
    """Reed harmonica: two slightly detuned reeds per note, reedy spectrum, tremolo."""
    midi, amp, age = lead_track(notes, N, glide=0.03, attack=0.06, release=0.15)
    t = np.arange(N) / SR
    out = np.zeros(N)
    for off in chord:
        for det in (-0.06, 0.07):
            f = mtof(midi + off + det) * _vibrato(age, t, 5.0, 0.004, 0.3, 0.4, r)
            ph = 2 * np.pi * np.cumsum(f) / SR + r.uniform(0, 6)
            for k in range(1, 14):
                a = (1 / k ** 0.8) * (1.4 if k in (2, 3) else 1.0)
                out += a * np.sin(k * ph) * (k * np.median(f) < 15000)
    out = peak_eq(out, 1600, 1.2, 5)
    trem = 1 - 0.12 * (0.5 + 0.5 * np.sin(2 * np.pi * 5.2 * t))
    breath = bp(r.standard_normal(N), 1500, 6000) * 0.8
    return amp * (out / (np.std(out) + 1e-9) * 0.3 + breath * 0.05) * trem


# =========================================================================== choir
VOWELS = {
    # F (Hz), gain (dB), bandwidth (Hz) — classic formant tables
    'ah': ([800, 1150, 2900, 3900, 4950], [0, -6, -32, -20, -50], [80, 90, 120, 130, 140]),
    'ah_m': ([650, 1080, 2650, 2900, 3250], [0, -6, -7, -8, -22], [80, 90, 120, 130, 140]),
    'oo': ([350, 600, 2700, 2900, 3300], [0, -20, -17, -14, -26], [40, 60, 100, 120, 120]),
    'oh': ([450, 800, 2830, 3500, 4950], [0, -9, -16, -28, -55], [70, 80, 100, 130, 135]),
}


def polyblep_saw(f, r):
    dt = f / SR
    ph = (np.cumsum(dt) + r.uniform()) % 1.0
    y = 2 * ph - 1
    m1 = ph < dt
    x = ph[m1] / dt[m1]
    y[m1] -= x + x - x * x - 1
    m2 = ph > 1 - dt
    x = (ph[m2] - 1) / dt[m2]
    y[m2] -= x * x + x + x + 1
    return y


def formant_bank(x, vowel):
    F, G, B = VOWELS[vowel]
    y = np.zeros_like(x)
    for f, g, b in zip(F, G, B):
        y += 10 ** (g / 20) * reson(x, f, f / b)
    return y


def choir(chords, N, r, vowel='ah', voices=3, swell=0.6, release=0.8, breath=0.05):
    """chords: list of (t0, dur, [midis], vel). Each note = detuned saw stack."""
    src = np.zeros(N + n_of(release * 4 + 1))
    M = src.size
    t = np.arange(M) / SR
    for (t0, d, midis, vel) in chords:
        s = int(t0 * SR)
        L = n_of(d + release * 3)
        tt = np.arange(L) / SR
        env = np.clip(tt / (swell * d if swell < 1 else swell), 0, 1) ** 1.5
        env *= np.where(tt < d, 1.0, np.exp(-(tt - d) / release))
        seg = np.zeros(L)
        for m in midis:
            for v in range(voices):
                det = (v - (voices - 1) / 2) * 0.09 + r.normal(0, 0.02)
                vib = 1 + 0.005 * np.sin(2 * np.pi * r.uniform(4.6, 5.6) * tt + r.uniform(0, 6))
                drift = 1 + 0.002 * lp(r.standard_normal(L), 2) * 4
                f = mtof(m + det) * vib * drift
                seg += polyblep_saw(f, r) / voices
        seg *= env * vel
        e = min(M, s + L)
        src[s:e] += seg[:e - s]
    y = formant_bank(src, vowel)
    nz = formant_bank(r.standard_normal(M), vowel) * breath
    amp_env = lp(np.abs(src), 20)
    y += nz * amp_env / (np.max(amp_env) + 1e-9) * np.std(y) * 3
    y = lp(y, 6000)
    return y


# =========================================================================== jaw harp
def jaw_twang(r, f0, h_from=4, h_to=8, dur=0.45, sweep=0.12):
    n = n_of(dur)
    t = np.arange(n) / SR
    src = polyblep_saw(np.full(n, f0), r) * np.exp(-t / 0.3)
    src *= 1 - np.exp(-t / 0.002)
    fc = f0 * (h_from + (h_to - h_from) * (1 - np.exp(-t / sweep)))
    y = svf_bp(src, fc, 11)
    y = y / (np.max(np.abs(y)) + 1e-9) + 0.15 * lp(src, 400)
    return y * np.exp(-t / 0.25)


# =========================================================================== percussion
def kick(r, f_end=46, tau=0.22):
    n = n_of(0.7)
    t = np.arange(n) / SR
    f = f_end + 60 * np.exp(-t / 0.028)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, tau, 0.002)
    y += 0.3 * lp(r.standard_normal(n), 2500) * env_exp(n, 0.004, 0.0003)
    return y


def snare(r, vel=1.0, tau=0.09):
    n = n_of(0.35)
    t = np.arange(n) / SR
    nz = bp(r.standard_normal(n), 1400, 8000) * env_exp(n, tau, 0.0008)
    tone = (np.sin(2 * np.pi * 185 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * env_exp(n, 0.035)
    return (nz / (np.max(np.abs(nz)) + 1e-9) + 0.5 * tone) * vel


def clipclop(r, hi=True):
    """Coconut-shell horse hoof 'clip-clop'."""
    f = r.uniform(1050, 1150) if hi else r.uniform(760, 840)
    y = modal([f, f * 1.9, f * 3.3], [0.025, 0.012, 0.006], [1, 0.35, 0.15], 0.12, r)
    y += 0.4 * bp(r.standard_normal(y.size), 800, 4000) * env_exp(y.size, 0.004, 0.0002)
    return y


def anvil(r, base=1180, dur=2.0):
    ratios = [1, 2.43, 3.61, 5.33, 6.44, 8.1, 9.7]
    y = modal([base * q for q in ratios], [1.2, 0.8, 0.6, 0.45, 0.3, 0.2, 0.15],
              [1, 0.8, 0.6, 0.45, 0.35, 0.25, 0.15], dur, r, jitter=0.01)
    y += 0.8 * hp(r.standard_normal(y.size), 2000) * env_exp(y.size, 0.003, 0.0002)
    return y


BELL_PARTS = [(0.5, 7.0, 0.55), (1.0, 5.0, 0.6), (1.19, 4.2, 0.55), (1.5, 2.5, 0.25),
              (2.0, 3.6, 1.0), (2.51, 2.2, 0.45), (2.66, 1.8, 0.35), (3.01, 1.6, 0.4),
              (4.1, 0.9, 0.3), (5.2, 0.6, 0.18), (6.4, 0.4, 0.12)]


def bell(r, prime, dur=5.0, decay_scale=1.0):
    n = n_of(dur)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, dec, amp in BELL_PARTS:
        f = prime * ratio
        if f > 16000:
            continue
        b = r.uniform(0.4, 1.8)
        y += amp * np.exp(-t / (dec * decay_scale)) * (
            np.sin(2 * np.pi * f * t + r.uniform(0, 6)) + 0.6 * np.sin(2 * np.pi * (f + b) * t))
    y *= 1 - np.exp(-t / 0.0015)
    y[:n_of(0.03)] += hp(r.standard_normal(n_of(0.03)), 1500) * env_exp(n_of(0.03), 0.005) * 2
    return y


def timpani(r, f0=73.4, vel=1.0, dur=2.5):
    y = modal([f0, f0 * 1.5, f0 * 1.99, f0 * 2.44, f0 * 2.9], [1.4, 0.9, 0.7, 0.5, 0.35],
              [1, 0.6, 0.35, 0.2, 0.1], dur, r)
    y += 0.5 * lp(r.standard_normal(y.size), 800) * env_exp(y.size, 0.02, 0.001)
    return y * vel


def tamtam(r, dur=5.0, bloom=0.6):
    n = n_of(dur)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for _ in range(70):
        f = np.exp(r.uniform(np.log(120), np.log(6000)))
        dec = r.uniform(1.5, 4.0) * (1000 / f) ** 0.3
        rise = 1 - np.exp(-t / (bloom * (f / 3000) ** 0.7 + 0.01))
        y += r.uniform(0.2, 1) * np.sin(2 * np.pi * f * t + r.uniform(0, 6)) * np.exp(-t / dec) * rise
    return y / np.max(np.abs(y))
