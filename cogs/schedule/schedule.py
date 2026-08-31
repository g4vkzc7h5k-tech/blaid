"""Scheduled messages - ,schedule (alias ,scheduled). Category
"Information". Not premium. All subcommands need Manage Guild."""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands, tasks

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.converters import Duration
from core.help_formatter import send_help
from database.database import get_session
from repositories import schedule_repository


class Schedule(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_scheduled.start()

    def cog_unload(self) -> None:
        self._poll_scheduled.cancel()

    @tasks.loop(seconds=30)
    async def _poll_scheduled(self):
        now = discord.utils.utcnow()
        async with get_session() as session:
            due = await schedule_repository.get_due(session, now)

        for item in due:
            channel = self.bot.get_channel(item.channel_id)
            if channel is not None:
                try:
                    await channel.send(item.message)
                except discord.HTTPException:
                    pass

            if item.interval_seconds:
                new_next = item.next_run_at
                while new_next <= now:
                    new_next += datetime.timedelta(seconds=item.interval_seconds)
                async with get_session() as session:
                    fresh = await schedule_repository.get_scheduled(session, item.id)
                    if fresh is not None:
                        await schedule_repository.update_scheduled(session, fresh, next_run_at=new_next)
            else:
                async with get_session() as session:
                    await schedule_repository.delete_scheduled(session, item.id)

    @_poll_scheduled.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------- root

    @command_meta(
        category="Information",
        description="Schedule messages to post later, once or on repeat.",
        syntax=",schedule",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["scheduled"],
        require_args=False,
    )
    @commands.group(name="schedule", aliases=["scheduled"], invoke_without_command=True, with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def schedule(self, ctx: commands.Context):
        await send_help(ctx, "schedule")

    @schedule.command(name="help")
    async def schedule_help(self, ctx: commands.Context):
        await send_help(ctx, "schedule")

    # ---------------------------------------------------------- add / repeat

    @command_meta(
        category="Information",
        description="Schedule a message.",
        syntax=",schedule add <channel> <when> <message>",
        examples=[",schedule add #announcements 2h We're back online!"],
        permissions=["Manage Guild"],
    )
    @schedule.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def schedule_add(self, ctx: commands.Context, channel: discord.TextChannel, when: Duration, *, message: str):
        next_run_at = discord.utils.utcnow() + datetime.timedelta(seconds=when)

        async with get_session() as session:
            row = await schedule_repository.create_scheduled(
                session, ctx.guild.id, channel.id, message, next_run_at, None, ctx.author.id,
            )

        await ctx.success(
            f"Scheduled message `#{row.id}` for {channel.mention} at "
            f"{discord.utils.format_dt(next_run_at, style='F')} ({discord.utils.format_dt(next_run_at, style='R')})."
        )

    @command_meta(
        category="Information",
        description="Schedule a repeating message.",
        syntax=",schedule repeat <channel> <every> <message>",
        examples=[",schedule repeat #reminders 1d Don't forget to check in!"],
        permissions=["Manage Guild"],
    )
    @schedule.command(name="repeat")
    @has_permission_or_fake("manage_guild")
    async def schedule_repeat(self, ctx: commands.Context, channel: discord.TextChannel, every: Duration, *, message: str):
        if every < 60:
            await ctx.error("The interval must be at least 1 minute.")
            return

        next_run_at = discord.utils.utcnow() + datetime.timedelta(seconds=every)

        async with get_session() as session:
            row = await schedule_repository.create_scheduled(
                session, ctx.guild.id, channel.id, message, next_run_at, every, ctx.author.id,
            )

        await ctx.success(
            f"Scheduled repeating message `#{row.id}` for {channel.mention}, first posting "
            f"{discord.utils.format_dt(next_run_at, style='R')}."
        )

    # ---------------------------------------------------------- cancel / list

    @command_meta(
        category="Information",
        description="Cancel a scheduled message.",
        syntax=",schedule cancel <id>",
        examples=[",schedule cancel 4"],
        permissions=["Manage Guild"],
    )
    @schedule.command(name="cancel")
    @has_permission_or_fake("manage_guild")
    async def schedule_cancel(self, ctx: commands.Context, scheduled_id: int):
        async with get_session() as session:
            removed = await schedule_repository.delete_scheduled(session, scheduled_id, guild_id=ctx.guild.id)

        if removed:
            await ctx.success(f"Cancelled scheduled message `#{scheduled_id}`.")
        else:
            await ctx.error(f"No scheduled message with ID `#{scheduled_id}` found in this server.")

    @command_meta(
        category="Information",
        description="List every scheduled message in this server.",
        syntax=",schedule list",
        examples=[",schedule list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @schedule.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def schedule_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await schedule_repository.get_all_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No scheduled messages.")
            return

        lines = []
        for row in rows:
            channel_display = f"<#{row.channel_id}>"
            when_display = discord.utils.format_dt(row.next_run_at, style="R")
            kind = f"every {row.interval_seconds}s" if row.interval_seconds else "one-time"
            preview = row.message if len(row.message) <= 50 else row.message[:47] + "..."
            lines.append(f"`#{row.id}` {channel_display} — {when_display} ({kind})\n> {preview}")

        embed = discord.Embed(title="Scheduled Messages", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Schedule(bot))