"""Automatic reactions to message keywords - ,autoreact (alias
,autoreactions). Category "Server". All subcommands need Manage
Messages."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import autoreact_repository


class AutoReact(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        async with get_session() as session:
            rows = await autoreact_repository.get_all_for_guild(session, message.guild.id)

        if not rows:
            return

        content_lower = message.content.lower()
        for row in rows:
            if row.keyword.lower() in content_lower:
                for emoji in row.emojis.split(","):
                    try:
                        await message.add_reaction(emoji.strip())
                    except discord.HTTPException:
                        pass

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Automatic reactions to message keywords.",
        syntax=",autoreact",
        examples=[],
        permissions=["Manage Messages"],
        aliases=["autoreactions"],
        require_args=False,
    )
    @commands.group(name="autoreact", aliases=["autoreactions"], invoke_without_command=True, with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.guild_only()
    async def autoreact(self, ctx: commands.Context):
        await send_help(ctx, "autoreact")

    @autoreact.command(name="help")
    async def autoreact_help(self, ctx: commands.Context):
        await send_help(ctx, "autoreact")

    # ---------------------------------------------------------- add

    @command_meta(
        category="Server",
        description="React with emojis on messages containing a keyword.",
        syntax=",autoreact add <keyword> <emojis>",
        examples=[",autoreact add good morning ☀️ 😊"],
        permissions=["Manage Messages"],
    )
    @autoreact.command(name="add")
    @has_permission_or_fake("manage_messages")
    async def autoreact_add(self, ctx: commands.Context, keyword: str, *, emojis: str):
        cleaned = ",".join(e.strip() for e in emojis.split() if e.strip())
        if not cleaned:
            await ctx.error("Provide at least one emoji.")
            return

        async with get_session() as session:
            is_new = await autoreact_repository.add_autoreact(session, ctx.guild.id, keyword.lower(), cleaned)

        if is_new:
            await ctx.success(f"Now reacting with {cleaned} on messages containing `{keyword}`.")
        else:
            await ctx.success(f"Updated the reaction for `{keyword}` to {cleaned}.")

    # ---------------------------------------------------------- remove / clear / list

    @command_meta(
        category="Server",
        description="Remove an autoreact.",
        syntax=",autoreact remove <keyword>",
        examples=[",autoreact remove good morning"],
        permissions=["Manage Messages"],
    )
    @autoreact.command(name="remove")
    @has_permission_or_fake("manage_messages")
    async def autoreact_remove(self, ctx: commands.Context, *, keyword: str):
        async with get_session() as session:
            removed = await autoreact_repository.remove_autoreact(session, ctx.guild.id, keyword.lower())

        if removed:
            await ctx.success(f"Removed the autoreact for `{keyword}`.")
        else:
            await ctx.error(f"No autoreact found for `{keyword}`.")

    @command_meta(
        category="Server",
        description="Remove all autoreacts.",
        syntax=",autoreact clear",
        examples=[",autoreact clear"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @autoreact.command(name="clear")
    @has_permission_or_fake("manage_messages")
    async def autoreact_clear(self, ctx: commands.Context):
        async with get_session() as session:
            count = await autoreact_repository.clear_autoreacts(session, ctx.guild.id)

        await ctx.success(f"Removed {count} autoreact(s).")

    @command_meta(
        category="Server",
        description="List all autoreacts.",
        syntax=",autoreact list",
        examples=[",autoreact list"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @autoreact.command(name="list")
    @has_permission_or_fake("manage_messages")
    async def autoreact_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await autoreact_repository.get_all_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No autoreacts configured.")
            return

        lines = [f"`{row.keyword}` → {row.emojis}" for row in rows]
        embed = discord.Embed(title="Autoreacts", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReact(bot))