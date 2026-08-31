"""
Antiraid detection logic - join/message-pattern-based, separate from
antinuke (which watches staff/audit-log actions). Punishments reuse
security_service.punish_member so ban/kick/timeout/jail behave
identically to antinuke's.

Join-burst and mention-burst tracking are in-memory rolling windows,
same convention as antinuke's _action_log - resets on restart by
design, this is a real-time rate limiter, not a permanent log.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict

import discord

from database.database import get_session
from repositories import antiraid_repository
from services import security_service

# guild_id -> list[timestamp] (recent joins)
_join_log: dict[int, list[float]] = defaultdict(list)
# (guild_id, user_id) -> list[timestamp] (recent mentions sent)
_mention_log: dict[tuple[int, int], list[float]] = defaultdict(list)

JOIN_WINDOW_SECONDS = 10


def parse_flags(rest: str | None) -> dict[str, str]:
    """'--do ban --threshold 5' -> {'do': 'ban', 'threshold': '5'}."""
    flags: dict[str, str] = {}
    for match in re.finditer(r"--(\w+)\s+(\S+)", rest or ""):
        flags[match.group(1).lower()] = match.group(2)
    return flags


async def is_exempt(guild: discord.Guild, member: discord.Member) -> bool:
    async with get_session() as session:
        ids = [member.id] + [r.id for r in member.roles]
        return await antiraid_repository.is_whitelisted(session, guild.id, ids)


async def lock_down(guild: discord.Guild) -> None:
    async with get_session() as session:
        cfg = await antiraid_repository.get_or_create_config(session, guild.id)
        if cfg.locked_down:
            return
        await antiraid_repository.update_config(session, cfg, locked_down=True)

    for channel in guild.text_channels:
        overwrite = channel.overwrites_for(guild.default_role)
        if overwrite.send_messages is not False:
            overwrite.send_messages = False
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Antiraid lockdown")
            except discord.HTTPException:
                pass


async def unlock_down(guild: discord.Guild) -> None:
    async with get_session() as session:
        cfg = await antiraid_repository.get_or_create_config(session, guild.id)
        await antiraid_repository.update_config(session, cfg, locked_down=False)

    for channel in guild.text_channels:
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = None
        try:
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Antiraid unlock")
        except discord.HTTPException:
            pass


async def toggle_lock_down(guild: discord.Guild) -> bool:
    """Used by ,antiraid state - flips the current lockdown state and
    returns the new state."""
    async with get_session() as session:
        cfg = await antiraid_repository.get_or_create_config(session, guild.id)
    if cfg.locked_down:
        await unlock_down(guild)
        return False
    await lock_down(guild)
    return True


async def handle_member_join(member: discord.Member) -> None:
    guild = member.guild
    async with get_session() as session:
        cfg = await antiraid_repository.get_config(session, guild.id)

    if cfg is None or not cfg.enabled:
        return

    if await is_exempt(guild, member):
        return

    if cfg.age_enabled:
        account_age_days = (discord.utils.utcnow() - member.created_at).days
        if account_age_days < cfg.age_threshold_days:
            await security_service.punish_member(
                guild, member, cfg.age_action, reason=f"Antiraid: account younger than {cfg.age_threshold_days}d"
            )
            return

    if cfg.avatar_enabled and member.avatar is None:
        await security_service.punish_member(guild, member, cfg.avatar_action, reason="Antiraid: default avatar")
        return

    if cfg.unverifiedbots_enabled and member.bot and not member.public_flags.verified_bot:
        await security_service.punish_member(guild, member, cfg.unverifiedbots_action, reason="Antiraid: unverified bot")
        return

    async with get_session() as session:
        patterns = await antiraid_repository.get_username_patterns(session, guild.id)
    lowered_name = member.name.lower()
    if any(pattern.lower() in lowered_name for pattern in patterns):
        # HONEST GAP: username-pattern matches don't have their own
        # configurable action field (none was specified) - always kicks.
        await security_service.punish_member(guild, member, "kick", reason="Antiraid: blocked username pattern")
        return

    if cfg.massjoin_enabled:
        now = time.time()
        _join_log[guild.id] = [t for t in _join_log[guild.id] if now - t < JOIN_WINDOW_SECONDS]
        _join_log[guild.id].append(now)

        if len(_join_log[guild.id]) >= cfg.massjoin_threshold:
            _join_log[guild.id].clear()
            if cfg.massjoin_lock:
                await lock_down(guild)
            if cfg.massjoin_punish:
                await security_service.punish_member(guild, member, cfg.massjoin_action, reason="Antiraid: mass-join detected")


async def handle_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None:
        return

    async with get_session() as session:
        cfg = await antiraid_repository.get_config(session, message.guild.id)

    if cfg is None or not cfg.enabled or not cfg.massmention_enabled:
        return

    mention_count = len(message.mentions) + len(message.role_mentions)
    if mention_count == 0:
        return

    if isinstance(message.author, discord.Member) and await is_exempt(message.guild, message.author):
        return

    now = time.time()
    key = (message.guild.id, message.author.id)
    _mention_log[key] = [t for t in _mention_log[key] if now - t < cfg.massmention_timeframe]
    _mention_log[key].extend([now] * mention_count)

    if len(_mention_log[key]) >= cfg.massmention_threshold:
        _mention_log[key].clear()
        if cfg.massmention_lock:
            await lock_down(message.guild)
        await security_service.punish_member(
            message.guild, message.author, cfg.massmention_action, reason="Antiraid: mass mention detected"
        )