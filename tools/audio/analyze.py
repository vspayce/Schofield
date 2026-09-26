"""Preview renderer: waveform + log-frequency spectrogram PNG (and loop-seam view)."""
import numpy as np
from PIL import Image, ImageDraw
from dsp import SR, db, lufs

W, HW, HS, HSEAM = 1000, 160, 300, 140


def _colormap(v):
    """v in [0,1] -> RGB (inferno-ish)."""
    stops = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99],
                      [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]],
                     dtype=float)
    x = np.clip(v, 0, 1) * (len(stops) - 1)
    i = np.minimum(x.astype(int), len(stops) - 2)
    f = (x - i)[..., None]
    return (stops[i] * (1 - f) + stops[i + 1] * f).astype(np.uint8)


def spectrogram(x, height=HS, width=W, fmin=30, fmax=20000, nfft=2048, rng_db=90):
    n = x.size
    hop = max(1, (n - nfft) // width) if n > nfft else 1
    win = np.hanning(nfft)
    cols = []
    for c in range(width):
        s = c * hop
        seg = x[s:s + nfft]
        if seg.size < nfft:
            seg = np.pad(seg, (0, nfft - seg.size))
        cols.append(np.abs(np.fft.rfft(seg * win)))
    S = np.array(cols).T  # (freq, time)
    freqs = np.fft.rfftfreq(nfft, 1 / SR)
    target = np.geomspace(fmin, fmax, height)
    idx = np.clip(np.searchsorted(freqs, target), 0, freqs.size - 1)
    S = S[idx][::-1]
    Sdb = 20 * np.log10(S / (np.max(S) + 1e-12) + 1e-9)
    v = (Sdb + rng_db) / rng_db
    return _colormap(v)


def render(x, path, title='', loop=False):
    mono = x if x.ndim == 1 else x.mean(axis=1)
    n = mono.size
    H = HW + HS + HSEAM + 40
    img = Image.new('RGB', (W, H), (18, 18, 22))
    d = ImageDraw.Draw(img)
    peak = np.max(np.abs(x))
    L = lufs(x)
    dur = n / SR
    d.text((6, 4), f'{title}   {dur:.3f}s  peak {db(peak):.2f} dBFS  {L:.1f} LUFS  '
                   f'{"stereo" if x.ndim == 2 else "mono"}', fill=(230, 230, 230))
    y0 = 22
    # waveform (min/max per column), plus dB envelope line
    mid = y0 + HW // 2
    d.line([(0, mid), (W, mid)], fill=(60, 60, 70))
    for dbl in (-1, -6, -12):
        yy = int(HW / 2 * 10 ** (dbl / 20))
        d.line([(0, mid - yy), (W, mid - yy)], fill=(70, 40, 40) if dbl == -1 else (45, 45, 55))
    step = n / W
    for c in range(W):
        seg = mono[int(c * step):max(int((c + 1) * step), int(c * step) + 1)]
        lo, hi = seg.min(), seg.max()
        clip = max(abs(lo), abs(hi)) >= 0.999
        d.line([(c, mid - hi * HW / 2), (c, mid - lo * HW / 2)],
               fill=(255, 60, 60) if clip else (120, 200, 255))
    # tick marks every 0.1 s / 1 s
    tick = 0.1 if dur < 3 else (1.0 if dur < 30 else 5.0)
    k = 0
    while k * tick < dur:
        xx = int(k * tick / dur * W)
        d.line([(xx, y0 + HW - 6), (xx, y0 + HW)], fill=(200, 200, 200))
        k += 1
    y1 = y0 + HW + 4
    spec = spectrogram(mono)
    img.paste(Image.fromarray(spec), (0, y1))
    for f in (100, 1000, 10000):
        yy = y1 + int((1 - np.log(f / 30) / np.log(20000 / 30)) * HS)
        d.line([(0, yy), (12, yy)], fill=(255, 255, 255))
        d.text((14, yy - 6), f'{f}Hz', fill=(255, 255, 255))
    if loop:
        # seam view: last 50 ms | first 50 ms, joined in the centre
        ys = y1 + HS + 8
        m = int(0.05 * SR)
        seam = np.concatenate([mono[-m:], mono[:m]])
        smid = ys + HSEAM // 2
        sc = HSEAM / 2 / (np.max(np.abs(seam)) + 1e-9)
        pts = [(i * W / seam.size, smid - seam[i] * sc) for i in range(0, seam.size, 2)]
        d.line(pts, fill=(140, 255, 140))
        d.line([(W // 2, ys), (W // 2, ys + HSEAM)], fill=(255, 80, 80))
        jump = abs(mono[0] - mono[-1])
        typ = np.median(np.abs(np.diff(mono))) + 1e-12
        rms_end = np.sqrt(np.mean(mono[-m:] ** 2))
        rms_start = np.sqrt(np.mean(mono[:m] ** 2))
        d.text((6, ys), f'seam: |x0-xN|={jump:.4f} (median step {typ:.4f})  '
                        f'rms end {db(rms_end):.1f} dB / start {db(rms_start):.1f} dB',
               fill=(230, 230, 230))
    else:
        # attack zoom: first 150 ms waveform
        ys = y1 + HS + 8
        m = min(n, int(0.15 * SR))
        seg = mono[:m]
        smid = ys + HSEAM // 2
        pts = [(i * W / m, smid - seg[i] * HSEAM / 2) for i in range(0, m, 2)]
        d.line(pts, fill=(255, 210, 120))
        for ms in range(0, 151, 10):
            xx = int(ms / 150 * W)
            d.line([(xx, ys + HSEAM - 5), (xx, ys + HSEAM)], fill=(200, 200, 200))
        d.text((6, ys), 'first 150 ms (ticks = 10 ms)', fill=(230, 230, 230))
    img.save(path)
    return dict(dur=dur, peak_db=float(db(peak)), lufs=L)
