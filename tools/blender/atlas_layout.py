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
# filled in by town_textures.py / build_town.py
TOWN = {}
