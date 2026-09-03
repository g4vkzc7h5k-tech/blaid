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

The variable reference below (VARIABLES) mirrors core/variables.py -
whenever that file changes, update this dict to match so the website
never drifts out of sync with what the bot actually supports.

Run:
    uvicorn website.backend.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
import time

# Make the project root importable regardless of what Render (or any
# other host) sets as the working directory/"root directory" - this
# is calculated from this file's own location, so it's correct no
# matter how the deploy is configured.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

STATUS_REPORT_TOKEN = os.environ.get("STATUS_REPORT_TOKEN", "")
BOT_API_TOKEN = os.environ.get("BOT_API_TOKEN", "")  # shared secret for bot<->backend calls (tickets queue)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")  # bot's real Discord token - only used for read-only REST calls (listing channels)
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "")  # e.g. https://blaid.onrender.com/api/auth/callback
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")  # e.g. https://blaid.best - where to redirect after login

app = FastAPI(title="Blaid API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://blaid.best", "https://www.blaid.best"],
    allow_credentials=True,  # required for the login cookie to work cross-subdomain (blaid.best <-> api.blaid.best)
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
        {"name": "{guild.member_count}", "description": "Member count (alias of guild.count)", "example": "1,204"},
        {"name": "{guild.owner_id}", "description": "Server owner's user ID", "example": "234567890123456789"},
        {"name": "{guild.created_at}", "description": "Unix timestamp the server was created", "example": "1609459200"},
        {"name": "{guild.emoji_count}", "description": "Number of custom emojis", "example": "42"},
        {"name": "{guild.role_count}", "description": "Number of roles", "example": "18"},
        {"name": "{guild.boost_count}", "description": "Number of boosts", "example": "14"},
        {"name": "{guild.booster_count}", "description": "Number of boosters", "example": "9"},
        {"name": "{guild.boost_tier}", "description": "Boost level", "example": "Level 2"},
        {"name": "{guild.preferred_locale}", "description": "Server's preferred locale", "example": "en-US"},
        {"name": "{guild.key_features}", "description": "Comma-separated server features", "example": "COMMUNITY, INVITE_SPLASH"},
        {"name": "{guild.icon}", "description": "Server icon URL", "example": "https://cdn.discordapp.com/icons/..."},
        {"name": "{guild.banner}", "description": "Server banner URL", "example": "https://cdn.discordapp.com/banners/..."},
        {"name": "{guild.splash}", "description": "Server invite splash URL", "example": "https://cdn.discordapp.com/splashes/..."},
        {"name": "{guild.max_members}", "description": "Max member count allowed", "example": "500000"},
        {"name": "{guild.afk_timeout}", "description": "AFK timeout in seconds", "example": "300"},
        {"name": "{guild.afk_channel}", "description": "AFK channel name", "example": "#afk"},
        {"name": "{guild.channels}", "description": "Comma-separated list of all channel names", "example": "general, voice-1"},
        {"name": "{guild.channels_count}", "description": "Total channel count", "example": "24"},
        {"name": "{guild.text_channels}", "description": "Comma-separated text channel names", "example": "general, rules"},
        {"name": "{guild.text_channels_count}", "description": "Text channel count", "example": "16"},
        {"name": "{guild.voice_channels}", "description": "Comma-separated voice channel names", "example": "General, AFK"},
        {"name": "{guild.voice_channels_count}", "description": "Voice channel count", "example": "6"},
        {"name": "{guild.category_channels}", "description": "Comma-separated category names", "example": "INFO, VOICE"},
        {"name": "{guild.category_channels_count}", "description": "Category count", "example": "5"},
        {"name": "{guild.vanity}", "description": "Vanity invite code, if set", "example": "blaid"},
    ],
    "User": [
        {"name": "{user.name}", "description": "Username", "example": "alex"},
        {"name": "{user.id}", "description": "User ID", "example": "345678901234567890"},
        {"name": "{user.mention}", "description": "Pings the user", "example": "@alex"},
        {"name": "{user.tag}", "description": "Legacy discriminator, e.g. #0001", "example": "#0001"},
        {"name": "{user.avatar}", "description": "Avatar URL", "example": "https://cdn.discordapp.com/..."},
        {"name": "{user.display_avatar}", "description": "Server-specific avatar if set, else global avatar", "example": "https://cdn.discordapp.com/..."},
        {"name": "{user.guild_avatar}", "description": "Server-specific avatar URL only", "example": "https://cdn.discordapp.com/..."},
        {"name": "{user.display_name}", "description": "Nickname if set, else username", "example": "Alex"},
        {"name": "{user.created_at}", "description": "Unix timestamp the account was created", "example": "1577836800"},
        {"name": "{user.joined_at}", "description": "Unix timestamp the member joined this server", "example": "1650000000"},
        {"name": "{user.bot}", "description": "Whether the user is a bot (Yes/No)", "example": "No"},
        {"name": "{user.boost}", "description": "Whether the user is boosting (Yes/No)", "example": "Yes"},
        {"name": "{user.boost_since}", "description": "Date boosting started", "example": "2026-01-15"},
        {"name": "{user.color}", "description": "The member's role color", "example": "#8B1E2F"},
        {"name": "{user.top_role}", "description": "Mentions the member's highest role", "example": "@Moderator"},
        {"name": "{user.role_list}", "description": "Comma-separated list of role names", "example": "Moderator, VIP"},
        {"name": "{user.join_position}", "description": "The member's join order number", "example": "42"},
        {"name": "{user.join_position_suffix}", "description": "Join order with ordinal suffix", "example": "42nd"},
        {"name": "{target_user.*}", "description": "Same fields as user.*, for a second/target member where applicable", "example": "{target_user.mention}"},
    ],
    "Channel": [
        {"name": "{channel.name}", "description": "Channel name", "example": "general"},
        {"name": "{channel.id}", "description": "Channel ID", "example": "456789012345678901"},
        {"name": "{channel.mention}", "description": "Mentions the channel", "example": "#general"},
        {"name": "{channel.type}", "description": "Channel type", "example": "text"},
        {"name": "{channel.topic}", "description": "Channel topic", "example": "Chat about anything"},
        {"name": "{channel.slowmode_delay}", "description": "Slowmode delay in seconds", "example": "5"},
        {"name": "{channel.category_name}", "description": "Parent category name", "example": "GENERAL"},
    ],
    "Ticket": [
        {"name": "{ticket.case}", "description": "The ticket's case number", "example": "42"},
        {"name": "{ticket.creator}", "description": "Who opened the ticket", "example": "alex#0001"},
        {"name": "{ticket.creator.mention}", "description": "Pings whoever opened the ticket", "example": "@alex"},
        {"name": "{ticket.claimed_by}", "description": "Who has claimed the ticket, or 'Unclaimed'", "example": "Unclaimed"},
        {"name": "{ticket.status}", "description": "Current ticket status", "example": "Open"},
        {"name": "{ticket.closed_by}", "description": "Who closed the ticket, or 'N/A'", "example": "N/A"},
        {"name": "{ticket.deleted_by}", "description": "Who deleted the ticket, or 'N/A'", "example": "N/A"},
        {"name": "{ticket.opened_at}", "description": "When the ticket was opened", "example": "January 15, 2026"},
        {"name": "{ticket.users}", "description": "Everyone added to the ticket", "example": "@alex, @sam"},
    ],
    "Twitch": [
        {"name": "{twitch.url}", "description": "Stream URL", "example": "https://twitch.tv/example"},
        {"name": "{twitch.title}", "description": "Stream title", "example": "ranked grind"},
        {"name": "{twitch.category}", "description": "Category/game being streamed", "example": "Just Chatting"},
        {"name": "{twitch.viewers}", "description": "Current viewer count", "example": "1,204"},
        {"name": "{twitch.thumbnail}", "description": "Stream thumbnail URL", "example": "https://static-cdn.jtvnw.net/..."},
        {"name": "{twitch.creator.name}", "description": "Streamer's display name", "example": "examplestreamer"},
    ],
    "YouTube": [
        {"name": "{youtube.url}", "description": "Video URL", "example": "https://youtube.com/watch?v=..."},
        {"name": "{youtube.title}", "description": "Video title", "example": "How to set up blaid"},
        {"name": "{youtube.channel.name}", "description": "Uploading channel's name", "example": "Blaid Official"},
        {"name": "{youtube.thumbnail}", "description": "Video thumbnail URL", "example": "https://i.ytimg.com/..."},
        {"name": "{youtube.published}", "description": "Publish date", "example": "2026-01-15"},
    ],
    "Leveling": [
        {"name": "{level}", "description": "The member's new level", "example": "12"},
        {"name": "{xp}", "description": "The member's total XP", "example": "4,820"},
    ],
    "Other": [
        {"name": "{custom.reason}", "description": "A moderation reason, where applicable", "example": "Spamming"},
        {"name": "{vanity}", "description": "The vanity/tag text a rewarded member is repping", "example": "discord.gg/blaid"},
        {"name": "{date}", "description": "Current UTC date", "example": "2026-08-18"},
        {"name": "{time}", "description": "Current UTC time", "example": "14:03:00"},
    ],
}


@app.on_event("startup")
def _load_commands_at_startup() -> None:
    global _commands_cache
    from command_export import build_commands_payload

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
    guild_ids: list[int] = []


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
        "guild_ids": report.guild_ids,
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


# ============================================================
# Discord OAuth login - lets the website know who's asking and which
# servers they can manage, so the ticket builder can offer a real
# "send to my server" flow.
#
# Session storage is in-memory (a dict keyed by a random token set as
# an httponly cookie) - fine for a single Render instance; sessions
# reset on redeploy, which just means logging in again, nothing lost.
# ============================================================

import secrets
import time as _time

import aiohttp
from fastapi import Cookie, Request
from fastapi.responses import RedirectResponse

DISCORD_API = "https://discord.com/api/v10"
ADMINISTRATOR = 0x8
MANAGE_GUILD = 0x20

_sessions: dict[str, dict] = {}  # session_token -> {user, guild_ids_admin, expires_at}
SESSION_TTL = 60 * 60 * 24 * 7  # 7 days


def _get_session(session_token: str | None) -> dict | None:
    if not session_token:
        return None
    session = _sessions.get(session_token)
    if session is None:
        return None
    if session["expires_at"] < _time.time():
        _sessions.pop(session_token, None)
        return None
    return session


@app.get("/api/auth/login")
def auth_login():
    if not DISCORD_CLIENT_ID or not OAUTH_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="OAuth is not configured on this backend.")
    params = (
        f"client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={OAUTH_REDIRECT_URI}"
        "&response_type=code"
        "&scope=identify%20guilds"
    )
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


@app.get("/api/auth/callback")
async def auth_callback(code: str):
    if not DISCORD_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="OAuth is not configured on this backend.")

    from urllib.parse import urlencode

    token_body = urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OAUTH_REDIRECT_URI,
    })

    async with aiohttp.ClientSession() as http:
        token_resp = await http.post(
            f"{DISCORD_API}/oauth2/token",
            data=token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status != 200:
            error_body = await token_resp.text()
            raise HTTPException(status_code=400, detail=f"Discord rejected the login: {error_body}")
        token_data = await token_resp.json()
        access_token = token_data["access_token"]

        auth_header = {"Authorization": f"Bearer {access_token}"}
        user_resp = await http.get(f"{DISCORD_API}/users/@me", headers=auth_header)
        user = await user_resp.json()

        guilds_resp = await http.get(f"{DISCORD_API}/users/@me/guilds", headers=auth_header)
        guilds = await guilds_resp.json()

    # Only guilds where this user has real management permissions -
    # the bot's own presence in the guild is checked separately at
    # request time against its live guild list, not cached here.
    admin_guilds = [
        {"id": g["id"], "name": g["name"], "icon": g.get("icon")}
        for g in guilds
        if (int(g.get("permissions", 0)) & (ADMINISTRATOR | MANAGE_GUILD))
    ]

    session_token = secrets.token_urlsafe(32)
    _sessions[session_token] = {
        "user": {"id": user["id"], "username": user["username"], "avatar": user.get("avatar")},
        "admin_guilds": admin_guilds,
        "expires_at": _time.time() + SESSION_TTL,
    }

    redirect_target = f"{FRONTEND_URL.rstrip('/')}/tickets.html" if FRONTEND_URL else "/"
    response = RedirectResponse(redirect_target)
    response.set_cookie(
        "blaid_session", session_token, httponly=True, samesite="lax", secure=True, max_age=SESSION_TTL,
    )
    return response


@app.post("/api/auth/logout")
def auth_logout(blaid_session: str | None = Cookie(default=None)):
    if blaid_session:
        _sessions.pop(blaid_session, None)
    response = RedirectResponse("/")
    response.delete_cookie("blaid_session")
    return response


@app.get("/api/auth/me")
def auth_me(blaid_session: str | None = Cookie(default=None)):
    session = _get_session(blaid_session)
    if session is None:
        return {"logged_in": False}

    bot_guild_ids = set(str(g) for g in (_last_status or {}).get("guild_ids", []))
    manageable = [g for g in session["admin_guilds"] if g["id"] in bot_guild_ids]

    return {
        "logged_in": True,
        "user": session["user"],
        "guilds": manageable,
    }


@app.get("/api/guilds/{guild_id}/channels")
async def guild_channels(guild_id: str, blaid_session: str | None = Cookie(default=None)):
    session = _get_session(blaid_session)
    manageable_ids = {g["id"] for g in session["admin_guilds"]} if session else set()
    if session is None or guild_id not in manageable_ids:
        raise HTTPException(status_code=403, detail="You don't manage this server.")
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured on this backend.")

    async with aiohttp.ClientSession() as http:
        resp = await http.get(
            f"{DISCORD_API}/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
        if resp.status != 200:
            raise HTTPException(status_code=502, detail="Couldn't fetch channels from Discord.")
        channels = await resp.json()

    text_channels = [
        {"id": c["id"], "name": c["name"]}
        for c in channels
        if c.get("type") == 0  # GUILD_TEXT
    ]
    return {"channels": text_channels}


@app.get("/api/guilds/{guild_id}/categories")
async def guild_categories(guild_id: str, blaid_session: str | None = Cookie(default=None)):
    session = _get_session(blaid_session)
    manageable_ids = {g["id"] for g in session["admin_guilds"]} if session else set()
    if session is None or guild_id not in manageable_ids:
        raise HTTPException(status_code=403, detail="You don't manage this server.")
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured on this backend.")

    async with aiohttp.ClientSession() as http:
        resp = await http.get(
            f"{DISCORD_API}/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
        if resp.status != 200:
            raise HTTPException(status_code=502, detail="Couldn't fetch categories from Discord.")
        channels = await resp.json()

    categories = [
        {"id": c["id"], "name": c["name"]}
        for c in channels
        if c.get("type") == 4  # GUILD_CATEGORY
    ]
    return {"categories": categories}


@app.get("/api/guilds/{guild_id}/roles")
async def guild_roles(guild_id: str, blaid_session: str | None = Cookie(default=None)):
    session = _get_session(blaid_session)
    manageable_ids = {g["id"] for g in session["admin_guilds"]} if session else set()
    if session is None or guild_id not in manageable_ids:
        raise HTTPException(status_code=403, detail="You don't manage this server.")
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured on this backend.")

    async with aiohttp.ClientSession() as http:
        resp = await http.get(
            f"{DISCORD_API}/guilds/{guild_id}/roles",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
        if resp.status != 200:
            raise HTTPException(status_code=502, detail="Couldn't fetch roles from Discord.")
        roles = await resp.json()

    roles = [{"id": r["id"], "name": r["name"]} for r in roles if r["name"] != "@everyone"]
    return {"roles": roles}


# ============================================================
# Ticket panel queue - the website submits a build request here; the
# bot polls /api/tickets/pending on an interval and creates the panel
# itself (reusing its own ticket_panel_manager_service), then reports
# back /complete. This indirection exists because the website backend
# and the bot run on different hosts and can't share a database or
# filesystem directly.
# ============================================================

# --- Ticket data model - mirrors database/tickets_models.py,
# database/ticket_options_models.py, and database/ticket_forms_models.py
# field-for-field, so the bot's poller can apply this directly via the
# real repositories with no translation layer.

class TicketPanelSettings(BaseModel):
    # Basics
    title: str
    description: str = ""
    button_label: str = "Open Ticket"

    # Category (channels/categories - all optional, resolved by the bot)
    channel_id: str  # where the panel itself is posted (also the "send to" channel)
    log_channel_id: str | None = None
    category_id: str | None = None
    closed_category_id: str | None = None

    # Behaviour
    delete_delay_seconds: int = 0
    max_open_tickets: int = 1
    auto_pin_controls: bool = False
    claims_enabled: bool = True
    logs_enabled: bool = False
    log_message_template: str | None = None

    # Display
    channel_name_format: str = "{ticket.case}-{ticket.author.name}"
    case_padding: int = 0
    dropdown_placeholder: str | None = None
    mode: str = "dropdown"  # "dropdown" | "buttons"


class TicketButtonConfig(BaseModel):
    label: str
    emoji: str | None = None
    color: str = "gray"  # blue|gray|green|red
    requires_reason: bool = False


class TicketOptionSettings(BaseModel):
    # Basics (Create Option + Style)
    name: str
    label: str
    emoji: str | None = None
    button_style: str = "blue"
    button_description: str | None = None

    # Behavior > Categories
    default_category_id: str | None = None
    claim_category_id: str | None = None
    close_category_id: str | None = None
    transcript_channel_id: str | None = None

    # Behavior > Naming
    channel_name_format: str = "{ticket.case}-{ticket.author.name}"
    claim_rename_template: str | None = None
    close_rename_template: str | None = None

    # Behavior > Permissions
    creator_can_close: bool = True
    close_on_leave: bool = False

    # Behavior > Required Roles
    require_all_roles: bool = False
    required_role_ids: list[str] = []

    # Behavior > Support Roles
    keep_staff_visible_on_claim: bool = True
    staff_can_speak_on_claim: bool = True
    support_role_ids: list[str] = []

    # Behavior > Trainee Roles
    trainees_can_claim: bool = False
    trainees_can_close: bool = False
    trainees_can_speak: bool = False
    trainee_role_ids: list[str] = []

    # Behavior > Button UX (claim/close/reopen/delete)
    button_configs: dict[str, TicketButtonConfig] = {}

    # Form (references a form built in the Forms tab, by its temp key - see TicketBuildRequest)
    form_key: str | None = None

    # Messages (message_type -> content)
    messages: dict[str, str] = {}

    # Automation (minutes)
    auto_close_timer: int | None = None
    auto_delete_timer: int | None = None
    inactivity_timer: int | None = None


class TicketFormField(BaseModel):
    field_type: str  # short_text|long_text|checkbox|select|role_select|user_select|channel_select
    label: str
    description: str | None = None
    key: str | None = None
    required: bool = True


class TicketFormSettings(BaseModel):
    key: str  # temporary client-side key, so options can reference "which form" before either has a real DB id
    name: str
    modal_title: str
    enable_filtering: bool = False
    fields: list[TicketFormField] = []


class TicketBuildRequest(BaseModel):
    guild_id: str
    panel: TicketPanelSettings
    options: list[TicketOptionSettings] = []
    forms: list[TicketFormSettings] = []


_ticket_queue: dict[str, dict] = {}  # id -> {status, request, created_at}


@app.post("/api/tickets/queue")
def queue_ticket_panel(payload: TicketBuildRequest, blaid_session: str | None = Cookie(default=None)):
    session = _get_session(blaid_session)
    manageable_ids = {g["id"] for g in session["admin_guilds"]} if session else set()
    if session is None or payload.guild_id not in manageable_ids:
        raise HTTPException(status_code=403, detail="You don't manage this server.")

    item_id = secrets.token_hex(8)
    _ticket_queue[item_id] = {
        "id": item_id,
        "status": "pending",
        "request": payload.model_dump(),
        "created_at": time.time(),
    }
    return {"ok": True, "id": item_id}


def _require_bot_auth(x_bot_token: str = Header(default="")) -> None:
    if not BOT_API_TOKEN or x_bot_token != BOT_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing bot token.")


@app.get("/api/tickets/pending")
def get_pending_tickets(x_bot_token: str = Header(default="")):
    _require_bot_auth(x_bot_token)
    pending = [item for item in _ticket_queue.values() if item["status"] == "pending"]
    return {"items": pending}


@app.post("/api/tickets/pending/{item_id}/complete")
def complete_pending_ticket(item_id: str, x_bot_token: str = Header(default="")):
    _require_bot_auth(x_bot_token)
    item = _ticket_queue.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    item["status"] = "done"
    return {"ok": True}


if __name__ == "__main__":
    # Lets platforms like Render/Railway run this file directly with `python main.py`
    # instead of requiring a separate uvicorn command. They inject the port via $PORT.
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
