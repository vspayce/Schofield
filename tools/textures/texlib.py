"""Shared helpers for SCHOFIELD procedural textures.

Everything here is *periodic* on the image domain so that outputs tile seamlessly:
  - spectral / value noise is built on wrapping lattices,
  - blurs use mode='wrap',
  - voronoi uses a periodic KD-tree (boxsize=1),
  - stroke/shape drawing repeats primitives across the tile borders.
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageFilter
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TEX_OUT = os.path.join(ROOT, 'public', 'assets', 'textures')
UI_OUT = os.path.join(ROOT, 'public', 'assets', 'ui')
PREVIEW = os.path.join(os.path.dirname(__file__), 'previews')
FONTS = os.path.join(os.path.dirname(__file__), 'fonts')
for d in (TEX_OUT, UI_OUT, PREVIEW):
    os.makedirs(d, exist_ok=True)


# ----------------------------------------------------------------------------- noise
def value_octave(n, cells, rng, order=3):
    """Periodic smooth value noise with `cells` lattice cells across the tile."""
    g = rng.random((cells, cells))
    z = ndimage.zoom(g, n / cells, order=order, mode='grid-wrap', grid_mode=True)
    return z[:n, :n]


def fbm(n, rng, base=4, octaves=6, gain=0.5, lac=2, order=3, aniso=None):
    """Periodic fbm in [0,1]. base = lattice cells of first octave.
    aniso=(sy, sx): cell multipliers per axis to stretch features (must stay integers)."""
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    c = base
    for _ in range(octaves):
        if c > n // 2:
            break
        if aniso:
            cy, cx = max(1, int(c * aniso[0])), max(1, int(c * aniso[1]))
            g = rng.random((cy, cx))
            z = ndimage.zoom(g, (n / cy, n / cx), order=order, mode='grid-wrap', grid_mode=True)[:n, :n]
        else:
            z = value_octave(n, c, rng, order)
        out += amp * (z - 0.5)
        tot += amp
        amp *= gain
        c = int(c * lac)
    out = out / tot
    return normalize(out)


def spectral(n, rng, beta=2.0, kmin=1, kmax=None):
    """1/f^beta coloured noise via FFT (inherently periodic), normalized 0..1."""
    w = rng.standard_normal((n, n))
    F = np.fft.fft2(w)
    ky = np.fft.fftfreq(n) * n
    kx = np.fft.fftfreq(n) * n
    K = np.sqrt(ky[:, None] ** 2 + kx[None, :] ** 2)
    K[0, 0] = 1
    filt = K ** (-beta / 2)
    filt[K < kmin] = 0
    if kmax:
        filt *= np.exp(-(K / kmax) ** 2)
    out = np.real(np.fft.ifft2(F * filt))
    return normalize(out)


def normalize(a, lo=None, hi=None):
    lo = a.min() if lo is None else lo
    hi = a.max() if hi is None else hi
    return (a - lo) / (hi - lo + 1e-9)


def eq(a):
    """Histogram-equalize to uniform [0,1] (rank transform)."""
    flat = a.ravel()
    r = np.empty_like(flat)
    r[np.argsort(flat)] = np.linspace(0, 1, flat.size)
    return r.reshape(a.shape)


def ridged(a):
    return 1 - np.abs(a * 2 - 1)


def warp(img, dx, dy):
    """Sample img at (y+dy, x+dx) with wrap (dx,dy in pixels)."""
    n0, n1 = img.shape[:2]
    yy, xx = np.mgrid[0:n0, 0:n1].astype(np.float64)
    coords = [yy + dy, xx + dx]
    if img.ndim == 2:
        return ndimage.map_coordinates(img, coords, order=1, mode='grid-wrap')
    return np.stack([ndimage.map_coordinates(img[..., c], coords, order=1, mode='grid-wrap')
                     for c in range(img.shape[2])], -1)


def blur(a, s):
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., c], s, mode='wrap') for c in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, s, mode='wrap')


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- voronoi
def voronoi(n, pts, jitter_field=None):
    """Periodic voronoi. pts in [0,1)^2 (x,y). Returns F1, F2 (pixels), index of nearest."""
    tree = cKDTree(pts, boxsize=1.0)
    yy, xx = np.mgrid[0:n, 0:n] / n
    q = np.stack([xx.ravel(), yy.ravel()], -1)
    if jitter_field is not None:
        q = (q + jitter_field.reshape(-1, 2)) % 1.0
    d, i = tree.query(q, k=2)
    return (d[:, 0].reshape(n, n) * n, d[:, 1].reshape(n, n) * n, i[:, 0].reshape(n, n))


# ----------------------------------------------------------------------------- normals / output
def normal_map(h, strength=4.0):
    """Tangent-space normal map (OpenGL / three.js convention: green = +V = image up)."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5  # +row = down in image = -V
    nx = -dx * strength
    ny = dy * strength
    nz = np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    nm = np.stack([nx / l, ny / l, nz / l], -1)
    return (nm * 0.5 + 0.5)


def to8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def save_jpg(arr, name, q=85):
    p = os.path.join(TEX_OUT, name)
    Image.fromarray(to8(arr)).save(p, quality=q, optimize=True, subsampling=0 if name.endswith('_n.jpg') else 2)
    return p


def tile_preview(arr, name, reps=2, size=1024):
    a = to8(arr)
    t = np.tile(a, (reps, reps, 1) if a.ndim == 3 else (reps, reps))
    im = Image.fromarray(t).resize((size, size), Image.LANCZOS)
    im.save(os.path.join(PREVIEW, name))


def lit_preview(albedo, h, strength, name, reps=2, size=1024, sun=(-0.5, 0.6, 0.62)):
    """Albedo shaded by the normal map under a low sun — shows how relief reads."""
    nm = normal_map(h, strength) * 2 - 1
    s = np.array(sun) / np.linalg.norm(sun)
    # image space: x right, y up (normal map green=up)
    ndl = np.clip(nm[..., 0] * s[0] + nm[..., 1] * s[1] + nm[..., 2] * s[2], 0, 1)
    col = albedo * (0.35 + 0.9 * ndl[..., None])
    tile_preview(col, name, reps, size)


def perspective_preview(albedo, name, tile_m=4.0, cam_h=3.0, W=960, H=400, fov=55, pitch=-8, fog=(0.78, 0.68, 0.55)):
    """Cheap ground-plane render: camera cam_h above ground looking slightly down, texture tiled
    every tile_m metres, box-filtered by mip level. Judge how it reads at gameplay distance."""
    n = albedo.shape[0]
    mips = [albedo]
    while mips[-1].shape[0] > 4:
        a = mips[-1]
        mips.append(0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]))
    out = np.zeros((H, W, 3))
    f = (W / 2) / np.tan(np.radians(fov / 2))
    pr = np.radians(pitch)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    dx = (xs - W / 2) / f
    dy = -(ys - H / 2) / f
    # rotate by pitch about x
    dz = np.ones_like(dx)
    ry = dy * np.cos(pr) + dz * np.sin(pr)
    rz = -dy * np.sin(pr) + dz * np.cos(pr)
    hit = ry < -1e-4
    t = np.where(hit, cam_h / np.maximum(-ry, 1e-4), 0)
    wx, wz = dx * t, rz * t
    dist = t * np.sqrt(dx * dx + ry * ry + rz * rz)
    # footprint of one pixel in texels
    fp = (dist / f) / np.maximum(-ry / np.sqrt(dx * dx + ry * ry + rz * rz), 0.02) * (n / tile_m)
    lvl = np.clip(np.log2(np.maximum(fp, 1)), 0, len(mips) - 1)
    li = np.round(lvl).astype(int)
    for L in range(len(mips)):
        m = hit & (li == L)
        if not m.any():
            continue
        mm = mips[L]
        s = mm.shape[0]
        u = ((wx[m] / tile_m) % 1) * s
        v = ((wz[m] / tile_m) % 1) * s
        out[m] = mm[v.astype(int) % s, u.astype(int) % s]
    sky = np.array([0.85, 0.75, 0.6])
    fogk = 1 - np.exp(-np.where(hit, dist, 1e4) / 140.0)
    out = np.where(hit[..., None], out * (1 - fogk[..., None]) + np.array(fog) * fogk[..., None], sky)
    Image.fromarray(to8(out)).save(os.path.join(PREVIEW, name))


# ----------------------------------------------------------------------------- colour
def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def ramp(t, stops):
    """stops: list of (pos, '#hex'). t array -> rgb."""
    t = np.clip(t, 0, 1)
    ps = np.array([s[0] for s in stops])
    cs = np.array([hexc(s[1]) for s in stops])
    return np.stack([np.interp(t, ps, cs[:, c]) for c in range(3)], -1)


def lerp(a, b, t):
    """Blend; a 2-D weight is broadcast over colour channels when a or b is a colour."""
    t = np.asarray(t)
    if t.ndim == 2 and (np.ndim(a) in (1, 3) or np.ndim(b) in (1, 3)):
        t = t[..., None]
    return a + (np.asarray(b) - a) * t


def bake_light(alb, h, strength, amt=0.3, sun=(-0.45, 0.55, 0.7)):
    """Bake a little soft top-left relief lighting into the albedo so detail reads even under flat
    lighting / when the normal map is mip-mapped away. amt=0 disables."""
    nm = normal_map(h, strength) * 2 - 1
    s = np.array(sun) / np.linalg.norm(sun)
    ndl = nm[..., 0] * s[0] + nm[..., 1] * s[1] + nm[..., 2] * s[2]
    flat = s[2]
    k = 1 + amt * (ndl - flat) / flat
    return alb * np.clip(k, 0.4, 1.6)[..., None]
