"""All database access for autorole, reaction roles, and button roles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.roles_models import Autorole, ButtonRole, ReactionRole, StickyRole


async def get_autoroles(session: AsyncSession, guild_id: int) -> list[Autorole]:
    result = await session.execute(select(Autorole).where(Autorole.guild_id == guild_id))
    return list(result.scalars().all())


async def add_autorole(session: AsyncSession, guild_id: int, role_id: int) -> None:
    existing = await session.execute(
        select(Autorole).where(Autorole.guild_id == guild_id, Autorole.role_id == role_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(Autorole(guild_id=guild_id, role_id=role_id))
    await session.commit()


async def remove_autorole(session: AsyncSession, guild_id: int, role_id: int) -> bool:
    result = await session.execute(
        select(Autorole).where(Autorole.guild_id == guild_id, Autorole.role_id == role_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def add_reaction_role(session: AsyncSession, guild_id: int, message_id: int, emoji: str, role_id: int) -> None:
    session.add(ReactionRole(guild_id=guild_id, message_id=message_id, emoji=emoji, role_id=role_id))
    await session.commit()


async def get_reaction_role(session: AsyncSession, message_id: int, emoji: str) -> ReactionRole | None:
    result = await session.execute(
        select(ReactionRole).where(ReactionRole.message_id == message_id, ReactionRole.emoji == emoji)
    )
    return result.scalar_one_or_none()


async def remove_reaction_role(session: AsyncSession, guild_id: int, message_id: int, emoji: str) -> bool:
    result = await session.execute(
        select(ReactionRole).where(
            ReactionRole.guild_id == guild_id, ReactionRole.message_id == message_id, ReactionRole.emoji == emoji
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_reaction_roles_for_guild(session: AsyncSession, guild_id: int) -> list[ReactionRole]:
    result = await session.execute(select(ReactionRole).where(ReactionRole.guild_id == guild_id))
    return list(result.scalars().all())


async def clear_reaction_roles(session: AsyncSession, guild_id: int) -> int:
    rows = await get_reaction_roles_for_guild(session, guild_id)
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


async def add_button_role(
    session: AsyncSession, guild_id: int, message_id: int, custom_id: str, role_id: int, label: str,
    style: str = "secondary", emoji: str | None = None,
) -> None:
    session.add(ButtonRole(
        guild_id=guild_id, message_id=message_id, custom_id=custom_id, role_id=role_id,
        label=label, style=style, emoji=emoji,
    ))
    await session.commit()


async def get_button_roles_for_message(session: AsyncSession, message_id: int) -> list[ButtonRole]:
    result = await session.execute(select(ButtonRole).where(ButtonRole.message_id == message_id))
    return list(result.scalars().all())


async def get_all_button_role_messages(session: AsyncSession) -> list[int]:
    """Distinct message IDs that have button roles - used to re-register
    persistent views after a restart."""
    result = await session.execute(select(ButtonRole.message_id).distinct())
    return [row[0] for row in result.all()]


async def get_button_role(session: AsyncSession, message_id: int, custom_id: str) -> ButtonRole | None:
    result = await session.execute(
        select(ButtonRole).where(ButtonRole.message_id == message_id, ButtonRole.custom_id == custom_id)
    )
    return result.scalar_one_or_none()


async def remove_button_role_row(session: AsyncSession, row: ButtonRole) -> None:
    await session.delete(row)
    await session.commit()


async def remove_button_roles_for_message(session: AsyncSession, message_id: int) -> int:
    rows = await get_button_roles_for_message(session, message_id)
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


async def get_all_button_roles_for_guild(session: AsyncSession, guild_id: int) -> list[ButtonRole]:
    result = await session.execute(select(ButtonRole).where(ButtonRole.guild_id == guild_id))
    return list(result.scalars().all())


async def clear_button_roles_for_guild(session: AsyncSession, guild_id: int) -> int:
    rows = await get_all_button_roles_for_guild(session, guild_id)
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


# ---------------------------------------------------------- sticky roles

async def save_sticky_roles(session: AsyncSession, guild_id: int, user_id: int, role_ids: list[int]) -> None:
    result = await session.execute(
        select(StickyRole).where(StickyRole.guild_id == guild_id, StickyRole.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    joined = ",".join(str(r) for r in role_ids)
    if row is None:
        session.add(StickyRole(guild_id=guild_id, user_id=user_id, role_ids=joined))
    else:
        row.role_ids = joined
    await session.commit()


async def get_sticky_roles(session: AsyncSession, guild_id: int, user_id: int) -> list[int]:
    result = await session.execute(
        select(StickyRole).where(StickyRole.guild_id == guild_id, StickyRole.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.role_ids:
        return []
    return [int(r) for r in row.role_ids.split(",") if r]