"""Database access for ,backup."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.backup_models import ServerBackup


async def create_backup(
    session: AsyncSession, guild_id: int, name: str, description: str | None, data: str, created_by: int,
) -> ServerBackup:
    row = ServerBackup(guild_id=guild_id, name=name, description=description, data=data, created_by=created_by)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_backup(session: AsyncSession, backup_id: int) -> ServerBackup | None:
    result = await session.execute(select(ServerBackup).where(ServerBackup.id == backup_id))
    return result.scalar_one_or_none()


async def get_backups_for_guild(session: AsyncSession, guild_id: int) -> list[ServerBackup]:
    result = await session.execute(
        select(ServerBackup).where(ServerBackup.guild_id == guild_id).order_by(ServerBackup.created_at.desc())
    )
    return list(result.scalars().all())


async def update_backup(session: AsyncSession, row: ServerBackup, **fields) -> ServerBackup:
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_backup(session: AsyncSession, backup_id: int, guild_id: int) -> bool:
    result = await session.execute(
        select(ServerBackup).where(ServerBackup.id == backup_id, ServerBackup.guild_id == guild_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True