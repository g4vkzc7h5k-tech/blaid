"""Configurable event logging - which channel(s) get which event
type(s), per-guild ignore list, and per-guild embed color."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

# Matches the picker exactly: Message, Member, Role, Channel, Invite,
# Moderation, Voice, Emoji, Sticker, Integration, Server.
LOG_EVENT_TYPES = [
    "message", "member", "role", "channel", "invite", "moderation",
    "voice", "emoji", "sticker", "integration", "server",
]


class LogChannel(Base):
    __tablename__ = "log_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)


class LogIgnore(Base):
    __tablename__ = "log_ignores"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class LogSettings(Base):
    __tablename__ = "log_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    color: Mapped[int] = mapped_column(Integer, default=0x2B2D31)