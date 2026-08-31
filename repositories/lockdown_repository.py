"""Database access for ,lockdown ignore."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.lockdown_models import LockdownIgnore


async def add_ignore(session: AsyncSession, guild_id: int, target_id: int, target_type: str) -> bool:
    result = await session.execute(
        select(LockdownIgnore).where(LockdownIgnore.guild_id == guild_id, LockdownIgnore.target_id == target_id)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(LockdownIgnore(guild_id=guild_id, target_id=target_id, target_type=target_type))
    await session.commit()
    return True


async def remove_ignore(session: AsyncSession, guild_id: int, target_id: int) -> bool:
    result = await session.execute(
        select(LockdownIgnore).where(LockdownIgnore.guild_id == guild_id, LockdownIgnore.target_id == target_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_ignored(session: AsyncSession, guild_id: int, target_id: int) -> bool:
    result = await session.execute(
        select(LockdownIgnore).where(LockdownIgnore.guild_id == guild_id, LockdownIgnore.target_id == target_id)
    )
    return result.scalar_one_or_none() is not None


async def get_ignore_list(session: AsyncSession, guild_id: int) -> list[LockdownIgnore]:
    result = await session.execute(select(LockdownIgnore).where(LockdownIgnore.guild_id == guild_id))
    return list(result.scalars().all())


async def get_ignored_channel_ids(session: AsyncSession, guild_id: int) -> set[int]:
    result = await session.execute(
        select(LockdownIgnore.target_id).where(LockdownIgnore.guild_id == guild_id, LockdownIgnore.target_type == "channel")
    )
    return {row[0] for row in result.all()}


async def get_ignored_role_ids(session: AsyncSession, guild_id: int) -> set[int]:
    result = await session.execute(
        select(LockdownIgnore.target_id).where(LockdownIgnore.guild_id == guild_id, LockdownIgnore.target_type == "role")
    )
    return {row[0] for row in result.all()}