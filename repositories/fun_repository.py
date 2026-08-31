"""Database access for fun-command interaction counts and vape flavors."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.fun_models import InteractionCount, VapeFlavor


async def increment_count(session: AsyncSession, guild_id: int, author_id: int, target_id: int, action: str) -> int:
    """Increments and returns the new count for this (author, target,
    action) triple, creating the row if it doesn't exist yet."""
    result = await session.execute(
        select(InteractionCount).where(
            InteractionCount.guild_id == guild_id,
            InteractionCount.author_id == author_id,
            InteractionCount.target_id == target_id,
            InteractionCount.action == action,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = InteractionCount(guild_id=guild_id, author_id=author_id, target_id=target_id, action=action, count=1)
        session.add(row)
    else:
        row.count += 1
    await session.commit()
    await session.refresh(row)
    return row.count


async def set_vape_flavor(session: AsyncSession, guild_id: int, user_id: int, flavor: str) -> None:
    result = await session.execute(
        select(VapeFlavor).where(VapeFlavor.guild_id == guild_id, VapeFlavor.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(VapeFlavor(guild_id=guild_id, user_id=user_id, flavor=flavor))
    else:
        row.flavor = flavor
    await session.commit()


async def get_vape_flavor(session: AsyncSession, guild_id: int, user_id: int) -> str | None:
    result = await session.execute(
        select(VapeFlavor).where(VapeFlavor.guild_id == guild_id, VapeFlavor.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.flavor if row else None