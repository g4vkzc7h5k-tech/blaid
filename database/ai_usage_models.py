"""Tracks how many ,ai questions each member has asked today, per
guild - resets naturally since each row is keyed by date."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AiUsage(Base):
    __tablename__ = "ai_usage"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # "YYYY-MM-DD", UTC
    count: Mapped[int] = mapped_column(Integer, default=0)
