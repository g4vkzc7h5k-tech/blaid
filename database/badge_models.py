"""Reward members who equip your server tag - ,badge."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "Thanks for repping our tag, {user.mention}!"


class BadgeConfig(Base):
    __tablename__ = "badge_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)


class BadgeRole(Base):
    __tablename__ = "badge_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class BadgeAwarded(Base):
    """Tracks who currently holds the badge reward, so we only
    announce/award once and can revoke it if they unequip the tag."""

    __tablename__ = "badge_awarded"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)