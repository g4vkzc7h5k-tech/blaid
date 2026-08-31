"""
Core shared tables: Guild and GuildConfig.

Every other model that needs guild-scoped settings should reference
GuildConfig or store its own guild_id column - never duplicate these
fields elsewhere.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Guild(Base):
    __tablename__ = "guilds"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(8), default=",")
    joined_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserPrefix(Base):
    """A personal prefix set via ,prefix self set - overrides the
    server's prefix for that user in every server Blade is in."""

    __tablename__ = "user_prefixes"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(8))


class GuildConfig(Base):
    __tablename__ = "guild_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Setup / moderation infrastructure - deliberately minimal: one
    # category, one jail channel, one jail role, one logs channel.
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    jail_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    jail_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    imute_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rmute_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    logs_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    website_url_override: Mapped[str | None] = mapped_column(String(256), nullable=True)
    setup_complete: Mapped[bool] = mapped_column(Boolean, default=False)
