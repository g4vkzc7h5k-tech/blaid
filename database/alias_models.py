"""Per-guild command alias table."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class CommandAlias(Base):
    __tablename__ = "command_aliases"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alias_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    # May contain {0}, {1}, ... placeholders substituted with the args
    # the user typed after the alias, e.g. "warn {0} spamming".
    command_template: Mapped[str] = mapped_column(String(256))
