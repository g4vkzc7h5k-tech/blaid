"""DM members a message when they join - ,joindm."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_MESSAGE = "Welcome to **{guild.name}**, {user.mention}!"


class JoinDmConfig(Base):
    __tablename__ = "joindm_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_MESSAGE)