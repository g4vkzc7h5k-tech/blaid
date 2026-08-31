"""Database access for ,verification."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.verification_models import VerificationConfig


async def get_or_create_config(session: AsyncSession, guild_id: int) -> VerificationConfig:
    result = await session.execute(select(VerificationConfig).where(VerificationConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = VerificationConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> VerificationConfig | None:
    result = await session.execute(select(VerificationConfig).where(VerificationConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: VerificationConfig, **fields) -> VerificationConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg