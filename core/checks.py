"""Reusable permission and hierarchy checks for moderation-style commands."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.errors import BotTargetError, HierarchyError, NotServerOwner, OwnerTargetError, SelfTargetError


def is_server_owner():
    """Restrict a command to the guild owner only (not Administrator)."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or ctx.author.id != ctx.guild.owner_id:
            raise NotServerOwner()
        return True

    return commands.check(predicate)


def validate_moderation_target(ctx: commands.Context, target: discord.Member) -> None:
    """
    Run before any punishment command executes. Raises a BladeError
    subclass if the target is invalid; callers should let it propagate
    to the global error handler.
    """
    if target.id == ctx.author.id:
        raise SelfTargetError()

    if target.id == ctx.bot.user.id:
        raise BotTargetError()

    if ctx.guild is not None and target.id == ctx.guild.owner_id:
        raise OwnerTargetError()

    author_top_role = ctx.author.top_role
    target_top_role = target.top_role

    # Server owner bypasses hierarchy checks against everyone but the bot/owner (handled above).
    if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
        return

    if target_top_role >= author_top_role:
        raise HierarchyError()


def has_permission_or_fake(permission_name: str):
    """Gates a command on a real Discord permission OR a fake permission
    granted via ,fakepermissions - a role granted `ban_members` this way
    can use bot commands gated on it, without Discord itself letting
    that role ban anyone. Real permission is checked first (no DB hit
    needed in the common case)."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        if getattr(ctx.author.guild_permissions, permission_name, False):
            return True

        from database.database import get_session
        from repositories import security_repository

        role_ids = [r.id for r in ctx.author.roles]
        async with get_session() as session:
            granted = await security_repository.has_fake_permission(session, ctx.guild.id, role_ids, permission_name)

        if granted:
            return True

        raise commands.MissingPermissions([permission_name])

    return commands.check(predicate)


async def check_owner_or_antinuke_admin(ctx: commands.Context) -> bool:
    """Plain boolean check - True if the user is the guild owner or an
    antinuke admin. Used both by the decorator below (which raises on
    False, for commands entirely gated on this) and directly by
    commands that only need this check conditionally, like ,unban
    checking it just for hardbanned targets."""
    if ctx.guild is None:
        return False
    if ctx.author.id == ctx.guild.owner_id:
        return True

    from database.database import get_session
    from repositories import security_repository

    async with get_session() as session:
        return await security_repository.is_antinuke_admin(session, ctx.guild.id, ctx.author.id)


def is_owner_or_antinuke_admin():
    """Restrict a command to the guild owner or a user explicitly added
    via ,antinuke admin - deliberately separate from Manage Guild/
    Administrator, since antinuke config is sensitive enough to
    warrant its own explicit allowlist."""

    async def predicate(ctx: commands.Context) -> bool:
        if await check_owner_or_antinuke_admin(ctx):
            return True
        raise NotServerOwner()

    return commands.check(predicate)


def requires_premium(plan: str):
    """Gates a command behind Server Premium ('server') or Customize
    ('customize') - sends the exact premium-gate embed itself and
    blocks the command if the guild isn't on that plan."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        from services import premium_service
        if await premium_service.is_premium(ctx.guild.id, plan):
            return True

        await premium_service.send_premium_gate(ctx, ctx.command.qualified_name, plan_hint=plan)
        return False

    return commands.check(predicate)


def bot_can_act_on(ctx: commands.Context, target: discord.Member) -> bool:
    """Check whether the bot's top role is above the target's - required
    before role/timeout/kick/ban operations can succeed."""
    if ctx.guild is None or ctx.guild.me is None:
        return False
    return ctx.guild.me.top_role > target.top_role
