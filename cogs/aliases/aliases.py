"""Command alias management. Resolution itself happens in core/bot.py's
on_message before commands are dispatched."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake

from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import alias_repository


class Aliases(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @command_meta(
        category="Server",
        description="Manages custom command aliases for this server. Use {0}, {1}, ... in the template for arguments.",
        syntax=",alias <add|remove|view|list>",
        examples=[",alias add sp warn {0} Spamming", ",alias list"],
        permissions=["Manage Guild"],
    )
    @commands.group(name="alias", invoke_without_command=True)
    @commands.guild_only()
    @has_permission_or_fake("manage_guild")
    async def alias(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @alias.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def alias_add(self, ctx: commands.Context, alias_name: str, *, command_template: str):
        alias_name = alias_name.lower()
        async with get_session() as session:
            await alias_repository.add_alias(session, ctx.guild.id, alias_name, command_template)
        await ctx.success(f"Alias `{alias_name}` now runs `{command_template}`.")

    @alias.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def alias_remove(self, ctx: commands.Context, alias_name: str):
        async with get_session() as session:
            removed = await alias_repository.remove_alias(session, ctx.guild.id, alias_name.lower())
        if removed:
            await ctx.success(f"Alias `{alias_name}` removed.")
        else:
            await ctx.error(f"No alias named `{alias_name}`.")

    @alias.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def alias_view(self, ctx: commands.Context, alias_name: str):
        async with get_session() as session:
            entry = await alias_repository.get_alias(session, ctx.guild.id, alias_name.lower())
        if entry is None:
            await ctx.error(f"No alias named `{alias_name}`.")
            return
        await ctx.send(embed=discord.Embed(title=f"Alias: {entry.alias_name}", description=f"```{entry.command_template}```"))

    @alias.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def alias_list(self, ctx: commands.Context):
        async with get_session() as session:
            aliases = await alias_repository.get_aliases(session, ctx.guild.id)
        if not aliases:
            await ctx.info("No aliases configured.")
            return
        lines = [f"`{a.alias_name}` → `{a.command_template}`" for a in aliases]
        await ctx.send(embed=discord.Embed(title="Command Aliases", description="\n".join(lines)[:4000]))


async def setup(bot: commands.Bot):
    await bot.add_cog(Aliases(bot))