"""Twitch channels a guild follows for live announcements."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "{twitch.creator.name} is now live playing {twitch.category}!\n{twitch.url}"


class TwitchFollow(Base):
    __tablename__ = "twitch_follows"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    login: Mapped[str] = mapped_column(String(64), primary_key=True)  # Twitch username, lowercase

    channel_id: Mapped[int] = mapped_column(BigInteger)
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)

    # Edge-detection state for the poll loop - not user-facing config.
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    last_stream_id: Mapped[str | None] = mapped_column(String(64), nullable=True)