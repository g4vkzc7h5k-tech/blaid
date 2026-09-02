"""Bump reminders for Disboard - ,bumpreminder. Category "Server".
Manage Guild required for configuration.

Detection: Disboard's bot posts an embed containing "Bump done" when
a /bump succeeds. The member who ran it is read from the message's
interaction metadata (discord.py 2.x) - if Disboard ever stops
attaching that, the thank-you/leaderboard still work, just without
crediting a specific member."""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands, tasks

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.bumpreminder_models import (
    BUMP_COOLDOWN_SECONDS,
    DEFAULT_REMINDER,
    DEFAULT_THANKYOU,
    DISBOARD_BOT_ID,
)
from database.database import get_session
from repositories import bumpreminder_repository


class BumpReminder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_reminders.start()

    def cog_unload(self) -> None:
        self._poll_reminders.cancel()

    # ---------------------------------------------------------- bump detection

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.id != DISBOARD_BOT_ID:
            return
        if not message.embeds:
            return

        description = (message.embeds[0].description or "").lower()
        if "bump done" not in description and "bump doné" not in description:
            return

        bumper = None
        interaction_meta = getattr(message, "interaction_metadata", None)
        if interaction_meta is not None:
            bumper = interaction_meta.user
        else:
            legacy_interaction = getattr(message, "interaction", None)
            if legacy_interaction is not None:
                bumper = legacy_interaction.user

        await self._handle_successful_bump(message.guild, bumper)

    async def _handle_successful_bump(self, guild: discord.Guild, bumper: discord.abc.User | None) -> None:
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_config(session, guild.id)
        if cfg is None or not cfg.enabled or not cfg.channel_id:
            return

        channel = guild.get_channel(cfg.channel_id)

        if bumper is not None:
            async with get_session() as session:
                await bumpreminder_repository.record_bump(session, guild.id, bumper.id)

        if channel is not None:
            resolved = resolve_variables(cfg.thankyou_message, guild=guild, member=bumper)
            parsed = parse_script(resolved)
            try:
                if parsed.embed is not None:
                    await channel.send(content=parsed.content, embed=parsed.embed)
                else:
                    await channel.send(resolved)
            except discord.HTTPException:
                pass

        next_bump_at = discord.utils.utcnow() + datetime.timedelta(seconds=BUMP_COOLDOWN_SECONDS)
        async with get_session() as session:
            fresh = await bumpreminder_repository.get_config(session, guild.id)
            await bumpreminder_repository.update_config(
                session, fresh, next_bump_at=next_bump_at, reminder_sent=False
            )

    # ---------------------------------------------------------- reminder poll

    @tasks.loop(seconds=60)
    async def _poll_reminders(self):
        now = discord.utils.utcnow()
        async with get_session() as session:
            due = await bumpreminder_repository.get_due_configs(session, now)

        for cfg in due:
            guild = self.bot.get_guild(cfg.guild_id)
            if guild is not None:
                channel = guild.get_channel(cfg.channel_id) if cfg.channel_id else None
                if channel is not None:
                    resolved = resolve_variables(cfg.reminder_message, guild=guild)
                    parsed = parse_script(resolved)
                    try:
                        if parsed.embed is not None:
                            await channel.send(content=parsed.content, embed=parsed.embed)
                        else:
                            await channel.send(resolved)
                    except discord.HTTPException:
                        pass

            async with get_session() as session:
                fresh = await bumpreminder_repository.get_config(session, cfg.guild_id)
                if fresh is not None:
                    await bumpreminder_repository.update_config(session, fresh, reminder_sent=True)

    @_poll_reminders.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Bump reminders for Disboard.",
        syntax=",bumpreminder",
        examples=[],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.group(name="bumpreminder", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def bumpreminder(self, ctx: commands.Context):
        await send_help(ctx, "bumpreminder")

    @bumpreminder.command(name="help")
    async def bumpreminder_help(self, ctx: commands.Context):
        await send_help(ctx, "bumpreminder")

    # ---------------------------------------------------------- enable / disable

    @command_meta(
        category="Server",
        description="Turn on bump reminders in a channel.",
        syntax=",bumpreminder enable [channel]",
        examples=[",bumpreminder enable", ",bumpreminder enable #bump"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="enable")
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_enable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_or_create_config(session, ctx.guild.id)
            await bumpreminder_repository.update_config(session, cfg, enabled=True, channel_id=channel.id)

        await ctx.success(f"Bump reminders enabled in {channel.mention}.")

    @command_meta(
        category="Server",
        description="Turn off bump reminders.",
        syntax=",bumpreminder disable",
        examples=[",bumpreminder disable"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="disable")
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_disable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_or_create_config(session, ctx.guild.id)
            await bumpreminder_repository.update_config(session, cfg, enabled=False)

        await ctx.success("Bump reminders disabled.")

    # ---------------------------------------------------------- thankyou / reminder

    @command_meta(
        category="Server",
        description="Set the message sent right after a successful bump.",
        syntax=",bumpreminder thankyou [message]",
        examples=[",bumpreminder thankyou Thanks {user.mention}! Back in 2 hours."],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="thankyou", aliases=["thanks"])
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_thankyou(self, ctx: commands.Context, *, message: str = None):
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_or_create_config(session, ctx.guild.id)
            await bumpreminder_repository.update_config(session, cfg, thankyou_message=message or DEFAULT_THANKYOU)

        await ctx.success("Updated the thank-you message." if message else "Reset the thank-you message to the default.")

    @command_meta(
        category="Server",
        description="Set the message sent when it's time to bump again.",
        syntax=",bumpreminder reminder [message]",
        examples=[",bumpreminder reminder Time to bump again! Use /bump"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="reminder")
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_reminder(self, ctx: commands.Context, *, message: str = None):
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_or_create_config(session, ctx.guild.id)
            await bumpreminder_repository.update_config(session, cfg, reminder_message=message or DEFAULT_REMINDER)

        await ctx.success("Updated the reminder message." if message else "Reset the reminder message to the default.")

    # ---------------------------------------------------------- view / test

    @command_meta(
        category="Server",
        description="Show the current bump reminder configuration.",
        syntax=",bumpreminder view",
        examples=[",bumpreminder view"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_view(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_config(session, ctx.guild.id)

        if cfg is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Bump reminders aren't configured yet.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        channel = ctx.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        next_bump = discord.utils.format_dt(cfg.next_bump_at, style="R") if cfg.next_bump_at else "Not scheduled"

        description = (
            f"**Enabled** {'✅' if cfg.enabled else '❌'}\n"
            f"**Channel** {channel.mention if channel else 'Not set'}\n"
            f"**Next reminder** {next_bump}\n\n"
            f"**Thank-you message**\n{cfg.thankyou_message}\n\n"
            f"**Reminder message**\n{cfg.reminder_message}"
        )
        embed = discord.Embed(title="Bump Reminder Configuration", description=description[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Preview both the thank-you and reminder messages.",
        syntax=",bumpreminder test",
        examples=[",bumpreminder test"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="test")
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_test(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await bumpreminder_repository.get_or_create_config(session, ctx.guild.id)

        thankyou_resolved = resolve_variables(cfg.thankyou_message, guild=ctx.guild, member=ctx.author)
        reminder_resolved = resolve_variables(cfg.reminder_message, guild=ctx.guild)

        await ctx.send(embed=discord.Embed(title="Preview: Thank-you", description=thankyou_resolved))
        await ctx.send(embed=discord.Embed(title="Preview: Reminder", description=reminder_resolved))

    # ---------------------------------------------------------- leaderboard

    @command_meta(
        category="Server",
        description="Shows who has bumped the server the most.",
        syntax=",bumpreminder leaderboard",
        examples=[",bumpreminder leaderboard"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @bumpreminder.command(name="leaderboard", aliases=["lb"])
    @has_permission_or_fake("manage_guild")
    async def bumpreminder_leaderboard(self, ctx: commands.Context):
        async with get_session() as session:
            entries = await bumpreminder_repository.get_leaderboard(session, ctx.guild.id)

        if not entries:
            await ctx.info("No bumps recorded yet.")
            return

        lines = [f"`{i}` <@{e.user_id}> — {e.bump_count} bump(s)" for i, e in enumerate(entries, start=1)]
        embed = discord.Embed(title="Bump Leaderboard", description="\n".join(lines))
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpReminder(bot))
