"""
Last.fm - ,lastfm (alias ,lf), ,fm, ,lyrics. Category "Last.fm" - a new
top-level module. Everyone can use every command here.

HONEST SCOPE NOTE: this is the CORE subset only - login/logout (aliases
of set/unlink), set/unlink, fm (now playing), recent, top artists/
albums/tracks, artist/album/track lookups, profile, plays, url, and a
lyrics *link* (not full text - see lastfm_service.find_lyrics_link's
docstring for why). Everything else from the full fmbot-style command
list (crowns, whoknows, collage, recap, custom reactions, friends,
neighbours, milestones, streaks, discovery date, leaderboards, etc.)
is NOT built here - each of those needs its own dedicated pass.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from core.command_meta import command_meta
from core.help_formatter import send_help
from core.paginator import Paginator
from database.database import get_session
from repositories import lastfm_repository
from services import lastfm_service

PLATFORM_SEARCH_URLS = {
    "spotify": "https://open.spotify.com/search/{query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "soundcloud": "https://soundcloud.com/search?q={query}",
    "itunes": "https://music.apple.com/search?term={query}",
}


class Lastfm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _require_linked(self, ctx: commands.Context, member: discord.Member = None) -> str | None:
        target = member or ctx.author
        async with get_session() as session:
            account = await lastfm_repository.get_account(session, target.id)

        if account is not None:
            return account.username

        if target.id == ctx.author.id:
            description = f"⚠️ {ctx.author.mention}: You haven't linked your Last.fm yet. Use `lastfm set (username)`"
        else:
            description = f"⚠️ {ctx.author.mention}: **{target.display_name}** hasn't linked their Last.fm yet."
        await ctx.send(embed=discord.Embed(description=description, color=discord.Color.orange()))
        return None

    # ---------------------------------------------------------- fm (quick now-playing)

    @command_meta(
        category="Last.fm",
        description="Shows what you're (or someone else is) currently or last playing.",
        syntax=",fm [member]",
        examples=[",fm", ",fm @User"],
        require_args=False,
    )
    @commands.command(name="fm", with_app_command=False)
    async def fm(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        username = await self._require_linked(ctx, member)
        if username is None:
            return

        tracks = await lastfm_service.get_recent_tracks(username, limit=1)
        if tracks is None:
            await ctx.error("Couldn't reach Last.fm (or it isn't configured on this bot).")
            return
        if not tracks:
            await ctx.info(f"No scrobbles found for **{username}**.")
            return

        track = tracks[0]
        now_playing = track.get("@attr", {}).get("nowplaying") == "true"
        artist = track.get("artist", {}).get("#text", "Unknown")
        name = track.get("name", "Unknown")
        album = track.get("album", {}).get("#text", "")
        image = lastfm_service.best_image(track.get("image"))
        status = "Now playing" if now_playing else "Last played"

        settings = None
        if target.id == ctx.author.id:
            async with get_session() as session:
                settings = await lastfm_repository.get_settings(session, ctx.author.id)

        if settings is not None and settings.compact_mode:
            text = f"**{name}** by {artist}" + (f" ({album})" if album else "")
            sent = await ctx.send(text)
        else:
            if settings is not None and settings.fm_template:
                variables = {
                    "{lastfm.artist}": artist, "{lastfm.track}": name, "{lastfm.album}": album or "N/A",
                    "{lastfm.username}": username, "{lastfm.url}": track.get("url", ""), "{lastfm.status}": status,
                }
                description = settings.fm_template
                for token, value in variables.items():
                    description = description.replace(token, value)
            else:
                description = f"**{name}**\nby {artist}" + (f"\non *{album}*" if album else "")

            color = discord.Color.default()
            if settings is not None and settings.embed_color:
                try:
                    color = discord.Color(int(settings.embed_color.lstrip("#"), 16))
                except ValueError:
                    pass

            embed = discord.Embed(title=f"{status} for {username}", description=description, url=track.get("url") or None, color=color)
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
            if image:
                embed.set_thumbnail(url=image)
            sent = await ctx.send(embed=embed)

        if settings is not None and settings.reactions:
            for emoji in settings.reactions.split(","):
                try:
                    await sent.add_reaction(emoji.strip())
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------- lastfm (root)

    @command_meta(
        category="Last.fm",
        description="Set and view your Last.fm stats.",
        syntax=",lastfm",
        examples=[],
        aliases=["lf"],
        require_args=False,
    )
    @commands.group(name="lastfm", aliases=["lf"], invoke_without_command=True, with_app_command=False)
    async def lastfm(self, ctx: commands.Context):
        await send_help(ctx, "lastfm")

    @lastfm.command(name="help")
    async def lastfm_help(self, ctx: commands.Context):
        await send_help(ctx, "lastfm")

    # ---------------------------------------------------------- set / unlink

    @command_meta(
        category="Last.fm",
        description="Link your Last.fm account.",
        syntax=",lastfm set <username>",
        examples=[",lastfm set rj"],
        aliases=["login"],
    )
    @lastfm.command(name="set", aliases=["login"])
    async def lastfm_set(self, ctx: commands.Context, *, username: str):
        user_info = await lastfm_service.get_user_info(username)
        if user_info is None:
            await ctx.error(f"Couldn't find a Last.fm user named `{username}` (or Last.fm isn't configured on this bot).")
            return

        async with get_session() as session:
            await lastfm_repository.set_account(session, ctx.author.id, username)

        await ctx.success(f"Linked your Last.fm account to `{username}`.")

    @command_meta(
        category="Last.fm",
        description="Unlink your Last.fm account.",
        syntax=",lastfm unlink",
        examples=[",lastfm unlink"],
        aliases=["logout"],
        require_args=False,
    )
    @lastfm.command(name="unlink", aliases=["logout"])
    async def lastfm_unlink(self, ctx: commands.Context):
        async with get_session() as session:
            removed = await lastfm_repository.unlink_account(session, ctx.author.id)

        if removed:
            await ctx.success("Unlinked your Last.fm account.")
        else:
            await ctx.error("You don't have a linked Last.fm account.")

    # ---------------------------------------------------------- recent

    @command_meta(
        category="Last.fm",
        description="Shows your recently played tracks.",
        syntax=",lastfm recent [count]",
        examples=[",lastfm recent", ",lastfm recent 10"],
        require_args=False,
    )
    @lastfm.command(name="recent")
    async def lastfm_recent(self, ctx: commands.Context, count: int = 5):
        username = await self._require_linked(ctx)
        if username is None:
            return
        count = max(1, min(count, 20))

        tracks = await lastfm_service.get_recent_tracks(username, limit=count)
        if tracks is None:
            await ctx.error("Couldn't reach Last.fm.")
            return
        if not tracks:
            await ctx.info(f"No scrobbles found for **{username}**.")
            return

        lines = []
        for t in tracks:
            artist = t.get("artist", {}).get("#text", "Unknown")
            name = t.get("name", "Unknown")
            now_playing = t.get("@attr", {}).get("nowplaying") == "true"
            marker = "🎵 " if now_playing else ""
            lines.append(f"{marker}**{name}** by {artist}")

        embed = discord.Embed(title=f"Recent tracks for {username}", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- top artists/albums/tracks

    @command_meta(
        category="Last.fm",
        description="Shows your top artists, albums, or tracks.",
        syntax=",lastfm top (artists | albums | tracks) [period]",
        examples=[",lastfm top artists", ",lastfm top albums month"],
        require_args=False,
    )
    @lastfm.group(name="top", invoke_without_command=True)
    async def lastfm_top(self, ctx: commands.Context):
        await send_help(ctx, "lastfm top")

    @lastfm_top.command(name="artists")
    async def lastfm_top_artists(self, ctx: commands.Context, period: str = "overall"):
        username = await self._require_linked(ctx)
        if username is None:
            return
        norm_period = lastfm_service.normalize_period(period)

        artists = await lastfm_service.get_top_artists(username, norm_period, limit=10)
        if artists is None:
            await ctx.error("Couldn't reach Last.fm.")
            return
        if not artists:
            await ctx.info(f"No top artists found for **{username}**.")
            return

        lines = [f"`{i}` **{a['name']}** — {a.get('playcount', '?')} plays" for i, a in enumerate(artists, start=1)]
        embed = discord.Embed(title=f"Top Artists for {username} ({period})", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @lastfm_top.command(name="albums")
    async def lastfm_top_albums(self, ctx: commands.Context, period: str = "overall"):
        username = await self._require_linked(ctx)
        if username is None:
            return
        norm_period = lastfm_service.normalize_period(period)

        albums = await lastfm_service.get_top_albums(username, norm_period, limit=10)
        if albums is None:
            await ctx.error("Couldn't reach Last.fm.")
            return
        if not albums:
            await ctx.info(f"No top albums found for **{username}**.")
            return

        lines = [
            f"`{i}` **{a['name']}** by {a.get('artist', {}).get('name', 'Unknown')} — {a.get('playcount', '?')} plays"
            for i, a in enumerate(albums, start=1)
        ]
        embed = discord.Embed(title=f"Top Albums for {username} ({period})", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @lastfm_top.command(name="tracks")
    async def lastfm_top_tracks(self, ctx: commands.Context, period: str = "overall"):
        username = await self._require_linked(ctx)
        if username is None:
            return
        norm_period = lastfm_service.normalize_period(period)

        tracks = await lastfm_service.get_top_tracks(username, norm_period, limit=10)
        if tracks is None:
            await ctx.error("Couldn't reach Last.fm.")
            return
        if not tracks:
            await ctx.info(f"No top tracks found for **{username}**.")
            return

        lines = [
            f"`{i}` **{t['name']}** by {t.get('artist', {}).get('name', 'Unknown')} — {t.get('playcount', '?')} plays"
            for i, t in enumerate(tracks, start=1)
        ]
        embed = discord.Embed(title=f"Top Tracks for {username} ({period})", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- artist / album / track

    async def _current_track(self, username: str) -> dict | None:
        tracks = await lastfm_service.get_recent_tracks(username, limit=1)
        return tracks[0] if tracks else None

    @command_meta(
        category="Last.fm",
        description="Look up an artist - defaults to what you're currently playing.",
        syntax=",lastfm artist [name]",
        examples=[",lastfm artist", ",lastfm artist Radiohead"],
        require_args=False,
    )
    @lastfm.command(name="artist")
    async def lastfm_artist(self, ctx: commands.Context, *, name: str = None):
        username = await self._require_linked(ctx)
        if username is None:
            return

        if name is None:
            current = await self._current_track(username)
            if current is None:
                await ctx.error("Provide an artist name.")
                return
            name = current.get("artist", {}).get("#text")

        info = await lastfm_service.get_artist_info(name, username)
        if info is None:
            await ctx.error(f"Couldn't find an artist named `{name}`.")
            return

        stats = info.get("stats", {})
        description = f"**Listeners** {stats.get('listeners', '?')}\n**Global Plays** {stats.get('playcount', '?')}"
        if stats.get("userplaycount") is not None:
            description += f"\n**Your Plays** {stats.get('userplaycount')}"

        embed = discord.Embed(title=info.get("name", name), description=description, url=info.get("url") or None)
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Look up an album - defaults to what you're currently playing.",
        syntax=",lastfm album [artist - album]",
        examples=[",lastfm album", ",lastfm album Radiohead - OK Computer"],
        require_args=False,
    )
    @lastfm.command(name="album")
    async def lastfm_album(self, ctx: commands.Context, *, query: str = None):
        username = await self._require_linked(ctx)
        if username is None:
            return

        artist = album = None
        if query and "-" in query:
            artist, album = (p.strip() for p in query.split("-", 1))

        if not artist or not album:
            current = await self._current_track(username)
            if current is None:
                await ctx.error("Provide `artist - album`.")
                return
            artist = current.get("artist", {}).get("#text")
            album = current.get("album", {}).get("#text")
            if not album:
                await ctx.error("Provide `artist - album`.")
                return

        info = await lastfm_service.get_album_info(artist, album, username)
        if info is None:
            await ctx.error(f"Couldn't find `{album}` by `{artist}`.")
            return

        description = f"by {info.get('artist', artist)}\n\n**Plays** {info.get('playcount', '?')}"
        if info.get("userplaycount") is not None:
            description += f"\n**Your Plays** {info.get('userplaycount')}"

        embed = discord.Embed(title=info.get("name", album), description=description, url=info.get("url") or None)
        image = lastfm_service.best_image(info.get("image"))
        if image:
            embed.set_thumbnail(url=image)
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Look up a track - defaults to what you're currently playing.",
        syntax=",lastfm track [artist - track]",
        examples=[",lastfm track", ",lastfm track Radiohead - Paranoid Android"],
        require_args=False,
    )
    @lastfm.command(name="track")
    async def lastfm_track(self, ctx: commands.Context, *, query: str = None):
        username = await self._require_linked(ctx)
        if username is None:
            return

        artist = track = None
        if query and "-" in query:
            artist, track = (p.strip() for p in query.split("-", 1))

        if not artist or not track:
            current = await self._current_track(username)
            if current is None:
                await ctx.error("Provide `artist - track`.")
                return
            artist = current.get("artist", {}).get("#text")
            track = current.get("name")

        info = await lastfm_service.get_track_info(artist, track, username)
        if info is None:
            await ctx.error(f"Couldn't find `{track}` by `{artist}`.")
            return

        description = f"by {info.get('artist', {}).get('name', artist)}\n\n**Plays** {info.get('playcount', '?')}"
        if info.get("userplaycount") is not None:
            description += f"\n**Your Plays** {info.get('userplaycount')}"

        embed = discord.Embed(title=info.get("name", track), description=description, url=info.get("url") or None)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- profile / plays / url

    @command_meta(
        category="Last.fm",
        description="Shows your Last.fm profile overview.",
        syntax=",lastfm profile",
        examples=[",lastfm profile"],
        require_args=False,
    )
    @lastfm.command(name="profile")
    async def lastfm_profile(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        info = await lastfm_service.get_user_info(username)
        if info is None:
            await ctx.error("Couldn't fetch that profile.")
            return

        registered = info.get("registered", {}).get("unixtime")
        registered_display = "Unknown"
        if registered:
            dt = datetime.datetime.fromtimestamp(int(registered), tz=datetime.timezone.utc)
            registered_display = discord.utils.format_dt(dt, style="D")

        description = f"**Total Scrobbles** {info.get('playcount', '?')}\n**Registered** {registered_display}"
        embed = discord.Embed(title=f"{username}'s Last.fm Profile", description=description, url=info.get("url") or None)
        image = lastfm_service.best_image(info.get("image"))
        if image:
            embed.set_thumbnail(url=image)
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows your total scrobble count.",
        syntax=",lastfm plays",
        examples=[",lastfm plays"],
        require_args=False,
    )
    @lastfm.command(name="plays")
    async def lastfm_plays(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        info = await lastfm_service.get_user_info(username)
        if info is None:
            await ctx.error("Couldn't fetch that profile.")
            return

        await ctx.send(embed=discord.Embed(description=f"**{username}** has **{info.get('playcount', '?')}** total scrobbles."))

    @command_meta(
        category="Last.fm",
        description="Shows a link to your Last.fm profile.",
        syntax=",lastfm url",
        examples=[",lastfm url"],
        require_args=False,
    )
    @lastfm.command(name="url")
    async def lastfm_url(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return
        await ctx.send(f"https://www.last.fm/user/{username}")

    # ---------------------------------------------------------- platform link-outs

    async def _platform_search(self, ctx: commands.Context, platform: str):
        username = await self._require_linked(ctx)
        if username is None:
            return
        current = await self._current_track(username)
        if current is None:
            await ctx.error("You have no scrobbles to search for.")
            return

        from urllib.parse import quote

        artist = current.get("artist", {}).get("#text", "")
        name = current.get("name", "")
        query = quote(f"{artist} {name}")
        url = PLATFORM_SEARCH_URLS[platform].format(query=query)
        await ctx.send(embed=discord.Embed(description=f"[**{name}** by {artist} on {platform.title()}]({url})"))

    @command_meta(
        category="Last.fm",
        description="Finds your current track on Spotify.",
        syntax=",lastfm spotify",
        examples=[",lastfm spotify"],
        require_args=False,
    )
    @lastfm.command(name="spotify")
    async def lastfm_spotify(self, ctx: commands.Context):
        await self._platform_search(ctx, "spotify")

    @command_meta(
        category="Last.fm",
        description="Finds your current track on YouTube.",
        syntax=",lastfm youtube",
        examples=[",lastfm youtube"],
        require_args=False,
    )
    @lastfm.command(name="youtube")
    async def lastfm_youtube(self, ctx: commands.Context):
        await self._platform_search(ctx, "youtube")

    @command_meta(
        category="Last.fm",
        description="Finds your current track on SoundCloud.",
        syntax=",lastfm soundcloud",
        examples=[",lastfm soundcloud"],
        require_args=False,
    )
    @lastfm.command(name="soundcloud")
    async def lastfm_soundcloud(self, ctx: commands.Context):
        await self._platform_search(ctx, "soundcloud")

    @command_meta(
        category="Last.fm",
        description="Finds your current track on Apple Music/iTunes.",
        syntax=",lastfm itunes",
        examples=[",lastfm itunes"],
        require_args=False,
    )
    @lastfm.command(name="itunes")
    async def lastfm_itunes(self, ctx: commands.Context):
        await self._platform_search(ctx, "itunes")

    # ---------------------------------------------------------- playing (alias-style), toptenalbums/toptentracks

    @command_meta(
        category="Last.fm",
        description="Shows what you're currently or last playing (same as ,fm).",
        syntax=",lastfm playing",
        examples=[",lastfm playing"],
        require_args=False,
    )
    @lastfm.command(name="playing")
    async def lastfm_playing(self, ctx: commands.Context):
        await self.fm(ctx)

    @command_meta(
        category="Last.fm",
        description="Shows your top 10 albums of all time.",
        syntax=",lastfm toptenalbums",
        examples=[",lastfm toptenalbums"],
        require_args=False,
    )
    @lastfm.command(name="toptenalbums")
    async def lastfm_toptenalbums(self, ctx: commands.Context):
        await self.lastfm_top_albums(ctx, period="overall")

    @command_meta(
        category="Last.fm",
        description="Shows your top 10 tracks of all time.",
        syntax=",lastfm toptentracks",
        examples=[",lastfm toptentracks"],
        require_args=False,
    )
    @lastfm.command(name="toptentracks")
    async def lastfm_toptentracks(self, ctx: commands.Context):
        await self.lastfm_top_tracks(ctx, period="overall")

    # ---------------------------------------------------------- count / overview / milestone / loved / globalchart

    @command_meta(
        category="Last.fm",
        description="Shows how many times you've played a specific track - defaults to what you're currently playing.",
        syntax=",lastfm count [artist - track]",
        examples=[",lastfm count", ",lastfm count Radiohead - Karma Police"],
        require_args=False,
    )
    @lastfm.command(name="count")
    async def lastfm_count(self, ctx: commands.Context, *, query: str = None):
        username = await self._require_linked(ctx)
        if username is None:
            return

        artist = track = None
        if query and "-" in query:
            artist, track = (p.strip() for p in query.split("-", 1))
        if not artist or not track:
            current = await self._current_track(username)
            if current is None:
                await ctx.error("Provide `artist - track`.")
                return
            artist = current.get("artist", {}).get("#text")
            track = current.get("name")

        info = await lastfm_service.get_track_info(artist, track, username)
        if info is None:
            await ctx.error(f"Couldn't find `{track}` by `{artist}`.")
            return

        plays = info.get("userplaycount", "0")
        await ctx.send(embed=discord.Embed(
            description=f"You've played **{info.get('name', track)}** by **{info.get('artist', {}).get('name', artist)}** `{plays}` time(s)."
        ))

    @command_meta(
        category="Last.fm",
        description="Shows a combined overview: recent track, top artist, and total scrobbles.",
        syntax=",lastfm overview",
        examples=[",lastfm overview"],
        require_args=False,
    )
    @lastfm.command(name="overview")
    async def lastfm_overview(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        current = await self._current_track(username)
        top_artists = await lastfm_service.get_top_artists(username, "overall", limit=1)
        info = await lastfm_service.get_user_info(username)

        lines = []
        if current:
            lines.append(f"**Now/Last Played** {current.get('name')} by {current.get('artist', {}).get('#text')}")
        if top_artists:
            lines.append(f"**Top Artist** {top_artists[0]['name']} ({top_artists[0].get('playcount', '?')} plays)")
        if info:
            lines.append(f"**Total Scrobbles** {info.get('playcount', '?')}")

        if not lines:
            await ctx.error("Couldn't fetch your overview.")
            return

        embed = discord.Embed(title=f"Overview for {username}", description="\n".join(lines))
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows how close you are to your next scrobble milestone.",
        syntax=",lastfm milestone",
        examples=[",lastfm milestone"],
        require_args=False,
    )
    @lastfm.command(name="milestone")
    async def lastfm_milestone(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        info = await lastfm_service.get_user_info(username)
        if info is None:
            await ctx.error("Couldn't fetch your profile.")
            return

        playcount = int(info.get("playcount", 0))
        step = 1000 if playcount < 10000 else (10000 if playcount < 100000 else 50000)
        next_milestone = ((playcount // step) + 1) * step
        remaining = next_milestone - playcount

        await ctx.send(embed=discord.Embed(
            description=(
                f"**{username}** has **{playcount:,}** scrobbles - "
                f"`{remaining:,}` away from **{next_milestone:,}**."
            )
        ))

    @command_meta(
        category="Last.fm",
        description="Shows your loved tracks.",
        syntax=",lastfm loved",
        examples=[",lastfm loved"],
        require_args=False,
    )
    @lastfm.command(name="loved")
    async def lastfm_loved(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        data = await lastfm_service.get_loved_tracks(username, limit=10)
        if data is None:
            await ctx.error("Couldn't reach Last.fm.")
            return
        if not data:
            await ctx.info(f"**{username}** has no loved tracks.")
            return

        lines = [f"`{i}` **{t['name']}** by {t.get('artist', {}).get('name', 'Unknown')}" for i, t in enumerate(data, start=1)]
        embed = discord.Embed(title=f"Loved Tracks for {username}", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows Last.fm's global top tracks chart.",
        syntax=",lastfm globalchart",
        examples=[",lastfm globalchart"],
        aliases=["global"],
        require_args=False,
    )
    @lastfm.command(name="globalchart", aliases=["global"])
    async def lastfm_globalchart(self, ctx: commands.Context):
        tracks = await lastfm_service.get_global_top_tracks(limit=10)
        if tracks is None:
            await ctx.error("Couldn't reach Last.fm.")
            return

        lines = [f"`{i}` **{t['name']}** by {t.get('artist', {}).get('name', 'Unknown')}" for i, t in enumerate(tracks, start=1)]
        embed = discord.Embed(title="Last.fm Global Top Tracks", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- mode / embed / color / variables / react / customreactions

    @command_meta(
        category="Last.fm",
        description="Switch ,fm between a rich embed and a compact one-line reply.",
        syntax=",lastfm mode <embed|compact>",
        examples=[",lastfm mode compact"],
    )
    @lastfm.command(name="mode")
    async def lastfm_mode(self, ctx: commands.Context, mode: str):
        mode = mode.lower()
        if mode not in ("embed", "compact"):
            await ctx.error("Mode must be `embed` or `compact`.")
            return

        async with get_session() as session:
            settings = await lastfm_repository.get_or_create_settings(session, ctx.author.id)
            await lastfm_repository.update_settings(session, settings, compact_mode=(mode == "compact"))

        await ctx.success(f"Set your `,fm` display mode to **{mode}**.")

    @command_meta(
        category="Last.fm",
        description="Customize the text shown in your ,fm embed. Run with no script to reset.",
        syntax=",lastfm embed [script]",
        examples=[",lastfm embed {lastfm.track} by {lastfm.artist}"],
        require_args=False,
    )
    @lastfm.command(name="embed")
    async def lastfm_embed(self, ctx: commands.Context, *, script: str = None):
        async with get_session() as session:
            settings = await lastfm_repository.get_or_create_settings(session, ctx.author.id)
            await lastfm_repository.update_settings(session, settings, fm_template=script)

        await ctx.success("Updated your `,fm` embed text." if script else "Reset your `,fm` embed text to the default.")

    @command_meta(
        category="Last.fm",
        description="Set your ,fm embed's color.",
        syntax=",lastfm color <hex>",
        examples=[",lastfm color #FF0000"],
    )
    @lastfm.command(name="color", aliases=["colour"])
    async def lastfm_color(self, ctx: commands.Context, hex_color: str):
        cleaned = hex_color.strip().lstrip("#")
        try:
            int(cleaned, 16)
        except ValueError:
            await ctx.error("Provide a valid hex color, e.g. `#ff0000`.")
            return
        if len(cleaned) != 6:
            await ctx.error("Provide a valid 6-digit hex color, e.g. `#ff0000`.")
            return

        async with get_session() as session:
            settings = await lastfm_repository.get_or_create_settings(session, ctx.author.id)
            await lastfm_repository.update_settings(session, settings, embed_color=f"#{cleaned.upper()}")

        await ctx.success(f"Set your `,fm` embed color to `#{cleaned.upper()}`.")

    @command_meta(
        category="Last.fm",
        description="Shows the variables available in your custom ,fm embed text.",
        syntax=",lastfm variables",
        examples=[",lastfm variables"],
        require_args=False,
    )
    @lastfm.command(name="variables", aliases=["vars"])
    async def lastfm_variables(self, ctx: commands.Context):
        variables = [
            "{lastfm.artist}", "{lastfm.track}", "{lastfm.album}",
            "{lastfm.username}", "{lastfm.url}", "{lastfm.status}",
        ]
        description = " ".join(f"`{v}`" for v in variables) + "\n\nUse these in `,lastfm embed`."
        await ctx.send(embed=discord.Embed(title="Last.fm Embed Variables", description=description))

    @command_meta(
        category="Last.fm",
        description="Set emoji to auto-react with after ,fm.",
        syntax=",lastfm react <emoji> [emoji2]",
        examples=[",lastfm react 🔥", ",lastfm react 🔥 ❤️"],
    )
    @lastfm.command(name="react")
    async def lastfm_react(self, ctx: commands.Context, first: str, second: str = None):
        reactions = first if not second else f"{first},{second}"
        async with get_session() as session:
            settings = await lastfm_repository.get_or_create_settings(session, ctx.author.id)
            await lastfm_repository.update_settings(session, settings, reactions=reactions)

        await ctx.success("Updated your `,fm` auto-reactions.")

    @command_meta(
        category="Last.fm",
        description="Shows your current ,fm auto-reactions.",
        syntax=",lastfm customreactions",
        examples=[",lastfm customreactions"],
        require_args=False,
    )
    @lastfm.command(name="customreactions")
    async def lastfm_customreactions(self, ctx: commands.Context):
        async with get_session() as session:
            settings = await lastfm_repository.get_settings(session, ctx.author.id)

        if settings is None or not settings.reactions:
            await ctx.info("You have no custom reactions set. Use `,lastfm react`.")
            return

        await ctx.send(embed=discord.Embed(description=f"Your `,fm` reactions: {settings.reactions}"))

    # ---------------------------------------------------------- friends / neighbours / taste

    @command_meta(
        category="Last.fm",
        description="Manage your Last.fm friends list (for friendwktrack/friendwkalbum/neighbours).",
        syntax=",lastfm friends (add | remove | list) [member]",
        examples=[",lastfm friends add @User", ",lastfm friends list"],
        require_args=False,
    )
    @lastfm.group(name="friends", invoke_without_command=True)
    async def lastfm_friends(self, ctx: commands.Context):
        await self.lastfm_friends_list(ctx)

    @lastfm_friends.command(name="add")
    async def lastfm_friends_add(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            added = await lastfm_repository.add_friend(session, ctx.author.id, member.id)
        if added:
            await ctx.success(f"Added {member.mention} as a Last.fm friend.")
        else:
            await ctx.error(f"{member.mention} is already your friend.")

    @lastfm_friends.command(name="remove")
    async def lastfm_friends_remove(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            removed = await lastfm_repository.remove_friend(session, ctx.author.id, member.id)
        if removed:
            await ctx.success(f"Removed {member.mention} from your Last.fm friends.")
        else:
            await ctx.error(f"{member.mention} wasn't your friend.")

    @lastfm_friends.command(name="list")
    async def lastfm_friends_list(self, ctx: commands.Context):
        async with get_session() as session:
            friend_ids = await lastfm_repository.get_friends(session, ctx.author.id)

        if not friend_ids:
            await ctx.info("You have no Last.fm friends. Add some with `,lastfm friends add`.")
            return

        lines = [f"<@{fid}>" for fid in friend_ids]
        await ctx.send(embed=discord.Embed(title="Your Last.fm Friends", description="\n".join(lines)[:4000]))

    @command_meta(
        category="Last.fm",
        description="Shows which of your friends know a track.",
        syntax=",lastfm friendwktrack [artist - track]",
        examples=[",lastfm friendwktrack"],
        require_args=False,
    )
    @lastfm.command(name="friendwktrack")
    async def lastfm_friendwktrack(self, ctx: commands.Context, *, query: str = None):
        await self._friend_wk(ctx, query, kind="track")

    @command_meta(
        category="Last.fm",
        description="Shows which of your friends know an album.",
        syntax=",lastfm friendwkalbum [artist - album]",
        examples=[",lastfm friendwkalbum"],
        require_args=False,
    )
    @lastfm.command(name="friendwkalbum")
    async def lastfm_friendwkalbum(self, ctx: commands.Context, *, query: str = None):
        await self._friend_wk(ctx, query, kind="album")

    async def _friend_wk(self, ctx: commands.Context, query: str | None, kind: str) -> None:
        username = await self._require_linked(ctx)
        if username is None:
            return

        artist = item = None
        if query and "-" in query:
            artist, item = (p.strip() for p in query.split("-", 1))
        if not artist or not item:
            current = await self._current_track(username)
            if current is None:
                await ctx.error(f"Provide `artist - {kind}`.")
                return
            artist = current.get("artist", {}).get("#text")
            item = current.get("album", {}).get("#text") if kind == "album" else current.get("name")
            if not item:
                await ctx.error(f"Provide `artist - {kind}`.")
                return

        async with get_session() as session:
            friend_ids = await lastfm_repository.get_friends(session, ctx.author.id)
            accounts = {}
            for fid in friend_ids:
                acc = await lastfm_repository.get_account(session, fid)
                if acc:
                    accounts[fid] = acc.username

        if not accounts:
            await ctx.info("You have no linked Last.fm friends.")
            return

        results = []
        for fid, fname in accounts.items():
            if kind == "album":
                info = await lastfm_service.get_album_info(artist, item, fname)
            else:
                info = await lastfm_service.get_track_info(artist, item, fname)
            plays = int(info.get("userplaycount", 0)) if info else 0
            if plays > 0:
                results.append((fid, plays))

        results.sort(key=lambda r: r[1], reverse=True)
        if not results:
            await ctx.info(f"None of your friends have played **{item}** by **{artist}**.")
            return

        lines = [f"`{i}` <@{fid}> — {plays} plays" for i, (fid, plays) in enumerate(results, start=1)]
        embed = discord.Embed(title=f"Friends who know {item} by {artist}", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows your closest Last.fm neighbours (friends ranked by shared top artists).",
        syntax=",lastfm neighbours",
        examples=[",lastfm neighbours"],
        require_args=False,
    )
    @lastfm.command(name="neighbours", aliases=["neighbors"])
    async def lastfm_neighbours(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        my_artists = await lastfm_service.get_top_artists(username, "overall", limit=50)
        if not my_artists:
            await ctx.error("Couldn't fetch your top artists.")
            return
        my_names = {a["name"].lower() for a in my_artists}

        async with get_session() as session:
            friend_ids = await lastfm_repository.get_friends(session, ctx.author.id)
            accounts = {}
            for fid in friend_ids:
                acc = await lastfm_repository.get_account(session, fid)
                if acc:
                    accounts[fid] = acc.username

        if not accounts:
            await ctx.info("You have no linked Last.fm friends to compare against.")
            return

        results = []
        for fid, fname in accounts.items():
            their_artists = await lastfm_service.get_top_artists(fname, "overall", limit=50)
            if not their_artists:
                continue
            their_names = {a["name"].lower() for a in their_artists}
            overlap = len(my_names & their_names)
            results.append((fid, overlap))

        results.sort(key=lambda r: r[1], reverse=True)
        if not results:
            await ctx.info("Couldn't compute neighbours.")
            return

        lines = [f"`{i}` <@{fid}> — {overlap} shared artists" for i, (fid, overlap) in enumerate(results, start=1)]
        embed = discord.Embed(title="Your Last.fm Neighbours", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Compares your musical taste with another member.",
        syntax=",lastfm taste <member>",
        examples=[",lastfm taste @User"],
    )
    @lastfm.command(name="taste")
    async def lastfm_taste(self, ctx: commands.Context, member: discord.Member):
        username = await self._require_linked(ctx)
        if username is None:
            return
        other_username = await self._require_linked(ctx, member)
        if other_username is None:
            return

        my_artists = await lastfm_service.get_top_artists(username, "overall", limit=50)
        their_artists = await lastfm_service.get_top_artists(other_username, "overall", limit=50)
        if not my_artists or not their_artists:
            await ctx.error("Couldn't fetch top artists for one of you.")
            return

        my_names = {a["name"] for a in my_artists}
        their_names = {a["name"] for a in their_artists}
        shared = sorted(my_names & their_names)

        if not shared:
            await ctx.info(f"No shared top artists between you and **{member.display_name}**.")
            return

        embed = discord.Embed(
            title=f"Shared taste: you & {member.display_name}",
            description=f"**{len(shared)}** shared artist(s):\n" + ", ".join(shared[:25]),
        )
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- whoknows / crowns / mostcrowns / server / leaderboard

    async def _linked_members(self, ctx: commands.Context) -> dict[int, str]:
        """All members of this guild who have a linked Last.fm account -
        {user_id: lastfm_username}. Caps at 50 members to keep API
        usage (and command runtime) bounded."""
        accounts = {}
        async with get_session() as session:
            for member in ctx.guild.members[:200]:
                if member.bot:
                    continue
                acc = await lastfm_repository.get_account(session, member.id)
                if acc:
                    accounts[member.id] = acc.username
                if len(accounts) >= 50:
                    break
        return accounts

    @command_meta(
        category="Last.fm",
        description="Ranks this server's linked members by plays of an artist - defaults to what you're currently playing.",
        syntax=",lastfm whoknows [artist]",
        examples=[",lastfm whoknows", ",lastfm whoknows Radiohead"],
        require_args=False,
    )
    @lastfm.command(name="whoknows")
    @commands.guild_only()
    async def lastfm_whoknows(self, ctx: commands.Context, *, artist: str = None):
        username = await self._require_linked(ctx)
        if username is None:
            return

        if artist is None:
            current = await self._current_track(username)
            if current is None:
                await ctx.error("Provide an artist name.")
                return
            artist = current.get("artist", {}).get("#text")

        async with ctx.typing():
            accounts = await self._linked_members(ctx)
            results = []
            for uid, uname in accounts.items():
                info = await lastfm_service.get_artist_info(artist, uname)
                plays = int(info.get("stats", {}).get("userplaycount", 0)) if info else 0
                if plays > 0:
                    results.append((uid, plays))

        results.sort(key=lambda r: r[1], reverse=True)
        if not results:
            await ctx.info(f"Nobody in this server has played **{artist}**.")
            return

        lines = [f"`{i}` <@{uid}> — {plays} plays" for i, (uid, plays) in enumerate(results[:10], start=1)]
        embed = discord.Embed(title=f"Who knows {artist}?", description="\n".join(lines))
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows artists where you're #1 in this server's whoknows, out of your own top 15.",
        syntax=",lastfm crowns",
        examples=[",lastfm crowns"],
        require_args=False,
    )
    @lastfm.command(name="crowns")
    @commands.guild_only()
    async def lastfm_crowns(self, ctx: commands.Context):
        username = await self._require_linked(ctx)
        if username is None:
            return

        my_top = await lastfm_service.get_top_artists(username, "overall", limit=15)
        if not my_top:
            await ctx.error("Couldn't fetch your top artists.")
            return

        async with ctx.typing():
            accounts = await self._linked_members(ctx)
            crowns = []
            for artist_entry in my_top:
                artist_name = artist_entry["name"]
                my_plays = int(artist_entry.get("playcount", 0))
                is_top = True
                for uid, uname in accounts.items():
                    if uid == ctx.author.id:
                        continue
                    info = await lastfm_service.get_artist_info(artist_name, uname)
                    their_plays = int(info.get("stats", {}).get("userplaycount", 0)) if info else 0
                    if their_plays >= my_plays:
                        is_top = False
                        break
                if is_top:
                    crowns.append(artist_name)

        if not crowns:
            await ctx.info("You don't hold any crowns in this server (checked your top 15 artists).")
            return

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Crowns",
            description="\n".join(f"👑 {a}" for a in crowns),
        )
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Ranks this server's linked members by total scrobbles.",
        syntax=",lastfm leaderboard",
        examples=[",lastfm leaderboard"],
        require_args=False,
    )
    @lastfm.command(name="leaderboard")
    @commands.guild_only()
    async def lastfm_leaderboard(self, ctx: commands.Context):
        async with ctx.typing():
            accounts = await self._linked_members(ctx)
            results = []
            for uid, uname in accounts.items():
                info = await lastfm_service.get_user_info(uname)
                if info:
                    results.append((uid, int(info.get("playcount", 0))))

        results.sort(key=lambda r: r[1], reverse=True)
        if not results:
            await ctx.info("Nobody in this server has linked Last.fm.")
            return

        lines = [f"`{i}` <@{uid}> — {plays:,} scrobbles" for i, (uid, plays) in enumerate(results[:10], start=1)]
        embed = discord.Embed(title="Last.fm Leaderboard", description="\n".join(lines))
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Shows this server's most common top artist among linked members.",
        syntax=",lastfm server",
        examples=[",lastfm server"],
        require_args=False,
    )
    @lastfm.command(name="server")
    @commands.guild_only()
    async def lastfm_server(self, ctx: commands.Context):
        async with ctx.typing():
            accounts = await self._linked_members(ctx)
            tally: dict[str, int] = {}
            for uid, uname in accounts.items():
                top = await lastfm_service.get_top_artists(uname, "overall", limit=1)
                if top:
                    name = top[0]["name"]
                    tally[name] = tally.get(name, 0) + 1

        if not tally:
            await ctx.info("Nobody in this server has linked Last.fm.")
            return

        ranked = sorted(tally.items(), key=lambda kv: kv[1], reverse=True)
        lines = [f"`{i}` **{name}** — {count} listener(s)" for i, (name, count) in enumerate(ranked[:10], start=1)]
        embed = discord.Embed(
            title=f"{ctx.guild.name}'s Top Artists",
            description=f"Based on **{len(accounts)}** linked member(s).\n\n" + "\n".join(lines),
        )
        await ctx.send(embed=embed)

    @command_meta(
        category="Last.fm",
        description="Ranks this server's linked members by how many crowns they hold (their top 10 artists checked against everyone else).",
        syntax=",lastfm mostcrowns",
        examples=[",lastfm mostcrowns"],
        require_args=False,
    )
    @lastfm.command(name="mostcrowns")
    @commands.guild_only()
    async def lastfm_mostcrowns(self, ctx: commands.Context):
        async with ctx.typing():
            accounts = await self._linked_members(ctx)
            if len(accounts) < 2:
                await ctx.info("Need at least 2 linked members in this server to compute crowns.")
                return

            # cache each member's top 10 + per-artist playcounts to avoid
            # re-fetching the same artist repeatedly
            member_tops: dict[int, list[dict]] = {}
            for uid, uname in accounts.items():
                top = await lastfm_service.get_top_artists(uname, "overall", limit=10)
                member_tops[uid] = top or []

            crown_counts: dict[int, int] = {uid: 0 for uid in accounts}
            for uid, top in member_tops.items():
                for entry in top:
                    artist_name = entry["name"]
                    my_plays = int(entry.get("playcount", 0))
                    is_top = True
                    for other_uid, other_uname in accounts.items():
                        if other_uid == uid:
                            continue
                        info = await lastfm_service.get_artist_info(artist_name, other_uname)
                        their_plays = int(info.get("stats", {}).get("userplaycount", 0)) if info else 0
                        if their_plays >= my_plays:
                            is_top = False
                            break
                    if is_top:
                        crown_counts[uid] += 1

        ranked = sorted(crown_counts.items(), key=lambda kv: kv[1], reverse=True)
        ranked = [r for r in ranked if r[1] > 0]
        if not ranked:
            await ctx.info("Nobody in this server holds any crowns yet.")
            return

        lines = [f"`{i}` <@{uid}> — 👑 {count}" for i, (uid, count) in enumerate(ranked[:10], start=1)]
        embed = discord.Embed(title="Most Crowns", description="\n".join(lines))
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- collage / recap

    @command_meta(
        category="Last.fm",
        description="Shows a grid of your top albums' cover art.",
        syntax=",lastfm collage [size] [period]",
        examples=[",lastfm collage", ",lastfm collage 4 month"],
        require_args=False,
    )
    @lastfm.command(name="collage")
    async def lastfm_collage(self, ctx: commands.Context, size: int = 3, period: str = "overall"):
        username = await self._require_linked(ctx)
        if username is None:
            return
        size = max(2, min(size, 5))
        norm_period = lastfm_service.normalize_period(period)

        async with ctx.typing():
            albums = await lastfm_service.get_top_albums(username, norm_period, limit=size * size)
            if not albums:
                await ctx.error("Couldn't fetch your top albums.")
                return

            buffer = await lastfm_service.build_collage(albums, grid=size)

        if buffer is None:
            await ctx.error("None of your top albums have cover art available.")
            return

        file = discord.File(buffer, filename="collage.png")
        embed = discord.Embed(title=f"{username}'s Top Albums ({period})")
        embed.set_image(url="attachment://collage.png")
        await ctx.send(embed=embed, file=file)

    @command_meta(
        category="Last.fm",
        description="Shows a recap of your listening for a period.",
        syntax=",lastfm recap [period]",
        examples=[",lastfm recap", ",lastfm recap month"],
        require_args=False,
    )
    @lastfm.command(name="recap")
    async def lastfm_recap(self, ctx: commands.Context, period: str = "overall"):
        username = await self._require_linked(ctx)
        if username is None:
            return
        norm_period = lastfm_service.normalize_period(period)

        artists = await lastfm_service.get_top_artists(username, norm_period, limit=5)
        albums = await lastfm_service.get_top_albums(username, norm_period, limit=5)
        tracks = await lastfm_service.get_top_tracks(username, norm_period, limit=5)

        description = ""
        if artists:
            description += "**Top Artists**\n" + "\n".join(f"{i}. {a['name']}" for i, a in enumerate(artists, start=1)) + "\n\n"
        if albums:
            description += "**Top Albums**\n" + "\n".join(f"{i}. {a['name']}" for i, a in enumerate(albums, start=1)) + "\n\n"
        if tracks:
            description += "**Top Tracks**\n" + "\n".join(f"{i}. {t['name']}" for i, t in enumerate(tracks, start=1))

        if not description:
            await ctx.error("Couldn't fetch your recap.")
            return

        embed = discord.Embed(title=f"{username}'s Recap ({period})", description=description[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- lyrics

    @command_meta(
        category="Last.fm",
        description="Finds a lyrics source for a track - defaults to what you're currently playing. Links out rather than showing full lyrics.",
        syntax=",lyrics [artist - title]",
        examples=[",lyrics", ",lyrics Radiohead - Karma Police"],
        require_args=False,
    )
    @commands.command(name="lyrics", with_app_command=False)
    async def lyrics(self, ctx: commands.Context, *, query: str = None):
        artist = title = None
        if query and "-" in query:
            artist, title = (p.strip() for p in query.split("-", 1))

        if not artist or not title:
            async with get_session() as session:
                account = await lastfm_repository.get_account(session, ctx.author.id)
            if account is None:
                await ctx.error("Provide `artist - title`, or link your Last.fm with `lastfm set` to default to your current track.")
                return
            tracks = await lastfm_service.get_recent_tracks(account.username, limit=1)
            if not tracks:
                await ctx.error("Provide `artist - title`.")
                return
            artist = tracks[0].get("artist", {}).get("#text")
            title = tracks[0].get("name")

        link = await lastfm_service.find_lyrics_link(artist, title)
        if link is None:
            await ctx.error(f"Couldn't find lyrics for **{title}** by **{artist}**.")
            return

        embed = discord.Embed(description=f"[**{title}** by {artist} - view lyrics]({link})")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lastfm(bot))