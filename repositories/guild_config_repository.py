"""Shared database access for GuildConfig. Any feature that needs a
guild's jail/category/logs-channel setup reads it from here instead
of querying GuildConfig directly, so there's one place that knows how
to find/create the row."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GuildConfig


async def get(session: AsyncSession, guild_id: int) -> GuildConfig | None:
    result = await session.execute(select(GuildConfig).where(GuildConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def get_or_create(session: AsyncSession, guild_id: int) -> GuildConfig:
    cfg = await get(session, guild_id)
    if cfg is None:
        cfg = GuildConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg