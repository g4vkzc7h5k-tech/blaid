"""Autoresponder tables."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AutoResponder(Base):
    __tablename__ = "autoresponders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    trigger: Mapped[str] = mapped_column(String(128))
    response: Mapped[str] = mapped_column(Text)


class AutoResponderRole(Base):
    """If a responder has any rows here, only members with one of these
    roles trigger it. No rows = everyone can trigger it."""

    __tablename__ = "autoresponder_roles"

    autoresponder_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)