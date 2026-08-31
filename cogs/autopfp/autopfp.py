"""Auto-post profile pictures to a channel on an interval - ,autopfp
(alias ,autopfps). Category "Server". Administrator only.

Only "anime" (illustrated, no real people) and "cats" (TheCatAPI)
categories exist - the other originally requested categories
(eboys/egirls/girls/roadmen) were declined: they map to communities
that repost real, unconsenting people's photos scraped from social
media, with a documented overlap with underage users, which isn't
something this bot automates."""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands, tasks

from core.command_meta import command_meta
from core.help_formatter import send_help
from database.autopfp_models import MAX_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS, VALID_CATEGORIES
from database.database import get_session
from repositories import autopfp_repository
from services import autopfp_service


class AutoPfp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_autopfp.start()

    def cog_unload(self) -> None:
        self._poll_autopfp.cancel()

    @tasks.loop(seconds=60)
    async def _poll_autopfp(self):
        now = discord.utils.utcnow()
        async with get_session() as session:
            due = await autopfp_repository.get_due(session, now)

        for row in due:
            channel = self.bot.get_channel(row.channel_id)
            categories = row.categories.split(",")

            if channel is not None:
                image_url = await autopfp_service.get_random_image(categories)
                if image_url:
                    embed = discord.Embed()
                    embed.set_image(url=image_url)
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException:
                        pass

            next_post_at = now + datetime.timedelta(seconds=row.interval_seconds)
            async with get_session() as session:
                fresh = await autopfp_repository.get_channel(session, row.guild_id, row.channel_id)
                if fresh is not None:
                    await autopfp_repository.update_channel(session, fresh, next_post_at=next_post_at)

    @_poll_autopfp.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Auto-post profile pictures to a channel on an interval.",
        syntax=",autopfp",
        examples=[],
        permissions=["Administrator"],
        aliases=["autopfps"],
        require_args=False,
    )
    @commands.group(name="autopfp", aliases=["autopfps"], invoke_without_command=True, with_app_command=False)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def autopfp(self, ctx: commands.Context):
        await send_help(ctx, "autopfp")

    @autopfp.command(name="help")
    async def autopfp_help(self, ctx: commands.Context):
        await send_help(ctx, "autopfp")

    # ---------------------------------------------------------- add

    @command_meta(
        category="Server",
        description="Post pfps to a channel. Categories: cats.",
        syntax=",autopfp add <channel> <categories>",
        examples=[",autopfp add #pfps cats"],
        permissions=["Administrator"],
    )
    @autopfp.command(name="add")
    @commands.has_permissions(administrator=True)
    async def autopfp_add(self, ctx: commands.Context, channel: discord.TextChannel, *, categories: str):
        chosen = [c.strip().lower() for c in categories.replace(",", " ").split() if c.strip()]
        valid = [c for c in chosen if c in VALID_CATEGORIES]
        invalid = [c for c in chosen if c not in VALID_CATEGORIES]

        if not valid:
            await ctx.error(f"No valid categories given. Valid: {', '.join(VALID_CATEGORIES)}.")
            return

        next_post_at = discord.utils.utcnow() + datetime.timedelta(seconds=3600)
        async with get_session() as session:
            await autopfp_repository.add_channel(
                session, ctx.guild.id, channel.id, ",".join(valid), 3600, next_post_at,
            )

        message = f"Now posting **{', '.join(valid)}** to {channel.mention} every hour by default."
        if invalid:
            message += f" (ignored unknown: {', '.join(invalid)})"
        message += " Use `,autopfp interval` to change how often."
        await ctx.success(message)

    # ---------------------------------------------------------- interval

    @command_meta(
        category="Server",
        description="How often to post (min 2 minutes, max 1 day).",
        syntax=",autopfp interval <channel> <every>",
        examples=[",autopfp interval #pfps 30m"],
        permissions=["Administrator"],
    )
    @autopfp.command(name="interval")
    @commands.has_permissions(administrator=True)
    async def autopfp_interval(self, ctx: commands.Context, channel: discord.TextChannel, every: str):
        from core.converters import Duration

        try:
            seconds = await Duration().convert(ctx, every)
        except commands.BadArgument:
            await ctx.error("Provide a valid duration, e.g. `30m`, `2h`, `1d`.")
            return

        if seconds < MIN_INTERVAL_SECONDS:
            await ctx.error("The interval must be at least 2 minutes.")
            return
        if seconds > MAX_INTERVAL_SECONDS:
            await ctx.error("The interval can be at most 1 day.")
            return

        async with get_session() as session:
            row = await autopfp_repository.get_channel(session, ctx.guild.id, channel.id)
            if row is None:
                await ctx.error(f"{channel.mention} isn't configured. Use `,autopfp add` first.")
                return
            next_post_at = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
            await autopfp_repository.update_channel(session, row, interval_seconds=seconds, next_post_at=next_post_at)

        await ctx.success(f"Now posting to {channel.mention} every **{every}**.")

    # ---------------------------------------------------------- list / remove / test

    @command_meta(
        category="Server",
        description="List the autopfp channels.",
        syntax=",autopfp list",
        examples=[",autopfp list"],
        permissions=["Administrator"],
        require_args=False,
    )
    @autopfp.command(name="list")
    @commands.has_permissions(administrator=True)
    async def autopfp_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await autopfp_repository.get_channels_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No autopfp channels configured.")
            return

        lines = []
        for row in rows:
            channel_display = f"<#{row.channel_id}>"
            lines.append(f"{channel_display} — {row.categories} — every {row.interval_seconds}s")

        embed = discord.Embed(title="Autopfp Channels", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Stop auto-posting to a channel.",
        syntax=",autopfp remove <channel>",
        examples=[",autopfp remove #pfps"],
        permissions=["Administrator"],
    )
    @autopfp.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def autopfp_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            removed = await autopfp_repository.remove_channel(session, ctx.guild.id, channel.id)

        if removed:
            await ctx.success(f"Stopped auto-posting to {channel.mention}.")
        else:
            await ctx.error(f"{channel.mention} isn't configured.")

    @command_meta(
        category="Server",
        description="Post one pfp to a configured channel now.",
        syntax=",autopfp test <channel>",
        examples=[",autopfp test #pfps"],
        permissions=["Administrator"],
    )
    @autopfp.command(name="test")
    @commands.has_permissions(administrator=True)
    async def autopfp_test(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            row = await autopfp_repository.get_channel(session, ctx.guild.id, channel.id)

        if row is None:
            await ctx.error(f"{channel.mention} isn't configured. Use `,autopfp add` first.")
            return

        categories = row.categories.split(",")
        image_url = await autopfp_service.get_random_image(categories)
        if image_url is None:
            await ctx.error("Couldn't fetch an image right now.")
            return

        embed = discord.Embed()
        embed.set_image(url=image_url)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            await ctx.error("I don't have permission to send messages in that channel.")
            return

        await ctx.success(f"Posted a test image to {channel.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoPfp(bot))