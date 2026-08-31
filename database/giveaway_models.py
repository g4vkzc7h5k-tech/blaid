"""Giveaway tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Giveaway(Base):
    __tablename__ = "giveaways"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    host_id: Mapped[int] = mapped_column(BigInteger)

    prize: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_count: Mapped[int] = mapped_column(Integer, default=1)

    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended: Mapped[bool] = mapped_column(Boolean, default=False)


class GiveawayEntry(Base):
    __tablename__ = "giveaway_entries"

    giveaway_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)