"""
Sends live bot stats to the website backend's /api/status/report
endpoint every interval, so /api/status can report real numbers
instead of fake ones.

The bot and the website backend are separate processes on separate
hosts (bot on PebbleHost, backend on its own VPS) - a local file
cannot bridge them, since neither host can see the other's
filesystem. An HTTP POST, authenticated with a shared secret, is the
only honest way to connect two genuinely separate machines.

Needs two settings (see config.py / your .env):
  WEBSITE_API_URL      e.g. https://api.blaid.best
  STATUS_REPORT_TOKEN  any secret string, must match the SAME
                       environment variable set on the backend's host
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import config

log = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)


async def write_status(bot) -> None:
    if not config.website_api_url or not config.status_report_token:
        log.warning("website_api_url or status_report_token not set - skipping status report.")
        return

    guild_count = len(bot.guilds)
    user_count = sum(g.member_count or 0 for g in bot.guilds)
    latency_ms = round(bot.latency * 1000) if bot.latency == bot.latency else None  # filters NaN

    payload = {
        "guild_count": guild_count,
        "user_count": user_count,
        "latency_ms": latency_ms,
        "started_at": bot.started_at.timestamp(),
        "guild_ids": [g.id for g in bot.guilds],
    }

    url = f"{config.website_api_url.rstrip('/')}/api/status/report"
    headers = {"x-status-token": config.status_report_token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Status report rejected: %s %s", resp.status, body)
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError) as exc:
        log.warning("Status report failed: %s", exc)
