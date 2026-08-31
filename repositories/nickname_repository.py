"""Database access for ,forcenickname."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.nickname_models import ForcedNickname


async def set_forced_nickname(session: AsyncSession, guild_id: int, user_id: int, nickname: str) -> None:
    result = await session.execute(
        select(ForcedNickname).where(ForcedNickname.guild_id == guild_id, ForcedNickname.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(ForcedNickname(guild_id=guild_id, user_id=user_id, nickname=nickname))
    else:
        row.nickname = nickname
    await session.commit()


async def remove_forced_nickname(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(ForcedNickname).where(ForcedNickname.guild_id == guild_id, ForcedNickname.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_forced_nickname(session: AsyncSession, guild_id: int, user_id: int) -> str | None:
    result = await session.execute(
        select(ForcedNickname).where(ForcedNickname.guild_id == guild_id, ForcedNickname.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.nickname if row else None