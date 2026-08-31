"""Database access for ,youtube."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.youtube_models import YoutubeFollow


async def add_follow(
    session: AsyncSession, guild_id: int, channel_query: str, discord_channel_id: int,
    youtube_channel_id: str, uploads_playlist_id: str, channel_title: str,
) -> bool:
    result = await session.execute(
        select(YoutubeFollow).where(YoutubeFollow.guild_id == guild_id, YoutubeFollow.channel_query == channel_query)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(YoutubeFollow(
        guild_id=guild_id, channel_query=channel_query, discord_channel_id=discord_channel_id,
        youtube_channel_id=youtube_channel_id, uploads_playlist_id=uploads_playlist_id,
        channel_title=channel_title,
    ))
    await session.commit()
    return True


async def remove_follow(session: AsyncSession, guild_id: int, channel_query: str) -> bool:
    result = await session.execute(
        select(YoutubeFollow).where(YoutubeFollow.guild_id == guild_id, YoutubeFollow.channel_query == channel_query)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_follow(session: AsyncSession, guild_id: int, channel_query: str) -> YoutubeFollow | None:
    result = await session.execute(
        select(YoutubeFollow).where(YoutubeFollow.guild_id == guild_id, YoutubeFollow.channel_query == channel_query)
    )
    return result.scalar_one_or_none()


async def get_follows_for_guild(session: AsyncSession, guild_id: int) -> list[YoutubeFollow]:
    result = await session.execute(select(YoutubeFollow).where(YoutubeFollow.guild_id == guild_id))
    return list(result.scalars().all())


async def get_all_follows(session: AsyncSession) -> list[YoutubeFollow]:
    result = await session.execute(select(YoutubeFollow))
    return list(result.scalars().all())


async def update_follow(session: AsyncSession, follow: YoutubeFollow, **fields) -> YoutubeFollow:
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