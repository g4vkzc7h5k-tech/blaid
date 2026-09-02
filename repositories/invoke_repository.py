"""Database access for ,invoke."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.invoke_models import InvokeMessage


async def set_message(session: AsyncSession, guild_id: int, command: str, message_type: str, content: str) -> None:
    result = await session.execute(
        select(InvokeMessage).where(
            InvokeMessage.guild_id == guild_id,
            InvokeMessage.command == command,
            InvokeMessage.message_type == message_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.content = content
    else:
        session.add(InvokeMessage(guild_id=guild_id, command=command, message_type=message_type, content=content))
    await session.commit()


async def get_message(session: AsyncSession, guild_id: int, command: str, message_type: str) -> str | None:
    result = await session.execute(
        select(InvokeMessage).where(
            InvokeMessage.guild_id == guild_id,
            InvokeMessage.command == command,
            InvokeMessage.message_type == message_type,
        )
    )
    row = result.scalar_one_or_none()
    return row.content if row is not None else None


async def delete_message(session: AsyncSession, guild_id: int, command: str, message_type: str | None) -> int:
    """message_type=None deletes both dm and text for that command.
    Returns how many rows were removed."""
    query = select(InvokeMessage).where(InvokeMessage.guild_id == guild_id, InvokeMessage.command == command)
    if message_type is not None:
        query = query.where(InvokeMessage.message_type == message_type)
    result = await session.execute(query)
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    if rows:
        await session.commit()
    return len(rows)


async def get_all_for_guild(session: AsyncSession, guild_id: int) -> list[InvokeMessage]:
    result = await session.execute(select(InvokeMessage).where(InvokeMessage.guild_id == guild_id))
    return list(result.scalars().all())


async def reset_guild(session: AsyncSession, guild_id: int) -> int:
    rows = await get_all_for_guild(session, guild_id)
    for row in rows:
        await session.delete(row)
    if rows:
        await session.commit()
    return len(rows)
