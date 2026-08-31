"""Ignore list for ,lockdown - a "role" entry stays able to send
messages even during a lockdown; a "channel" entry is skipped entirely
by ,lockdown all."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class LockdownIgnore(Base):
    __tablename__ = "lockdown_ignores"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16))  # "role" or "channel"