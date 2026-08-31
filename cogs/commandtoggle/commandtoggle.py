""",enable and ,disable - two separate top-level commands. Category
"Server". Administrator only.

With no target, applies server-wide. With a channel or role target,
applies only there. Enforced via a bot-wide check so it covers every
command without needing to touch each one individually."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.command_meta import command_meta
from database.database import get_session
from repositories import command_toggle_repository

PROTECTED_COMMANDS = {"enable", "disable"}


async def _resolve_target(ctx: commands.Context, target: str | None) -> tuple[int, str] | None:
    """Returns (target_id, display_name), or None if target couldn't
    be resolved. target_id is 0 for "server-wide" (no target given)."""
    if target is None:
        return 0, "this server"

    try:
        channel = await commands.TextChannelConverter().convert(ctx, target)
        return channel.id, channel.mention
    except commands.BadArgument:
        pass

    try:
        role = await commands.RoleConverter().convert(ctx, target)
        return role.id, role.mention
    except commands.BadArgument:
        pass

    return None


def _resolve_command_name(bot: commands.Bot, name: str) -> str | None:
    command = bot.get_command(name.lower())
    if command is None:
        return None
    return command.qualified_name.split()[0]  # root command name - disabling covers the whole family


class CommandToggle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_check(self._global_check)

    def cog_unload(self) -> None:
        self.bot.remove_check(self._global_check)

    async def _global_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or ctx.command is None:
            return True

        root_name = ctx.command.qualified_name.split()[0]
        target_ids = [0, ctx.channel.id] + [r.id for r in getattr(ctx.author, "roles", [])]

        async with get_session() as session:
            disabled = await command_toggle_repository.is_disabled(session, ctx.guild.id, root_name, target_ids)

        return not disabled

    # ---------------------------------------------------------- enable

    @command_meta(
        category="Server",
        description="Re-enable a command in this server.",
        syntax=",enable <command> [target]",
        examples=[",enable ban", ",enable ban #general", ",enable ban @Moderator"],
        permissions=["Administrator"],
    )
    @commands.command(name="enable", with_app_command=False)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def enable(self, ctx: commands.Context, command: str, *, target: str = None):
        root_name = _resolve_command_name(self.bot, command)
        if root_name is None:
            await ctx.error(f"No command named `{command}` found.")
            return

        resolved = await _resolve_target(ctx, target)
        if resolved is None:
            await ctx.error(f"Couldn't find a channel or role matching `{target}`.")
            return
        target_id, target_display = resolved

        async with get_session() as session:
            enabled = await command_toggle_repository.enable_command(session, ctx.guild.id, root_name, target_id)

        if enabled:
            await ctx.success(f"Re-enabled `,{root_name}` in {target_display}.")
        else:
            await ctx.error(f"`,{root_name}` isn't disabled in {target_display}.")

    # ---------------------------------------------------------- disable

    @command_meta(
        category="Server",
        description="Disable a command in this server.",
        syntax=",disable <command> [target]",
        examples=[",disable ban", ",disable ban #general", ",disable ban @Moderator"],
        permissions=["Administrator"],
    )
    @commands.command(name="disable", with_app_command=False)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def disable(self, ctx: commands.Context, command: str, *, target: str = None):
        root_name = _resolve_command_name(self.bot, command)
        if root_name is None:
            await ctx.error(f"No command named `{command}` found.")
            return

        if root_name in PROTECTED_COMMANDS:
            await ctx.error(f"`,{root_name}` can't be disabled - you'd lock yourself out of turning it back on.")
            return

        resolved = await _resolve_target(ctx, target)
        if resolved is None:
            await ctx.error(f"Couldn't find a channel or role matching `{target}`.")
            return
        target_id, target_display = resolved

        async with get_session() as session:
            disabled = await command_toggle_repository.disable_command(session, ctx.guild.id, root_name, target_id)

        if disabled:
            await ctx.success(f"Disabled `,{root_name}` in {target_display}.")
        else:
            await ctx.error(f"`,{root_name}` is already disabled in {target_display}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandToggle(bot))