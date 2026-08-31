"""All database access for the level system."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.levels_models import LevelConfig, LevelIgnored, LevelRole, LevelUser


async def get_or_create_user(session: AsyncSession, guild_id: int, user_id: int) -> LevelUser:
    result = await session.execute(
        select(LevelUser).where(LevelUser.guild_id == guild_id, LevelUser.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = LevelUser(guild_id=guild_id, user_id=user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_or_create_config(session: AsyncSession, guild_id: int) -> LevelConfig:
    result = await session.execute(select(LevelConfig).where(LevelConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = LevelConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def add_xp(session: AsyncSession, guild_id: int, user_id: int, amount: int, *, voice: bool = False) -> LevelUser:
    user = await get_or_create_user(session, guild_id, user_id)
    user.total_xp += amount
    if voice:
        user.voice_xp += amount
    else:
        user.text_xp += amount
        user.message_count += 1
    await session.commit()
    await session.refresh(user)
    return user


async def remove_xp(session: AsyncSession, guild_id: int, user_id: int, amount: int) -> LevelUser:
    user = await get_or_create_user(session, guild_id, user_id)
    user.total_xp = max(0, user.total_xp - amount)
    await session.commit()
    await session.refresh(user)
    return user


async def set_xp(session: AsyncSession, guild_id: int, user_id: int, amount: int) -> LevelUser:
    user = await get_or_create_user(session, guild_id, user_id)
    user.total_xp = max(0, amount)
    await session.commit()
    await session.refresh(user)
    return user


async def set_level(session: AsyncSession, guild_id: int, user_id: int, level: int) -> LevelUser:
    user = await get_or_create_user(session, guild_id, user_id)
    user.level = max(0, level)
    await session.commit()
    await session.refresh(user)
    return user


async def reset_guild(session: AsyncSession, guild_id: int) -> None:
    await session.execute(delete(LevelUser).where(LevelUser.guild_id == guild_id))
    await session.commit()


async def get_leaderboard(session: AsyncSession, guild_id: int, limit: int = 10, offset: int = 0) -> list[LevelUser]:
    result = await session.execute(
        select(LevelUser)
        .where(LevelUser.guild_id == guild_id)
        .order_by(LevelUser.total_xp.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_roles(session: AsyncSession, guild_id: int) -> list[LevelRole]:
    result = await session.execute(
        select(LevelRole).where(LevelRole.guild_id == guild_id).order_by(LevelRole.rank)
    )
    return list(result.scalars().all())


async def add_role(session: AsyncSession, guild_id: int, rank: int, role_id: int, level_required: int) -> LevelRole:
    result = await session.execute(
        select(LevelRole).where(LevelRole.guild_id == guild_id, LevelRole.rank == rank)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.role_id = role_id
        existing.level_required = level_required
        await session.commit()
        await session.refresh(existing)
        return existing

    level_role = LevelRole(guild_id=guild_id, rank=rank, role_id=role_id, level_required=level_required)
    session.add(level_role)
    await session.commit()
    await session.refresh(level_role)
    return level_role


async def remove_role(session: AsyncSession, guild_id: int, rank: int) -> bool:
    result = await session.execute(
        select(LevelRole).where(LevelRole.guild_id == guild_id, LevelRole.rank == rank)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True


async def get_ignored(session: AsyncSession, guild_id: int) -> list[LevelIgnored]:
    result = await session.execute(select(LevelIgnored).where(LevelIgnored.guild_id == guild_id))
    return list(result.scalars().all())


async def add_ignored(session: AsyncSession, guild_id: int, target_id: int, target_type: str) -> None:
    session.add(LevelIgnored(guild_id=guild_id, target_id=target_id, target_type=target_type))
    await session.commit()


async def remove_ignored(session: AsyncSession, guild_id: int, target_id: int, target_type: str) -> bool:
    result = await session.execute(
        select(LevelIgnored).where(
            LevelIgnored.guild_id == guild_id,
            LevelIgnored.target_id == target_id,
            LevelIgnored.target_type == target_type,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True
