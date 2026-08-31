"""Database access for ,boosterrole."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.boosterrole_models import BoosterRole, BoosterRoleConfig, BoosterRoleFilterWord


async def get_or_create_config(session: AsyncSession, guild_id: int) -> BoosterRoleConfig:
    result = await session.execute(select(BoosterRoleConfig).where(BoosterRoleConfig.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = BoosterRoleConfig(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def update_config(session: AsyncSession, config: BoosterRoleConfig, **fields) -> BoosterRoleConfig:
    for key, value in fields.items():
        setattr(config, key, value)
    await session.commit()
    await session.refresh(config)
    return config


async def create_booster_role(session: AsyncSession, guild_id: int, owner_id: int, role_id: int) -> BoosterRole:
    row = BoosterRole(guild_id=guild_id, owner_id=owner_id, role_id=role_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_booster_role(session: AsyncSession, guild_id: int, owner_id: int) -> BoosterRole | None:
    result = await session.execute(
        select(BoosterRole).where(BoosterRole.guild_id == guild_id, BoosterRole.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def delete_booster_role(session: AsyncSession, guild_id: int, owner_id: int) -> BoosterRole | None:
    row = await get_booster_role(session, guild_id, owner_id)
    if row is None:
        return None
    await session.delete(row)
    await session.commit()
    return row


async def get_all_booster_roles(session: AsyncSession, guild_id: int) -> list[BoosterRole]:
    result = await session.execute(select(BoosterRole).where(BoosterRole.guild_id == guild_id))
    return list(result.scalars().all())


async def count_booster_roles(session: AsyncSession, guild_id: int) -> int:
    return len(await get_all_booster_roles(session, guild_id))


# ---------------------------------------------------------- filter words

async def add_filter_word(session: AsyncSession, guild_id: int, word: str) -> bool:
    result = await session.execute(
        select(BoosterRoleFilterWord).where(BoosterRoleFilterWord.guild_id == guild_id, BoosterRoleFilterWord.word == word)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(BoosterRoleFilterWord(guild_id=guild_id, word=word))
    await session.commit()
    return True


async def remove_filter_word(session: AsyncSession, guild_id: int, word: str) -> bool:
    result = await session.execute(
        select(BoosterRoleFilterWord).where(BoosterRoleFilterWord.guild_id == guild_id, BoosterRoleFilterWord.word == word)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_filter_words(session: AsyncSession, guild_id: int) -> list[str]:
    result = await session.execute(
        select(BoosterRoleFilterWord.word).where(BoosterRoleFilterWord.guild_id == guild_id)
    )
    return [row[0] for row in result.all()]