"""Moderation business logic: creates cases, posts modlog embeds, and
(optionally) DMs the target. Cogs call this instead of touching the
repository directly."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord

from core.modlog import build_modlog_embed
from database.database import get_session
from database.moderation_models import ModerationCase
from repositories import guild_config_repository, moderation_repository

# (guild_id, user_id) -> asyncio.Task, so unjailing manually or re-jailing
# with a new duration can cancel and replace the exact task that would
# otherwise fire at the old time.
_jail_tasks: dict[tuple[int, int], asyncio.Task] = {}


async def log_action(
    *,
    guild_id: int,
    user_id: int,
    moderator_id: int,
    action_type: str,
    reason: str | None,
    duration_seconds: int | None = None,
) -> ModerationCase:
    async with get_session() as session:
        return await moderation_repository.create_case(
            session,
            guild_id=guild_id,
            user_id=user_id,
            moderator_id=moderator_id,
            action_type=action_type,
            reason=reason,
            duration_seconds=duration_seconds,
        )


async def log_and_announce(
    guild: discord.Guild,
    action_type: str,
    moderator: discord.abc.User,
    *,
    target_id: int | None = None,
    target_mention: str | None = None,
    reason: str | None = None,
    duration_seconds: int | None = None,
) -> ModerationCase:
    """Records the case AND posts the standard modlog embed to the
    guild's configured logs channel (if one exists). Used for every
    action that should show up in the mod log: setup, ban, unban,
    kick, warn, timeout, untimeout."""
    async with get_session() as session:
        cfg = await guild_config_repository.get(session, guild.id)
        case = await moderation_repository.create_case(
            session,
            guild_id=guild.id,
            user_id=target_id if target_id is not None else moderator.id,
            moderator_id=moderator.id,
            action_type=action_type,
            reason=reason,
            duration_seconds=duration_seconds,
        )

    if cfg is not None and cfg.logs_channel_id:
        channel = guild.get_channel(cfg.logs_channel_id)
        if channel is not None:
            embed = build_modlog_embed(
                case.case_number,
                action_type,
                moderator,
                target_mention=target_mention,
                reason=reason,
                timestamp=case.created_at,
            )
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    return case


async def try_dm(member: discord.Member, description: str) -> bool:
    """Best-effort DM - returns False (never raises) if the member has DMs closed."""
    try:
        await member.send(description)
        return True
    except discord.HTTPException:
        return False


_PUNISHMENT_TITLES = {
    "jailed": "Jailed", "banned": "Banned", "timedout": "Timed Out",
    "unbanned": "Unbanned", "unjailed": "Unjailed", "untimedout": "Timeout Removed",
}
_PUNISHMENT_VERBS = {
    "jailed": "jailed in", "banned": "banned from", "timedout": "timed out in",
    "unbanned": "unbanned from", "unjailed": "unjailed in", "untimedout": "had your timeout removed in",
}

# Maps send_punishment_dm's past-tense `action` values to ,invoke's
# command-name keys (database/invoke_models.VALID_COMMANDS).
_ACTION_TO_INVOKE_COMMAND = {
    "jailed": "jail", "banned": "ban", "timedout": "timeout",
    "unbanned": "unban", "unjailed": "unjail", "untimedout": "untimeout",
}


async def send_punishment_dm(
    member_or_user, guild: discord.Guild, action: str, moderator, reason: str | None = None,
    duration: str | None = None,
) -> bool:
    """Red embed DM for ban/timeout/jail and their reversals - best
    effort, never raises. action is one of: jailed, banned, timedout,
    unbanned, unjailed, untimedout.

    Checks ,invoke first for a server-specific custom "dm" message for
    the matching command; falls back to the built-in embed if none is
    configured."""
    from core.script_parser import parse_script
    from core.variables import resolve_variables
    from repositories import invoke_repository

    invoke_command = _ACTION_TO_INVOKE_COMMAND.get(action)
    custom_content = None
    if invoke_command is not None:
        async with get_session() as session:
            custom_content = await invoke_repository.get_message(session, guild.id, invoke_command, "dm")

    if custom_content:
        resolved = resolve_variables(
            custom_content, guild=guild, member=member_or_user, reason=reason or "No reason provided",
        )
        resolved = resolved.replace("{moderator.mention}", getattr(moderator, "mention", str(moderator)))
        resolved = resolved.replace("{moderator.name}", getattr(moderator, "name", str(moderator)))
        resolved = resolved.replace("{moderator.id}", str(getattr(moderator, "id", "")))
        resolved = resolved.replace("{duration}", duration or "N/A")
        parsed = parse_script(resolved)
        try:
            if parsed.embed is not None:
                await member_or_user.send(content=parsed.content, embed=parsed.embed)
            else:
                await member_or_user.send(resolved)
            return True
        except discord.HTTPException:
            return False

    title = _PUNISHMENT_TITLES.get(action, action.title())
    verb = _PUNISHMENT_VERBS.get(action, action)

    description = f"**You have been {verb}** {guild.name}\n**Moderator** {moderator}"
    if duration:
        description += f"\n**Duration** {duration}"
    description += f"\n**Reason** {reason or 'No reason provided'}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.red())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="If you would like to dispute this punishment, contact a staff member.")
    embed.timestamp = discord.utils.utcnow()

    try:
        await member_or_user.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


async def get_invoke_text(guild_id: int, command: str, **kwargs) -> str | None:
    """Looks up a server-specific custom "text" (channel) message for
    ,invoke - returns the fully resolved string, or None if nothing is
    configured for that command (caller should fall back to its own
    default message). kwargs are passed straight to resolve_variables
    (guild, member, reason, etc.) - pass whatever that command has on
    hand."""
    from core.variables import resolve_variables
    from repositories import invoke_repository

    async with get_session() as session:
        content = await invoke_repository.get_message(session, guild_id, command, "text")

    if not content:
        return None

    return resolve_variables(content, **kwargs)


async def get_case_history(guild_id: int, user_id: int) -> list[ModerationCase]:
    async with get_session() as session:
        return await moderation_repository.get_cases_for_user(session, guild_id, user_id)


async def get_warning_history(guild_id: int, user_id: int) -> list[ModerationCase]:
    async with get_session() as session:
        return await moderation_repository.get_warnings_for_user(session, guild_id, user_id)


# ---------------------------------------------------------- jail scheduling

def schedule_unjail(bot: discord.Client, guild_id: int, user_id: int, delay_seconds: float) -> None:
    key = (guild_id, user_id)
    existing = _jail_tasks.get(key)
    if existing is not None and not existing.done():
        existing.cancel()
    _jail_tasks[key] = bot.loop.create_task(_auto_unjail(bot, guild_id, user_id, delay_seconds))


def cancel_scheduled_unjail(guild_id: int, user_id: int) -> None:
    key = (guild_id, user_id)
    task = _jail_tasks.pop(key, None)
    if task is not None and not task.done():
        task.cancel()


async def _auto_unjail(bot: discord.Client, guild_id: int, user_id: int, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
    except asyncio.CancelledError:
        return  # rescheduled or manually unjailed - a newer task/action owns this now

    guild = bot.get_guild(guild_id)

    async with get_session() as session:
        cfg = await guild_config_repository.get(session, guild_id)
        await moderation_repository.delete_jail_record(session, guild_id, user_id)

    if guild is not None and cfg is not None and cfg.jail_role_id:
        jail_role = guild.get_role(cfg.jail_role_id)
        member = guild.get_member(user_id)
        if jail_role is not None and member is not None:
            try:
                await member.remove_roles(jail_role, reason="Jail duration expired")
            except discord.Forbidden:
                pass

        await log_and_announce(
            guild, "unjail", guild.me,
            target_id=user_id, target_mention=f"<@{user_id}>", reason="Jail duration expired",
        )

    _jail_tasks.pop((guild_id, user_id), None)


async def resume_jails(bot: discord.Client) -> int:
    """Call on startup: reschedules every still-active timed jail so a
    restart never leaves someone jailed forever by accident."""
    async with get_session() as session:
        records = await moderation_repository.get_all_timed_jail_records(session)

    now = datetime.now(timezone.utc)
    resumed = 0
    for record in records:
        unjail_at = record.unjail_at
        if unjail_at.tzinfo is None:
            # SQLite doesn't preserve tz-awareness on read - treat a
            # naive value as UTC (what everything here is written in).
            unjail_at = unjail_at.replace(tzinfo=timezone.utc)
        remaining = (unjail_at - now).total_seconds()
        schedule_unjail(bot, record.guild_id, record.user_id, max(0, remaining))
        resumed += 1

    return resumed
