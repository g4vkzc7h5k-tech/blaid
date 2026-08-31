"""Tracks daily join/leave counts per guild, for ,guild stats. One row
per (guild, date) - date is a plain 'YYYY-MM-DD' string in UTC."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class GuildDailyStats(Base):
    __tablename__ = "guild_daily_stats"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    joins: Mapped[int] = mapped_column(Integer, default=0)
    leaves: Mapped[int] = mapped_column(Integer, default=0)