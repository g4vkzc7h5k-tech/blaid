"""Free, keyless image source for ,autopfp - "cats" (TheCatAPI). The
"anime" category was removed for now - every free anime image API
tried (waifu.pics, nekos.best, waifu.im) failed from this host, most
likely a shared-IP reputation/rate-limit issue on the hosting side."""

from __future__ import annotations

import asyncio
import logging
import random

import aiohttp

log = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


async def get_cat_image() -> str | None:
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get("https://api.thecatapi.com/v1/images/search", timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    log.warning("thecatapi.com returned status %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError) as exc:
        log.warning("thecatapi.com request failed: %s", exc)
        return None
    if not data:
        return None
    return data[0].get("url")


async def get_random_image(categories: list[str]) -> str | None:
    shuffled = categories[:]
    random.shuffle(shuffled)

    for category in shuffled:
        if category == "cats":
            image = await get_cat_image()
        else:
            image = None
        if image:
            return image
    return None