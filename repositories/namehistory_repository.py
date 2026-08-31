"""Database access for ,namehistory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.namehistory_models import NameHistoryEntry


async def record_name(session: AsyncSession, user_id: int, name: str) -> None:
    """Only records if this name differs from the most recently
    recorded one for this user, so re-seeding on every join/message
    doesn't spam duplicate rows."""
    result = await session.execute(
        select(NameHistoryEntry)
        .where(NameHistoryEntry.user_id == user_id)
        .order_by(NameHistoryEntry.recorded_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if latest is not None and latest.name == name:
        return

    session.add(NameHistoryEntry(user_id=user_id, name=name))
    await session.commit()


async def get_name_history(session: AsyncSession, user_id: int) -> list[NameHistoryEntry]:
    result = await session.execute(
        select(NameHistoryEntry).where(NameHistoryEntry.user_id == user_id).order_by(NameHistoryEntry.recorded_at.desc())
    )
    return list(result.scalars().all())