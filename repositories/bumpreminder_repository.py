"""Database access for ,bumpreminder."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.bumpreminder_models import BumpLeaderboardEntry, BumpReminderConfig


async def get_or_create_config(session: AsyncSession, guild_id: int) -> BumpReminderConfig:
    result = await session.execute(select(BumpReminderConfig).where(BumpReminderConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = BumpReminderConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> BumpReminderConfig | None:
    result = await session.execute(select(BumpReminderConfig).where(BumpReminderConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: BumpReminderConfig, **fields) -> BumpReminderConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg


async def get_due_configs(session: AsyncSession, now: datetime) -> list[BumpReminderConfig]:
    result = await session.execute(
        select(BumpReminderConfig).where(
            BumpReminderConfig.enabled.is_(True),
            BumpReminderConfig.next_bump_at.is_not(None),
            BumpReminderConfig.next_bump_at <= now,
            BumpReminderConfig.reminder_sent.is_(False),
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------- leaderboard

async def record_bump(session: AsyncSession, guild_id: int, user_id: int) -> int:
    result = await session.execute(
        select(BumpLeaderboardEntry).where(
            BumpLeaderboardEntry.guild_id == guild_id, BumpLeaderboardEntry.user_id == user_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = BumpLeaderboardEntry(guild_id=guild_id, user_id=user_id, bump_count=1)
        session.add(entry)
    else:
        entry.bump_count += 1
    await session.commit()
    await session.refresh(entry)
    return entry.bump_count


async def get_leaderboard(session: AsyncSession, guild_id: int, limit: int = 10) -> list[BumpLeaderboardEntry]:
    result = await session.execute(
        select(BumpLeaderboardEntry)
        .where(BumpLeaderboardEntry.guild_id == guild_id)
        .order_by(BumpLeaderboardEntry.bump_count.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
