"""
Giveaway settings tables.

- GiveawayUserSettings: per-user DM preferences (not guild-scoped -
  a user's "DM me when my giveaways end" preference follows them
  across every server, matching how these settings work in most
  giveaway bots).
- GiveawayTemplate: per-guild custom embed template (title/description/color).
- GiveawayBlacklist: roles that cannot enter giveaways in a guild.
- GiveawayRoleMax: the number of entries a member with a given role
  receives (weight), used for weighted winner selection.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class GiveawayUserSettings(Base):
    __tablename__ = "giveaway_user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dm_on_creator_end: Mapped[bool] = mapped_column(Boolean, default=True)
    dm_on_winner: Mapped[bool] = mapped_column(Boolean, default=True)


class GiveawayTemplate(Base):
    __tablename__ = "giveaway_template"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)  # supports {prize}
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "#RRGGBB"


class GiveawayBlacklist(Base):
    __tablename__ = "giveaway_blacklist"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class GiveawayRoleMax(Base):
    __tablename__ = "giveaway_role_max"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    max_entries: Mapped[int] = mapped_column(Integer, default=1)