"""Shared DSP helpers for the SCHOFIELD audio generators.

Everything is synthesised from scratch (numpy/scipy). All functions work on float64
arrays at SR = 44100 Hz. Mono = 1-D array, stereo = (N, 2) array.
"""
import numpy as np
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d

SR = 44100


# --------------------------------------------------------------------------- basics
def rng(seed):
    return np.random.default_rng(seed)


def n_of(dur):
    return int(round(dur * SR))


def tvec(dur):
    return np.arange(n_of(dur)) / SR


def silence(dur, ch=1):
    n = n_of(dur)
    return np.zeros(n) if ch == 1 else np.zeros((n, ch))


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def undb(d):
    return 10 ** (d / 20.0)


def mtof(m):
    return 440.0 * 2 ** ((np.asarray(m, dtype=float) - 69) / 12.0)


NOTE_NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def nm(name):
    """'C#5' / 'Bb3' / 'A4' -> midi number."""
    base = NOTE_NAMES[name[0]]
    i = 1
    while i < len(name) and name[i] in '#b':
        base += 1 if name[i] == '#' else -1
        i += 1
    octave = int(name[i:])
    return base + 12 * (octave + 1)


# --------------------------------------------------------------------------- filters
def _sos(kind, f, order=2, fs=SR):
    f = np.atleast_1d(np.asarray(f, dtype=float))
    f = np.clip(f, 10, fs / 2 * 0.98)
    wn = f[0] if f.size == 1 else f
    return signal.butter(order, wn, btype=kind, fs=fs, output='sos')


def lp(x, f, order=2):
    return signal.sosfilt(_sos('lowpass', f, order), x, axis=0)


def hp(x, f, order=2):
    return signal.sosfilt(_sos('highpass', f, order), x, axis=0)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(_sos('bandpass', [lo, hi], order), x, axis=0)


def peak_eq(x, f0, q, gain_db):
    """RBJ peaking EQ biquad."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / SR
    alpha = np.sin(w0) / (2 * q)
    b = [1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A]
    a = [1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A]
    return signal.lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)


def reson(x, f0, q):
    """Constant-peak-gain resonator (RBJ bandpass)."""
    w0 = 2 * np.pi * f0 / SR
    alpha = np.sin(w0) / (2 * q)
    b = [alpha, 0, -alpha]
    a = [1 + alpha, -2 * np.cos(w0), 1 - alpha]
    return signal.lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)


def svf_bp(x, fc, q):
    """Time-varying state-variable bandpass. fc may be an array (per sample)."""
    n = len(x)
    fc = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    qv = np.broadcast_to(np.asarray(q, dtype=float), (n,))
    g = np.tan(np.pi * np.clip(fc, 5, SR * 0.45) / SR)
    k = 1.0 / qv
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    y = np.empty(n)
    ic1 = ic2 = 0.0
    xl = x.tolist()
    a1l, a2l, a3l = a1.tolist(), a2.tolist(), a3.tolist()
    for i in range(n):
        v0 = xl[i]
        v3 = v0 - ic2
        v1 = a1l[i] * ic1 + a2l[i] * v3
        v2 = ic2 + a2l[i] * ic1 + a3l[i] * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        y[i] = v1
    return y


def svf_lp(x, fc, q=0.707):
    n = len(x)
    fc = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    g = np.tan(np.pi * np.clip(fc, 5, SR * 0.45) / SR)
    k = 1.0 / q
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    y = np.empty(n)
    ic1 = ic2 = 0.0
    xl = x.tolist()
    a1l, a2l, a3l = a1.tolist(), a2.tolist(), a3.tolist()
    for i in range(n):
        v0 = xl[i]
        v3 = v0 - ic2
        v1 = a1l[i] * ic1 + a2l[i] * v3
        v2 = ic2 + a2l[i] * ic1 + a3l[i] * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        y[i] = v2
    return y


def fir_eq(x, curve):
    """Zero-phase frequency-domain shaping. curve(freqs)->linear gain. Circular."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / SR)
    g = curve(f)
    if X.ndim == 2:
        g = g[:, None]
    return np.fft.irfft(X * g, n=x.shape[0], axis=0)


def colored_noise(n, r, slope_db_oct=0.0, lo=20, hi=20000):
    """Periodic (loopable) noise with a spectral slope, generated in the freq domain."""
    f = np.fft.rfftfreq(n, 1 / SR)
    mag = np.zeros_like(f)
    ok = (f >= lo) & (f <= hi)
    mag[ok] = (f[ok] / 1000.0) ** (slope_db_oct / 6.0206)
    ph = r.uniform(0, 2 * np.pi, f.size)
    x = np.fft.irfft(mag * np.exp(1j * ph), n=n)
    return x / (np.std(x) + 1e-12)


# --------------------------------------------------------------------------- envelopes
def env_exp(n, tau, attack=0.0005):
    t = np.arange(n) / SR
    e = np.exp(-t / tau)
    if attack > 0:
        e *= 1 - np.exp(-t / (attack / 3))
    return e


def adsr(n, a, d, s, r, hold=None):
    """Piecewise envelope. hold = seconds at sustain before release (default fills)."""
    na, nd, nr = n_of(a), n_of(d), n_of(r)
    nh = n - na - nd - nr if hold is None else n_of(hold)
    nh = max(nh, 0)
    e = np.concatenate([
        np.linspace(0, 1, na, endpoint=False) if na else [],
        1 - (1 - s) * (1 - np.exp(-np.linspace(0, 5, nd))) if nd else [],
        np.full(nh, s),
        s * np.exp(-np.linspace(0, 6, nr)) if nr else [],
    ])
    out = np.zeros(n)
    m = min(n, e.size)
    out[:m] = e[:m]
    return out


def fade(x, fin=0.0, fout=0.0):
    x = x.copy()
    a, b = n_of(fin), n_of(fout)
    if a:
        w = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
        x[:a] *= w if x.ndim == 1 else w[:, None]
    if b:
        w = np.cos(np.linspace(0, np.pi / 2, b)) ** 2
        x[-b:] *= w if x.ndim == 1 else w[:, None]
    return x


# --------------------------------------------------------------------------- building
def place(buf, x, t0, gain=1.0, wrap=False):
    """Mix x into buf at time t0 (seconds). wrap=True folds overflow to the start
    (for circular / seamless loops)."""
    i0 = int(round(t0 * SR))
    n = buf.shape[0]
    if wrap:
        i0 %= n
        pos = 0
        while pos < x.shape[0]:
            start = (i0 + pos) % n
            m = min(n - start, x.shape[0] - pos)
            buf[start:start + m] += gain * x[pos:pos + m]
            pos += m
        return buf
    if i0 >= n:
        return buf
    if i0 < 0:
        x = x[-i0:]
        i0 = 0
    m = min(n - i0, x.shape[0])
    buf[i0:i0 + m] += gain * x[:m]
    return buf


def mix_to(n, *parts):
    out = np.zeros(n)
    for p in parts:
        m = min(n, len(p))
        out[:m] += p[:m]
    return out


def pan(x, p):
    """Equal-power pan, p in [-1, 1]. Returns (N, 2)."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], axis=1)


def circ(fn, x, reps=2):
    """Run a (stable) causal process on a periodic signal so the output is periodic:
    process `reps` copies, keep the last one."""
    n = x.shape[0]
    tiled = np.concatenate([x] * reps, axis=0)
    y = fn(tiled)
    return y[(reps - 1) * n:reps * n]


def fold_tail(buf, n):
    """Fold everything beyond n samples back onto the start (seamless loop)."""
    out = buf[:n].copy()
    pos = n
    while pos < buf.shape[0]:
        m = min(n, buf.shape[0] - pos)
        out[:m] += buf[pos:pos + m]
        pos += m
    return out


def xfade_loop(x, n_loop, n_xf):
    """Classic crossfade loop: x must be >= n_loop + n_xf long. The tail
    x[n_loop:n_loop+n_xf] is equal-power crossfaded into the head."""
    out = x[:n_loop].copy()
    w = np.linspace(0, np.pi / 2, n_xf)
    fin, fout = np.sin(w), np.cos(w)
    if x.ndim == 2:
        fin, fout = fin[:, None], fout[:, None]
    out[:n_xf] = x[:n_xf] * fin + x[n_loop:n_loop + n_xf] * fout
    return out


# --------------------------------------------------------------------------- synthesis
def modal(freqs, decays, amps, dur, r=None, jitter=0.0, phase_rand=True):
    """Sum of exponentially damped sinusoids (modal synthesis)."""
    t = tvec(dur)
    out = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps):
        if r is not None and jitter:
            f = f * (1 + r.uniform(-jitter, jitter))
        ph = r.uniform(0, 2 * np.pi) if (r is not None and phase_rand) else 0
        out += a * np.exp(-t / d) * np.sin(2 * np.pi * f * t + ph)
    return out


def metal_click(r, dur=0.12, base=2600, spread=(1.0, 1.51, 2.27, 3.08, 4.13, 5.4),
                decay=0.03, bright=1.0, body=0.0, body_f=220):
    """Short resonant metallic click: modal ring excited by a tiny noise impulse."""
    freqs = [base * s * (1 + r.uniform(-0.03, 0.03)) for s in spread]
    freqs = [f for f in freqs if f < 19000]
    decays = [decay * (0.9 / (1 + 0.35 * i)) * r.uniform(0.7, 1.3) for i in range(len(freqs))]
    amps = [(0.8 ** i) * r.uniform(0.5, 1.0) * (bright if i > 2 else 1) for i in range(len(freqs))]
    ring = modal(freqs, decays, amps, dur, r)
    n = ring.size
    # exciter: very short click of highpassed noise
    ex = np.zeros(n)
    ne = n_of(0.0015)
    ex[:ne] = r.standard_normal(ne) * np.exp(-np.arange(ne) / (ne / 4))
    ex = hp(ex, 1500)
    out = ring * 0.6 + ex * 1.2
    if body:
        out += body * modal([body_f, body_f * 2.3], [0.012, 0.006], [1, 0.4], dur, r)
    return out


def adsr_note(n, a=0.005, r=0.05):
    e = np.ones(n)
    na, nr = min(n_of(a), n), min(n_of(r), n)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def softclip(x, drive=1.0):
    return np.tanh(x * drive) / np.tanh(drive)


# --------------------------------------------------------------------------- spaces
def outdoor_ir(r, dur=2.2, early=True, slaps=((0.19, 0.32), (0.31, 0.2), (0.47, 0.12)),
               diffuse_gain=0.35, tau=0.45, lp_start=6000, lp_end=900, predelay=0.012):
    """Synthetic outdoor impulse response (mono):
    direct + ground reflection + sparse early reflections + air-absorbed diffuse
    decay + slapback echoes off distant hills (each smeared and low-passed)."""
    n = n_of(dur)
    ir = np.zeros(n)
    ir[0] = 1.0
    if early:
        # ground bounce a few ms later, slightly dull
        ir[n_of(0.0045)] += -0.45
        for _ in range(9):
            tt = r.uniform(0.012, 0.09)
            ir[n_of(tt)] += r.uniform(-1, 1) * 0.18 * np.exp(-tt / 0.06)
    # diffuse tail: noise with frequency-dependent decay (split in 3 bands)
    t = np.arange(n) / SR
    onset = np.clip((t - predelay) / 0.04, 0, 1) ** 2
    nz = r.standard_normal(n)
    lo = lp(nz, 500) * np.exp(-t / (tau * 1.5))
    mid = bp(nz, 500, 2500) * np.exp(-t / (tau * 0.8))
    hi = hp(nz, 2500) * np.exp(-t / (tau * 0.3))
    diff = (lo * 1.2 + mid * 0.8 + hi * 0.5) * onset
    ir += diffuse_gain * diff / (np.sqrt(np.sum(diff ** 2)) + 1e-9)
    # slapbacks: smeared, low-passed copies
    for (d, g) in slaps:
        m = n_of(0.05)
        sm = r.standard_normal(m) * np.exp(-np.arange(m) / (m / 5))
        sm = lp(sm, 2200 * (0.25 / max(d, 0.2)))
        sm /= np.sqrt(np.sum(sm ** 2)) + 1e-9
        place(ir, sm * g, d)
    # progressive air absorption across the whole IR via crossfaded lowpasses
    a = lp(ir, lp_start)
    b = lp(ir, lp_end)
    w = np.clip(t / (dur * 0.5), 0, 1)
    out = a * (1 - w) + b * w
    out[0] = 1.0
    return out


def conv(x, ir):
    return signal.fftconvolve(x, ir)[:len(x) + len(ir) - 1]


def stereo_reverb_ir(r, dur=2.5, tau=0.55, predelay=0.02, damp=4500, er=True):
    """Hall/plate-ish stereo IR (decorrelated L/R noise decays) for music."""
    n = n_of(dur)
    t = np.arange(n) / SR
    chans = []
    for c in range(2):
        nz = r.standard_normal(n)
        lo = lp(nz, 700) * np.exp(-t / (tau * 1.25))
        mid = bp(nz, 700, 3500) * np.exp(-t / tau)
        hi = hp(nz, 3500) * np.exp(-t / (tau * 0.45))
        d = lo + mid * 0.8 + hi * 0.4
        d = lp(d, damp)
        onset = np.clip((t - predelay) / 0.03, 0, 1)
        d *= onset
        if er:
            for _ in range(12):
                tt = r.uniform(predelay * 0.5, predelay + 0.07)
                d[n_of(tt)] += r.uniform(-1, 1) * 0.6 * np.max(np.abs(d))
        chans.append(d)
    ir = np.stack(chans, axis=1)
    ir /= np.sqrt(np.sum(ir ** 2) / 2)
    return ir


def reverb_stereo(x, ir, wet=0.3, circular=False):
    """x: mono or stereo; ir: (N,2). Returns stereo wet+dry, same length as x
    (+tail unless circular)."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    if circular:
        n = x.shape[0]
        wetl = circ_conv(x[:, 0], ir[:, 0])
        wetr = circ_conv(x[:, 1], ir[:, 1])
        return x * (1 - wet * 0.5) + wet * np.stack([wetl, wetr], axis=1)
    wl = signal.fftconvolve(x[:, 0], ir[:, 0])
    wr = signal.fftconvolve(x[:, 1], ir[:, 1])
    n = wl.size
    out = np.zeros((n, 2))
    out[:x.shape[0]] += x * (1 - wet * 0.5)
    out[:, 0] += wet * wl
    out[:, 1] += wet * wr
    return out


def circ_conv(x, h):
    n = x.size
    if h.size > n:
        h = h[:n]
    H = np.fft.rfft(h, n)
    return np.fft.irfft(np.fft.rfft(x) * H, n)


# --------------------------------------------------------------------------- loudness
def _k_weight(x):
    """ITU-R BS.1770 K-weighting at arbitrary fs (coeffs as in pyloudnorm)."""
    fs = SR
    # high shelf
    G, Q, fc = 4.0, 1 / np.sqrt(2), 1500.0
    A = 10 ** (G / 40.0)
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    b0 = A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * np.cos(w0))
    b2 = A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
    a1 = 2 * ((A - 1) - (A + 1) * np.cos(w0))
    a2 = (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha
    y = signal.lfilter([b0 / a0, b1 / a0, b2 / a0], [1, a1 / a0, a2 / a0], x, axis=0)
    # high pass
    fc, Q = 38.0, 0.5
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    b = np.array([(1 + np.cos(w0)) / 2, -(1 + np.cos(w0)), (1 + np.cos(w0)) / 2])
    a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
    return signal.lfilter(b / a[0], a / a[0], y, axis=0)


def lufs(x):
    """Integrated loudness (gated) — BS.1770-4. Mono is treated as a single channel."""
    y = _k_weight(x)
    if y.ndim == 1:
        y = y[:, None]
    blk, hop = n_of(0.4), n_of(0.1)
    if y.shape[0] < blk:
        y = np.concatenate([y, np.zeros((blk - y.shape[0], y.shape[1]))])
    zs = []
    for s in range(0, y.shape[0] - blk + 1, hop):
        zs.append(np.sum(np.mean(y[s:s + blk] ** 2, axis=0)))
    zs = np.array(zs)
    lk = -0.691 + 10 * np.log10(zs + 1e-20)
    zs = zs[lk > -70]
    if zs.size == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(zs)) - 10
    lk2 = -0.691 + 10 * np.log10(zs + 1e-20)
    zs2 = zs[lk2 > rel]
    return float(-0.691 + 10 * np.log10(np.mean(zs2)))


def limiter(x, ceiling_db=-1.0, release=0.08, lookahead=0.003):
    """Simple look-ahead peak limiter (no clipping above ceiling)."""
    thr = undb(ceiling_db)
    mag = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    g = np.minimum(1.0, thr / np.maximum(mag, 1e-12))
    la = max(1, n_of(lookahead))
    g = minimum_filter1d(g, size=2 * la + 1)
    g = uniform_filter1d(g, size=la)
    # release smoothing (one-pole, only when gain rises)
    coef = np.exp(-1 / (release * SR))
    gs = np.empty_like(g)
    prev = 1.0
    gl = g.tolist()
    for i, v in enumerate(gl):
        prev = v if v < prev else coef * prev + (1 - coef) * v
        gs[i] = prev
    y = x * (gs if x.ndim == 1 else gs[:, None])
    peak = np.max(np.abs(y))
    if peak > thr:
        y *= thr / peak
    return y


def normalize_peak(x, dbfs=-1.0):
    p = np.max(np.abs(x))
    return x * (undb(dbfs) / p) if p > 0 else x


def normalize_lufs(x, target=-14.0, ceiling=-1.0):
    g = undb(target - lufs(x))
    return limiter(x * g, ceiling)
