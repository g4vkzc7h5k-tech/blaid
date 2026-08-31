"""Tracks how many times one member has done a fun action to another -
e.g. ,kiss counting "for the 3rd time." One row per (guild, author,
target, action) triple."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class InteractionCount(Base):
    __tablename__ = "fun_interaction_counts"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    author_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class VapeFlavor(Base):
    """A user's chosen vape flavor, set via ,vape flavor - referenced
    by the self-only ,vape command."""

    __tablename__ = "fun_vape_flavors"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    flavor: Mapped[str] = mapped_column(String(64), default="menthol")