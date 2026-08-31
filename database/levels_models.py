"""Level system tables: per-user stats, config, roles, ignore lists."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class LevelUser(Base):
    __tablename__ = "level_users"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    total_xp: Mapped[int] = mapped_column(Integer, default=0)
    text_xp: Mapped[int] = mapped_column(Integer, default=0)
    voice_xp: Mapped[int] = mapped_column(Integer, default=0)

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    voice_minutes: Mapped[int] = mapped_column(Integer, default=0)

    level: Mapped[int] = mapped_column(Integer, default=0)

    last_xp_at: Mapped[float] = mapped_column(Float, default=0.0)  # unix timestamp, for cooldown


class LevelConfig(Base):
    __tablename__ = "level_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # locked by default
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    stack_roles: Mapped[bool] = mapped_column(Boolean, default=True)

    levelup_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    levelup_message: Mapped[str] = mapped_column(
        String(512), default="{user.mention} reached Level {level}!"
    )
    leaderboard_title: Mapped[str] = mapped_column(String(128), default="Leaderboard")

    xp_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60)


class LevelRole(Base):
    __tablename__ = "level_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)

    role_id: Mapped[int] = mapped_column(BigInteger)
    level_required: Mapped[int] = mapped_column(Integer)


class LevelIgnored(Base):
    __tablename__ = "level_ignored"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), primary_key=True)  # "role" | "channel"
