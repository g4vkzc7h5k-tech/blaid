"""
Antiraid - a separate, join/message-pattern-based raid protection
system from antinuke (which watches audit-log actions by staff/
compromised staff accounts). Antiraid watches new members and message
bursts instead: young accounts, default avatars, join floods, mass
mentions, unverified bots, and username patterns.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AntiraidConfig(Base):
    __tablename__ = "antiraid_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # master switch
    locked_down: Mapped[bool] = mapped_column(Boolean, default=False)  # ,antiraid state

    age_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    age_action: Mapped[str] = mapped_column(String(16), default="kick")
    age_threshold_days: Mapped[int] = mapped_column(Integer, default=7)

    avatar_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_action: Mapped[str] = mapped_column(String(16), default="kick")

    massjoin_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    massjoin_action: Mapped[str] = mapped_column(String(16), default="kick")
    massjoin_threshold: Mapped[int] = mapped_column(Integer, default=10)
    massjoin_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    massjoin_punish: Mapped[bool] = mapped_column(Boolean, default=False)

    massmention_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    massmention_action: Mapped[str] = mapped_column(String(16), default="timeout")
    massmention_threshold: Mapped[int] = mapped_column(Integer, default=5)
    massmention_timeframe: Mapped[int] = mapped_column(Integer, default=10)
    massmention_lock: Mapped[bool] = mapped_column(Boolean, default=False)

    unverifiedbots_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    unverifiedbots_action: Mapped[str] = mapped_column(String(16), default="kick")


class AntiraidWhitelist(Base):
    __tablename__ = "antiraid_whitelist"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16))  # "user" or "role"


class AntiraidUsernamePattern(Base):
    """Blocked username substrings/patterns - new members whose
    username contains one get the configured action applied."""

    __tablename__ = "antiraid_username_patterns"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(100), primary_key=True)