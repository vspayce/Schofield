"""SCHOFIELD terrain / material textures (tiling 1024² JPG + _n normal maps).

usage: python3 tools/textures/gen_terrain.py [name ...]      (no args = all)
Writes public/assets/textures/<name>.jpg, <name>_n.jpg and previews into tools/textures/previews/.
"""
import sys
import numpy as np
from PIL import Image
from texlib import *
from strokes import WrapCanvas, splat_stones

N = 1024

# Suggested world tiling (metres per repeat) and normal strength — used for previews and reported.
META = {}


def finish(name, albedo, h, nstrength, tile_m, bake=0.3):
    """Save albedo + normal map + previews."""
    if bake:
        albedo = bake_light(albedo, h, nstrength, bake)
    save_jpg(albedo, f'{name}.jpg', 85)
    nm = normal_map(h, nstrength)
    save_jpg(nm, f'{name}_n.jpg', 90)
    tile_preview(albedo, f'{name}_2x2.jpg')
    lit_preview(albedo, h, nstrength, f'{name}_lit.jpg')
    perspective_preview(albedo, f'{name}_persp.jpg', tile_m=tile_m)
    META[name] = tile_m
    print('wrote', name)


def ao_from_height(h, s=6, k=2.0):
    """Cheap cavity AO: darker where below the local average."""
    d = h - blur(h, s)
    return np.clip(1 + k * np.minimum(d, 0) + 0.3 * k * np.maximum(d, 0), 0.3, 1.2)


# ============================================================================ dirt road
def dirt_road():
    rng = np.random.default_rng(11)
    # macro colour & height
    big = fbm(N, rng, base=3, octaves=4)
    mid = fbm(N, rng, base=12, octaves=5)
    fine = fbm(N, rng, base=64, octaves=4)
    wx = (fbm(N, rng, base=4, octaves=3) - 0.5) * 60
    wy = (fbm(N, rng, base=4, octaves=3) - 0.5) * 60
    mid = warp(mid, wx, wy)
    # wheel-rut streaks along V (image vertical): noise stretched vertically
    streak = fbm(N, rng, base=24, octaves=4, aniso=(0.08, 1.0))
    streak2 = fbm(N, rng, base=64, octaves=3, aniso=(0.05, 1.0))
    # two faint rut bands, wobbling in x
    xs = np.arange(N) / N
    wob = (fbm(N, rng, base=3, octaves=3) - 0.5) * 0.05
    X = xs[None, :] + wob
    rut = np.zeros((N, N))
    for c, w in ((0.27, 0.05), (0.73, 0.05)):
        dd = np.abs(((X - c + 0.5) % 1) - 0.5)
        rut += np.exp(-(dd / w) ** 2)
    rut *= 0.6 + 0.4 * fbm(N, rng, base=6, octaves=3, aniso=(0.3, 1))
    # dried mud cracks in patches
    pts = rng.random((900, 2))
    jit = (np.stack([fbm(N, rng, base=16, octaves=3), fbm(N, rng, base=16, octaves=3)], -1) - 0.5) * 0.012
    F1, F2, _ = voronoi(N, pts, jit)
    crack = (1 - smoothstep(0.0, 1.6, F2 - F1)) * (0.4 + 0.6 * fbm(N, rng, base=40, octaves=3))
    crackmask = smoothstep(0.62, 0.8, fbm(N, rng, base=7, octaves=4)) * (1 - 0.8 * rut)
    crack *= crackmask
    # hoof scuffs along the centre band between the ruts (crescent divots)
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    hoof = np.zeros((N, N))
    for _ in range(46):
        cx = (0.5 + rng.normal(0, 0.09)) * N
        cy = rng.random() * N
        r = rng.uniform(9, 14)
        dxk = ((xx - cx + N / 2) % N) - N / 2
        dyk = ((yy - cy + N / 2) % N) - N / 2
        m = (np.abs(dxk) < 20) & (np.abs(dyk) < 20)
        d = np.sqrt(dxk[m] ** 2 + (dyk[m] * 1.15) ** 2)
        ring = np.exp(-((d - r * 0.75) / (r * 0.28)) ** 2) * (dyk[m] > -r * 0.35) + 0.5 * (d < r * 0.8)
        hoof[m] = np.maximum(hoof[m], ring * rng.uniform(0.4, 1.0))
    hoof = blur(hoof, 1.2)
    clod_pts = rng.random((2500, 2))
    C1, C2, _ = voronoi(N, clod_pts)
    clod = smoothstep(0, 1, 1 - C1 / 12) * (fbm(N, rng, base=32, octaves=3) > 0.5)
    # height: soft undulation + ruts + streaks
    h = -0.25 * hoof + 0.05 * clod + 0.35 * big + 0.25 * mid + 0.08 * fine - 0.25 * rut + 0.08 * streak - 0.05 * crack
    # pebbles: many small, a few larger, partially buried
    H1, ID1, R1 = splat_stones(N, 3800, 1.2, 6.5, rng, bury=(0.35, 0.8), existing=np.full((N, N), -1.0))
    H2, ID2, R2 = splat_stones(N, 140, 6, 17, rng, bury=(0.45, 0.85), existing=np.full((N, N), -1.0))
    # keep pebbles out of rut centres (wheels crush / push them to the sides)
    keep = rng.random(4000)
    peb_h = np.maximum(H1, H2)
    clus = fbm(N, rng, base=6, octaves=4)
    pmask = (peb_h > 0) & ~((rut > 0.55) & (np.where(ID1 >= 0, keep[np.maximum(ID1, 0)], 1) < 0.7))
    pmask &= (np.where(ID1 >= 0, keep[np.maximum(ID1, 0)], 0) < smoothstep(0.25, 0.75, clus) * 1.1) | (H2 >= H1)
    pid = np.where(H2 >= H1, ID2 + 5000, ID1)
    prim = np.where(H2 >= H1, R2, R1)
    # soil colour: keep tile-scale contrast low (terrain shader adds macro variation) so repeats don't show
    tone = 0.5 + 0.55 * (0.35 * (big - 0.5) + 0.65 * (mid - 0.5))
    dust = ramp(tone, [(0, '#80664c'), (0.35, '#957a5c'), (0.7, '#a58a6a'), (1, '#b39a7a')])
    dust = lerp(dust, hexc('#c1aa8a'), 0.3 * smoothstep(0.3, 1.0, rut) * (0.5 + streak))  # packed, lighter ruts
    dust *= (0.9 + 0.2 * streak2)[..., None] * (0.92 + 0.16 * fine)[..., None]
    dust = lerp(dust, hexc('#6a5240'), 0.4 * crack)
    dust = lerp(dust, hexc('#6e5641'), 0.35 * hoof)
    # grain speckle
    sp = rng.random((N, N))
    dust *= (1 + 0.12 * (sp - 0.5) + 0.25 * (sp > 0.985) - 0.25 * (sp < 0.012))[..., None]
    # pebble colours
    pal = np.array([hexc(c) for c in ('#8d8173', '#a39583', '#6f655b', '#b9a88f', '#7d6a57', '#9b8a79', '#5f5750', '#c2b49c')])
    sid = np.where(pid >= 0, pid, 0)
    pc = pal[(sid * 7919) % len(pal)] * (0.85 + 0.3 * ((sid * 104729) % 97 / 97))[..., None]
    shade = (1.08 - 0.35 * prim ** 3)[..., None]
    pc = pc * shade * (0.9 + 0.2 * fine[..., None])
    alb = np.where(pmask[..., None], pc, dust)
    h2 = np.where(pmask, h + 0.18 + 0.25 * np.maximum(peb_h, 0), h)
    # dusty film over pebbles
    alb = lerp(alb, dust, 0.25)
    # contact shadows
    ao = ao_from_height(h2, 3, 1.6)
    alb = alb * ao[..., None]
    finish('dirt_road', alb, h2 * 1.0, 10.0, tile_m=4.0, bake=0.35)


# ============================================================================ grass (shared)
def grass(name, seed, soil_stops, blade_stops, thatch_stops, density=1.0, clump_blades=(10, 26),
          blade_len=(14, 44), patch_stops=None, tile_m=3.0, soil_show=1.0, alt_stops=(), alt_p=0.0,
          macro=0.45, thatch_n=26000):
    rng = np.random.default_rng(seed)
    S = N * 2  # supersample
    n = N
    big = fbm(n, rng, base=3, octaves=4)
    mid = fbm(n, rng, base=10, octaves=5)
    soil = ramp(eq(mid), soil_stops) * (0.85 + 0.3 * fbm(n, rng, base=48, octaves=4))[..., None]
    soil_img = Image.fromarray(to8(soil)).resize((S, S), Image.BILINEAR)
    cv = WrapCanvas(S, soil_img, Image.new('L', (S, S), 10))
    bigS = np.asarray(Image.fromarray(to8(big)).resize((S, S), Image.BILINEAR)) / 255.0
    midS = np.asarray(Image.fromarray(to8(mid)).resize((S, S), Image.BILINEAR)) / 255.0
    patch = patch_stops

    def colour(stops, t, x, y):
        c = ramp(np.array([t]), stops)[0]
        # macro variation
        b = bigS[int(y) % S, int(x) % S]
        m = midS[int(y) % S, int(x) % S]
        if patch is not None:
            c = c * (1 - macro * b) + ramp(np.array([m]), patch)[0] * macro * b
        c = c * (1 - macro * 0.35 + macro * 0.6 * m)
        return tuple(int(v) for v in np.clip(c * 255, 0, 255))

    def blade(x, y, ang, L, w, stops, t0, hbase, droop=0.0):
        segs = 4
        pts = [(x, y)]
        cols, hs, ws = [], [], []
        a = ang
        curl = rng.normal(0, 0.12)
        for i in range(segs):
            a += curl + droop
            x += np.cos(a) * L / segs
            y += np.sin(a) * L / segs
            pts.append((x, y))
            f = (i + 0.5) / segs
            cols.append(colour(stops, np.clip(t0 + 0.55 * f + rng.normal(0, 0.06), 0, 1), x, y))
            hs.append(hbase + f * 120)
            ws.append(w * (1 - 0.6 * f))
        cv.polyline(pts, cols, hs, ws)

    # 1) thatch: dead flat blades lying on soil
    nth = int(thatch_n * density)
    for _ in range(nth):
        x, y = rng.random() * S, rng.random() * S
        blade(x, y, rng.random() * 6.283, rng.uniform(10, 34), rng.uniform(1.6, 3.2), thatch_stops,
              rng.uniform(0.0, 0.4), 20)
    # 2) clumps (tufts seen from above: blades radiating from a crown, leaning with a shared bias)
    ncl = int(2300 * density)
    lean = rng.random() * 6.283
    for _ in range(ncl):
        cx, cy = rng.random() * S, rng.random() * S
        if midS[int(cy), int(cx)] < rng.random() * 0.5 * soil_show:  # sparser in some patches -> soil shows
            continue
        nb = rng.integers(*clump_blades)
        sc = rng.uniform(0.6, 1.25)
        la = lean + rng.normal(0, 1.2)
        cst = blade_stops
        if alt_stops and rng.random() < alt_p:
            cst = alt_stops[rng.integers(len(alt_stops))]
        for b in range(nb):
            a = rng.random() * 6.283
            # blend blade direction towards the clump lean
            a = np.arctan2(np.sin(a) + 0.8 * np.sin(la), np.cos(a) + 0.8 * np.cos(la))
            L = rng.uniform(*blade_len) * sc * 2
            blade(cx + rng.normal(0, 3), cy + rng.normal(0, 3), a, L, rng.uniform(1.8, 3.6), cst,
                  rng.uniform(0.0, 0.45), 60, droop=rng.normal(0, 0.05))
    # 3) seed heads / bright tips
    for _ in range(int(1100 * density)):
        x, y = rng.random() * S, rng.random() * S
        L = rng.uniform(6, 14)
        a = rng.random() * 6.283
        col = colour(blade_stops, rng.uniform(0.6, 0.9), x, y)
        cv.polyline([(x, y), (x + np.cos(a) * L, y + np.sin(a) * L)], [col], [230], [rng.uniform(2.5, 4.5)])
    rgb = cv.rgb.resize((n, n), Image.LANCZOS)
    hh = cv.h.resize((n, n), Image.LANCZOS)
    alb = np.asarray(rgb) / 255.0
    h = np.asarray(hh) / 255.0
    ao = ao_from_height(h, 4, 1.4)
    alb = alb * (0.82 + 0.18 * ao)[..., None]
    # gentle macro value variation (tile-scale so still tiles)
    alb *= (1 - macro * 0.15 + macro * 0.3 * big)[..., None]
    finish(name, alb, h * 0.6, 2.5, tile_m=tile_m)


def dry_grass():
    grass('dry_grass', 21,
          soil_stops=[(0, '#6e5a42'), (0.5, '#8a7455'), (1, '#a08a68')],
          blade_stops=[(0, '#7a6538'), (0.35, '#b0925a'), (0.7, '#d2b886'), (1, '#ecdcb0')],
          thatch_stops=[(0, '#806a48'), (0.5, '#a88f64'), (1, '#c8b084')],
          patch_stops=[(0, '#9a8a5a'), (0.5, '#b89e68'), (1, '#c8aa70')],
          alt_stops=([(0, '#6a6440'), (0.4, '#8f8c5c'), (0.8, '#b3ae80'), (1, '#cfc9a0')],   # grey-green
                     [(0, '#6e4a2c'), (0.4, '#9a6a40'), (0.8, '#c29460'), (1, '#dcb888')],   # russet bluestem
                     [(0, '#8a7a5a'), (0.4, '#b8a888'), (0.8, '#dcd0b4'), (1, '#f0e8d0')]),  # bleached
          alt_p=0.45, macro=0.22, thatch_n=40000, tile_m=3.0, soil_show=0.5)


def green_grass():
    grass('green_grass', 31,
          soil_stops=[(0, '#3a3522'), (0.5, '#4d4830'), (1, '#625a3c')],
          blade_stops=[(0, '#34401e'), (0.35, '#55642f'), (0.7, '#788543'), (1, '#a3a86c')],
          thatch_stops=[(0, '#56543a'), (0.5, '#76724c'), (1, '#9a9468')],
          patch_stops=[(0, '#6a7038'), (0.5, '#80803f'), (1, '#8e8a52')],
          alt_stops=([(0, '#3a4a22'), (0.4, '#5e7036'), (0.8, '#8a9a58'), (1, '#b0b880')],
                     [(0, '#4a4a26'), (0.4, '#707040'), (0.8, '#9c985e'), (1, '#c0b888')]),
          alt_p=0.4, macro=0.15, thatch_n=30000, density=1.25, tile_m=3.0, soil_show=0.2)


# ============================================================================ sand
def sand():
    rng = np.random.default_rng(41)
    big = fbm(N, rng, base=3, octaves=4)
    mid = fbm(N, rng, base=10, octaves=5)
    wx = (fbm(N, rng, base=3, octaves=4) - 0.5) * 70
    wy = (fbm(N, rng, base=3, octaves=4) - 0.5) * 70
    yy, xx = np.mgrid[0:N, 0:N] / N
    # wind ripples: integer wave vector keeps it periodic; warp for organic sinuous crests.
    # asymmetric saw profile: long gentle stoss slope, short steep lee face.
    ph = (2 * xx + 30 * yy) % 1.0
    ph = warp(np.sin(2 * np.pi * ph), wx, wy), warp(np.cos(2 * np.pi * ph), wx, wy)
    p = (np.arctan2(ph[0], ph[1]) / (2 * np.pi)) % 1.0
    saw = np.where(p < 0.78, p / 0.78, (1 - p) / 0.22)
    saw = smoothstep(0, 1, saw)
    ripstrength = 0.55 + 0.45 * smoothstep(0.2, 0.7, fbm(N, rng, base=4, octaves=3))
    grain = rng.random((N, N))
    fine = fbm(N, rng, base=128, octaves=3)
    h = 0.25 * big + 0.1 * mid + 0.22 * saw * ripstrength + 0.015 * grain
    tone = 0.5 + 0.6 * (0.4 * (big - 0.5) + 0.6 * (mid - 0.5))
    alb = ramp(tone, [(0, '#bf9a6c'), (0.4, '#cda87a'), (0.8, '#d9b88c'), (1, '#e0c49c')])
    # coarse darker grains settle in troughs; crests are finer & paler
    trough = smoothstep(0.35, 0.0, saw) * ripstrength
    alb = lerp(alb, hexc('#a98460'), 0.3 * trough)
    alb = lerp(alb, hexc('#e6cda6'), 0.15 * smoothstep(0.7, 1.0, saw))
    alb *= (0.95 + 0.08 * fine)[..., None]
    alb *= (1 + 0.16 * (grain - 0.5))[..., None]
    dark = (grain > 0.993) & (rng.random((N, N)) < 0.5 + 0.5 * trough)
    alb = np.where(dark[..., None], alb * 0.6, alb)
    H1, ID1, R1 = splat_stones(N, 220, 1.2, 4.5, rng, bury=(0.4, 0.8), existing=np.full((N, N), -1.0))
    pm = H1 > 0
    pal = np.array([hexc(c) for c in ('#8f7358', '#b39b7d', '#6e5a47', '#c7b394')])
    pc = pal[np.maximum(ID1, 0) % 4] * (1.05 - 0.3 * R1 ** 3)[..., None]
    alb = np.where(pm[..., None], pc, alb)
    h = np.where(pm, h + 0.05 + 0.1 * H1, h)
    alb *= ao_from_height(h, 3, 0.8)[..., None]
    finish('sand', alb, h, 8.0, tile_m=4.0, bake=0.35)


# ============================================================================ rock (grey granite)
def rock():
    rng = np.random.default_rng(51)
    wx = (fbm(N, rng, base=3, octaves=5) - 0.5) * 140
    wy = (fbm(N, rng, base=3, octaves=5) - 0.5) * 140
    big = warp(fbm(N, rng, base=3, octaves=7, gain=0.55), wx, wy)
    rid = warp(ridged(fbm(N, rng, base=4, octaves=7, gain=0.5)), wx * 0.6, wy * 0.6)
    # exfoliation ledges: soft terracing of the big shape
    k = 7
    terr = np.floor(big * k) / k + smoothstep(0.75, 1.0, (big * k) % 1) / k
    # a handful of long fractures: voronoi edges, most suppressed by a mask
    pts = rng.random((26, 2))
    jit = (np.stack([fbm(N, rng, base=6, octaves=5), fbm(N, rng, base=6, octaves=5)], -1) - 0.5) * 0.06
    F1, F2, idx = voronoi(N, pts, jit)
    edge = F2 - F1
    fmask = smoothstep(0.5, 0.65, fbm(N, rng, base=4, octaves=4))
    wid = 1.5 + 3 * fbm(N, rng, base=16, octaves=3)
    frac = (1 - smoothstep(0, wid, edge)) * fmask
    fracsh = (1 - smoothstep(0, wid * 4, edge)) * fmask  # shadowed margins
    # micro roughness
    micro = fbm(N, rng, base=64, octaves=5, gain=0.6)
    h = 0.35 * terr + 0.25 * big + 0.2 * rid + 0.03 * micro - 0.12 * frac - 0.05 * fracsh
    # granite colour
    tone = eq(0.5 * big + 0.3 * rid + 0.2 * micro)
    base = ramp(0.5 + 0.5 * (tone - 0.5), [(0, '#5f5c57'), (0.4, '#7a766f'), (0.75, '#928d85'), (1, '#a39e95')])
    # crystals: feldspar blobs (pinkish/cream), quartz (pale grey), biotite (black flecks)
    alb = base.copy()
    for cnt, rmin, rmax, colr, a in ((9000, 0.8, 2.6, '#b8a597', 0.55), (7000, 0.7, 2.0, '#c8c6c0', 0.5),
                                      (6000, 0.5, 1.4, '#1e1c1b', 0.7)):
        hh, ii, rr = splat_stones(N, cnt, rmin, rmax, rng, elong=0.6, bury=(0.0, 0.1),
                                  existing=np.full((N, N), -1.0))
        m = (hh > 0) * a
        alb = lerp(alb, hexc(colr) * (0.9 + 0.2 * micro)[..., None], m)
    # weathering: dark water streaks down the face, rusty iron stains, lichen spots
    streak = fbm(N, rng, base=24, octaves=4, aniso=(0.08, 1))
    smask = smoothstep(0.5, 0.8, streak) * smoothstep(0.4, 0.8, fbm(N, rng, base=3, octaves=3))
    alb = lerp(alb, hexc('#4a4642'), 0.25 * smask)
    rust = smoothstep(0.62, 0.8, fbm(N, rng, base=6, octaves=5))
    alb = lerp(alb, hexc('#857060'), 0.2 * rust)
    lich_pts = rng.random((260, 2))
    L1, _, lid = voronoi(N, lich_pts)
    lrad = (4 + 14 * rng.random(260) ** 2)[lid] * (0.8 + 0.4 * micro)
    lich = (L1 < lrad) * (rng.random(260) < 0.6)[lid] * smoothstep(0.35, 0.6, h)
    lcol = np.array([hexc('#b7b28a'), hexc('#9c9f78'), hexc('#c8a256'), hexc('#2e2c28')])[lid % 4]
    alb = lerp(alb, lcol, 0.55 * lich[..., None] * (0.7 + 0.3 * micro[..., None]))
    alb = lerp(alb, hexc('#3a3632'), 0.4 * frac)
    alb = lerp(alb, hexc('#4a4540'), 0.15 * fracsh)
    alb *= ao_from_height(h, 10, 1.0)[..., None]
    alb *= (1 + 0.1 * (rng.random((N, N)) - 0.5))[..., None]
    finish('rock', alb, h, 40.0, tile_m=6.0, bake=0.5)


# ============================================================================ red rock (sandstone strata)
def red_rock():
    rng = np.random.default_rng(61)
    # random layer stack in y, total exactly N (periodic)
    nl = 26
    th = rng.gamma(1.6, 1.0, nl) + 0.25
    th = th / th.sum() * N
    edges = np.concatenate([[0], np.cumsum(th)])
    lv = rng.random(nl)  # layer "type" 0..1
    cream = rng.random(nl) < 0.1
    hard = np.clip(rng.random(nl) * 0.8 + cream * 0.3, 0, 1)
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    wyl = (fbm(N, rng, base=3, octaves=4) - 0.5) * 36  # large gentle undulation
    wyh = (fbm(N, rng, base=24, octaves=5) - 0.5) * 12  # crumbly boundaries
    Yw = (yy + wyl + wyh + 137) % N  # offset so no bed boundary hugs the tile edge
    li = np.clip(np.searchsorted(edges, Yw, side='right') - 1, 0, nl - 1)
    fin = (Yw - edges[li]) / th[li]
    colr = ramp(lv[li], [(0, '#9c4327'), (0.3, '#ae5231'), (0.6, '#bf623a'), (0.85, '#c8744a'), (1, '#b35e3c')])
    colr = np.where(cream[li][..., None], ramp(lv[li], [(0, '#c48e68'), (1, '#d4a67e')]), colr)
    # cross-bedding laminae (anisotropic noise, tilted per layer)
    lam = fbm(N, rng, base=12, octaves=4, aniso=(3.0, 0.25))
    lamw = warp(lam, np.zeros((N, N)), (xx * 0.0))
    colr = colr * (0.92 + 0.16 * lamw)[..., None]
    colr = colr * (1.04 - 0.1 * fin)[..., None]  # lighter top of each bed
    fine = fbm(N, rng, base=64, octaves=5)
    big = fbm(N, rng, base=3, octaves=5)
    colr = colr * (0.88 + 0.24 * fine)[..., None]
    colr = lerp(colr, hexc('#d7a57c'), 0.2 * smoothstep(0.6, 0.9, big))  # bleached patches
    # height: harder beds stand proud as ledges with rounded eroded lips; soft beds recede
    lip = smoothstep(0.0, 0.25, fin) * smoothstep(1.0, 0.7, fin)
    h = 0.06 * hard[li] + 0.04 * hard[li] * lip + 0.02 * lamw + 0.02 * fine + 0.15 * big
    # vertical joints: noisy dark fissures, periodic in x
    xw = xx + (fbm(N, rng, base=6, octaves=4, aniso=(1, 0.5)) - 0.5) * 50
    joints = np.zeros((N, N))
    jsh = np.zeros((N, N))
    for jx in rng.random(2) * N:
        d = np.abs(((xw - jx + N / 2) % N) - N / 2)
        jm = smoothstep(0.3, 0.55, fbm(N, rng, base=3, octaves=3, aniso=(1, 0.3)))
        w = 4 + 10 * fine
        joints = np.maximum(joints, (1 - smoothstep(0, w, d)) * jm)
        jsh = np.maximum(jsh, (1 - smoothstep(0, w * 5, d)) * jm)
    h -= 0.05 * joints + 0.03 * jsh
    # tafoni / honeycomb pitting, mostly in the softer beds
    P1, _, pid = voronoi(N, rng.random((700, 2)))
    prad = (3 + 9 * rng.random(700))[pid]
    pit = (1 - smoothstep(0.3, 1.0, P1 / prad)) * (1 - hard[li]) * smoothstep(0.5, 0.7, fbm(N, rng, base=5, octaves=3))
    h -= 0.05 * pit
    colr = lerp(colr, hexc('#7a3a24'), 0.3 * pit)
    # desert varnish: dark streaks running down from ledges (along +row / down the face)
    streak = fbm(N, rng, base=32, octaves=5, aniso=(0.05, 1.0))
    vmask = smoothstep(0.52, 0.8, streak) * smoothstep(0.35, 0.65, fbm(N, rng, base=4, octaves=3, aniso=(0.5, 1)))
    colr = lerp(colr, hexc('#5a3024'), 0.35 * vmask)
    colr = lerp(colr, hexc('#4a2618'), 0.22 * joints)
    colr = lerp(colr, hexc('#5a2c1e'), 0.12 * jsh)
    grain = rng.random((N, N))
    colr *= (1 + 0.12 * (grain - 0.5))[..., None]
    colr *= ao_from_height(h, 6, 1.0)[..., None]
    finish('red_rock', colr, h, 40.0, tile_m=8.0, bake=0.45)


# ============================================================================ snow
def snow():
    rng = np.random.default_rng(71)
    big = fbm(N, rng, base=3, octaves=5)
    wx = (fbm(N, rng, base=3, octaves=4) - 0.5) * 100
    wy = (fbm(N, rng, base=3, octaves=4) - 0.5) * 100
    # sastrugi: elongated wind-carved ridges with sharp upwind edges
    s = warp(fbm(N, rng, base=5, octaves=6, aniso=(1, 0.3)), wx, wy)
    sast = smoothstep(0.35, 0.75, s)
    sast = np.maximum(sast - 0.6 * np.roll(sast, 6, axis=1), 0)  # sharp lee edges
    fine = fbm(N, rng, base=96, octaves=4)
    dimp = fbm(N, rng, base=24, octaves=4)
    h = 0.3 * big + 0.4 * sast + 0.15 * dimp + 0.03 * fine
    tone = normalize(h)
    alb = ramp(0.35 + 0.65 * tone, [(0, '#c3ccd8'), (0.35, '#d9dfe7'), (0.7, '#e9edf2'), (1, '#f5f7f9')])
    alb *= (0.985 + 0.03 * fine)[..., None]
    g = rng.random((N, N))
    alb = np.where((g > 0.998)[..., None], np.minimum(alb * 1.08 + 0.05, 1.0), alb)
    # rare debris: pine needles / grit
    dirt = smoothstep(0.72, 0.88, fbm(N, rng, base=8, octaves=4)) * (g < 0.012)
    alb = lerp(alb, hexc('#6b6358'), 0.55 * dirt)
    finish('snow', alb, h, 5.0, tile_m=6.0, bake=0.45)


# ============================================================================ gravel
def gravel():
    rng = np.random.default_rng(81)
    base_h = fbm(N, rng, base=6, octaves=5) * 0.2 - 0.2
    H, ID, R = splat_stones(N, 5200, 3, 12, rng, elong=0.5, bury=(0.1, 0.5), existing=base_h)
    H, ID2, R2 = splat_stones(N, 700, 9, 22, rng, elong=0.5, bury=(0.15, 0.45), existing=H)
    sid = np.where(ID2 >= 0, ID2 + 10000, ID)
    rr = np.where(ID2 >= 0, R2, R)
    pal = np.array([hexc(c) for c in ('#8a8279', '#9c948a', '#6e6760', '#7f7366', '#a9a296', '#5e5852',
                                      '#8f7c68', '#b0a898', '#736a5f', '#958a7c')])
    s = np.maximum(sid, 0)
    col = pal[(s * 7919) % len(pal)] * (0.85 + 0.3 * ((s * 104729) % 101 / 101))[..., None]
    fine = fbm(N, rng, base=96, octaves=3)
    col *= (0.9 + 0.2 * fine)[..., None]
    col *= (1.1 - 0.3 * rr ** 2)[..., None]
    soil = ramp(fbm(N, rng, base=16, octaves=4), [(0, '#3d352d'), (1, '#5e5244')])
    col = np.where((sid >= 0)[..., None], col, soil)
    col *= ao_from_height(H, 4, 2.2)[..., None]
    finish('gravel', col, H, 2.5, tile_m=2.0)


# ============================================================================ wood planks
def wood_planks():
    """Weathered, sun-bleached boards running along V (image vertical). 8 boards across the tile."""
    rng = np.random.default_rng(91)
    nplank = 8
    pw = N // nplank
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    col_i = (xx // pw).astype(int)
    u = (xx % pw) / pw
    board = np.zeros((N, N), dtype=int)
    dv = np.zeros((N, N))
    joints = []
    for c in range(nplank):
        j = rng.random() * N
        joints.append(j)
        m = col_i == c
        rel = (yy[m] - j) % N
        board[m] = c * 2 + (rel > N * 0.5 + rng.normal(0, 60)).astype(int) * 0  # one board per joint cycle
        dv[m] = np.minimum(rel, N - rel)
        # second joint for some columns (shorter boards)
    nb = nplank * 2
    btone = rng.normal(0, 1, nb)
    bshift = rng.random(nb) * 500
    bcurve = rng.normal(0, 1, nb)
    # growth rings: distance field from a (virtual) pith line far to one side, bent by knots & noise
    warpn = fbm(N, rng, base=8, octaves=5, aniso=(0.25, 1.0))
    fibre = fbm(N, rng, base=48, octaves=4, aniso=(0.03, 1.0))
    fibre2 = fbm(N, rng, base=160, octaves=2, aniso=(0.02, 1.0))
    kdx = np.zeros((N, N))
    knots = np.zeros((N, N))
    for _ in range(11):
        c = rng.integers(nplank)
        kx = c * pw + rng.uniform(0.2, 0.8) * pw
        ky = rng.random() * N
        dxk = ((xx - kx + N / 2) % N) - N / 2
        dyk = ((yy - ky + N / 2) % N) - N / 2
        rad = rng.uniform(4, 9)
        r2 = dxk ** 2 + (dyk / 1.3) ** 2
        knots = np.maximum(knots, np.exp(-r2 / rad ** 2) * (col_i == c))
        kdx += np.sign(dxk) * rad * 3 * np.exp(-r2 / (rad * 3.5) ** 2) * (col_i == c)
    ring_c = (u * pw) + kdx + 14 * warpn + bcurve[board] * 0.00002 * (yy - N / 2) ** 2 + bshift[board]
    rings = (ring_c / rng.uniform(5, 7)) % 1.0
    late = smoothstep(0.55, 0.8, rings) * smoothstep(1.0, 0.85, rings)  # darker latewood bands
    tone = np.clip(0.5 + 0.32 * btone[board], 0, 1)
    base = ramp(tone, [(0, '#5c4a3a'), (0.5, '#7b6a5a'), (1, '#9a8b7c')])
    col = base * (0.88 + 0.2 * fibre)[..., None] * (0.94 + 0.1 * fibre2)[..., None]
    col = lerp(col, hexc('#3f3024') * (0.9 + 0.2 * tone[..., None]), 0.45 * late)
    col = lerp(col, hexc('#2e2016'), 0.85 * smoothstep(0.3, 0.8, knots))
    col = lerp(col, hexc('#4a382a'), 0.4 * smoothstep(0.05, 0.3, knots))
    # silver-grey weathering, stronger near board ends; darker damp near ends
    wea = smoothstep(0.4, 0.8, fbm(N, rng, base=6, octaves=4, aniso=(0.5, 1)))
    col = lerp(col, hexc('#948e86'), 0.3 * wea)
    col = lerp(col, hexc('#4a3b2e'), 0.35 * (1 - smoothstep(0, 60, dv)))
    # checks (cracks) along grain
    ck = fbm(N, rng, base=40, octaves=3, aniso=(0.03, 1.0))
    crack = smoothstep(0.83, 0.87, ck) * smoothstep(0.45, 0.6, fbm(N, rng, base=6, octaves=2, aniso=(0.3, 1)))
    col = lerp(col, hexc('#1c140e'), 0.75 * crack)
    # gaps + rounded edges
    edgeu = np.minimum(u, 1 - u) * pw
    ed = np.minimum(edgeu, dv)
    gap = 1 - smoothstep(1.2, 3.2, ed)
    bevel = smoothstep(0, 9, ed)
    col = col * (0.72 + 0.28 * bevel)[..., None]
    col = lerp(col, hexc('#120c08'), gap)
    # square cut nails at board ends with rust bleed
    nail = np.zeros((N, N))
    rust = np.zeros((N, N))
    for c in range(nplank):
        for s_ in (-1, 1):
            for fu in (0.25, 0.75):
                ny = (joints[c] + s_ * 16) % N
                nx = c * pw + fu * pw
                ddx = ((xx - nx + N / 2) % N) - N / 2
                ddy = ((yy - ny + N / 2) % N) - N / 2
                nail = np.maximum(nail, 1 - smoothstep(2.0, 3.5, np.maximum(np.abs(ddx), np.abs(ddy))))
                rust = np.maximum(rust, np.exp(-(ddx ** 2 / 20 + np.maximum(ddy, 0) ** 2 / 400 + np.minimum(ddy, 0) ** 2 / 40)))
    col = lerp(col, hexc('#5a3a24'), 0.45 * rust)
    col = lerp(col, hexc('#2a2422'), nail)
    h = 0.5 * bevel + 0.08 * fibre + 0.05 * late - 0.3 * crack - 0.6 * gap - 0.15 * knots * 0 + 0.04 * btone[board] + 0.2 * nail
    col *= (1 + 0.05 * (rng.random((N, N)) - 0.5))[..., None]
    finish('wood_planks', col, h, 12.0, tile_m=2.0, bake=0.35)


ALL = {f.__name__: f for f in (dirt_road, dry_grass, green_grass, sand, rock, red_rock, snow, gravel, wood_planks)}

if __name__ == '__main__':
    names = sys.argv[1:] or list(ALL)
    for nme in names:
        ALL[nme]()
