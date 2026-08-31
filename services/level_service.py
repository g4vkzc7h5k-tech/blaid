"""
Level system business logic: XP -> level curve, message XP awarding
with cooldown, and role sync. Cogs call this instead of touching
repositories directly.
"""

from __future__ import annotations

import random
import time

import discord

from database.database import get_session
from database.levels_models import LevelUser
from repositories import level_repository

# XP required to reach a given level. Simple, tunable curve:
# level n requires 5 * n^2 + 50 * n + 100 total XP.
def xp_for_level(level: int) -> int:
    return 5 * (level**2) + 50 * level + 100


def level_from_xp(total_xp: int) -> int:
    level = 0
    while total_xp >= xp_for_level(level + 1):
        level += 1
    return level


async def is_ignored(guild_id: int, *, role_ids: set[int], channel_id: int) -> bool:
    async with get_session() as session:
        ignored = await level_repository.get_ignored(session, guild_id)

    ignored_roles = {i.target_id for i in ignored if i.target_type == "role"}
    ignored_channels = {i.target_id for i in ignored if i.target_type == "channel"}

    if channel_id in ignored_channels:
        return True
    if role_ids & ignored_roles:
        return True
    return False


async def award_message_xp(member: discord.Member, channel_id: int) -> tuple[LevelUser, bool]:
    """
    Awards text XP for a message if the guild has leveling unlocked and
    the user is off cooldown. Returns (user, leveled_up).
    """
    guild_id = member.guild.id

    async with get_session() as session:
        config = await level_repository.get_or_create_config(session, guild_id)
        if not config.enabled:
            return await level_repository.get_or_create_user(session, guild_id, member.id), False

        user = await level_repository.get_or_create_user(session, guild_id, member.id)

        now = time.time()
        if now - user.last_xp_at < config.xp_cooldown_seconds:
            return user, False

        role_ids = {r.id for r in member.roles}
        if await is_ignored(guild_id, role_ids=role_ids, channel_id=channel_id):
            return user, False

        base_xp = random.randint(15, 25)
        gained = int(base_xp * config.multiplier)

        old_level = user.level
        user = await level_repository.add_xp(session, guild_id, member.id, gained, voice=False)
        user.last_xp_at = now

        new_level = level_from_xp(user.total_xp)
        leveled_up = new_level > old_level
        if leveled_up:
            user.level = new_level

        await session.commit()
        await session.refresh(user)

    if leveled_up:
        await sync_roles(member, new_level)

    return user, leveled_up


async def sync_roles(member: discord.Member, level: int) -> None:
    """Add/remove level roles according to the guild's stack_roles setting.
    Never crashes the caller - permission/hierarchy failures are swallowed
    (a production build should log these to the mod-log channel)."""
    guild_id = member.guild.id

    async with get_session() as session:
        config = await level_repository.get_or_create_config(session, guild_id)
        roles = await level_repository.get_roles(session, guild_id)

    eligible = [r for r in roles if level >= r.level_required]
    if not eligible:
        return

    if config.stack_roles:
        target_role_ids = {r.role_id for r in eligible}
    else:
        highest = max(eligible, key=lambda r: r.level_required)
        target_role_ids = {highest.role_id}

    all_level_role_ids = {r.role_id for r in roles}
    member_role_ids = {r.id for r in member.roles}

    to_add = [
        rid for rid in target_role_ids
        if rid not in member_role_ids and member.guild.get_role(rid) is not None
    ]
    to_remove = [
        rid for rid in (all_level_role_ids - target_role_ids)
        if rid in member_role_ids and member.guild.get_role(rid) is not None
    ]

    try:
        if to_add:
            await member.add_roles(*[member.guild.get_role(r) for r in to_add], reason="Level role sync")
        if to_remove:
            await member.remove_roles(*[member.guild.get_role(r) for r in to_remove], reason="Level role sync")
    except discord.Forbidden:
        pass  # bot's role is below the target role - nothing more we can do here
