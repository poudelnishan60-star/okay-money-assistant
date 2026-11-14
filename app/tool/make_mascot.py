"""Cut the O-Kay mascot (with its gold glow) out of the provided Khalti screenshot.

    python make_mascot.py <screenshot.png> <out_dir>

The artwork itself is not altered: this crops a square around the glow and fades the outer
rim of the glow to transparent (it already fades to black there), so the image also sits
cleanly on surfaces that are not pure black. Outputs mascot.webp (hero) and
mascot_avatar.webp (small, for the header and message avatars).
"""
import math
import sys
from pathlib import Path

from PIL import Image

src, out_dir = sys.argv[1], Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

im = Image.open(src).convert("RGB")
# Measured on the 1290x2796 screenshot: the glow is a circle centred here.
CX, CY, R_OUT = 645, 896, 264
R_IN = 258  # the whole glow (radius ~254) and the antenna tip lie inside this radius

box = (CX - R_OUT, CY - R_OUT, CX + R_OUT, CY + R_OUT)
crop = im.crop(box).convert("RGBA")
size = crop.size[0]
px = crop.load()
c = (size - 1) / 2
for y in range(size):
    for x in range(size):
        r = math.hypot(x - c, y - c)
        if r >= R_OUT:
            a = 0
        elif r <= R_IN:
            a = 255
        else:
            a = int(255 * (R_OUT - r) / (R_OUT - R_IN))
        rr, gg, bb, _ = px[x, y]
        px[x, y] = (rr, gg, bb, a)

hero = crop  # 528 px: sharp up to 176 dp at 3x
avatar = crop.resize((168, 168), Image.LANCZOS)  # 56 dp at 3x
hero.save(out_dir / "mascot.webp", "WEBP", quality=92, method=6)
avatar.save(out_dir / "mascot_avatar.webp", "WEBP", quality=92, method=6)
hero.save(out_dir / "_preview_hero.png")
# Previews on the app's surfaces, to check the rim blends.
for name, bg in (("black", (0, 0, 0)), ("surface", (0x26, 0x26, 0x26))):
    canvas = Image.new("RGBA", (size + 60, size + 60), bg + (255,))
    canvas.alpha_composite(hero, (30, 30))
    small = Image.new("RGBA", (120, 120), bg + (255,))
    small.alpha_composite(avatar.resize((84, 84), Image.LANCZOS), (18, 18))
    canvas.alpha_composite(small, (0, 0))
    canvas.convert("RGB").save(out_dir / f"_preview_on_{name}.png")
for f in sorted(out_dir.glob("mascot*.webp")):
    print(f.name, Image.open(f).size, f"{f.stat().st_size / 1024:.1f} KB")
