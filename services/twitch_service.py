"""
,twitch - checks live status via Twitch's official Helix API using
the Client Credentials flow (free, no user login - a free Twitch
Developer app's Client ID + Secret).

Needs TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET set (create a free
app at https://dev.twitch.tv/console/apps, no approval/waitlist).
Without them, every command here fails gracefully.
"""

from __future__ import annotations

import asyncio
import os
import time

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_token() -> str | None:
    if not CLIENT_ID or not CLIENT_SECRET:
        return None

    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://id.twitch.tv/oauth2/token",
                data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"},
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


async def _headers() -> dict | None:
    token = await _get_token()
    if token is None:
        return None
    return {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"}


async def _get_json(url: str, params: dict) -> dict | None:
    headers = await _headers()
    if headers is None:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def get_user(login: str) -> dict | None:
    data = await _get_json("https://api.twitch.tv/helix/users", {"login": login.lower()})
    if not data or not data.get("data"):
        return None
    return data["data"][0]


async def get_stream(login: str) -> dict | None:
    """Returns the live stream object, or None if the channel is offline
    (or doesn't exist, or Twitch isn't configured)."""
    data = await _get_json("https://api.twitch.tv/helix/streams", {"user_login": login.lower()})
    if not data or not data.get("data"):
        return None
    return data["data"][0]