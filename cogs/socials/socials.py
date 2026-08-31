"""
Roblox lookups - ,roblox. Category "Socials" - a new top-level module.
Everyone can use every one of these (no permission requirement, per
the reference command list).
"""

from __future__ import annotations

import io

import discord
from discord.ext import commands

from core.command_meta import command_meta
from core.help_formatter import send_help
from services import roblox_service, minecraft_service, github_service, spotify_service


def _relative_time(iso_string: str | None) -> str:
    if not iso_string:
        return "unknown"
    try:
        dt = discord.utils.parse_time(iso_string)
    except Exception:
        return "unknown"
    if dt is None:
        return "unknown"
    delta = discord.utils.utcnow() - dt
    days = delta.days
    if days >= 365:
        return f"{days // 365} year(s) ago"
    if days >= 30:
        return f"{days // 30} month(s) ago"
    if days >= 1:
        return f"{days} day(s) ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} hour(s) ago"
    return f"{max(1, delta.seconds // 60)} minute(s) ago"


class Socials(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- root

    @command_meta(
        category="Socials",
        description="Roblox.",
        syntax=",roblox",
        examples=[],
        require_args=False,
    )
    @commands.hybrid_group(name="roblox", invoke_without_command=True)
    async def roblox(self, ctx: commands.Context):
        await send_help(ctx, "roblox")

    @roblox.command(name="help")
    async def roblox_help(self, ctx: commands.Context):
        await send_help(ctx, "roblox")

    # ---------------------------------------------------------- profile

    @command_meta(
        category="Socials",
        description="Look up a Roblox user's profile.",
        syntax=",roblox profile <username>",
        examples=[",roblox profile builderman"],
    )
    @roblox.command(name="profile")
    async def roblox_profile(self, ctx: commands.Context, *, username: str):
        user = await roblox_service.resolve_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a Roblox user named `{username}`.")
            return

        profile = await roblox_service.get_user_profile(user["id"])
        if profile is None:
            await ctx.error("Couldn't fetch that user's profile.")
            return

        avatar_url = await roblox_service.get_avatar_thumbnail(user["id"])
        created_relative = _relative_time(profile.get("created"))

        description = (
            f"**Display Name** {profile.get('displayName', user['name'])}\n"
            f"**User ID** `{user['id']}`\n"
            f"**Created** {created_relative}\n"
            f"**Banned** {'Yes' if profile.get('isBanned') else 'No'}"
        )
        embed = discord.Embed(title=f"@{profile.get('name', username)}", description=description)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.url = f"https://www.roblox.com/users/{user['id']}/profile"
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- history

    @command_meta(
        category="Socials",
        description="Show a Roblox user's past usernames.",
        syntax=",roblox history <username>",
        examples=[",roblox history builderman"],
    )
    @roblox.command(name="history")
    async def roblox_history(self, ctx: commands.Context, *, username: str):
        user = await roblox_service.resolve_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a Roblox user named `{username}`.")
            return

        names = await roblox_service.get_username_history(user["id"])
        if not names:
            await ctx.info(f"**{username}** has no past usernames on record.")
            return

        embed = discord.Embed(
            title=f"@{user['name']}'s Past Usernames",
            description="\n".join(f"`{n}`" for n in names[:25]),
        )
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- outfits

    @command_meta(
        category="Socials",
        description="Show a Roblox user's saved outfits.",
        syntax=",roblox outfits <username>",
        examples=[",roblox outfits builderman"],
    )
    @roblox.command(name="outfits")
    async def roblox_outfits(self, ctx: commands.Context, *, username: str):
        user = await roblox_service.resolve_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a Roblox user named `{username}`.")
            return

        outfits = await roblox_service.get_outfits(user["id"])
        if not outfits:
            await ctx.info(f"**{username}** has no saved outfits.")
            return

        lines = [f"`#{o['id']}` {o['name']}" for o in outfits[:25]]
        embed = discord.Embed(title=f"@{user['name']}'s Outfits", description="\n".join(lines))
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- games (user's created games)

    @command_meta(
        category="Socials",
        description="List a Roblox user's games.",
        syntax=",roblox games <username>",
        examples=[",roblox games builderman"],
    )
    @roblox.command(name="games")
    async def roblox_games(self, ctx: commands.Context, *, username: str):
        user = await roblox_service.resolve_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a Roblox user named `{username}`.")
            return

        games = await roblox_service.get_user_games(user["id"])
        if not games:
            await ctx.info(f"**{username}** has no public games.")
            return

        lines = [f"**{g['name']}** — {g.get('placeVisits', 0):,} visits" for g in games[:25]]
        embed = discord.Embed(title=f"@{user['name']}'s Games", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- game (look up a game by name)

    @command_meta(
        category="Socials",
        description="Look up a Roblox game.",
        syntax=",roblox game <name>",
        examples=[",roblox game Da Hood"],
    )
    @roblox.command(name="game")
    async def roblox_game(self, ctx: commands.Context, *, name: str):
        game = await roblox_service.search_game(name)
        if game is None:
            await ctx.error(f"Couldn't find a Roblox game named `{name}`.")
            return

        creator = game.get("creator", {}).get("name", "Unknown")
        description = (game.get("description") or "").strip()
        if len(description) > 300:
            description = description[:300] + "…"

        updated_relative = _relative_time(game.get("updated"))
        favorites = game.get("favoritedCount")

        body = f"by **{creator}**\n"
        if description:
            body += f"{description}\n"
        body += (
            f"\n🟢 **{game.get('playing', 0):,}** playing • 👁 **{game.get('visits', 0):,}** visits"
            + (f" • ❤ **{favorites:,}** favorites" if favorites is not None else "")
            + f"\nup to {game.get('maxPlayers', '?')} players • updated {updated_relative}"
        )

        embed = discord.Embed(title=game.get("name", name), description=body)
        if game.get("iconUrl"):
            embed.set_thumbnail(url=game["iconUrl"])

        place_id = game.get("rootPlaceId")
        view = None
        if place_id:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Play", style=discord.ButtonStyle.link,
                url=f"https://www.roblox.com/games/{place_id}",
            ))

        await ctx.send(embed=embed, view=view)

    # ---------------------------------------------------------- group / groups

    @command_meta(
        category="Socials",
        description="Look up a Roblox group.",
        syntax=",roblox group <name>",
        examples=[",roblox group Roblox"],
    )
    @roblox.command(name="group")
    async def roblox_group(self, ctx: commands.Context, *, name: str):
        group = await roblox_service.search_group(name)
        if group is None:
            await ctx.error(f"Couldn't find a Roblox group named `{name}`.")
            return

        details = await roblox_service.get_group_details(group["id"])
        if details is None:
            details = group

        description = (details.get("description") or "").strip()
        if len(description) > 300:
            description = description[:300] + "…"

        owner = details.get("owner", {}).get("username", "None")
        body = f"**Owner** {owner}\n**Members** {details.get('memberCount', 0):,}"
        if description:
            body += f"\n\n{description}"

        embed = discord.Embed(title=details.get("name", name), description=body)
        embed.url = f"https://www.roblox.com/groups/{details.get('id', group['id'])}"
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="List the groups a Roblox user is in.",
        syntax=",roblox groups <username>",
        examples=[",roblox groups builderman"],
    )
    @roblox.command(name="groups")
    async def roblox_groups(self, ctx: commands.Context, *, username: str):
        user = await roblox_service.resolve_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a Roblox user named `{username}`.")
            return

        groups = await roblox_service.get_user_groups(user["id"])
        if not groups:
            await ctx.info(f"**{username}** isn't in any groups.")
            return

        lines = [f"**{g['group']['name']}** — {g['role']['name']}" for g in groups[:25]]
        embed = discord.Embed(title=f"@{user['name']}'s Groups", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- item

    @command_meta(
        category="Socials",
        description="Look up a Roblox catalog item.",
        syntax=",roblox item <name>",
        examples=[",roblox item Dominus"],
    )
    @roblox.command(name="item")
    async def roblox_item(self, ctx: commands.Context, *, name: str):
        item = await roblox_service.search_catalog_item(name)
        if item is None:
            await ctx.error(f"Couldn't find a Roblox catalog item named `{name}`.")
            return

        price = item.get("price")
        price_display = f"{price:,} Robux" if price else ("Free" if item.get("price") == 0 else "Not for sale")

        description = (
            f"**Creator** {item.get('creatorName', 'Unknown')}\n"
            f"**Price** {price_display}\n"
            f"**Favorites** {item.get('favoriteCount', 0):,}"
        )
        embed = discord.Embed(title=item.get("name", name), description=description)
        embed.url = f"https://www.roblox.com/catalog/{item.get('id')}"

        asset_id = item.get("id")
        if asset_id:
            thumbnail_url = await roblox_service.get_asset_thumbnail(asset_id)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

        await ctx.send(embed=embed)

    # ---------------------------------------------------------- minecraft

    @command_meta(
        category="Socials",
        description="Minecraft.",
        syntax=",minecraft",
        examples=[],
        require_args=False,
    )
    @commands.hybrid_group(name="minecraft", invoke_without_command=True)
    async def minecraft(self, ctx: commands.Context):
        await send_help(ctx, "minecraft")

    @minecraft.command(name="help")
    async def minecraft_help(self, ctx: commands.Context):
        await send_help(ctx, "minecraft")

    @command_meta(
        category="Socials",
        description="Look up a Minecraft player.",
        syntax=",minecraft player <username>",
        examples=[",minecraft player Notch"],
    )
    @minecraft.command(name="player")
    async def minecraft_player(self, ctx: commands.Context, *, username: str):
        player = await minecraft_service.get_player(username)
        if player is None:
            await ctx.error(f"Couldn't find a Minecraft player named `{username}`.")
            return

        description = f"**UUID** `{player['uuid']}`"
        embed = discord.Embed(title=player["name"], description=description)
        if player.get("skin_url"):
            embed.set_thumbnail(url=f"https://crafatar.com/renders/body/{player['uuid']}?overlay")
        if player.get("cape_url"):
            embed.add_field(name="Cape", value="Yes", inline=True)
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Look up a Minecraft server's status.",
        syntax=",minecraft server <address>",
        examples=[",minecraft server hypixel.net"],
    )
    @minecraft.command(name="server")
    async def minecraft_server(self, ctx: commands.Context, *, address: str):
        status = await minecraft_service.get_server_status(address)
        if status is None or not status.get("online"):
            await ctx.error(f"Couldn't reach a Minecraft server at `{address}`, or it's offline.")
            return

        players = status.get("players", {})
        motd_lines = status.get("motd", {}).get("clean", [])
        motd = " ".join(motd_lines) if motd_lines else "None"

        description = (
            f"**MOTD** {motd}\n"
            f"**Version** {status.get('version', 'Unknown')}\n"
            f"**Players** {players.get('online', 0)}/{players.get('max', 0)}"
        )
        embed = discord.Embed(title=address, description=description, color=discord.Color.green())
        icon = status.get("icon")
        if icon and icon.startswith("data:image"):
            pass  # base64 favicon - not worth decoding/uploading for a lookup command
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- github

    @command_meta(
        category="Socials",
        description="GitHub lookups.",
        syntax=",github (profile | repository | 2email)",
        examples=[",github"],
        require_args=False,
    )
    @commands.hybrid_group(name="github", invoke_without_command=True)
    async def github(self, ctx: commands.Context):
        await send_help(ctx, "github")

    @github.command(name="help")
    async def github_help(self, ctx: commands.Context):
        await send_help(ctx, "github")

    @command_meta(
        category="Socials",
        description="Look up a GitHub user.",
        syntax=",github profile <username>",
        examples=[",github profile torvalds"],
    )
    @github.command(name="profile")
    async def github_profile(self, ctx: commands.Context, *, username: str):
        user = await github_service.get_user(username)
        if user is None:
            await ctx.error(f"Couldn't find a GitHub user named `{username}`.")
            return

        description = (
            (f"{user['bio']}\n\n" if user.get("bio") else "")
            + f"**Name** {user.get('name') or 'Not set'}\n"
            + f"**Repos** {user.get('public_repos', 0):,}\n"
            + f"**Followers** {user.get('followers', 0):,} • **Following** {user.get('following', 0):,}\n"
            + (f"**Company** {user['company']}\n" if user.get("company") else "")
            + (f"**Location** {user['location']}\n" if user.get("location") else "")
        )
        embed = discord.Embed(title=f"@{user['login']}", description=description, url=user.get("html_url"))
        if user.get("avatar_url"):
            embed.set_thumbnail(url=user["avatar_url"])
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Look up a GitHub repository.",
        syntax=",github repository <name>",
        examples=[",github repository discord.py"],
        aliases=["repo"],
    )
    @github.command(name="repository", aliases=["repo"])
    async def github_repository(self, ctx: commands.Context, *, name: str):
        repo = await github_service.get_repo(name)
        if repo is None:
            await ctx.error(f"Couldn't find a GitHub repository matching `{name}`.")
            return

        description = (
            (f"{repo['description']}\n\n" if repo.get("description") else "")
            + f"⭐ **{repo.get('stargazers_count', 0):,}** stars • 🍴 **{repo.get('forks_count', 0):,}** forks "
            + f"• 👁 **{repo.get('watchers_count', 0):,}** watching\n"
            + f"**Language** {repo.get('language') or 'Unknown'}\n"
            + f"**Open Issues** {repo.get('open_issues_count', 0):,}"
        )
        embed = discord.Embed(title=repo.get("full_name", name), description=description, url=repo.get("html_url"))
        owner = repo.get("owner", {})
        if owner.get("avatar_url"):
            embed.set_thumbnail(url=owner["avatar_url"])
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Find public commit emails behind a GitHub user.",
        syntax=",github 2email <username>",
        examples=[",github 2email torvalds"],
    )
    @github.command(name="2email")
    async def github_2email(self, ctx: commands.Context, *, username: str):
        emails = await github_service.find_commit_emails(username)
        if not emails:
            await ctx.info(f"No public commit emails found for **{username}** (their recent public activity has none, or they're private).")
            return

        embed = discord.Embed(
            title=f"@{username}'s Public Commit Emails",
            description="\n".join(f"`{e}`" for e in emails[:25]),
        )
        embed.set_footer(text="Sourced from public push events - nothing hidden or scraped.")
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- spotify

    @command_meta(
        category="Socials",
        description="Search Spotify tracks, artists, albums, and previews.",
        syntax=",spotify (track | artist | album | preview)",
        examples=[",spotify"],
        require_args=False,
    )
    @commands.hybrid_group(name="spotify", invoke_without_command=True)
    async def spotify(self, ctx: commands.Context):
        await send_help(ctx, "spotify")

    @spotify.command(name="help")
    async def spotify_help(self, ctx: commands.Context):
        await send_help(ctx, "spotify")

    @command_meta(
        category="Socials",
        description="Look up a track on Spotify.",
        syntax=",spotify track <query>",
        examples=[",spotify track Bohemian Rhapsody"],
    )
    @spotify.command(name="track")
    async def spotify_track(self, ctx: commands.Context, *, query: str):
        track = await spotify_service.search_track(query)
        if track is None:
            await ctx.error(f"Couldn't find a track matching `{query}` (or Spotify isn't configured on this bot).")
            return

        artists = ", ".join(a["name"] for a in track.get("artists", []))
        description = (
            f"**Artist(s)** {artists}\n"
            f"**Album** {track.get('album', {}).get('name', 'Unknown')}\n"
            f"**Popularity** {track.get('popularity', 0)}/100"
        )
        embed = discord.Embed(
            title=track.get("name", query), description=description,
            url=track.get("external_urls", {}).get("spotify"),
        )
        images = track.get("album", {}).get("images", [])
        if images:
            embed.set_thumbnail(url=images[0]["url"])
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Look up an artist on Spotify.",
        syntax=",spotify artist <query>",
        examples=[",spotify artist Queen"],
    )
    @spotify.command(name="artist")
    async def spotify_artist(self, ctx: commands.Context, *, query: str):
        artist = await spotify_service.search_artist(query)
        if artist is None:
            await ctx.error(f"Couldn't find an artist matching `{query}` (or Spotify isn't configured on this bot).")
            return

        genres = ", ".join(artist.get("genres", [])[:5]) or "Unknown"
        description = (
            f"**Followers** {artist.get('followers', {}).get('total', 0):,}\n"
            f"**Popularity** {artist.get('popularity', 0)}/100\n"
            f"**Genres** {genres}"
        )
        embed = discord.Embed(
            title=artist.get("name", query), description=description,
            url=artist.get("external_urls", {}).get("spotify"),
        )
        images = artist.get("images", [])
        if images:
            embed.set_thumbnail(url=images[0]["url"])
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Look up an album on Spotify.",
        syntax=",spotify album <query>",
        examples=[",spotify album A Night at the Opera"],
    )
    @spotify.command(name="album")
    async def spotify_album(self, ctx: commands.Context, *, query: str):
        album = await spotify_service.search_album(query)
        if album is None:
            await ctx.error(f"Couldn't find an album matching `{query}` (or Spotify isn't configured on this bot).")
            return

        artists = ", ".join(a["name"] for a in album.get("artists", []))
        description = (
            f"**Artist(s)** {artists}\n"
            f"**Tracks** {album.get('total_tracks', 0)}\n"
            f"**Released** {album.get('release_date', 'Unknown')}"
        )
        embed = discord.Embed(
            title=album.get("name", query), description=description,
            url=album.get("external_urls", {}).get("spotify"),
        )
        images = album.get("images", [])
        if images:
            embed.set_thumbnail(url=images[0]["url"])
        await ctx.send(embed=embed)

    @command_meta(
        category="Socials",
        description="Play a 30-second preview of a track.",
        syntax=",spotify preview <query>",
        examples=[",spotify preview Bohemian Rhapsody"],
    )
    @spotify.command(name="preview")
    async def spotify_preview(self, ctx: commands.Context, *, query: str):
        track = await spotify_service.search_track(query)
        if track is None:
            await ctx.error(f"Couldn't find a track matching `{query}` (or Spotify isn't configured on this bot).")
            return

        preview_url = track.get("preview_url")
        if not preview_url:
            await ctx.error(f"**{track.get('name', query)}** has no 30-second preview available on Spotify.")
            return

        audio_bytes = await spotify_service.download_preview(preview_url)
        if audio_bytes is None:
            await ctx.error("Couldn't download that preview.")
            return

        artists = ", ".join(a["name"] for a in track.get("artists", []))
        file = discord.File(io.BytesIO(audio_bytes), filename="preview.mp3")
        await ctx.send(content=f"🎵 **{track.get('name', query)}** — {artists}", file=file)


async def setup(bot: commands.Bot):
    await bot.add_cog(Socials(bot))