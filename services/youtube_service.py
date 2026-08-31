"""
,youtube - checks for new uploads (and optionally live status) via the
official YouTube Data API v3. Free, 10,000 quota units/day per key -
no cost, no card.

Needs YOUTUBE_API_KEY set (free key from Google Cloud Console, ~10
minutes to set up, no waitlist).

QUOTA DESIGN: search.list costs 100 units/call - way too expensive to
poll repeatedly. Everything here avoids it wherever possible:
- resolve_channel() uses channels.list with forHandle/id (1 unit),
  falling back to search.list (100 units) only as a last resort for a
  plain channel name that isn't a handle or raw ID.
- get_latest_video() uses playlistItems.list on the channel's cached
  "uploads" playlist (1 unit) instead of search.list.
- get_video_live_status() uses videos.list (1 unit) rather than
  search.list with eventType=live (100 units).
With this, a full poll cycle for one followed channel costs ~2 units,
so even dozens of follows checked every few minutes stay well inside
the free daily quota.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
API_KEY = os.getenv("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"


async def _get_json(endpoint: str, params: dict) -> dict | None:
    if not API_KEY:
        return None
    params = {**params, "key": API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def resolve_channel(query: str) -> dict | None:
    """Resolves a handle (@name), raw channel ID (UC...), or plain
    name to {id, title, url, uploads_playlist_id, thumbnail}."""
    query = query.strip()

    if query.startswith("UC") and len(query) == 24:
        data = await _get_json("channels", {"part": "snippet,contentDetails", "id": query})
    else:
        handle = query if query.startswith("@") else f"@{query}"
        data = await _get_json("channels", {"part": "snippet,contentDetails", "forHandle": handle})

    if not data or not data.get("items"):
        # last resort - expensive, only reached if handle/ID lookup found nothing
        search = await _get_json("search", {"part": "snippet", "q": query, "type": "channel", "maxResults": "1"})
        if not search or not search.get("items"):
            return None
        channel_id = search["items"][0]["snippet"]["channelId"]
        data = await _get_json("channels", {"part": "snippet,contentDetails", "id": channel_id})
        if not data or not data.get("items"):
            return None

    item = data["items"][0]
    return {
        "id": item["id"],
        "title": item["snippet"]["title"],
        "url": f"https://www.youtube.com/channel/{item['id']}",
        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
        "thumbnail": item["snippet"].get("thumbnails", {}).get("high", {}).get("url"),
    }


async def get_latest_video(uploads_playlist_id: str) -> dict | None:
    data = await _get_json("playlistItems", {"part": "snippet", "playlistId": uploads_playlist_id, "maxResults": "1"})
    if not data or not data.get("items"):
        return None
    item = data["items"][0]
    snippet = item["snippet"]
    video_id = snippet.get("resourceId", {}).get("videoId")
    if not video_id:
        return None
    return {
        "id": video_id,
        "title": snippet.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        "published": snippet.get("publishedAt", ""),
    }


async def get_video_live_status(video_id: str) -> str | None:
    """Returns 'live', 'upcoming', 'none', or None on failure."""
    data = await _get_json("videos", {"part": "snippet", "id": video_id})
    if not data or not data.get("items"):
        return None
    return data["items"][0]["snippet"].get("liveBroadcastContent", "none")