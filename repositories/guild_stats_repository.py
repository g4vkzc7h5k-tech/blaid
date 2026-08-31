"""Database access for daily join/leave stats, powering ,guild stats."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.guild_stats_models import GuildDailyStats


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


async def _get_or_create_today(session: AsyncSession, guild_id: int) -> GuildDailyStats:
    today = _today()
    result = await session.execute(
        select(GuildDailyStats).where(GuildDailyStats.guild_id == guild_id, GuildDailyStats.date == today)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = GuildDailyStats(guild_id=guild_id, date=today, joins=0, leaves=0)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def record_join(session: AsyncSession, guild_id: int) -> None:
    row = await _get_or_create_today(session, guild_id)
    row.joins += 1
    await session.commit()


async def record_leave(session: AsyncSession, guild_id: int) -> None:
    row = await _get_or_create_today(session, guild_id)
    row.leaves += 1
    await session.commit()


async def get_today(session: AsyncSession, guild_id: int) -> tuple[int, int]:
    today = _today()
    result = await session.execute(
        select(GuildDailyStats).where(GuildDailyStats.guild_id == guild_id, GuildDailyStats.date == today)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return 0, 0
    return row.joins, row.leaves