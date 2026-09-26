"""Morricone-style score: ride loop, menu loop, ghost-town loop, results cadence, stings.

All melodies are original compositions written as note lists below. Loops are
rendered *circularly*: every note/hit is placed on a buffer and anything ringing past
the loop end (including reverb and echo tails) is folded back onto the start, so the
seam is sample-accurate with no crossfade needed.
"""
import numpy as np
from dsp import (SR, rng, n_of, lp, hp, bp, place, fold_tail, pan, circ_conv, mtof, nm,
                 stereo_reverb_ir, normalize_lufs, limiter, fade, softclip, env_exp, reson)
import instruments as I
from world import whip_crack

TAIL = 7.0  # seconds of overhang rendered before folding
DEBUG = {}


# =========================================================================== helpers
PC = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6,
      'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}


def parse_chord(c):
    """'Dm', 'A7', 'Bb', 'F#m' -> (pc, quality)."""
    root = c[:2] if len(c) > 1 and c[1] in '#b' else c[:1]
    q = c[len(root):] or 'M'
    return PC[root], q


def in_range(pc, lo, hi):
    m = lo + ((pc - lo) % 12)
    return m if m <= hi else m - 12


def third_of(q):
    return 3 if q.startswith('m') else 4


def seventh_of(q):
    return 10 if q in ('m', 'm7', '7') else 9


def active_rms(x):
    m = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    thr = np.max(m) * 0.02
    a = x[m > thr]
    return np.sqrt(np.mean(a ** 2)) + 1e-12


def level(x, db_rms):
    return x * (10 ** (db_rms / 20) / active_rms(x))


def mixdown(stems, N, ir, circular=True):
    """stems: list of (mono, rms_db, pan, send). Returns stereo."""
    L = N if circular else max(s[0].size for s in stems) + ir.shape[0]
    dry = np.zeros((L, 2))
    wet_in = np.zeros((L, 2))
    DEBUG['stems'] = []
    for (x, g, p, send) in stems:
        if x is None or not np.any(x):
            continue
        DEBUG['stems'].append(level(x, g))
        y = pan(level(x, g), p)
        dry[:y.shape[0]] += y
        wet_in[:y.shape[0]] += y * send
    if circular:
        wl = circ_conv(wet_in[:, 0], ir[:, 0])
        wr = circ_conv(wet_in[:, 1], ir[:, 1])
    else:
        from scipy.signal import fftconvolve
        wl = fftconvolve(wet_in[:, 0], ir[:, 0])[:L]
        wr = fftconvolve(wet_in[:, 1], ir[:, 1])[:L]
    return dry + np.stack([wl, wr], axis=1)


def notes_from(grid, bar_lists, transpose=0, vel=0.9):
    """bar_lists: {bar: [(beat, dur_beats, 'C#5'), ...]} -> [(t, dur_s, midi, vel)]"""
    out = []
    for bar, lst in bar_lists.items():
        for item in lst:
            beat, d, name = item[:3]
            v = item[3] if len(item) > 3 else vel
            out.append((grid.t(bar, beat), d * grid.beat * 0.97, nm(name) + transpose, v))
    return out


def fold(x, N):
    return fold_tail(x, N)


# =========================================================================== RIDE
RIDE_CHORDS = (['Dm', 'Dm', 'C', 'C', 'Bb', 'Bb', 'A', 'A'] +          # A  : whistle
               ['Dm', 'F', 'C', 'Dm', 'Gm', 'Dm', 'A', 'A'] +          # B  : trumpet
               ['Dm', 'Dm', 'Bb', 'Bb', 'Gm', 'Gm', 'A', 'A'] +        # C  : ocarina/jaw harp
               ['Dm', 'Dm', 'C', 'C', 'Bb', 'Gm', 'A', 'A7'])          # A' : whistle + all

WHISTLE_A = {
    1: [(0, .5, 'D5'), (.5, 3.5, 'A5')],
    2: [(0, .5, 'G5'), (.5, .5, 'F5'), (1, .5, 'E5'), (1.5, 2.5, 'F5')],
    3: [(0, .5, 'E5'), (.5, 3.5, 'G5')],
    4: [(0, .5, 'F5'), (.5, .5, 'E5'), (1, .5, 'D5'), (1.5, 2.5, 'E5')],
    5: [(0, .5, 'D5'), (.5, .5, 'F5'), (1, 3, 'Bb5')],
    6: [(0, .5, 'A5'), (.5, .5, 'G5'), (1, .5, 'F5'), (1.5, 2.5, 'D5')],
    7: [(0, 1, 'E5'), (1, 1, 'C#5'), (2, 1, 'E5'), (3, 1, 'A5')],
    8: [(0, .5, 'G5'), (.5, .5, 'F5'), (1, 3, 'E5')],
}
WHISTLE_END = {
    31: [(0, 1, 'E5'), (1, .5, 'F5'), (1.5, .5, 'E5'), (2, .5, 'D5'), (2.5, 1.5, 'C#5')],
    32: [(0, 1, 'A4'), (1, 1, 'C#5'), (2, 1, 'E5'), (3, 1, 'G5')],
}
TRUMPET_B = {
    9: [(0, 3, 'F5'), (3, .5, 'E5'), (3.5, .5, 'F5')],
    10: [(0, 3, 'A5'), (3, .5, 'G5'), (3.5, .5, 'A5')],
    11: [(0, 2, 'C6'), (2, 1, 'Bb5'), (3, 1, 'G5')],
    12: [(0, 4, 'A5')],
    13: [(0, 1.5, 'Bb5'), (1.5, .5, 'A5'), (2, 1, 'G5'), (3, 1, 'D5')],
    14: [(0, 1.5, 'F5'), (1.5, .5, 'E5'), (2, 2, 'D5')],
    15: [(0, 1, 'E5'), (1, 2, 'A5'), (3, .5, 'G5'), (3.5, .5, 'F5')],
    16: [(0, 3.5, 'E5')],
}
OCARINA_C = {
    17: [(0, .5, 'A5'), (.5, .5, 'F5'), (1, 1, 'D5')],
    18: [(0, .5, 'A5'), (.5, .5, 'C6'), (1, 1, 'A5')],
    19: [(0, .5, 'F5'), (.5, .5, 'D5'), (1, 1, 'Bb4')],
    20: [(0, .5, 'F5'), (.5, .5, 'G5'), (1, 1, 'F5')],
    21: [(0, .5, 'G5'), (.5, .5, 'Bb5'), (1, 1, 'D6')],
    22: [(0, .5, 'D6'), (.5, .5, 'C6'), (1, 1, 'Bb5')],
    23: [(0, .5, 'A5'), (.5, .5, 'G5'), (1, 1, 'E5')],
    24: [(0, .5, 'C#6'), (.5, .5, 'A5'), (1, 1, 'E5')],
}
# twang riff: (beat, interval token, dur, vel); tokens: int semitones, 't'=3rd, 's'=7th
RIFF_1 = [(0, 0, .75, 1.0), (.75, 0, .25, .7), (1, 7, .5, .8), (1.5, 0, .5, .7),
          (2, 12, .75, .9), (2.75, 's', .25, .7), (3, 7, .5, .8), (3.5, 't', .5, .75)]
RIFF_2 = [(0, 0, 1.5, 1.0), (2, 0, .25, .6), (2.25, 0, .25, .6), (2.5, 7, .5, .8),
          (3, 5, .5, .7), (3.5, 't', .5, .8)]


def music_ride_loop():
    r = rng(1966)
    g = I.Grid(120, 32)
    N = g.N
    M = N + n_of(TAIL)
    chords = [parse_chord(c) for c in RIDE_CHORDS]

    perc = np.zeros(M)
    hits = np.zeros(M)      # anvil / whip / bell (own send)
    bass = np.zeros(M)
    twang = np.zeros(M)
    strum = np.zeros(M)
    jaw = np.zeros(M)
    for bar in range(1, 33):
        pc, q = chords[bar - 1]
        sec = (bar - 1) // 8  # 0 A, 1 B, 2 C, 3 A'
        # ---------------- percussion: boom drum + galloping snare + clip-clop
        for b in (0, 2):
            place(perc, I.kick(r) * 1.0, g.t(bar, b))
        if sec in (1, 3) and bar % 2 == 0:
            place(perc, I.kick(r) * 0.7, g.t(bar, 3.5))
        for b in range(4):
            acc = 1.0 if b in (1, 3) else 0.55
            place(perc, I.snare(r, acc * 0.8, 0.07), g.t(bar, b))
            place(perc, I.snare(r, 0.32, 0.05), g.t(bar, b + .5))
            place(perc, I.snare(r, 0.42, 0.05), g.t(bar, b + .75))
            if sec in (0, 2, 3):
                place(perc, I.clipclop(r, True) * 0.35, g.t(bar, b))
                place(perc, I.clipclop(r, False) * 0.3, g.t(bar, b + .5))
        # ---------------- anvil, whip, bell
        if sec in (1, 3):
            place(hits, I.anvil(r, 1180, 1.5) * 0.45, g.t(bar, 0))
        if bar in (8, 16, 24):
            place(hits, I.anvil(r, 1180, 1.5) * 0.4, g.t(bar, 2.5))
            place(hits, I.anvil(r, 1180, 1.5) * 0.55, g.t(bar, 3))
        if bar in (9, 17, 25, 29):
            place(hits, whip_crack()[n_of(0.25):] * 0.55, g.t(bar, 0) - 0.05)
        if bar in (1, 17):
            place(hits, I.bell(r, 146.8, 5.0) * 0.35, g.t(bar, 0))
        # ---------------- bass: boom-chick gallop on root/fifth
        root_b = in_range(pc, 33, 44)
        for (b, iv, d, v) in [(0, 0, 1.0, 1.0), (1.5, 7, .5, .8), (2, 0, 1.0, .9),
                              (3, 7, .5, .8), (3.5, 12, .5, .7)]:
            place(bass, I.pluck_note(r, root_b + iv, d * g.beat, 'bass', v), g.t(bar, b))
        # ---------------- twang riff (baritone electric), sparser in C
        root_t = in_range(pc, 40, 51)
        riff = RIFF_2 if (bar % 2 == 0 or sec == 2) else RIFF_1
        if sec == 2:
            riff = [x for x in RIFF_2 if x[0] < 2]  # leave room for the jaw-harp answer
        for (b, iv, d, v) in riff:
            if iv == 't':
                iv = third_of(q)
            elif iv == 's':
                iv = seventh_of(q)
            place(twang, I.pluck_note(r, root_t + iv, d * g.beat, 'twang', v), g.t(bar, b))
        # ---------------- nylon strum in gallop rhythm
        voic = I.chord_voicing(in_range(pc, 40, 51), q[:1] if q != 'M' else 'M', 40)
        if q == 'A7' or q == '7':
            voic = I.chord_voicing(in_range(pc, 40, 51), '7', 40)
        for b in range(4):
            for (off, down, v, d) in ((0, True, 0.9, .5), (.5, False, .45, .25),
                                      (.75, True, .55, .25)):
                I.strum(strum, r, g.t(bar, b + off), voic, d * g.beat, down, v, 0.009, False)
        # ---------------- jaw harp answers in C
        if sec == 2:
            f0 = float(mtof(in_range(pc, 45, 56)))
            for (b, h0, h1) in ((2, 4, 8), (2.5, 6, 4), (2.75, 8, 5), (3.5, 4, 10)):
                place(jaw, I.jaw_twang(r, f0, h0, h1), g.t(bar, b))

    lead_w = I.whistle(notes_from(g, WHISTLE_A) +
                       notes_from(g, {k + 24: v for k, v in WHISTLE_A.items() if k <= 6}) +
                       notes_from(g, WHISTLE_END), M, r)
    lead_t = I.trumpet(notes_from(g, TRUMPET_B, vel=0.95), M, r)
    lead_o = I.ocarina(notes_from(g, OCARINA_C, vel=0.9), M, r)
    # trumpet harmony (sixth below) under the whistle in A'
    harm = {25: [(0, 4, 'F4')], 26: [(0, 4, 'A4')], 27: [(0, 4, 'G4')], 28: [(0, 4, 'E4')],
            29: [(0, 4, 'F4')], 30: [(0, 4, 'D4')], 31: [(0, 4, 'E4')], 32: [(0, 3.8, 'C#5')]}
    lead_h = I.trumpet(notes_from(g, harm, vel=0.6), M, r, bright_base=0.2, mute=True)

    # choir 'ah' swells
    ch = []
    for bar in list(range(5, 9)) + list(range(9, 17)) + list(range(17, 25)) + list(range(25, 33)):
        pc, q = chords[bar - 1]
        th = third_of(q)
        top = [in_range(pc, 57, 68), in_range((pc + th) % 12, 60, 71),
               in_range((pc + 7) % 12, 62, 73)]
        low = [in_range(pc, 45, 56), in_range((pc + 7) % 12, 50, 61)]
        vel = 0.55 if bar < 17 else 0.85
        if bar % 2 == 1 or bar >= 25:
            dur = g.bar * (1 if bar >= 25 else 2) * 0.98
            ch.append((g.t(bar), dur, top + low, vel))
    choir = I.choir(ch, M, r, 'ah', voices=3, swell=0.45, release=0.7)

    tw = I.twang_fx(fold(twang, N), r, circular=True)
    stems = [
        (fold(perc, N), -19.5, 0.0, 0.12),
        (fold(hits, N), -24, 0.25, 0.3),
        (fold(bass, N), -24, 0.0, 0.04),
        (tw, -23, 0.3, 0.12),
        (fold(strum, N), -26.5, -0.45, 0.2),
        (fold(lead_w, N), -17.5, 0.1, 0.4),
        (fold(lead_t, N), -19, -0.1, 0.38),
        (fold(lead_h, N), -27, -0.3, 0.35),
        (fold(lead_o, N), -18.5, 0.2, 0.4),
        (fold(jaw, N), -22, -0.35, 0.3),
        (fold(choir, N), -24, 0.0, 0.55),
    ]
    ir = stereo_reverb_ir(r, 2.8, 0.6, 0.025)
    mix = mixdown(stems, N, ir)
    return normalize_lufs(mix, -14, -1.0)


# =========================================================================== MENU
MENU_CHORDS = ['Am', 'Am', 'Dm', 'Am', 'F', 'E', 'Am', 'Am', 'Dm', 'G', 'C', 'F', 'E', 'E']
MENU_TRUMPET = {
    1: [(2, 1, 'E5'), (3, 1, 'D5')],
    2: [(0, 3, 'C5'), (3, .5, 'B4'), (3.5, .5, 'C5')],
    3: [(0, 2, 'D5'), (2, 1, 'F5'), (3, 1, 'E5')],
    4: [(0, 3.5, 'A4')],
    5: [(0, 1.5, 'C5'), (1.5, .5, 'D5'), (2, 2, 'F5')],
    6: [(0, 3, 'E5'), (3, 1, 'G#4')],
    7: [(0, 3.5, 'A4')],
    9: [(0, 2, 'F5'), (2, 1, 'E5'), (3, 1, 'D5')],
    10: [(0, 3, 'D5'), (3, 1, 'B4')],
    11: [(0, 2, 'C5'), (2, 1, 'E5'), (3, 1, 'G5')],
    12: [(0, 3, 'A5'), (3, .5, 'G5'), (3.5, .5, 'F5')],
    13: [(0, 4, 'E5')],
    14: [(0, 2, 'B4'), (2, 1.5, 'G#4')],
}
MENU_WHISTLE = {
    8: [(0.5, 1, 'E6'), (1.5, .5, 'D6'), (2, 1.5, 'C6'), (3.5, .5, 'B5')],
}


def music_menu():
    r = rng(1964)
    g = I.Grid(70, 14)
    N = g.N
    M = N + n_of(TAIL)
    chords = [parse_chord(c) for c in MENU_CHORDS]
    gtr = np.zeros(M)
    twang = np.zeros(M)
    hits = np.zeros(M)
    pattern_full = [0, 1, 2, 3, 4, 3, 2, 1]
    for bar in range(1, 15):
        pc, q = chords[bar - 1]
        v = I.chord_voicing(in_range(pc, 40, 51), 'm' if q.startswith('m') else 'M', 40)
        sparse = bar in (1, 4, 7, 8, 13, 14)
        for i, idx in enumerate(pattern_full):
            if sparse and i in (3, 5, 6):
                continue
            vel = 0.9 if i == 0 else 0.55 + 0.1 * r.random()
            place(gtr, I.pluck_note(r, v[idx], 2.2, 'nylon', vel, ring=2.4), g.t(bar, i * .5)
                  + r.normal(0, 0.006))
        if bar in (1, 8):
            place(hits, I.bell(r, 110.0, 6.0, 1.2) * 0.5, g.t(bar, 0))
        if bar in (1, 5, 9, 13):
            place(twang, I.pluck_note(r, in_range(pc, 28, 39) + 12, 3.0, 'twang', 1.0, ring=3.5),
                  g.t(bar, 0))
        if bar == 14:
            place(hits, I.timpani(r, 82.4, 0.5), g.t(bar, 2))
    lead = I.trumpet(notes_from(g, MENU_TRUMPET, vel=0.85), M, r, bright_base=0.22)
    wh = I.whistle(notes_from(g, MENU_WHISTLE, vel=0.7), M, r)
    ch = []
    for bar in range(1, 15, 2):
        pc, q = chords[bar - 1]
        th = third_of(q)
        ch.append((g.t(bar), g.bar * 2 * 0.98,
                   [in_range(pc, 45, 56), in_range((pc + 7) % 12, 50, 61),
                    in_range((pc + th) % 12, 55, 66)], 0.6))
    choir = I.choir(ch, M, r, 'oo', voices=3, swell=0.6, release=1.2)
    tw = I.twang_fx(fold(twang, N), r, circular=True, drive=1.8, spring_wet=0.5)
    stems = [
        (fold(gtr, N), -21, -0.3, 0.35),
        (tw, -25, 0.35, 0.3),
        (fold(hits, N), -25, 0.2, 0.5),
        (fold(lead, N), -17.5, 0.05, 0.6),
        (fold(wh, N), -17, 0.25, 0.7),
        (fold(choir, N), -23, 0.0, 0.6),
    ]
    ir = stereo_reverb_ir(r, 5.5, 1.3, 0.04)
    mix = mixdown(stems, N, ir)
    return normalize_lufs(mix, -16, -1.0)


# =========================================================================== TOWN
def music_town_loop():
    """Tense, sparse ghost-town bed: tolling bell, harmonica drone, low twang, pulse."""
    r = rng(1880)
    g = I.Grid(64, 12)
    N = g.N
    M = N + n_of(TAIL)
    bells = np.zeros(M)
    twang = np.zeros(M)
    pulse = np.zeros(M)
    jaw = np.zeros(M)
    for bar in range(1, 13):
        if bar % 2 == 1:
            place(bells, I.bell(r, 164.8, 7.0, 1.3), g.t(bar, 0))
        place(pulse, I.kick(r, 40, 0.3) * 0.9, g.t(bar, 0))
        place(pulse, I.kick(r, 42, 0.25) * 0.55, g.t(bar, 0.45))
        if bar in (6, 10):
            f0 = float(mtof(nm('E3')))
            for (b, h0, h1) in ((2, 4, 8), (2.75, 8, 4)):
                place(jaw, I.jaw_twang(r, f0, h0, h1, 0.6, 0.2), g.t(bar, b))
    tw_notes = [(1, 0, 'E2', 3.5), (2, 2.5, 'G2', 1), (2, 3.5, 'F#2', .5), (3, 0, 'F2', 3),
                (4, 2, 'E2', 1), (4, 3, 'D#2', 1), (5, 0, 'E2', 3.5), (7, 0, 'F2', 3.5),
                (8, 2, 'G2', .75), (8, 2.75, 'F2', .75), (8, 3.5, 'E2', .5), (9, 0, 'E2', 3.5),
                (10, 2.5, 'B2', 1), (11, 0, 'C3', 2), (11, 2, 'B2', 2), (12, 0, 'E2', 2),
                (12, 2.5, 'D#2', 1.5)]
    for (bar, b, n_, d) in tw_notes:
        place(twang, I.pluck_note(r, nm(n_), d * g.beat, 'twang', 0.9, ring=3.5), g.t(bar, b))
    harm_notes = {1: [(0, 7.8, 'E4', 0.6)], 3: [(0, 7.8, 'F4', 0.7)], 5: [(0, 7.8, 'E4', 0.7)],
                  7: [(0, 7.8, 'F4', 0.8)], 9: [(0, 7.8, 'E4', 0.7)], 11: [(0, 7.8, 'D#4', 0.8)]}
    harm = I.harmonica(notes_from(g, harm_notes), M, r, chord=(0, 7))
    # slow swell envelope on the harmonica (breathing in and out)
    t = np.arange(M) / SR
    harm *= 0.55 + 0.45 * np.sin(np.pi * ((t / (g.bar * 2)) % 1.0)) ** 2
    wh = I.whistle(notes_from(g, {9: [(0, 3, 'B5')], 10: [(0, 2, 'C6'), (2, 2, 'B5')]}, vel=0.6),
                   M, r)
    ch = [(g.t(5), g.bar * 4 * 0.98, [nm('E3'), nm('B3'), nm('F4')], 0.5),
          (g.t(9), g.bar * 4 * 0.98, [nm('E3'), nm('B3'), nm('G4')], 0.5)]
    choir = I.choir(ch, M, r, 'oo', voices=3, swell=0.7, release=1.5)
    tw = I.twang_fx(fold(twang, N), r, circular=True, drive=2.0, slap=0.14, spring_wet=0.5)
    stems = [
        (fold(bells, N), -22.5, 0.3, 0.55),
        (tw, -24, -0.2, 0.3),
        (fold(pulse, N), -22, 0.0, 0.15),
        (fold(harm, N), -22.5, 0.15, 0.45),
        (fold(wh, N), -24, -0.3, 0.6),
        (fold(jaw, N), -25, -0.4, 0.4),
        (fold(choir, N), -25, 0.0, 0.6),
    ]
    ir = stereo_reverb_ir(r, 4.5, 1.1, 0.04)
    mix = mixdown(stems, N, ir)
    return normalize_lufs(mix, -17, -1.0)


# =========================================================================== one-shots
D_MAJOR = [2, 4, 6, 7, 9, 11, 1]


def third_below(midi, scale):
    """Diatonic third below in `scale` (list of pitch classes)."""
    m = midi - 1
    steps = 0
    while steps < 2:
        if m % 12 in scale:
            steps += 1
            if steps == 2:
                return m
        m -= 1
    return m


def _finish(mix, dur, target=-14):
    n = n_of(dur)
    mix = mix[:n]
    mix = fade(mix, 0.0, min(1.5, dur * 0.3))
    return normalize_lufs(mix, target, -1.0)


def music_results():
    """~12 s triumphant trumpet + choir cadence in D major."""
    r = rng(1873)
    g = I.Grid(90, 5)
    M = n_of(15.0)
    t1 = {1: [(0, .75, 'A4'), (.75, .25, 'D5'), (1, 1, 'F#5'), (2, 2, 'A5')],
          2: [(0, 1.5, 'B5'), (1.5, .5, 'A5'), (2, 1, 'G5'), (3, 1, 'B5')],
          3: [(0, 1.5, 'C#6'), (1.5, .5, 'B5'), (2, 1, 'A5'), (3, 1, 'E5')],
          4: [(0, 5.5, 'D6')]}
    t2 = {b: [(x[0], x[1], None) for x in v] for b, v in t1.items()}
    n1 = notes_from(g, t1, vel=0.95)
    n2 = [(a, d, third_below(m, D_MAJOR), 0.75) for (a, d, m, v) in n1]
    n2[-1] = (n2[-1][0], n2[-1][1], nm('F#5'), 0.75)
    tr1 = I.trumpet(n1, M, r, bright_base=0.32)
    tr2 = I.trumpet(n2, M, r, bright_base=0.25)
    chords = ['D', 'G', 'A', 'D', 'D']
    gtr = np.zeros(M)
    perc = np.zeros(M)
    ch = []
    for bar in range(1, 5):
        pc, q = parse_chord(chords[bar - 1])
        v = I.chord_voicing(in_range(pc, 40, 51), 'M', 40)
        beats = (0, 1, 2, 3) if bar < 4 else (0,)
        for b in beats:
            I.strum(gtr, r, g.t(bar, b), v, g.beat * (1 if bar < 4 else 4), True,
                    0.9 if b == 0 else 0.6, 0.012, False)
        place(perc, I.timpani(r, 73.4 if pc == 2 else float(mtof(in_range(pc, 38, 49))), 1.0),
              g.t(bar, 0))
        ch.append((g.t(bar), g.bar * (1 if bar < 4 else 2.2),
                   [in_range(pc, 57, 68), in_range((pc + 4) % 12, 60, 71),
                    in_range((pc + 7) % 12, 62, 73), in_range(pc, 45, 56),
                    in_range((pc + 7) % 12, 50, 61)], 0.8 if bar < 4 else 1.0))
    # timpani roll into the final chord
    for k in range(10):
        place(perc, I.timpani(r, 110.0, 0.25 + 0.05 * k, 1.0), g.t(3, 3) + k * g.beat / 10)
    place(perc, I.anvil(r, 1180, 3.0) * 0.5, g.t(4, 0))
    place(perc, I.bell(r, 293.7, 5.0) * 0.4, g.t(4, 0))
    place(perc, whip_crack()[n_of(0.25):] * 0.5, g.t(4, 0) - 0.05)
    choir = I.choir(ch, M, r, 'ah', voices=3, swell=0.35, release=1.0)
    stems = [(tr1, -17, 0.1, 0.35), (tr2, -21, -0.15, 0.35), (gtr, -22, -0.35, 0.2),
             (perc, -20, 0.1, 0.25), (choir, -21, 0.0, 0.5)]
    ir = stereo_reverb_ir(r, 3.2, 0.8, 0.03)
    mix = mixdown(stems, M, ir, circular=False)
    return _finish(mix, 12.5, -14)


def sting_victory():
    r = rng(1881)
    g = I.Grid(140, 3)
    M = n_of(5.0)
    n1 = [(0.0, 0.12, nm('A4'), 0.9), (0.14, 0.12, nm('D5'), 0.9), (0.28, 0.12, nm('F#5'), 0.9),
          (0.44, 2.0, nm('A5'), 1.0)]
    n2 = [(a, d, third_below(m, D_MAJOR), 0.7) for (a, d, m, v) in n1]
    n2[-1] = (0.44, 2.0, nm('F#5'), 0.7)
    tr1 = I.trumpet(n1, M, r, bright_base=0.35)
    tr2 = I.trumpet(n2, M, r, bright_base=0.25)
    gtr = np.zeros(M)
    v = I.chord_voicing(nm('D3'), 'M', 40)
    for k, tt in enumerate((0.0, 0.07, 0.14, 0.21, 0.28, 0.44)):
        I.strum(gtr, r, tt, v, 0.1 if k < 5 else 2.5, k % 2 == 0, 0.8, 0.006, False)
    perc = np.zeros(M)
    place(perc, I.timpani(r, 73.4, 1.0), 0.44)
    place(perc, I.anvil(r, 1180, 2.5) * 0.4, 0.44)
    place(perc, I.bell(r, 293.7, 3.5) * 0.25, 0.44)
    choir = I.choir([(0.3, 2.0, [nm('D4'), nm('F#4'), nm('A4'), nm('D3'), nm('A3')], 1.0)], M, r,
                    'ah', swell=0.3, release=0.8)
    stems = [(tr1, -16, 0.1, 0.3), (tr2, -20, -0.15, 0.3), (gtr, -20, -0.3, 0.2),
             (perc, -19, 0.1, 0.25), (choir, -23, 0, 0.5)]
    ir = stereo_reverb_ir(r, 2.8, 0.7, 0.03)
    mix = mixdown(stems, M, ir, circular=False)
    return _finish(mix, 3.8, -13)


def sting_death():
    r = rng(1882)
    M = n_of(7.0)
    ch = [(0.05, 3.0, [nm('D2'), nm('A2'), nm('D3'), nm('F3'), nm('Eb4')], 1.0)]
    choir = I.choir(ch, M, r, 'oo', voices=4, swell=1.2, release=1.4)
    low = np.zeros(M)
    place(low, I.timpani(r, 36.7, 1.0, 4.0) * 0.8, 0.0)
    place(low, I.kick(r, 34, 0.9), 0.0)
    place(low, I.pluck_note(r, nm('D2'), 3.5, 'twang', 1.0, ring=4.0), 0.02)
    place(low, I.pluck_note(r, nm('Eb2'), 2.5, 'twang', 0.7, ring=4.0), 1.2)
    low_tw = I.twang_fx(low, r, circular=False, drive=1.8, spring_wet=0.4)
    tam = I.tamtam(r, 5.5, 0.9)
    bl = I.bell(r, 98.0, 6.0, 1.3)
    stems = [(choir, -20, 0.0, 0.5), (low_tw, -19, 0.0, 0.2), (tam, -26, 0.2, 0.4),
             (bl, -26, -0.25, 0.45)]
    ir = stereo_reverb_ir(r, 4.0, 1.0, 0.03)
    mix = mixdown(stems, M, ir, circular=False)
    return _finish(mix, 5.2, -15)


SOUNDS = {
    'music_ride_loop': music_ride_loop,
    'music_menu': music_menu,
    'music_town_loop': music_town_loop,
    'music_results': music_results,
    'sting_victory': sting_victory,
    'sting_death': sting_death,
}
