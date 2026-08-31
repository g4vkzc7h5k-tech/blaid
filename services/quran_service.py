"""
,quran - fetches a random ayah from api.alquran.cloud (free, no
signup, no API key, Saheeh International English translation).

There's no dedicated "random" endpoint documented for this API (unlike
bible-api.com) - instead this picks a random ayah number between 1 and
6236 (the total number of ayahs across the whole Quran) and requests
that one directly via /ayah/{number}/en.sahih.

HONEST GAP: the exact field names for a single-ayah response (surah
name, edition name, etc.) are my best guess based on this API's other
documented responses (e.g. the surah-listing endpoint), not confirmed
against a live single-ayah response. If this comes back empty or
wrong, the actual JSON shape is the first thing to check.
"""

from __future__ import annotations

import asyncio
import random

import aiohttp

TOTAL_AYAHS = 6236


async def get_random_verse() -> dict | None:
    ayah_number = random.randint(1, TOTAL_AYAHS)
    url = f"https://api.alquran.cloud/v1/ayah/{ayah_number}/en.sahih"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    data = payload.get("data") or {}
    text = data.get("text")
    if not text:
        return None

    surah = data.get("surah") or {}
    surah_name = surah.get("englishName") or surah.get("name") or "Unknown Surah"
    verse_number = data.get("numberInSurah")

    if verse_number:
        reference = f"{surah_name} {surah.get('number', '?')}:{verse_number}"
    else:
        reference = surah_name

    edition = data.get("edition") or {}
    translation_name = edition.get("englishName") or edition.get("name") or "Saheeh International"

    return {
        "text": text.strip(),
        "reference": reference,
        "translation_name": translation_name,
    }