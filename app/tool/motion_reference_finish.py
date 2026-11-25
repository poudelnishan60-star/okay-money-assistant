"""After `flutter test tool/motion_reference_test.dart`: trims the empty space under the tall
pages and writes contact.png, one sheet with every screen, to ../motion-reference/.

    python tool/motion_reference_finish.py      (needs Pillow; backend/.venv has it)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[2] / "motion-reference"


def trim_bottom(path: Path, margin: int = 96) -> None:
    """Cut the rows under the content that are all the page's background colour."""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    bg = img.getpixel((w // 2, h - 1))
    px = img.load()
    bottom = h - 1
    while bottom > 0 and all(px[x, bottom] == bg for x in range(0, w, 3)):
        bottom -= 1
    if bottom < h - 1:
        img.crop((0, 0, w, min(h, bottom + margin))).save(path)


def contact_sheet() -> None:
    shots = sorted((OUT / "screens").glob("*.png"))
    cols, thumb_w = 6, 360
    thumb_h = round(thumb_w * 2556 / 1179)
    label_h = 44
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (thumb_w + 24) + 24, rows * (thumb_h + label_h + 24) + 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for i, shot in enumerate(shots):
        x = 24 + (i % cols) * (thumb_w + 24)
        y = 24 + (i // cols) * (thumb_h + label_h + 24)
        img = Image.open(shot).convert("RGB")
        img.thumbnail((thumb_w, thumb_h))
        sheet.paste(img, (x, y))
        draw.text((x, y + thumb_h + 10), shot.stem, fill=(200, 200, 200), font=font)
    sheet.save(OUT / "contact.png")


if __name__ == "__main__":
    for tall in sorted((OUT / "tall").glob("*.png")):
        trim_bottom(tall)
    contact_sheet()
    for folder in ("screens", "tall", "parts"):
        files = sorted((OUT / folder).glob("*.png"))
        sizes = {Image.open(f).size for f in files}
        print(f"{folder}: {len(files)} images", "" if len(sizes) > 3 else sorted(sizes))
    print("contact sheet:", OUT / "contact.png")
