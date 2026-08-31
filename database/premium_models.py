"""Premium system - server-wide premium (higher limits + premium-only
commands) and customize premium (per-server bot branding), plus the
manual purchase/billing-channel flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class PremiumConfig(Base):
    __tablename__ = "premium_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    server_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    server_premium_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # None = lifetime

    customize_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    customize_premium_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PremiumPurchase(Base):
    """One row per billing-channel purchase attempt - tracks it from
    plan selection through payment-method choice through to the
    optional form answer, for the owner to review before approving."""

    __tablename__ = "premium_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)

    plan: Mapped[str] = mapped_column(String(20))  # "server" | "customize"
    billing_period: Mapped[str] = mapped_column(String(20))  # "monthly" | "yearly" | "lifetime"
    payment_method: Mapped[str] = mapped_column(String(20), nullable=True)  # "card" | "paypal"

    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | denied
    payment_detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # their form answer

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
