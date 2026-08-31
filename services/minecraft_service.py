"""
,minecraft - looks up Minecraft players (via Mojang's own official,
free, keyless APIs) and server status (via api.mcsrvstat.us, a
long-established free public service used by many Minecraft tools).
"""

from __future__ import annotations

import asyncio
import base64
import json

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _get_json(url: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def get_player(username: str) -> dict | None:
    """Resolves a username to a UUID via Mojang, then fetches the full
    profile (skin/cape texture URLs) via the session server."""
    identity = await _get_json(f"https://api.mojang.com/users/profiles/minecraft/{username}")
    if identity is None or "id" not in identity:
        return None

    uuid = identity["id"]
    profile = await _get_json(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}")
    if profile is None:
        return None

    skin_url = None
    cape_url = None
    for prop in profile.get("properties", []):
        if prop.get("name") == "textures":
            try:
                decoded = json.loads(base64.b64decode(prop["value"]))
                skin_url = decoded.get("textures", {}).get("SKIN", {}).get("url")
                cape_url = decoded.get("textures", {}).get("CAPE", {}).get("url")
            except Exception:
                pass

    return {
        "uuid": uuid,
        "name": profile.get("name", identity.get("name", username)),
        "skin_url": skin_url,
        "cape_url": cape_url,
    }


async def get_server_status(address: str) -> dict | None:
    return await _get_json(f"https://api.mcsrvstat.us/3/{address}")