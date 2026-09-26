"""Atlas rectangles shared by the texture generators (system python) and the Blender
builders. Rects are (x, y, w, h) in pixels, y measured DOWN from the image top."""

PROPS_SIZE = (1024, 1024)
# Opaque props atlas (JPEG)
PROPS = {
    'rock_sand':    (0,   0,   512, 512),
    'rock_granite': (512, 0,   512, 512),
    'bark_pond':    (0,   512, 128, 512),
    'bark_fir':     (128, 512, 128, 256),
    'deadwood':     (128, 768, 128, 256),
    'saguaro':      (256, 512, 128, 512),
    'signs':        (384, 512, 128, 512),   # text boards, written rotated 90deg (read bottom->top)
    'wood_grey':    (512, 512, 256, 256),   # plain grain, grain runs along v
    'planks':       (768, 512, 256, 256),   # 5 boards with gaps + nails, boards run along v
    'wood_brown':   (512, 768, 256, 256),
    'planks_stencil': (768, 768, 256, 128), # crate side with stencil, boards along u
    'metal_rust':   (768, 896, 128, 128),
    'bone':         (896, 896, 128, 128),
}
# sign boards inside 'signs' (each a column; text runs along v)
SIGN_TEXTS = ['PERDITION', 'DRY CREEK', 'SILVER NOTCH']

FOLIAGE_SIZE = (1024, 1024)
FOLIAGE = {
    'pond_a':    (0,   0,   512, 512),
    'pond_b':    (512, 0,   512, 512),
    'fir':       (0,   512, 512, 256),
    'fir_snow':  (0,   768, 512, 256),
    'sage':      (512, 512, 256, 256),
    'joshua':    (768, 512, 256, 256),
    'tumble':    (512, 768, 256, 256),
    'twigs':     (768, 768, 256, 256),
}

TOWN_SIZE = (1024, 1024)
# Town atlas (JPEG). Tiling regions state the metres they represent in build_town.py.
TOWN = {
    'siding_grey':   (0,   0,   256, 384),   # vertical board-and-batten, 2 m x 3 m
    'siding_red':    (256, 0,   256, 384),   # faded barn-red paint, peeling
    'siding_ochre':  (512, 0,   256, 384),   # faded ochre/cream paint, peeling
    'clapboard':     (768, 0,   256, 384),   # horizontal lap siding, peeling white, 2 m x 3 m
    'shingle':       (0,   384, 256, 256),   # wood shingles, 2 m x 2 m (v = up the slope)
    'tin':           (256, 384, 256, 256),   # corrugated rusty tin, 2 m x 2 m (ribs along v)
    'floor':         (512, 384, 256, 256),   # deck boards along u, 2 m x 2 m
    'brick':         (768, 384, 256, 256),   # 2 m x 2 m
    'trim':          (0,   640, 128, 384),   # beam/post grain along v
    'signs':         (128, 640, 512, 384),   # 6 signs, 512 x 64 each (top to bottom = TOWN_SIGNS)
    'win_glass':     (640, 640, 96,  128),
    'win_broken':    (736, 640, 96,  128),
    'win_boarded':   (832, 640, 96,  128),
    'win_open':      (928, 640, 96,  128),
    'door_panel':    (640, 768, 96,  256),
    'door_saloon':   (736, 768, 96,  256),
    'door_barn':     (832, 768, 128, 256),
    'dark':          (960, 768, 64,  128),
    'iron':          (960, 896, 64,  64),
    'rope':          (960, 960, 64,  64),
}
TOWN_SIGNS = ['SALOON', 'GENERAL STORE', 'SHERIFF', 'BANK', 'HOTEL', 'LIVERY']
