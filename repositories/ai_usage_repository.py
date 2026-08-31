"""Database access for ,ai's daily-question limit."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.ai_usage_models import AiUsage


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


async def get_usage_today(session: AsyncSession, guild_id: int, user_id: int) -> int:
    result = await session.execute(
        select(AiUsage).where(AiUsage.guild_id == guild_id, AiUsage.user_id == user_id, AiUsage.date == _today())
    )
    row = result.scalar_one_or_none()
    return row.count if row else 0


async def increment_usage_today(session: AsyncSession, guild_id: int, user_id: int) -> int:
    today = _today()
    result = await session.execute(
        select(AiUsage).where(AiUsage.guild_id == guild_id, AiUsage.user_id == user_id, AiUsage.date == today)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AiUsage(guild_id=guild_id, user_id=user_id, date=today, count=1)
        session.add(row)
    else:
        row.count += 1
    await session.commit()
    return row.count
