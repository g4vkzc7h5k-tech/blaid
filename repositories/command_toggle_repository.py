"""Database access for ,enable / ,disable."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.command_toggle_models import DisabledCommand


async def disable_command(session: AsyncSession, guild_id: int, command_name: str, target_id: int = 0) -> bool:
    result = await session.execute(
        select(DisabledCommand).where(
            DisabledCommand.guild_id == guild_id,
            DisabledCommand.command_name == command_name,
            DisabledCommand.target_id == target_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(DisabledCommand(guild_id=guild_id, command_name=command_name, target_id=target_id))
    await session.commit()
    return True


async def enable_command(session: AsyncSession, guild_id: int, command_name: str, target_id: int = 0) -> bool:
    result = await session.execute(
        select(DisabledCommand).where(
            DisabledCommand.guild_id == guild_id,
            DisabledCommand.command_name == command_name,
            DisabledCommand.target_id == target_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_all_for_guild(session: AsyncSession, guild_id: int) -> list[DisabledCommand]:
    result = await session.execute(select(DisabledCommand).where(DisabledCommand.guild_id == guild_id))
    return list(result.scalars().all())


async def is_disabled(session: AsyncSession, guild_id: int, command_name: str, target_ids: list[int]) -> bool:
    """target_ids should include 0 (server-wide) plus the channel ID
    and every role ID the invoker has."""
    result = await session.execute(
        select(DisabledCommand).where(
            DisabledCommand.guild_id == guild_id,
            DisabledCommand.command_name == command_name,
            DisabledCommand.target_id.in_(target_ids),
        )
    )
    return result.scalar_one_or_none() is not None