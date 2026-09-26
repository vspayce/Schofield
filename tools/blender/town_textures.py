"""Generate the ghost-town atlas (system python3: numpy, scipy, PIL).

Output: tools/blender/_build/town_atlas.jpg (1024², opaque) — sun-bleached board siding,
peeling paint, clapboard, shingles, rusty tin, deck boards, brick, trim, faded painted
signs, windows (glass / broken / boarded / open), doors, interior darkness, iron, rope.
Run: python3 tools/blender/town_textures.py
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from texlib import *  # noqa
import atlas_layout as L
from props_textures import wood_grain, GREY_WOOD, BROWN_WOOD

OUT = os.path.join(HERE, '_build')
os.makedirs(OUT, exist_ok=True)
FONTS = '/System/Library/Fonts/Supplemental/'
BLEACHED = ((0.34, 0.31, 0.27), (0.56, 0.52, 0.46), (0.72, 0.68, 0.61))


def board_and_batten(w, h, seed, nboards=11, base=BLEACHED):
    col = np.zeros((h, w, 3))
    height = np.zeros((h, w))
    edges = np.round(np.linspace(0, w, nboards + 1)).astype(int)
    r = rng(seed)
    for i in range(nboards):
        x0, x1 = edges[i], edges[i + 1]
        g = wood_grain(x1 - x0, h, seed + 17 * i, base, nlines=3)
        tint = r.uniform(0.85, 1.08) + r.uniform(-0.03, 0.03, 3)
        col[:, x0:x1] = g * tint
        bw = x1 - x0
        xs = np.arange(bw)
        col[:, x0:x1] *= (1 - 0.25 * np.exp(-xs / 1.5) - 0.15 * np.exp(-(bw - 1 - xs) / 2.0))[None, :, None]
        col[:, x0:x0 + 2] = np.array([0.07, 0.06, 0.05])
        # occasional knot hole / split
        if r.random() < 0.35:
            ky = r.integers(0, h)
            yy, xx = np.mgrid[0:h, 0:w]
            d = np.sqrt(((xx - (x0 + bw / 2)) * 1.0) ** 2 + ((yy - ky) * 0.6) ** 2)
            col[d < 2.5] = np.array([0.05, 0.04, 0.04])
    # battens over every 2nd seam
    for i in range(1, nboards, 2):
        x = edges[i]
        bw = 7
        x0 = max(0, x - bw // 2)
        g = wood_grain(bw, h, seed + 500 + i, base, nlines=1) * 1.05
        col[:, x0:x0 + bw] = g[:, :min(bw, w - x0)]
        col[:, x0:x0 + 1] *= 0.55
        col[:, min(w - 1, x0 + bw)] *= 0.45  # shadow right of the batten
    # nail heads rows
    for ny in (int(h * 0.08), int(h * 0.58)):
        for i in range(nboards):
            cx = (edges[i] + edges[i + 1]) // 2
            col[ny - 1:ny + 1, cx - 1:cx + 1] = np.array([0.15, 0.1, 0.08])
            col[ny + 1:ny + 7, cx - 1:cx + 1] *= 0.8  # rust drip
    # water staining from the top, sun bleaching variation
    stain = fbm(h, w, seed + 3, beta=2.8, aniso=(1, 8))
    col *= (0.85 + 0.25 * stain)[..., None]
    return np.clip(col, 0, 1)


def peel_paint(base, seed, paint, coverage=0.55, fade=0.35):
    h, w = base.shape[:2]
    m = fbm(h, w, seed, beta=3.2)
    m2 = fbm(h, w, seed + 1, beta=1.4)
    mask = smoothstep(1 - coverage - 0.03, 1 - coverage + 0.03, m * 0.85 + m2 * 0.15)
    # paint keeps the board structure (gaps/grain) but flattens tone
    lum = base.mean(-1, keepdims=True)
    pc = np.array(paint)[None, None, :] * (0.55 + 0.6 * lum / max(lum.mean(), 1e-3) * 0.75)
    pc = pc * (1 - fade) + np.array([0.78, 0.74, 0.68]) * fade  # sun bleach
    chalk = fbm(h, w, seed + 2, beta=1.0)
    pc *= (0.9 + 0.15 * chalk)[..., None]
    # dark edge where paint flakes
    edge = np.abs(np.gradient(mask, axis=1)) + np.abs(np.gradient(mask, axis=0))
    out = base * (1 - mask[..., None]) + pc * mask[..., None]
    out *= (1 - np.clip(edge * 1.5, 0, 0.35))[..., None]
    return np.clip(out, 0, 1)


def clapboard(w, h, seed=41, rows=20):
    col = np.zeros((h, w, 3))
    edges = np.round(np.linspace(0, h, rows + 1)).astype(int)
    r = rng(seed)
    for i in range(rows):
        y0, y1 = edges[i], edges[i + 1]
        g = np.rot90(wood_grain(y1 - y0, w, seed + i * 7, BLEACHED, nlines=2), 1)  # grain along u
        col[y0:y1] = g[:y1 - y0, :w] * r.uniform(0.9, 1.05)
        bh = y1 - y0
        ys = np.arange(bh)
        # lap shadow at the bottom edge of each board, highlight at top
        col[y0:y1] *= (0.8 + 0.25 * ys / bh)[::-1][:, None, None] * 1.0
        col[y1 - 2:y1] *= 0.45
    col = peel_paint(col, seed + 9, (0.86, 0.84, 0.78), coverage=0.62, fade=0.2)
    return np.clip(col, 0, 1)


def shingles(w, h, seed=51, rows=10):
    col = np.zeros((h, w, 3))
    rh = h // rows
    r = rng(seed)
    for i in range(rows):
        y0 = i * rh
        x = -r.integers(0, 20)
        while x < w:
            sw = int(r.uniform(14, 30))
            x0, x1 = max(0, x), min(w, x + sw)
            if x1 > x0:
                g = wood_grain(x1 - x0, rh, int(r.integers(0, 10 ** 6)), ((0.22, 0.18, 0.15), (0.40, 0.35, 0.30), (0.55, 0.50, 0.44)), nlines=2)
                t = r.uniform(0.75, 1.15)
                col[y0:y0 + rh, x0:x1] = g * t
                col[y0:y0 + rh, x0:x0 + 1] *= 0.35
            x += sw
        ys = np.arange(rh)
        # image y down: the bottom (down-slope) edge of each row casts shadow on the next row
        col[y0:y0 + rh] *= (0.65 + 0.35 * np.clip(ys / (rh * 0.35), 0, 1))[:, None, None]
        col[y0 + rh - 2:y0 + rh] *= 0.8
    moss = smoothstep(0.62, 0.75, fbm(h, w, seed + 1, beta=2.4))
    col = col * (1 - 0.4 * moss[..., None]) + np.array([0.35, 0.33, 0.22]) * 0.4 * moss[..., None]
    return np.clip(col, 0, 1)


def tin(w, h, seed=61):
    x = (np.arange(w)[None, :] + 0.5) / w * np.ones((h, 1))
    rib = np.sin(2 * np.pi * x * 24)
    shade = 0.8 + 0.2 * rib
    rust = fbm(h, w, seed, beta=2.4)
    streak = fbm(h, w, seed + 1, beta=2.0, aniso=(1, 12))
    t = np.clip(rust * 0.6 + streak * 0.4, 0, 1)
    col = ramp(t, [(0, (0.46, 0.46, 0.44)), (0.45, (0.42, 0.34, 0.27)), (0.7, (0.45, 0.25, 0.13)), (1, (0.28, 0.14, 0.08))])
    col *= shade[..., None]
    # sheet overlaps (every 0.8 m => 256 px / 2.5) with nail rows
    for k in range(3):
        xs = int(w * (k + 0.5) / 2.5) % w
    for yy in (int(h * 0.2), int(h * 0.7)):
        col[yy:yy + 2] *= 0.5
        col[yy + 2:yy + 14] *= np.linspace(0.8, 1.0, 12)[:, None, None]
    return np.clip(col, 0, 1)


def deck(w, h, seed=71, nb=13):
    # boards along u: build vertically then rotate
    col = np.zeros((w, h, 3))
    edges = np.round(np.linspace(0, w, nb + 1)).astype(int)
    r = rng(seed)
    for i in range(nb):
        x0, x1 = edges[i], edges[i + 1]
        g = wood_grain(x1 - x0, h, seed + 11 * i, ((0.26, 0.22, 0.18), (0.46, 0.41, 0.35), (0.62, 0.57, 0.50)), nlines=2)
        col[x0:x1] = np.transpose(g, (1, 0, 2))[:x1 - x0] if False else np.zeros((x1 - x0, h, 3))
        col[x0:x1] = np.transpose(g * r.uniform(0.8, 1.1), (1, 0, 2)).transpose(0, 1, 2)[:x1 - x0] if g.shape[1] == x1 - x0 else col[x0:x1]
    # simpler: generate row by row
    col = np.zeros((h, w, 3))
    edges = np.round(np.linspace(0, h, nb + 1)).astype(int)
    for i in range(nb):
        y0, y1 = edges[i], edges[i + 1]
        g = np.rot90(wood_grain(y1 - y0, w, seed + 11 * i, ((0.26, 0.22, 0.18), (0.46, 0.41, 0.35), (0.62, 0.57, 0.50)), nlines=2), 1)
        col[y0:y1] = g * r.uniform(0.8, 1.1)
        col[y0:y0 + 2] = np.array([0.06, 0.05, 0.04])
        # staggered butt joint
        jx = int(r.uniform(0, w))
        col[y0:y1, jx:jx + 2] = np.array([0.08, 0.07, 0.06])
        for nx in (jx - 5, jx + 6):
            if 0 <= nx < w:
                col[y0 + 3:y0 + 5, nx:nx + 2] = np.array([0.12, 0.09, 0.07])
    wear = fbm(h, w, seed + 5, beta=2.5, aniso=(4, 1))
    col *= (0.85 + 0.25 * wear)[..., None]
    return np.clip(col, 0, 1)


def brick(w, h, seed=81, cols=10, rows=30):
    col = np.zeros((h, w, 3))
    r = rng(seed)
    mortar = np.array([0.55, 0.50, 0.44])
    col[:] = mortar
    bh = h / rows
    bw = w / cols
    for j in range(rows):
        off = (bw / 2) if j % 2 else 0
        for i in range(-1, cols + 1):
            x0 = int(i * bw + off) + 1
            x1 = int((i + 1) * bw + off) - 1
            y0 = int(j * bh) + 1
            y1 = int((j + 1) * bh) - 1
            c = np.array([0.52, 0.27, 0.19]) * r.uniform(0.7, 1.15) + r.uniform(-0.03, 0.03, 3)
            xa, xb = max(0, x0), min(w, x1)
            if xb > xa:
                col[y0:y1, xa:xb] = c
            # wrap
            if x1 > w:
                col[y0:y1, 0:x1 - w] = c
    n = fbm(h, w, seed + 1, beta=1.0)
    col *= (0.85 + 0.25 * n)[..., None]
    grime = fbm(h, w, seed + 2, beta=2.5, aniso=(1, 6))
    col *= (0.8 + 0.3 * grime)[..., None]
    return np.clip(col, 0, 1)


def window(w, h, kind, seed):
    ss = 4
    img = Image.new('RGB', (w * ss, h * ss), (14, 11, 9))
    d = ImageDraw.Draw(img)
    r = rng(seed)
    W, H = w * ss, h * ss
    fr = 7 * ss  # frame width
    # interior darkness with faint depth gradient
    arr = np.zeros((H, W, 3))
    yy = np.linspace(0, 1, H)[:, None]
    arr[:] = (np.array([0.05, 0.04, 0.035]) + 0.04 * (1 - yy)[..., None])
    img = Image.fromarray((arr * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    panes = [(fr + (W - 2 * fr) * i / 2, fr + (H - 2 * fr) * j / 3, fr + (W - 2 * fr) * (i + 1) / 2, fr + (H - 2 * fr) * (j + 1) / 3) for i in range(2) for j in range(3)]
    if kind in ('glass', 'broken'):
        for k, (x0, y0, x1, y1) in enumerate(panes):
            if kind == 'broken' and r.random() < 0.6:
                # jagged shard left in the corner
                cx, cy = (x0, y0) if r.random() < 0.5 else (x1, y1)
                pts = [(cx, cy), (cx + (x1 - x0) * r.uniform(0.2, 0.6) * (1 if cx == x0 else -1), cy),
                       (cx, cy + (y1 - y0) * r.uniform(0.2, 0.7) * (1 if cy == y0 else -1))]
                d.polygon(pts, fill=(70, 82, 88))
                continue
            # dusty glass: reflection gradient + dirt
            for yy_ in range(int(y0), int(y1)):
                t = (yy_ - y0) / (y1 - y0)
                c = (int(40 + 50 * (1 - t)), int(52 + 55 * (1 - t)), int(60 + 60 * (1 - t)))
                d.line([(x0, yy_), (x1, yy_)], fill=c)
            d.line([(x0 + (x1 - x0) * 0.2, y1), (x0 + (x1 - x0) * 0.7, y0)], fill=(120, 130, 135), width=3 * ss)
        # tattered curtain
        if kind == 'glass':
            d.polygon([(fr, fr), (fr + W * 0.28, fr), (fr + W * 0.18, H * 0.55), (fr, H * 0.7)], fill=(96, 58, 44))
    elif kind == 'boarded':
        pass
    elif kind == 'open':
        d.polygon([(W - fr, fr), (W - fr - W * 0.22, fr), (W - fr - W * 0.12, H * 0.45), (W - fr, H * 0.6)], fill=(70, 44, 34))
    # frame + muntins (faded white paint over grey wood)
    fcol = (176, 168, 150)
    d.rectangle([0, 0, W, fr], fill=fcol)
    d.rectangle([0, H - fr, W, H], fill=fcol)
    d.rectangle([0, 0, fr, H], fill=fcol)
    d.rectangle([W - fr, 0, W, H], fill=fcol)
    if kind in ('glass', 'broken'):
        d.rectangle([W / 2 - 1.5 * ss, fr, W / 2 + 1.5 * ss, H - fr], fill=fcol)
        for j in (1, 2):
            y = fr + (H - 2 * fr) * j / 3
            d.rectangle([fr, y - 1.5 * ss, W - fr, y + 1.5 * ss], fill=fcol)
    img = img.resize((w, h), Image.LANCZOS)
    a = np.asarray(img).astype(float) / 255
    # weather the frame paint
    fm = np.zeros((h, w), bool)
    fm[:7] = fm[-7:] = True
    fm[:, :7] = fm[:, -7:] = True
    wood = wood_grain(w, h, seed + 3, BLEACHED)
    peel = smoothstep(0.55, 0.65, fbm(h, w, seed + 4, beta=1.5))
    frame_mix = (a.sum(-1) > 1.2)[..., None] * peel[..., None]
    a = a * (1 - frame_mix) + wood * frame_mix
    if kind == 'boarded':
        for k, (yc, ang) in enumerate([(0.3, 0.15), (0.55, -0.1), (0.78, 0.05)]):
            bd = wood_grain(w + 40, 16, seed + 10 + k, GREY_WOOD, nlines=1)
            bimg = Image.fromarray((np.rot90(wood_grain(16, w + 40, seed + 10 + k, GREY_WOOD, nlines=1), 1) * 255).astype(np.uint8))
            bimg = bimg.convert('RGBA').rotate(math.degrees(ang), expand=True, resample=Image.BICUBIC)
            base = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).convert('RGBA')
            base.alpha_composite(bimg, (int(w / 2 - bimg.width / 2), int(h * yc - bimg.height / 2)))
            a = np.asarray(base.convert('RGB')).astype(float) / 255
    return np.clip(a, 0, 1)


def door(w, h, kind, seed):
    if kind == 'panel':
        g = wood_grain(w, h, seed, BROWN_WOOD, nlines=4)
        col = peel_paint(g, seed + 1, (0.30, 0.36, 0.30), coverage=0.6, fade=0.25)
        # raised panels
        for (x0, y0, x1, y1) in [(0.14, 0.06, 0.46, 0.45), (0.54, 0.06, 0.86, 0.45), (0.14, 0.52, 0.46, 0.94), (0.54, 0.52, 0.86, 0.94)]:
            X0, Y0, X1, Y1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
            col[Y0:Y0 + 2, X0:X1] *= 1.25
            col[Y0:Y1, X0:X0 + 2] *= 1.2
            col[Y1 - 2:Y1, X0:X1] *= 0.5
            col[Y0:Y1, X1 - 2:X1] *= 0.55
        ky, kx = int(0.52 * h), int(0.82 * w)
        col[ky - 3:ky + 3, kx - 3:kx + 3] = np.array([0.35, 0.28, 0.12])
        col[:, :3] *= 0.4
        col[:, -3:] *= 0.4
        return np.clip(col, 0, 1)
    if kind == 'saloon':
        col = np.zeros((h, w, 3))
        yy = np.linspace(0, 1, h)[:, None]
        col[:] = np.array([0.05, 0.04, 0.035])
        col += (0.05 * np.exp(-((yy - 0.45) / 0.3) ** 2))[..., None] * np.array([1.0, 0.7, 0.4])  # faint lamp glow
        y0, y1 = int(0.28 * h), int(0.72 * h)
        for side in (0, 1):
            x0 = 3 if side == 0 else w // 2 + 1
            x1 = w // 2 - 1 if side == 0 else w - 3
            g = wood_grain(x1 - x0, y1 - y0, seed + side, BROWN_WOOD, nlines=2)
            g = peel_paint(g, seed + 5 + side, (0.55, 0.20, 0.14), coverage=0.7, fade=0.3)
            # louvres
            for k in range(y0 + 10, y1 - 10, 7):
                g[k - y0:k - y0 + 2] *= 0.45
            # top curve
            col[y0:y1, x0:x1] = g
        return np.clip(col, 0, 1)
    if kind == 'barn':
        col = np.zeros((h, w, 3))
        planks = np.zeros((h, w, 3))
        nb = 7
        e = np.round(np.linspace(0, w, nb + 1)).astype(int)
        for i in range(nb):
            planks[:, e[i]:e[i + 1]] = wood_grain(e[i + 1] - e[i], h, seed + i, BLEACHED, nlines=2)
            planks[:, e[i]:e[i] + 2] *= 0.35
        col = peel_paint(planks, seed + 9, (0.55, 0.18, 0.12), coverage=0.5, fade=0.3)
        # Z/X bracing boards
        img = Image.fromarray((col * 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        bc = (150, 140, 120)
        for (y0, y1) in [(4, 12), (h // 2 - 4, h // 2 + 4), (h - 12, h - 4)]:
            d.rectangle([0, y0, w, y1], fill=bc)
        d.line([(6, 12), (w - 6, h // 2 - 4)], fill=bc, width=9)
        d.line([(w - 6, 12), (6, h // 2 - 4)], fill=bc, width=9)
        d.line([(6, h // 2 + 4), (w - 6, h - 12)], fill=bc, width=9)
        d.line([(w - 6, h // 2 + 4), (6, h - 12)], fill=bc, width=9)
        a = np.asarray(img).astype(float) / 255
        brace = (np.abs(a - np.array(bc) / 255).sum(-1) < 0.02)
        wood = wood_grain(w, h, seed + 30, BLEACHED)
        a[brace] = wood[brace] * 1.05
        return np.clip(a, 0, 1)


def signs(w, h, seed=91):
    styles = [  # (text, bg paint, letter colour, font, index)
        ('SALOON', (0.42, 0.13, 0.10), (0.92, 0.84, 0.62), 'SuperClarendon.ttc', 5),
        ('GENERAL STORE', (0.84, 0.80, 0.68), (0.12, 0.10, 0.09), 'Rockwell.ttc', 2),
        ('SHERIFF', (0.14, 0.12, 0.10), (0.86, 0.70, 0.36), 'SuperClarendon.ttc', 5),
        ('BANK', (0.16, 0.26, 0.20), (0.90, 0.78, 0.45), 'Bodoni 72.ttc', 2),
        ('HOTEL', (0.10, 0.10, 0.10), (0.92, 0.90, 0.84), 'SuperClarendon.ttc', 5),
        ('LIVERY', None, (0.90, 0.88, 0.82), 'Rockwell.ttc', 2),
    ]
    sh = h // len(styles)
    out = np.zeros((h, w, 3))
    for i, (txt, bg, fg, fnt, idx) in enumerate(styles):
        board = np.rot90(wood_grain(sh, w, seed + i, BLEACHED, nlines=2), 1).copy()  # grain along u
        if bg is not None:
            board = peel_paint(board, seed + 20 + i, bg, coverage=0.75, fade=0.3)
        ss = 3
        img = Image.new('L', (w * ss, sh * ss), 0)
        d = ImageDraw.Draw(img)
        size = int(sh * ss * 0.66)
        try:
            f = font(FONTS + fnt, size, index=idx)
        except Exception:
            f = font(FONTS + fnt, size, index=0)
        bb = d.textbbox((0, 0), txt, font=f)
        tw = bb[2] - bb[0]
        if tw > w * ss * 0.9:
            size = int(size * w * ss * 0.9 / tw)
            try:
                f = font(FONTS + fnt, size, index=idx)
            except Exception:
                f = font(FONTS + fnt, size, index=0)
            bb = d.textbbox((0, 0), txt, font=f)
            tw = bb[2] - bb[0]
        d.text(((w * ss - tw) / 2 - bb[0], (sh * ss - (bb[3] - bb[1])) / 2 - bb[1]), txt, font=f, fill=255)
        # border line
        d.rectangle([5 * ss, 5 * ss, w * ss - 5 * ss, sh * ss - 5 * ss], outline=180, width=2 * ss)
        m = np.asarray(img.resize((w, sh), Image.LANCZOS)).astype(float) / 255
        wear = smoothstep(0.25, 0.5, fbm(sh, w, seed + 40 + i, beta=1.3))
        m *= 0.9 * wear
        board = board * (1 - m[..., None]) + np.array(fg) * m[..., None]
        ys = np.arange(sh)
        board *= (1 - 0.4 * np.exp(-ys / 2.0) - 0.4 * np.exp(-(sh - 1 - ys) / 2.0))[:, None, None]
        out[i * sh:(i + 1) * sh] = board
    return np.clip(out, 0, 1)


def dark(w, h):
    yy = np.linspace(0, 1, h)[:, None, None]
    col = np.ones((h, w, 3)) * np.array([0.045, 0.038, 0.032]) * (1 + 0.6 * (1 - yy))
    return col


def iron(w, h, seed=95):
    n = fbm(h, w, seed, beta=2.0)
    return ramp(n, [(0, (0.12, 0.10, 0.09)), (0.6, (0.28, 0.18, 0.12)), (1, (0.42, 0.26, 0.14))])


def rope(w, h, seed=97):
    x = np.arange(w)[None, :] / w
    y = np.arange(h)[:, None] / h
    tw = 0.5 + 0.5 * np.sin(2 * np.pi * (x * 3 + y * 6))
    col = ramp(tw * 0.8 + fbm(h, w, seed, beta=0.8) * 0.2, [(0, (0.30, 0.24, 0.15)), (1, (0.66, 0.56, 0.38))])
    return col


def build():
    W, H = L.TOWN_SIZE
    A = Atlas(W, H, 3)
    R = L.TOWN
    grey = lambda w, h: board_and_batten(w, h, 1)
    gens = {
        'siding_grey': grey,
        'siding_red': lambda w, h: peel_paint(board_and_batten(w, h, 2), 12, (0.50, 0.17, 0.12), coverage=0.6, fade=0.25),
        'siding_ochre': lambda w, h: peel_paint(board_and_batten(w, h, 3), 13, (0.80, 0.62, 0.34), coverage=0.6, fade=0.3),
        'clapboard': lambda w, h: clapboard(w, h),
        'shingle': lambda w, h: shingles(w, h),
        'tin': lambda w, h: tin(w, h),
        'floor': lambda w, h: deck(w, h),
        'brick': lambda w, h: brick(w, h),
        'trim': lambda w, h: wood_grain(w, h, 33, BLEACHED, nlines=5),
        'signs': lambda w, h: signs(w, h),
        'win_glass': lambda w, h: window(w, h, 'glass', 1),
        'win_broken': lambda w, h: window(w, h, 'broken', 2),
        'win_boarded': lambda w, h: window(w, h, 'boarded', 3),
        'win_open': lambda w, h: window(w, h, 'open', 4),
        'door_panel': lambda w, h: door(w, h, 'panel', 5),
        'door_saloon': lambda w, h: door(w, h, 'saloon', 6),
        'door_barn': lambda w, h: door(w, h, 'barn', 7),
        'dark': lambda w, h: dark(w, h),
        'iron': lambda w, h: iron(w, h),
        'rope': lambda w, h: rope(w, h),
    }
    for k, rect in R.items():
        A.put(rect, gens[k](rect[2], rect[3]))
    img = to_img(A.data)
    p = os.path.join(OUT, 'town_atlas.jpg')
    img.save(p, quality=87, optimize=True, subsampling=0)
    print('town_atlas.jpg', os.path.getsize(p) // 1024, 'KB')


if __name__ == '__main__':
    build()
