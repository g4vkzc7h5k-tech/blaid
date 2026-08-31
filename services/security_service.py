"""
Antinuke business logic.

Every module (ban, channel, role, webhook, ...) shares one generic
detection path: handle_audit_log_entry() is called from a single
on_audit_log_entry_create listener (added in discord.py 2.4+, fires
for literally every audit log entry) and dispatches by entry.action to
the right module via MODULE_ACTIONS. That table is built defensively -
if a given discord.py install doesn't have a particular AuditLogAction
member (some, like soundboard sounds, are very new and may not exist
under this exact name on every version), that module just has no live
trigger rather than crashing the whole bot on import.

Tracking is an in-memory rolling window per (guild, executor, module) -
resets on restart by design; this is a real-time rate limiter, not a
permanent audit log.
"""

from __future__ import annotations

import datetime
import time
from collections import defaultdict

import discord

from database.database import get_session
from repositories import guild_config_repository, security_repository

# (guild_id, executor_id, module_name) -> list[timestamp]
_action_log: dict[tuple[int, int, str], list[float]] = defaultdict(list)

WINDOW_SECONDS = 10

# Blade commands that double-count toward a module's threshold when
# that module has track_commands enabled - only the modules with an
# obvious 1:1 Blade command are covered.
COMMAND_TO_MODULE = {
    "ban": "ban",
    "kick": "kick",
    "role": "role",
}


def _build_module_actions() -> dict:
    """module_name -> set of discord.AuditLogAction members, built
    defensively so a missing enum member on this discord.py version
    just drops that one trigger instead of raising ImportError."""
    mapping: dict[str, list[str]] = {
        "ban": ["ban"],
        "kick": ["kick"],
        "channel": ["channel_create", "channel_delete", "channel_update"],
        "emoji": ["emoji_create", "emoji_delete", "emoji_update"],
        "guildupdate": ["guild_update"],
        "integration": ["integration_update"],
        "integrationcreate": ["integration_create"],
        "integrationdelete": ["integration_delete"],
        "integrationupdate": ["integration_update"],
        "invite": ["invite_create", "invite_delete"],
        "role": ["role_create", "role_delete", "role_update"],
        "soundboard": ["sound_board_sound_create", "sound_board_sound_delete"],
        "sticker": ["sticker_create", "sticker_delete", "sticker_update"],
        "webhook": ["webhook_create", "webhook_delete", "webhook_update"],
        # "vanity" and "botadd" have no direct AuditLogAction - vanity is
        # detected via guild_update (see handle_audit_log_entry), botadd
        # is detected via on_member_join (see handle_bot_join).
    }

    built: dict[str, set] = {}
    for module_name, action_names in mapping.items():
        actions = set()
        for action_name in action_names:
            action = getattr(discord.AuditLogAction, action_name, None)
            if action is not None:
                actions.add(action)
        if actions:
            built[module_name] = actions
    return built


MODULE_ACTIONS = _build_module_actions()
_ACTION_TO_MODULES: dict = {}
for _module, _actions in MODULE_ACTIONS.items():
    for _action in _actions:
        _ACTION_TO_MODULES.setdefault(_action, []).append(_module)


async def _is_exempt(guild: discord.Guild, executor_id: int) -> bool:
    if executor_id == guild.owner_id or executor_id == guild.me.id:
        return True
    async with get_session() as session:
        if await security_repository.is_whitelisted(session, guild.id, executor_id):
            return True
        if await security_repository.is_antinuke_admin(session, guild.id, executor_id):
            return True
    return False


async def _record_and_check(guild: discord.Guild, executor: discord.Member, module_name: str) -> bool:
    """Records one action toward `module_name`'s threshold for
    `executor`. Returns True if this pushed them over it (and
    punishment was attempted)."""
    async with get_session() as session:
        cfg = await security_repository.get_or_create_antinuke_config(session, guild.id)
        if not cfg.enabled:
            return False
        module = await security_repository.get_or_create_module(session, guild.id, module_name)
        if not module.enabled:
            return False

    if await _is_exempt(guild, executor.id):
        return False

    key = (guild.id, executor.id, module_name)
    now = time.time()
    _action_log[key] = [t for t in _action_log[key] if now - t < WINDOW_SECONDS]
    _action_log[key].append(now)

    if len(_action_log[key]) < module.threshold:
        return False

    _action_log[key].clear()
    await _punish(guild, executor, module.punishment, reason=f"Antinuke: exceeded {module_name} threshold")
    return True


async def handle_audit_log_entry(entry: discord.AuditLogEntry, guild: discord.Guild) -> None:
    modules = _ACTION_TO_MODULES.get(entry.action)
    if not modules:
        return

    executor = entry.user
    if executor is None or not isinstance(executor, discord.Member):
        member = guild.get_member(entry.user_id) if entry.user_id else None
        if member is None:
            return
        executor = member

    for module_name in modules:
        if module_name == "guildupdate":
            # "vanity" is a sub-case of guild_update specifically for the
            # vanity invite code changing - checked separately so it can
            # have its own on/off/threshold independent of guildupdate.
            before_vanity = getattr(entry.before, "vanity_url_code", None)
            after_vanity = getattr(entry.after, "vanity_url_code", None)
            if before_vanity != after_vanity:
                await _record_and_check(guild, executor, "vanity")
        await _record_and_check(guild, executor, module_name)


async def handle_bot_join(member: discord.Member) -> None:
    """botadd module: any bot joining that isn't whitelisted gets kicked
    immediately - this is a gate, not a threshold, since a single
    unwanted bot join is already the problem."""
    if not member.bot:
        return

    guild = member.guild
    async with get_session() as session:
        cfg = await security_repository.get_or_create_antinuke_config(session, guild.id)
        if not cfg.enabled:
            return
        module = await security_repository.get_or_create_module(session, guild.id, "botadd")
        if not module.enabled:
            return
        whitelisted = await security_repository.is_whitelisted(session, guild.id, member.id)

    if whitelisted:
        return

    try:
        await member.kick(reason="Antinuke: bot not whitelisted")
    except discord.Forbidden:
        pass


async def handle_command_used(ctx) -> None:
    """Call from an on_command_completion listener - double-counts a
    Blade command toward its module's threshold when that module has
    track_commands enabled (e.g. ,ban counting toward the ban module
    even when nothing shows up in Discord's own audit log yet)."""
    if ctx.guild is None:
        return
    module_name = COMMAND_TO_MODULE.get(ctx.command.qualified_name)
    if module_name is None:
        return

    async with get_session() as session:
        module = await security_repository.get_or_create_module(session, ctx.guild.id, module_name)
    if not module.enabled or not module.track_commands:
        return

    if not isinstance(ctx.author, discord.Member):
        return
    await _record_and_check(ctx.guild, ctx.author, module_name)

async def punish_member(guild: discord.Guild, member: discord.Member, punishment: str, *, reason: str) -> None:
    """Public wrapper around _punish, for other security-family
    services (e.g. antiraid) that need the same ban/kick/timeout/jail
    logic without duplicating it."""
    await _punish(guild, member, punishment, reason=reason)


async def strip_all_roles(guild: discord.Guild, member: discord.Member, *, reason: str) -> list[discord.Role]:
    """Public wrapper around the same 'strip' logic antinuke uses -
    removes every role the member has (regardless of permissions) that
    Blade can actually remove (below Blade's top role). Returns the
    roles that were removed."""
    roles_to_remove = [r for r in member.roles if r.name != "@everyone" and r < guild.me.top_role]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason=reason)
    return roles_to_remove

async def strip_staff_roles(guild: discord.Guild, member: discord.Member, *, reason: str) -> list[discord.Role]:
    """Public wrapper around the same 'stripstaff' logic antinuke uses -
    removes every role the member has that grants a staff-level
    permission (Administrator, Manage Guild/Roles/Channels/Messages/
    Webhooks, Ban/Kick Members) and that Blade can actually remove.
    Returns the roles that were removed."""
    dangerous = discord.Permissions(
        administrator=True, manage_guild=True, manage_roles=True, manage_channels=True,
        ban_members=True, kick_members=True, manage_messages=True, manage_webhooks=True,
    )
    roles_to_remove = [
        r for r in member.roles
        if r.name != "@everyone" and r < guild.me.top_role and (r.permissions.value & dangerous.value)
    ]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason=reason)
    return roles_to_remove
  
async def _punish(guild: discord.Guild, member: discord.Member, punishment: str, *, reason: str) -> None:
    try:
        if punishment == "ban":
            await guild.ban(member, reason=reason)
        elif punishment == "kick":
            await guild.kick(member, reason=reason)
        elif punishment == "timeout":
            until = discord.utils.utcnow() + datetime.timedelta(hours=1)
            await member.timeout(until, reason=reason)
        elif punishment == "strip":
            roles_to_remove = [r for r in member.roles if r.name != "@everyone" and r < guild.me.top_role]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason)
        elif punishment == "stripstaff":
            dangerous = discord.Permissions(
                administrator=True, manage_guild=True, manage_roles=True, manage_channels=True,
                ban_members=True, kick_members=True, manage_messages=True, manage_webhooks=True,
            )
            roles_to_remove = [
                r for r in member.roles
                if r.name != "@everyone" and r < guild.me.top_role and (r.permissions.value & dangerous.value)
            ]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason)
        elif punishment == "jail":
            async with get_session() as session:
                guild_cfg = await guild_config_repository.get(session, guild.id)
            if guild_cfg is not None and guild_cfg.jail_role_id:
                jail_role = guild.get_role(guild_cfg.jail_role_id)
                if jail_role is not None:
                    await member.add_roles(jail_role, reason=reason)
    except discord.Forbidden:
        pass  # bot's role is below the target - nothing more we can do


# ---------------------------------------------------------- legacy join gate (unchanged)

async def record_action(guild: discord.Guild, executor: discord.Member, action_type: str) -> bool:
    """Kept for the existing on_guild_channel_delete/on_guild_role_delete/
    on_member_ban/on_member_remove listeners in cogs/security/security.py -
    those now just forward into the generic module system."""
    module_name = {"channel_delete": "channel", "role_delete": "role", "ban": "ban", "kick": "kick"}.get(action_type)
    if module_name is None:
        return False
    return await _record_and_check(guild, executor, module_name)