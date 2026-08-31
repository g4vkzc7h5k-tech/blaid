"""Verification gate - holds risky new accounts in a role until a
moderator approves them - ,verification / ,verifygate."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class VerificationConfig(Base):
    __tablename__ = "verification_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # where held members wait
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # the quarantine role
    threshold_days: Mapped[int] = mapped_column(Integer, default=7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)