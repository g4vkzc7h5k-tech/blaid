"""Economy system - balances, cooldowns, and the shop."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class EconomyBalance(Base):
    __tablename__ = "economy_balances"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet: Mapped[int] = mapped_column(BigInteger, default=0)
    bank: Mapped[int] = mapped_column(BigInteger, default=0)

    last_daily: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_work: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_crime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rob: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EconomyShopItem(Base):
    __tablename__ = "economy_shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(BigInteger)


class EconomyInventoryItem(Base):
    __tablename__ = "economy_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    item_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)