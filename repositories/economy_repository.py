"""Database access for the economy system."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.economy_models import EconomyBalance, EconomyInventoryItem, EconomyShopItem


async def get_or_create_balance(session: AsyncSession, guild_id: int, user_id: int) -> EconomyBalance:
    result = await session.execute(
        select(EconomyBalance).where(EconomyBalance.guild_id == guild_id, EconomyBalance.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = EconomyBalance(guild_id=guild_id, user_id=user_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def update_balance(session: AsyncSession, row: EconomyBalance, **fields) -> EconomyBalance:
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def add_wallet(session: AsyncSession, guild_id: int, user_id: int, amount: int) -> EconomyBalance:
    row = await get_or_create_balance(session, guild_id, user_id)
    row.wallet = max(0, row.wallet + amount)
    await session.commit()
    await session.refresh(row)
    return row


async def get_leaderboard(session: AsyncSession, guild_id: int, limit: int = 10) -> list[EconomyBalance]:
    result = await session.execute(
        select(EconomyBalance)
        .where(EconomyBalance.guild_id == guild_id)
        .order_by((EconomyBalance.wallet + EconomyBalance.bank).desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def reset_balance(session: AsyncSession, guild_id: int, user_id: int) -> None:
    row = await get_or_create_balance(session, guild_id, user_id)
    row.wallet = 0
    row.bank = 0
    await session.commit()


# ---------------------------------------------------------- shop

async def add_shop_item(session: AsyncSession, guild_id: int, name: str, price: int) -> EconomyShopItem:
    item = EconomyShopItem(guild_id=guild_id, name=name, price=price)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_shop_items(session: AsyncSession, guild_id: int) -> list[EconomyShopItem]:
    result = await session.execute(select(EconomyShopItem).where(EconomyShopItem.guild_id == guild_id))
    return list(result.scalars().all())


async def get_shop_item(session: AsyncSession, item_id: int) -> EconomyShopItem | None:
    result = await session.execute(select(EconomyShopItem).where(EconomyShopItem.id == item_id))
    return result.scalar_one_or_none()


async def add_inventory_item(session: AsyncSession, guild_id: int, user_id: int, item_id: int, quantity: int = 1) -> None:
    result = await session.execute(
        select(EconomyInventoryItem).where(
            EconomyInventoryItem.guild_id == guild_id,
            EconomyInventoryItem.user_id == user_id,
            EconomyInventoryItem.item_id == item_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(EconomyInventoryItem(guild_id=guild_id, user_id=user_id, item_id=item_id, quantity=quantity))
    else:
        row.quantity += quantity
    await session.commit()


async def get_inventory(session: AsyncSession, guild_id: int, user_id: int) -> list[EconomyInventoryItem]:
    result = await session.execute(
        select(EconomyInventoryItem).where(EconomyInventoryItem.guild_id == guild_id, EconomyInventoryItem.user_id == user_id)
    )
    return list(result.scalars().all())