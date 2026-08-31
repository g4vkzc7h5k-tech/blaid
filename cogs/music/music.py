"""Music commands. Isolated cog - see services/music_service.py for why."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from services.music_service import MusicError, MusicManager


def _format_duration(seconds: int) -> str:
    if not seconds:
        return "Live/Unknown"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = MusicManager(bot)

    async def _require_voice(self, ctx: commands.Context) -> discord.VoiceChannel | None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.error("You need to be in a voice channel to use this.")
            return None
        return ctx.author.voice.channel

    @command_meta(
        category="Music",
        description="Plays a song from a URL or search query, queueing it if something is already playing.",
        syntax=",play <url or search query>",
        examples=[",play lofi hip hop radio"],
    )
    @commands.hybrid_command(name="play")
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str):
        voice_channel = await self._require_voice(ctx)
        if voice_channel is None:
            return

        async with ctx.typing():
            try:
                track = await self.manager.resolve_track(query, ctx.author.id)
            except MusicError as exc:
                await ctx.error(str(exc))
                return

            started = await self.manager.enqueue(ctx.guild, voice_channel, track, ctx.channel)

        if not started:
            await ctx.success(f"Queued: **{track.title}**")

    @command_meta(
        category="Music",
        description="Pauses the currently playing track.",
        syntax=",pause",
        examples=[",pause"],
        require_args=False,
    )
    @commands.hybrid_command(name="pause")
    @commands.guild_only()
    async def pause(self, ctx: commands.Context):
        player = self.manager.get_player(ctx.guild.id)
        if player.voice_client is None or not player.voice_client.is_playing():
            await ctx.error("Nothing is playing.")
            return
        player.voice_client.pause()
        await ctx.success("Paused.")

    @command_meta(
        category="Music",
        description="Resumes a paused track.",
        syntax=",resume",
        examples=[",resume"],
        require_args=False,
    )
    @commands.hybrid_command(name="resume")
    @commands.guild_only()
    async def resume(self, ctx: commands.Context):
        player = self.manager.get_player(ctx.guild.id)
        if player.voice_client is None or not player.voice_client.is_paused():
            await ctx.error("Nothing is paused.")
            return
        player.voice_client.resume()
        await ctx.success("Resumed.")

    @command_meta(
        category="Music",
        description="Joins a voice channel fully muted and deafened and stays connected until manually disconnected. Run again to leave.",
        syntax=",247 [channel]",
        examples=[",247", ",247 General Voice"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.hybrid_command(name="247")
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def two_four_seven(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        player = self.manager.get_player(ctx.guild.id)

        if player.voice_client is not None and player.voice_client.is_connected():
            await player.voice_client.disconnect()
            player.voice_client = None
            await ctx.success("Left the voice channel. 24/7 mode is now off.")
            return

        if channel is None:
            channel = await self._require_voice(ctx)
            if channel is None:
                return

        player.voice_client = await channel.connect(self_mute=True, self_deaf=True)
        await ctx.success(f"Joined {channel.mention} and will stay connected until manually disconnected (run `,247` again to leave).")

    @command_meta(
        category="Music",
        description="Stops playback, clears the queue, and disconnects.",
        syntax=",stop",
        examples=[",stop"],
        require_args=False,
    )
    @commands.hybrid_command(name="stop")
    @commands.guild_only()
    async def stop(self, ctx: commands.Context):
        await self.manager.stop(ctx.guild.id)
        await ctx.success("Stopped and disconnected.")

    @command_meta(
        category="Music",
        description="Skips the currently playing track.",
        syntax=",skip",
        examples=[",skip"],
        require_args=False,
    )
    @commands.hybrid_command(name="skip")
    @commands.guild_only()
    async def skip(self, ctx: commands.Context):
        if self.manager.skip(ctx.guild.id):
            await ctx.success("Skipped.")
        else:
            await ctx.error("Nothing is playing.")

    @command_meta(
        category="Music",
        description="Shows the current queue.",
        syntax=",queue",
        examples=[",queue"],
        require_args=False,
    )
    @commands.hybrid_command(name="queue", aliases=["q"])
    @commands.guild_only()
    async def queue(self, ctx: commands.Context):
        player = self.manager.get_player(ctx.guild.id)
        if not player.queue and player.current is None:
            await ctx.info("The queue is empty.")
            return

        embed = discord.Embed(title="Queue")
        if player.current is not None:
            embed.add_field(name="Now Playing", value=f"{player.current.title} ({_format_duration(player.current.duration)})", inline=False)

        if player.queue:
            lines = [f"`{i+1}.` {t.title} ({_format_duration(t.duration)})" for i, t in enumerate(player.queue[:15])]
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)

        await ctx.send(embed=embed)

    @command_meta(
        category="Music",
        description="Shows the currently playing track.",
        syntax=",nowplaying",
        examples=[",nowplaying"],
        require_args=False,
    )
    @commands.hybrid_command(name="nowplaying", aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context):
        player = self.manager.get_player(ctx.guild.id)
        if player.current is None:
            await ctx.info("Nothing is playing.")
            return
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{player.current.title}]({player.current.webpage_url})",
        )
        embed.add_field(name="Duration", value=_format_duration(player.current.duration))
        embed.add_field(name="Requested by", value=f"<@{player.current.requester_id}>")
        await ctx.send(embed=embed)

    @command_meta(
        category="Music",
        description="Sets playback volume (0-100).",
        syntax=",volume <0-100>",
        examples=[",volume 50"],
    )
    @commands.hybrid_command(name="volume", aliases=["vol"])
    @commands.guild_only()
    async def volume(self, ctx: commands.Context, level: int):
        level = max(0, min(level, 100))
        player = self.manager.get_player(ctx.guild.id)
        player.volume = level / 100
        if player.voice_client is not None and player.voice_client.source is not None:
            player.voice_client.source.volume = player.volume
        await ctx.success(f"Volume set to `{level}%`.")

    @command_meta(
        category="Music",
        description="Toggles looping the current track.",
        syntax=",loop",
        examples=[",loop"],
        require_args=False,
    )
    @commands.hybrid_command(name="loop")
    @commands.guild_only()
    async def loop(self, ctx: commands.Context):
        player = self.manager.get_player(ctx.guild.id)
        player.loop = not player.loop
        await ctx.success(f"Loop is now **{'on' if player.loop else 'off'}**.")

    @command_meta(
        category="Music",
        description="Shuffles the current queue.",
        syntax=",shuffle",
        examples=[",shuffle"],
        require_args=False,
    )
    @commands.hybrid_command(name="shuffle")
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context):
        self.manager.shuffle(ctx.guild.id)
        await ctx.success("Queue shuffled.")

    @command_meta(
        category="Music",
        description="Removes a track from the queue by its position number.",
        syntax=",remove <position>",
        examples=[",remove 2"],
    )
    @commands.hybrid_command(name="remove")
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, position: int):
        track = self.manager.remove(ctx.guild.id, position - 1)
        if track is None:
            await ctx.error("Invalid queue position.")
            return
        await ctx.success(f"Removed **{track.title}** from the queue.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))