"""All database access for per-guild command aliases."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.alias_models import CommandAlias


async def add_alias(session: AsyncSession, guild_id: int, alias_name: str, command_template: str) -> CommandAlias:
    result = await session.execute(
        select(CommandAlias).where(CommandAlias.guild_id == guild_id, CommandAlias.alias_name == alias_name)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.command_template = command_template
        await session.commit()
        await session.refresh(existing)
        return existing

    alias = CommandAlias(guild_id=guild_id, alias_name=alias_name, command_template=command_template)
    session.add(alias)
    await session.commit()
    await session.refresh(alias)
    return alias


async def remove_alias(session: AsyncSession, guild_id: int, alias_name: str) -> bool:
    result = await session.execute(
        select(CommandAlias).where(CommandAlias.guild_id == guild_id, CommandAlias.alias_name == alias_name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_aliases(session: AsyncSession, guild_id: int) -> list[CommandAlias]:
    result = await session.execute(select(CommandAlias).where(CommandAlias.guild_id == guild_id))
    return list(result.scalars().all())


async def get_alias(session: AsyncSession, guild_id: int, alias_name: str) -> CommandAlias | None:
    result = await session.execute(
        select(CommandAlias).where(CommandAlias.guild_id == guild_id, CommandAlias.alias_name == alias_name)
    )
    return result.scalar_one_or_none()
