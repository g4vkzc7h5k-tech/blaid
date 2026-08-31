"""Briefly pings new members in a channel on join - ,pingonjoin (alias
,poj). Category "Server". All subcommands need Manage Guild."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.pingonjoin_models import DEFAULT_MESSAGE
from repositories import pingonjoin_repository


class PingOnJoin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_config(session, member.guild.id)

        if cfg is None or not cfg.enabled or not cfg.channel_id:
            return

        channel = member.guild.get_channel(cfg.channel_id)
        if channel is None:
            return

        resolved = resolve_variables(cfg.message_template, guild=member.guild, member=member)
        parsed = parse_script(resolved)

        try:
            if parsed.embed is not None:
                message = await channel.send(content=parsed.content, embed=parsed.embed)
            else:
                message = await channel.send(resolved)
        except discord.HTTPException:
            return

        try:
            await message.delete(delay=cfg.delete_after_seconds)
        except discord.HTTPException:
            pass

    async def _send_config_embed(self, ctx: commands.Context, cfg) -> None:
        channel = ctx.guild.get_channel(cfg.channel_id)
        channel_display = channel.mention if channel else f"`{cfg.channel_id}` (deleted)"
        embed = discord.Embed(
            description=f"{ctx.author.mention}: Pinging new members in {channel_display} (auto deletes after **{cfg.delete_after_seconds}s**)"
        )
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Briefly ping new members in a channel.",
        syntax=",pingonjoin",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["poj"],
        require_args=False,
    )
    @commands.hybrid_group(name="pingonjoin", aliases=["poj"], invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def pingonjoin(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_config(session, ctx.guild.id)

        if cfg is None or not cfg.enabled or not cfg.channel_id:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Ping-on-join isn't configured. Use `pingonjoin enable (channel)`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        await self._send_config_embed(ctx, cfg)

    @pingonjoin.command(name="help")
    async def pingonjoin_help(self, ctx: commands.Context):
        await send_help(ctx, "pingonjoin")

    # ---------------------------------------------------------- enable / disable / info

    @command_meta(
        category="Server",
        description="Ping new members in a channel.",
        syntax=",pingonjoin enable <channel> [seconds]",
        examples=[",pingonjoin enable #welcome", ",pingonjoin enable #welcome 5"],
        permissions=["Manage Guild"],
    )
    @pingonjoin.command(name="enable")
    @has_permission_or_fake("manage_guild")
    async def pingonjoin_enable(self, ctx: commands.Context, channel: discord.TextChannel, seconds: int = 1):
        seconds = max(1, seconds)
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_or_create_config(session, ctx.guild.id)
            await pingonjoin_repository.update_config(
                session, cfg, channel_id=channel.id, delete_after_seconds=seconds, enabled=True,
            )

        await ctx.success(f"{ctx.author.mention}: New members will be pinged in {channel.mention} (deletes after **{seconds}s**)")

    @command_meta(
        category="Server",
        description="Turn off ping-on-join.",
        syntax=",pingonjoin disable",
        examples=[",pingonjoin disable"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @pingonjoin.command(name="disable")
    @has_permission_or_fake("manage_guild")
    async def pingonjoin_disable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_or_create_config(session, ctx.guild.id)
            await pingonjoin_repository.update_config(session, cfg, enabled=False)

        await ctx.success(f"{ctx.author.mention}: Disabled ping-on-join.")

    @command_meta(
        category="Server",
        description="Show the config.",
        syntax=",pingonjoin info",
        examples=[",pingonjoin info"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @pingonjoin.command(name="info")
    @has_permission_or_fake("manage_guild")
    async def pingonjoin_info(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_config(session, ctx.guild.id)

        if cfg is None or not cfg.enabled or not cfg.channel_id:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Ping-on-join isn't configured. Use `pingonjoin enable (channel)`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        await self._send_config_embed(ctx, cfg)

    # ---------------------------------------------------------- message

    @command_meta(
        category="Server",
        description="Set a custom ping message.",
        syntax=",pingonjoin message [text]",
        examples=[",pingonjoin message Welcome {user.mention} to {guild.name}!"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @pingonjoin.command(name="message", aliases=["msg", "template"])
    @has_permission_or_fake("manage_guild")
    async def pingonjoin_message(self, ctx: commands.Context, *, text: str = None):
        async with get_session() as session:
            cfg = await pingonjoin_repository.get_or_create_config(session, ctx.guild.id)
            await pingonjoin_repository.update_config(session, cfg, message_template=text or DEFAULT_MESSAGE)

        await ctx.success(f"{ctx.author.mention}: Updated the ping-on-join message.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PingOnJoin(bot))