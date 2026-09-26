"""SCHOFIELD UI art, part 2: touch buttons, poster/paper panels, weapon engravings, logo.
Run through gen_ui.py (python3 tools/textures/gen_ui.py [name ...])."""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from texlib import hexc, ramp, smoothstep, to8, normalize, fbm, UI_OUT, PREVIEW
from uikit import *
import os

BRASS = [(0, '#4a3312'), (0.35, '#9a7430'), (0.6, '#cfae5e'), (0.8, '#f0dc98'), (1, '#a88238')]


def yx(h, w):
    return np.mgrid[0:h, 0:w].astype(np.float64)


def outline_of(mask, px):
    return np.clip(ndi.grey_dilation(mask, size=(px, px)) - mask, 0, 1)


# =============================================================================== touch buttons
BTN = 220


def _btn_base(leather_stops, seed):
    n = BTN
    c = n / 2 - 0.5
    y, x = yx(n, n)
    R = radial(n, n, c, c, 1)
    ang = np.arctan2(y - c, x - c)
    disc = smoothstep(106, 104.8, R)
    bez = disc * smoothstep(91.5, 92.5, R)
    leather = smoothstep(92.5, 91.5, R)
    # brass bezel: rounded profile + knurling + 8 rivets
    t = np.clip((R - 92) / 13, 0, 1)
    hb = np.sin(t * np.pi) ** 0.7
    knurl = (0.5 + 0.5 * np.sin(ang * 90)) * smoothstep(0.6, 0.9, t) * smoothstep(1.0, 0.92, t)
    hb = hb + 0.05 * knurl
    riv = np.zeros((n, n))
    for k in range(8):
        a = k * np.pi / 4 + np.pi / 8
        px, py = c + np.cos(a) * 98.5, c + np.sin(a) * 98.5
        d = np.hypot(x - px, y - py)
        riv = np.maximum(riv, np.sqrt(np.clip(1 - (d / 3.6) ** 2, 0, 1)))
    hb = hb + 0.6 * riv
    bcol = ramp(normalize(1 - (x + y) / (2 * n)) * 0.8 + 0.1, BRASS)
    bcol *= (0.92 + 0.16 * noise(n, n, seed + 1, base=16))[..., None]
    bcol = light(hb * 6, bcol, scale=1.2, amb=0.55, spec=0.8, shin=20, spec_col=(1, 0.9, 0.65))
    # leather: dome + grain pores + wrinkles + wear in centre
    g1 = noise(n, n, seed + 2, base=24, octaves=4)
    g2 = noise(n, n, seed + 3, base=64, octaves=3)
    rng = np.random.default_rng(seed)
    pores = gblur((rng.random((n, n)) > 0.985).astype(float), 0.9)
    hl = 0.6 * (1 - (R / 92) ** 2) + 0.06 * g1 + 0.012 * g2 - 0.04 * pores
    # stitched groove
    groove = smoothstep(2.2, 0.6, np.abs(R - 84))
    hl -= 0.12 * groove
    lcol = ramp(0.35 + 0.5 * (1 - R / 92) * 0.5 + 0.3 * g1, leather_stops)
    lcol *= (1 + 0.06 * (g2 - 0.5))[..., None]
    lcol = light(hl, lcol, scale=40, amb=0.55, spec=0.25, shin=10)
    # stitches: dashes along the groove
    stitch = (np.sin(ang * 48) > 0.25).astype(float) * smoothstep(1.6, 0.6, np.abs(R - 84))
    lcol = lcol * (1 - stitch[..., None]) + np.array([0.82, 0.74, 0.58]) * stitch[..., None] * (0.8 + 0.2 * (y < c))[..., None]
    # inner shadow under the bezel lip
    lsh = smoothstep(92, 80, R)
    lcol *= (0.55 + 0.45 * lsh)[..., None]
    out = compose([(np.zeros(3), drop_shadow(disc, 0, 4, 5, 0.6)),
                   (np.clip(lcol, 0, 1), leather), (np.clip(bcol, 0, 1), bez)], n, n)
    out[..., 3] = np.maximum(out[..., 3], 0)
    return out


def _btn_icon(base, icon_mask, col_stops=None, glow=None):
    """Emboss an icon mask (float, BTN²) onto the button in cream/brass with a dark inset shadow."""
    n = BTN
    col_stops = col_stops or [(0, '#7a6440'), (0.5, '#d9c69a'), (1, '#fbf1d6')]
    y, x = yx(n, n)
    h = bevel(icon_mask > 0.5, 4)
    icol = ramp(normalize(1 - (y / n) * 0.8 - (x / n) * 0.2) * 0.7 + 0.3, col_stops)
    icol = light(h, icol, scale=6, amb=0.6, spec=0.5, shin=16)
    layers = [(base[..., :3], base[..., 3]),
              (np.zeros(3), drop_shadow(icon_mask, 2, 3, 2.5, 0.8))]
    if glow is not None:
        layers.append((hexc(glow), gblur(icon_mask, 6) * 0.7))
    layers.append((np.clip(icol, 0, 1), icon_mask))
    return compose(layers, n, n)


LEATHER = [(0, '#1a0f08'), (0.5, '#3a2416'), (1, '#5c3a22')]
OXBLOOD = [(0, '#1e0605'), (0.5, '#4a110c'), (1, '#7a2016')]


def _icon_bullet(m, c=110):
    # cartridge, tip up-right at 45 degrees
    pts = []
    L, W = 104, 30
    ca, sa = np.cos(-np.pi / 4), np.sin(-np.pi / 4)

    def T(u, v):  # u along axis (0 base -> L tip), v across
        return (c + (u - L / 2) * ca - v * sa, c + (u - L / 2) * sa + v * ca)
    case = [T(0, -W / 2 - 3), T(8, -W / 2 - 3), T(8, -W / 2), T(58, -W / 2), T(58, W / 2), T(8, W / 2), T(8, W / 2 + 3), T(0, W / 2 + 3)]
    m.poly(case)
    tip = [T(61, -W / 2 + 1)]
    for k in range(17):
        a = -np.pi / 2 + k * np.pi / 16
        tip.append(T(61 + 34 * np.cos(a) ** 1 * (1 if True else 0) * 1.0 * (np.cos(a)), (W / 2 - 1) * np.sin(a)))
    tip = [T(61, -W / 2 + 1)] + [T(61 + 40 * np.cos(a) ** 0.8, (W / 2 - 1) * np.sin(a)) for a in np.linspace(-np.pi / 2, np.pi / 2, 21)] + [T(61, W / 2 - 1)]
    m.poly(tip)


def btn_fire():
    base = _btn_base(OXBLOOD, 10)
    m = Mask(BTN, BTN)
    _icon_bullet(m)
    save_rgba(_btn_icon(base, m.get(), glow='#ffb060'), 'btn_fire.png')


def btn_reload():
    base = _btn_base(LEATHER, 11)
    m = Mask(BTN, BTN)
    c, r = 110, 44
    for a0 in (200, 20):
        m.arc(c, c, r, a0, a0 + 130, 13)
        a = np.radians(a0 + 130)
        tx, ty = c + np.cos(a) * r, c + np.sin(a) * r
        tang = a + np.pi / 2
        nx, ny = np.cos(a), np.sin(a)
        m.poly([(tx + nx * 17, ty + ny * 17), (tx - nx * 17, ty - ny * 17),
                (tx + np.cos(tang) * 24, ty + np.sin(tang) * 24)])
    # little cartridge heads in the middle (3)
    for k in range(3):
        a = k * 2 * np.pi / 3 - np.pi / 2
        m.circle(c + np.cos(a) * 14, c + np.sin(a) * 14, 8)
    save_rgba(_btn_icon(base, m.get()), 'btn_reload.png')


def _revolver(m, ox, oy, s):
    T = lambda x, y: (ox + x * s, oy + y * s)
    m.poly([T(34, 5), T(98, 5), T(98, 12), T(34, 12)])            # barrel
    m.poly([T(95, 1), T(98, 1), T(98, 5), T(95, 5)])              # front sight
    m.rect(*T(21, 1), *T(40, 18), r=3 * s)                        # cylinder
    m.poly([T(12, 2), T(24, 2), T(24, 19), T(34, 19), T(30, 22), T(14, 20)])  # frame
    m.poly([T(14, 3), T(6, -4), T(2, -4), T(8, 4)])               # hammer spur
    m.poly([T(12, 16), T(22, 18), T(19, 30), T(12, 42), T(2, 42), T(6, 28)])  # grip
    m.ring(*T(27, 24), 5.5 * s, 2.2 * s)                          # trigger guard


def _shotgun(m, ox, oy, s):
    T = lambda x, y: (ox + x * s, oy + y * s)
    m.poly([T(0, 8), T(6, 6), T(44, 11), T(50, 11), T(50, 18), T(44, 18), T(38, 24), T(32, 24), T(30, 19), T(6, 22), T(0, 22)])  # stock
    m.rect(*T(48, 9), *T(62, 18), r=1.5 * s)                     # action
    m.poly([T(52, 9), T(50, 3), T(46, 1), T(48, 5), T(49, 9)])    # hammer
    m.rect(*T(60, 9), *T(132, 15), r=1.5 * s)                    # barrels
    m.rect(*T(62, 14), *T(90, 18), r=2 * s)                      # forend
    m.ring(*T(55, 21), 4.5 * s, 1.8 * s)


def btn_swap():
    base = _btn_base(LEATHER, 12)
    m = Mask(BTN, BTN)
    _revolver(m, 40, 60, 1.02)
    _shotgun(m, 32, 124, 0.97)
    # curved double-headed swap arrow on the right
    m.arc(116, 110, 68, -34, 34, 6)
    for a, sgn in ((-34, -1), (34, 1)):
        ar = np.radians(a)
        tx, ty = 116 + np.cos(ar) * 68, 110 + np.sin(ar) * 68
        tang = ar + sgn * np.pi / 2
        nx, ny = np.cos(ar), np.sin(ar)
        m.poly([(tx + nx * 10, ty + ny * 10), (tx - nx * 10, ty - ny * 10), (tx + np.cos(tang) * 16, ty + np.sin(tang) * 16)])
    save_rgba(_btn_icon(base, m.get()), 'btn_swap.png')


def btn_deadeye():
    base = _btn_base(LEATHER, 13)
    n = BTN
    c = 110
    y, x = yx(n, n)
    d1 = np.hypot(x - c, y - (c + 40))
    d2 = np.hypot(x - c, y - (c - 40))
    eye = smoothstep(68, 66.5, d1) * smoothstep(68, 66.5, d2) * smoothstep(66, 64.5, np.abs(x - c))
    ring = smoothstep(21, 20, np.hypot(x - c, y - c)) * smoothstep(12, 13, np.hypot(x - c, y - c))
    pupil = smoothstep(7, 6, np.hypot(x - c, y - c))
    inner = smoothstep(58, 56.5, d1) * smoothstep(58, 56.5, d2) * smoothstep(56, 54.5, np.abs(x - c))
    mk = np.clip(eye - inner + ring + pupil, 0, 1)
    out = _btn_icon(base, mk, col_stops=[(0, '#5a0c08'), (0.5, '#c8301e'), (1, '#ff8a60')], glow='#ff3010')
    save_rgba(out, 'btn_deadeye.png')


def btn_whip():
    base = _btn_base(LEATHER, 14)
    m = Mask(BTN, BTN)
    # braided handle, bottom-left
    m.line([(54, 168), (88, 134)], 14)
    m.circle(52, 170, 9)
    for k in range(4):
        t = 0.2 + k * 0.18
        px, py = 54 + (88 - 54) * t, 168 + (134 - 168) * t
        m.line([(px - 7, py - 7), (px + 7, py + 7)], 2.0, fill=0)
    # lash: cubic bezier S-curve, tapering, flicking up to the right
    P = np.array([(88, 134), (170, 170), (100, 40), (172, 54)], float)
    t = np.linspace(0, 1, 80)[:, None]
    pts = (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]
    for i in range(len(pts) - 1):
        wdt = 8.5 * (1 - i / len(pts)) ** 1.2 + 1.8
        m.line([tuple(pts[i]), tuple(pts[i + 1])], wdt)
    tx, ty = pts[-1]
    for k in range(5):
        a = -np.pi / 4 + (k - 2) * 0.5
        m.line([(tx + np.cos(a) * 9, ty + np.sin(a) * 9), (tx + np.cos(a) * 21, ty + np.sin(a) * 21)], 3.5)
    save_rgba(_btn_icon(base, m.get()), 'btn_whip.png')


def btn_brake():
    base = _btn_base(LEATHER, 15)
    n = BTN
    c = 110
    y, x = yx(n, n)
    # horseshoe: thick arc open at the bottom
    R = np.hypot((x - c) / 0.92, y - (c - 4))
    ang = np.degrees(np.arctan2(y - (c - 4), x - c))
    shoe = smoothstep(58, 56.5, R) * smoothstep(30, 31.5, R) * ((ang < 50) | (ang > 130)).astype(float)
    # calkins (heels)
    m = Mask(n, n)
    for sx in (-1, 1):
        a = np.radians(90 - sx * 40)
        m.circle(c + np.cos(a) * 44 * 0.92, (c - 4) + np.sin(a) * 44, 13)
    heels = m.get()
    shoe = np.clip(shoe + heels, 0, 1)
    # nail holes
    holes = np.zeros((n, n))
    for a in np.radians([150, 175, 200, 230, 310, 340, 5, 30]):
        hx, hy = c + np.cos(a) * 44 * 0.92, (c - 4) + np.sin(a) * 44
        holes = np.maximum(holes, smoothstep(4.2, 3.2, np.hypot(x - hx, y - hy)))
    groove = smoothstep(1.6, 0.6, np.abs(R - 44)) * shoe
    mk = np.clip(shoe - holes - 0.35 * groove, 0, 1)
    save_rgba(_btn_icon(base, mk, col_stops=[(0, '#3a3e44'), (0.5, '#9aa2aa'), (1, '#e6ebef')]), 'btn_brake.png')


# =============================================================================== paper panels
def _paper_base(w, h, seed, stops, stains=6, folds=((0.5, 'h'),), foxing=300):
    rng = np.random.default_rng(seed)
    n = 1 << int(np.ceil(np.log2(max(w, h))))
    y, x = yx(h, w)
    big = fbm(n, rng, base=3, octaves=5)[:h, :w]
    mid = fbm(n, rng, base=12, octaves=5)[:h, :w]
    fib = fbm(n, rng, base=96, octaves=3, aniso=(0.3, 1))[:h, :w]
    col = ramp(0.5 + 0.6 * (big - 0.5) + 0.35 * (mid - 0.5), stops)
    col *= (0.96 + 0.08 * fib)[..., None]
    # edge darkening (age)
    ed = np.minimum.reduce([x, w - 1 - x, y, h - 1 - y]) / min(w, h)
    col *= (0.72 + 0.28 * smoothstep(0.0, 0.18, ed + 0.05 * (mid - 0.5)))[..., None]
    # water / coffee stains: soft blotch with darker tide-line ring
    for _ in range(stains):
        cx, cy = rng.random() * w, rng.random() * h
        r = rng.uniform(40, 160)
        wob = 1 + 0.7 * (fbm(n, rng, base=3, octaves=4)[:h, :w] - 0.5)
        d = np.hypot(x - cx, y - cy) / (r * wob)
        inside = smoothstep(1.0, 0.7, d) * rng.uniform(0.03, 0.08)
        tide = smoothstep(0.1, 0.0, np.abs(d - 1.0)) * rng.uniform(0.03, 0.08) * (0.4 + wob - 0.75)
        col *= (1 - inside - tide)[..., None]
        col = col * (1 - 0.3 * tide[..., None]) + hexc('#7a4a20') * 0.3 * tide[..., None]
    # foxing specks
    for _ in range(foxing):
        cx, cy = rng.random() * w, rng.random() * h
        r = rng.uniform(1, 5)
        if abs(cx - w / 2) > w * 0.3 or rng.random() < 0.3:
            d = np.hypot(x[int(max(cy - 8, 0)):int(cy + 8), int(max(cx - 8, 0)):int(cx + 8)] - cx,
                         y[int(max(cy - 8, 0)):int(cy + 8), int(max(cx - 8, 0)):int(cx + 8)] - cy)
            sub = col[int(max(cy - 8, 0)):int(cy + 8), int(max(cx - 8, 0)):int(cx + 8)]
            sub *= (1 - 0.25 * smoothstep(r, 0, d))[..., None]
    # folds: bright ridge + dark valley
    for pos, ori in folds:
        if ori == 'h':
            d = y - pos * h + 6 * (mid - 0.5)
        else:
            d = x - pos * w + 6 * (mid - 0.5)
        col *= (1 + 0.08 * np.exp(-((d + 2) / 2) ** 2) - 0.12 * np.exp(-((d - 1.5) / 1.5) ** 2) - 0.03 * np.exp(-(d / 30) ** 2))[..., None]
    col *= grain(h, w, 0.05, seed)[..., None]
    return col, mid


def _torn_alpha(w, h, seed, inset=24, amp=14, burnt=False):
    rng = np.random.default_rng(seed)
    n = 1 << int(np.ceil(np.log2(max(w, h))))
    y, x = yx(h, w)
    d = np.minimum.reduce([x - inset, w - 1 - inset - x, y - inset, h - 1 - inset - y])
    n1 = fbm(n, rng, base=10, octaves=6, gain=0.6)[:h, :w]
    n2 = fbm(n, rng, base=48, octaves=4)[:h, :w]
    dd = d + amp * (n1 - 0.5) * 2 + 5 * (n2 - 0.5) * 2
    # a few deeper tears / bites
    for _ in range(5):
        cx, cy = rng.random() * w, rng.random() * h
        side = rng.integers(4)
        if side == 0:
            cx = inset
        elif side == 1:
            cx = w - inset
        elif side == 2:
            cy = inset
        else:
            cy = h - inset
        r = rng.uniform(15, 40)
        dd -= 22 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / r ** 2)
    alpha = smoothstep(-0.8, 0.8, dd)
    return alpha, dd


def poster():
    w, h = 1024, 1280
    col, mid = _paper_base(w, h, 21, [(0, '#b89a68'), (0.5, '#d6bf8e'), (1, '#e6d4a8')], stains=5,
                           folds=((0.36, 'h'), (0.69, 'h'), (0.5, 'v')))
    alpha, dd = _torn_alpha(w, h, 22, inset=20, amp=12)
    # torn fibres: lighter rim right at the tear
    col = col * (1 + 0.12 * smoothstep(6, 0, dd))[..., None]
    y, x = yx(h, w)
    # nail holes at top corners with rust bleed
    for cx, cy in ((70, 70), (w - 70, 72)):
        d = np.hypot(x - cx, y - cy)
        col = col * (1 - 0.5 * np.exp(-(d / 22) ** 2) * (1 + (y > cy)))[..., None]
        col = col * (1 - 0.1 * np.exp(-(np.abs(x - cx) / 6) ** 2) * (y > cy) * np.exp(-(y - cy) / 120))[..., None]
        alpha = alpha * smoothstep(4, 6, d)
    # printed border: double rule frame
    ink = np.zeros((h, w))
    for off, wd in ((70, 5), (84, 1.8)):
        e = np.minimum.reduce([np.abs(x - off), np.abs(x - (w - off)), np.abs(y - off), np.abs(y - (h - off))])
        inside_box = (x >= off - wd) & (x <= w - off + wd) & (y >= off - wd) & (y <= h - off + wd)
        ink = np.maximum(ink, smoothstep(wd / 2 + 0.7, wd / 2 - 0.3, e) * inside_box)
    # WANTED headline
    m = Mask(w, h, ss=2)
    fs = 250
    while font('Rye-Regular.ttf', fs * 2).getlength('WANTED') > 780 * 2:
        fs -= 4
    m.text((w / 2, 250), 'WANTED', font('Rye-Regular.ttf', fs * 2))
    ink = np.maximum(ink, m.get())
    # ornamental rules under headline
    m2 = Mask(w, h, ss=2)
    m2.rect(150, 392, w - 150, 398).rect(150, 406, w - 150, 408)
    for sx in (130, w - 130):
        m2.poly([(sx, 380), (sx + 12, 400), (sx, 420), (sx - 12, 400)])
    m2.poly([(w / 2 - 14, 400), (w / 2, 386), (w / 2 + 14, 400), (w / 2, 414)])
    ink = np.maximum(ink, m2.get())
    # print texture: uneven ink, speckle dropouts, slight spread
    rng = np.random.default_rng(23)
    speck = gblur(rng.random((h, w)), 0.8)
    dens = 0.75 + 0.25 * normalize(fbm(2048, rng, base=24, octaves=4)[:h, :w])
    ink = ink * dens * (speck > 0.36)
    inkc = hexc('#23150c')
    col = col * (1 - ink[..., None] * 0.92) + inkc * ink[..., None] * 0.92
    out = np.concatenate([np.clip(col, 0, 1), alpha[..., None]], -1)
    sh = drop_shadow(alpha, 6, 10, 10, 0.5)
    out = compose([(np.zeros(3), sh), (out[..., :3], alpha)], w, h)
    save_rgba(out, 'poster.png')


def paper():
    w, h = 1024, 768
    col, mid = _paper_base(w, h, 31, [(0, '#c4a676'), (0.5, '#dcc89c'), (1, '#ecdcb6')], stains=4,
                           folds=((0.5, 'v'),), foxing=200)
    alpha, dd = _torn_alpha(w, h, 32, inset=26, amp=16)
    # burnt edge: brown scorch fading into char black right at the edge
    scorch = smoothstep(34, 4, dd)
    char = smoothstep(9, 0.5, dd)
    col = col * (1 - 0.55 * scorch[..., None]) + hexc('#6a3a14') * 0.35 * scorch[..., None]
    col = col * (1 - char[..., None]) + hexc('#1a0e08') * char[..., None]
    # glowing ember specks on the very edge (subtle)
    rng = np.random.default_rng(33)
    ember = (rng.random((h, w)) > 0.985) * smoothstep(3, 0, dd) * smoothstep(-1, 0.5, dd)
    col = col + hexc('#c25a1a') * gblur(ember.astype(float), 1.0)[..., None] * 1.5
    out = compose([(np.zeros(3), drop_shadow(alpha, 5, 8, 9, 0.5)), (np.clip(col, 0, 1), alpha)], w, h)
    save_rgba(out, 'paper.png')


# =============================================================================== weapon engravings
INK = hexc('#21150d')


def _engrave(parts, w, h, ss=4, outline_px=1.6):
    """parts: list of (mask_hi, darkness_hi, period, angle). Returns RGBA at (w,h)."""
    W, H = w * ss, h * ss
    ink = np.zeros((H, W))
    union = np.zeros((H, W))
    edges = np.zeros((H, W))
    for mk, dark, period, ang in parts:
        ink = np.where(mk > 0.5, hatch_fill(mk, np.clip(dark, 0, 1), period * ss, ang), ink)
        union = np.maximum(union, mk)
        edges = np.maximum(edges, outline_of((mk > 0.5).astype(float), int(outline_px * ss * 0.9) | 1))
    edges = np.maximum(edges, outline_of((union > 0.5).astype(float), int(outline_px * ss * 1.6) | 1))
    ink = np.maximum(ink, edges)
    a = down(ink, w, h)
    rgba = np.concatenate([np.broadcast_to(INK, (h, w, 3)), a[..., None]], -1)
    return rgba


def _cyl_dark(H, W, y0, y1, base=0.12, gain=0.75, bottom_bias=0.25):
    y = np.mgrid[0:H, 0:W][0].astype(float)
    t = np.clip((y - y0) / max(y1 - y0, 1), 0, 1)
    # lit from above: light band at 25%, darker toward bottom edge
    return base + gain * np.abs(t - 0.25) ** 1.4 * 1.6 + bottom_bias * t


def bez3(p0, p1, p2, p3, k=24):
    t = np.linspace(0, 1, k)[:, None]
    P = [np.array(p, float) for p in (p0, p1, p2, p3)]
    pts = (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]
    return [tuple(p) for p in pts]


def weapon_schofield():
    """S&W Schofield, side view, muzzle right. Ink engraving on transparent."""
    w, h, ss = 512, 192, 4
    W, H = w * ss, h * ss
    yy, xx = np.mgrid[0:H, 0:W].astype(float)

    def M():
        return Mask(w, h, ss)
    parts = []
    # grip first (frame overlaps it): plow-handle curve with wood panel
    grip = bez3((150, 60), (142, 100), (122, 132), (104, 168)) + bez3((104, 168), (100, 178), (110, 186), (122, 186)) \
        + [(140, 186)] + bez3((140, 186), (146, 160), (158, 132), (176, 114)) + [(176, 104), (152, 100)]
    gm = M().poly(grip).get(True)
    gdark = 0.3 + 0.4 * np.clip((xx - 104 * ss) / (70 * ss), 0, 1) ** 0.7
    parts.append((gm, gdark, 3.0, np.radians(40)))
    panel = bez3((148, 76), (142, 104), (126, 132), (114, 164)) + bez3((114, 164), (112, 172), (118, 176), (128, 176)) \
        + bez3((136, 176), (142, 152), (152, 130), (166, 114)) + [(166, 104), (152, 96)]
    pm = M().poly(panel).get(True)
    parts.append((pm, 0.35 + 0.35 * np.clip((xx - 110 * ss) / (60 * ss), 0, 1), 2.6, np.radians(-40)))
    # barrel with top rib + front sight, ejector housing beneath
    parts.append((M().rect(220, 58, 494, 74, r=1.5).get(True), _cyl_dark(H, W, 58 * ss, 74 * ss), 3.0, 0.0))
    parts.append((M().rect(218, 53, 492, 59, r=2).poly([(478, 54), (482, 45), (489, 45), (491, 54)]).get(True),
                  np.full((H, W), 0.25), 3.0, 0.0))
    parts.append((M().rect(222, 74, 404, 83, r=4.5).get(True), _cyl_dark(H, W, 74 * ss, 83 * ss, 0.2), 2.6, 0.0))
    # frame: top strap, standing breech, bottom strap, front web sweeping into the guard
    frame = [(146, 48), (226, 48), (226, 54), (162, 54), (162, 106), (222, 106), (224, 114), (196, 116), (176, 118),
             (170, 112), (152, 100), (146, 60)]
    parts.append((M().poly(frame).get(True), 0.28 + 0.3 * yy / H, 3.0, np.radians(35)))
    # Schofield barrel catch (stirrup latch) on top of the frame
    parts.append((M().poly([(140, 50), (146, 38), (166, 38), (170, 48)]).get(True), np.full((H, W), 0.4), 2.4, np.radians(80)))
    # cylinder with two flutes
    parts.append((M().rect(162, 52, 222, 106, r=9).get(True), _cyl_dark(H, W, 52 * ss, 106 * ss, 0.1), 2.8, np.pi / 2))
    parts.append((M().rect(170, 62, 214, 70, r=4).rect(170, 88, 214, 96, r=4).get(True), np.full((H, W), 0.72), 2.2, np.pi / 2))
    # hammer: body in the frame, spur curling back
    ham = [(148, 56), (150, 44)] + bez3((150, 44), (146, 34), (136, 26), (122, 24)) + [(120, 30)] \
        + bez3((120, 30), (132, 32), (140, 42), (142, 58))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.45), 2.4, np.radians(55)))
    # trigger guard & trigger
    parts.append((M().ring(186, 130, 16, 4.5).get(True) * (yy > 114 * ss), np.full((H, W), 0.35), 2.4, 0.0))
    trig = [(184, 114), (190, 114)] + bez3((190, 114), (188, 124), (184, 132), (176, 138)) + [(178, 128)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.55), 2.2, 0.0))
    # lanyard ring & grip screw
    parts.append((M().ring(118, 188, 5, 2).get(True), np.full((H, W), 0.9), 2.0, 0.0))
    rgba = _engrave(parts, w, h, ss)
    y, x = yx(h, w)
    screw = smoothstep(3.6, 2.6, np.hypot(x - 138, y - 140)) - smoothstep(1.8, 1.0, np.hypot(x - 138, y - 140))
    rgba[..., 3] = np.maximum(rgba[..., 3], np.clip(screw, 0, 1))
    save_rgba(rgba, 'weapon_schofield.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_shotgun():
    """Double-barrel coach gun with external hammers, side view, muzzle right."""
    w, h, ss = 512, 192, 4
    W, H = w * ss, h * ss
    yy, xx = np.mgrid[0:H, 0:W].astype(float)

    def M():
        return Mask(w, h, ss)
    parts = []
    # stock: straight English grip, drop at heel, slight belly
    stock = [(200, 84)] + bez3((200, 84), (170, 88), (120, 92), (16, 96)) + [(14, 162)] \
        + bez3((14, 162), (80, 150), (140, 118), (172, 110)) + [(200, 110)]
    sm = M().poly(stock).get(True)
    sdark = 0.25 + 0.5 * np.clip((yy - 88 * ss) / (70 * ss), 0, 1) + 0.08 * np.sin(xx / (30 * ss) + yy / (50 * ss))
    parts.append((sm, sdark, 3.0, np.radians(-10)))
    parts.append((M().rect(8, 94, 16, 164, r=2).get(True), np.full((H, W), 0.7), 2.2, np.pi / 2))  # butt plate
    # checkering at the wrist
    ck = M().poly([(150, 94), (192, 88), (192, 106), (152, 112)]).get(True)
    parts.append((ck, np.full((H, W), 0.45), 2.2, np.radians(50)))
    # receiver / lock plate
    rc = [(196, 82), (256, 82), (256, 104)] + bez3((256, 104), (240, 112), (220, 114), (200, 112))
    parts.append((M().poly(rc).get(True), _cyl_dark(H, W, 82 * ss, 114 * ss, 0.2, 0.5), 2.8, np.radians(30)))
    parts.append((M().poly([(202, 88)] + bez3((202, 88), (230, 86), (246, 90), (250, 100)) + [(240, 106), (204, 106)]).get(True),
                  np.full((H, W), 0.18), 2.8, np.radians(30)))
    # twin hammers
    for dx, dk in ((8, 0.7), (0, 0.4)):
        hm = [(222 + dx, 86), (216 + dx, 84)] + bez3((216 + dx, 84), (212 + dx, 74), (204 + dx, 66), (194 + dx, 64)) \
            + [(194 + dx, 70)] + bez3((196 + dx, 70), (204 + dx, 74), (210 + dx, 82), (212 + dx, 90))
        parts.append((M().poly(hm).get(True), np.full((H, W), dk), 2.4, np.radians(70)))
    # barrels, rib, muzzle band, bead
    parts.append((M().rect(254, 84, 504, 97, r=2).get(True), _cyl_dark(H, W, 84 * ss, 97 * ss, 0.08), 3.0, 0.0))
    parts.append((M().rect(254, 80, 502, 85, r=2).poly([(496, 81), (498, 76), (501, 76), (502, 81)]).get(True),
                  np.full((H, W), 0.3), 3.0, 0.0))
    parts.append((M().rect(494, 83, 506, 98, r=2).get(True), np.full((H, W), 0.2), 2.2, np.pi / 2))
    # forend
    fe = [(256, 96), (350, 96)] + bez3((350, 96), (358, 98), (358, 104), (348, 106)) + [(262, 108)]
    parts.append((M().poly(fe).get(True), 0.3 + 0.45 * np.clip((yy - 96 * ss) / (12 * ss), 0, 1), 2.8, np.radians(-8)))
    # trigger guard + two triggers
    parts.append((M().ring(222, 124, 14, 4).get(True) * (yy > 111 * ss), np.full((H, W), 0.35), 2.2, 0.0))
    for tx in (218, 228):
        t = [(tx, 112), (tx + 4, 112)] + bez3((tx + 4, 112), (tx + 2, 120), (tx - 2, 126), (tx - 7, 130)) + [(tx - 4, 122)]
        parts.append((M().poly(t).get(True), np.full((H, W), 0.6), 2.0, 0.0))
    rgba = _engrave(parts, w, h, ss)
    save_rgba(rgba, 'weapon_shotgun.png', bg_preview=(0.86, 0.8, 0.66))


# =============================================================================== logo
def logo():
    w, h = 1600, 500
    ss = 2
    W, H = w * ss, h * ss
    left, right = 'SCH', 'FIELD'
    size = 300
    while True:  # fit the word into ~1420 px
        f = font('Rye-Regular.ttf', size * ss)
        lw, rw, ow = f.getlength(left), f.getlength(right), f.getlength('O') * 1.05
        gap = 8 * ss
        total = lw + ow + rw + 2 * gap
        if total <= 1420 * ss:
            break
        size -= 4
    x0 = (W - total) / 2
    bbH = f.getbbox('H', anchor='ls')
    base_y = 105 * ss - bbH[1]  # cap top at y=105
    from PIL import ImageDraw
    im = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(im)
    d.text((x0, base_y), left, font=f, fill=255, anchor='ls')
    d.text((x0 + lw + ow + 2 * gap, base_y), right, font=f, fill=255, anchor='ls')
    txt = np.asarray(im).astype(np.float64) / 255
    # O position: cap-height centre
    bb = f.getbbox('H', anchor='ls')
    cap_top, cap_bot = base_y + bb[1], base_y + bb[3]
    ocx = x0 + lw + gap + ow / 2
    ocy = (cap_top + cap_bot) / 2
    orad = (cap_bot - cap_top) / 2 * 1.12
    # --- lettering fill: aged gold wood-type with bevel, inline highlight, distress
    tm = down(txt, w, h)
    hgt = bevel(tm > 0.5, 9)
    y, x = yx(h, w)
    gold = ramp(normalize(1 - (y - 60) / 300) * 0.75 + 0.15, [(0, '#5a3a14'), (0.35, '#a8742c'), (0.6, '#dcae58'), (0.8, '#f6e2a0'), (1, '#fff4cf')])
    wood = noise(h, w, 41, base=8, octaves=5)
    streak = normalize(fbm(2048, np.random.default_rng(42), base=32, octaves=4, aniso=(0.15, 1))[:h, :w])
    gold *= (0.9 + 0.12 * streak + 0.06 * wood)[..., None]
    face = light(hgt, gold, scale=10, amb=0.55, spec=0.7, shin=18, spec_col=(1, 0.93, 0.7))
    inline = smoothstep(1.2, 0.2, np.abs(ndi.distance_transform_edt(tm > 0.5) - 5)) * (tm > 0.5)
    face = face * (1 - 0.35 * inline[..., None])
    rng = np.random.default_rng(43)
    distress = (gblur(rng.random((h, w)), 1.0) < 0.3) * smoothstep(0.55, 0.75, noise(h, w, 44, base=24))
    face = face * (1 - 0.45 * distress[..., None])
    # --- revolver cylinder as the 'O' (reuse the HUD art, loaded with brass)
    cyl = Image.open(os.path.join(UI_OUT, 'revolver_cylinder.png')).convert('RGBA')
    full = Image.open(os.path.join(UI_OUT, 'cyl_full.png')).convert('RGBA').resize((64, 64), Image.LANCZOS)
    c = 256 / 2 - 0.5
    for k in range(6):
        a_ = -np.pi / 2 + k * np.pi / 3
        cyl.alpha_composite(full, (int(round(c + np.cos(a_) * 76)) - 32, int(round(c + np.sin(a_) * 76)) - 32))
    osz = int(orad * 2 / ss)
    cyl = cyl.resize((osz, osz), Image.LANCZOS).rotate(8, resample=Image.BICUBIC)
    cyl_arr = np.zeros((h, w, 4))
    ox, oy = int(ocx / ss - osz / 2), int(ocy / ss - osz / 2)
    cyl_arr[oy:oy + osz, ox:ox + osz] = np.asarray(cyl).astype(np.float64) / 255
    # dark outline around everything, then shadow
    allmask = np.maximum(tm, cyl_arr[..., 3])
    ol = np.clip(ndi.grey_dilation(allmask, size=(13, 13)), 0, 1)
    ol = gblur(ol, 0.8)
    ol2 = np.clip(ndi.grey_dilation(allmask, size=(19, 19)), 0, 1)
    # --- underline flourish: rule with bullets at either end and a centre diamond
    fm = Mask(w, h, 4)
    lx0, lx1 = x0 / ss + 20, (x0 + total) / ss - 20
    ly = cap_bot / ss + 48
    fm.rect(lx0 + 40, ly - 3, lx1 - 40, ly + 3, r=3)
    fm.rect(lx0 + 60, ly + 9, lx1 - 60, ly + 11)
    for sx, dirn in ((lx0, 1), (lx1, -1)):
        # cartridge pointing outward
        fm.rect(sx + dirn * 10 - (0 if dirn > 0 else 26), ly - 8, sx + dirn * 10 + (26 if dirn > 0 else 0), ly + 8, r=2)
        tip = [(sx + dirn * 10, ly - 7)] + [(sx + dirn * 10 - dirn * 22 * np.cos(a) ** 0.8, ly + 7 * np.sin(a)) for a in np.linspace(-np.pi / 2, np.pi / 2, 15)] + [(sx + dirn * 10, ly + 7)]
        fm.poly(tip)
    cx_ = (lx0 + lx1) / 2
    fm.poly([(cx_ - 22, ly), (cx_, ly - 14), (cx_ + 22, ly), (cx_, ly + 14)])
    flo = fm.get()
    fh = bevel(flo > 0.5, 3)
    fcol = light(fh, ramp(normalize(1 - y / h) * 0.6 + 0.25, [(0, '#5a3a14'), (0.5, '#c89848'), (1, '#f6e2a0')]), scale=4, spec=0.5)
    flo_ol = np.clip(ndi.grey_dilation(flo, size=(9, 9)), 0, 1)
    shadow_src = np.maximum(ol2, flo_ol)
    layers = [(np.zeros(3), drop_shadow(shadow_src, 6, 10, 9, 0.7)),
              (hexc('#e8d3a0'), ol2 * 0.9),            # thin cream keyline (outer)
              (hexc('#2a140a'), ol),                   # dark brown outline
              (hexc('#e8d3a0'), flo_ol * 0.9), (hexc('#2a140a'), np.clip(ndi.grey_dilation(flo, size=(5, 5)), 0, 1)),
              (np.clip(fcol, 0, 1), flo),
              (np.clip(face, 0, 1), tm),
              (cyl_arr[..., :3], cyl_arr[..., 3])]
    out = compose(layers, w, h)
    save_rgba(out, 'logo.png', bg_preview=(0.3, 0.2, 0.14))


ALL = {f.__name__: f for f in (btn_fire, btn_reload, btn_swap, btn_deadeye, btn_whip, btn_brake,
                               poster, paper, weapon_schofield, weapon_shotgun, logo)}
