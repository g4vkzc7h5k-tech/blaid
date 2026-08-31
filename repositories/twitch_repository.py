"""Database access for ,twitch."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.twitch_models import TwitchFollow


async def add_follow(session: AsyncSession, guild_id: int, login: str, channel_id: int) -> bool:
    login = login.lower()
    result = await session.execute(
        select(TwitchFollow).where(TwitchFollow.guild_id == guild_id, TwitchFollow.login == login)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(TwitchFollow(guild_id=guild_id, login=login, channel_id=channel_id))
    await session.commit()
    return True


async def remove_follow(session: AsyncSession, guild_id: int, login: str) -> bool:
    login = login.lower()
    result = await session.execute(
        select(TwitchFollow).where(TwitchFollow.guild_id == guild_id, TwitchFollow.login == login)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_follow(session: AsyncSession, guild_id: int, login: str) -> TwitchFollow | None:
    result = await session.execute(
        select(TwitchFollow).where(TwitchFollow.guild_id == guild_id, TwitchFollow.login == login.lower())
    )
    return result.scalar_one_or_none()


async def get_follows_for_guild(session: AsyncSession, guild_id: int) -> list[TwitchFollow]:
    result = await session.execute(select(TwitchFollow).where(TwitchFollow.guild_id == guild_id))
    return list(result.scalars().all())


async def get_all_follows(session: AsyncSession) -> list[TwitchFollow]:
    result = await session.execute(select(TwitchFollow))
    return list(result.scalars().all())


async def update_follow(session: AsyncSession, follow: TwitchFollow, **fields) -> TwitchFollow:
    for key, value in fields.items():
        setattr(follow, key, value)
    await session.commit()
    await session.refresh(follow)
    return follow


async def reset_guild_follows(session: AsyncSession, guild_id: int) -> int:
    rows = await get_follows_for_guild(session, guild_id)
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)