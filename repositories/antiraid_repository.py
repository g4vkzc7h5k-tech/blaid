"""Database access for ,antiraid."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.antiraid_models import AntiraidConfig, AntiraidUsernamePattern, AntiraidWhitelist


async def get_or_create_config(session: AsyncSession, guild_id: int) -> AntiraidConfig:
    result = await session.execute(select(AntiraidConfig).where(AntiraidConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = AntiraidConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> AntiraidConfig | None:
    result = await session.execute(select(AntiraidConfig).where(AntiraidConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: AntiraidConfig, **fields) -> AntiraidConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg


# ---------------------------------------------------------- whitelist

async def add_whitelist(session: AsyncSession, guild_id: int, target_id: int, target_type: str) -> bool:
    result = await session.execute(
        select(AntiraidWhitelist).where(AntiraidWhitelist.guild_id == guild_id, AntiraidWhitelist.target_id == target_id)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(AntiraidWhitelist(guild_id=guild_id, target_id=target_id, target_type=target_type))
    await session.commit()
    return True


async def remove_whitelist(session: AsyncSession, guild_id: int, target_id: int) -> bool:
    result = await session.execute(
        select(AntiraidWhitelist).where(AntiraidWhitelist.guild_id == guild_id, AntiraidWhitelist.target_id == target_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_whitelist(session: AsyncSession, guild_id: int) -> list[AntiraidWhitelist]:
    result = await session.execute(select(AntiraidWhitelist).where(AntiraidWhitelist.guild_id == guild_id))
    return list(result.scalars().all())


async def is_whitelisted(session: AsyncSession, guild_id: int, target_ids: list[int]) -> bool:
    result = await session.execute(
        select(AntiraidWhitelist).where(AntiraidWhitelist.guild_id == guild_id, AntiraidWhitelist.target_id.in_(target_ids))
    )
    return result.scalar_one_or_none() is not None


# ---------------------------------------------------------- username patterns

async def add_username_pattern(session: AsyncSession, guild_id: int, pattern: str) -> bool:
    result = await session.execute(
        select(AntiraidUsernamePattern).where(
            AntiraidUsernamePattern.guild_id == guild_id, AntiraidUsernamePattern.pattern == pattern
        )
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(AntiraidUsernamePattern(guild_id=guild_id, pattern=pattern))
    await session.commit()
    return True


async def remove_username_pattern(session: AsyncSession, guild_id: int, pattern: str) -> bool:
    result = await session.execute(
        select(AntiraidUsernamePattern).where(
            AntiraidUsernamePattern.guild_id == guild_id, AntiraidUsernamePattern.pattern == pattern
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_username_patterns(session: AsyncSession, guild_id: int) -> list[str]:
    result = await session.execute(
        select(AntiraidUsernamePattern.pattern).where(AntiraidUsernamePattern.guild_id == guild_id)
    )
    return [row[0] for row in result.all()]