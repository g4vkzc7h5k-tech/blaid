"""Database access for ,funnel."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.funnel_models import FunnelJoinRecord


async def record_join(session: AsyncSession, guild_id: int, user_id: int) -> None:
    session.add(FunnelJoinRecord(guild_id=guild_id, user_id=user_id))
    await session.commit()


async def mark_spoken(session: AsyncSession, guild_id: int, user_id: int) -> None:
    """Marks the member's most recent (un-marked) join record as
    having spoken - a no-op if they have no join record at all (e.g.
    they joined before this feature was added)."""
    result = await session.execute(
        select(FunnelJoinRecord)
        .where(
            FunnelJoinRecord.guild_id == guild_id,
            FunnelJoinRecord.user_id == user_id,
            FunnelJoinRecord.has_spoken == False,  # noqa: E712
        )
        .order_by(FunnelJoinRecord.joined_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return
    record.has_spoken = True
    await session.commit()


async def get_records_since(session: AsyncSession, guild_id: int, since: datetime) -> list[FunnelJoinRecord]:
    result = await session.execute(
        select(FunnelJoinRecord).where(FunnelJoinRecord.guild_id == guild_id, FunnelJoinRecord.joined_at >= since)
    )
    return list(result.scalars().all())