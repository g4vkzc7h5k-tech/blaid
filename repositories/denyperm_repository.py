"""Database access for ,denyperm."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.denyperm_models import DeniedPermission


async def add_denied_permission(session: AsyncSession, guild_id: int, permission: str) -> bool:
    result = await session.execute(
        select(DeniedPermission).where(DeniedPermission.guild_id == guild_id, DeniedPermission.permission == permission)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(DeniedPermission(guild_id=guild_id, permission=permission))
    await session.commit()
    return True


async def remove_denied_permission(session: AsyncSession, guild_id: int, permission: str) -> bool:
    result = await session.execute(
        select(DeniedPermission).where(DeniedPermission.guild_id == guild_id, DeniedPermission.permission == permission)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def clear_denied_permissions(session: AsyncSession, guild_id: int) -> int:
    result = await session.execute(select(DeniedPermission).where(DeniedPermission.guild_id == guild_id))
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


async def get_denied_permissions(session: AsyncSession, guild_id: int) -> list[str]:
    result = await session.execute(select(DeniedPermission.permission).where(DeniedPermission.guild_id == guild_id))
    return [row[0] for row in result.all()]


async def is_permission_denied(session: AsyncSession, guild_id: int, permission: str) -> bool:
    result = await session.execute(
        select(DeniedPermission).where(DeniedPermission.guild_id == guild_id, DeniedPermission.permission == permission)
    )
    return result.scalar_one_or_none() is not None