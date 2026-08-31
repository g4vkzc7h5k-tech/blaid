"""
Twitch live announcements - ,twitch. Category "Socials". All
management subcommands need Manage Guild; ,twitch variables is open
to everyone.

Polls followed channels every 2 minutes via Twitch's Helix API and
announces on the live-edge (offline -> live, or a new stream ID while
already marked live, catching a restart between polls) - never on
going offline, since that wasn't requested.
"""

from __future__ import annotations

import discord
from discord.ext import commands, tasks

from core.checks import has_permission_or_fake, requires_premium
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.twitch_models import DEFAULT_MESSAGE
from repositories import twitch_repository
from services import twitch_service

VARIABLES = [
    "{twitch.url}", "{twitch.title}", "{twitch.category}", "{twitch.game}",
    "{twitch.viewers}", "{twitch.started}", "{twitch.thumbnail}", "{twitch.id}",
    "{twitch.creator}", "{twitch.creator.name}", "{twitch.creator.url}",
]


class Twitch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_streams.start()

    def cog_unload(self) -> None:
        self._poll_streams.cancel()

    async def _announce(self, follow, stream: dict, user_info: dict | None) -> None:
        channel = self.bot.get_channel(follow.channel_id)
        if channel is None:
            return

        display_name = user_info.get("display_name", follow.login) if user_info else follow.login
        twitch_data = {
            "url": f"https://twitch.tv/{follow.login}",
            "title": stream.get("title", ""),
            "category": stream.get("game_name", ""),
            "viewers": stream.get("viewer_count", 0),
            "started": stream.get("started_at", ""),
            "thumbnail": stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720"),
            "id": stream.get("id", ""),
            "creator_name": display_name,
            "creator_url": f"https://twitch.tv/{follow.login}",
        }

        guild = getattr(channel, "guild", None)
        resolved = resolve_variables(follow.message_template, guild=guild, twitch=twitch_data)
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

    @tasks.loop(minutes=2)
    async def _poll_streams(self):
        async with get_session() as session:
            follows = await twitch_repository.get_all_follows(session)

        for follow in follows:
            stream = await twitch_service.get_stream(follow.login)
            went_live = stream is not None and (not follow.is_live or follow.last_stream_id != stream.get("id"))

            if went_live:
                user_info = await twitch_service.get_user(follow.login)
                await self._announce(follow, stream, user_info)

            async with get_session() as session:
                fresh = await twitch_repository.get_follow(session, follow.guild_id, follow.login)
                if fresh is not None:
                    await twitch_repository.update_follow(
                        session, fresh,
                        is_live=stream is not None,
                        last_stream_id=stream.get("id") if stream else fresh.last_stream_id,
                    )

    @_poll_streams.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------- root

    @command_meta(
        category="Socials",
        description="Twitch live announcements.",
        syntax=",twitch",
        examples=[],
        require_args=False,
    )
    @commands.hybrid_group(name="twitch", invoke_without_command=True)
    @requires_premium("server")
    @commands.guild_only()
    async def twitch(self, ctx: commands.Context):
        await send_help(ctx, "twitch")

    @twitch.command(name="help")
    async def twitch_help(self, ctx: commands.Context):
        await send_help(ctx, "twitch")

    # ---------------------------------------------------------- add / remove / reset / list

    @command_meta(
        category="Socials",
        description="Announce a channel going live.",
        syntax=",twitch add <login> <channel>",
        examples=[",twitch add shroud #streams"],
        permissions=["Manage Guild"],
    )
    @twitch.command(name="add")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_add(self, ctx: commands.Context, login: str, channel: discord.TextChannel):
        user = await twitch_service.get_user(login)
        if user is None:
            await ctx.error(f"Couldn't find a Twitch channel named `{login}` (or Twitch isn't configured on this bot).")
            return

        async with get_session() as session:
            added = await twitch_repository.add_follow(session, ctx.guild.id, login, channel.id)

        if added:
            await ctx.success(f"Now announcing **{user.get('display_name', login)}** going live in {channel.mention}.")
        else:
            await ctx.error(f"Already announcing `{login}`.")

    @command_meta(
        category="Socials",
        description="Stop announcing a channel.",
        syntax=",twitch remove <login>",
        examples=[",twitch remove shroud"],
        permissions=["Manage Guild"],
    )
    @twitch.command(name="remove")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_remove(self, ctx: commands.Context, *, login: str):
        async with get_session() as session:
            removed = await twitch_repository.remove_follow(session, ctx.guild.id, login)
        if removed:
            await ctx.success(f"Stopped announcing `{login}`.")
        else:
            await ctx.error(f"`{login}` wasn't being announced.")

    @command_meta(
        category="Socials",
        description="Stop announcing every channel.",
        syntax=",twitch reset",
        examples=[",twitch reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @twitch.command(name="reset")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_reset(self, ctx: commands.Context):
        async with get_session() as session:
            count = await twitch_repository.reset_guild_follows(session, ctx.guild.id)
        await ctx.success(f"Stopped announcing {count} channel(s).")

    @command_meta(
        category="Socials",
        description="List the Twitch channels this server follows.",
        syntax=",twitch list",
        examples=[",twitch list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @twitch.command(name="list")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_list(self, ctx: commands.Context):
        async with get_session() as session:
            follows = await twitch_repository.get_follows_for_guild(session, ctx.guild.id)

        if not follows:
            await ctx.info("This server isn't following any Twitch channels.")
            return

        lines = []
        for f in follows:
            channel_display = f"<#{f.channel_id}>"
            role_display = f" • pings <@&{f.role_id}>" if f.role_id else ""
            lines.append(f"**{f.login}** → {channel_display}{role_display}")

        embed = discord.Embed(title="Followed Twitch Channels", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- message / ping

    @command_meta(
        category="Socials",
        description="Set the message posted for a channel's live announcement.",
        syntax=",twitch message <login> [script]",
        examples=[",twitch message shroud {twitch.creator.name} just went live!"],
        permissions=["Manage Guild"],
    )
    @twitch.command(name="message", aliases=["msg", "template"])
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_message(self, ctx: commands.Context, login: str, *, script: str = None):
        async with get_session() as session:
            follow = await twitch_repository.get_follow(session, ctx.guild.id, login)
            if follow is None:
                await ctx.error(f"`{login}` isn't being announced. Add it first with `,twitch add`.")
                return
            await twitch_repository.update_follow(session, follow, message_template=script or DEFAULT_MESSAGE)

        await ctx.success(f"Updated the live-announcement message for `{login}`.")

    @command_meta(
        category="Socials",
        description="Ping a role when the channel goes live.",
        syntax=",twitch ping <login> [role]",
        examples=[",twitch ping shroud @Streams", ",twitch ping shroud"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @twitch.command(name="ping")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def twitch_ping(self, ctx: commands.Context, login: str, role: discord.Role = None):
        async with get_session() as session:
            follow = await twitch_repository.get_follow(session, ctx.guild.id, login)
            if follow is None:
                await ctx.error(f"`{login}` isn't being announced. Add it first with `,twitch add`.")
                return
            await twitch_repository.update_follow(session, follow, role_id=role.id if role else None)

        if role:
            await ctx.success(f"{role.mention} will now be pinged when `{login}` goes live.")
        else:
            await ctx.success(f"Removed the ping role for `{login}`.")

    # ---------------------------------------------------------- variables

    @command_meta(
        category="Socials",
        description="Show the variables available in Twitch alerts.",
        syntax=",twitch variables",
        examples=[",twitch variables"],
        require_args=False,
    )
    @twitch.command(name="variables", aliases=["vars"])
    @requires_premium("server")
    async def twitch_variables(self, ctx: commands.Context):
        description = (
            " ".join(f"`{v}`" for v in VARIABLES)
            + f"\n\nUse these in `,twitch message` — everything else renders as normal script."
        )
        embed = discord.Embed(title="Twitch Alert Variables", description=description)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Twitch(bot))