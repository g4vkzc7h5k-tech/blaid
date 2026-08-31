"""Database access for the configurable logging system."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.logging_models import LogChannel, LogIgnore, LogSettings


async def add_log_channel(session: AsyncSession, guild_id: int, channel_id: int, event_type: str) -> bool:
    result = await session.execute(
        select(LogChannel).where(
            LogChannel.guild_id == guild_id, LogChannel.channel_id == channel_id, LogChannel.event_type == event_type
        )
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(LogChannel(guild_id=guild_id, channel_id=channel_id, event_type=event_type))
    await session.commit()
    return True


async def remove_log_channel(session: AsyncSession, guild_id: int, channel_id: int, event_type: str) -> bool:
    result = await session.execute(
        select(LogChannel).where(
            LogChannel.guild_id == guild_id, LogChannel.channel_id == channel_id, LogChannel.event_type == event_type
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_channels_for_event(session: AsyncSession, guild_id: int, event_type: str) -> list[int]:
    result = await session.execute(
        select(LogChannel.channel_id).where(LogChannel.guild_id == guild_id, LogChannel.event_type == event_type)
    )
    return [row[0] for row in result.all()]


async def get_all_for_guild(session: AsyncSession, guild_id: int) -> list[tuple[int, str]]:
    result = await session.execute(
        select(LogChannel.channel_id, LogChannel.event_type).where(LogChannel.guild_id == guild_id)
    )
    return [(row[0], row[1]) for row in result.all()]


async def add_ignore(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(LogIgnore).where(LogIgnore.guild_id == guild_id, LogIgnore.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        session.add(LogIgnore(guild_id=guild_id, user_id=user_id))
        await session.commit()


async def remove_ignore(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(LogIgnore).where(LogIgnore.guild_id == guild_id, LogIgnore.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()


async def is_ignored(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(LogIgnore).where(LogIgnore.guild_id == guild_id, LogIgnore.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def get_ignore_list(session: AsyncSession, guild_id: int) -> list[int]:
    result = await session.execute(select(LogIgnore.user_id).where(LogIgnore.guild_id == guild_id))
    return [row[0] for row in result.all()]


async def get_color(session: AsyncSession, guild_id: int) -> int | None:
    result = await session.execute(select(LogSettings).where(LogSettings.guild_id == guild_id))
    row = result.scalar_one_or_none()
    return row.color if row else None


async def set_color(session: AsyncSession, guild_id: int, color: int) -> None:
    result = await session.execute(select(LogSettings).where(LogSettings.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(LogSettings(guild_id=guild_id, color=color))
    else:
        row.color = color
    await session.commit()