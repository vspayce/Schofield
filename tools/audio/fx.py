"""Dead Eye, heartbeat, UI."""
import numpy as np
from dsp import (SR, rng, n_of, lp, hp, bp, env_exp, place, modal, metal_click,
                 normalize_peak, normalize_lufs, fade, svf_bp, softclip, fold_tail,
                 stereo_reverb_ir, reverb_stereo, limiter)


def _heartbeat(r, gain=1.0, pitch=1.0):
    """lub-dub: two low, pitched-down thumps."""
    out = np.zeros(n_of(0.6))
    for i, (tt, g, f0) in enumerate(((0.0, 1.0, 58), (0.27, 0.7, 66))):
        n = n_of(0.3)
        t = np.arange(n) / SR
        f = (f0 * pitch) * (1 + 0.6 * np.exp(-t / 0.02))
        th = softclip(np.sin(2 * np.pi * np.cumsum(f) / SR) * 2.5) * env_exp(n, 0.07, 0.008)
        body = lp(r.standard_normal(n), 120) * env_exp(n, 0.05, 0.01)
        body /= np.max(np.abs(body))
        knock = bp(r.standard_normal(n), 90, 450) * env_exp(n, 0.025, 0.004)
        knock /= np.max(np.abs(knock))
        place(out, (th + 0.35 * body + 0.35 * knock) * g, tt)
    return out * gain


def heartbeat_loop():
    r = rng(60)
    bpm = 64
    beat = 60 / bpm
    L = n_of(beat * 2)
    out = np.zeros(L)
    place(out, _heartbeat(r, 1.0), 0.0, wrap=True)
    place(out, _heartbeat(r, 0.92, 0.98), beat, wrap=True)
    out = softclip(out / np.max(np.abs(out)) * 1.2)
    return normalize_peak(out, -1.0)


def _whoosh(r, dur, f0, f1, curve=2.0):
    n = n_of(dur)
    t = np.arange(n) / SR
    fc = f0 * (f1 / f0) ** ((t / dur) ** curve)
    w = svf_bp(r.standard_normal(n), fc, 1.4)
    w2 = svf_bp(r.standard_normal(n), fc * 2.1, 3)
    return (w + 0.4 * w2) / np.max(np.abs(w + 0.4 * w2))


def deadeye_in():
    r = rng(900)
    dur = 2.6
    out = np.zeros(n_of(dur))
    # rising air swell into the hit
    sw = _whoosh(r, 0.45, 300, 3000) * np.linspace(0, 1, n_of(0.45)) ** 2.5
    place(out, sw * 0.9, 0.0)
    # low boom: very low pitch drop + filtered noise
    n = n_of(2.2)
    t = np.arange(n) / SR
    f = 48 + 70 * np.exp(-t / 0.08)
    boom = softclip(np.sin(2 * np.pi * np.cumsum(f) / SR) * 2) * env_exp(n, 0.4, 0.004)
    nb = lp(r.standard_normal(n), 400) * env_exp(n, 0.2, 0.003)
    boom += 0.6 * nb / np.max(np.abs(nb))
    place(out, boom * 1.0, 0.43)
    # falling whoosh (time slowing down) after the hit
    fall = _whoosh(r, 1.4, 2400, 150, 0.6) * env_exp(n_of(1.4), 0.5, 0.01)
    place(out, fall * 0.35, 0.43)
    # pitched-down heartbeat swell
    place(out, _heartbeat(r, 0.9, 0.85), 1.2)
    place(out, _heartbeat(r, 0.7, 0.82), 1.95)
    # add a sub-bass swell tone under it all
    tone = np.sin(2 * np.pi * 41 * np.arange(n_of(2.0)) / SR) * \
        np.sin(np.linspace(0, np.pi, n_of(2.0))) ** 2
    place(out, tone * 0.08, 0.5)
    rv = stereo_reverb_ir(r, 2.0, 0.5)
    st = reverb_stereo(out, rv, wet=0.25)[:out.size].mean(axis=1)
    st = fade(st, 0, 0.4)
    return normalize_peak(limiter(st * 1.3, -1.0), -1.0)


def deadeye_out():
    r = rng(901)
    dur = 1.0
    n = n_of(dur)
    t = np.arange(n) / SR
    # reverse whoosh: swell up and cut, rising pitch (time snapping back)
    sw = _whoosh(r, dur, 180, 3500, 1.5)
    env = (t / dur) ** 3
    env[-n_of(0.012):] *= np.linspace(1, 0, n_of(0.012))
    y = sw * env
    f = 60 * (1 + 3 * (t / dur) ** 2)
    rise = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 2
    y += 0.35 * rise
    # reversed reverb tail feel: exponential-growth noise
    rv = lp(r.standard_normal(n), 3000) * np.exp((t - dur) / 0.2)
    y += 0.25 * rv / np.max(np.abs(rv))
    # tiny snap at the end
    place(y, hp(r.standard_normal(n_of(0.01)), 2000) * env_exp(n_of(0.01), 0.002) * 0.4,
          dur - 0.015)
    y = fade(y, 0, 0.012)
    return normalize_peak(y, -1.0)


def ui_click():
    r = rng(7)
    n = n_of(0.09)
    wood = modal([780, 1930, 3300], [0.012, 0.007, 0.004], [1, 0.5, 0.3], 0.09, r)
    tick = metal_click(r, 0.09, base=3600, decay=0.008)
    y = wood * 0.9 + tick * 0.45
    return normalize_peak(fade(y, 0, 0.02), -1.0)


SOUNDS = {
    'deadeye_in': deadeye_in,
    'deadeye_out': deadeye_out,
    'heartbeat_loop': heartbeat_loop,
    'ui_click': ui_click,
}
