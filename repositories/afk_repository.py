"""Database access for ,afk."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.afk_models import AfkStatus


async def set_afk(session: AsyncSession, guild_id: int, user_id: int, status: str) -> None:
    result = await session.execute(
        select(AfkStatus).where(AfkStatus.guild_id == guild_id, AfkStatus.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(AfkStatus(guild_id=guild_id, user_id=user_id, status=status))
    else:
        row.status = status
    await session.commit()


async def get_afk(session: AsyncSession, guild_id: int, user_id: int) -> AfkStatus | None:
    result = await session.execute(
        select(AfkStatus).where(AfkStatus.guild_id == guild_id, AfkStatus.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def remove_afk(session: AsyncSession, guild_id: int, user_id: int) -> AfkStatus | None:
    result = await session.execute(
        select(AfkStatus).where(AfkStatus.guild_id == guild_id, AfkStatus.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    await session.delete(row)
    await session.commit()
    return row