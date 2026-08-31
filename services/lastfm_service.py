"""
,lastfm / ,fm - Last.fm lookups via the official, free Last.fm API
(https://www.last.fm/api). Free for non-commercial use, needs a free
API key (self-serve, no waitlist) - set LASTFM_API_KEY.

Also ,lyrics via lyrics.ovh - genuinely free, no key at all.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
API_KEY = os.getenv("LASTFM_API_KEY")
BASE_URL = "https://ws.audioscrobbler.com/2.0/"

PERIOD_MAP = {
    "overall": "overall", "all": "overall", "alltime": "overall",
    "week": "7day", "7day": "7day",
    "month": "1month", "1month": "1month",
    "3month": "3month", "quarter": "3month",
    "6month": "6month", "halfyear": "6month",
    "year": "12month", "12month": "12month",
}


async def _call(method: str, params: dict) -> dict | None:
    if not API_KEY:
        return None
    query = {"method": method, "api_key": API_KEY, "format": "json", **params}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, params=query, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    if "error" in data:
        return None
    return data


def normalize_period(period: str | None) -> str:
    if not period:
        return "overall"
    return PERIOD_MAP.get(period.lower(), "overall")


async def get_recent_tracks(username: str, limit: int = 1):
    data = await _call("user.getrecenttracks", {"user": username, "limit": str(limit)})
    if not data:
        return None
    return data.get("recenttracks", {}).get("track", [])


async def get_top_artists(username: str, period: str, limit: int = 10):
    data = await _call("user.gettopartists", {"user": username, "period": period, "limit": str(limit)})
    if not data:
        return None
    return data.get("topartists", {}).get("artist", [])


async def get_top_albums(username: str, period: str, limit: int = 10):
    data = await _call("user.gettopalbums", {"user": username, "period": period, "limit": str(limit)})
    if not data:
        return None
    return data.get("topalbums", {}).get("album", [])


async def get_top_tracks(username: str, period: str, limit: int = 10):
    data = await _call("user.gettoptracks", {"user": username, "period": period, "limit": str(limit)})
    if not data:
        return None
    return data.get("toptracks", {}).get("track", [])


async def get_artist_info(artist: str, username: str | None = None):
    params = {"artist": artist}
    if username:
        params["username"] = username
    data = await _call("artist.getinfo", params)
    if not data:
        return None
    return data.get("artist")


async def get_album_info(artist: str, album: str, username: str | None = None):
    params = {"artist": artist, "album": album}
    if username:
        params["username"] = username
    data = await _call("album.getinfo", params)
    if not data:
        return None
    return data.get("album")


async def get_track_info(artist: str, track: str, username: str | None = None):
    params = {"artist": artist, "track": track}
    if username:
        params["username"] = username
    data = await _call("track.getinfo", params)
    if not data:
        return None
    return data.get("track")


async def get_user_info(username: str):
    data = await _call("user.getinfo", {"user": username})
    if not data:
        return None
    return data.get("user")


async def get_loved_tracks(username: str, limit: int = 10):
    data = await _call("user.getlovedtracks", {"user": username, "limit": str(limit)})
    if not data:
        return None
    return data.get("lovedtracks", {}).get("track", [])


async def get_global_top_tracks(limit: int = 10):
    data = await _call("chart.gettoptracks", {"limit": str(limit)})
    if not data:
        return None
    return data.get("tracks", {}).get("track", [])


def best_image(images: list[dict] | None) -> str | None:
    if not images:
        return None
    for size in ("extralarge", "large", "medium", "small"):
        for img in images:
            if img.get("size") == size and img.get("#text"):
                return img["#text"]
    return None


# ---------------------------------------------------------- collage

async def build_collage(albums: list[dict], grid: int = 3) -> "io.BytesIO | None":
    """Downloads each album's cover art and composites a grid x grid
    collage. Skips albums with no artwork; returns None if none of
    them had usable art."""
    import io

    from PIL import Image

    tile_size = 300
    urls = []
    for album in albums[: grid * grid]:
        url = best_image(album.get("image"))
        urls.append(url)

    async def _fetch(url: str | None) -> "Image.Image | None":
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB").resize((tile_size, tile_size))
        except Exception:
            return None

    tiles = [await _fetch(u) for u in urls]
    if not any(tiles):
        return None

    canvas = Image.new("RGB", (tile_size * grid, tile_size * grid), "black")
    for i, tile in enumerate(tiles):
        if tile is None:
            continue
        x = (i % grid) * tile_size
        y = (i // grid) * tile_size
        canvas.paste(tile, (x, y))

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------- lyrics (search-and-link, not full reproduction)

async def find_lyrics_link(artist: str, title: str) -> str | None:
    """Deliberately does NOT fetch/display full lyrics text - only
    confirms the track exists on a lyrics source and returns a link to
    it, since reproducing full copyrighted lyrics isn't something this
    bot does. Uses lyrics.ovh's suggest endpoint just to verify a
    match exists, then points to Genius's search instead of quoting
    any text."""
    from urllib.parse import quote

    url = f"https://api.lyrics.ovh/suggest/{quote(f'{artist} {title}')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None

    if not data.get("data"):
        return None
    return f"https://genius.com/search?q={quote(f'{artist} {title}')}"