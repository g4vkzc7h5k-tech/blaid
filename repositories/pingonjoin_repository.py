"""Database access for ,pingonjoin."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.pingonjoin_models import PingOnJoinConfig


async def get_or_create_config(session: AsyncSession, guild_id: int) -> PingOnJoinConfig:
    result = await session.execute(select(PingOnJoinConfig).where(PingOnJoinConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PingOnJoinConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> PingOnJoinConfig | None:
    result = await session.execute(select(PingOnJoinConfig).where(PingOnJoinConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: PingOnJoinConfig, **fields) -> PingOnJoinConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg