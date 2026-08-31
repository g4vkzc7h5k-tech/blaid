"""All database access for giveaways."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.giveaway_models import Giveaway, GiveawayEntry
from database.giveaway_settings_models import (
    GiveawayBlacklist,
    GiveawayRoleMax,
    GiveawayTemplate,
    GiveawayUserSettings,
)


async def create_giveaway(session: AsyncSession, **kwargs) -> Giveaway:
    giveaway = Giveaway(**kwargs)
    session.add(giveaway)
    await session.commit()
    await session.refresh(giveaway)
    return giveaway


async def get_giveaway(session: AsyncSession, giveaway_id: int) -> Giveaway | None:
    result = await session.execute(select(Giveaway).where(Giveaway.id == giveaway_id))
    return result.scalar_one_or_none()


async def get_active_giveaways(session: AsyncSession) -> list[Giveaway]:
    result = await session.execute(select(Giveaway).where(Giveaway.ended == False))  # noqa: E712
    return list(result.scalars().all())


async def set_message_id(session: AsyncSession, giveaway: Giveaway, message_id: int) -> None:
    giveaway.message_id = message_id
    await session.commit()


async def mark_ended(session: AsyncSession, giveaway: Giveaway) -> None:
    giveaway.ended = True
    await session.commit()


async def update_giveaway(session: AsyncSession, giveaway: Giveaway, **fields) -> Giveaway:
    for key, value in fields.items():
        setattr(giveaway, key, value)
    await session.commit()
    await session.refresh(giveaway)
    return giveaway


async def add_entry(session: AsyncSession, giveaway_id: int, user_id: int) -> bool:
    existing = await session.execute(
        select(GiveawayEntry).where(GiveawayEntry.giveaway_id == giveaway_id, GiveawayEntry.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        return False
    session.add(GiveawayEntry(giveaway_id=giveaway_id, user_id=user_id))
    await session.commit()
    return True


async def get_entries(session: AsyncSession, giveaway_id: int) -> list[int]:
    result = await session.execute(select(GiveawayEntry.user_id).where(GiveawayEntry.giveaway_id == giveaway_id))
    return [row[0] for row in result.all()]


async def count_entries(session: AsyncSession, giveaway_id: int) -> int:
    result = await session.execute(select(GiveawayEntry.user_id).where(GiveawayEntry.giveaway_id == giveaway_id))
    return len(result.all())


# ---------------------------------------------------------- user settings

async def get_or_create_user_settings(session: AsyncSession, user_id: int) -> GiveawayUserSettings:
    result = await session.execute(select(GiveawayUserSettings).where(GiveawayUserSettings.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = GiveawayUserSettings(user_id=user_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


# ---------------------------------------------------------- template

async def get_or_create_template(session: AsyncSession, guild_id: int) -> GiveawayTemplate:
    result = await session.execute(select(GiveawayTemplate).where(GiveawayTemplate.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = GiveawayTemplate(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def get_template(session: AsyncSession, guild_id: int) -> GiveawayTemplate | None:
    result = await session.execute(select(GiveawayTemplate).where(GiveawayTemplate.guild_id == guild_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------- blacklist

async def get_blacklisted_roles(session: AsyncSession, guild_id: int) -> list[int]:
    result = await session.execute(select(GiveawayBlacklist.role_id).where(GiveawayBlacklist.guild_id == guild_id))
    return [row[0] for row in result.all()]


async def toggle_blacklist(session: AsyncSession, guild_id: int, role_id: int) -> bool:
    """Returns True if the role is now blacklisted, False if it was removed."""
    result = await session.execute(
        select(GiveawayBlacklist).where(GiveawayBlacklist.guild_id == guild_id, GiveawayBlacklist.role_id == role_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.commit()
        return False

    session.add(GiveawayBlacklist(guild_id=guild_id, role_id=role_id))
    await session.commit()
    return True


# ---------------------------------------------------------- role max entries

async def get_role_max_entries(session: AsyncSession, guild_id: int) -> dict[int, int]:
    result = await session.execute(select(GiveawayRoleMax).where(GiveawayRoleMax.guild_id == guild_id))
    return {row.role_id: row.max_entries for row in result.scalars().all()}


async def set_role_max_entries(session: AsyncSession, guild_id: int, role_id: int, max_entries: int) -> None:
    result = await session.execute(
        select(GiveawayRoleMax).where(GiveawayRoleMax.guild_id == guild_id, GiveawayRoleMax.role_id == role_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.max_entries = max_entries
        await session.commit()
        return

    session.add(GiveawayRoleMax(guild_id=guild_id, role_id=role_id, max_entries=max_entries))
    await session.commit()