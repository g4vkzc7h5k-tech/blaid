"""
,color - extracts a member's average avatar color, or parses a hex
code directly, and renders a solid-color swatch image.

Needs Pillow (added to requirements.txt) - if not installed on the
host yet, this will ImportError; run a fresh pip install from
requirements.txt after deploying this.
"""

from __future__ import annotations

import asyncio
import io

import aiohttp
from PIL import Image

WEBSAFE_STEPS = [0, 51, 102, 153, 204, 255]


async def get_average_color(avatar_url: str) -> tuple[int, int, int] | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        small = image.resize((1, 1))
        r, g, b = small.getpixel((0, 0))
        return (r, g, b)
    except Exception:
        return None


def make_swatch_image(rgb: tuple[int, int, int], width: int = 600, height: int = 150) -> io.BytesIO:
    image = Image.new("RGB", (width, height), rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def nearest_websafe(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    def snap(value: int) -> int:
        return min(WEBSAFE_STEPS, key=lambda step: abs(step - value))

    return (snap(rgb[0]), snap(rgb[1]), snap(rgb[2]))