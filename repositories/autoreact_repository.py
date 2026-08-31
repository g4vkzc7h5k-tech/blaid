"""Database access for ,autoreact."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.autoreact_models import AutoReact


async def add_autoreact(session: AsyncSession, guild_id: int, keyword: str, emojis: str) -> bool:
    result = await session.execute(
        select(AutoReact).where(AutoReact.guild_id == guild_id, AutoReact.keyword == keyword)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.emojis = emojis
        await session.commit()
        return False

    session.add(AutoReact(guild_id=guild_id, keyword=keyword, emojis=emojis))
    await session.commit()
    return True


async def get_all_for_guild(session: AsyncSession, guild_id: int) -> list[AutoReact]:
    result = await session.execute(select(AutoReact).where(AutoReact.guild_id == guild_id))
    return list(result.scalars().all())


async def remove_autoreact(session: AsyncSession, guild_id: int, keyword: str) -> bool:
    result = await session.execute(
        select(AutoReact).where(AutoReact.guild_id == guild_id, AutoReact.keyword == keyword)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def clear_autoreacts(session: AsyncSession, guild_id: int) -> int:
    rows = await get_all_for_guild(session, guild_id)
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)