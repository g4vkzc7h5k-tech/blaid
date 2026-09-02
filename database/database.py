"""
Database engine, session factory, and safe startup migrations.

IMPORTANT: every model module must be imported here (even if unused
directly) so its table is registered on Base.metadata before
create_all() runs. If you add a new *_models.py file, add its import
below or its table will silently never be created.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import config
from database.base import Base

# --- Register every model module (see note above) ---
from database import models  # noqa: F401  Guild, GuildConfig
from database import moderation_models  # noqa: F401  ModerationCase
from database import levels_models  # noqa: F401  LevelUser, LevelConfig, LevelRole, LevelIgnored
from database import tickets_models  # noqa: F401  TicketPanel, Ticket
from database import ticket_forms_models  # noqa: F401  TicketForm, TicketFormField, TicketFormResponse
from database import ticket_options_models  # noqa: F401  TicketOption + related tables
from database import voicemaster_models  # noqa: F401  VoiceMasterConfig, TempVoiceChannel
from database import welcome_models  # noqa: F401  WelcomeConfig, GoodbyeConfig, BoostConfig
from database import logging_models  # noqa: F401  LogChannel, LogIgnore, LogSettings
from database import security_models  # noqa: F401  AntinukeConfig, AntinukeWhitelist, HoneypotConfig
from database import roles_models  # noqa: F401  Autorole, ReactionRole, ButtonRole, StickyRole
from database import automod_models  # noqa: F401  AutoResponder, AutoResponderRole
from database import filter_models  # noqa: F401  FilterConfig, FilterModule, FilterWord, FilterWhitelist, FilterExemptChannel, FilterStrike
from database import giveaway_models  # noqa: F401  Giveaway, GiveawayEntry
from database import giveaway_settings_models  # noqa: F401  GiveawayUserSettings, GiveawayTemplate, GiveawayBlacklist, GiveawayRoleMax
from database import alias_models  # noqa: F401  CommandAlias
from database import fun_models  # noqa: F401  InteractionCount
from database import guild_stats_models  # noqa: F401  GuildDailyStats
from database import nickname_models  # noqa: F401  ForcedNickname
from database import bug_models  # noqa: F401  BugReport
from database import lockdown_models  # noqa: F401  LockdownIgnore
from database import afk_models  # noqa: F401  AfkStatus
from database import denyperm_models  # noqa: F401  DeniedPermission
from database import boosterrole_models  # noqa: F401  BoosterRoleConfig, BoosterRole, BoosterRoleFilterWord
from database import namehistory_models  # noqa: F401  NameHistoryEntry
from database import antiraid_models  # noqa: F401  AntiraidConfig, AntiraidWhitelist, AntiraidUsernamePattern
from database import funnel_models  # noqa: F401  FunnelJoinRecord
from database import imageonly_models  # noqa: F401  ImageOnlyChannel
from database import economy_models  # noqa: F401  EconomyBalance, EconomyShopItem, EconomyInventoryItem
from database import twitch_models  # noqa: F401  TwitchFollow
from database import youtube_models  # noqa: F401  YoutubeFollow
from database import pingonjoin_models  # noqa: F401  PingOnJoinConfig
from database import verification_models  # noqa: F401  VerificationConfig
from database import premium_models  # noqa: F401  PremiumConfig, PremiumPurchase
from database import ai_usage_models  # noqa: F401  AiUsage
from database import schedule_models  # noqa: F401  ScheduledMessage
from database import reminder_models  # noqa: F401  Reminder
from database import lastfm_models  # noqa: F401  LastfmAccount
from database import autopfp_models  # noqa: F401  AutoPfpChannel
from database import autoreact_models  # noqa: F401  AutoReact
from database import backup_models  # noqa: F401  ServerBackup
from database import joindm_models  # noqa: F401  JoinDmConfig
from database import vanity_models  # noqa: F401  VanityConfig, VanityRole, VanityAwarded
from database import badge_models  # noqa: F401  BadgeConfig, BadgeRole, BadgeAwarded
from database import command_toggle_models  # noqa: F401  DisabledCommand
from database import invoke_models  # noqa: F401  InvokeMessage
from database import bumpreminder_models  # noqa: F401  BumpReminderConfig, BumpLeaderboardEntry

log = logging.getLogger("blade.database")


def _ensure_sqlite_dir_exists() -> None:
    """SQLite will not create parent directories on its own - if
    DATABASE_URL points at e.g. sqlite+aiosqlite:///data/blade.db and
    data/ doesn't exist yet, connecting fails with 'unable to open
    database file'. Create it up front so a fresh deploy just works."""
    url = config.database_url
    if not url.startswith("sqlite"):
        return

    # sqlite+aiosqlite:///data/blade.db -> data/blade.db
    path_part = url.split("///", 1)[-1]
    directory = os.path.dirname(path_part)
    if directory:
        os.makedirs(directory, exist_ok=True)


_ensure_sqlite_dir_exists()

engine = create_async_engine(config.database_url, echo=False)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def get_session() -> AsyncSession:
    """Return a new AsyncSession. Callers are responsible for closing/using
    it as an async context manager: `async with get_session() as session:`."""
    return SessionFactory()


async def _run_sqlite_column_migration() -> None:
    """
    create_all() does not add missing columns to tables that already
    exist. This walks every registered table, compares its model
    columns to what SQLite actually has, and ALTERs in anything
    missing. It never drops columns or tables, so existing data is
    always preserved.
    """
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            result = await conn.execute(text(f"PRAGMA table_info('{table.name}')"))
            existing_columns = {row[1] for row in result.fetchall()}

            if not existing_columns:
                # Table does not exist yet - create_all() will handle it.
                continue

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(dialect=conn.dialect)
                nullable = "" if column.nullable else " NOT NULL DEFAULT 0"
                alter_sql = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{nullable}"
                log.info("Migration: adding column %s.%s", table.name, column.name)
                await conn.execute(text(alter_sql))


async def _drop_legacy_honeypot_punishment_column() -> None:
    """One-off: honeypot_config used to have a NOT NULL 'punishment'
    column, replaced by 'action' when the honeypot system was rebuilt.
    The generic column-migration pass above only ADDS missing columns
    and never drops/relaxes old ones, so inserts kept failing that
    legacy NOT NULL constraint even though nothing writes to it
    anymore. This explicitly drops it if still present. Needs
    SQLite 3.35+ (ALTER TABLE ... DROP COLUMN) - if that's not
    available, this logs a warning and leaves the column in place
    rather than crashing startup."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info('honeypot_config')"))
        columns = {row[1] for row in result.fetchall()}
        if "punishment" not in columns:
            return
        try:
            log.info("Migration: dropping legacy honeypot_config.punishment column")
            await conn.execute(text("ALTER TABLE honeypot_config DROP COLUMN punishment"))
        except Exception as exc:
            log.warning("Could not drop legacy honeypot_config.punishment column: %s", exc)


async def init_database() -> None:
    """Create any missing tables, then run the column-migration pass."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _run_sqlite_column_migration()
    await _drop_legacy_honeypot_punishment_column()
    log.info("Database initialized.")


async def close_database() -> None:
    await engine.dispose()
    log.info("Database connection closed.")
