"""Database access for ,autopfp."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.autopfp_models import AutoPfpChannel


async def add_channel(
    session: AsyncSession, guild_id: int, channel_id: int, categories: str,
    interval_seconds: int, next_post_at: datetime,
) -> AutoPfpChannel:
    result = await session.execute(
        select(AutoPfpChannel).where(AutoPfpChannel.guild_id == guild_id, AutoPfpChannel.channel_id == channel_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.categories = categories
        existing.interval_seconds = interval_seconds
        await session.commit()
        await session.refresh(existing)
        return existing

    row = AutoPfpChannel(
        guild_id=guild_id, channel_id=channel_id, categories=categories,
        interval_seconds=interval_seconds, next_post_at=next_post_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_channel(session: AsyncSession, guild_id: int, channel_id: int) -> AutoPfpChannel | None:
    result = await session.execute(
        select(AutoPfpChannel).where(AutoPfpChannel.guild_id == guild_id, AutoPfpChannel.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_channels_for_guild(session: AsyncSession, guild_id: int) -> list[AutoPfpChannel]:
    result = await session.execute(select(AutoPfpChannel).where(AutoPfpChannel.guild_id == guild_id))
    return list(result.scalars().all())


async def get_due(session: AsyncSession, now: datetime) -> list[AutoPfpChannel]:
    result = await session.execute(select(AutoPfpChannel).where(AutoPfpChannel.next_post_at <= now))
    return list(result.scalars().all())


async def update_channel(session: AsyncSession, row: AutoPfpChannel, **fields) -> AutoPfpChannel:
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def remove_channel(session: AsyncSession, guild_id: int, channel_id: int) -> bool:
    result = await session.execute(
        select(AutoPfpChannel).where(AutoPfpChannel.guild_id == guild_id, AutoPfpChannel.channel_id == channel_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True