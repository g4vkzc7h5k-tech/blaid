"""
Blaid website backend.

Serves the command documentation, the variable reference, and a live
status endpoint.

The command list is loaded directly from the bot's own command_meta
registry ONE TIME, at backend startup (see load_commands() below and
its call in the startup event) - never from a hand-maintained or
manually-exported file. This means: add or change a @command_meta
anywhere in the bot's cogs, redeploy this backend (which happens
automatically on every push if your host auto-deploys from Git), and
the website's command docs are current - no separate export step,
ever. This is exactly the piece a purely static host (Netlify,
Vercel's static mode, etc.) cannot do on its own, since it can't run
Python to read the bot's actual source at deploy time - which is why
this lives in its own small always-on backend instead.

Status works across two separate hosts (the bot on one host, this
backend on another) via HTTP: the bot POSTs its live stats to
/api/status/report on an interval, authenticated with a shared secret
(STATUS_REPORT_TOKEN, set as an environment variable on THIS backend's
host and matching the one the bot sends). This backend just caches the
last report in memory and serves it back via GET /api/status - no
shared filesystem needed, since bot and backend genuinely run on
different machines.

Run:
    uvicorn website.backend.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

STATUS_REPORT_TOKEN = os.environ.get("STATUS_REPORT_TOKEN", "")

app = FastAPI(title="Blaid API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your actual frontend origin in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Populated once at startup by _load_commands_at_startup() - see the
# startup event below. Never re-read from disk or re-imported per
# request; redeploy the backend to pick up command changes.
_commands_cache: list[dict] = []

# In-memory cache of the bot's last status report - fine for a single
# backend instance; resets on redeploy, which just means "offline"
# shows briefly until the bot's next report comes in.
_last_status: dict | None = None

# --- Variable reference (mirrors core/variables.py - update both together) ---
VARIABLES = {
    "Guild": [
        {"name": "{guild.name}", "description": "Server name", "example": "Blaid Community"},
        {"name": "{guild.id}", "description": "Server ID", "example": "123456789012345678"},
        {"name": "{guild.count}", "description": "Member count", "example": "1,204"},
        {"name": "{guild.owner_id}", "description": "Server owner's user ID", "example": "234567890123456789"},
    ],
    "User": [
        {"name": "{user.name}", "description": "Username", "example": "alex"},
        {"name": "{user.id}", "description": "User ID", "example": "345678901234567890"},
        {"name": "{user.mention}", "description": "Pings the user", "example": "@alex"},
        {"name": "{user.avatar}", "description": "Avatar URL", "example": "https://cdn.discordapp.com/..."},
    ],
    "Channel": [
        {"name": "{channel.name}", "description": "Channel name", "example": "general"},
        {"name": "{channel.id}", "description": "Channel ID", "example": "456789012345678901"},
    ],
    "Leveling": [
        {"name": "{level}", "description": "The member's new level", "example": "12"},
        {"name": "{xp}", "description": "The member's total XP", "example": "4,820"},
    ],
    "Date/Time": [
        {"name": "{date}", "description": "Current UTC date", "example": "2026-08-18"},
        {"name": "{time}", "description": "Current UTC time", "example": "14:03:00"},
    ],
}


@app.on_event("startup")
def _load_commands_at_startup() -> None:
    global _commands_cache
    from website.backend.command_export import build_commands_payload

    try:
        _commands_cache = build_commands_payload()
        print(f"Loaded {len(_commands_cache)} commands from the live command_meta registry.")
    except Exception as exc:
        print(f"WARNING: failed to load commands at startup: {exc}")
        _commands_cache = []


def _load_commands() -> list[dict]:
    return _commands_cache


@app.get("/api/commands")
def list_commands(category: str | None = None):
    commands_ = _load_commands()
    if category:
        commands_ = [c for c in commands_ if c["category"].lower() == category.lower()]
    return {"commands": commands_}


@app.get("/api/commands/search")
def search_commands(q: str):
    q_lower = q.lower().strip()
    if not q_lower:
        return {"commands": []}
    commands_ = _load_commands()
    results = [
        c for c in commands_
        if q_lower in c["name"].lower()
        or q_lower in c["description"].lower()
        or any(q_lower in a.lower() for a in c.get("aliases", []))
    ]
    return {"commands": results}


@app.get("/api/commands/{name}")
def get_command(name: str):
    commands_ = _load_commands()
    for c in commands_:
        if c["name"].lower() == name.lower() or name.lower() in [a.lower() for a in c.get("aliases", [])]:
            return c
    raise HTTPException(status_code=404, detail="Command not found")


@app.get("/api/categories")
def list_categories():
    commands_ = _load_commands()
    categories: dict[str, int] = {}
    for c in commands_:
        categories[c["category"]] = categories.get(c["category"], 0) + 1
    return {"categories": [{"name": k, "command_count": v} for k, v in sorted(categories.items())]}


@app.get("/api/variables")
def list_variables():
    return {"groups": VARIABLES}


class StatusReport(BaseModel):
    guild_count: int
    user_count: int
    latency_ms: int | None = None
    started_at: float


@app.post("/api/status/report")
def report_status(report: StatusReport, x_status_token: str = Header(default="")):
    if not STATUS_REPORT_TOKEN or x_status_token != STATUS_REPORT_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing status token.")

    global _last_status
    _last_status = {
        "online": True,
        "guild_count": report.guild_count,
        "user_count": report.user_count,
        "latency_ms": report.latency_ms,
        "started_at": report.started_at,
        "updated_at": time.time(),
    }
    return {"ok": True}


@app.get("/api/status")
def status():
    if _last_status is None:
        return {"online": False, "reason": "Bot has not reported status yet."}

    # If the bot hasn't reported in >3 minutes, treat it as offline
    # rather than showing stale numbers as if they were live.
    if time.time() - _last_status["updated_at"] > 180:
        return {"online": False, "reason": "Status data is stale."}

    return _last_status


if __name__ == "__main__":
    # Lets platforms like Render/Railway run this file directly with `python main.py`
    # instead of requiring a separate uvicorn command. They inject the port via $PORT.
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)