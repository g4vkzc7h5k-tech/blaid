"""Tracks each join event per guild and whether that member ever sent
a message afterward, powering ,funnel (joined / spoke / stayed)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class FunnelJoinRecord(Base):
    __tablename__ = "funnel_join_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    has_spoken: Mapped[bool] = mapped_column(Boolean, default=False)