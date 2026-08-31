"""Scheduled messages - post once later, or on a repeating interval -
,schedule."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = one-time
    creator_id: Mapped[int] = mapped_column(BigInteger)