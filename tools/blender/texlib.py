"""Procedural texture helpers (system Python 3 + numpy/scipy/PIL).

All noise here is *periodic* (FFT-filtered white noise / wrapped Worley), so any
region generated with it tiles seamlessly — the Blender builders rely on that
when they restart UVs at tile boundaries inside an atlas rectangle.
Colours are handled as float sRGB in [0,1] (painterly authoring, not PBR-linear).
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def rng(seed):
    return np.random.default_rng(seed)


def norm01(a):
    lo, hi = np.percentile(a, 0.5), np.percentile(a, 99.5)
    return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)


def fbm(h, w, seed, beta=2.0, aniso=(1.0, 1.0), lowcut=1.0, highcut=None):
    """Periodic 1/f^beta noise, normalised to [0,1].
    aniso=(ax, ay): >1 on an axis compresses features along it (ay>1 -> streaks along x)."""
    r = rng(seed)
    white = r.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    rad = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    rad[0, 0] = 1.0
    filt = 1.0 / rad ** (beta / 2.0)
    filt[rad < lowcut] = 0
    if highcut is not None:
        filt *= np.exp(-(rad / highcut) ** 2)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * filt))
    return norm01(out)


def worley(h, w, n, seed, aniso=(1.0, 1.0)):
    """Periodic Worley noise. Returns (F1, F2, cell_index) with distances in pixels
    (in the anisotropically-scaled metric)."""
    r = rng(seed)
    pts = r.random((n, 2)) * [w, h]
    tiles = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            tiles.append(pts + [dx * w, dy * h])
    allp = np.concatenate(tiles)
    ids = np.tile(np.arange(n), 9)
    sx, sy = aniso
    tree = cKDTree(allp * [sx, sy])
    yy, xx = np.mgrid[0:h, 0:w]
    q = np.stack([xx.ravel() * sx, yy.ravel() * sy], 1)
    d, i = tree.query(q, k=2)
    F1 = d[:, 0].reshape(h, w)
    F2 = d[:, 1].reshape(h, w)
    cid = ids[i[:, 0]].reshape(h, w)
    return F1, F2, cid


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(t, stops):
    """stops: list of (pos, (r,g,b)). t: HxW -> HxWx3"""
    t = np.clip(t, 0, 1)
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def emboss(height, strength=1.0, light=(-0.6, -0.8)):
    """Directional shading from a height map. Image y points DOWN; light=(lx,ly) is the
    direction light comes FROM in image space ((-,-) = from upper-left)."""
    gy, gx = np.gradient(height)
    # wrap-safe gradient for tileables
    gx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    gy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    return 1.0 + strength * (-(gx * light[0] + gy * light[1]))


def blur_wrap(a, sigma):
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., c], sigma, mode='wrap') for c in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, sigma, mode='wrap')


def to_img(rgb, alpha=None):
    a = np.clip(rgb, 0, 1)
    arr = (a * 255 + 0.5).astype(np.uint8)
    if alpha is not None:
        al = (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)
        return Image.fromarray(np.dstack([arr, al]), 'RGBA')
    return Image.fromarray(arr, 'RGB')


def bleed_rgb(rgba, iters=24):
    """Push colour of opaque texels into transparent ones so filtering/mips don't pull
    in black fringes. rgba float HxWx4."""
    rgb = rgba[..., :3].copy()
    a = rgba[..., 3]
    known = a > 0.02
    for _ in range(iters):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(a.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            k = np.roll(np.roll(known, dy, 0), dx, 1)
            acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * k[..., None]
            cnt += k
        newk = (~known) & (cnt > 0)
        rgb[newk] = acc[newk] / cnt[newk][:, None]
        known = known | newk
    # anything left: region mean
    if (~known).any():
        m = rgb[a > 0.02].mean(0) if (a > 0.02).any() else np.array([0.3, 0.3, 0.3])
        rgb[~known] = m
    out = rgba.copy()
    out[..., :3] = rgb
    return out


class Atlas:
    """Simple canvas with named rectangles (x, y, w, h in pixels, y down)."""

    def __init__(self, w, h, channels=3, fill=0.5):
        self.w, self.h = w, h
        self.data = np.full((h, w, channels), fill, dtype=float)
        if channels == 4:
            self.data[..., 3] = 0

    def put(self, rect, arr):
        x, y, w, h = rect
        assert arr.shape[0] == h and arr.shape[1] == w, (rect, arr.shape)
        c = arr.shape[2] if arr.ndim == 3 else 1
        self.data[y:y + h, x:x + w, :c] = arr if arr.ndim == 3 else arr[..., None]


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def draw_supersampled(w, h, ss, fn, mode='RGBA'):
    """Create a PIL image at ss× size, call fn(draw, img, ss), downsample. Returns float array."""
    img = Image.new(mode, (w * ss, h * ss), (0, 0, 0, 0) if mode == 'RGBA' else (0, 0, 0))
    d = ImageDraw.Draw(img)
    fn(d, img, ss)
    if mode == 'RGBA':
        img = img.convert('RGBa').resize((w, h), Image.LANCZOS).convert('RGBA')
    else:
        img = img.resize((w, h), Image.LANCZOS)
    return np.asarray(img).astype(float) / 255.0
