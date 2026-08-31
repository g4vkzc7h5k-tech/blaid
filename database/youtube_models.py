"""YouTube channels a guild follows for upload/live announcements."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "{youtube.channel} just uploaded a new video!\n{youtube.url}"


class YoutubeFollow(Base):
    __tablename__ = "youtube_follows"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_query: Mapped[str] = mapped_column(String(100), primary_key=True)  # what the user typed (handle/name/ID)

    youtube_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # resolved UC... ID
    uploads_playlist_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # cached to save quota

    discord_channel_id: Mapped[int] = mapped_column(BigInteger)
    channel_title: Mapped[str] = mapped_column(String(100), default="")  # friendly name for {youtube.channel}
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Edge-detection state for the poll loop - not user-facing config.
    last_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)