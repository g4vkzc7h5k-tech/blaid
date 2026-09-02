"""Custom DM/channel messages for moderation commands - ,invoke."""

from __future__ import annotations

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

VALID_COMMANDS = (
    "ban", "hardban", "softban", "unban", "kick", "timeout", "untimeout",
    "jail", "unjail", "mute", "unmute", "warn",
)
VALID_TYPES = ("dm", "text")


class InvokeMessage(Base):
    __tablename__ = "invoke_messages"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command: Mapped[str] = mapped_column(String(32), primary_key=True)
    message_type: Mapped[str] = mapped_column(String(8), primary_key=True)  # "dm" | "text"
    content: Mapped[str] = mapped_column(Text)
