"""Autorole, reaction role, and button role tables."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Autorole(Base):
    __tablename__ = "autoroles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class ReactionRole(Base):
    __tablename__ = "reaction_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    emoji: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger)


class ButtonRole(Base):
    __tablename__ = "button_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    custom_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    label: Mapped[str] = mapped_column(String(80), default="Role")
    style: Mapped[str] = mapped_column(String(16), default="secondary")
    emoji: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StickyRole(Base):
    """A member's role IDs at the moment they left - used by ,role
    restore to re-apply them if they come back. Stored as a comma-
    separated string of role IDs; @everyone is never included."""

    __tablename__ = "sticky_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_ids: Mapped[str] = mapped_column(String(2000), default="")