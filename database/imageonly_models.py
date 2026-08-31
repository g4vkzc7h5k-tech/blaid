"""Channels where messages without an attachment get deleted
automatically - ,imageonly."""

from __future__ import annotations

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ImageOnlyChannel(Base):
    __tablename__ = "image_only_channels"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger)