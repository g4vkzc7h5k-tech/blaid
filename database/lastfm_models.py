"""Last.fm account links - global per Discord user, not per-guild,
matching how Last.fm accounts actually work (one account, used
everywhere) - ,lastfm set / ,fm."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class LastfmAccount(Base):
    __tablename__ = "lastfm_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LastfmSettings(Base):
    """Per-user ,fm customization - ,lastfm mode/embed/color/react."""

    __tablename__ = "lastfm_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    embed_color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex, e.g. "#FF0000"
    compact_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    fm_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    reactions: Mapped[str | None] = mapped_column(String(64), nullable=True)  # comma-separated emoji


class LastfmFriend(Base):
    """,lastfm friends - a one-way follow list used by friendwktrack/
    friendwkalbum/neighbours."""

    __tablename__ = "lastfm_friends"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    friend_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)