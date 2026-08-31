"""Builds the ,prefix info response - shared between the ,prefix
command itself and the bare-mention (@Blade) listener in core/bot.py,
so both show exactly the same message."""

from __future__ import annotations

from discord.ext import commands

from config import config
from core import embeds


async def send_prefix_info(ctx: commands.Context) -> None:
    bot = ctx.bot
    if ctx.guild is not None:
        prefix = bot.guild_prefixes.get(ctx.guild.id, config.default_prefix)
    else:
        prefix = config.default_prefix

    bot_name = bot.user.name if bot.user else "Blaid"
    description = (
        f"{ctx.author.mention}: **{bot_name}'s prefix** for this **server** is `{prefix}`\n"
        f"↳ Set a new prefix by using `{prefix}prefix set`"
    )
    await ctx.send(embed=embeds.success(description))
