"""Custom booster roles - one role per server booster, positioned
under a configurable base role."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class BoosterRoleConfig(Base):
    __tablename__ = "booster_role_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    base_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hoist_default: Mapped[bool] = mapped_column(Boolean, default=False)
    limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited


class BoosterRole(Base):
    """One row per booster's own custom role."""

    __tablename__ = "booster_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger)
    role_id: Mapped[int] = mapped_column(BigInteger)


class BoosterRoleFilterWord(Base):
    """Words blocked from being used in a booster role name."""

    __tablename__ = "booster_role_filter_words"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    word: Mapped[str] = mapped_column(String(64), primary_key=True)