"""
,roblox - looks up Roblox users/games/groups/items via Roblox's own
official public web APIs (users.roblox.com, games.roblox.com,
groups.roblox.com, catalog.roblox.com, avatar.roblox.com,
thumbnails.roblox.com, apis.roblox.com/search-api). All free, no key,
no signup - genuinely different footing from Instagram, which has no
such option for third-party bots.

HONEST GAP: as of an August 2026 Roblox policy change, the user
description field (users.roblox.com GetUser) now always returns an
empty string for privacy reasons - so ,roblox profile can't show a
bio anymore even though the field is still requested. Everything else
here (usernames, join dates, games, groups, outfits, catalog items,
username history) is unaffected.
"""

from __future__ import annotations

import asyncio

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _get_json(url: str, **kwargs) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=TIMEOUT, **kwargs) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def _post_json(url: str, json_body: dict) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_body, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


# ---------------------------------------------------------- users

async def resolve_user(username: str) -> dict | None:
    """Username -> {id, name, displayName} via the official bulk
    username-lookup endpoint."""
    data = await _post_json(
        "https://users.roblox.com/v1/usernames/users",
        {"usernames": [username], "excludeBannedUsers": False},
    )
    if not data or not data.get("data"):
        return None
    return data["data"][0]


async def get_user_profile(user_id: int) -> dict | None:
    return await _get_json(f"https://users.roblox.com/v1/users/{user_id}")


async def get_username_history(user_id: int) -> list[str]:
    data = await _get_json(f"https://users.roblox.com/v1/users/{user_id}/username-history?limit=25&sortOrder=Desc")
    if not data:
        return []
    return [entry["name"] for entry in data.get("data", [])]


async def get_avatar_thumbnail(user_id: int) -> str | None:
    data = await _get_json(
        "https://thumbnails.roblox.com/v1/users/avatar",
        params={"userIds": str(user_id), "size": "420x420", "format": "Png"},
    )
    if not data or not data.get("data"):
        return None
    return data["data"][0].get("imageUrl")


async def get_user_games(user_id: int) -> list[dict]:
    data = await _get_json(f"https://games.roblox.com/v2/users/{user_id}/games?accessFilter=Public&limit=25")
    if not data:
        return []
    return data.get("data", [])


async def get_user_groups(user_id: int) -> list[dict]:
    data = await _get_json(f"https://groups.roblox.com/v1/users/{user_id}/groups/roles")
    if not data:
        return []
    return data.get("data", [])


async def get_outfits(user_id: int) -> list[dict]:
    data = await _get_json(f"https://avatar.roblox.com/v1/users/{user_id}/outfits?itemsPerPage=25")
    if not data:
        return []
    return data.get("data", [])


# ---------------------------------------------------------- games

async def search_game(name: str) -> dict | None:
    """Uses Roblox's own omni-search (what their search bar calls) to
    resolve a game name to a universeId, then fetches full details."""
    data = await _get_json(
        "https://apis.roblox.com/search-api/omni-search",
        params={"searchQuery": name, "pageType": "games"},
    )
    if not data:
        return None

    universe_id = None
    for section in data.get("searchResults", []):
        for entry in section.get("contents", []):
            uid = entry.get("universeId") or entry.get("rootPlaceId")
            if uid:
                universe_id = entry.get("universeId")
                break
        if universe_id:
            break

    if universe_id is None:
        return None

    return await get_game_details(universe_id)


async def get_game_details(universe_id: int) -> dict | None:
    details = await _get_json(f"https://games.roblox.com/v1/games?universeIds={universe_id}")
    if not details or not details.get("data"):
        return None
    game = details["data"][0]

    favorites = await _get_json(f"https://games.roblox.com/v1/games/{universe_id}/favorites/count")
    game["favoritedCount"] = favorites.get("favoritesCount") if favorites else None

    thumb = await _get_json(
        "https://thumbnails.roblox.com/v1/games/icons",
        params={"universeIds": str(universe_id), "size": "512x512", "format": "Png"},
    )
    if thumb and thumb.get("data"):
        game["iconUrl"] = thumb["data"][0].get("imageUrl")

    return game


# ---------------------------------------------------------- groups

async def search_group(name: str) -> dict | None:
    data = await _get_json("https://groups.roblox.com/v1/groups/search", params={"keyword": name, "limit": "10"})
    if not data or not data.get("data"):
        return None
    return data["data"][0]


async def get_group_details(group_id: int) -> dict | None:
    return await _get_json(f"https://groups.roblox.com/v1/groups/{group_id}")


async def get_asset_thumbnail(asset_id: int) -> str | None:
    data = await _get_json(
        "https://thumbnails.roblox.com/v1/assets",
        params={"assetIds": str(asset_id), "size": "420x420", "format": "Png"},
    )
    if not data or not data.get("data"):
        return None
    return data["data"][0].get("imageUrl")


# ---------------------------------------------------------- catalog

async def search_catalog_item(name: str) -> dict | None:
    data = await _get_json(
        "https://catalog.roblox.com/v1/search/items/details",
        params={"category": "All", "keyword": name, "limit": "10"},
    )
    if not data or not data.get("data"):
        return None
    return data["data"][0]