"""
,bible - fetches a random verse from bible-api.com (free, no signup,
no API key, default World English Bible translation).

HONEST GAP: the docs for the /data/{translation}/random endpoint don't
show a literal example JSON response (unlike the reference-lookup
endpoint, which does), so the exact field names below are my best
guess based on the site's other /data/ endpoints, not confirmed
against a real response. If this comes back empty or wrong, the
actual JSON shape is the first thing to check - send me a traceback
or the raw response and I'll fix the field names.
"""

from __future__ import annotations

import asyncio

import aiohttp

RANDOM_VERSE_URL = "https://bible-api.com/data/web/random"


async def get_random_verse() -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(RANDOM_VERSE_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    verse = data.get("random_verse") or data.get("verse") or data
    translation = data.get("translation") or {}

    book = verse.get("book") or verse.get("book_name")
    chapter = verse.get("chapter")
    verse_number = verse.get("verse")
    text = verse.get("text")

    if not text:
        return None

    if book and chapter and verse_number:
        reference = f"{book} {chapter}:{verse_number}"
    else:
        reference = verse.get("reference") or data.get("reference") or "Unknown Reference"

    translation_name = translation.get("name") or data.get("translation_name") or "World English Bible"

    return {
        "text": text.strip(),
        "reference": reference,
        "translation_name": translation_name,
    }