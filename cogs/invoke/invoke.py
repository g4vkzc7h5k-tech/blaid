"""Customize the DM/channel messages sent when moderation commands run
- ,invoke. Category "Server". Manage Guild required.

This holds the CONFIGURATION only (set/view/delete/list/reset/
variables). Actually using these custom messages inside ,ban/,kick/
etc. is a separate wiring step in services/moderation_service.py -
see invoke_repository.get_message() for the lookup those commands
should call before falling back to their own default message."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from database.invoke_models import VALID_COMMANDS, VALID_TYPES
from repositories import invoke_repository

VARIABLES_DESCRIPTION = (
    "**The member** `{user.mention}` `{user.name}` `{user.id}` `{user.avatar}`\n"
    "**The moderator** `{moderator.mention}` `{moderator.name}` `{moderator.id}`\n"
    "**The server** `{guild.name}` `{guild.id}` `{guild.icon}`\n"
    "**The action** `{custom.reason}` `{duration}` (timeout/jail only)"
)


class Invoke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _validate_command(command: str) -> str | None:
        command = command.lower().strip()
        return command if command in VALID_COMMANDS else None

    @staticmethod
    def _validate_type(message_type: str | None) -> str | bool | None:
        """Returns the normalized type, True for 'not given' (caller
        decides the meaning), or None if invalid."""
        if message_type is None:
            return True
        message_type = message_type.lower().strip()
        return message_type if message_type in VALID_TYPES else None

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Customize the DM/channel messages sent when moderation commands run.",
        syntax=",invoke (set | view | delete | list | reset | variables)",
        examples=[",invoke"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.group(name="invoke", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def invoke(self, ctx: commands.Context):
        await send_help(ctx, "invoke")

    @invoke.command(name="help")
    async def invoke_help(self, ctx: commands.Context):
        await send_help(ctx, "invoke")

    # ---------------------------------------------------------- set

    @command_meta(
        category="Server",
        description="Set a custom message for a moderation command.",
        syntax=",invoke set <command> <dm|text> <message>",
        examples=[",invoke set ban dm You were banned from {guild.name}. Reason: {custom.reason}"],
        permissions=["Manage Guild"],
    )
    @invoke.command(name="set")
    @has_permission_or_fake("manage_guild")
    async def invoke_set(self, ctx: commands.Context, command: str, message_type: str, *, message: str):
        resolved_command = self._validate_command(command)
        if resolved_command is None:
            await ctx.error(f"Unknown command `{command}`. Valid: {', '.join(VALID_COMMANDS)}.")
            return

        resolved_type = self._validate_type(message_type)
        if resolved_type in (None, True):
            await ctx.error(f"Type must be one of: {', '.join(VALID_TYPES)}.")
            return

        async with get_session() as session:
            await invoke_repository.set_message(session, ctx.guild.id, resolved_command, resolved_type, message)

        await ctx.success(f"Updated the **{resolved_type}** message for `,{resolved_command}`.")

    # ---------------------------------------------------------- view

    @command_meta(
        category="Server",
        description="View the custom message(s) for a moderation command.",
        syntax=",invoke view <command> [dm|text]",
        examples=[",invoke view ban", ",invoke view ban dm"],
        permissions=["Manage Guild"],
    )
    @invoke.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def invoke_view(self, ctx: commands.Context, command: str, message_type: str = None):
        resolved_command = self._validate_command(command)
        if resolved_command is None:
            await ctx.error(f"Unknown command `{command}`. Valid: {', '.join(VALID_COMMANDS)}.")
            return

        resolved_type = self._validate_type(message_type)
        if resolved_type is None:
            await ctx.error(f"Type must be one of: {', '.join(VALID_TYPES)}.")
            return

        types_to_check = VALID_TYPES if resolved_type is True else (resolved_type,)

        async with get_session() as session:
            lines = []
            for t in types_to_check:
                content = await invoke_repository.get_message(session, ctx.guild.id, resolved_command, t)
                lines.append(f"**{t}**\n{content if content else '*(default)*'}")

        embed = discord.Embed(title=f"Invoke: {resolved_command}", description="\n\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- delete

    @command_meta(
        category="Server",
        description="Remove a custom message, reverting to the default.",
        syntax=",invoke delete <command> [dm|text]",
        examples=[",invoke delete ban", ",invoke delete ban text"],
        permissions=["Manage Guild"],
    )
    @invoke.command(name="delete")
    @has_permission_or_fake("manage_guild")
    async def invoke_delete(self, ctx: commands.Context, command: str, message_type: str = None):
        resolved_command = self._validate_command(command)
        if resolved_command is None:
            await ctx.error(f"Unknown command `{command}`. Valid: {', '.join(VALID_COMMANDS)}.")
            return

        resolved_type = self._validate_type(message_type)
        if resolved_type is None:
            await ctx.error(f"Type must be one of: {', '.join(VALID_TYPES)}.")
            return

        target_type = None if resolved_type is True else resolved_type

        async with get_session() as session:
            removed = await invoke_repository.delete_message(session, ctx.guild.id, resolved_command, target_type)

        if removed:
            await ctx.success(f"Removed the custom message(s) for `,{resolved_command}` - back to the default.")
        else:
            await ctx.error(f"No custom message found for `,{resolved_command}`.")

    # ---------------------------------------------------------- list

    @command_meta(
        category="Server",
        description="List every command with a custom message configured.",
        syntax=",invoke list",
        examples=[",invoke list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @invoke.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def invoke_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await invoke_repository.get_all_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No custom invoke messages configured.")
            return

        lines = [f"`,{row.command}` — **{row.message_type}**" for row in rows]
        embed = discord.Embed(title="Custom Invoke Messages", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- reset

    @command_meta(
        category="Server",
        description="Clear every custom invoke message for this server.",
        syntax=",invoke reset",
        examples=[",invoke reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @invoke.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def invoke_reset(self, ctx: commands.Context):
        async with get_session() as session:
            removed = await invoke_repository.reset_guild(session, ctx.guild.id)

        await ctx.success(f"Cleared {removed} custom invoke message(s).")

    # ---------------------------------------------------------- variables

    @command_meta(
        category="Server",
        description="Show the variables available in invoke messages.",
        syntax=",invoke variables",
        examples=[",invoke variables"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @invoke.command(name="variables", aliases=["vars"])
    @has_permission_or_fake("manage_guild")
    async def invoke_variables(self, ctx: commands.Context):
        embed = discord.Embed(title="Invoke Message Variables", description=VARIABLES_DESCRIPTION)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invoke(bot))
