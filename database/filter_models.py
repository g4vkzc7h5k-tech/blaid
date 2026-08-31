"""Chat filter (,filter / ,chatfilter) tables."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

FILTER_MODULES = [
    "links", "spam", "caps", "emoji", "invites", "massmention",
    "spoilers", "musicfiles", "images", "repetition", "walloftext",
    "malicious", "nsfw", "nicknames",
]
FILTER_PUNISHMENTS = ["delete", "warn", "timeout", "kick", "ban"]


class FilterConfig(Base):
    __tablename__ = "filter_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    default_punishment: Mapped[str] = mapped_column(String(16), default="delete")

    # The Discord AutoMod rule ID holding the custom word/phrase/regex
    # list, so edits update the same native rule instead of creating a
    # new one each time. None until the first sync creates it.
    automod_rule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class FilterModule(Base):
    """Per-module config for the 15 built-in categories - one row per
    (guild, module_name). See FILTER_MODULES above."""

    __tablename__ = "filter_modules"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module_name: Mapped[str] = mapped_column(String(32), primary_key=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    punishment: Mapped[str] = mapped_column(String(16), default="delete")
    threshold: Mapped[int] = mapped_column(Integer, default=5)


class FilterWord(Base):
    """Custom filtered words/phrases/regex patterns. `kind` is one of
    'word' (,filter add), 'phrase' (,filter blacklist), or 'regex'
    (,filter regex). `is_preset` marks entries added in bulk by
    ,filter wordmigrate, so ,filter unmigrate can cleanly remove only
    those without touching manually-added entries."""

    __tablename__ = "filter_words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    value: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default="word")  # word | phrase | regex
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)


class FilterWhitelist(Base):
    """Users/roles exempt from the filter entirely."""

    __tablename__ = "filter_whitelist"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(8), default="user")  # user | role


class FilterExemptChannel(Base):
    __tablename__ = "filter_exempt_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class FilterStrike(Base):
    """One row per (guild, user) tracking how many times the filter has
    punished them - separate from antinuke's rolling window, since
    filter strikes are meant to persist and be viewable/resettable."""

    __tablename__ = "filter_strikes"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)