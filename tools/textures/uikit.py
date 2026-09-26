"""Helpers for SCHOFIELD UI art: supersampled masks, height-field lighting (emboss), materials,
drop shadows, grain, engraving hatch."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage
from texlib import UI_OUT, PREVIEW, FONTS, hexc, smoothstep, to8, fbm, normalize
import os

LIGHT = np.array([-0.5, -0.62, 0.6])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


class Mask:
    """Supersampled drawing surface returning float masks."""

    def __init__(self, w, h, ss=4):
        self.w, self.h, self.ss = w, h, ss
        self.im = Image.new('L', (w * ss, h * ss), 0)
        self.d = ImageDraw.Draw(self.im)

    def S(self, v):
        return v * self.ss

    def circle(self, cx, cy, r, fill=255):
        s = self.ss
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=fill)
        return self

    def ring(self, cx, cy, r, width, fill=255):
        s = self.ss
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], outline=fill, width=int(width * s))
        return self

    def poly(self, pts, fill=255):
        s = self.ss
        self.d.polygon([(x * s, y * s) for x, y in pts], fill=fill)
        return self

    def line(self, pts, width, fill=255, joint='curve'):
        s = self.ss
        self.d.line([(x * s, y * s) for x, y in pts], fill=fill, width=max(1, int(width * s)), joint=joint)
        return self

    def rect(self, x0, y0, x1, y1, fill=255, r=0):
        s = self.ss
        if r:
            self.d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], radius=r * s, fill=fill)
        else:
            self.d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], fill=fill)
        return self

    def arc(self, cx, cy, r, a0, a1, width, fill=255):
        s = self.ss
        self.d.arc([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], a0, a1, fill=fill, width=int(width * s))
        return self

    def text(self, xy, txt, fnt, fill=255, anchor='mm'):
        s = self.ss
        self.d.text((xy[0] * s, xy[1] * s), txt, font=fnt, fill=fill, anchor=anchor)
        return self

    def get(self, hi=False):
        """float mask at final size (or supersampled if hi)."""
        if hi:
            return np.asarray(self.im).astype(np.float64) / 255
        return np.asarray(self.im.resize((self.w, self.h), Image.LANCZOS)).astype(np.float64) / 255


def down(a, w, h):
    """Downsample a float array (H,W[,C]) to (h,w)."""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(to8(a)).resize((w, h), Image.LANCZOS)).astype(np.float64) / 255
    return np.stack([down(a[..., c], w, h) for c in range(a.shape[2])], -1)


def gblur(a, s):
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., c], s) for c in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, s)


def bevel(mask, radius, profile='round'):
    """Height field from a mask: rises over `radius` px from the edge (distance transform)."""
    inside = ndimage.distance_transform_edt(mask > 0.5)
    t = np.clip(inside / max(radius, 1e-3), 0, 1)
    if profile == 'round':
        hgt = np.sqrt(1 - (1 - t) ** 2)
    else:
        hgt = t
    return gblur(hgt, 0.7) * (mask > 0.02)


def light(h, base, scale=1.0, amb=0.5, diff=1.0, spec=0.0, shin=24, spec_col=(1, 1, 1)):
    """Shade a height field. base: (H,W,3) or rgb. Returns rgb."""
    gy, gx = np.gradient(h * scale)
    n = np.stack([-gx, -gy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    ndl = np.clip((n * LIGHT).sum(-1), 0, 1)
    flat = LIGHT[2]
    k = (amb + (1 - amb) * diff * ndl / flat)[..., None]  # flat surface -> ~1.0
    b = np.asarray(base, dtype=np.float64)
    col = (b if b.ndim == 3 else b[None, None, :]) * k
    if spec:
        hv = LIGHT + np.array([0, 0, 1.0])
        hv /= np.linalg.norm(hv)
        s = np.clip((n * hv).sum(-1), 0, 1) ** shin * spec
        col = col + s[..., None] * np.array(spec_col)
    return col


def metal_gradient(h, w, stops, angle=0.0):
    """Vertical-ish linear gradient ramp for metal."""
    from texlib import ramp
    yy, xx = np.mgrid[0:h, 0:w]
    t = (yy / h) * np.cos(angle) + (xx / w) * np.sin(angle)
    return ramp(normalize(t), stops)


def radial(h, w, cx, cy, r):
    yy, xx = np.mgrid[0:h, 0:w]
    return np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r


def grain(h, w, amt, seed=0):
    rng = np.random.default_rng(seed)
    return 1 + amt * (rng.random((h, w)) - 0.5)


def noise(h, w, seed=0, base=6, octaves=5):
    n = max(h, w)
    n2 = 1 << int(np.ceil(np.log2(n)))
    f = fbm(n2, np.random.default_rng(seed), base=base, octaves=octaves)
    return f[:h, :w]


def compose(layers, w, h):
    """layers: list of (rgb (H,W,3), alpha (H,W)) bottom->top. Returns RGBA float."""
    out = np.zeros((h, w, 4))
    for rgb, a in layers:
        a = np.clip(a, 0, 1)
        ao = out[..., 3]
        na = a + ao * (1 - a)
        rgb = np.broadcast_to(rgb, (h, w, 3)) if np.ndim(rgb) == 1 else rgb
        out[..., :3] = np.where(na[..., None] > 1e-6,
                                (rgb * a[..., None] + out[..., :3] * ao[..., None] * (1 - a[..., None])) / np.maximum(na[..., None], 1e-6),
                                out[..., :3])
        out[..., 3] = na
    return out


def drop_shadow(alpha, dx, dy, blur_px, opacity):
    sh = np.roll(np.roll(alpha, int(dy), 0), int(dx), 1)
    return gblur(sh, blur_px) * opacity


def save_rgba(arr, name, bg_preview=(0.25, 0.2, 0.16)):
    img = Image.fromarray(to8(arr))
    p = os.path.join(UI_OUT, name)
    img.save(p, optimize=True)
    # preview on a mid background + checker to judge alpha
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    chk = ((xx // 16 + yy // 16) % 2)[..., None] * 0.08 + np.array(bg_preview)
    a = arr[..., 3:4]
    prev = arr[..., :3] * a + chk * (1 - a)
    Image.fromarray(to8(prev)).save(os.path.join(PREVIEW, 'ui_' + name.replace('.png', '.jpg')), quality=92)
    print('wrote', name, img.size)
    return p


def hatch_fill(mask, darkness, period=4.0, angle=0.0, jitter=None):
    """Engraving: parallel lines whose thickness follows darkness (0 = paper, 1 = solid ink)."""
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    c = yy * np.cos(angle) + xx * np.sin(angle)
    if jitter is not None:
        c = c + jitter
    ph = (c / period) % 1.0
    tri = np.abs(ph - 0.5) * 2  # 0 at line centre -> 1 between lines
    ink = smoothstep(darkness + 0.08, darkness - 0.08, tri)
    return ink * mask
