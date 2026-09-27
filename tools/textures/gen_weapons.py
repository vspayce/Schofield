"""SCHOFIELD weapon engravings, part 3: the nine guns the gunsmith sells.

Same ink-engraving style as weapon_schofield / weapon_shotgun in gen_ui2.py —
side view, muzzle right, on a 512x192 transparent canvas. Drawn from the photos
in references/ (gitignored, local only). The art here is all vector, so it
regenerates without them.
Run through gen_ui.py (python3 tools/textures/gen_ui.py [name ...]).
"""
import numpy as np
from uikit import *
from gen_ui2 import _engrave, _cyl_dark, bez3

W_, H_, SS = 512, 192, 4


def _setup():
    """Canvas scaffolding shared by every gun: supersampled grids + a Mask factory."""
    W, H = W_ * SS, H_ * SS
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    return W, H, yy, xx, (lambda: Mask(W_, H_, SS))


def _wood(yy, y0, y1, dark=0.22, gain=0.5):
    """Walnut: darker toward the belly, with a slow grain wave."""
    return dark + gain * np.clip((yy - y0 * SS) / max((y1 - y0) * SS, 1), 0, 1)


# =============================================================================== revolvers
def _plow_grip(M, parts, yy, xx, back, top, butt, toe, front):
    """Colt-pattern plow handle. Points are (x, y) in canvas space."""
    g = bez3(top, (top[0] - 6, top[1] + 42), (back[0] + 14, back[1] - 34), back) \
        + bez3(back, (back[0] - 4, back[1] + 10), (back[0] + 8, butt[1]), butt) \
        + [toe] + bez3(toe, (toe[0] + 8, toe[1] - 28), (front[0] - 14, front[1] + 22), front)
    gm = M().poly(g).get(True)
    parts.append((gm, 0.28 + 0.42 * np.clip((xx - back[0] * SS) / (70 * SS), 0, 1) ** 0.7, 3.0, np.radians(40)))
    return gm


def weapon_peacemaker():
    """Colt Single Action Army: solid frame, round barrel, ejector housing, plow handle."""
    W, H, yy, xx, M = _setup()
    parts = []
    _plow_grip(M, parts, yy, xx, back=(104, 168), top=(150, 62), butt=(122, 186), toe=(142, 186), front=(178, 112))
    # chequered hard-rubber grip panel inset
    panel = bez3((146, 80), (140, 106), (126, 134), (116, 164)) + bez3((116, 164), (114, 172), (120, 176), (130, 176)) \
        + bez3((138, 176), (144, 152), (154, 130), (168, 114)) + [(168, 104), (152, 98)]
    parts.append((M().poly(panel).get(True), np.full((H, W), 0.5), 2.0, np.radians(-45)))
    # barrel: round, front sight blade at the muzzle
    parts.append((M().rect(228, 58, 496, 75, r=2).get(True), _cyl_dark(H, W, 58 * SS, 75 * SS), 3.0, 0.0))
    parts.append((M().poly([(482, 58), (486, 47), (492, 47), (493, 58)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    # ejector rod housing under the barrel, with the rod head
    parts.append((M().rect(238, 75, 424, 86, r=4).get(True), _cyl_dark(H, W, 75 * SS, 86 * SS, 0.22), 2.6, 0.0))
    parts.append((M().rect(418, 73, 436, 88, r=3).get(True), np.full((H, W), 0.42), 2.2, np.pi / 2))
    # frame: top strap over the cylinder, standing breech, lower strap into the guard
    frame = [(146, 48), (232, 48), (232, 56), (162, 56), (162, 104), (230, 104), (232, 114), (198, 117),
             (176, 118), (168, 112), (152, 100), (146, 60)]
    parts.append((M().poly(frame).get(True), 0.26 + 0.32 * yy / H, 3.0, np.radians(35)))
    # fluted cylinder
    parts.append((M().rect(166, 54, 230, 104, r=8).get(True), _cyl_dark(H, W, 54 * SS, 104 * SS, 0.1), 2.8, np.pi / 2))
    for fy in (63, 88):
        parts.append((M().rect(174, fy, 222, fy + 8, r=4).get(True), np.full((H, W), 0.74), 2.2, np.pi / 2))
    # hammer: wide chequered spur curling back over the grip
    ham = [(148, 56), (152, 42)] + bez3((152, 42), (148, 30), (136, 23), (120, 22)) + [(118, 29)] \
        + bez3((118, 29), (132, 31), (142, 40), (144, 58))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # trigger guard and trigger
    parts.append((M().ring(192, 130, 17, 4.5).get(True) * (yy > 116 * SS), np.full((H, W), 0.34), 2.4, 0.0))
    trig = [(188, 116), (195, 116)] + bez3((195, 116), (193, 126), (188, 134), (180, 140)) + [(182, 129)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.55), 2.2, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_peacemaker.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_navy():
    """Colt 1851 Navy: open-top frame, octagonal barrel, loading lever, brass guard."""
    W, H, yy, xx, M = _setup()
    parts = []
    # one-piece walnut grip: slimmer and more curved than a plow handle
    grip = bez3((158, 96), (150, 124), (128, 152), (110, 174)) + bez3((110, 174), (106, 182), (116, 188), (130, 186)) \
        + bez3((130, 186), (146, 162), (164, 134), (184, 118)) + [(184, 108), (162, 100)]
    parts.append((M().poly(grip).get(True), 0.24 + 0.44 * np.clip((xx - 108 * SS) / (72 * SS), 0, 1) ** 0.7, 3.0, np.radians(42)))
    # octagonal barrel: body plus a lit top facet and a shaded lower facet
    parts.append((M().rect(230, 54, 480, 76, r=1).get(True), _cyl_dark(H, W, 54 * SS, 76 * SS, 0.16, 0.6), 3.0, 0.0))
    parts.append((M().rect(230, 54, 478, 61, r=1).get(True), np.full((H, W), 0.2), 3.0, 0.0))
    parts.append((M().rect(230, 70, 478, 76, r=1).get(True), np.full((H, W), 0.62), 2.8, 0.0))
    parts.append((M().poly([(468, 54), (472, 45), (477, 45), (478, 54)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    # barrel lug and the wedge through it
    parts.append((M().rect(230, 76, 262, 92, r=2).get(True), np.full((H, W), 0.45), 2.6, np.radians(20)))
    parts.append((M().rect(236, 62, 244, 74, r=1).get(True), np.full((H, W), 0.8), 2.0, np.pi / 2))
    # loading lever hinged under the barrel, with its plunger and catch
    parts.append((M().rect(258, 78, 430, 88, r=4).get(True), _cyl_dark(H, W, 78 * SS, 88 * SS, 0.24), 2.6, 0.0))
    parts.append((M().poly([(424, 76), (444, 80), (444, 90), (424, 90)]).get(True), np.full((H, W), 0.45), 2.2, 0.0))
    parts.append((M().rect(262, 88, 404, 95, r=3).get(True), np.full((H, W), 0.55), 2.2, 0.0))
    # OPEN TOP: no strap over the cylinder. Frame sits below, recoil shield behind.
    parts.append((M().rect(160, 100, 238, 120, r=3).get(True), 0.28 + 0.3 * yy / H, 2.8, np.radians(35)))
    parts.append((M().circle(168, 78, 27).rect(152, 52, 176, 104).get(True), 0.3 + 0.28 * yy / H, 2.8, np.radians(-30)))
    # cylinder, naked on top, with the naval engraving band suggested
    parts.append((M().rect(172, 52, 236, 102, r=7).get(True), _cyl_dark(H, W, 52 * SS, 102 * SS, 0.1), 2.8, np.pi / 2))
    parts.append((M().rect(186, 60, 226, 94, r=3).get(True), np.full((H, W), 0.62), 2.0, np.radians(70)))
    # hammer
    ham = [(152, 56), (156, 42)] + bez3((156, 42), (152, 30), (140, 23), (124, 22)) + [(122, 29)] \
        + bez3((122, 29), (136, 31), (146, 40), (148, 58))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # brass trigger guard: squared front, long tang back along the grip
    gd = [(176, 118), (226, 118), (228, 132)] + bez3((228, 132), (222, 146), (200, 152), (182, 148)) \
        + bez3((182, 148), (190, 142), (196, 134), (196, 126)) + [(176, 126)]
    parts.append((M().poly(gd).get(True), np.full((H, W), 0.3), 2.4, np.radians(15)))
    trig = [(198, 120), (205, 120)] + bez3((205, 120), (203, 130), (198, 138), (190, 144)) + [(192, 132)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.58), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_navy.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_paterson():
    """Colt Paterson: no trigger guard, folding trigger, slender barrel, flared grip."""
    W, H, yy, xx, M = _setup()
    parts = []
    # flared grip: one long graceful sweep, no heel
    grip = bez3((186, 92), (180, 122), (162, 152), (140, 176)) \
        + bez3((140, 176), (128, 190), (144, 194), (158, 186)) \
        + bez3((158, 186), (178, 160), (196, 132), (210, 112)) + [(208, 100), (190, 94)]
    parts.append((M().poly(grip).get(True), 0.22 + 0.46 * np.clip((xx - 136 * SS) / (76 * SS), 0, 1) ** 0.7, 3.0, np.radians(46)))
    # slender octagonal barrel
    parts.append((M().rect(250, 56, 488, 72, r=1).get(True), _cyl_dark(H, W, 56 * SS, 72 * SS, 0.16, 0.6), 3.0, 0.0))
    parts.append((M().rect(250, 56, 486, 62, r=1).get(True), np.full((H, W), 0.2), 3.0, 0.0))
    parts.append((M().rect(250, 67, 486, 72, r=1).get(True), np.full((H, W), 0.6), 2.8, 0.0))
    parts.append((M().poly([(476, 56), (480, 48), (485, 48), (486, 56)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    parts.append((M().rect(250, 72, 272, 86, r=2).get(True), np.full((H, W), 0.45), 2.4, np.radians(20)))
    # long slim cylinder, roll-engraved band
    parts.append((M().rect(196, 54, 252, 98, r=6).get(True), _cyl_dark(H, W, 54 * SS, 98 * SS, 0.1), 2.8, np.pi / 2))
    parts.append((M().rect(206, 61, 244, 91, r=3).get(True), np.full((H, W), 0.62), 2.0, np.radians(70)))
    # minimal frame: a low bar under the cylinder and the standing breech
    parts.append((M().rect(190, 96, 258, 110, r=3).get(True), 0.28 + 0.3 * yy / H, 2.8, np.radians(35)))
    parts.append((M().poly([(180, 52), (196, 52), (196, 108), (182, 106), (176, 84)]).get(True), 0.3 + 0.28 * yy / H, 2.8, np.radians(-30)))
    # folding trigger: a small stub, no guard at all
    parts.append((M().poly([(214, 108), (221, 108), (218, 124), (212, 124)]).get(True), np.full((H, W), 0.55), 2.0, 0.0))
    # hammer, spur back over the grip
    ham = [(180, 56), (182, 42)] + bez3((182, 42), (176, 30), (164, 23), (150, 23)) + [(148, 30)] \
        + bez3((148, 30), (162, 32), (172, 41), (174, 58))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_paterson.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_russian():
    """S&W No. 3 Russian: top break, humped grip, spurred trigger guard."""
    W, H, yy, xx, M = _setup()
    parts = []
    # grip with the Russian hump at the top of the backstrap
    grip = bez3((156, 62), (140, 84), (136, 96), (130, 122)) + bez3((130, 122), (124, 148), (118, 164), (114, 176)) \
        + bez3((114, 176), (112, 184), (122, 188), (134, 186)) \
        + bez3((134, 186), (146, 158), (160, 130), (178, 112)) + [(178, 102), (158, 96)]
    parts.append((M().poly(grip).get(True), 0.26 + 0.42 * np.clip((xx - 114 * SS) / (68 * SS), 0, 1) ** 0.7, 3.0, np.radians(42)))
    panel = bez3((152, 82), (144, 104), (136, 128), (128, 158)) + bez3((128, 158), (126, 168), (132, 172), (142, 170)) \
        + bez3((148, 168), (156, 144), (164, 126), (172, 112)) + [(170, 102), (154, 98)]
    parts.append((M().poly(panel).get(True), np.full((H, W), 0.48), 2.2, np.radians(-42)))
    # ribbed round barrel
    parts.append((M().rect(234, 58, 478, 76, r=2).get(True), _cyl_dark(H, W, 58 * SS, 76 * SS), 3.0, 0.0))
    parts.append((M().rect(232, 52, 476, 59, r=2).poly([(462, 53), (466, 44), (472, 44), (474, 53)]).get(True),
                  np.full((H, W), 0.26), 3.0, 0.0))
    # extractor housing under the barrel
    parts.append((M().rect(236, 76, 330, 85, r=4).get(True), _cyl_dark(H, W, 76 * SS, 85 * SS, 0.22), 2.6, 0.0))
    # frame, standing breech and the top-break latch sitting behind the cylinder
    frame = [(152, 50), (182, 50), (182, 108), (226, 108), (228, 116), (196, 119), (176, 120), (166, 112), (152, 100)]
    parts.append((M().poly(frame).get(True), 0.26 + 0.32 * yy / H, 3.0, np.radians(35)))
    parts.append((M().poly([(160, 52), (166, 38), (188, 38), (192, 52)]).get(True), np.full((H, W), 0.42), 2.2, np.radians(80)))
    # cylinder
    parts.append((M().rect(182, 54, 236, 106, r=8).get(True), _cyl_dark(H, W, 54 * SS, 106 * SS, 0.1), 2.8, np.pi / 2))
    for fy in (64, 90):
        parts.append((M().rect(190, fy, 228, fy + 7, r=3).get(True), np.full((H, W), 0.74), 2.2, np.pi / 2))
    # hammer
    ham = [(156, 52), (158, 40)] + bez3((158, 40), (152, 29), (140, 22), (126, 22)) + [(124, 29)] \
        + bez3((124, 29), (138, 31), (148, 40), (150, 54))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # trigger guard with the finger spur that marks the Russian
    parts.append((M().ring(196, 132, 16, 4.5).get(True) * (yy > 118 * SS), np.full((H, W), 0.34), 2.4, 0.0))
    spur = bez3((188, 144), (182, 156), (176, 166), (170, 176)) + [(180, 174)] + bez3((180, 174), (188, 162), (194, 152), (198, 144))
    parts.append((M().poly(spur).get(True), np.full((H, W), 0.4), 2.2, np.radians(60)))
    trig = [(192, 118), (199, 118)] + bez3((199, 118), (197, 128), (192, 136), (184, 142)) + [(186, 131)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.56), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_russian.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_lightning():
    """Colt double-action: big trigger guard, wide trigger, bird's-head butt."""
    W, H, yy, xx, M = _setup()
    parts = []
    # bird's head grip: the butt swells and curls forward
    grip = bez3((152, 66), (146, 96), (134, 120), (126, 144)) \
        + bez3((126, 144), (120, 164), (126, 178), (142, 180)) \
        + bez3((142, 180), (158, 180), (166, 166), (170, 148)) \
        + bez3((170, 148), (176, 130), (180, 118), (182, 110)) + [(180, 100), (156, 96)]
    parts.append((M().poly(grip).get(True), 0.28 + 0.4 * np.clip((xx - 124 * SS) / (60 * SS), 0, 1) ** 0.7, 3.0, np.radians(40)))
    # chequered panel with the rampant-colt medallion
    panel = bez3((150, 84), (142, 108), (134, 128), (130, 146)) + bez3((130, 146), (126, 162), (132, 172), (144, 172)) \
        + bez3((144, 172), (156, 170), (162, 158), (166, 142)) + bez3((166, 142), (170, 128), (172, 116), (174, 110)) + [(172, 102), (154, 98)]
    parts.append((M().poly(panel).get(True), np.full((H, W), 0.5), 2.0, np.radians(-45)))
    parts.append((M().ring(152, 116, 9, 2.4).get(True), np.full((H, W), 0.3), 2.0, 0.0))
    # barrel + ejector housing
    parts.append((M().rect(232, 58, 492, 75, r=2).get(True), _cyl_dark(H, W, 58 * SS, 75 * SS), 3.0, 0.0))
    parts.append((M().poly([(478, 58), (482, 48), (488, 48), (489, 58)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    parts.append((M().rect(240, 75, 412, 86, r=4).get(True), _cyl_dark(H, W, 75 * SS, 86 * SS, 0.22), 2.6, 0.0))
    parts.append((M().rect(406, 73, 424, 88, r=3).get(True), np.full((H, W), 0.42), 2.2, np.pi / 2))
    # frame: top strap, and the deep side plate that houses the DA lockwork
    frame = [(150, 48), (234, 48), (234, 56), (166, 56), (166, 104), (232, 104), (234, 114), (200, 118),
             (178, 120), (168, 112), (152, 98), (150, 60)]
    parts.append((M().poly(frame).get(True), 0.26 + 0.32 * yy / H, 3.0, np.radians(35)))
    parts.append((M().circle(178, 108, 20).get(True) * (yy < 122 * SS), np.full((H, W), 0.36), 2.6, np.radians(-35)))
    # cylinder
    parts.append((M().rect(170, 54, 232, 104, r=8).get(True), _cyl_dark(H, W, 54 * SS, 104 * SS, 0.1), 2.8, np.pi / 2))
    for fy in (63, 88):
        parts.append((M().rect(178, fy, 224, fy + 8, r=4).get(True), np.full((H, W), 0.74), 2.2, np.pi / 2))
    # low hammer spur
    ham = [(152, 56), (154, 44)] + bez3((154, 44), (148, 34), (138, 29), (128, 29)) + [(127, 35)] \
        + bez3((127, 35), (137, 37), (145, 44), (147, 58))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # full-loop guard and the long double-action trigger
    parts.append((M().ring(198, 132, 20, 4.5).get(True), np.full((H, W), 0.34), 2.4, 0.0))
    trig = [(194, 118), (203, 118)] + bez3((203, 118), (202, 130), (197, 140), (189, 146)) + [(188, 133)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.56), 2.0, 0.0))
    # lanyard ring at the toe of the butt
    parts.append((M().ring(140, 184, 5, 2).get(True), np.full((H, W), 0.9), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_lightning.png', bg_preview=(0.86, 0.8, 0.66))


# =============================================================================== long guns
def _rifle_stock(M, parts, yy, comb_y=84, butt_x=14, wrist_x=196, belly_y=150, crescent=True):
    """Straight-wrist stock running back from the action to a butt plate."""
    stock = [(wrist_x, comb_y)] + bez3((wrist_x, comb_y), (150, comb_y + 2), (90, comb_y + 3), (butt_x + 12, comb_y + 6)) \
        + [(butt_x + 10, belly_y)] + bez3((butt_x + 10, belly_y), (80, belly_y - 6), (150, comb_y + 32), (wrist_x, comb_y + 28))
    sm = M().poly(stock).get(True)
    parts.append((sm, _wood(yy, comb_y, belly_y) + 0.06 * np.sin(np.mgrid[0:yy.shape[0], 0:yy.shape[1]][1] / (30 * SS)), 3.0, np.radians(-10)))
    bp = M().rect(butt_x - 4, comb_y + 4, butt_x + 10, belly_y, r=2)
    if crescent:
        bp.poly([(butt_x + 10, comb_y + 4), (butt_x + 10, belly_y), (butt_x + 20, belly_y - 6), (butt_x + 20, comb_y + 12)])
    parts.append((bp.get(True), np.full(yy.shape, 0.68), 2.2, np.pi / 2))
    return sm


def weapon_winchester():
    """Winchester 1873: lever action, tube magazine, crescent butt."""
    W, H, yy, xx, M = _setup()
    parts = []
    _rifle_stock(M, parts, yy, comb_y=78, butt_x=16, wrist_x=200, belly_y=148)
    # receiver
    parts.append((M().rect(198, 74, 292, 114, r=3).get(True), _cyl_dark(H, W, 74 * SS, 114 * SS, 0.18, 0.5), 2.8, np.radians(30)))
    parts.append((M().rect(206, 82, 268, 100, r=2).get(True), np.full((H, W), 0.2), 2.6, np.radians(30)))
    # side plate screws and the loading gate
    parts.append((M().ring(256, 104, 7, 2.2).get(True), np.full((H, W), 0.5), 2.0, 0.0))
    # barrel + magazine tube, band, front sight
    parts.append((M().rect(292, 82, 486, 95, r=2).get(True), _cyl_dark(H, W, 82 * SS, 95 * SS, 0.08), 3.0, 0.0))
    parts.append((M().rect(292, 96, 476, 107, r=4).get(True), _cyl_dark(H, W, 96 * SS, 107 * SS, 0.2), 2.6, 0.0))
    parts.append((M().rect(378, 80, 390, 109, r=2).get(True), np.full((H, W), 0.5), 2.2, np.pi / 2))
    parts.append((M().poly([(470, 82), (474, 72), (480, 72), (481, 82)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    # forend wood
    fe = [(292, 94), (376, 94)] + bez3((376, 94), (382, 96), (382, 106), (374, 108)) + [(292, 110)]
    parts.append((M().poly(fe).get(True), _wood(yy, 94, 110, 0.3, 0.42), 2.8, np.radians(-8)))
    # hammer at the rear of the receiver
    ham = [(206, 76), (208, 64)] + bez3((208, 64), (202, 54), (192, 49), (182, 49)) + [(181, 56)] \
        + bez3((181, 56), (191, 58), (199, 65), (201, 78))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # finger lever: down from the receiver into the loop
    parts.append((M().poly([(226, 112), (246, 112), (258, 128), (250, 132), (234, 118)]).get(True), np.full((H, W), 0.36), 2.4, np.radians(50)))
    parts.append((M().ring(250, 140, 15, 4.5).get(True), np.full((H, W), 0.36), 2.4, 0.0))
    trig = [(232, 114), (239, 114)] + bez3((239, 114), (237, 124), (232, 132), (226, 137)) + [(227, 126)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.56), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_winchester.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_springfield():
    """Springfield Allin conversion: trapdoor breech, full-length stock, barrel bands."""
    W, H, yy, xx, M = _setup()
    parts = []
    _rifle_stock(M, parts, yy, comb_y=80, butt_x=14, wrist_x=190, belly_y=146, crescent=False)
    # lock plate and hammer
    parts.append((M().rect(186, 84, 232, 108, r=3).get(True), _cyl_dark(H, W, 84 * SS, 108 * SS, 0.2, 0.5), 2.8, np.radians(30)))
    ham = [(206, 84), (208, 70)] + bez3((208, 70), (202, 60), (192, 55), (182, 56)) + [(181, 63)] \
        + bez3((181, 63), (191, 64), (199, 71), (201, 86))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.44), 2.4, np.radians(55)))
    # breech block: the hinged "trapdoor" sitting proud on top
    parts.append((M().rect(232, 74, 286, 90, r=2).get(True), _cyl_dark(H, W, 74 * SS, 90 * SS, 0.22, 0.5), 2.6, np.radians(25)))
    parts.append((M().rect(238, 68, 268, 76, r=2).get(True), np.full((H, W), 0.4), 2.2, np.pi / 2))
    # long barrel, rear sight ladder, front sight
    parts.append((M().rect(286, 84, 504, 95, r=2).get(True), _cyl_dark(H, W, 84 * SS, 95 * SS, 0.08), 3.0, 0.0))
    parts.append((M().rect(294, 76, 322, 84, r=1).get(True), np.full((H, W), 0.36), 2.2, 0.0))
    parts.append((M().poly([(486, 84), (489, 74), (494, 74), (496, 84)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    # full-length forend with two bands and the ramrod beneath
    fe = [(190, 94), (470, 94)] + bez3((470, 94), (478, 96), (478, 104), (468, 106)) + [(190, 110)]
    parts.append((M().poly(fe).get(True), _wood(yy, 94, 110, 0.3, 0.42), 2.8, np.radians(-8)))
    for bx in (330, 424):
        parts.append((M().rect(bx, 82, bx + 13, 110, r=2).get(True), np.full((H, W), 0.5), 2.2, np.pi / 2))
    parts.append((M().rect(230, 104, 466, 110, r=2).get(True), _cyl_dark(H, W, 104 * SS, 110 * SS, 0.3), 2.2, 0.0))
    # trigger guard
    parts.append((M().ring(212, 122, 14, 4).get(True) * (yy > 110 * SS), np.full((H, W), 0.34), 2.4, 0.0))
    trig = [(208, 110), (215, 110)] + bez3((215, 110), (213, 120), (208, 127), (202, 132)) + [(203, 121)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.56), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_springfield.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_sharps():
    """Sharps "Old Reliable": falling block, heavy barrel, lever/guard, side hammer."""
    W, H, yy, xx, M = _setup()
    parts = []
    _rifle_stock(M, parts, yy, comb_y=78, butt_x=14, wrist_x=196, belly_y=150, crescent=False)
    # receiver: the tall falling-block frame
    parts.append((M().rect(196, 72, 268, 118, r=3).get(True), _cyl_dark(H, W, 72 * SS, 118 * SS, 0.18, 0.5), 2.8, np.radians(30)))
    parts.append((M().rect(204, 80, 246, 110, r=2).get(True), np.full((H, W), 0.22), 2.6, np.radians(30)))
    # big side hammer
    ham = [(206, 74), (206, 60)] + bez3((206, 60), (198, 48), (186, 42), (172, 43)) + [(171, 52)] \
        + bez3((171, 52), (184, 53), (194, 60), (198, 76))
    parts.append((M().poly(ham).get(True), np.full((H, W), 0.42), 2.4, np.radians(55)))
    # heavy barrel, round, with the rear sight
    parts.append((M().rect(268, 80, 502, 98, r=2).get(True), _cyl_dark(H, W, 80 * SS, 98 * SS, 0.08), 3.0, 0.0))
    parts.append((M().rect(276, 71, 306, 80, r=1).get(True), np.full((H, W), 0.36), 2.2, 0.0))
    parts.append((M().poly([(484, 80), (487, 69), (493, 69), (495, 80)]).get(True), np.full((H, W), 0.3), 2.2, 0.0))
    # forend and barrel bands
    fe = [(268, 97), (444, 97)] + bez3((444, 97), (452, 99), (452, 108), (442, 110)) + [(268, 112)]
    parts.append((M().poly(fe).get(True), _wood(yy, 97, 112, 0.3, 0.42), 2.8, np.radians(-8)))
    for bx in (348, 428):
        parts.append((M().rect(bx, 78, bx + 13, 112, r=2).get(True), np.full((H, W), 0.5), 2.2, np.pi / 2))
    # the trigger guard doubles as the falling-block lever
    lever = [(212, 118), (256, 118)] + bez3((256, 118), (262, 132), (256, 144), (238, 148)) \
        + bez3((238, 148), (222, 150), (210, 142), (208, 130))
    parts.append((M().poly(lever).get(True), np.full((H, W), 0.34), 2.4, np.radians(20)))
    parts.append((M().poly([(224, 126), (250, 126)] + bez3((250, 126), (252, 134), (246, 140), (234, 141))
                           + bez3((234, 141), (224, 141), (219, 136), (219, 130))).get(True), np.full((H, W), 0.0), 2.4, 0.0))
    trig = [(226, 118), (233, 118)] + bez3((233, 118), (231, 126), (226, 132), (220, 136)) + [(221, 126)]
    parts.append((M().poly(trig).get(True), np.full((H, W), 0.56), 2.0, 0.0))
    # saddle ring on the receiver
    parts.append((M().ring(200, 110, 6, 2).get(True), np.full((H, W), 0.85), 2.0, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_sharps.png', bg_preview=(0.86, 0.8, 0.66))


def weapon_gatling():
    """Gatling gun: six-barrel cluster, brass housing, feed hopper, crank."""
    W, H, yy, xx, M = _setup()
    parts = []
    # barrel cluster: three tubes read as a round bundle in side view
    for y0, y1, dk in ((62, 78, 0.16), (78, 96, 0.08), (96, 112, 0.26)):
        parts.append((M().rect(248, y0, 496, y1, r=3).get(True), _cyl_dark(H, W, y0 * SS, y1 * SS, dk), 2.8, 0.0))
    # muzzle face and the bands clamping the cluster
    parts.append((M().rect(488, 60, 502, 114, r=4).get(True), np.full((H, W), 0.3), 2.4, np.pi / 2))
    for bx in (300, 376, 452):
        parts.append((M().rect(bx, 58, bx + 14, 116, r=3).get(True), np.full((H, W), 0.46), 2.2, np.pi / 2))
    # brass receiver housing
    parts.append((M().rect(168, 58, 252, 118, r=5).get(True), _cyl_dark(H, W, 58 * SS, 118 * SS, 0.18, 0.5), 2.8, np.radians(30)))
    parts.append((M().rect(178, 68, 240, 108, r=3).get(True), np.full((H, W), 0.24), 2.6, np.radians(30)))
    # feed hopper standing on top
    parts.append((M().poly([(186, 58), (232, 58), (226, 16), (196, 16)]).get(True), _wood(yy, 16, 58, 0.24, 0.4), 2.8, np.pi / 2))
    parts.append((M().rect(192, 14, 230, 22, r=2).get(True), np.full((H, W), 0.44), 2.2, 0.0))
    # crank: shaft, wheel and handle at the breech end
    parts.append((M().ring(150, 88, 22, 5).get(True), np.full((H, W), 0.4), 2.4, 0.0))
    parts.append((M().rect(146, 84, 172, 92, r=2).get(True), np.full((H, W), 0.42), 2.2, 0.0))
    parts.append((M().rect(128, 62, 140, 90, r=3).get(True), np.full((H, W), 0.5), 2.2, np.pi / 2))
    parts.append((M().rect(124, 54, 146, 64, r=3).get(True), _wood(yy, 54, 64, 0.3, 0.4), 2.4, 0.0))
    # trunnion yoke and elevation screw below the housing
    parts.append((M().rect(196, 118, 226, 136, r=3).get(True), np.full((H, W), 0.38), 2.4, np.radians(30)))
    parts.append((M().rect(204, 136, 218, 176, r=3).get(True), _cyl_dark(H, W, 136 * SS, 176 * SS, 0.25), 2.4, np.pi / 2))
    parts.append((M().rect(184, 174, 238, 184, r=3).get(True), np.full((H, W), 0.45), 2.2, 0.0))
    save_rgba(_engrave(parts, W_, H_, SS), 'weapon_gatling.png', bg_preview=(0.86, 0.8, 0.66))


ALL = {f.__name__: f for f in (weapon_peacemaker, weapon_navy, weapon_paterson, weapon_russian,
                               weapon_lightning, weapon_winchester, weapon_springfield, weapon_sharps,
                               weapon_gatling)}
