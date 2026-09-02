"""
Avatar manipulation effects - pure algorithmic image transforms (no
external template images needed). Each function takes a PIL Image
(RGBA) and returns a new PIL Image.

HONEST SCOPE: this is a first batch covering the effects that are
genuinely buildable with code alone. Anything that's really a meme
TEMPLATE (drake, pooh, oogway, sadcat, wanted, patpat, bonks, gun,
calling, captcha, console, ipcam, phone, laundry, gallery, print,
billboard, cinema, tv, supreme, facts, equations) needs an actual
template image file supplied separately, and isn't here yet.
"""

from __future__ import annotations

import io
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

SIZE = 512  # avatars are resized to this before any effect runs


def _prep(img: Image.Image) -> Image.Image:
    return img.convert("RGBA").resize((SIZE, SIZE))


def _to_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGB")).astype(np.float32)


def _from_array(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


# ---------------------------------------------------------- simple filters

def fx_invert(img: Image.Image) -> Image.Image:
    img = _prep(img)
    rgb = ImageOps.invert(img.convert("RGB"))
    return rgb.convert("RGBA")


def fx_halfinvert(img: Image.Image) -> Image.Image:
    img = _prep(img)
    rgb = img.convert("RGB")
    inverted = ImageOps.invert(rgb)
    left = rgb.crop((0, 0, SIZE // 2, SIZE))
    right = inverted.crop((SIZE // 2, 0, SIZE, SIZE))
    out = Image.new("RGB", (SIZE, SIZE))
    out.paste(left, (0, 0))
    out.paste(right, (SIZE // 2, 0))
    return out.convert("RGBA")


def fx_blur(img: Image.Image) -> Image.Image:
    img = _prep(img)
    return img.filter(ImageFilter.GaussianBlur(radius=8))


def fx_neon(img: Image.Image) -> Image.Image:
    img = _prep(img)
    edges = img.convert("RGB").filter(ImageFilter.FIND_EDGES)
    edges = ImageEnhance.Color(edges).enhance(2.5)
    edges = ImageEnhance.Brightness(edges).enhance(1.8)
    return edges.convert("RGBA")


def fx_cartoon(img: Image.Image) -> Image.Image:
    img = _prep(img)
    rgb = img.convert("RGB")
    posterized = ImageOps.posterize(rgb, 3)
    edges = rgb.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p < 40 else 0)
    edges_rgb = Image.merge("RGB", (edges, edges, edges))
    out = ImageChops.subtract(posterized, ImageOps.invert(edges_rgb))
    return out.convert("RGBA")


def fx_painting(img: Image.Image) -> Image.Image:
    img = _prep(img)
    rgb = img.convert("RGB").filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.SMOOTH_MORE)
    rgb = ImageOps.posterize(rgb, 4)
    rgb = ImageEnhance.Color(rgb).enhance(1.4)
    return rgb.convert("RGBA")


def fx_lines(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    arr[::3, :, :] *= 0.55
    return _from_array(arr)


def fx_matrix(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = np.array(img.convert("L")).astype(np.float32) / 255.0
    out = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    out[:, :, 1] = gray * 255
    noise = np.random.rand(SIZE, SIZE) * 40
    out[:, :, 1] = np.clip(out[:, :, 1] + noise, 0, 255)
    return _from_array(out)


def fx_lsd(img: Image.Image) -> Image.Image:
    img = _prep(img)
    hsv = np.array(img.convert("HSV")).astype(np.int16)
    hsv[:, :, 0] = (hsv[:, :, 0] + 90) % 256
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.6, 0, 255)
    out = Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")
    return out.convert("RGBA")


def fx_gameboy(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = np.array(img.convert("L")).astype(np.float32)
    palette = np.array([[15, 56, 15], [48, 98, 48], [139, 172, 15], [155, 188, 15]])
    bucket = np.clip((gray / 255 * 3).astype(int), 0, 3)
    out = palette[bucket]
    return _from_array(out.astype(np.float32))


def fx_dither(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = img.convert("L")
    dithered = gray.convert("1")  # PIL's built-in Floyd-Steinberg dithering
    return dithered.convert("RGBA")


def fx_bayer(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = np.array(img.convert("L")).astype(np.float32) / 255
    bayer4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16
    tiled = np.tile(bayer4, (SIZE // 4 + 1, SIZE // 4 + 1))[:SIZE, :SIZE]
    out = (gray > tiled).astype(np.float32) * 255
    return _from_array(np.stack([out, out, out], axis=-1))


def fx_blocks(img: Image.Image) -> Image.Image:
    img = _prep(img)
    small = img.resize((24, 24), Image.NEAREST)
    return small.resize((SIZE, SIZE), Image.NEAREST)


def fx_tiles(img: Image.Image) -> Image.Image:
    img = _prep(img)
    tile = img.resize((SIZE // 4, SIZE // 4))
    out = Image.new("RGBA", (SIZE, SIZE))
    for x in range(4):
        for y in range(4):
            out.paste(tile, (x * SIZE // 4, y * SIZE // 4))
    return out


def fx_pattern(img: Image.Image) -> Image.Image:
    img = _prep(img)
    quarter = img.resize((SIZE // 2, SIZE // 2))
    flipped_h = ImageOps.mirror(quarter)
    flipped_v = ImageOps.flip(quarter)
    flipped_both = ImageOps.flip(flipped_h)
    out = Image.new("RGBA", (SIZE, SIZE))
    out.paste(quarter, (0, 0))
    out.paste(flipped_h, (SIZE // 2, 0))
    out.paste(flipped_v, (0, SIZE // 2))
    out.paste(flipped_both, (SIZE // 2, SIZE // 2))
    return out


# ---------------------------------------------------------- distortions

def fx_wiggle(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = np.zeros_like(arr)
    for y in range(SIZE):
        shift = int(12 * math.sin(y / 18))
        out[y] = np.roll(arr[y], shift, axis=0)
    return Image.fromarray(out)


def fx_earthquake(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = arr.copy()
    for y in range(0, SIZE, random.randint(4, 10)):
        band_h = random.randint(4, 12)
        shift = random.randint(-15, 15)
        end = min(y + band_h, SIZE)
        out[y:end] = np.roll(arr[y:end], shift, axis=1)
    return Image.fromarray(out)


def fx_glitch(img: Image.Image) -> Image.Image:
    img = _prep(img)
    r, g, b, a = img.split()
    shift = random.randint(6, 16)
    r = ImageChops.offset(r, shift, 0)
    b = ImageChops.offset(b, -shift, 0)
    out = Image.merge("RGBA", (r, g, b, a))
    arr = np.array(out)
    for _ in range(6):
        y = random.randint(0, SIZE - 20)
        h = random.randint(4, 20)
        shift = random.randint(-30, 30)
        arr[y:y + h] = np.roll(arr[y:y + h], shift, axis=1)
    return Image.fromarray(arr)


def fx_shred(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    strip_w = 16
    out = arr.copy()
    for x in range(0, SIZE, strip_w):
        shift = random.randint(-25, 25)
        out[:, x:x + strip_w] = np.roll(arr[:, x:x + strip_w], shift, axis=0)
    return Image.fromarray(out)


def fx_slice(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    strip_h = 16
    out = arr.copy()
    for y in range(0, SIZE, strip_h):
        shift = random.randint(-25, 25)
        out[y:y + strip_h] = np.roll(arr[y:y + strip_h], shift, axis=1)
    return Image.fromarray(out)


def fx_shear(img: Image.Image) -> Image.Image:
    img = _prep(img)
    coeffs = (1, 0.3, -0.15 * SIZE, 0, 1, 0)
    return img.transform((SIZE, SIZE), Image.AFFINE, coeffs, fillcolor=(0, 0, 0, 0))


def fx_stretch(img: Image.Image) -> Image.Image:
    img = _prep(img)
    stretched = img.resize((SIZE, int(SIZE * 1.6)))
    out = Image.new("RGBA", (SIZE, SIZE))
    top = (stretched.height - SIZE) // 2
    out.paste(stretched.crop((0, top, SIZE, top + SIZE)), (0, 0))
    return out


def fx_spin(img: Image.Image) -> Image.Image:
    img = _prep(img)
    layers = [img.rotate(a, resample=Image.BICUBIC) for a in range(-10, 11, 4)]
    base = Image.new("RGBA", (SIZE, SIZE))
    for i, layer in enumerate(layers):
        base = Image.blend(base.convert("RGBA"), layer, 1.0 / (i + 1))
    return base


def fx_dizzy(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy = SIZE / 2, SIZE / 2
    for y in range(SIZE):
        for x in range(0, SIZE, 2):
            dx, dy = x - cx, y - cy
            radius = math.hypot(dx, dy)
            angle = math.atan2(dy, dx) + radius / 60
            sx = int(cx + radius * math.cos(angle))
            sy = int(cy + radius * math.sin(angle))
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                out[y, x] = arr[sy, sx]
                if x + 1 < SIZE:
                    out[y, x + 1] = arr[sy, sx]
    return _from_array(out)


def fx_globe(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy, r = SIZE / 2, SIZE / 2, SIZE / 2
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = (x - cx) / r, (y - cy) / r
            dist = math.hypot(dx, dy)
            if dist < 1:
                factor = math.sin(dist * math.pi / 2) / max(dist, 1e-6)
                sx = int(cx + dx * factor * r)
                sy = int(cy + dy * factor * r)
                if 0 <= sx < SIZE and 0 <= sy < SIZE:
                    out[y, x] = arr[sy, sx]
    return _from_array(out)


def fx_warp(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy = SIZE / 2, SIZE / 2
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = (x - cx), (y - cy)
            dist = math.hypot(dx, dy) / (SIZE / 2)
            factor = 1 + 0.5 * dist
            sx = int(cx + dx / factor)
            sy = int(cy + dy / factor)
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                out[y, x] = arr[sy, sx]
    return _from_array(out)


def fx_magnify(img: Image.Image) -> Image.Image:
    img = _prep(img)
    center_crop = img.crop((SIZE // 4, SIZE // 4, 3 * SIZE // 4, 3 * SIZE // 4)).resize((SIZE, SIZE))
    return center_crop


def fx_boil(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    for y in range(SIZE):
        offset_x = int(6 * math.sin(y / 10 + random.random()))
        offset_y = int(4 * math.cos(y / 14))
        src_y = min(max(y + offset_y, 0), SIZE - 1)
        out[y] = np.roll(arr[src_y], offset_x, axis=0)
    return _from_array(out)


def fx_liquefy(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy = SIZE / 2, SIZE / 2
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            swirl = 2.5 * math.exp(-dist / 120)
            angle = math.atan2(dy, dx) + swirl
            sx = int(cx + dist * math.cos(angle))
            sy = int(cy + dist * math.sin(angle))
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                out[y, x] = arr[sy, sx]
    return _from_array(out)


def fx_flush(img: Image.Image) -> Image.Image:
    return fx_liquefy(img)  # same swirl-toward-center mechanic


def fx_drip(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = arr.copy()
    for x in range(SIZE):
        drip_amount = random.randint(0, 60)
        out[:, x] = np.roll(arr[:, x], drip_amount, axis=0)
    return Image.fromarray(out)


def fx_fall(img: Image.Image) -> Image.Image:
    return fx_drip(img)  # same downward-smear mechanic


def fx_melt(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = arr.copy()
    for x in range(SIZE):
        smear = int(30 + 20 * math.sin(x / 20))
        col = arr[:, x]
        stretched = np.repeat(col, 2, axis=0)[: SIZE + smear]
        out[:, x] = stretched[-SIZE:] if len(stretched) >= SIZE else col
    return Image.fromarray(out)


def fx_tunnel(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy = SIZE / 2, SIZE / 2
    max_r = math.hypot(cx, cy)
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            new_r = max_r - dist
            sx = int(cx + new_r * math.cos(angle))
            sy = int(cy + new_r * math.sin(angle))
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                out[y, x] = arr[sy, sx]
    return _from_array(out)


def fx_endless(img: Image.Image) -> Image.Image:
    img = _prep(img)
    layers = [img.resize((int(SIZE / (1.4 ** i)), int(SIZE / (1.4 ** i)))) for i in range(5)]
    base = img.copy()
    for i, layer in enumerate(layers):
        pos = ((SIZE - layer.width) // 2, (SIZE - layer.height) // 2)
        base.paste(layer, pos, layer)
    return base


def fx_infinity(img: Image.Image) -> Image.Image:
    return fx_endless(img)  # recursive nested-copy zoom, same idea


def fx_radiate(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    cx, cy = SIZE / 2, SIZE / 2
    for angle in range(0, 360, 6):
        rad = math.radians(angle)
        x2 = cx + SIZE * math.cos(rad)
        y2 = cy + SIZE * math.sin(rad)
        draw.line([(cx, cy), (x2, y2)], fill=90, width=2)
    base = img.convert("RGB")
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.screen(base, glow)
    return out.convert("RGBA")


def fx_shine(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    for i in range(-SIZE, SIZE, 40):
        draw.line([(i, 0), (i + SIZE, SIZE)], fill=180, width=12)
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.screen(img.convert("RGB"), glow)
    return out.convert("RGBA")


def fx_rain(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    for _ in range(150):
        x = random.randint(0, SIZE)
        y = random.randint(0, SIZE)
        length = random.randint(10, 25)
        draw.line([(x, y), (x - 4, y + length)], fill=200, width=1)
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.screen(img.convert("RGB"), glow)
    return out.convert("RGBA")


def fx_fire(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = np.array(img.convert("L")).astype(np.float32) / 255
    fire_palette_r = np.clip(gray * 2, 0, 1) * 255
    fire_palette_g = np.clip(gray * 1.3 - 0.2, 0, 1) * 180
    fire_palette_b = np.clip(gray * 0.4 - 0.3, 0, 1) * 60
    out = np.stack([fire_palette_r, fire_palette_g, fire_palette_b], axis=-1)
    return _from_array(out)


def fx_lamp(img: Image.Image) -> Image.Image:
    img = _prep(img)
    vignette = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(vignette)
    draw.ellipse((-SIZE * 0.3, -SIZE * 0.3, SIZE * 1.3, SIZE * 1.3), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(80))
    warm = ImageEnhance.Color(img.convert("RGB")).enhance(1.3)
    warm_arr = np.array(warm).astype(np.float32)
    warm_arr[:, :, 0] = np.clip(warm_arr[:, :, 0] * 1.15, 0, 255)
    warm_arr[:, :, 2] = np.clip(warm_arr[:, :, 2] * 0.8, 0, 255)
    warm = _from_array(warm_arr).convert("RGB")
    out = Image.composite(warm, Image.new("RGB", (SIZE, SIZE), (10, 5, 0)), vignette)
    return out.convert("RGBA")


def fx_reflection(img: Image.Image) -> Image.Image:
    img = _prep(img)
    top = img.resize((SIZE, SIZE // 2))
    bottom = ImageOps.flip(top).convert("RGBA")
    fade = Image.new("L", (SIZE, SIZE // 2))
    for y in range(SIZE // 2):
        fade.paste(int(200 * (1 - y / (SIZE // 2))), (0, y, SIZE, y + 1))
    bottom.putalpha(fade)
    out = Image.new("RGBA", (SIZE, SIZE), (10, 10, 10, 255))
    out.paste(top, (0, 0))
    out.paste(bottom, (0, SIZE // 2), bottom)
    return out


def fx_stereo(img: Image.Image) -> Image.Image:
    img = _prep(img)
    half = img.resize((SIZE // 2, SIZE))
    out = Image.new("RGBA", (SIZE, SIZE))
    out.paste(half, (0, 0))
    out.paste(half, (SIZE // 2, 0))
    return out


def fx_phase(img: Image.Image) -> Image.Image:
    img = _prep(img)
    r, g, b, a = img.split()
    g = ImageChops.offset(g, 8, 0)
    b = ImageChops.offset(b, -8, 8)
    return Image.merge("RGBA", (r, g, b, a))


def fx_layers(img: Image.Image) -> Image.Image:
    img = _prep(img)
    r, g, b, a = img.split()
    r = ImageChops.offset(r, -10, -10)
    b = ImageChops.offset(b, 10, 10)
    out = Image.merge("RGB", (r, g, b))
    return Image.blend(img.convert("RGB"), out, 0.6).convert("RGBA")


def fx_optics(img: Image.Image) -> Image.Image:
    return fx_globe(img)  # lens-distortion look, same spherize mechanic


def fx_bevel(img: Image.Image) -> Image.Image:
    img = _prep(img)
    emboss = img.convert("RGB").filter(ImageFilter.EMBOSS)
    return Image.blend(img.convert("RGB"), emboss, 0.6).convert("RGBA")


def fx_3d(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = img.convert("L")
    r = ImageChops.offset(gray, -6, 0)
    b = ImageChops.offset(gray, 6, 0)
    out = Image.merge("RGB", (r, gray, b))
    return out.convert("RGBA")


def fx_letters(img: Image.Image) -> Image.Image:
    img = _prep(img)
    small = img.resize((64, 64)).convert("L")
    out = Image.new("RGB", (SIZE, SIZE), "black")
    draw = ImageDraw.Draw(out)
    chars = "@%#*+=-:. "
    cell = SIZE // 64
    pixels = small.load()
    for y in range(64):
        for x in range(64):
            brightness = pixels[x, y]
            char = chars[min(len(chars) - 1, brightness * len(chars) // 256)]
            draw.text((x * cell, y * cell), char, fill=(0, 255, 70))
    return out.convert("RGBA")


def fx_knit(img: Image.Image) -> Image.Image:
    img = _prep(img)
    small = img.resize((48, 48), Image.NEAREST)
    pixelated = small.resize((SIZE, SIZE), Image.NEAREST)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    step = SIZE // 48
    for i in range(0, SIZE, step):
        draw.line([(i, 0), (i, SIZE)], fill=50, width=1)
        draw.line([(0, i), (SIZE, i)], fill=50, width=1)
    return Image.composite(Image.new("RGB", (SIZE, SIZE), "black"), pixelated.convert("RGB"), overlay).convert("RGBA")


def fx_cow(img: Image.Image) -> Image.Image:
    img = _prep(img)
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    random.seed(7)
    for _ in range(14):
        x, y = random.randint(0, SIZE), random.randint(0, SIZE)
        w, h = random.randint(60, 140), random.randint(60, 140)
        draw.ellipse((x, y, x + w, y + h), fill=255)
    black = Image.new("RGB", (SIZE, SIZE), "black")
    out = Image.composite(black, img.convert("RGB"), ImageOps.invert(mask))
    return out.convert("RGBA")


def fx_cracks(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    random.seed(3)
    for _ in range(8):
        x, y = random.randint(0, SIZE), random.randint(0, SIZE)
        for _ in range(20):
            nx = x + random.randint(-25, 25)
            ny = y + random.randint(-25, 25)
            draw.line([(x, y), (nx, ny)], fill=255, width=2)
            x, y = nx, ny
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.subtract(img.convert("RGB"), glow)
    return out.convert("RGBA")


def fx_shock(img: Image.Image) -> Image.Image:
    img = _prep(img)
    high_contrast = ImageEnhance.Contrast(img.convert("RGB")).enhance(2.2)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    x, y = random.randint(0, SIZE), 0
    while y < SIZE:
        nx = x + random.randint(-30, 30)
        ny = y + random.randint(15, 35)
        draw.line([(x, y), (nx, ny)], fill=255, width=3)
        x, y = nx, ny
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.screen(high_contrast, glow)
    return out.convert("RGBA")


def fx_soap(img: Image.Image) -> Image.Image:
    img = _prep(img)
    blurred = img.convert("RGB").filter(ImageFilter.GaussianBlur(3))
    hsv = np.array(blurred.convert("HSV")).astype(np.int16)
    hsv[:, :, 0] = (hsv[:, :, 0] + 40) % 256
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.4, 0, 255)
    out = Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")
    return out.convert("RGBA")


def fx_ads(img: Image.Image) -> Image.Image:
    img = _prep(img)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, SIZE - 40, 60, SIZE), fill=(0, 0, 0, 200))
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((6, SIZE - 32), "AD", fill=(255, 255, 255, 255), font=font)
    return img


def fx_sensitive(img: Image.Image) -> Image.Image:
    img = _prep(img)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=20))
    draw = ImageDraw.Draw(blurred)
    draw.rectangle((0, SIZE // 2 - 30, SIZE, SIZE // 2 + 30), fill=(20, 20, 20, 220))
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((SIZE // 2 - 60, SIZE // 2 - 8), "Sensitive Content", fill=(255, 255, 255, 255), font=font)
    return blurred


def fx_explicit(img: Image.Image) -> Image.Image:
    img = _prep(img)
    draw = ImageDraw.Draw(img)
    box_w, box_h = 220, 90
    x, y = (SIZE - box_w) // 2, SIZE - box_h - 20
    draw.rectangle((x, y, x + box_w, y + box_h), fill=(0, 0, 0, 255), outline=(255, 255, 255, 255), width=3)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((x + 15, y + 12), "PARENTAL", fill=(255, 255, 255, 255), font=font)
    draw.text((x + 15, y + 28), "ADVISORY", fill=(255, 255, 255, 255), font=font)
    draw.text((x + 15, y + 50), "EXPLICIT CONTENT", fill=(255, 255, 255, 255), font=font)
    return img


# ---------------------------------------------------------- batch 2

def fx_canny(img: Image.Image) -> Image.Image:
    img = _prep(img)
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = edges.point(lambda p: 255 if p > 30 else 0)
    return edges.convert("RGB").convert("RGBA")


def fx_cube(img: Image.Image) -> Image.Image:
    img = _prep(img)
    face = img.resize((SIZE // 3, SIZE // 3))
    shades = [1.0, 0.75, 0.55, 0.85, 0.65, 0.45]
    faces = []
    for shade in shades:
        arr = np.array(face).astype(np.float32)
        arr[:, :, :3] *= shade
        faces.append(_from_array(arr[:, :, :3]))
    out = Image.new("RGBA", (SIZE, SIZE), (10, 10, 10, 255))
    # cross-shaped net layout: top, left-front-right-back row, bottom
    fw = SIZE // 3
    out.paste(faces[0], (fw, 0))
    out.paste(faces[1], (0, fw))
    out.paste(faces[2], (fw, fw))
    out.paste(faces[3], (2 * fw, fw))
    out.paste(faces[4], (fw, 2 * fw))
    return out


def fx_didyoumean(img: Image.Image) -> Image.Image:
    img = _prep(img)
    canvas = Image.new("RGBA", (SIZE, SIZE + 90), (255, 255, 255, 255))
    canvas.paste(img, (0, 90))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((10, 10), "Did you mean:", fill=(80, 80, 80), font=font)
    draw.text((10, 30), "an L", fill=(30, 100, 220), font=font)
    draw.line((10, 46, 60, 46), fill=(30, 100, 220), width=1)
    return canvas


def fx_emojify(img: Image.Image) -> Image.Image:
    img = _prep(img)
    small = img.resize((16, 16))
    cell = SIZE // 16
    out = Image.new("RGBA", (SIZE, SIZE), (54, 57, 63, 255))
    draw = ImageDraw.Draw(out)
    pixels = small.convert("RGB").load()
    pad = 3
    for y in range(16):
        for x in range(16):
            color = pixels[x, y]
            x0, y0 = x * cell + pad, y * cell + pad
            x1, y1 = x0 + cell - pad * 2, y0 + cell - pad * 2
            draw.ellipse((x0, y0, x1, y1), fill=color)
    return out


def fx_fan(img: Image.Image) -> Image.Image:
    img = _prep(img)
    base = img.convert("RGBA")
    out = Image.new("RGBA", (SIZE, SIZE))
    steps = 12
    for i in range(steps):
        angle = (i - steps / 2) * 1.2
        rotated = base.rotate(angle, resample=Image.BICUBIC)
        out = Image.blend(out, rotated, 1.0 / (i + 1))
    return out


def fx_hearts(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    random.seed(11)

    def heart(cx, cy, s, color):
        pts = []
        for t_deg in range(0, 360, 6):
            t = math.radians(t_deg)
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((cx + x * s / 16, cy + y * s / 16))
        draw.polygon(pts, fill=color)

    for _ in range(9):
        cx, cy = random.randint(0, SIZE), random.randint(0, SIZE)
        size = random.randint(14, 30)
        alpha = random.randint(140, 220)
        heart(cx, cy, size, (255, 60, 100, alpha))

    out = Image.alpha_composite(img, overlay)
    return out


def fx_logoff(img: Image.Image) -> Image.Image:
    img = _prep(img)
    blue = Image.new("RGB", (SIZE, SIZE), (0, 60, 150))
    faded = Image.blend(img.convert("RGB"), blue, 0.55)
    arr = np.array(faded)
    arr[::4, :, :] = (arr[::4, :, :] * 0.7).astype(np.uint8)
    return Image.fromarray(arr).convert("RGBA")


def fx_paparazzi(img: Image.Image) -> Image.Image:
    img = _prep(img)
    dark = ImageEnhance.Brightness(img.convert("RGB")).enhance(0.6)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    random.seed(5)
    for _ in range(5):
        x, y = random.randint(0, SIZE), random.randint(0, SIZE)
        r = random.randint(40, 90)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=255)
    overlay = overlay.filter(ImageFilter.GaussianBlur(20))
    glow = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.screen(dark, glow)
    return out.convert("RGBA")


def fx_plank(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = arr.copy()
    band_h = SIZE // 10
    for i, y in enumerate(range(0, SIZE, band_h)):
        stretch = 1 + (0.15 if i % 2 == 0 else -0.1)
        band = arr[y:y + band_h]
        w = band.shape[1]
        new_w = max(1, int(w * stretch))
        band_img = Image.fromarray(band).resize((new_w, band.shape[0]))
        band_img = band_img.resize((w, band.shape[0]))
        out[y:y + band_h] = np.array(band_img)
    return Image.fromarray(out)


def fx_plates(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = np.array(img)
    out = arr.copy()
    block = SIZE // 6
    random.seed(9)
    for gy in range(0, SIZE, block):
        for gx in range(0, SIZE, block):
            dx = random.randint(-10, 10)
            dy = random.randint(-10, 10)
            src_y0, src_y1 = max(0, gy + dy), min(SIZE, gy + dy + block)
            src_x0, src_x1 = max(0, gx + dx), min(SIZE, gx + dx + block)
            patch = arr[src_y0:src_y1, src_x0:src_x1]
            h, w = patch.shape[:2]
            out[gy:gy + h, gx:gx + w] = patch
    return Image.fromarray(out)


def fx_poly(img: Image.Image) -> Image.Image:
    img = _prep(img)
    small = img.resize((32, 32), Image.BILINEAR)
    posterized = ImageOps.posterize(small.convert("RGB"), 3)
    return posterized.resize((SIZE, SIZE), Image.NEAREST).convert("RGBA")


def fx_pyramid(img: Image.Image) -> Image.Image:
    img = _prep(img)
    arr = _to_array(img)
    out = np.zeros_like(arr)
    cx, cy = SIZE / 2, SIZE / 2
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = abs(x - cx), abs(y - cy)
            level = max(dx, dy) / (SIZE / 2)
            factor = 1 - 0.3 * math.floor(level * 5) / 5
            sx = int(cx + (x - cx) * factor)
            sy = int(cy + (y - cy) * factor)
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                out[y, x] = arr[sy, sx]
    return _from_array(out)


def fx_ripped(img: Image.Image) -> Image.Image:
    img = _prep(img)
    mask = Image.new("L", (SIZE, SIZE), 255)
    draw = ImageDraw.Draw(mask)
    random.seed(13)
    pts = [(0, 0)]
    x = 0
    while x < SIZE:
        x += random.randint(15, 35)
        pts.append((min(x, SIZE), random.randint(0, 40)))
    pts += [(SIZE, 0), (SIZE, SIZE), (0, SIZE)]
    draw.polygon(pts, fill=0)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    bg = Image.new("RGBA", (SIZE, SIZE), (20, 20, 20, 255))
    bg.paste(out, (0, 0), out)
    return bg


def fx_wall(img: Image.Image) -> Image.Image:
    img = _prep(img)
    overlay = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(overlay)
    brick_w, brick_h = 64, 24
    for row, y in enumerate(range(0, SIZE, brick_h)):
        offset = brick_w // 2 if row % 2 else 0
        for x in range(-offset, SIZE, brick_w):
            draw.rectangle((x, y, x + brick_w - 4, y + brick_h - 4), outline=200, width=2)
    mortar = Image.merge("RGB", (overlay, overlay, overlay))
    out = ImageChops.subtract(img.convert("RGB"), mortar)
    return out.convert("RGBA")


def fx_zonk(img: Image.Image) -> Image.Image:
    img = _prep(img)
    inverted = ImageOps.invert(img.convert("RGB"))
    arr = np.array(inverted)
    for _ in range(10):
        y = random.randint(0, SIZE - 30)
        h = random.randint(5, 30)
        arr[y:y + h] = np.roll(arr[y:y + h], random.randint(-40, 40), axis=1)
    return Image.fromarray(arr).convert("RGBA")


def fx_equations(img: Image.Image) -> Image.Image:
    img = _prep(img)
    board = Image.new("RGB", (SIZE, SIZE + 100), (30, 60, 45))
    draw = ImageDraw.Draw(board)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    eqs = ["E=mc\u00b2", "\u222b f(x)dx", "a\u00b2+b\u00b2=c\u00b2", "F=ma", "\u2202y/\u2202x"]
    random.seed(1)
    for _ in range(14):
        x, y = random.randint(0, SIZE - 60), random.randint(0, 90)
        draw.text((x, y), random.choice(eqs), fill=(230, 230, 230), font=font)
    board.paste(img.convert("RGB"), (0, 100))
    return board.convert("RGBA")


def fx_facts(img: Image.Image) -> Image.Image:
    img = _prep(img)
    canvas = img.convert("RGBA").copy()
    draw = ImageDraw.Draw(canvas)
    colors = [(255, 0, 0), (255, 140, 0), (255, 230, 0), (0, 200, 0), (0, 120, 255), (140, 0, 200)]
    cx, cy = SIZE // 2, SIZE
    for i, color in enumerate(colors):
        r = SIZE - i * 18
        draw.arc((cx - r, cy - r, cx + r, cy + r), start=180, end=360, fill=color, width=14)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((SIZE // 2 - 60, SIZE - 40), "THE MORE YOU KNOW", fill=(255, 255, 255), font=font)
    return canvas
