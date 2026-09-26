"""Contact sheet of UI PNGs on a dark HUD-ish background (preview only)."""
import sys, os
from PIL import Image
from texlib import UI_OUT, PREVIEW
names = sys.argv[2:]
scale = float(sys.argv[1])
ims = [Image.open(os.path.join(UI_OUT, n)).convert('RGBA') for n in names]
ims = [i.resize((int(i.width * scale), int(i.height * scale)), Image.LANCZOS) for i in ims]
W = sum(i.width for i in ims) + 20 * (len(ims) + 1)
H = max(i.height for i in ims) + 40
bg = Image.new('RGBA', (W, H), (70, 58, 44, 255))
# half the sheet on a light background to check both
bg.paste((200, 185, 160, 255), (0, H // 2, W, H))
x = 20
for i in ims:
    bg.alpha_composite(i, (x, 20))
    x += i.width + 20
bg.convert('RGB').save(os.path.join(PREVIEW, 'sheet.png'))
