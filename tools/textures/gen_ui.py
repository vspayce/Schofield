"""SCHOFIELD UI art -> public/assets/ui/*.png (RGBA, @2x for retina).

usage: python3 tools/textures/gen_ui.py [name ...]   (no args = all)
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from texlib import hexc, ramp, smoothstep, to8, normalize, fbm, UI_OUT, PREVIEW
from uikit import *

BRASS = [(0, '#5a3f16'), (0.35, '#a47c34'), (0.6, '#d9b765'), (0.8, '#f4e2a0'), (1, '#b08840')]
STEEL = [(0, '#1b1e23'), (0.4, '#3a4049'), (0.7, '#687280'), (1, '#2a2f36')]


def yx(h, w):
    return np.mgrid[0:h, 0:w].astype(np.float64)


# =============================================================================== chambers
CYL_ICON = 96          # cyl_full / cyl_empty size
CYL_DISC_R = 46.5      # outer radius of the steel surround in the icon


def _chamber_surround(n, rng_seed=1):
    """Steel ring around the chamber mouth (shared by full/empty)."""
    c = n / 2
    R = radial(n, n, c - 0.5, c - 0.5, 1)
    outer = smoothstep(CYL_DISC_R + 0.7, CYL_DISC_R - 0.7, R)
    inner_r = 39.5
    ring = outer * smoothstep(inner_r - 0.7, inner_r + 0.7, R)
    # chamfer: slopes down into the hole
    hgt = np.clip((CYL_DISC_R - R) / (CYL_DISC_R - inner_r), 0, 1)
    hgt = 1 - hgt ** 2
    col = ramp(normalize(-(R * 0) + yx(n, n)[0] / n * 0.6 + yx(n, n)[1] / n * 0.4), STEEL)
    col = light(hgt * ring, col, scale=14, amb=0.55, spec=0.6, shin=30)
    return col, ring, outer, R


def cyl_full():
    n = CYL_ICON
    col, ring, outer, R = _chamber_surround(n)
    c = n / 2 - 0.5
    y, x = yx(n, n)
    ang = np.arctan2(y - c, x - c)
    # brass case head: rim, extractor groove, head, primer pocket, primer
    rim = smoothstep(40.2, 39.2, R)
    hgt = np.zeros((n, n))
    hgt += smoothstep(39.5, 36.5, R) * 0.7                      # rounded rim edge
    hgt -= (smoothstep(33.5, 32.2, R) * smoothstep(30.0, 31.3, R)) * 0.35  # headstamp groove
    hgt -= smoothstep(13.5, 12.5, R) * 0.3                      # primer pocket step
    hgt += smoothstep(12.2, 10.5, R) * 0.2                      # primer face
    # brushed/turned brass: angular streaks + radial falloff
    turn = 0.5 + 0.5 * np.sin(R * 2.3 + np.sin(ang * 3) * 0.6)
    tone = normalize(0.55 * (1 - (x + y) / (2 * n)) + 0.2 * turn * 0.3)
    brass = ramp(tone * 0.7 + 0.2, BRASS)
    primer = ramp(tone, [(0, '#6b4a2a'), (0.5, '#b87a4c'), (1, '#e7b88a')])  # copper primer
    base = np.where((R < 12.5)[..., None], primer, brass)
    shaded = light(hgt, base, scale=10, amb=0.6, spec=0.9, shin=18, spec_col=(1.0, 0.92, 0.7))
    # headstamp letters as tiny dots ring
    stamp = np.zeros((n, n))
    for k in range(10):
        a = k * np.pi / 5 + 0.3
        px, py = c + np.cos(a) * 22, c + np.sin(a) * 22
        stamp = np.maximum(stamp, smoothstep(1.6, 0.8, np.hypot(x - px, y - py)))
    shaded = shaded * (1 - 0.35 * stamp)[..., None]
    out = compose([(col, ring), (np.clip(shaded, 0, 1), rim)], n, n)
    out[..., 3] = np.clip(np.maximum(ring, rim), 0, 1)
    save_rgba(out, 'cyl_full.png')


def cyl_empty():
    n = CYL_ICON
    col, ring, outer, R = _chamber_surround(n)
    c = n / 2 - 0.5
    y, x = yx(n, n)
    hole = smoothstep(40.2, 39.2, R)
    # deep bore: darkest centre, lit wall on the far (lower-right) side like a real chamber
    wall = np.clip((R - 18) / 22, 0, 1)
    dirn = ((x - c) * 0.6 + (y - c) * 0.8) / np.maximum(R, 1)
    lit = np.clip(dirn, 0, 1) * wall ** 1.5
    bore = ramp(0.15 * wall + 0.65 * lit, [(0, '#050404'), (0.3, '#15171a'), (0.7, '#3b4048'), (1, '#6d7580')])
    # rifling hint: 5 faint lands in the wall
    ang = np.arctan2(y - c, x - c)
    rif = (0.5 + 0.5 * np.sin(ang * 5 + R * 0.25)) * wall * 0.15
    bore = bore * (1 + rif)[..., None]
    out = compose([(col, ring), (bore, hole)], n, n)
    out[..., 3] = np.clip(np.maximum(ring, hole), 0, 1)
    save_rgba(out, 'cyl_empty.png')


# =============================================================================== revolver cylinder face
CYL_N = 256
CH_R = 29.0      # chamber hole radius (transparent)
CH_ORBIT = 76.0  # chamber centre distance from cylinder centre


def revolver_cylinder():
    n = CYL_N
    c = n / 2 - 0.5
    y, x = yx(n, n)
    R = radial(n, n, c, c, 1)
    ang = np.arctan2(y - c, x - c)
    body = smoothstep(122.5, 121.0, R)
    # flutes: six scallops on the rim between chambers (Schofield cylinders are fluted)
    flutes = np.zeros((n, n))
    holes = np.zeros((n, n))
    for k in range(6):
        a = -np.pi / 2 + k * np.pi / 3
        hx, hy = c + np.cos(a) * CH_ORBIT, c + np.sin(a) * CH_ORBIT
        holes = np.maximum(holes, smoothstep(CH_R + 0.7, CH_R - 0.7, np.hypot(x - hx, y - hy)))
        fa = a + np.pi / 6
        fx, fy = c + np.cos(fa) * 128, c + np.sin(fa) * 128
        flutes = np.maximum(flutes, smoothstep(24, 22.5, np.hypot(x - fx, y - fy)))
    body = body * (1 - flutes)
    # height: domed face, chamfered outer edge, chamfered chamber mouths, centre boss & ratchet star
    hgt = 0.35 * (1 - (R / 122) ** 2)
    hgt += smoothstep(122, 114, R) * 0.3
    for k in range(6):
        a = -np.pi / 2 + k * np.pi / 3
        hx, hy = c + np.cos(a) * CH_ORBIT, c + np.sin(a) * CH_ORBIT
        d = np.hypot(x - hx, y - hy)
        hgt -= smoothstep(CH_R + 6, CH_R, d) * 0.35
    boss = smoothstep(27, 25.5, R)
    hgt += boss * 0.35
    # ratchet: 6 teeth around the boss
    tooth = (0.5 + 0.5 * np.sign(np.sin(ang * 6))) * ((ang * 6 / (2 * np.pi)) % 1)
    ratchet = smoothstep(25, 24, R) * smoothstep(12, 13, R)
    hgt += ratchet * tooth * 0.25
    pin = smoothstep(8, 7, R)
    hgt -= pin * 0.3
    # engraved ring & scrollwork dots on the face
    engr = smoothstep(1.2, 0.3, np.abs(R - 110)) + smoothstep(1.0, 0.2, np.abs(R - 46))
    for k in range(6):
        a = -np.pi / 2 + k * np.pi / 3 + np.pi / 6
        px, py = c + np.cos(a) * 100, c + np.sin(a) * 100
        engr = np.maximum(engr, smoothstep(3.2, 2.2, np.hypot(x - px, y - py)) - smoothstep(1.6, 0.8, np.hypot(x - px, y - py)))
    hgt -= engr * 0.08
    # blued steel with case-colour hints and wear on the high edges
    tone = normalize(0.6 * (1 - y / n) + 0.4 * (1 - x / n))
    blue = ramp(tone, [(0, '#0f1217'), (0.4, '#232a35'), (0.75, '#44505f'), (1, '#6d7888')])
    wear = smoothstep(112, 121, R) * 0.5 + boss * 0.2
    blue = blue * (1 - wear[..., None]) + hexc('#9aa3ad') * wear[..., None]
    blue *= (1 + 0.08 * (noise(n, n, 3, base=8) - 0.5))[..., None]
    col = light(hgt, blue, scale=40, amb=0.5, spec=0.7, shin=26, spec_col=(0.8, 0.85, 0.95))
    col = col * (1 - 0.5 * engr[..., None])
    a = body * (1 - holes)
    sh = drop_shadow(body, 3, 4, 4, 0.55)
    out = compose([(np.zeros(3), sh * (1 - holes)), (np.clip(col, 0, 1), a)], n, n)
    save_rgba(out, 'revolver_cylinder.png')
    # composite preview with chambers filled
    full = np.asarray(Image.open(os.path.join(UI_OUT, 'cyl_full.png')).resize((64, 64), Image.LANCZOS)).astype(float) / 255
    empt = np.asarray(Image.open(os.path.join(UI_OUT, 'cyl_empty.png')).resize((64, 64), Image.LANCZOS)).astype(float) / 255
    base = out.copy()
    for k in range(6):
        a_ = -np.pi / 2 + k * np.pi / 3
        hx, hy = int(round(c + np.cos(a_) * CH_ORBIT)) - 32, int(round(c + np.sin(a_) * CH_ORBIT)) - 32
        ic = full if k < 4 else empt
        reg = base[hy:hy + 64, hx:hx + 64]
        base[hy:hy + 64, hx:hx + 64] = compose([(reg[..., :3], reg[..., 3]), (ic[..., :3], ic[..., 3])], 64, 64)
    Image.fromarray(to8(base)).save(os.path.join(PREVIEW, 'ui_cylinder_loaded.png'))


# =============================================================================== shotgun shells
def _shell_shapes(w, h):
    m_hull = Mask(w, h)
    m_hull.rect(10, 14, w - 10, h - 30, r=4)
    m_crimp = Mask(w, h)
    m_crimp.rect(10, 6, w - 10, 20, r=8)
    m_brass = Mask(w, h)
    m_brass.rect(9, h - 44, w - 9, h - 10, r=3)
    m_rim = Mask(w, h)
    m_rim.rect(6, h - 14, w - 6, h - 4, r=3)
    return m_hull.get(), m_crimp.get(), m_brass.get(), m_rim.get()


def shell_full():
    w, h = 64, 128
    hull, crimp, brass, rim = _shell_shapes(w, h)
    y, x = yx(h, w)
    cyl = np.clip(1 - ((x - w / 2) / (w / 2 - 9)) ** 2, 0, 1)  # cylindrical shading term
    # red paper hull with vertical paper fibre + printed band
    fib = normalize(fbm(128, np.random.default_rng(4), base=16, octaves=4, aniso=(0.1, 1))[:h, :w])
    red = ramp(0.2 + 0.6 * cyl + 0.15 * fib, [(0, '#3a0b08'), (0.4, '#7e1a12'), (0.75, '#b8321f'), (1, '#e0735a')])
    # darker crimp top with star-crimp folds
    ang_lines = 0.5 + 0.5 * np.sin((x - w / 2) * 0.9)
    crimp_col = ramp(0.2 + 0.5 * cyl * (0.6 + 0.4 * ang_lines), [(0, '#2a0806'), (0.5, '#6e160f'), (1, '#b0402c')])
    # brass head
    brass_col = ramp(0.1 + 0.85 * cyl, BRASS)
    ridge = smoothstep(1.5, 0.5, np.abs(y - (h - 36))) * brass
    brass_col = brass_col * (1 - 0.35 * ridge[..., None])
    rim_col = ramp(0.1 + 0.8 * cyl, BRASS) * 0.85
    # paper label band (off-white) with thin rules
    band = ((y > 50) & (y < 66)).astype(float) * hull
    band_col = ramp(0.3 + 0.6 * cyl, [(0, '#6f604a'), (1, '#e8dcc0')])
    rules = (smoothstep(0.9, 0.2, np.abs(y - 52)) + smoothstep(0.9, 0.2, np.abs(y - 64))) * band
    band_col = band_col * (1 - 0.6 * rules[..., None])
    hullc = np.where(band[..., None] > 0.5, band_col, red)
    out = compose([
        (np.zeros(3), drop_shadow(np.maximum.reduce([hull, crimp, brass, rim]), 2, 3, 2.5, 0.5)),
        (hullc, hull), (crimp_col, crimp), (brass_col, brass), (rim_col, rim)], w, h)
    save_rgba(out, 'shell_full.png')


def shell_empty():
    """Empty slot: a faint engraved outline of a shell."""
    w, h = 64, 128
    hull, crimp, brass, rim = _shell_shapes(w, h)
    sil = np.maximum.reduce([hull, crimp, brass, rim])
    inner = gblur(sil, 0.1)
    from scipy import ndimage as ndi
    er = ndi.grey_erosion(sil, size=(5, 5))
    outline = np.clip(sil - er, 0, 1)
    fillc = hexc('#1a1410')
    out = compose([(fillc, sil * 0.35), (hexc('#b8a582'), outline * 0.55)], w, h)
    save_rgba(out, 'shell_empty.png')


# =============================================================================== deadeye / heart / coach / crosshair
def deadeye_icon():
    n = 128
    c = n / 2 - 0.5
    y, x = yx(n, n)
    R = radial(n, n, c, c, 1)
    # dark badge with red rim
    badge = smoothstep(61, 59.5, R)
    rimm = badge * smoothstep(52, 54, R)
    # eye shape: intersection of two circles (almond)
    d1 = np.hypot(x - c, y - (c + 30))
    d2 = np.hypot(x - c, y - (c - 30))
    eye = smoothstep(51, 49.5, d1) * smoothstep(51, 49.5, d2) * smoothstep(46, 45, np.abs(x - c))
    iris = smoothstep(19, 17.8, R)
    pupil = smoothstep(7.5, 6.5, R)
    # crosshair through pupil
    cross = ((np.abs(x - c) < 1.2) | (np.abs(y - c) < 1.2)).astype(float) * smoothstep(17, 15, R) * (1 - smoothstep(9, 8, R))
    hb = bevel(badge > 0.5, 6)
    badge_col = ramp(normalize(1 - y / n), [(0, '#120a08'), (1, '#3a1a14')])
    badge_col = light(hb, badge_col, scale=10, amb=0.6)
    rim_col = light(bevel(rimm > 0.5, 3), ramp(normalize(1 - (x + y) / (2 * n)), [(0, '#4a0c08'), (0.6, '#a8261a'), (1, '#f0806a')]), scale=6, spec=0.6)
    # eye white (bone/parchment) with red veins-glow edge
    eye_col = ramp(normalize(-np.abs(y - c) + 30), [(0, '#8a6a52'), (1, '#f2e2c4')])
    iris_col = ramp(R / 18, [(0, '#ff5a3a'), (0.6, '#c01a10'), (1, '#4a0604')])
    glow = gblur(eye, 4) * 0.9
    out = compose([
        (np.zeros(3), drop_shadow(badge, 2, 3, 3, 0.6)),
        (np.clip(badge_col, 0, 1), badge),
        (hexc('#ff3a1c'), glow * badge * (1 - eye) * 0.6),
        (np.clip(rim_col, 0, 1), rimm),
        (eye_col, eye), (iris_col, iris * eye), (hexc('#0a0202'), pupil), (hexc('#ffd0a0'), cross * 0.9)], n, n)
    save_rgba(out, 'deadeye_icon.png')


def health_heart():
    n = 128
    m = Mask(n, n)
    # playing-card heart from two circles + triangle
    m.circle(44, 48, 27).circle(84, 48, 27).poly([(18.5, 56), (109.5, 56), (64, 112)])
    mask = m.get()
    hb = bevel(mask > 0.5, 16)
    y, x = yx(n, n)
    base = ramp(normalize(1 - (y / n) * 0.8 - (x / n) * 0.2), [(0, '#3e0605'), (0.45, '#8e1510'), (0.8, '#c8281c'), (1, '#e85a40')])
    col = light(hb, base, scale=16, amb=0.55, spec=0.9, shin=30, spec_col=(1, 0.85, 0.8))
    from scipy import ndimage as ndi
    outline = np.clip(ndi.grey_dilation(mask, size=(7, 7)) - mask, 0, 1)
    out = compose([(np.zeros(3), drop_shadow(np.maximum(mask, outline), 2, 3, 3, 0.55)),
                   (hexc('#e9dcc0'), outline), (np.clip(col, 0, 1), mask)], n, n)
    save_rgba(out, 'health_heart.png')


def coach_icon():
    """Stagecoach side silhouette, light parchment fill + dark outline (tintable), 256x128, faces right."""
    w, h = 256, 128
    m = Mask(w, h)
    def bez(p0, p1, p2, k=16):
        t = np.linspace(0, 1, k)[:, None]
        return list(map(tuple, (1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + t ** 2 * np.array(p2)))
    # Concord body: flat roof, bulging egg-shaped sides and rounded belly
    body = [(66, 30), (154, 30)] + bez((154, 30), (172, 58), (150, 88)) + bez((150, 88), (110, 96), (74, 88)) \
        + bez((74, 88), (50, 58), (66, 30))
    m.poly(body)
    m.rect(62, 26, 158, 31, r=2)                       # roof edge
    m.line([(64, 26), (64, 16), (156, 16), (156, 26)], 2.5, joint=None)  # luggage rail
    m.rect(72, 16, 120, 26, r=3).rect(124, 19, 150, 26, r=2)            # luggage
    m.poly([(40, 46), (60, 42), (62, 80), (44, 76)])   # leather rear boot
    # driver box & footboard at the front top
    m.rect(152, 22, 176, 30, r=2)
    m.poly([(168, 30), (178, 28), (196, 58), (188, 62)])
    # running gear: perch, thoroughbraces, pole
    m.line([(70, 94), (176, 100)], 4)
    m.line([(170, 100), (250, 90)], 3.5)
    for cx, cy, r in ((84, 96, 28), (172, 104, 20)):
        m.ring(cx, cy, r, 4.5)
        m.circle(cx, cy, 5.5)
        for k in range(14):
            a = k * np.pi / 7
            m.line([(cx, cy), (cx + np.cos(a) * r, cy + np.sin(a) * r)], 2.2)
    mask = m.get()
    # windows/doors as cutouts
    cut = Mask(w, h)
    cut.rect(82, 40, 104, 60, r=3).rect(116, 40, 140, 60, r=3)
    cm = cut.get()
    fill = mask * (1 - cm * 0.85)
    from scipy import ndimage as ndi
    outline = np.clip(ndi.grey_dilation(fill, size=(5, 5)) - fill, 0, 1)
    out = compose([(hexc('#1a120c'), outline), (hexc('#efe3c6'), fill)], w, h)
    save_rgba(out, 'coach_icon.png')


def crosshair():
    n = 64
    c = n / 2
    m = Mask(n, n)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        m.line([(c + dx * 7, c + dy * 7), (c + dx * 17, c + dy * 17)], 2.2)
    m.circle(c, c, 2.0)
    white = m.get()
    from scipy import ndimage as ndi
    dark = np.clip(gblur(ndi.grey_dilation(white, size=(4, 4)), 0.8) * 0.8, 0, 1)
    out = compose([(hexc('#000000'), dark * 0.7), (hexc('#fff6e6'), white)], n, n)
    save_rgba(out, 'crosshair.png')


ALL = {f.__name__: f for f in (cyl_full, cyl_empty, revolver_cylinder, shell_full, shell_empty, deadeye_icon,
                               health_heart, coach_icon, crosshair)}

if __name__ == '__main__':
    import gen_ui2  # noqa: registers buttons / panels / weapons / logo
    import gen_weapons  # noqa: registers the gunsmith's nine guns
    ALL.update(gen_ui2.ALL)
    ALL.update(gen_weapons.ALL)
    for nm in sys.argv[1:] or list(ALL):
        ALL[nm]()
