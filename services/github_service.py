"""
,github - looks up GitHub users/repos and finds public commit emails,
via GitHub's own official REST API. Free, no key needed for public
data, but capped at 60 requests/hour per IP without one (5,000/hour
with a free personal access token - see GITHUB_TOKEN below).

GitHub requires a User-Agent header on every request or it 403s -
every call here sends one.

,github 2email works by scanning a user's public events feed
(PushEvents) for commit author emails - a well-known technique, since
GitHub includes the commit author's email in push event payloads
unless the user has GitHub's "keep my email private" setting on
(which swaps it for a noreply address). This only surfaces what's
already public in that feed - nothing hidden or scraped.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # optional - raises the rate limit from 60/hr to 5,000/hr if set


def _headers() -> dict:
    headers = {
        "User-Agent": "Blade-Discord-Bot",
        "Accept": "application/vnd.github+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


async def _get_json(url: str, params: dict | None = None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_headers(), params=params, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        return None


async def get_user(username: str) -> dict | None:
    return await _get_json(f"https://api.github.com/users/{username}")


async def get_repo(name: str) -> dict | None:
    """Accepts either 'owner/repo' (direct fetch) or a free-text name
    (falls back to GitHub's own search, top result by stars)."""
    if "/" in name:
        direct = await _get_json(f"https://api.github.com/repos/{name}")
        if direct is not None:
            return direct

    data = await _get_json("https://api.github.com/search/repositories", params={"q": name, "sort": "stars", "order": "desc"})
    if not data or not data.get("items"):
        return None
    return data["items"][0]


async def find_commit_emails(username: str) -> list[str]:
    events = await _get_json(f"https://api.github.com/users/{username}/events/public", params={"per_page": "100"})
    if not events:
        return []

    emails: list[str] = []
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        for commit in event.get("payload", {}).get("commits", []):
            email = commit.get("author", {}).get("email")
            if email and email not in emails:
                emails.append(email)

    return emails