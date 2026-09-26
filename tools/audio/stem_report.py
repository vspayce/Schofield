"""Debug: render a music piece, print per-stem loudness per section, and save
zoomed spectrogram strips (tools/audio/previews/<name>_zoom.png)."""
import sys
import numpy as np
from PIL import Image, ImageDraw
import music
import analyze
from dsp import SR, lufs, n_of

name = sys.argv[1]
secs = [float(v) for v in sys.argv[2].split(',')] if len(sys.argv) > 2 else [0, 16, 32, 48]
win = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
x = getattr(music, name)()
stems = music.DEBUG['stems']
print('stem  ' + ' '.join(f'{s:>7.0f}s' for s in secs))
for i, st in enumerate(stems):
    row = []
    for s in secs:
        seg = st[n_of(s):n_of(s + win)]
        row.append(lufs(seg) if np.any(seg) else -99)
    print(f'{i:4d}  ' + ' '.join(f'{v:8.1f}' for v in row))
mono = x.mean(axis=1) if x.ndim == 2 else x
strips = []
for s in secs:
    seg = mono[n_of(s):n_of(s + win)]
    strips.append(analyze.spectrogram(seg, height=220, width=1000, fmin=60, fmax=12000, nfft=2048, rng_db=60))
img = Image.fromarray(np.concatenate(strips, axis=0))
d = ImageDraw.Draw(img)
for i, s in enumerate(secs):
    d.text((4, i * 220 + 2), f'{s:.1f}s .. {s + win:.1f}s', fill=(255, 255, 255))
img.save(f'previews/{name}_zoom.png')
