"""Custom exceptions and the global command error handler."""

from __future__ import annotations

import logging

from discord.ext import commands

from core import embeds

log = logging.getLogger("blade.errors")


class BladeError(commands.CommandError):
    """Base class for Blade's own command errors."""


class HierarchyError(BladeError):
    def __init__(self, message: str = "You cannot act on a member with an equal or higher role."):
        super().__init__(message)


class SelfTargetError(BladeError):
    def __init__(self, message: str = "You cannot target yourself with this command."):
        super().__init__(message)


class BotTargetError(BladeError):
    def __init__(self, message: str = "You cannot target me with this command."):
        super().__init__(message)


class OwnerTargetError(BladeError):
    def __init__(self, message: str = "You cannot target the server owner with this command."):
        super().__init__(message)


class NotServerOwner(BladeError):
    def __init__(self, message: str = "Only the server owner can use this command."):
        super().__init__(message)


async def handle_command_error(ctx: commands.Context, error_: Exception) -> None:
    """Attach this as bot.on_command_error. Converts every known error
    type into a clean embed and logs the technical traceback to console
    instead of dumping it into Discord."""

    # Unwrap CommandInvokeError to see the real cause
    original = getattr(error_, "original", error_)

    if isinstance(error_, commands.CommandNotFound):
        return  # silently ignore unknown commands

    if isinstance(error_, BladeError):
        await ctx.send(embed=embeds.error(str(error_)))
        return

    if isinstance(error_, commands.MissingPermissions):
        perms = ", ".join(error_.missing_permissions)
        await ctx.send(embed=embeds.error(f"You are missing the following permission(s): `{perms}`"))
        return

    if isinstance(error_, commands.BotMissingPermissions):
        perms = ", ".join(error_.missing_permissions)
        await ctx.send(embed=embeds.error(f"I am missing the following permission(s): `{perms}`"))
        return

    if isinstance(error_, commands.MissingRequiredArgument):
        from core.command_meta import registry
        meta = registry.get(ctx.command.qualified_name) if ctx.command else None
        if meta is not None and meta.require_args and not meta.no_help_on_empty:
            from core.help_formatter import command_usage_embed
            await ctx.send(embed=command_usage_embed(meta, ctx.author))
            return
        await ctx.send(embed=embeds.error(f"Missing required argument: `{error_.param.name}`"))
        return

    if isinstance(error_, commands.MemberNotFound):
        await ctx.send(embed=embeds.error(f"Member `{error_.argument}` not found."))
        return

    if isinstance(error_, commands.RoleNotFound):
        await ctx.send(embed=embeds.error(f"Role `{error_.argument}` not found."))
        return

    if isinstance(error_, commands.ChannelNotFound):
        await ctx.send(embed=embeds.error(f"Channel `{error_.argument}` not found."))
        return

    if isinstance(error_, commands.BadArgument):
        await ctx.send(embed=embeds.error(str(error_) or "Invalid argument provided."))
        return

    if isinstance(error_, commands.CommandOnCooldown):
        await ctx.send(embed=embeds.warning(f"This command is on cooldown. Try again in {error_.retry_after:.1f}s."))
        return

    if isinstance(error_, commands.NoPrivateMessage):
        await ctx.send(embed=embeds.error("This command cannot be used in DMs."))
        return

    # A plain CheckFailure (not one of the more specific subclasses
    # above) means a custom check predicate returned False after
    # already telling the user why (e.g. requires_premium sends its
    # own gate embed) - nothing more to say, and definitely not a bug
    # worth a traceback.
    if isinstance(error_, commands.CheckFailure):
        return

    # Unhandled - log full traceback to console, show a generic message to the user.
    log.exception("Unhandled command error in '%s'", ctx.command, exc_info=original)
    await ctx.send(embed=embeds.error("Something went wrong running that command."))