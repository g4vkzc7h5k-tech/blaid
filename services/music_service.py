"""
Music playback engine.

Deliberately isolated: nothing outside cogs/music imports this module,
and this module never imports anything from moderation/levels/tickets/
etc. If yt-dlp or ffmpeg are missing/misconfigured, only music breaks -
the rest of Blade keeps running.

Requires ffmpeg to be installed on the host and available on PATH.
PebbleHost's Python bot environment typically has it preinstalled;
if not, the ,play command will raise a clear error instead of crashing
the bot process.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

import discord

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    title: str
    stream_url: str
    webpage_url: str
    duration: int
    requester_id: int


@dataclass
class GuildPlayer:
    guild_id: int
    voice_client: discord.VoiceClient | None = None
    queue: list[Track] = field(default_factory=list)
    current: Track | None = None
    loop: bool = False
    volume: float = 0.5
    text_channel: discord.abc.Messageable | None = None

    def next_track(self) -> Track | None:
        if self.loop and self.current is not None:
            return self.current
        if not self.queue:
            return None
        return self.queue.pop(0)


class MusicError(Exception):
    pass


class MusicManager:
    """One instance shared by the Music cog; holds a GuildPlayer per guild."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(guild_id=guild_id)
        return self.players[guild_id]

    async def resolve_track(self, query: str, requester_id: int) -> Track:
        if not YTDLP_AVAILABLE:
            raise MusicError(
                "Music support requires the `yt-dlp` package to be installed "
                "(`pip install yt-dlp`)."
            )

        loop = asyncio.get_event_loop()

        def extract():
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                return info

        try:
            info = await loop.run_in_executor(None, extract)
        except Exception as exc:  # yt-dlp raises various exception types
            raise MusicError(f"Couldn't find or load that track: {exc}") from exc

        return Track(
            title=info.get("title", "Unknown title"),
            stream_url=info["url"],
            webpage_url=info.get("webpage_url", query),
            duration=int(info.get("duration") or 0),
            requester_id=requester_id,
        )

    async def play_next(self, guild: discord.Guild) -> None:
        player = self.get_player(guild.id)
        if player.voice_client is None:
            return

        track = player.next_track()
        player.current = track

        if track is None:
            return

        def after_playback(error: Exception | None):
            fut = asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)
            try:
                fut.result()
            except Exception:
                pass

        source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=player.volume)
        player.voice_client.play(source, after=after_playback)

        if player.text_channel is not None:
            try:
                await player.text_channel.send(f"▶️ Now playing: **{track.title}**")
            except discord.HTTPException:
                pass

    async def enqueue(self, guild: discord.Guild, voice_channel: discord.VoiceChannel, track: Track, text_channel: discord.abc.Messageable) -> bool:
        """Returns True if playback started immediately, False if queued behind something already playing."""
        player = self.get_player(guild.id)
        player.text_channel = text_channel

        if player.voice_client is None or not player.voice_client.is_connected():
            player.voice_client = await voice_channel.connect()

        player.queue.append(track)

        if not player.voice_client.is_playing() and not player.voice_client.is_paused():
            await self.play_next(guild)
            return True
        return False

    def skip(self, guild_id: int) -> bool:
        player = self.get_player(guild_id)
        if player.voice_client is None or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
            return False
        player.loop = False  # skipping should not replay the current track
        player.voice_client.stop()  # triggers after_playback -> play_next
        return True

    def shuffle(self, guild_id: int) -> None:
        random.shuffle(self.get_player(guild_id).queue)

    def remove(self, guild_id: int, index: int) -> Track | None:
        queue = self.get_player(guild_id).queue
        if 0 <= index < len(queue):
            return queue.pop(index)
        return None

    async def stop(self, guild_id: int) -> None:
        player = self.get_player(guild_id)
        player.queue.clear()
        player.current = None
        player.loop = False
        if player.voice_client is not None:
            if player.voice_client.is_playing() or player.voice_client.is_paused():
                player.voice_client.stop()
            await player.voice_client.disconnect()
            player.voice_client = None
