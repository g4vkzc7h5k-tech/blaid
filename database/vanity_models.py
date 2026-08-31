"""Reward members who put your vanity in their custom status -
,vanity."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "Thanks for repping **{vanity}**, {user.mention}!"


class VanityConfig(Base):
    __tablename__ = "vanity_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pattern: Mapped[str | None] = mapped_column(String(100), nullable=True)
    strict: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)


class VanityRole(Base):
    __tablename__ = "vanity_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class VanityAwarded(Base):
    """Tracks who currently holds the vanity reward, so we only
    announce/award once and can revoke it if they stop repping."""

    __tablename__ = "vanity_awarded"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)