"""Database access for the premium system."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.premium_models import PremiumConfig, PremiumPurchase


async def get_or_create_config(session: AsyncSession, guild_id: int) -> PremiumConfig:
    result = await session.execute(select(PremiumConfig).where(PremiumConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PremiumConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> PremiumConfig | None:
    result = await session.execute(select(PremiumConfig).where(PremiumConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: PremiumConfig, **fields) -> PremiumConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg


async def get_all_configs(session: AsyncSession) -> list[PremiumConfig]:
    result = await session.execute(select(PremiumConfig))
    return list(result.scalars().all())


# ---------------------------------------------------------- purchases

async def create_purchase(
    session: AsyncSession, guild_id: int, user_id: int, plan: str, billing_period: str,
) -> PremiumPurchase:
    purchase = PremiumPurchase(guild_id=guild_id, user_id=user_id, plan=plan, billing_period=billing_period)
    session.add(purchase)
    await session.commit()
    await session.refresh(purchase)
    return purchase


async def get_purchase(session: AsyncSession, purchase_id: int) -> PremiumPurchase | None:
    result = await session.execute(select(PremiumPurchase).where(PremiumPurchase.id == purchase_id))
    return result.scalar_one_or_none()


async def get_latest_pending_purchase(session: AsyncSession, guild_id: int, plan: str) -> PremiumPurchase | None:
    result = await session.execute(
        select(PremiumPurchase)
        .where(PremiumPurchase.guild_id == guild_id, PremiumPurchase.plan == plan, PremiumPurchase.status == "pending")
        .order_by(PremiumPurchase.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_purchase(session: AsyncSession, purchase: PremiumPurchase, **fields) -> PremiumPurchase:
    for key, value in fields.items():
        setattr(purchase, key, value)
    await session.commit()
    await session.refresh(purchase)
    return purchase