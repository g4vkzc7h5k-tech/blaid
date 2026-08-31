"""Security tables: antinuke config/whitelist and honeypot config."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AntinukeConfig(Base):
    __tablename__ = "antinuke_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # "strip_roles" | "kick" | "ban"
    punishment: Mapped[str] = mapped_column(String(16), default="strip_roles")

    ban_threshold: Mapped[int] = mapped_column(Integer, default=3)
    kick_threshold: Mapped[int] = mapped_column(Integer, default=3)
    channel_delete_threshold: Mapped[int] = mapped_column(Integer, default=3)
    role_delete_threshold: Mapped[int] = mapped_column(Integer, default=3)
    window_seconds: Mapped[int] = mapped_column(Integer, default=10)

    # basic anti-raid / join gate
    join_gate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    join_gate_min_account_age_hours: Mapped[int] = mapped_column(Integer, default=24)


class AntinukeWhitelist(Base):
    __tablename__ = "antinuke_whitelist"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class AntinukeAdmin(Base):
    """Users (besides the server owner) allowed to configure antinuke -
    separate from Manage Guild/Administrator, since antinuke is
    sensitive enough to warrant its own explicit allowlist."""

    __tablename__ = "antinuke_admins"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


ANTINUKE_MODULES = [
    "ban", "botadd", "channel", "emoji", "guildupdate", "integration",
    "integrationcreate", "integrationdelete", "integrationupdate", "invite",
    "kick", "role", "soundboard", "sticker", "vanity", "webhook",
]
ANTINUKE_PUNISHMENTS = ["ban", "kick", "timeout", "strip", "stripstaff", "jail"]


class AntinukeModule(Base):
    """Per-module config - one row per (guild, module_name). See
    ANTINUKE_MODULES above for the full set of module names."""

    __tablename__ = "antinuke_modules"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module_name: Mapped[str] = mapped_column(String(32), primary_key=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    punishment: Mapped[str] = mapped_column(String(16), default="ban")  # see ANTINUKE_PUNISHMENTS
    threshold: Mapped[int] = mapped_column(Integer, default=3)
    track_commands: Mapped[bool] = mapped_column(Boolean, default=False)


class HoneypotConfig(Base):
    __tablename__ = "honeypot_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(16), default="ban")  # "ban" | "kick" | "softban"
    purge_days: Mapped[int] = mapped_column(Integer, default=0)  # 0-7
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    caught_count: Mapped[int] = mapped_column(Integer, default=0)


class FakePermission(Base):
    """A Discord permission granted to a role through Blade only - it
    lets members with that role use bot commands gated on that
    permission, without actually granting the permission in Discord."""

    __tablename__ = "fake_permissions"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)