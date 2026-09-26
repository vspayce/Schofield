"""Gunfire, weapon mechanics, bullet whiz / ricochet / impacts."""
import numpy as np
from dsp import (SR, rng, n_of, tvec, lp, hp, bp, peak_eq, env_exp, place, modal,
                 metal_click, outdoor_ir, conv, softclip, normalize_peak, fade, svf_bp,
                 reson, limiter, normalize_lufs, undb)


# =========================================================================== reports
def _report(r, dur, crack_tau=0.0035, crack_hp=900, crack_gain=1.0,
            blast_tau=0.022, blast_lp=3800, blast_gain=1.4,
            thump_f0=125, thump_f1=55, thump_tau=0.045, thump_gain=0.6,
            drive=1.6):
    """Dry muzzle report: supersonic crack + muzzle blast + low body thump."""
    n = n_of(dur)
    t = np.arange(n) / SR
    nz = r.standard_normal(n)
    # 1. crack: a steep N-wave-ish spike and a very short hard noise burst
    crack = hp(nz, crack_hp, 2) * env_exp(n, crack_tau, attack=0.00012)
    crack = peak_eq(crack, 3200, 1.0, 5)
    nw = np.zeros(n)
    k = n_of(0.0007)
    nw[:k] = np.linspace(1, -1, k)
    nw[k:2 * k] = np.linspace(-1, 0, k) * 0.6
    crack = crack / (np.max(np.abs(crack)) + 1e-9) + 0.5 * nw
    # 2. blast: broadband noise, dulled, a bit longer, with 2-stage decay
    blast = lp(nz * 0.8 + r.standard_normal(n) * 0.4, blast_lp, 2)
    be = 0.8 * env_exp(n, blast_tau, attack=0.0004) + 0.2 * env_exp(n, blast_tau * 4, 0.002)
    blast = peak_eq(blast * be, 900, 0.8, 6)
    blast = hp(blast, 150)
    blast /= np.max(np.abs(blast)) + 1e-9
    # 3. thump: pitched-down sine + lowpassed noise body
    f = thump_f1 + (thump_f0 - thump_f1) * np.exp(-t / 0.025)
    ph = 2 * np.pi * np.cumsum(f) / SR
    thump = np.sin(ph) * env_exp(n, thump_tau, attack=0.0015)
    body = lp(r.standard_normal(n), 180, 2) * env_exp(n, thump_tau * 0.8, 0.001)
    body /= np.max(np.abs(body)) + 1e-9
    thump = thump + 0.5 * body
    dry = crack_gain * crack + blast_gain * blast + thump_gain * thump
    dry = softclip(dry / np.max(np.abs(dry)) * drive, 1.0)
    return hp(dry, 35, 2)


def _shot(seed, dur=2.4, wet=0.35, ir_kw=None, squash=8.5, **kw):
    r = rng(seed)
    dry = _report(r, 0.6, **kw)
    ir = outdoor_ir(r, **(ir_kw or {}))
    ir[0] = 0.0  # wet only; add dry ourselves
    wetsig = conv(hp(dry, 220, 2), ir)
    out = np.zeros(n_of(dur))
    place(out, dry, 0)
    place(out, wetsig * wet, 0)
    out = fade(out, 0, 0.3)
    return normalize_peak(limiter(normalize_peak(out, 0) * undb(squash), -1.0, 0.05), -1.0)


def schofield_shot():
    return _shot(4501, dur=2.3, wet=0.75,
                 ir_kw=dict(dur=2.2, slaps=((0.21, 0.30), (0.34, 0.2), (0.52, 0.12)),
                            tau=0.42, diffuse_gain=0.5))


def schofield_shot2():
    return _shot(4502, dur=2.3, wet=0.75, crack_tau=0.003, crack_hp=1100, thump_f0=135,
                 thump_f1=52, blast_lp=3200,
                 ir_kw=dict(dur=2.2, slaps=((0.17, 0.26), (0.29, 0.22), (0.44, 0.14),
                                            (0.63, 0.07)),
                            tau=0.4, diffuse_gain=0.5))


def shotgun_shot():
    r = rng(1212)
    # two superimposed reports a hair apart = wider, thicker blast
    a = _report(r, 0.9, crack_tau=0.005, crack_hp=600, crack_gain=0.8, blast_tau=0.045,
                blast_lp=2600, blast_gain=1.5, thump_f0=95, thump_f1=40, thump_tau=0.1,
                thump_gain=1.4, drive=2.8)
    b = _report(r, 0.9, crack_tau=0.004, crack_hp=800, blast_tau=0.03, blast_lp=2000,
                thump_f0=110, thump_f1=40, thump_tau=0.1, drive=2.0)
    dry = np.zeros(n_of(0.95))
    place(dry, a, 0)
    place(dry, b * 0.6, 0.0023)
    dry /= np.max(np.abs(dry))
    ir = outdoor_ir(r, dur=3.2, slaps=((0.24, 0.17), (0.39, 0.13), (0.61, 0.09), (0.9, 0.05)),
                    tau=0.6, diffuse_gain=0.65, lp_end=700)
    ir[0] = 0
    out = np.zeros(n_of(3.3))
    place(out, dry, 0)
    place(out, conv(hp(dry, 160, 2), ir) * 0.6, 0)
    out = fade(out, 0, 0.4)
    return normalize_peak(limiter(normalize_peak(out, 0) * undb(7), -1.0, 0.07), -1.0)


def rifle_shot_far():
    """Distant rifle: supersonic bullet crack arrives first, muzzle boom ~0.3 s later,
    heavily low-passed with a big wet tail."""
    r = rng(777)
    n = n_of(2.8)
    out = np.zeros(n)
    # bullet crack (N-wave, bright but small)
    k = n_of(0.0005)
    nw = np.zeros(n_of(0.05))
    nw[:k] = np.linspace(1, -1, k)
    nw[k:2 * k] = np.linspace(-1, 0, k) * 0.5
    snap = hp(r.standard_normal(nw.size), 2500) * env_exp(nw.size, 0.002, 0.0001)
    crack = nw * 0.7 + snap * 0.5
    place(out, crack * 0.55, 0.0)
    # distant boom
    boom = _report(r, 0.8, crack_tau=0.006, crack_hp=500, crack_gain=0.3, blast_tau=0.05,
                   blast_lp=900, thump_f0=90, thump_f1=40, thump_tau=0.12, drive=1.5)
    boom = lp(boom, 1200, 2)
    boom = fade(boom, 0.004, 0)
    ir = outdoor_ir(r, dur=2.6, slaps=((0.28, 0.35), (0.5, 0.25), (0.8, 0.15)), tau=0.7,
                    diffuse_gain=0.9, lp_start=2500, lp_end=500, predelay=0.02)
    ir[0] = 0.6
    ir2 = ir.copy()
    ir2[0] = 0
    place(out, boom * 0.6, 0.32)
    place(out, conv(hp(boom, 150, 2), ir2) * 1.0, 0.32)
    out = fade(out, 0, 0.5)
    return normalize_peak(limiter(normalize_peak(out, 0) * undb(4), -1.0, 0.05), -1.0)


# =========================================================================== mechanics
def _slide(r, dur, f0, f1, gain=1.0, q=4):
    """Friction / sliding noise with a swept resonance."""
    n = n_of(dur)
    fc = np.geomspace(f0, f1, n)
    x = svf_bp(r.standard_normal(n), fc, q)
    x *= np.sin(np.linspace(0, np.pi, n)) ** 1.5
    return x / (np.max(np.abs(x)) + 1e-9) * gain


def _brass_casing(r, bounces=3):
    """An ejected .45 brass case hitting the ground and bouncing / tinkling."""
    base = r.uniform(3300, 4200)
    ratios = [1.0, 1.73, 2.61, 3.52, 4.7]
    n = n_of(0.5)
    out = np.zeros(n)
    t = 0.0
    g = 1.0
    for b in range(bounces):
        ring = modal([base * q * r.uniform(0.99, 1.01) for q in ratios],
                     [r.uniform(0.04, 0.09) / (1 + 0.3 * i) for i in range(len(ratios))],
                     [r.uniform(0.4, 1) * 0.8 ** i for i in range(len(ratios))], 0.25, r)
        ex = hp(r.standard_normal(n_of(0.002)), 3000) * 0.8
        hit = ring
        hit[:ex.size] += ex
        place(out, hit * g, t)
        t += r.uniform(0.035, 0.08) * (0.7 ** b)
        g *= r.uniform(0.35, 0.55)
    return out


def schofield_cock():
    r = rng(31)
    out = np.zeros(n_of(0.45))
    # cylinder hand turning: two faint ratchet ticks while the hammer is drawn back
    for tt in (0.02, 0.06, 0.095):
        place(out, metal_click(r, 0.05, base=3800, decay=0.008) * 0.18, tt)
    # hammer pulled: friction swish
    place(out, _slide(r, 0.11, 1800, 3500, 0.06, q=3), 0.01)
    # 'click' (bolt drops into cylinder notch)
    place(out, metal_click(r, 0.15, base=2400, decay=0.03, body=0.3, body_f=320) * 0.7, 0.13)
    # 'clack' (sear engages full cock) - louder, lower
    place(out, metal_click(r, 0.2, base=1750, decay=0.045, body=0.6, body_f=260) * 1.0, 0.215)
    out = fade(out, 0, 0.05)
    return normalize_peak(out, -1.0)


def schofield_reload():
    r = rng(1873)
    out = np.zeros(n_of(1.62))
    # thumb pulls the barrel latch
    place(out, metal_click(r, 0.12, base=2100, decay=0.03, body=0.3) * 0.7, 0.0)
    # barrel swings down on the hinge
    place(out, _slide(r, 0.14, 900, 2300, 0.12, q=2.5), 0.03)
    # hits the stop (extractor star kicks) - heavy clack
    place(out, metal_click(r, 0.25, base=1500, decay=0.05, body=0.8, body_f=190) * 1.0, 0.17)
    # 6 casings eject and tinkle on the ground
    for i in range(6):
        place(out, _brass_casing(r, bounces=r.integers(2, 4)) * r.uniform(0.25, 0.4),
              0.28 + i * 0.03 + r.uniform(0, 0.05))
    # six rounds thumbed into the chambers (fast, in pairs)
    t = 0.66
    for i in range(6):
        place(out, _slide(r, 0.04, 2500, 1500, 0.05, q=3), t - 0.03)
        place(out, metal_click(r, 0.07, base=2900, decay=0.012, body=0.5, body_f=420) * 0.35, t)
        t += 0.07 if i % 2 == 0 else 0.085
    # cylinder spun: free-wheeling ratchet slowing down
    t = 1.13
    dt = 0.018
    for i in range(12):
        place(out, metal_click(r, 0.04, base=4200, decay=0.006) * (0.3 - i * 0.015), t)
        t += dt
        dt *= 1.09
    # snap shut + latch catch
    place(out, metal_click(r, 0.2, base=1650, decay=0.045, body=0.9, body_f=230) * 1.0, 1.44)
    place(out, metal_click(r, 0.12, base=2600, decay=0.02) * 0.55, 1.462)
    out = fade(out, 0, 0.04)
    return normalize_peak(out, -1.0)


def shotgun_reload():
    r = rng(1878)
    out = np.zeros(n_of(1.82))
    # top lever thrown
    place(out, metal_click(r, 0.12, base=1900, decay=0.025, body=0.3) * 0.6, 0.0)
    # breaks open - heavy hinge clunk + wooden stock knock
    place(out, _slide(r, 0.12, 700, 1600, 0.12, q=2), 0.03)
    place(out, metal_click(r, 0.3, base=1100, decay=0.06, body=1.2, body_f=150) * 1.0, 0.14)
    # two spent shells pulled / flung (hollow brass-head paper hulls)
    for tt in (0.3, 0.34):
        place(out, _slide(r, 0.06, 1200, 2400, 0.1, q=3), tt)
    for tt in (0.52, 0.6):
        hull = modal([1250 * r.uniform(0.95, 1.05), 2150, 3400, 5200],
                     [0.03, 0.02, 0.015, 0.01], [1, 0.6, 0.4, 0.3], 0.1, r)
        place(out, hull * 0.35, tt)
        place(out, hull * 0.12, tt + 0.07)
    # two fresh shells slid in, seating with a soft thock
    for tt in (0.82, 1.12):
        place(out, _slide(r, 0.1, 900, 1800, 0.1, q=2.5), tt)
        seat = modal([820, 1760, 2900], [0.025, 0.015, 0.01], [1, 0.5, 0.25], 0.08, r)
        place(out, seat * 0.35, tt + 0.1)
        place(out, metal_click(r, 0.05, base=3100, decay=0.01) * 0.12, tt + 0.1)
    # snap shut - big clack + lever snapping home
    place(out, metal_click(r, 0.3, base=1300, decay=0.06, body=1.2, body_f=170) * 1.0, 1.55)
    place(out, metal_click(r, 0.15, base=2300, decay=0.025) * 0.7, 1.575)
    out = fade(out, 0, 0.05)
    return normalize_peak(out, -1.0)


# =========================================================================== whiz / ricochet
def bullet_whiz(seed):
    r = rng(seed)
    dur = r.uniform(0.38, 0.55)
    n = n_of(dur)
    t = np.arange(n) / SR
    tp = dur * r.uniform(0.4, 0.5)  # time of closest pass
    d0 = r.uniform(0.02, 0.05)       # "closeness" (s)
    x = (t - tp)
    # doppler factor sweeps from + to - through the pass
    v = r.uniform(0.22, 0.3)
    dop = 1 + v * (-x / np.sqrt(x ** 2 + d0 ** 2))
    amp = 1 / (1 + (x / d0) ** 2) ** 0.8
    f0 = r.uniform(1600, 2300)
    # air-tear: bandpassed noise tracking doppler
    tear = svf_bp(r.standard_normal(n), f0 * 1.8 * dop, 2.5)
    # whistle: tonal component with slight flutter (tumbling)
    ph = 2 * np.pi * np.cumsum(f0 * dop * (1 + 0.01 * np.sin(2 * np.pi * 70 * t))) / SR
    whistle = np.sin(ph) + 0.3 * np.sin(2 * ph + 1)
    y = (tear / (np.max(np.abs(tear)) + 1e-9) * 0.9 + whistle * 0.35) * amp
    # sonic 'snap' as it passes
    snap = hp(r.standard_normal(n_of(0.004)), 3000) * env_exp(n_of(0.004), 0.0008, 0.0001)
    place(y, snap * 0.5, tp - 0.002)
    y = fade(y, 0.01, 0.05)
    return normalize_peak(y, -1.0)


def ricochet(seed):
    """Classic western 'pyeeeoww': metallic spank then a descending tumbling whine."""
    r = rng(seed)
    dur = r.uniform(0.95, 1.3)
    n = n_of(dur)
    t = np.arange(n) / SR
    out = np.zeros(n_of(dur + 0.8))
    # impact spank on rock
    spank = hp(r.standard_normal(n_of(0.05)), 1200) * env_exp(n_of(0.05), 0.006, 0.0002)
    spank += metal_click(r, 0.05, base=r.uniform(2500, 3200), decay=0.01) * 0.6
    place(out, spank * 0.9, 0)
    grit = hp(r.standard_normal(n_of(0.12)), 2500) * env_exp(n_of(0.12), 0.03, 0.001)
    grit *= (r.random(grit.size) < 0.08)
    place(out, grit * 0.8, 0.003)
    # whine
    fs_, fe = r.uniform(3200, 4200), r.uniform(900, 1300)
    rise = 1 - np.exp(-t / 0.012)
    f = fe + (fs_ - fe) * np.exp(-t / (dur * 0.42))
    f = f * (0.93 + 0.07 * rise)
    wob = 1 + 0.012 * np.sin(2 * np.pi * r.uniform(28, 45) * t)
    ph = 2 * np.pi * np.cumsum(f * wob) / SR
    tone = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
    am = 1 - 0.35 * (0.5 + 0.5 * np.sin(2 * np.pi * r.uniform(45, 70) * t))  # tumble
    env = (1 - np.exp(-t / 0.02)) * np.exp(-t / (dur * 0.45))
    airy = svf_bp(r.standard_normal(n), f * 1.02, 8)
    airy /= np.max(np.abs(airy)) + 1e-9
    whine = (tone * 0.8 + airy * 0.5) * am * env
    place(out, whine * 0.55, 0.012)
    ir = outdoor_ir(r, dur=0.9, slaps=((0.2, 0.15),), tau=0.25, diffuse_gain=0.3)
    ir[0] = 1
    out = conv(out, ir * 0.9)[:out.size]
    out = fade(out, 0, 0.3)
    return normalize_peak(out, -1.0)


# =========================================================================== impacts
def hit_flesh(seed):
    r = rng(seed)
    n = n_of(0.35)
    t = np.arange(n) / SR
    thud = lp(r.standard_normal(n), 700, 2) * env_exp(n, 0.035, 0.001)
    thud /= np.max(np.abs(thud))
    f = 70 + 80 * np.exp(-t / 0.02)
    low = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, 0.05, 0.002)
    wet = bp(r.standard_normal(n), 400, 1400) * env_exp(n, 0.05, 0.004)
    wet *= 0.6 + 0.4 * np.sin(2 * np.pi * r.uniform(40, 70) * t)
    wet /= np.max(np.abs(wet))
    slap = bp(r.standard_normal(n), 1500, 4000) * env_exp(n, 0.004, 0.0003)
    slap /= np.max(np.abs(slap))
    y = thud * 0.9 + low * 0.9 + wet * 0.25 + slap * 0.25
    y = softclip(y * 1.4)
    return normalize_peak(fade(y, 0, 0.08), -1.0)


def hit_wood(seed):
    r = rng(seed)
    n = n_of(0.45)
    base = r.uniform(190, 260)
    knock = modal([base, base * 2.6, base * 4.9, base * 7.3, base * 11.0],
                  [0.05, 0.03, 0.018, 0.012, 0.008], [1, 0.7, 0.5, 0.35, 0.2], 0.45, r)
    ex = lp(r.standard_normal(n), 3500) * env_exp(n, 0.003, 0.0002)
    y = knock + ex * 1.2
    # splinters: crackle of tiny sharp clicks decaying over ~100 ms
    cr = np.zeros(n)
    for _ in range(int(r.integers(14, 24))):
        tt = abs(r.normal(0.0, 0.035)) + 0.002
        c = hp(r.standard_normal(n_of(0.003)), 2500) * np.hanning(n_of(0.003))
        place(cr, c * r.uniform(0.3, 1.0) * np.exp(-tt / 0.05), tt)
    y = y / np.max(np.abs(y)) + cr * 0.7
    y = limiter(normalize_peak(y, 0) * undb(6), -1.0, 0.04)
    return normalize_peak(fade(y, 0, 0.1), -1.0)


SOUNDS = {
    'schofield_shot': schofield_shot,
    'schofield_shot2': schofield_shot2,
    'shotgun_shot': shotgun_shot,
    'rifle_shot_far': rifle_shot_far,
    'schofield_cock': schofield_cock,
    'schofield_reload': schofield_reload,
    'shotgun_reload': shotgun_reload,
    'bullet_whiz_1': lambda: bullet_whiz(101),
    'bullet_whiz_2': lambda: bullet_whiz(102),
    'bullet_whiz_3': lambda: bullet_whiz(103),
    'ricochet_1': lambda: ricochet(201),
    'ricochet_2': lambda: ricochet(202),
    'ricochet_3': lambda: ricochet(203),
    'hit_flesh_1': lambda: hit_flesh(301),
    'hit_flesh_2': lambda: hit_flesh(302),
    'hit_wood_1': lambda: hit_wood(401),
    'hit_wood_2': lambda: hit_wood(402),
}
