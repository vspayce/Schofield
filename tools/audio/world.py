"""Horses, coach, wind, whip, town bell."""
import numpy as np
from dsp import (SR, rng, n_of, lp, hp, bp, env_exp, place, modal, metal_click,
                 outdoor_ir, conv, normalize_peak, normalize_lufs, fade, svf_bp, svf_lp,
                 colored_noise, circ, fir_eq, softclip, reson, limiter)


# =========================================================================== gallop
def _hoof(r, gain=1.0, dirt=1.0):
    n = n_of(0.16)
    t = np.arange(n) / SR
    f = 62 + r.uniform(40, 70) * np.exp(-t / 0.012)
    thud = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, 0.03, 0.0015)
    body = lp(r.standard_normal(n), r.uniform(600, 900), 2) * env_exp(n, 0.018, 0.0008)
    body /= np.max(np.abs(body)) + 1e-9
    # hoof wall 'clop' (dull, dirt damps it)
    clop = modal([r.uniform(380, 460), r.uniform(900, 1100), r.uniform(1700, 2100)],
                 [0.012, 0.007, 0.004], [1, 0.5, 0.25], 0.16, r)
    # dirt spray: sparse grains 1.5-6 kHz over ~50 ms
    grains = hp(r.standard_normal(n), 1500) * (r.random(n) < 0.12) * env_exp(n, 0.025, 0.002)
    grains = lp(grains, 6500)
    y = thud * 0.9 + body * 0.8 + clop * 0.25 + grains * 0.9 * dirt
    return y * gain


def _exhale(r, dur=0.16, gain=1.0, flutter=30):
    n = n_of(dur)
    t = np.arange(n) / SR
    nz = r.standard_normal(n)
    x = reson(nz, r.uniform(380, 480), 3) * 1.0 + reson(nz, r.uniform(1100, 1400), 4) * 0.6 \
        + bp(nz, 2000, 4000) * 0.15
    am = 0.55 + 0.45 * np.sin(2 * np.pi * flutter * t + r.uniform(0, 6)) ** 2
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.7 * np.exp(-t / (dur * 0.8))
    x = x * am * e
    return x / (np.max(np.abs(x)) + 1e-9) * gain


def _snort(r, gain=1.0):
    """Bigger nasal blow with lip/nostril flutter ('brrr')."""
    n = n_of(0.38)
    t = np.arange(n) / SR
    nz = r.standard_normal(n)
    x = reson(nz, 300, 2.5) + 0.8 * reson(nz, 900, 3) + 0.4 * reson(nz, 1900, 4)
    am = np.clip(np.sin(2 * np.pi * 26 * t), 0, 1) ** 2 * 0.8 + 0.2
    e = (1 - np.exp(-t / 0.02)) * np.exp(-t / 0.13)
    x = x * am * e
    return x / (np.max(np.abs(x)) + 1e-9) * gain


def horse_gallop_loop():
    r = rng(1860)
    stride = 0.55
    strides = 8
    L = n_of(stride * strides)
    out = np.zeros(L)
    beats = [0.0, 0.075, 0.19, 0.262]       # hind, hind, fore, leading fore
    gains = [0.75, 0.85, 0.8, 1.0]
    for s in range(strides):
        t0 = s * stride + r.normal(0, 0.004)
        for b, g in zip(beats, gains):
            tt = t0 + b + r.normal(0, 0.005)
            place(out, _hoof(r, g * r.uniform(0.85, 1.1), dirt=r.uniform(0.7, 1.2)), tt,
                  wrap=True)
        # tack jingle: bit rings / buckles bounce after the fore landing
        for k in range(int(r.integers(2, 5))):
            place(out, metal_click(r, 0.08, base=r.uniform(3800, 5200), decay=0.02) * 0.07,
                  t0 + 0.27 + k * r.uniform(0.02, 0.05), wrap=True)
        # leather saddle creak-thump at suspension
        place(out, lp(r.standard_normal(n_of(0.06)), 500) * env_exp(n_of(0.06), 0.02) * 0.1,
              t0 + 0.33, wrap=True)
        # respiration locked to stride: exhale on the leading fore landing
        if s in (3, 7):
            place(out, _snort(r, 0.55), t0 + 0.27, wrap=True)
        else:
            place(out, _exhale(r, r.uniform(0.13, 0.18), r.uniform(0.2, 0.32)), t0 + 0.28,
                  wrap=True)
    out = circ(lambda x: hp(x, 35), out)
    return normalize_lufs(out, -14, -1.0)


# =========================================================================== neigh
def horse_neigh():
    r = rng(1500)
    dur = 1.85
    n = n_of(dur)
    t = np.arange(n) / SR
    # ---- F0 contour (Hz): squeal onset, high plateau, pulsed descent, low rough end
    kt = [0.0, 0.06, 0.18, 0.38, 0.52, 0.8, 1.1, 1.35, 1.55, 1.8]
    kf = [520, 930, 1080, 1150, 1060, 820, 600, 450, 330, 260]
    f0 = np.interp(t, kt, kf)
    # whinny pulsing: FM + AM at ~10-12 Hz, depth ramping in after the squeal
    rate = np.interp(t, [0, 0.5, 1.0, 1.8], [7, 10.5, 12, 10])
    rate = rate * (1 + 0.1 * lp(r.standard_normal(n), 8) * 8)
    vph = 2 * np.pi * np.cumsum(rate) / SR
    depth = np.interp(t, [0, 0.35, 0.6, 1.2, 1.8], [0.01, 0.02, 0.1, 0.13, 0.08])
    jitter = lp(r.standard_normal(n), 25) * 6
    f0 = f0 * (1 + depth * (np.sin(vph) + 0.35 * np.sin(2 * vph - 0.8))) * (1 + 0.012 * jitter)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    am_pulse = 1 - np.interp(t, [0, 0.45, 0.7, 1.8], [0, 0.1, 0.55, 0.5]) * \
        (0.5 - 0.5 * np.cos(vph)) ** 1.5
    # ---- time-varying formants ("iiih" -> "haa" -> "hmm")
    F = [np.interp(t, [0, 0.4, 0.9, 1.8], a) for a in
         ([700, 820, 900, 500], [2500, 2100, 1500, 1100], [3400, 3100, 2800, 2500],
          [4500, 4300, 4000, 3700])]
    B = [250, 350, 450, 600]
    A = [1.0, 0.8, 0.45, 0.25]

    def env(freq):
        e = 0.02 * np.ones_like(freq)
        for Fi, Bi, Ai in zip(F, B, A):
            e += Ai / (1 + ((freq - Fi) / (Bi / 2)) ** 2)
        return e

    voice = np.zeros(n)
    for k in range(1, 18):
        fk = k * f0
        a = env(fk) * (k ** -0.45) * (fk < 16000)
        voice += a * np.sin(k * ph + r.uniform(0, 1))
    # biphonation: an independent, higher, non-harmonic whistle in the squeal
    g0 = f0 * 2.31 * (1 + 0.02 * np.sin(2 * np.pi * 5 * t))
    bi = np.sin(2 * np.pi * np.cumsum(g0) / SR) * np.interp(t, [0, 0.05, 0.45, 0.65],
                                                             [0, 0.35, 0.3, 0])
    voice += bi * 0.5
    # subharmonic roughness in the low tail (period doubling)
    sub = np.sin(ph / 2) * np.interp(t, [0, 1.2, 1.45, 1.8], [0, 0, 0.35, 0.3])
    voice += sub * env(f0 / 2) * 2
    # breath noise through the same formants, strong at onset & end
    nz = r.standard_normal(n)
    breath = sum(Ai * reson(nz, float(np.mean(Fi)), 5) for Fi, Ai in zip(F, A))
    breath *= np.interp(t, [0, 0.04, 0.2, 1.2, 1.6, 1.8], [0.9, 0.5, 0.12, 0.15, 0.4, 0.3])
    amp = np.interp(t, [0, 0.03, 0.1, 1.4, 1.7, 1.85], [0, 0.7, 1.0, 0.8, 0.25, 0])
    rough = 1 + 0.25 * lp(r.standard_normal(n), 90) * 12 * np.interp(t, [0, 0.8, 1.8], [0.3, 0.6, 1.0])
    voice = voice * np.clip(rough, 0.2, 1.8)
    y = (voice / np.max(np.abs(voice)) * am_pulse + breath / np.max(np.abs(breath)) * 0.25) \
        * amp
    y = softclip(y * 1.3)
    ir = outdoor_ir(r, dur=1.2, slaps=((0.22, 0.12),), tau=0.3, diffuse_gain=0.25)
    out = conv(y, ir)[:n_of(2.4)]
    out = fade(out, 0, 0.3)
    return normalize_peak(out, -1.0)


# =========================================================================== coach
def coach_rumble_loop():
    r = rng(1851)
    P = 8.0
    L = n_of(P)
    t = np.arange(L) / SR
    out = np.zeros(L)
    # 1. continuous low rumble of iron tyres on hard dirt (periodic noise)
    rum = colored_noise(L, r, -6, lo=35, hi=350)
    und = 0.7 + 0.15 * np.sin(2 * np.pi * 2 / P * t) + 0.1 * np.sin(2 * np.pi * 11 / P * t + 1) \
        + 0.08 * np.sin(2 * np.pi * 23 / P * t + 2)
    out += rum * und * 0.13
    # 2. gravel crunch (periodic grain noise), modulated by the wheels
    gr = colored_noise(L, r, -2, lo=1200, hi=7000) * (r.random(L) < 0.05)
    wheel = 0.6 + 0.4 * np.sin(2 * np.pi * 14 / P * t) ** 2
    out += circ(lambda x: lp(x, 5000), gr) * wheel * 0.35
    # 3. wheel bumps (front 2.5 rev/s, rear 1.75 rev/s) - wooden thunks
    for rate, g in ((20 / P, 0.35), (14 / P, 0.45)):
        k = 0
        while k / rate < P:
            thunk = modal([r.uniform(90, 130), r.uniform(240, 300), r.uniform(560, 700)],
                          [0.05, 0.025, 0.012], [1, 0.5, 0.3], 0.2, r)
            place(out, thunk * g * r.uniform(0.6, 1.1), k / rate + r.normal(0, 0.004),
                  wrap=True)
            k += 1
    # 4. random ruts - heavier body jolts through the thoroughbraces
    for _ in range(7):
        tt = r.uniform(0, P)
        n = n_of(0.35)
        jt = lp(r.standard_normal(n), 220) * env_exp(n, 0.08, 0.01)
        place(out, jt / np.max(np.abs(jt)) * r.uniform(0.4, 0.7), tt, wrap=True)
        # rattles: loose luggage / door / wooden fittings knocking after a jolt
        for k in range(int(r.integers(4, 10))):
            knock = modal([r.uniform(700, 1100), r.uniform(1800, 2600), r.uniform(3500, 4500)],
                          [0.02, 0.012, 0.006], [1, 0.5, 0.3], 0.08, r)
            place(out, knock * r.uniform(0.12, 0.28), tt + 0.03 + k * r.uniform(0.03, 0.06),
                  wrap=True)
    # 5. creaks: wood/leather stick-slip, pulse train through wood formants
    for _ in range(6):
        dur = r.uniform(0.35, 0.8)
        n = n_of(dur)
        tc = np.arange(n) / SR
        fr = r.uniform(70, 110) * (1 + 0.5 * np.sin(np.pi * tc / dur)) * \
            (1 + 0.05 * lp(r.standard_normal(n), 20) * 5)
        ph = np.cumsum(fr) / SR
        pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
        pulses *= r.uniform(0.5, 1.0, n)
        cr = reson(pulses, r.uniform(450, 650), 6) + 0.8 * reson(pulses, r.uniform(1100, 1500), 8) \
            + 0.4 * reson(pulses, r.uniform(2300, 2900), 10)
        cr *= np.sin(np.pi * tc / dur) ** 1.2
        place(out, cr / (np.max(np.abs(cr)) + 1e-9) * r.uniform(0.25, 0.4), r.uniform(0, P),
              wrap=True)
    # 6. trace chains / harness hardware jingling
    for _ in range(14):
        tt = r.uniform(0, P)
        for k in range(int(r.integers(3, 7))):
            place(out, metal_click(r, 0.1, base=r.uniform(2600, 4200), decay=0.03) *
                  r.uniform(0.03, 0.07), tt + k * r.uniform(0.015, 0.04), wrap=True)
    out = circ(lambda x: hp(x, 30), out)
    return normalize_lufs(out, -14, -1.0)


# =========================================================================== wind
def wind_loop():
    r = rng(1849)
    P = 16.0
    L = n_of(P)
    t = np.arange(L) / SR

    def gust(off):
        return np.clip(0.5 + 0.22 * np.sin(2 * np.pi * t / P + 0.3 + off)
                       + 0.16 * np.sin(2 * np.pi * 3 * t / P + 1.7 + off * 2)
                       + 0.09 * np.sin(2 * np.pi * 7 * t / P + 4.1 + off * 3)
                       + 0.05 * np.sin(2 * np.pi * 13 * t / P + 2.2), 0.08, 1.2)

    chans = []
    for c in range(2):
        g = gust(c * 0.25)
        base = colored_noise(L, r, -3, lo=90, hi=5000)
        body = circ(lambda x: svf_lp(x, np.tile(180 + 900 * g ** 1.5, 2), 0.8), base)
        wh1 = circ(lambda x: svf_bp(x, np.tile(420 + 650 * g, 2), 14), colored_noise(L, r, 0, 100, 5000))
        wh2 = circ(lambda x: svf_bp(x, np.tile(1050 + 900 * g ** 2, 2), 22), colored_noise(L, r, 0, 100, 8000))
        rustle = colored_noise(L, r, -1, lo=2500, hi=11000)
        flick = 0.6 + 0.4 * np.abs(colored_noise(L, r, -12, 2, 30))
        y = body * (0.35 + 0.65 * g) * 0.9 \
            + wh1 / np.std(wh1) * 0.22 * g ** 2 \
            + wh2 / np.std(wh2) * 0.1 * g ** 3 \
            + rustle * 0.07 * g ** 2 * np.clip(flick, 0, 2)
        chans.append(y)
    out = np.stack(chans, axis=1)
    out = circ(lambda x: hp(x, 70, 2), out)
    return normalize_lufs(out, -14, -1.0)


# =========================================================================== whip
def whip_crack():
    r = rng(1776)
    out = np.zeros(n_of(1.3))
    # swish of the lash through the air
    n = n_of(0.3)
    tt = np.arange(n) / SR
    sw = svf_bp(r.standard_normal(n), 350 * (1 + 8 * (tt / 0.3) ** 2), 1.8)
    sw *= (tt / 0.3) ** 2.2
    place(out, sw / np.max(np.abs(sw)) * 0.3, 0.0)
    # the crack: supersonic tip - N-wave + very short hard noise burst
    k = n_of(0.00035)
    nw = np.zeros(n_of(0.02))
    nw[:k] = np.linspace(1, -1, k)
    nw[k:2 * k] = np.linspace(-1, 0, k) * 0.4
    burst = hp(r.standard_normal(nw.size), 1800) * env_exp(nw.size, 0.0018, 0.00005)
    crack = nw + burst / np.max(np.abs(burst)) * 0.8
    crack = softclip(crack * 1.5)
    ir = outdoor_ir(r, dur=1.0, slaps=((0.17, 0.2), (0.3, 0.1)), tau=0.25, diffuse_gain=0.35)
    place(out, conv(crack, ir), 0.3)
    out = limiter(normalize_peak(out, 0) * 2.0, -1.0, 0.04)
    return normalize_peak(fade(out, 0, 0.2), -1.0)


# =========================================================================== bell
def bell_town():
    r = rng(1880)
    dur = 6.5
    p = 293.7  # prime ~ D4 (strike note is the nominal, D5)
    parts = [  # ratio, decay (s), amp
        (0.5, 7.0, 0.55), (1.0, 5.0, 0.6), (1.19, 4.2, 0.55), (1.5, 2.5, 0.25),
        (2.0, 3.6, 1.0), (2.51, 2.2, 0.45), (2.66, 1.8, 0.35), (3.01, 1.6, 0.4),
        (3.34, 1.1, 0.2), (4.1, 0.9, 0.3), (5.2, 0.6, 0.18), (6.4, 0.4, 0.12),
        (7.7, 0.3, 0.08), (9.1, 0.2, 0.05)]
    n = n_of(dur)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, dec, amp in parts:
        f = p * ratio
        beat = r.uniform(0.4, 1.8)  # doublet beating (asymmetry)
        y += amp * np.exp(-t / dec) * (np.sin(2 * np.pi * f * t + r.uniform(0, 6)) +
                                       0.6 * np.sin(2 * np.pi * (f + beat) * t + r.uniform(0, 6)))
    y *= 1 - np.exp(-t / 0.0015)
    # clapper strike: metallic clang burst
    strike = hp(r.standard_normal(n_of(0.05)), 1500) * env_exp(n_of(0.05), 0.006, 0.0002)
    place(y, strike * 2.5, 0)
    ir = outdoor_ir(r, dur=3.0, slaps=((0.3, 0.2), (0.55, 0.12)), tau=0.9, diffuse_gain=0.4)
    out = conv(y, ir * 0.8)[:n]
    return normalize_peak(fade(out, 0, 1.2), -1.0)


SOUNDS = {
    'horse_gallop_loop': horse_gallop_loop,
    'horse_neigh': horse_neigh,
    'coach_rumble_loop': coach_rumble_loop,
    'wind_loop': wind_loop,
    'whip_crack': whip_crack,
    'bell_town': bell_town,
}
