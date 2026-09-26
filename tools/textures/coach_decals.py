#!/usr/bin/env python3
"""Paint the stagecoach body decals (gold pinstripe, belt band, lettering,
door medallion) as projection images consumed by tools/blender/build_stagecoach.py.

Outputs (tools/blender/src_tex/):
  coach_side_col.png  RGBA  colour + coverage, projected on the body sides (Y,Z)
  coach_side_gold.png L     gold-leaf mask (-> metallic / low roughness)
  coach_rear_col.png  RGBA  projected on the rear & front faces (X,Z)
  coach_rear_gold.png L

All layout comes from tools/blender/coach_dims.py (metres, Blender space).
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'blender'))
import coach_dims as D  # noqa: E402

OUT = os.path.join(HERE, '..', 'blender', 'src_tex')
os.makedirs(OUT, exist_ok=True)

GOLD = np.array([222, 178, 86], np.float32) / 255
GOLD_SH = np.array([26, 10, 6], np.float32) / 255
BELT = np.array([34, 11, 9], np.float32) / 255
SEAM = np.array([14, 6, 4], np.float32) / 255
FONT = '/System/Library/Fonts/Supplemental/SuperClarendon.ttc'


class Canvas:
    def __init__(self, u0, u1, v0, v1, w):
        self.u0, self.u1, self.v0, self.v1 = u0, u1, v0, v1
        self.W = w
        self.H = int(round(w * (v1 - v0) / (u1 - u0)))
        self.px = (u1 - u0) / w                   # metres per pixel
        us = u0 + (np.arange(self.W) + 0.5) * self.px
        vs = v1 - (np.arange(self.H) + 0.5) * self.px
        self.U, self.V = np.meshgrid(us, vs)
        self.rgb = np.zeros((self.H, self.W, 3), np.float32)
        self.a = np.zeros((self.H, self.W), np.float32)
        self.gold = np.zeros((self.H, self.W), np.float32)

    # coverage helpers (sd < 0 inside)
    def fill(self, sd):
        return np.clip(0.5 - sd / self.px, 0, 1)

    def stroke(self, sd, width, offset=0.0):
        return np.clip(0.5 - (np.abs(sd - offset) - width / 2) / self.px, 0, 1)

    def put(self, cov, col, gold=0.0):
        col = np.asarray(col, np.float32)
        self.rgb = self.rgb * (1 - cov[..., None]) + col * cov[..., None]
        self.a = self.a + cov * (1 - self.a)
        self.gold = self.gold * (1 - cov) + gold * cov

    def to_px(self, u, v):
        return ((u - self.u0) / self.px, (self.v1 - v) / self.px)

    def text(self, s, cu, cv, height, col, gold=1.0, shadow=True, max_w=None):
        hpx = int(round(height / self.px))
        font = ImageFont.truetype(FONT, int(hpx * 1.35))
        bbox = font.getbbox(s)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        layer = Image.new('L', (tw + 8, th + 8), 0)
        ImageDraw.Draw(layer).text((4 - bbox[0], 4 - bbox[1]), s, font=font, fill=255)
        sx = 1.0
        if max_w and tw * self.px > max_w:
            sx = max_w / (tw * self.px)
        layer = layer.resize((max(1, int(layer.width * sx)), int(layer.height * hpx / th)), Image.LANCZOS)
        cx, cy = self.to_px(cu, cv)
        big = Image.new('L', (self.W, self.H), 0)
        big.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))
        m = np.asarray(big, np.float32) / 255
        if shadow:
            off = max(1, int(0.004 / self.px))
            sh = np.roll(np.roll(m, off, 0), off, 1)
            self.put(sh * 0.9, GOLD_SH, 0.0)
        self.put(m, col, gold)

    def save(self, name):
        rgba = np.dstack([self.rgb, self.a])
        Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGBA').save(
            os.path.join(OUT, name + '_col.png'))
        Image.fromarray((np.clip(self.gold, 0, 1) * 255 + 0.5).astype(np.uint8), 'L').save(
            os.path.join(OUT, name + '_gold.png'))


def sd_box(U, V, cu, cv, hu, hv, r=0.0):
    qx = np.abs(U - cu) - (hu - r)
    qy = np.abs(V - cv) - (hv - r)
    out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    return out + np.minimum(np.maximum(qx, qy), 0) - r


def sd_ellipse(U, V, cu, cv, ru, rv):
    # cheap approximation, good near the boundary
    k = np.hypot((U - cu) / ru, (V - cv) / rv)
    return (k - 1) * min(ru, rv)


def sd_polygon(c, pts):
    pts = np.asarray(pts, np.float32)
    d = np.full(c.U.shape, 1e9, np.float32)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        ab = b - a
        t = np.clip(((c.U - a[0]) * ab[0] + (c.V - a[1]) * ab[1]) / max(ab @ ab, 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(c.U - (a[0] + t * ab[0]), c.V - (a[1] + t * ab[1])))
    mask = Image.new('L', (c.W, c.H), 0)
    ImageDraw.Draw(mask).polygon([c.to_px(p[0], p[1]) for p in pts], fill=255)
    inside = np.asarray(mask) > 127
    return np.where(inside, -d, d)


def smin_max(*ds):
    out = ds[0]
    for d in ds[1:]:
        out = np.maximum(out, d)
    return out


def belt_and_edges(c):
    z0, z1 = D.BELT_Z
    band = np.clip(np.minimum((c.V - z0) / c.px + 0.5, (z1 - c.V) / c.px + 0.5), 0, 1)
    c.put(band, BELT)
    c.put(c.stroke(c.V - (z0 + 0.0065), 0.0045), GOLD, 1)
    c.put(c.stroke(c.V - (z1 - 0.0065), 0.0045), GOLD, 1)
    c.put(c.stroke(c.V - 2.186, 0.006), GOLD, 1)


def side():
    s = D.SIDE_DECAL
    c = Canvas(s['y0'] - D.YC, s['y1'] - D.YC, s['z0'], s['z1'], s['w'])
    U, V = c.U, c.V
    outline = [(y - D.YC, z) for (y, z) in D.side_outline()]
    sil = sd_polygon(c, outline)

    # outline stripe following the egg-shaped silhouette (lower body + upper ends)
    keep = ((V < 1.535) | ((V > 1.625) & (V < 2.17))).astype(np.float32)
    c.put(c.stroke(sil, 0.010, -0.032) * keep, GOLD, 1)
    c.put(c.stroke(sil, 0.0035, -0.052) * keep * (V < 1.535), GOLD, 1)

    belt_and_edges(c)

    # window surrounds
    wz0, wz1 = D.WINDOW_Z
    for (y0, y1) in D.WINDOWS_Y:
        cu, hu = (y0 + y1) / 2, (y1 - y0) / 2
        cv, hv = (wz0 + wz1) / 2, (wz1 - wz0) / 2
        d = sd_box(U, V, cu, cv, hu + 0.030, hv + 0.030, 0.05)
        c.put(c.stroke(d, 0.009), GOLD, 1)
        c.put(c.stroke(d, 0.0035, 0.020), GOLD, 1)

    # door seam + hinges shadow lines
    dy0, dy1 = D.DOOR_Y
    dz0, dz1 = D.DOOR_Z
    door = sd_box(U, V, 0, (dz0 + dz1) / 2, (dy1 - dy0) / 2, (dz1 - dz0) / 2, 0.035)
    c.put(c.stroke(door, 0.006), SEAM, 0)

    # door lower panel with medallion
    dp = sd_box(U, V, 0, 1.29, 0.235, 0.205, 0.05)
    c.put(c.stroke(dp, 0.009), GOLD, 1)
    c.put(c.stroke(dp, 0.0035, -0.020), GOLD, 1)
    med = sd_ellipse(U, V, 0, 1.29, 0.150, 0.118)
    inside = c.fill(med)
    t = np.clip((V - (1.29 - 0.118)) / 0.236, 0, 1)
    sky = np.dstack([0.93 - 0.45 * t, 0.64 - 0.12 * t, 0.36 + 0.22 * t])
    c.put(inside, np.zeros(3))  # reset
    c.rgb = c.rgb * (1 - inside[..., None]) + sky * inside[..., None]
    # sun + mesas
    sun = c.fill(np.hypot(U - 0.045, V - 1.265) - 0.022) * inside
    c.put(sun, [1.0, 0.85, 0.55])
    mesa = (V < 1.235 + 0.035 * np.clip(1 - np.abs(U + 0.06) / 0.07, 0, 1).clip(0, 0.8) * 1.2
            + 0.01 * np.sin(U * 90)).astype(np.float32)
    c.put(mesa * inside, [0.36, 0.20, 0.17])
    ground = (V < 1.215 + 0.012 * np.sin(U * 40 + 1)).astype(np.float32)
    c.put(ground * inside, [0.17, 0.10, 0.06])
    c.put(c.stroke(med, 0.008), GOLD, 1)
    c.put(c.stroke(med, 0.003, 0.016), GOLD, 1)

    # lower quarter panels either side of the door
    for sgn in (-1, 1):
        q = smin_max(sil + 0.075, V - 1.49, (0.375 - sgn * U))
        c.put(c.stroke(q, 0.009), GOLD, 1)
        c.put(c.stroke(q, 0.0035, -0.020), GOLD, 1)
        # little corner scrolls at the upper inner corner
        cu, cv = sgn * 0.435, 1.43
        ring = np.hypot(U - cu, V - cv) - 0.022
        c.put(c.stroke(ring, 0.0035) * ((V - cv) * 1 + sgn * (U - cu) * 0.0 < 0.012), GOLD, 1)
        c.put(c.fill(np.hypot(U - cu, V - cv) - 0.006), GOLD, 1)

    # stage-line name on the top rail
    c.text('OVERLAND  STAGE  Co.', 0.0, 2.11, 0.058, GOLD, max_w=1.9)
    c.save('coach_side')


def rear():
    s = D.REAR_DECAL
    # u axis = -X (screen-right seen from behind), so mirror x0/x1 here
    c = Canvas(s['x0'], s['x1'], s['z0'], s['z1'], s['w'])
    U, V = c.U, c.V
    belt_and_edges(c)
    for (z0, z1) in ((1.64, 2.14), (1.02, 1.50)):
        d = sd_box(U, V, 0, (z0 + z1) / 2, 0.58, (z1 - z0) / 2, 0.06)
        c.put(c.stroke(d, 0.009), GOLD, 1)
        c.put(c.stroke(d, 0.0035, -0.020), GOLD, 1)
    c.text('No. 7', 0.0, 2.035, 0.07, GOLD)
    c.save('coach_rear')


if __name__ == '__main__':
    side()
    rear()
    print('decals written to', os.path.abspath(OUT))
