"""Database access for ,reminder."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.reminder_models import Reminder


async def create_reminder(
    session: AsyncSession, user_id: int, channel_id: int, guild_id: int | None,
    description: str | None, remind_at: datetime,
) -> Reminder:
    row = Reminder(
        user_id=user_id, channel_id=channel_id, guild_id=guild_id,
        description=description, remind_at=remind_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_for_user(session: AsyncSession, user_id: int) -> list[Reminder]:
    result = await session.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at)
    )
    return list(result.scalars().all())


async def get_due(session: AsyncSession, now: datetime) -> list[Reminder]:
    result = await session.execute(select(Reminder).where(Reminder.remind_at <= now))
    return list(result.scalars().all())


async def delete_reminder(session: AsyncSession, reminder_id: int) -> bool:
    result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True