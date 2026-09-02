"""Bump reminders for Disboard - ,bumpreminder."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DISBOARD_BOT_ID = 302050872383242240
BUMP_COOLDOWN_SECONDS = 2 * 60 * 60  # Disboard's real cooldown - 2 hours

DEFAULT_THANKYOU = "Thanks for bumping the server, {user.mention}! I'll remind everyone in 2 hours."
DEFAULT_REMINDER = "⏰ It's time to bump the server again! Use `/bump`."


class BumpReminderConfig(Base):
    __tablename__ = "bumpreminder_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thankyou_message: Mapped[str] = mapped_column(Text, default=DEFAULT_THANKYOU)
    reminder_message: Mapped[str] = mapped_column(Text, default=DEFAULT_REMINDER)
    next_bump_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)


class BumpLeaderboardEntry(Base):
    __tablename__ = "bumpreminder_leaderboard"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bump_count: Mapped[int] = mapped_column(Integer, default=0)
