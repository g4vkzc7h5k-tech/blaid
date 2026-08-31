"""Briefly pings new members in a channel on join - ,pingonjoin."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "{user.mention}"


class PingOnJoinConfig(Base):
    __tablename__ = "pingonjoin_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delete_after_seconds: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)