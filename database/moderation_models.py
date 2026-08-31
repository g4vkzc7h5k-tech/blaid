"""Moderation case history (bans, kicks, warns, timeouts, jails)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ModerationCase(Base):
    __tablename__ = "moderation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_number: Mapped[int] = mapped_column(Integer)  # per-guild sequential number

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    moderator_id: Mapped[int] = mapped_column(BigInteger)

    action_type: Mapped[str] = mapped_column(String(32))  # ban, unban, kick, warn, timeout, jail, unjail, lock, unlock
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WarnPunishment(Base):
    """An auto-punishment tier: at exactly `count` active warnings, the
    given punishment fires automatically. `punishment` is "kick", "ban",
    or "timeout:<seconds>" (parsed and stored as seconds at add-time)."""

    __tablename__ = "warn_punishments"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, primary_key=True)
    punishment: Mapped[str] = mapped_column(String(64))


class JailRecord(Base):
    """Tracks who is currently jailed and when (if ever) they should be
    automatically unjailed. unjail_at = None means an indefinite jail."""

    __tablename__ = "jail_records"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    unjail_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HardbanRecord(Base):
    """Marks a ban as a hardban - while this row exists, only the
    server owner or an antinuke admin can ,unban that user. Deleted
    once they're unbanned (by anyone eligible to do so)."""

    __tablename__ = "hardban_records"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)