"""Database access for ,schedule."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.schedule_models import ScheduledMessage


async def create_scheduled(
    session: AsyncSession, guild_id: int, channel_id: int, message: str, next_run_at: datetime,
    interval_seconds: int | None, creator_id: int,
) -> ScheduledMessage:
    row = ScheduledMessage(
        guild_id=guild_id, channel_id=channel_id, message=message, next_run_at=next_run_at,
        interval_seconds=interval_seconds, creator_id=creator_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_scheduled(session: AsyncSession, scheduled_id: int) -> ScheduledMessage | None:
    result = await session.execute(select(ScheduledMessage).where(ScheduledMessage.id == scheduled_id))
    return result.scalar_one_or_none()


async def get_all_for_guild(session: AsyncSession, guild_id: int) -> list[ScheduledMessage]:
    result = await session.execute(
        select(ScheduledMessage).where(ScheduledMessage.guild_id == guild_id).order_by(ScheduledMessage.next_run_at)
    )
    return list(result.scalars().all())


async def get_due(session: AsyncSession, now: datetime) -> list[ScheduledMessage]:
    result = await session.execute(select(ScheduledMessage).where(ScheduledMessage.next_run_at <= now))
    return list(result.scalars().all())


async def update_scheduled(session: AsyncSession, row: ScheduledMessage, **fields) -> ScheduledMessage:
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_scheduled(session: AsyncSession, scheduled_id: int, guild_id: int | None = None) -> bool:
    result = await session.execute(select(ScheduledMessage).where(ScheduledMessage.id == scheduled_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    if guild_id is not None and row.guild_id != guild_id:
        return False
    await session.delete(row)
    await session.commit()
    return True