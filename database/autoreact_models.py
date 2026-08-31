"""Automatic reactions to message keywords - ,autoreact."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AutoReact(Base):
    __tablename__ = "autoreacts"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), primary_key=True)
    emojis: Mapped[str] = mapped_column(String(200))  # comma-separated