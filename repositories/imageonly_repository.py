"""Database access for ,imageonly."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.imageonly_models import ImageOnlyChannel


async def enable(session: AsyncSession, guild_id: int, channel_id: int) -> None:
    result = await session.execute(select(ImageOnlyChannel).where(ImageOnlyChannel.channel_id == channel_id))
    if result.scalar_one_or_none() is not None:
        return
    session.add(ImageOnlyChannel(channel_id=channel_id, guild_id=guild_id))
    await session.commit()


async def disable(session: AsyncSession, channel_id: int) -> bool:
    result = await session.execute(select(ImageOnlyChannel).where(ImageOnlyChannel.channel_id == channel_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_enabled(session: AsyncSession, channel_id: int) -> bool:
    result = await session.execute(select(ImageOnlyChannel).where(ImageOnlyChannel.channel_id == channel_id))
    return result.scalar_one_or_none() is not None