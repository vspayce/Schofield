#!/usr/bin/env python3
"""Build every SCHOFIELD audio asset.

    python3 tools/audio/build.py            # everything
    python3 tools/audio/build.py shotgun_shot music_menu   # a subset

Writes public/assets/audio/<name>.mp3 (44.1 kHz) and a preview PNG per file in
tools/audio/previews/. Everything is synthesised from seeded RNGs, so builds are
reproducible.
"""
import os
import subprocess
import sys
import tempfile
import time

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import analyze  # noqa: E402
from dsp import SR  # noqa: E402
import guns, world, fx, music  # noqa: E402,E401

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(ROOT, 'public', 'assets', 'audio')
PREV = os.path.join(HERE, 'previews')
FFMPEG = '/opt/homebrew/bin/ffmpeg' if os.path.exists('/opt/homebrew/bin/ffmpeg') else 'ffmpeg'

REGISTRY = {}
for mod in (guns, world, fx, music):
    REGISTRY.update(mod.SOUNDS)

LOOPS = {'horse_gallop_loop', 'coach_rumble_loop', 'wind_loop', 'heartbeat_loop',
         'music_ride_loop', 'music_menu', 'music_town_loop'}


def bitrate(name, x):
    if name.startswith('music'):
        return '128k'
    if x.ndim == 2:
        return '112k'
    return '96k'


def encode(name, x):
    os.makedirs(OUT, exist_ok=True)
    x = np.clip(x, -1, 1).astype(np.float32)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, name + '.wav')
        wavfile.write(wav, SR, x)
        mp3 = os.path.join(OUT, name + '.mp3')
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', wav, '-ar', str(SR),
                        '-c:a', 'libmp3lame', '-b:a', bitrate(name, x), mp3], check=True)
    return mp3


def main(names):
    os.makedirs(PREV, exist_ok=True)
    rows = []
    for name in names:
        t0 = time.time()
        x = REGISTRY[name]()
        mp3 = encode(name, x)
        st = analyze.render(x, os.path.join(PREV, name + '.png'), name, loop=name in LOOPS)
        size = os.path.getsize(mp3)
        rows.append((name, st['dur'], x.shape[0], size, st['peak_db'], st['lufs'],
                     'stereo' if x.ndim == 2 else 'mono'))
        print(f'{name:22s} {st["dur"]:7.3f}s {x.shape[0]:8d} smp {size / 1024:7.1f} KB '
              f'peak {st["peak_db"]:6.2f} dBFS {st["lufs"]:6.1f} LUFS '
              f'{rows[-1][6]:6s} ({time.time() - t0:.1f}s)', flush=True)
    return rows


if __name__ == '__main__':
    args = sys.argv[1:] or list(REGISTRY)
    bad = [a for a in args if a not in REGISTRY]
    if bad:
        sys.exit(f'unknown: {bad}\nknown: {sorted(REGISTRY)}')
    rows = main(args)
    if len(args) == len(REGISTRY):
        tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)
                  if f.endswith('.mp3'))
        print(f'TOTAL {tot / 1024 / 1024:.2f} MB in {len(rows)} files')
