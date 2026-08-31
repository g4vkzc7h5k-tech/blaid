"""Leave (goodbye) message system."""

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
from database.welcome_models import GoodbyeConfig


async def _get_or_create(session, guild_id: int) -> GoodbyeConfig:
    result = await session.execute(select(GoodbyeConfig).where(GoodbyeConfig.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = GoodbyeConfig(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _send_rendered(channel: discord.abc.Messageable, template: str, member: discord.Member) -> None:
    """Resolves variables then parses the {embed} script syntax, so the
    leave message can be plain text or a full embed."""
    resolved = resolve_variables(template, member=member)
    parsed = parse_script(resolved)
    if parsed.embed is not None or parsed.content:
        await channel.send(content=parsed.content, embed=parsed.embed)
    else:
        await channel.send(resolved)


class Leave(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
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

    # ---------------------------------------------------------- ,leave

    @command_meta(
        category="Server",
        description="Configures leave messages for members who leave the server.",
        syntax=",leave",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["bye", "goodbye"],
        require_args=False,
    )
    @commands.group(name="leave", aliases=["bye", "goodbye"], invoke_without_command=True)
    @commands.guild_only()
    async def leave(self, ctx: commands.Context):
        await send_help(ctx, "leave")

    @leave.command(name="help")
    async def leave_help(self, ctx: commands.Context):
        await send_help(ctx, "leave")

    @command_meta(
        category="Server",
        description="Sets the channel leave messages are sent in.",
        syntax=",leave channel <channel>",
        examples=[",leave channel #general"],
        permissions=["Manage Guild"],
    )
    @leave.command(name="channel")
    @has_permission_or_fake("manage_guild")
    async def leave_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.channel_id = channel.id
            cfg.enabled = True
            await session.commit()
        await ctx.success(f"Leave messages will be sent in {channel.mention}.")

    @leave.command(name="message")
    @has_permission_or_fake("manage_guild")
    async def leave_message(self, ctx: commands.Context, *, text: str):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.message = text
            await session.commit()
        await ctx.success("Leave message updated.")

    @command_meta(
        category="Server",
        description="Completely resets the leave system - clears the channel, message, and turns it off.",
        syntax=",leave reset",
        examples=[",leave reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @leave.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def leave_reset(self, ctx: commands.Context):
        async with get_session() as session:
            result = await session.execute(select(GoodbyeConfig).where(GoodbyeConfig.guild_id == ctx.guild.id))
            cfg = result.scalar_one_or_none()
            if cfg is not None:
                await session.delete(cfg)
                await session.commit()
        await ctx.success("Leave system has been reset.")

    @command_meta(
        category="Server",
        description="Sends the leave message right now, pinging you as if you had just left.",
        syntax=",leave test",
        examples=[",leave test"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @leave.command(name="test")
    @has_permission_or_fake("manage_guild")
    async def leave_test(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)

        if not cfg.channel_id:
            await ctx.error("No leave channel is set. Run `,leave channel #channel` first.")
            return

        channel = ctx.guild.get_channel(cfg.channel_id)
        if channel is None:
            await ctx.error("The configured leave channel no longer exists.")
            return

        await _send_rendered(channel, cfg.message, ctx.author)
        if channel.id != ctx.channel.id:
            await ctx.success(f"Test leave message sent to {channel.mention}.")

    @command_meta(
        category="Server",
        description="Shows the raw leave message template.",
        syntax=",leave view",
        examples=[",leave view"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @leave.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def leave_view(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
        await ctx.send(embed=discord.Embed(description=f"```{cfg.message}```"))

    @leave.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def leave_toggle(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await _get_or_create(session, ctx.guild.id)
            cfg.enabled = not cfg.enabled
            await session.commit()
        await ctx.success(f"Leave messages are now **{'on' if cfg.enabled else 'off'}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Leave(bot))