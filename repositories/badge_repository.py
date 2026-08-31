"""Database access for ,badge."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.badge_models import BadgeAwarded, BadgeConfig, BadgeRole


async def get_or_create_config(session: AsyncSession, guild_id: int) -> BadgeConfig:
    result = await session.execute(select(BadgeConfig).where(BadgeConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = BadgeConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def get_config(session: AsyncSession, guild_id: int) -> BadgeConfig | None:
    result = await session.execute(select(BadgeConfig).where(BadgeConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def update_config(session: AsyncSession, cfg: BadgeConfig, **fields) -> BadgeConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg


# ---------------------------------------------------------- roles

async def add_role(session: AsyncSession, guild_id: int, role_id: int) -> bool:
    result = await session.execute(
        select(BadgeRole).where(BadgeRole.guild_id == guild_id, BadgeRole.role_id == role_id)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(BadgeRole(guild_id=guild_id, role_id=role_id))
    await session.commit()
    return True


async def remove_role(session: AsyncSession, guild_id: int, role_id: int) -> bool:
    result = await session.execute(
        select(BadgeRole).where(BadgeRole.guild_id == guild_id, BadgeRole.role_id == role_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_roles(session: AsyncSession, guild_id: int) -> list[int]:
    result = await session.execute(select(BadgeRole.role_id).where(BadgeRole.guild_id == guild_id))
    return [row[0] for row in result.all()]


# ---------------------------------------------------------- awarded tracking

async def is_awarded(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(BadgeAwarded).where(BadgeAwarded.guild_id == guild_id, BadgeAwarded.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def mark_awarded(session: AsyncSession, guild_id: int, user_id: int) -> None:
    session.add(BadgeAwarded(guild_id=guild_id, user_id=user_id))
    await session.commit()


async def unmark_awarded(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(BadgeAwarded).where(BadgeAwarded.guild_id == guild_id, BadgeAwarded.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()


async def clear_config(session: AsyncSession, guild_id: int) -> None:
    result = await session.execute(select(BadgeRole).where(BadgeRole.guild_id == guild_id))
    for row in result.scalars().all():
        await session.delete(row)

    result = await session.execute(select(BadgeAwarded).where(BadgeAwarded.guild_id == guild_id))
    for row in result.scalars().all():
        await session.delete(row)

    await session.commit()