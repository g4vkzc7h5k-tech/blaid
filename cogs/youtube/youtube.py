"""
YouTube upload/live announcements - ,youtube (alias ,yt). Category
"Socials". All management subcommands need Manage Guild; ,youtube
variables is open to everyone.

Polls followed channels every 3 minutes: cheap playlistItems.list
call for the latest upload, and (only for channels with live
announcements enabled) a cheap videos.list call to check
liveBroadcastContent - see services/youtube_service.py for why this
avoids the expensive search.list endpoint entirely.
"""

from __future__ import annotations

import discord
from discord.ext import commands, tasks

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.youtube_models import DEFAULT_MESSAGE
from repositories import youtube_repository
from services import youtube_service

VARIABLES = [
    "{youtube.url}", "{youtube.title}", "{youtube.channel}", "{youtube.channel.name}",
    "{youtube.channel.url}", "{youtube.thumbnail}", "{youtube.id}", "{youtube.published}",
]


class Youtube(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_uploads.start()

    def cog_unload(self) -> None:
        self._poll_uploads.cancel()

    async def _announce(self, follow, video: dict) -> None:
        channel = self.bot.get_channel(follow.discord_channel_id)
        if channel is None:
            return

        youtube_data = {
            "url": video["url"],
            "title": video["title"],
            "channel_name": follow.channel_title or follow.channel_query,
            "channel_url": f"https://www.youtube.com/channel/{follow.youtube_channel_id}",
            "thumbnail": video.get("thumbnail", ""),
            "id": video["id"],
            "published": video.get("published", ""),
        }

        guild = getattr(channel, "guild", None)
        resolved = resolve_variables(follow.message_template, guild=guild, youtube=youtube_data)
        parsed = parse_script(resolved)
        role_prefix = f"<@&{follow.role_id}> " if follow.role_id else ""

        try:
            if parsed.embed is not None:
                content = (role_prefix + (parsed.content or "")).strip() or None
                await channel.send(content=content, embed=parsed.embed)
            else:
                await channel.send(role_prefix + resolved)
        except discord.HTTPException:
            pass

    @tasks.loop(minutes=3)
    async def _poll_uploads(self):
        async with get_session() as session:
            follows = await youtube_repository.get_all_follows(session)

        for follow in follows:
            if not follow.uploads_playlist_id:
                continue

            video = await youtube_service.get_latest_video(follow.uploads_playlist_id)
            new_upload = video is not None and video["id"] != follow.last_video_id

            if new_upload:
                await self._announce(follow, video)

            newly_live = False
            if follow.live_enabled and video is not None:
                status = await youtube_service.get_video_live_status(video["id"])
                is_live_now = status == "live"
                newly_live = is_live_now and not follow.is_live
                if newly_live and not new_upload:
                    await self._announce(follow, video)
                async with get_session() as session:
                    fresh = await youtube_repository.get_follow(session, follow.guild_id, follow.channel_query)
                    if fresh is not None:
                        await youtube_repository.update_follow(session, fresh, is_live=is_live_now)

            if new_upload:
                async with get_session() as session:
                    fresh = await youtube_repository.get_follow(session, follow.guild_id, follow.channel_query)
                    if fresh is not None:
                        await youtube_repository.update_follow(session, fresh, last_video_id=video["id"])

    @_poll_uploads.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------- root

    @command_meta(
        category="Socials",
        description="YouTube upload/live announcements.",
        syntax=",youtube",
        examples=[],
        aliases=["yt"],
        require_args=False,
    )
    @commands.hybrid_group(name="youtube", aliases=["yt"], invoke_without_command=True)
    @commands.guild_only()
    async def youtube(self, ctx: commands.Context):
        await send_help(ctx, "youtube")

    @youtube.command(name="help")
    async def youtube_help(self, ctx: commands.Context):
        await send_help(ctx, "youtube")

    # ---------------------------------------------------------- add / remove / reset / list

    @command_meta(
        category="Socials",
        description="Post a channel's uploads in a channel.",
        syntax=",youtube add <channel_name> <channel>",
        examples=[",youtube add MrBeast #uploads"],
        permissions=["Manage Guild"],
    )
    @youtube.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def youtube_add(self, ctx: commands.Context, channel_name: str, channel: discord.TextChannel):
        resolved = await youtube_service.resolve_channel(channel_name)
        if resolved is None:
            await ctx.error(f"Couldn't find a YouTube channel matching `{channel_name}` (or YouTube isn't configured on this bot).")
            return

        async with get_session() as session:
            added = await youtube_repository.add_follow(
                session, ctx.guild.id, channel_name, channel.id,
                resolved["id"], resolved["uploads_playlist_id"], resolved["title"],
            )

        if added:
            await ctx.success(f"Now posting **{resolved['title']}**'s uploads in {channel.mention}.")
        else:
            await ctx.error(f"Already following `{channel_name}`.")

    @command_meta(
        category="Socials",
        description="Stop announcing a channel.",
        syntax=",youtube remove <channel_name>",
        examples=[",youtube remove MrBeast"],
        permissions=["Manage Guild"],
    )
    @youtube.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def youtube_remove(self, ctx: commands.Context, *, channel_name: str):
        async with get_session() as session:
            removed = await youtube_repository.remove_follow(session, ctx.guild.id, channel_name)
        if removed:
            await ctx.success(f"Stopped announcing `{channel_name}`.")
        else:
            await ctx.error(f"`{channel_name}` wasn't being announced.")

    @command_meta(
        category="Socials",
        description="Stop announcing every channel.",
        syntax=",youtube reset",
        examples=[",youtube reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @youtube.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def youtube_reset(self, ctx: commands.Context):
        async with get_session() as session:
            count = await youtube_repository.reset_guild_follows(session, ctx.guild.id)
        await ctx.success(f"Stopped announcing {count} channel(s).")

    @command_meta(
        category="Socials",
        description="List the YouTube channels this server follows.",
        syntax=",youtube list",
        examples=[",youtube list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @youtube.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def youtube_list(self, ctx: commands.Context):
        async with get_session() as session:
            follows = await youtube_repository.get_follows_for_guild(session, ctx.guild.id)

        if not follows:
            await ctx.info("This server isn't following any YouTube channels.")
            return

        lines = []
        for f in follows:
            discord_channel_display = f"<#{f.discord_channel_id}>"
            role_display = f" • pings <@&{f.role_id}>" if f.role_id else ""
            live_display = " • live alerts on" if f.live_enabled else ""
            lines.append(f"**{f.channel_query}** → {discord_channel_display}{role_display}{live_display}")

        embed = discord.Embed(title="Followed YouTube Channels", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- live / message / ping

    @command_meta(
        category="Socials",
        description="Also announce when the channel goes live.",
        syntax=",youtube live <channel_name> [enabled]",
        examples=[",youtube live MrBeast on", ",youtube live MrBeast off"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @youtube.command(name="live")
    @has_permission_or_fake("manage_guild")
    async def youtube_live(self, ctx: commands.Context, channel_name: str, enabled: str = None):
        value = enabled is None or enabled.lower() in ("on", "true", "enable", "enabled")

        async with get_session() as session:
            follow = await youtube_repository.get_follow(session, ctx.guild.id, channel_name)
            if follow is None:
                await ctx.error(f"`{channel_name}` isn't being announced. Add it first with `,youtube add`.")
                return
            await youtube_repository.update_follow(session, follow, live_enabled=value)

        await ctx.success(f"Live announcements for `{channel_name}` are now **{'enabled' if value else 'disabled'}**.")

    @command_meta(
        category="Socials",
        description="Set the message posted for this channel.",
        syntax=",youtube message <channel_name> [script]",
        examples=[",youtube message MrBeast {youtube.channel} just uploaded!"],
        permissions=["Manage Guild"],
    )
    @youtube.command(name="message", aliases=["msg", "template"])
    @has_permission_or_fake("manage_guild")
    async def youtube_message(self, ctx: commands.Context, channel_name: str, *, script: str = None):
        async with get_session() as session:
            follow = await youtube_repository.get_follow(session, ctx.guild.id, channel_name)
            if follow is None:
                await ctx.error(f"`{channel_name}` isn't being announced. Add it first with `,youtube add`.")
                return
            await youtube_repository.update_follow(session, follow, message_template=script or DEFAULT_MESSAGE)

        await ctx.success(f"Updated the announcement message for `{channel_name}`.")

    @command_meta(
        category="Socials",
        description="Ping a role when the channel uploads or goes live.",
        syntax=",youtube ping <channel_name> [role]",
        examples=[",youtube ping MrBeast @Uploads", ",youtube ping MrBeast"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @youtube.command(name="ping")
    @has_permission_or_fake("manage_guild")
    async def youtube_ping(self, ctx: commands.Context, channel_name: str, role: discord.Role = None):
        async with get_session() as session:
            follow = await youtube_repository.get_follow(session, ctx.guild.id, channel_name)
            if follow is None:
                await ctx.error(f"`{channel_name}` isn't being announced. Add it first with `,youtube add`.")
                return
            await youtube_repository.update_follow(session, follow, role_id=role.id if role else None)

        if role:
            await ctx.success(f"{role.mention} will now be pinged for `{channel_name}`.")
        else:
            await ctx.success(f"Removed the ping role for `{channel_name}`.")

    # ---------------------------------------------------------- variables

    @command_meta(
        category="Socials",
        description="Show the variables available in YouTube alerts.",
        syntax=",youtube variables",
        examples=[",youtube variables"],
        require_args=False,
    )
    @youtube.command(name="variables", aliases=["vars"])
    async def youtube_variables(self, ctx: commands.Context):
        description = (
            " ".join(f"`{v}`" for v in VARIABLES)
            + "\n\nUse these in `,youtube message` — everything else renders as normal script."
        )
        embed = discord.Embed(title="YouTube Alert Variables", description=description)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Youtube(bot))