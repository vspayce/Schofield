"""Wrapped primitive drawing (strokes, stones) for tiling textures."""
import numpy as np
from PIL import Image, ImageDraw


class WrapCanvas:
    """A pair of PIL canvases (colour RGB + height L) of size S that draws every primitive at the
    tile offsets it overlaps, so the result tiles seamlessly."""

    def __init__(self, S, bg_rgb, bg_h=0):
        self.S = S
        self.rgb = Image.new('RGB', (S, S), tuple(int(c * 255) for c in bg_rgb)) if not isinstance(bg_rgb, Image.Image) else bg_rgb
        self.h = Image.new('L', (S, S), bg_h) if not isinstance(bg_h, Image.Image) else bg_h
        self.dc = ImageDraw.Draw(self.rgb)
        self.dh = ImageDraw.Draw(self.h)

    def _offsets(self, xs, ys, pad):
        S = self.S
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        ox = [0] + ([S] if x0 < 0 else []) + ([-S] if x1 >= S else [])
        oy = [0] + ([S] if y0 < 0 else []) + ([-S] if y1 >= S else [])
        return [(a, b) for a in ox for b in oy]

    def polyline(self, pts, cols, hs, widths):
        """pts: list of (x,y) (len k+1); per-segment colours (k), heights (k), widths (k)."""
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        for ox, oy in self._offsets(xs, ys, max(widths) + 2):
            for i in range(len(pts) - 1):
                a = (pts[i][0] + ox, pts[i][1] + oy)
                b = (pts[i + 1][0] + ox, pts[i + 1][1] + oy)
                w = int(round(widths[i]))
                self.dc.line([a, b], fill=cols[i], width=max(1, w))
                if hs is not None:
                    self.dh.line([a, b], fill=int(hs[i]), width=max(1, w))
                if w >= 3:  # round joints
                    r = w / 2
                    self.dc.ellipse([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=cols[i])
                    if hs is not None:
                        self.dh.ellipse([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=int(hs[i]))

    def polygon(self, pts, col, h=None):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        for ox, oy in self._offsets(xs, ys, 2):
            q = [(x + ox, y + oy) for x, y in pts]
            self.dc.polygon(q, fill=col)
            if h is not None:
                self.dh.polygon(q, fill=int(h))

    def arrays(self):
        return np.asarray(self.rgb).astype(np.float64) / 255, np.asarray(self.h).astype(np.float64) / 255


def splat_stones(n, count, rmin, rmax, rng, elong=0.35, bury=(0.2, 0.7), existing=None, pts=None, rdist=None):
    """Splat irregular domed stones (periodic). Returns height (max composite), stone id (-1 none),
    per-stone rim distance 0..1 (0 = centre). existing: height to composite over."""
    H = np.zeros((n, n)) if existing is None else existing.copy()
    ID = -np.ones((n, n), dtype=np.int32)
    R = np.ones((n, n))
    if pts is None:
        pts = rng.random((count, 2)) * n
    if rdist is None:
        rdist = rmin + (rmax - rmin) * rng.random(count) ** 2.2
    for k in range(count):
        cx, cy = pts[k]
        r = rdist[k]
        ang = rng.random() * np.pi
        e = 1 + elong * rng.random()
        harm = [(rng.normal(0, 0.12 / (j - 1)), rng.random() * 6.28) for j in range(2, 7)]
        R0 = int(np.ceil(r * e * 1.35)) + 2
        ys = np.arange(int(cy) - R0, int(cy) + R0 + 1)
        xs = np.arange(int(cx) - R0, int(cx) + R0 + 1)
        Y, X = np.meshgrid(ys - cy, xs - cx, indexing='ij')
        ca, sa = np.cos(ang), np.sin(ang)
        u = (X * ca + Y * sa) / e
        v = -X * sa + Y * ca
        th = np.arctan2(v, u)
        rr = r * (1 + sum(a * np.cos((j + 2) * th + p) for j, (a, p) in enumerate(harm)))
        d = np.sqrt(u * u + v * v) / np.maximum(rr, 0.5)
        dome = np.sqrt(np.clip(1 - d * d, 0, 1)) ** 0.8
        b = bury[0] + (bury[1] - bury[0]) * rng.random()
        hgt = (dome - b) * (r / rmax) ** 0.5 + 0.0
        hgt = np.where(d < 1, hgt, -9)
        iy = ys % n
        ix = xs % n
        sub = H[np.ix_(iy, ix)]
        m = hgt > sub
        sub = np.where(m, hgt, sub)
        H[np.ix_(iy, ix)] = sub
        subid = ID[np.ix_(iy, ix)]
        ID[np.ix_(iy, ix)] = np.where(m, k, subid)
        subr = R[np.ix_(iy, ix)]
        R[np.ix_(iy, ix)] = np.where(m, d, subr)
    return H, ID, R
