"""
Fun command helpers - fetches a random anime reaction gif per call from
otakugifs.xyz (https://otakugifs.xyz/api), a free, no-signup API built
specifically for this (Discord bot reaction commands like ,kiss/,hug).
A fresh gif is fetched every invocation, so it's genuinely different
each time rather than picked from a small hardcoded list.
"""

from __future__ import annotations

import aiohttp

OTAKUGIFS_BASE = "https://api.otakugifs.xyz/gif"


async def fetch_reaction_gif(reaction: str) -> str | None:
    """Returns a gif URL for the given reaction (e.g. "kiss"), or None
    if the API is unreachable - callers should handle that gracefully
    rather than erroring out the whole command."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(OTAKUGIFS_BASE, params={"reaction": reaction}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("url")
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


def ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th', ..."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def ship_percentage(id1: int, id2: int) -> int:
    """Deterministic 0-100 'compatibility' for a pair of user IDs - same
    two users always get the same result, order doesn't matter."""
    pair = (min(id1, id2), max(id1, id2))
    return hash(pair) % 101


def ship_name(name1: str, name2: str) -> str:
    """Classic portmanteau: first half of name1 + second half of name2."""
    half1 = name1[: max(1, len(name1) // 2)]
    half2 = name2[len(name2) // 2 :] or name2
    return (half1 + half2).title()


def ship_comment(percentage: int) -> str:
    if percentage >= 81:
        return "Soulmates!"
    if percentage >= 51:
        return "Pretty solid match!"
    if percentage >= 21:
        return "There's potential..."
    return "Not looking good..."


def ship_bar(percentage: int, length: int = 10) -> str:
    filled = round(percentage / 100 * length)
    return "█" * filled + "░" * (length - filled)