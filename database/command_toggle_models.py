"""Server-side command enable/disable - ,enable / ,disable. A
target_id of 0 means "server-wide"; otherwise it's a channel or role
ID the command is specifically disabled for."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DisabledCommand(Base):
    __tablename__ = "disabled_commands"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)