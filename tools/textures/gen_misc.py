"""SCHOFIELD misc environment textures:
  grass_blade.png          256x256 RGBA  clump of blades for camera-facing grass cards
  cloud_noise.png          512x512 L     tiling fbm for sky clouds
  mountain_silhouette.png  2048x512 RGBA white ridges with alpha (3 layers), tiles horizontally
  lens_dirt.png            1024x1024 RGB black background, use additively

usage: python3 tools/textures/gen_misc.py [name ...]
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from texlib import *


# ---------------------------------------------------------------------------- grass card
def grass_blade():
    """Dense dry-grass clump (~30-40 % alpha coverage) with oat-like seed heads.
    RGB of every transparent texel is dilated from the nearest opaque texel so mips
    never pull in dark fringes."""
    from scipy import ndimage
    rng = np.random.default_rng(5)
    S = 1024  # 4x supersample of 256
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base_x = S / 2
    blades = []
    for i in range(46):
        rx = base_x + rng.normal(0, S * 0.11)
        rx = float(np.clip(rx, S * 0.12, S * 0.88))
        lean = (rx - base_x) / (S * 0.11) * 0.16 + rng.normal(0, 0.2)
        L = S * rng.uniform(0.45, 0.97)
        curve = rng.normal(0, 0.35) + np.sign(lean) * 0.2
        w0 = S * rng.uniform(0.014, 0.026)
        blades.append((L, rx, lean, curve, w0, rng.random()))
    blades.sort(key=lambda b: -b[0])  # tall ones behind
    tips = []
    for bi, (L, rx, lean, curve, w0, tone) in enumerate(blades):
        segs = 24
        left, right = [], []
        x, y = rx, S - 2
        a = -np.pi / 2 + lean
        for k in range(segs + 1):
            f = k / segs
            w = w0 * (1 - f) ** 0.85 + 1.5
            nx = -np.sin(a)
            left.append((x + nx * w, y))
            right.append((x - nx * w, y))
            a += curve * (f * 2.2) / segs
            x += np.cos(a) * L / segs
            y += np.sin(a) * L / segs
        x = min(max(x, 8), S - 8)
        y = max(y, 40)
        tips.append((x, y, a, L))
        c_root = np.array([0.34, 0.27, 0.14])
        c_mid = np.array([0.70, 0.57, 0.32]) * (0.82 + 0.3 * tone)
        c_tip = np.array([0.92, 0.83, 0.60]) * (0.88 + 0.12 * tone)
        for k in range(segs):
            f = k / segs
            c = c_root + (c_mid - c_root) * smoothstep(0, 0.45, f) if f < 0.45 else c_mid + (c_tip - c_mid) * smoothstep(0.45, 1.0, f)
            q = [left[k], left[k + 1], right[k + 1], right[k]]
            d.polygon(q, fill=tuple(int(v * 255) for v in np.clip(c, 0, 1)) + (255,))
            d.line([left[k], left[k + 1]], fill=tuple(int(v * 255) for v in np.clip(c * 1.18, 0, 1)) + (255,), width=3)
    # seed heads on ~8 of the taller stems: thin stalk extension + drooping spikelets
    for (x, y, a, L) in tips[:14:2] + tips[1:4]:
        for s_ in range(7):
            t = s_ / 7
            px = x - np.cos(a) * t * S * 0.11
            py = y - np.sin(a) * t * S * 0.11
            side = 1 if s_ % 2 else -1
            ex = px + side * S * 0.024
            ey = py + S * 0.02
            d.line([(px, py), (ex, ey - 8)], fill=(190, 160, 100, 255), width=4)
            d.polygon([(ex, ey - 14), (ex + 8, ey + 4), (ex, ey + 20), (ex - 8, ey + 4)], fill=(224, 200, 142, 255))
    small = img.convert('RGBa').resize((256, 256), Image.LANCZOS).convert('RGBA')
    a = np.asarray(small).astype(np.float64)
    rgb = a[..., :3]
    al = a[..., 3]
    opaque = al > 128
    idx = ndimage.distance_transform_edt(~opaque, return_distances=False, return_indices=True)
    near = rgb[idx[0], idx[1]]
    rgb = np.where((al > 200)[..., None], rgb, near)
    out = np.concatenate([np.clip(rgb, 0, 255), al[..., None]], -1).astype(np.uint8)
    Image.fromarray(out).save(os.path.join(TEX_OUT, 'grass_blade.png'), optimize=True)
    print('grass coverage (alpha>127): %.1f%%' % (100 * (al > 127).mean()))
    bg = Image.new('RGBA', (256, 256), (140, 170, 200, 255))
    bg.alpha_composite(Image.fromarray(out))
    bg.resize((512, 512), Image.NEAREST).save(os.path.join(PREVIEW, 'grass_blade_prev.png'))
    print('wrote grass_blade')


# ---------------------------------------------------------------------------- clouds
def cloud_noise():
    rng = np.random.default_rng(6)
    n = 512
    wx = (fbm(n, rng, base=4, octaves=3) - 0.5) * 28
    wy = (fbm(n, rng, base=4, octaves=3) - 0.5) * 28
    c = fbm(n, rng, base=5, octaves=7, gain=0.5)
    c = warp(c, wx, wy)
    billow = warp(ridged(fbm(n, rng, base=8, octaves=5)), wx * 0.5, wy * 0.5)
    c = 0.88 * c + 0.12 * billow
    c = eq(c)
    # coverage curve: ~45% clear sky, soft puffy edges
    c = smoothstep(0.35, 1.0, c)
    Image.fromarray(to8(c)).save(os.path.join(TEX_OUT, 'cloud_noise.png'), optimize=True)
    tile_preview(c, 'cloud_noise_2x2.jpg')
    print('wrote cloud_noise')


# ---------------------------------------------------------------------------- mountains
def periodic_1d(n, rng, beta, kmin=1, kmax=None):
    F = np.fft.rfft(rng.standard_normal(n))
    k = np.arange(len(F)).astype(float)
    k[0] = 1
    f = k ** (-beta / 2)
    f[:kmin] = 0
    if kmax:
        f *= np.exp(-(k / kmax) ** 2)
    x = np.fft.irfft(F * f, n)
    return (x - x.min()) / (x.max() - x.min())


def mountain_silhouette():
    rng = np.random.default_rng(8)
    W, H = 2048, 512
    alpha = np.zeros((H, W))
    shade = np.ones((H, W))
    yy = np.arange(H)[:, None].astype(float)
    xs = np.arange(W)
    layers = [  # (top of range px, amplitude px, roughness beta, alpha, kmin)
        (60, 190, 2.5, 0.45, 2),
        (150, 170, 2.4, 0.72, 3),
        (260, 140, 2.3, 1.0, 3),
    ]
    for top, amp, beta, a, kmin in layers:
        base = periodic_1d(W, rng, beta, kmin=kmin, kmax=160)
        # sharpen peaks (ridged look) and add fine crag detail
        r = periodic_1d(W, rng, 2.0, kmin=16, kmax=140)
        prof = base ** 1.3
        prof = 0.93 * prof + 0.07 * (1 - np.abs(r * 2 - 1))
        ridge_y = top + amp * (1 - prof)
        m = yy >= ridge_y[None, :]
        # soft 1px AA edge
        edge = np.clip(yy - ridge_y[None, :] + 0.5, 0, 1)
        # this layer covers what's behind it
        alpha = alpha * (1 - edge) + a * edge
        # gully shading: vertical streaks darken the body a little below the ridge (tint detail)
        g = periodic_1d(W, rng, 2.0, kmin=8, kmax=30)
        depth = np.clip((yy - ridge_y[None, :]) / 120, 0, 1)
        gully = 0.92 + 0.08 * np.clip(g[None, :] * 1.6 - 0.3, 0, 1)
        sh = gully * (1 - 0.1 * depth) + 0.1 * depth
        # sunlit slope: slope sign of ridge -> brighter faces towards +x
        slope = np.gradient(np.convolve(np.tile(ridge_y, 3), np.ones(25) / 25, 'same')[W:2 * W])
        lit = 1 + 0.08 * np.tanh(-slope / 2)[None, :] * (1 - depth)
        shade = np.where(edge > 0.5, np.clip(sh * lit, 0.75, 1), shade)
    rgb = np.repeat((shade[..., None]), 3, -1)
    out = np.concatenate([to8(rgb), to8(alpha)[..., None]], -1)
    Image.fromarray(out).save(os.path.join(TEX_OUT, 'mountain_silhouette.png'), optimize=True)
    # preview: tinted over sky, tiled 2x horizontally
    sky = np.linspace(0, 1, H)[:, None, None] * np.array([0.95, 0.72, 0.5]) + (1 - np.linspace(0, 1, H))[:, None, None] * np.array([0.55, 0.65, 0.8])
    sky = np.repeat(sky, W, 1)
    tint = np.array([0.42, 0.36, 0.40])
    col = sky * (1 - alpha[..., None]) + rgb * tint * alpha[..., None]
    col = np.concatenate([col, col], 1)
    Image.fromarray(to8(col)).resize((2048, 256), Image.LANCZOS).save(os.path.join(PREVIEW, 'mountain_prev.jpg'))
    print('wrote mountain_silhouette')


# ---------------------------------------------------------------------------- lens dirt
def lens_dirt():
    rng = np.random.default_rng(9)
    n = 1024
    S = n
    acc = np.zeros((S, S))
    img = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(img)
    # soft bokeh discs of dust
    for _ in range(55):
        x, y = rng.random() * S, rng.random() * S
        r = rng.uniform(4, 38) * (1 if rng.random() < 0.85 else 2.2)
        v = int(rng.uniform(15, 60))
        d.ellipse([x - r, y - r, x + r, y + r], fill=v)
    discs = np.asarray(img.filter(ImageFilter.GaussianBlur(2.5))).astype(float) / 255
    # ring-edged bokeh for a few bigger ones
    img2 = Image.new('L', (S, S), 0)
    d2 = ImageDraw.Draw(img2)
    for _ in range(8):
        x, y = rng.random() * S, rng.random() * S
        r = rng.uniform(20, 60)
        d2.ellipse([x - r, y - r, x + r, y + r], outline=int(rng.uniform(30, 70)), width=3)
        d2.ellipse([x - r + 3, y - r + 3, x + r - 3, y + r - 3], fill=int(rng.uniform(10, 25)))
    rings = np.asarray(img2.filter(ImageFilter.GaussianBlur(3))).astype(float) / 255
    # finger smudges / streaks
    sm = fbm(n, rng, base=3, octaves=5)
    streak = fbm(n, rng, base=6, octaves=4, aniso=(0.15, 1))
    smudge = smoothstep(0.55, 0.85, sm) * 0.18 + smoothstep(0.6, 0.9, streak) * 0.1 * smoothstep(0.3, 0.7, sm)
    # tiny sharp specks
    sp = (rng.random((n, n)) > 0.99985).astype(float)
    sp = blur(sp, 0.8) * 6
    tot = discs * 0.7 + rings * 0.8 + smudge + np.clip(sp, 0, 0.6)
    # stronger towards edges (vignette of dirt), weak in centre so aim point stays clean
    yy, xx = np.mgrid[0:n, 0:n] / n - 0.5
    rad = np.sqrt(xx ** 2 + yy ** 2)
    tot *= 0.35 + 0.9 * smoothstep(0.1, 0.6, rad)
    tot = np.clip(tot, 0, 1) * 0.75
    col = tot[..., None] * np.array([1.0, 0.93, 0.82])
    Image.fromarray(to8(col)).save(os.path.join(TEX_OUT, 'lens_dirt.png'), optimize=True)
    Image.fromarray(to8(np.clip(col * 2.2, 0, 1))).resize((512, 512)).save(os.path.join(PREVIEW, 'lens_dirt_prev_x2.jpg'))
    print('wrote lens_dirt')


ALL = {f.__name__: f for f in (grass_blade, cloud_noise, mountain_silhouette, lens_dirt)}
if __name__ == '__main__':
    for nm in sys.argv[1:] or list(ALL):
        ALL[nm]()
