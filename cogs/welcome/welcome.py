"""Welcome message system."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from sqlalchemy import select

from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.welcome_models import WelcomeConfig


async def _get_or_create(session, guild_id: int) -> WelcomeConfig:
    result = await session.execute(select(WelcomeConfig).where(WelcomeConfig.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = WelcomeConfig(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _send_rendered(channel: discord.abc.Messageable, template: str, member: discord.Member) -> None:
    """Resolves variables then parses the {embed} script syntax, so the
    welcome message can be plain text or a full embed."""
    resolved = resolve_variables(template, member=member)
    parsed = parse_script(resolved)
    if parsed.embed is not None or parsed.content:
        await channel.send(content=parsed.content, embed=parsed.embed)
    else:
        await channel.send(resolved)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            cfg = await _get_or_create(session, member.guild.id)

        if not cfg.enabled or not cfg.channel_id:
            return

        channel = member.guild.get_channel(cfg.channel_id)
        if channel is None:
            return

        try:
            await _send_rendered(channel, cfg.message, member)
        except discord.HTTPException:
            pass

    # ---------------------------------------------------------- ,welcome

    @command_meta(
        category="Server",
        description="Configures welcome messages for new members.",
        syntax=",welcome",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["wlc"],
        require_args=False,
    )
    @commands.group(name="welcome", aliases=["wlc"], invoke_without_command=True)
    @commands.guild_only()
    async def welcome(self, ctx: commands.Context):
        await send_help(ctx, "welcome")

    @welcome.command(name="help")
    async def welcome_help(self, ctx: commands.Context):
        await send_help(ctx, "welcome")

    @command_meta(
        category="Server",
        description="Sets the channel welcome messages are sent in.",
        syntax=",welcome channel <channel>",
        examples=[",welcome channel #welcome"],
        permissions=["Manage Guild"],
    )
    @welcome.command(name="channel")
    @has_permission_or_fake("manage_guild")
    async def welcome_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.channel_id = channel.id
            cfg.enabled = True
            await session.commit()
        await ctx.success(f"Welcome messages will be sent in {channel.mention}.")

    @welcome.command(name="message")
    @has_permission_or_fake("manage_guild")
    async def welcome_message(self, ctx: commands.Context, *, text: str):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.message = text
            await session.commit()
        await ctx.success("Welcome message updated.")

    @command_meta(
        category="Server",
        description="Completely resets the welcome system - clears the channel, message, and turns it off.",
        syntax=",welcome reset",
        examples=[",welcome reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @welcome.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def welcome_reset(self, ctx: commands.Context):
        async with get_session() as session:
            result = await session.execute(select(WelcomeConfig).where(WelcomeConfig.guild_id == ctx.guild.id))
            cfg = result.scalar_one_or_none()
            if cfg is not None:
                await session.delete(cfg)
                await session.commit()
        await ctx.success("Welcome system has been reset.")

    @command_meta(
        category="Server",
        description="Sends the welcome message right now, pinging you as if you had just joined.",
        syntax=",welcome test",
        examples=[",welcome test"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @welcome.command(name="test")
    @has_permission_or_fake("manage_guild")
    async def welcome_test(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)

        if not cfg.channel_id:
            await ctx.error("No welcome channel is set. Run `,welcome channel #channel` first.")
            return

        channel = ctx.guild.get_channel(cfg.channel_id)
        if channel is None:
            await ctx.error("The configured welcome channel no longer exists.")
            return

        await _send_rendered(channel, cfg.message, ctx.author)
        if channel.id != ctx.channel.id:
            await ctx.success(f"Test welcome message sent to {channel.mention}.")

    @command_meta(
        category="Server",
        description="Shows the raw welcome message template.",
        syntax=",welcome view",
        examples=[",welcome view"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @welcome.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def welcome_view(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
        await ctx.send(embed=discord.Embed(description=f"```{cfg.message}```"))

    @welcome.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def welcome_toggle(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.enabled = not cfg.enabled
            await session.commit()
        await ctx.success(f"Welcome messages are now **{'on' if cfg.enabled else 'off'}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))