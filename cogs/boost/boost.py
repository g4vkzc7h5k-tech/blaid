"""Server boost announcement system."""

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
from database.welcome_models import BoostConfig


async def _get_or_create(session, guild_id: int) -> BoostConfig:
    result = await session.execute(select(BoostConfig).where(BoostConfig.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = BoostConfig(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _send_rendered(channel: discord.abc.Messageable, template: str, member: discord.Member) -> None:
    """Resolves variables then parses the {embed} script syntax, so the
    boost message can be plain text or a full embed."""
    resolved = resolve_variables(template, member=member)
    parsed = parse_script(resolved)
    if parsed.embed is not None or parsed.content:
        await channel.send(content=parsed.content, embed=parsed.embed)
    else:
        await channel.send(resolved)


class Boost(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            async with get_session() as session:
                cfg = await _get_or_create(session, after.guild.id)

            if not cfg.enabled or not cfg.channel_id:
                return

            channel = after.guild.get_channel(cfg.channel_id)
            if channel is None:
                return

            try:
                await _send_rendered(channel, cfg.message, after)
            except discord.HTTPException:
                pass

    # ---------------------------------------------------------- ,boost

    @command_meta(
        category="Server",
        description="Configures server boost announcement messages.",
        syntax=",boost",
        examples=[],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.group(name="boost", invoke_without_command=True)
    @commands.guild_only()
    async def boost(self, ctx: commands.Context):
        await send_help(ctx, "boost")

    @boost.command(name="help")
    async def boost_help(self, ctx: commands.Context):
        await send_help(ctx, "boost")

    @command_meta(
        category="Server",
        description="Sets the channel boost messages are sent in.",
        syntax=",boost channel <channel>",
        examples=[",boost channel #boosts"],
        permissions=["Manage Guild"],
    )
    @boost.command(name="channel")
    @has_permission_or_fake("manage_guild")
    async def boost_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.channel_id = channel.id
            cfg.enabled = True
            await session.commit()
        await ctx.success(f"Boost messages will be sent in {channel.mention}.")

    @boost.command(name="message")
    @has_permission_or_fake("manage_guild")
    async def boost_message(self, ctx: commands.Context, *, text: str):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.message = text
            await session.commit()
        await ctx.success("Boost message updated.")

    @command_meta(
        category="Server",
        description="Completely resets the boost system - clears the channel, message, and turns it off.",
        syntax=",boost reset",
        examples=[",boost reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boost.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def boost_reset(self, ctx: commands.Context):
        async with get_session() as session:
            result = await session.execute(select(BoostConfig).where(BoostConfig.guild_id == ctx.guild.id))
            cfg = result.scalar_one_or_none()
            if cfg is not None:
                await session.delete(cfg)
                await session.commit()
        await ctx.success("Boost system has been reset.")

    @command_meta(
        category="Server",
        description="Sends the boost message right now, pinging you as if you had just boosted.",
        syntax=",boost test",
        examples=[",boost test"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boost.command(name="test")
    @has_permission_or_fake("manage_guild")
    async def boost_test(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)

        if not cfg.channel_id:
            await ctx.error("No boost channel is set. Run `,boost channel #channel` first.")
            return

        channel = ctx.guild.get_channel(cfg.channel_id)
        if channel is None:
            await ctx.error("The configured boost channel no longer exists.")
            return

        await _send_rendered(channel, cfg.message, ctx.author)
        if channel.id != ctx.channel.id:
            await ctx.success(f"Test boost message sent to {channel.mention}.")

    @command_meta(
        category="Server",
        description="Shows the raw boost message template.",
        syntax=",boost view",
        examples=[",boost view"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boost.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def boost_view(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
        await ctx.send(embed=discord.Embed(description=f"```{cfg.message}```"))

    @boost.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def boost_toggle(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.enabled = not cfg.enabled
            await session.commit()
        await ctx.success(f"Boost messages are now **{'on' if cfg.enabled else 'off'}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))