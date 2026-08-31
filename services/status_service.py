"""
Writes live bot stats to data/status.json every interval so the
website's /api/status endpoint can report real numbers instead of
fake ones. The bot and the website are separate processes - a shared
file is the simplest honest way to bridge them without requiring the
website to hold a Discord connection of its own.
"""

from __future__ import annotations

import json
import os
import time

STATUS_PATH = "data/status.json"


def write_status(bot) -> None:
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)

    guild_count = len(bot.guilds)
    user_count = sum(g.member_count or 0 for g in bot.guilds)

    payload = {
        "online": True,
        "guild_count": guild_count,
        "user_count": user_count,
        "latency_ms": round(bot.latency * 1000) if bot.latency == bot.latency else None,  # filter NaN
        "started_at": bot.started_at.timestamp(),
        "updated_at": time.time(),
    }

    tmp_path = STATUS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, STATUS_PATH)  # atomic on POSIX - website never reads a half-written file
