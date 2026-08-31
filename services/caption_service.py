"""
,caption - adds a white bar with bold black text above an image
(classic meme-caption style, text goes ABOVE the image, not overlaid
on it).

HONEST GAP: for an animated GIF, this only captions the FIRST FRAME
and returns a static PNG - captioning every frame of an animated GIF
is a much bigger undertaking (per-frame redraw + re-encoding), not
done here.

Needs Pillow (already a dependency, added earlier for ,color).
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # No bundled/system bold font found - falls back to PIL's tiny
    # built-in font, which won't look like a real meme caption. Bundle
    # a .ttf in the repo and point _FONT_PATHS at it for a real fix.
    return ImageFont.load_default()


def build_caption_image(image_bytes: bytes, text: str) -> io.BytesIO | None:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    width, height = image.size
    font = _load_font(max(24, width // 12))
    draw_probe = ImageDraw.Draw(image)

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw_probe.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width - 20 and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    if not lines:
        lines = [""]

    line_bbox = font.getbbox("Ay")
    line_height = (line_bbox[3] - line_bbox[1]) + 10
    bar_height = line_height * len(lines) + 20

    new_image = Image.new("RGB", (width, height + bar_height), "white")
    new_image.paste(image, (0, bar_height))

    draw = ImageDraw.Draw(new_image)
    y = 10
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = max(0, (width - line_width) // 2)
        draw.text((x, y), line, font=font, fill="black")
        y += line_height

    buffer = io.BytesIO()
    new_image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer