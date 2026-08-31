"""Forced nicknames - a member's nickname is locked to a specific
value until explicitly cleared via ,forcenickname <member> (no name)."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ForcedNickname(Base):
    __tablename__ = "forced_nicknames"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32))