"""Permissions blocked from being assigned via role commands (currently
enforced by ,fakepermissions add - see security.py)."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DeniedPermission(Base):
    __tablename__ = "denied_permissions"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)