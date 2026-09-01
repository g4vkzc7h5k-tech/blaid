"""
Central configuration loader for Blade.

All environment-dependent values live here. Nothing else in the
project should call os.getenv() directly - import from this module
instead, so every setting has exactly one source of truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_list(name: str, default: str = "") -> list[str]:
    val = os.getenv(name, default)
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    # --- Discord ---
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))
    discord_client_id: str = field(default_factory=lambda: os.getenv("DISCORD_CLIENT_ID", ""))

    # --- Prefix ---
    default_prefix: str = field(default_factory=lambda: os.getenv("DEFAULT_PREFIX", ","))

    # --- Database ---
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/blade.db")
    )

    # --- Branding / links ---
    website_url: str = field(default_factory=lambda: os.getenv("WEBSITE_URL", ""))
    support_server_url: str = field(default_factory=lambda: os.getenv("SUPPORT_SERVER_URL", ""))
    invite_url: str = field(default_factory=lambda: os.getenv("INVITE_URL", ""))
    topgg_vote_url: str = field(default_factory=lambda: os.getenv("TOPGG_VOTE_URL", ""))
    website_api_url: str = field(default_factory=lambda: os.getenv("WEBSITE_API_URL", ""))
    status_report_token: str = field(default_factory=lambda: os.getenv("STATUS_REPORT_TOKEN", ""))

    # --- Behaviour ---
    owner_ids: list[int] = field(
        default_factory=lambda: [int(x) for x in _get_list("OWNER_IDS", "")]
    )
    debug: bool = field(default_factory=lambda: _get_bool("DEBUG", False))


config = Config()


def validate_config() -> None:
    """Raise a clear error early if required settings are missing."""
    if not config.discord_token or config.discord_token == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Add it to your .env file before starting Blade."
        )
