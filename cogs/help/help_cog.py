"""The ,help / ,h commands. All rendering logic lives in
core/help_formatter.py - this cog is intentionally thin."""

from __future__ import annotations

from discord.ext import commands

from core.command_meta import command_meta
from core.help_formatter import send_help


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @command_meta(
        category="Information",
        description="Shows this help menu, or details on a specific command/category.",
        syntax=",help [command or category]",
        examples=[",help", ",help ban", ",help Moderation"],
        aliases=["h"],
        require_args=False,
    )
    @commands.hybrid_command(name="help")
    async def help_command(self, ctx: commands.Context, *, query: str = None):
        await send_help(ctx, query)

    @commands.hybrid_command(name="h")
    async def h_command(self, ctx: commands.Context, *, query: str = None):
        await send_help(ctx, query)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))