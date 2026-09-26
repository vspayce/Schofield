"""Generate the props texture atlases (system python3: numpy, scipy, PIL).

Outputs (tools/blender/_build/):
  props_atlas.jpg    1024² opaque atlas: rocks, barks, saguaro, wood, planks, metal, bone, signs
  props_foliage.png  1024² RGBA alpha-cut atlas: pine clumps, fir sprays (+snow), sagebrush,
                     joshua leaves, tumbleweed, twigs
Run: python3 tools/blender/props_textures.py
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from texlib import *  # noqa
import atlas_layout as L

OUT = os.path.join(HERE, '_build')
os.makedirs(OUT, exist_ok=True)
FONTS = '/System/Library/Fonts/Supplemental/'


# ----------------------------------------------------------------------------- opaque
def rock_sand(w, h, seed=11):
    t = np.arange(h)[:, None] / h * np.ones((1, w))
    warp = fbm(h, w, seed + 1, beta=3.2)
    warp2 = fbm(h, w, seed + 2, beta=2.4, aniso=(6, 1))
    tt = t + (warp - 0.5) * 0.22 + (warp2 - 0.5) * 0.05
    r = rng(seed)
    strat = (0.5 + 0.22 * np.sin(2 * np.pi * 3 * tt + r.random() * 6)
             + 0.16 * np.sin(2 * np.pi * 9 * tt + r.random() * 6)
             + 0.08 * np.sin(2 * np.pi * 23 * tt + r.random() * 6))
    layers = fbm(h, w, seed + 3, beta=2.0, aniso=(10, 1))
    big = fbm(h, w, seed + 4, beta=3.5)
    v = np.clip(strat * 0.65 + layers * 0.35, 0, 1)
    col = ramp(v, [(0.0, (0.48, 0.32, 0.23)), (0.3, (0.63, 0.45, 0.32)), (0.55, (0.76, 0.61, 0.46)),
                   (0.78, (0.84, 0.72, 0.57)), (1.0, (0.69, 0.52, 0.38))])
    col *= (0.82 + 0.3 * big)[..., None]
    # cracks (worley cell edges, broken up)
    F1, F2, cid = worley(h, w, 14, seed + 5, aniso=(0.6, 1.3))
    edge = F2 - F1
    crack = (1 - smoothstep(0.0, 2.2, edge)) * smoothstep(0.55, 0.75, fbm(h, w, seed + 6, beta=2.5))
    # bedding cracks along strata
    bed = (1 - smoothstep(0.0, 0.035, np.abs(np.sin(2 * np.pi * 9 * tt)))) * smoothstep(0.45, 0.7, fbm(h, w, seed + 7, beta=2.2, aniso=(4, 1)))
    cells = rng(seed + 8).random(14)[cid]
    col *= (0.93 + 0.12 * cells)[..., None]
    fine = fbm(h, w, seed + 9, beta=0.9)
    height = v * 0.9 + big * 2.2 + fine * 0.35 - crack * 0.8 - bed * 0.6
    shade = emboss(blur_wrap(height, 1.0) * 6, 1.0, light=(-0.4, -0.9))
    col *= np.clip(shade, 0.6, 1.4)[..., None]
    col *= (1 - 0.55 * crack - 0.35 * bed)[..., None]
    # desert varnish streaks running down
    streak = smoothstep(0.55, 0.85, fbm(h, w, seed + 10, beta=3.0, aniso=(1, 6)))
    col = col * (1 - 0.45 * streak[..., None]) + np.array([0.26, 0.17, 0.13]) * 0.45 * streak[..., None]
    col += (fine[..., None] - 0.5) * 0.08
    return np.clip(col, 0, 1)


def rock_granite(w, h, seed=21):
    big = fbm(h, w, seed, beta=3.4)
    mid = fbm(h, w, seed + 1, beta=2.2)
    fine = fbm(h, w, seed + 2, beta=0.6)
    v = big * 0.5 + mid * 0.35 + fine * 0.15
    col = ramp(v, [(0.0, (0.30, 0.29, 0.28)), (0.4, (0.47, 0.45, 0.42)), (0.7, (0.60, 0.58, 0.54)), (1.0, (0.72, 0.70, 0.66))])
    r = rng(seed + 3)
    spec = r.random((h, w))
    col[spec > 0.93] *= 0.45
    col[spec < 0.05] = col[spec < 0.05] * 0.5 + 0.42
    col = blur_wrap(col, 0.55)
    F1, F2, cid = worley(h, w, 10, seed + 4, aniso=(1.0, 1.0))
    edge = F2 - F1
    crack = (1 - smoothstep(0.0, 2.2, edge)) * smoothstep(0.55, 0.75, fbm(h, w, seed + 5, beta=2.5))
    cells = rng(seed + 6).random(10)[cid]
    col *= (0.93 + 0.12 * cells)[..., None]
    height = big * 2.6 + mid * 1.0 + fine * 0.25 - crack * 0.8
    shade = emboss(blur_wrap(height, 1.0) * 6, 1.0, light=(-0.4, -0.9))
    col *= np.clip(shade, 0.6, 1.4)[..., None]
    col *= (1 - 0.6 * crack)[..., None]
    # lichen: yellow-green and rust-orange crusts
    l1 = fbm(h, w, seed + 7, beta=2.6)
    l1m = smoothstep(0.70, 0.76, l1) * smoothstep(0.35, 0.65, fine)
    col = col * (1 - l1m[..., None] * 0.6) + np.array([0.60, 0.60, 0.44]) * (l1m[..., None] * 0.6)
    l2 = fbm(h, w, seed + 8, beta=2.8)
    l2m = smoothstep(0.80, 0.84, l2) * (0.5 + 0.5 * fine)
    col = col * (1 - l2m[..., None] * 0.5) + np.array([0.66, 0.48, 0.26]) * (l2m[..., None] * 0.5)
    streak = smoothstep(0.6, 0.85, fbm(h, w, seed + 9, beta=2.2, aniso=(1, 14)))
    col *= (1 - 0.3 * streak)[..., None]
    return np.clip(col, 0, 1)


def bark_pond(w, h, seed=31):
    n = 64
    F1, F2, cid = worley(h, w, n, seed, aniso=(1.0, 0.42))
    edge = F2 - F1
    r = rng(seed + 1)
    tone = r.random(n)[cid]
    flake = fbm(h, w, seed + 2, beta=1.4, aniso=(1, 3))
    plate = ramp(np.clip(tone * 0.6 + flake * 0.4, 0, 1), [
        (0.0, (0.36, 0.23, 0.16)), (0.35, (0.52, 0.33, 0.21)), (0.65, (0.64, 0.44, 0.30)), (1.0, (0.66, 0.56, 0.47))])
    fiss = 1 - smoothstep(0.6, 3.5, edge)
    height = smoothstep(0.0, 7.0, edge) * 0.7 + flake * 0.6
    shade = emboss(blur_wrap(height, 0.8) * 3, 0.7, light=(-0.7, -0.7))
    col = plate * np.clip(shade, 0.6, 1.35)[..., None]
    dark = np.array([0.10, 0.07, 0.06])
    col = col * (1 - fiss[..., None]) + dark * fiss[..., None]
    # scale lines inside plates (puzzle flakes)
    sub = fbm(h, w, seed + 3, beta=1.2, aniso=(1, 2.5))
    col *= (0.85 + 0.3 * sub)[..., None]
    return np.clip(col, 0, 1)


def bark_fir(w, h, seed=41):
    """Grey-brown conifer bark: long shallow vertical fissures with flaky ridges."""
    x = (np.arange(w)[None, :] + 0.5) / w * np.ones((h, 1))
    warp = fbm(h, w, seed, beta=3.2, aniso=(1, 3))
    ph = x * 9 + (warp - 0.5) * 2.2
    f = ph - np.floor(ph)
    ridge = np.exp(-((f - 0.5) / 0.24) ** 2)
    brk = fbm(h, w, seed + 1, beta=1.6, aniso=(1, 6))
    F1, F2, cid = worley(h, w, 120, seed + 2, aniso=(1.0, 0.3))
    plate = smoothstep(0.0, 4.0, F2 - F1)
    height = ridge * 0.6 + plate * 0.4 * ridge + brk * 0.4
    tone = rng(seed + 3).random(120)[cid]
    col = ramp(np.clip(height * 0.7 + tone * 0.3, 0, 1), [(0, (0.12, 0.09, 0.07)), (0.4, (0.30, 0.24, 0.19)), (0.75, (0.45, 0.39, 0.33)), (1, (0.56, 0.51, 0.45))])
    shade = emboss(blur_wrap(height, 0.8) * 3, 0.7)
    col *= np.clip(shade, 0.7, 1.3)[..., None]
    return np.clip(col, 0, 1)


def deadwood(w, h, seed=51):
    xx = np.arange(w)[None, :] / w * np.ones((h, 1))
    warp = fbm(h, w, seed, beta=3.0)
    g = fbm(h, w, seed + 1, beta=1.8, aniso=(1, 18))
    grain = 0.5 + 0.5 * np.sin(2 * np.pi * (xx * 9 + (warp - 0.5) * 1.5) + g * 3)
    col = ramp(g * 0.6 + grain * 0.4, [(0, (0.36, 0.33, 0.30)), (0.5, (0.58, 0.55, 0.50)), (1, (0.74, 0.71, 0.66))])
    cr = smoothstep(0.82, 0.9, fbm(h, w, seed + 2, beta=2.0, aniso=(1, 30)))
    col *= (1 - 0.7 * cr)[..., None]
    col *= (0.85 + 0.25 * fbm(h, w, seed + 3, beta=3))[..., None]
    return np.clip(col, 0, 1)


def saguaro(w, h, seed=61):
    u = (np.arange(w)[None, :] + 0.5) / w * np.ones((h, 1))
    # ridge at u=0/1, valley at 0.5
    ridge = np.abs(u - 0.5) * 2  # 1 at ridge, 0 in valley
    n = fbm(h, w, seed, beta=2.0, aniso=(3, 1))
    stripes = fbm(h, w, seed + 1, beta=1.2, aniso=(1, 25))
    col = ramp(ridge * 0.7 + n * 0.2 + stripes * 0.1, [
        (0, (0.15, 0.20, 0.12)), (0.45, (0.27, 0.34, 0.20)), (0.8, (0.40, 0.46, 0.29)), (1.0, (0.52, 0.55, 0.38))])
    # horizontal growth bands / weathering
    band = fbm(h, w, seed + 2, beta=2.5, aniso=(20, 1))
    col *= (0.88 + 0.22 * band)[..., None]

    def spines(d, img, ss):
        r = rng(seed + 3)
        step = 26 * ss
        y = r.random() * step
        while y < h * ss + step:
            for cx in (0, w * ss):
                yy = y + r.uniform(-3, 3) * ss
                d.ellipse([cx - 4 * ss, yy - 4 * ss, cx + 4 * ss, yy + 4 * ss], fill=(120, 104, 78, 255))
                for k in range(9):
                    a = r.uniform(0, 2 * np.pi)
                    L_ = r.uniform(6, 14) * ss
                    d.line([cx, yy, cx + np.cos(a) * L_, yy + np.sin(a) * L_], fill=(205, 190, 160, 255), width=max(1, ss))
            y += step
    sp = draw_supersampled(w, h, 3, spines)
    a = sp[..., 3:4]
    col = col * (1 - a) + sp[..., :3] * a
    return np.clip(col, 0, 1)


def wood_grain(w, h, seed, base, nlines=11):
    """Long vertical grain: thin dark late-wood lines bent by low-freq warp and knots,
    fine fibres, checking cracks. Tileable; grain runs along image y (== UV v)."""
    x = (np.arange(w)[None, :] + 0.5) / w * np.ones((h, 1))
    yy, xg = np.mgrid[0:h, 0:w]
    warp = fbm(h, w, seed, beta=3.6, aniso=(1, 5))
    phase = x * nlines + (warp - 0.5) * 2.5
    r = rng(seed + 2)
    knot_dark = np.zeros((h, w))
    for _ in range(2):
        kx, ky = r.random() * w, r.random() * h
        for ox in (-w, 0, w):
            for oy in (-h, 0, h):
                dx = (xg - kx - ox)
                dy = (yy - ky - oy) * 0.35
                d = np.sqrt(dx ** 2 + dy ** 2)
                phase += 1.4 * np.exp(-(d / (w * 0.07)) ** 2) * np.sign(dx + 1e-3) * 0.5
                knot_dark = np.maximum(knot_dark, np.exp(-(np.sqrt(dx ** 2 + (dy / 0.35 * 0.8) ** 2) / (w * 0.018)) ** 2))
    f = phase - np.floor(phase)
    line = np.exp(-((f - 0.5) / 0.07) ** 2)
    fibers = fbm(h, w, seed + 1, beta=0.9, aniso=(1, 40))
    broad = fbm(h, w, seed + 4, beta=3.0, aniso=(1, 3))
    lo, mid, hi = base
    v = np.clip(0.25 + fibers * 0.45 + broad * 0.35 - line * 0.35, 0, 1)
    col = ramp(v, [(0, lo), (0.5, mid), (1, hi)])
    col *= (1 - 0.7 * knot_dark)[..., None]
    cr = smoothstep(0.86, 0.93, fbm(h, w, seed + 3, beta=1.8, aniso=(1, 40)))
    col *= (1 - 0.7 * cr)[..., None]
    col += (fbm(h, w, seed + 5, beta=0.3)[..., None] - 0.5) * 0.05
    return np.clip(col, 0, 1)


GREY_WOOD = ((0.30, 0.27, 0.24), (0.52, 0.49, 0.44), (0.68, 0.65, 0.59))
BROWN_WOOD = ((0.22, 0.15, 0.10), (0.40, 0.29, 0.19), (0.55, 0.42, 0.29))


def planks(w, h, seed, nboards=5, base=GREY_WOOD, gap=3):
    col = np.zeros((h, w, 3))
    edges = np.linspace(0, w, nboards + 1).astype(int)
    r = rng(seed)
    for i in range(nboards):
        x0, x1 = edges[i], edges[i + 1]
        gtex = wood_grain(x1 - x0, h, seed + 10 * i + 1, base)
        tint = np.array([1, 1, 1]) * r.uniform(0.82, 1.1) + r.uniform(-0.04, 0.04, 3)
        col[:, x0:x1] = gtex * tint
        # bevel shading at board edges
        bw = x1 - x0
        xs = np.arange(bw)
        bev = 1 - 0.35 * np.exp(-xs / 2.5) - 0.25 * np.exp(-(bw - 1 - xs) / 2.5)
        col[:, x0:x1] *= bev[None, :, None]
        col[:, x0:x0 + gap] = np.array([0.08, 0.065, 0.055])
        # nails near top & bottom (tile boundary) — rust halos
        for ny in (int(h * 0.1), int(h * 0.6)):
            cx = x0 + bw // 2
            yy, xx = np.mgrid[0:h, 0:w]
            d = np.sqrt((xx - cx) ** 2 + (yy - ny) ** 2)
            col *= (1 - 0.35 * np.exp(-(d / 5) ** 2))[..., None]
            col[d < 2.0] = np.array([0.16, 0.12, 0.10])
    return np.clip(col, 0, 1)


def planks_stencil(w, h, seed=81):
    base = planks(h, w, seed, nboards=3, base=BROWN_WOOD)  # boards along v, then rotate
    base = np.rot90(base, 1).copy()  # boards now along u
    img = Image.new('L', (w * 3, h * 3), 0)
    d = ImageDraw.Draw(img)
    f = font(FONTS + 'Rockwell.ttc', 30 * 3, index=0)
    txt = 'DYNAMITE'
    bb = d.textbbox((0, 0), txt, font=f)
    d.text(((w * 3 - (bb[2] - bb[0])) / 2 - bb[0], (h * 3 - (bb[3] - bb[1])) / 2 - bb[1] - 6), txt, font=f, fill=255)
    f2 = font(FONTS + 'Rockwell.ttc', 13 * 3, index=0)
    t2 = 'HANDLE WITH CARE'
    bb = d.textbbox((0, 0), t2, font=f2)
    d.text(((w * 3 - (bb[2] - bb[0])) / 2 - bb[0], h * 3 * 0.74), t2, font=f2, fill=255)
    m = np.asarray(img.resize((w, h), Image.LANCZOS)).astype(float) / 255
    wear = smoothstep(0.2, 0.45, fbm(h, w, seed + 5, beta=1.2))
    m *= wear * 0.92
    red = np.array([0.66, 0.22, 0.13])
    return np.clip(base * (1 - m[..., None]) + red * m[..., None], 0, 1)


def metal_rust(w, h, seed=91):
    n = fbm(h, w, seed, beta=2.4)
    f = fbm(h, w, seed + 1, beta=0.8)
    col = ramp(n * 0.7 + f * 0.3, [(0, (0.14, 0.10, 0.08)), (0.45, (0.27, 0.18, 0.12)), (0.75, (0.44, 0.26, 0.14)), (1, (0.38, 0.35, 0.32))])
    pits = rng(seed + 2).random((h, w)) > 0.97
    col[pits] *= 0.4
    return np.clip(blur_wrap(col, 0.5), 0, 1)


def bone(w, h, seed=101):
    n = fbm(h, w, seed, beta=2.2)
    f = fbm(h, w, seed + 1, beta=0.9)
    col = ramp(n * 0.6 + f * 0.4, [(0, (0.55, 0.50, 0.42)), (0.5, (0.82, 0.78, 0.68)), (1, (0.93, 0.90, 0.82))])
    cr = smoothstep(0.8, 0.88, fbm(h, w, seed + 2, beta=1.8, aniso=(1, 6)))
    col *= (1 - 0.5 * cr)[..., None]
    return np.clip(col, 0, 1)


def signs(w, h, seed=111):
    """Three columns; each a board 512 long (v) × w/3 tall (u), text rotated."""
    cols = []
    ncol = len(L.SIGN_TEXTS)
    cw = w // ncol
    for i, txt in enumerate(L.SIGN_TEXTS):
        bw = cw if i < ncol - 1 else w - cw * (ncol - 1)
        board = wood_grain(bw, h, seed + i * 7, GREY_WOOD)  # grain along v == along the board
        board = np.rot90(board, -1).copy()  # now horizontal: shape (bw, h)
        bh, bl = board.shape[:2]
        ss = 3
        img = Image.new('L', (bl * ss, bh * ss), 0)
        d = ImageDraw.Draw(img)
        f = font(FONTS + 'SuperClarendon.ttc', int(bh * 0.62 * ss), index=5)
        bb = d.textbbox((0, 0), txt, font=f)
        tw = bb[2] - bb[0]
        x = (bl * ss * 0.86 - tw) / 2 - bb[0] + bl * ss * 0.02
        y = (bh * ss - (bb[3] - bb[1])) / 2 - bb[1]
        d.text((x, y), txt, font=f, fill=255)
        # arrow head at right end
        ax = bl * ss * 0.9
        d.polygon([(ax, bh * ss * 0.25), (bl * ss * 0.985, bh * ss * 0.5), (ax, bh * ss * 0.75)], fill=255)
        m = np.asarray(img.resize((bl, bh), Image.LANCZOS)).astype(float) / 255
        wear = smoothstep(0.3, 0.55, fbm(bh, bl, seed + 30 + i, beta=1.0))
        m *= 0.85 * wear
        paint = np.array([0.88, 0.86, 0.78])
        board = board * (1 - m[..., None]) + paint * m[..., None]
        xs = np.arange(bh)
        bev = 1 - 0.3 * np.exp(-xs / 2.0) - 0.3 * np.exp(-(bh - 1 - xs) / 2.0)
        board *= bev[:, None, None]
        cols.append(np.rot90(board, 1).copy())  # back to vertical; left end of text at bottom
    return np.clip(np.concatenate(cols, 1), 0, 1)


def build_opaque():
    W, H = L.PROPS_SIZE
    A = Atlas(W, H, 3)
    R = L.PROPS
    gens = {
        'rock_sand': lambda w, h: rock_sand(w, h),
        'rock_granite': lambda w, h: rock_granite(w, h),
        'bark_pond': lambda w, h: bark_pond(w, h),
        'bark_fir': lambda w, h: bark_fir(w, h),
        'deadwood': lambda w, h: deadwood(w, h),
        'saguaro': lambda w, h: saguaro(w, h),
        'signs': lambda w, h: signs(w, h),
        'wood_grey': lambda w, h: wood_grain(w, h, 71, GREY_WOOD),
        'planks': lambda w, h: planks(w, h, 75),
        'wood_brown': lambda w, h: wood_grain(w, h, 77, BROWN_WOOD),
        'planks_stencil': lambda w, h: planks_stencil(w, h),
        'metal_rust': lambda w, h: metal_rust(w, h),
        'bone': lambda w, h: bone(w, h),
    }
    for k, rect in R.items():
        A.put(rect, gens[k](rect[2], rect[3]))
        print('  opaque', k)
    img = to_img(A.data)
    img.save(os.path.join(OUT, 'props_atlas.jpg'), quality=88, optimize=True, subsampling=0)
    return img


# ----------------------------------------------------------------------------- foliage
def lerpc(a, b, t):
    return tuple(int(255 * (a[i] + (b[i] - a[i]) * t)) for i in range(3))


def needle_tuft(d, r, cx, cy, n, length, width, dark, light, spread=np.pi, base_ang=-np.pi / 2, droop=0.25, alpha=255):
    for _ in range(n):
        a = base_ang + r.normal(0, spread * 0.5)
        L_ = length * r.uniform(0.55, 1.0)
        # curve: bend toward gravity
        mx = cx + np.cos(a) * L_ * 0.5
        my = cy + np.sin(a) * L_ * 0.5
        ex = cx + np.cos(a) * L_
        ey = cy + np.sin(a) * L_ + droop * L_ * abs(np.cos(a)) * r.uniform(0.3, 1.0)
        up = max(0.0, -np.sin(a))  # upward needles catch light
        t = np.clip(0.25 + 0.5 * up + r.uniform(-0.25, 0.3), 0, 1)
        c = lerpc(dark, light, t)
        d.line([(cx, cy), (mx, my), (ex, ey)], fill=c + (alpha,), width=width, joint='curve')


def pond_card(w, h, seed, n_tufts=6, needle_len=0.20, per_tuft=120):
    ss = 3
    W, Hh = w * ss, h * ss
    dark = (0.07, 0.12, 0.05)
    light = (0.34, 0.42, 0.18)

    def fn(d, img, s):
        r = rng(seed)
        base = (W * 0.5, Hh * 0.995)
        hub = (W * r.uniform(0.46, 0.54), Hh * 0.74)
        tw = (72, 52, 38, 255)
        d.line([base, ((base[0] + hub[0]) / 2 + W * 0.03, (base[1] + hub[1]) / 2), hub], fill=tw, width=int(7 * s), joint='curve')
        tufts = []
        for i in range(n_tufts):
            ang = -np.pi / 2 + (i - (n_tufts - 1) / 2) / max(n_tufts - 1, 1) * 2.6 + r.normal(0, 0.15)
            dist = r.uniform(0.22, 0.46) * W
            tx = hub[0] + np.cos(ang) * dist
            ty = hub[1] + np.sin(ang) * dist * 1.1
            tx = np.clip(tx, W * (0.08 + needle_len), W * (0.92 - needle_len))
            ty = np.clip(ty, Hh * (0.06 + needle_len), Hh * 0.66)
            tufts.append((tx, ty, ang))
            d.line([hub, (tx, ty)], fill=tw, width=int(4.5 * s))
        # back layer: darker, gives body so the card keeps mass when mipped
        for tx, ty, ang in tufts:
            needle_tuft(d, r, tx, ty, per_tuft // 2, needle_len * W * 0.9, int(2.2 * s),
                        (0.06, 0.10, 0.05), (0.20, 0.26, 0.11), spread=2 * np.pi, base_ang=ang)
        for tx, ty, ang in tufts:
            needle_tuft(d, r, tx, ty, per_tuft, needle_len * W, int(1.8 * s), dark, light, spread=2.4, base_ang=ang)
            # bright top needles
            needle_tuft(d, r, tx, ty, per_tuft // 3, needle_len * W * 0.85, int(1.6 * s), (0.24, 0.32, 0.13), (0.50, 0.54, 0.27),
                        spread=1.4, base_ang=-np.pi / 2 * 0.7 + ang * 0.3)
    return draw_supersampled(w, h, ss, fn)


def fir_card(w, h, seed, snow=False):
    ss = 3
    W, Hh = w * ss, h * ss

    def fn(d, img, s):
        r = rng(seed)
        stem = []
        n = 60
        for i in range(n + 1):
            t = i / n
            x = W * (0.02 + 0.95 * t)
            y = Hh * (0.5 + 0.10 * t * t) + np.sin(t * 5) * Hh * 0.01
            stem.append((x, y))
        dark = (0.07, 0.13, 0.09)
        light = (0.30, 0.40, 0.22)
        branchlets = []
        side = 1
        for i in range(4, n - 1, 3):
            t = i / n
            x, y = stem[i]
            L_ = (1 - t) ** 0.7 * Hh * 0.52 + Hh * 0.08
            for sd in (-1, 1):
                a = sd * r.uniform(0.55, 0.8) + r.normal(0, 0.08) + 0.12
                ex = x + np.cos(a) * L_
                ey = y + np.sin(a) * L_ * 0.95
                branchlets.append(((x, y), (ex, ey), L_))
        # back needles
        for (p0, p1, L_) in branchlets:
            m = int(L_ / (2.2 * s))
            for k in range(m):
                t = k / max(m - 1, 1)
                px = p0[0] + (p1[0] - p0[0]) * t
                py = p0[1] + (p1[1] - p0[1]) * t
                ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
                for sd in (-1, 1):
                    a = ang + sd * r.uniform(0.7, 1.3)
                    nl = r.uniform(10, 16) * s * (1 - 0.35 * t)
                    tt = np.clip(0.35 + 0.4 * (sd < 0) + r.uniform(-0.3, 0.3), 0, 1)
                    d.line([(px, py), (px + np.cos(a) * nl, py + np.sin(a) * nl)], fill=lerpc(dark, light, tt) + (255,), width=int(2.0 * s))
        for (p0, p1, L_) in branchlets:
            d.line([p0, p1], fill=(60, 44, 30, 255), width=int(2 * s))
        d.line(stem, fill=(70, 50, 34, 255), width=int(4 * s), joint='curve')
        # top needles over the stem
        for (x, y) in stem[::1]:
            for _ in range(5):
                a = r.uniform(-np.pi, 0)
                nl = r.uniform(6, 12) * s
                d.line([(x, y), (x + np.cos(a) * nl, y + np.sin(a) * nl)], fill=lerpc(dark, light, r.uniform(0.3, 1)) + (255,), width=int(1.7 * s))
    arr = draw_supersampled(w, h, ss, fn)
    if snow:
        from scipy import ndimage as ndi
        A = arr[..., 3]
        bA = ndi.gaussian_filter(A, 2.2)
        nz = fbm(h, w, seed + 50, beta=2.4)
        nz2 = fbm(h, w, seed + 51, beta=1.2)
        m = smoothstep(0.30, 0.5, bA) * smoothstep(0.50, 0.62, nz * 0.7 + nz2 * 0.3)
        m = np.maximum(m, np.roll(m, -2, 0) * 0.9)  # sits on top: extend upward
        m = ndi.gaussian_filter(m, 0.8)
        sb = ndi.gaussian_filter(m, 1.5)
        gy = np.gradient(sb, axis=0)
        shade = np.clip(1.0 + gy * 6.0, 0.72, 1.08)
        snowc = np.array([0.93, 0.95, 0.98])[None, None, :] * shade[..., None]
        snowc = snowc * np.array([1.0, 1.0, 1.0]) + (1 - shade[..., None]) * np.array([-0.05, 0.0, 0.08])
        mm = np.clip(m * 1.6, 0, 1)[..., None]
        arr[..., :3] = arr[..., :3] * (1 - mm) + snowc * mm
        arr[..., 3] = np.maximum(A, smoothstep(0.35, 0.6, m))
    return arr


def branchy(d, r, x, y, ang, length, width, depth, col, leaf_fn=None, spread=0.5, shrink=0.72):
    ex = x + np.cos(ang) * length
    ey = y + np.sin(ang) * length
    mx = (x + ex) / 2 + r.normal(0, length * 0.08)
    my = (y + ey) / 2 + r.normal(0, length * 0.08)
    d.line([(x, y), (mx, my), (ex, ey)], fill=col, width=max(1, int(width)), joint='curve')
    if depth <= 0:
        if leaf_fn:
            leaf_fn(ex, ey)
        return
    nb = 2 if r.random() < 0.75 else 3
    for i in range(nb):
        a = ang + r.uniform(-spread, spread) + (i - (nb - 1) / 2) * spread * 0.6
        branchy(d, r, ex, ey, a, length * r.uniform(shrink - 0.1, shrink + 0.08), width * 0.68, depth - 1, col, leaf_fn, spread, shrink)
    if leaf_fn and depth <= 2:
        leaf_fn((x + ex) / 2, (y + ey) / 2)


def sage_card(w, h, seed=201):
    ss = 3
    W, Hh = w * ss, h * ss

    def fn(d, img, s):
        r = rng(seed)
        leaves = []

        def leaf(x, y):
            leaves.append((x, y))
        for i in range(16):
            a = -np.pi / 2 + (i / 15 - 0.5) * 2.4 + r.normal(0, 0.1)
            branchy(d, r, W * 0.5 + r.normal(0, W * 0.03), Hh * 0.98, a, Hh * r.uniform(0.13, 0.19), 4 * s, 3,
                    (88, 74, 60, 255), leaf, spread=0.45)
        # leaf clusters: dark back then light silver-green
        for pas, (c0, c1, rad) in enumerate([((0.20, 0.23, 0.17), (0.32, 0.36, 0.26), 4.5), ((0.40, 0.45, 0.34), (0.64, 0.68, 0.55), 3.0)]):
            for (x, y) in leaves:
                for _ in range(22 if pas == 0 else 30):
                    px = x + r.normal(0, 7 * s)
                    py = y + r.normal(0, 6 * s)
                    ex, ey = (px - W * 0.5) / (W * 0.47), (py - Hh * 0.6) / (Hh * 0.42)
                    if py > Hh * 0.93 or ex * ex + ey * ey > 1.0 + r.uniform(-0.25, 0.1):
                        continue
                    rr = r.uniform(0.6, 1.0) * rad * s * 0.5
                    up = np.clip(1 - py / Hh, 0, 1)
                    c = lerpc(c0, c1, np.clip(r.uniform(0, 0.8) + up * 0.4, 0, 1))
                    d.ellipse([px - rr, py - rr * 1.4, px + rr, py + rr * 1.4], fill=c + (255,))
    return draw_supersampled(w, h, ss, fn)


def joshua_card(w, h, seed=211):
    ss = 3
    W, Hh = w * ss, h * ss

    def fn(d, img, s):
        r = rng(seed)
        cx, cy = W * 0.5, Hh * 0.5
        # dead skirt (drooping brown leaves)
        for _ in range(70):
            a = np.pi / 2 + r.normal(0, 0.7)
            L_ = r.uniform(0.25, 0.42) * Hh
            ex, ey = cx + np.cos(a) * L_ * 0.6, cy + abs(np.sin(a)) * L_
            c = lerpc((0.25, 0.20, 0.14), (0.55, 0.46, 0.33), r.random())
            wv = r.uniform(3, 5) * s
            d.polygon([(cx - wv, cy), (cx + wv, cy), (ex, ey)], fill=c + (255,))
        # live rosette
        for k in range(110):
            a = r.uniform(-np.pi, 0.25 * np.pi) if r.random() < 0.85 else r.uniform(0, np.pi)
            if a > 0.3 and a < np.pi - 0.3 and r.random() < 0.7:
                continue
            L_ = r.uniform(0.28, 0.47) * Hh
            ex, ey = cx + np.cos(a) * L_, cy + np.sin(a) * L_
            nx, ny = -np.sin(a), np.cos(a)
            wv = r.uniform(3.5, 6) * s
            t = np.clip(0.4 + (-np.sin(a)) * 0.4 + r.uniform(-0.3, 0.3), 0, 1)
            c = lerpc((0.20, 0.27, 0.14), (0.55, 0.62, 0.32), t)
            d.polygon([(cx + nx * wv, cy + ny * wv), (cx - nx * wv, cy - ny * wv), (ex, ey)], fill=c + (255,))
            d.line([(ex - np.cos(a) * 8 * s, ey - np.sin(a) * 8 * s), (ex, ey)], fill=(200, 180, 110, 255), width=int(1.5 * s))
    return draw_supersampled(w, h, ss, fn)


def tumble_card(w, h, seed=221):
    ss = 3
    W, Hh = w * ss, h * ss

    def fn(d, img, s):
        r = rng(seed)
        cx, cy, R = W / 2, Hh / 2, W * 0.46
        for i in range(520):
            # arcs biased toward the rim
            rad = R * r.uniform(0.05, 1.0) ** 0.45
            a0 = r.uniform(0, 2 * np.pi)
            pts = []
            steps = 6
            da = r.uniform(0.2, 0.7) * r.choice([-1, 1])
            rr = rad
            for k in range(steps):
                a = a0 + da * k / steps
                rr = np.clip(rr + r.normal(0, R * 0.05), R * 0.1, R)
                pts.append((cx + np.cos(a) * rr, cy + np.sin(a) * rr))
            t = r.random()
            c = lerpc((0.40, 0.30, 0.20), (0.80, 0.68, 0.48), t)
            d.line(pts, fill=c + (255,), width=int(r.uniform(1.2, 2.2) * s), joint='curve')
    return draw_supersampled(w, h, ss, fn)


def twig_card(w, h, seed=231):
    ss = 3
    W, Hh = w * ss, h * ss

    def fn(d, img, s):
        r = rng(seed)
        for i in range(3):
            branchy(d, r, W * (0.5 + (i - 1) * 0.04), Hh * 0.99, -np.pi / 2 + (i - 1) * 0.35, Hh * 0.3, 6 * s, 5,
                    (140, 132, 122, 255), None, spread=0.55, shrink=0.72)
    return draw_supersampled(w, h, ss, fn)


def build_foliage():
    W, H = L.FOLIAGE_SIZE
    A = Atlas(W, H, 4)
    R = L.FOLIAGE
    gens = {
        'pond_a': lambda w, h: pond_card(w, h, 301, n_tufts=6, needle_len=0.19, per_tuft=130),
        'pond_b': lambda w, h: pond_card(w, h, 302, n_tufts=9, needle_len=0.13, per_tuft=110),
        'fir': lambda w, h: fir_card(w, h, 303, snow=False),
        'fir_snow': lambda w, h: fir_card(w, h, 303, snow=True),
        'sage': lambda w, h: sage_card(w, h),
        'joshua': lambda w, h: joshua_card(w, h),
        'tumble': lambda w, h: tumble_card(w, h),
        'twigs': lambda w, h: twig_card(w, h),
    }
    for k, rect in R.items():
        arr = gens[k](rect[2], rect[3])
        # colour: un-premultiplied already; harden alpha a bit for MASK
        arr = bleed_rgb(arr)
        A.put(rect, arr)
        print('  foliage', k)
    img = to_img(A.data[..., :3], A.data[..., 3])
    img.save(os.path.join(OUT, 'props_foliage_rgba.png'))
    # palette-quantise for size (MASK alpha only needs a hard-ish edge)
    q = img.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    q.save(os.path.join(OUT, 'props_foliage.png'), optimize=True)
    return img


if __name__ == '__main__':
    which = sys.argv[1:] or ['opaque', 'foliage']
    if 'opaque' in which:
        build_opaque()
    if 'foliage' in which:
        build_foliage()
    for f in ('props_atlas.jpg', 'props_foliage.png'):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            print(f, os.path.getsize(p) // 1024, 'KB')
