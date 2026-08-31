"""Database access for personal (,prefix self set) prefixes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserPrefix


async def set_user_prefix(session: AsyncSession, user_id: int, prefix: str) -> None:
    result = await session.execute(select(UserPrefix).where(UserPrefix.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(UserPrefix(user_id=user_id, prefix=prefix))
    else:
        row.prefix = prefix
    await session.commit()


async def get_user_prefix(session: AsyncSession, user_id: int) -> str | None:
    result = await session.execute(select(UserPrefix).where(UserPrefix.user_id == user_id))
    row = result.scalar_one_or_none()
    return row.prefix if row else None


async def delete_user_prefix(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(UserPrefix).where(UserPrefix.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True