"""
,spotify - searches tracks/artists/albums via Spotify's Web API using
the Client Credentials flow (free, no user login needed - just a free
Spotify Developer app's Client ID + Secret).

Needs SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET set (create a free
app at https://developer.spotify.com/dashboard, no approval/waitlist).
Without them, every command here fails gracefully with a clear error
telling you they're missing - it won't crash the bot.

HONEST GAP: a February 2026 Spotify policy change restricted several
endpoints (browse categories, new releases, artist top tracks, other
users' profiles/playlists) for apps not in "extended quota mode" -
search and basic track/artist/album lookups (everything used here)
are unaffected, but if Spotify tightens further, that's the first
place to check.
"""

from __future__ import annotations

import asyncio
import os
import time

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_token() -> str | None:
    if not CLIENT_ID or not CLIENT_SECRET:
        return None

    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET),
                timeout=TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    return _token_cache["token"]


async def _search(query: str, search_type: str) -> dict | None:
    token = await _get_token()
    if token is None:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query, "type": search_type, "limit": "1"},
                timeout=TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def search_track(query: str) -> dict | None:
    data = await _search(query, "track")
    if not data:
        return None
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None


async def search_artist(query: str) -> dict | None:
    data = await _search(query, "artist")
    if not data:
        return None
    items = data.get("artists", {}).get("items", [])
    return items[0] if items else None


async def search_album(query: str) -> dict | None:
    data = await _search(query, "album")
    if not data:
        return None
    items = data.get("albums", {}).get("items", [])
    return items[0] if items else None


async def download_preview(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None