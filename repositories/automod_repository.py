"""All database access for autoresponders."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.automod_models import AutoResponder, AutoResponderRole


async def create_responder(session: AsyncSession, guild_id: int, trigger: str, response: str) -> AutoResponder:
    responder = AutoResponder(guild_id=guild_id, trigger=trigger, response=response)
    session.add(responder)
    await session.commit()
    await session.refresh(responder)
    return responder


async def get_responder(session: AsyncSession, guild_id: int, trigger: str) -> AutoResponder | None:
    result = await session.execute(
        select(AutoResponder).where(
            AutoResponder.guild_id == guild_id, AutoResponder.trigger.ilike(trigger)
        )
    )
    return result.scalar_one_or_none()


async def get_all_responders(session: AsyncSession, guild_id: int) -> list[AutoResponder]:
    result = await session.execute(select(AutoResponder).where(AutoResponder.guild_id == guild_id))
    return list(result.scalars().all())


async def update_response(session: AsyncSession, responder: AutoResponder, response: str) -> AutoResponder:
    responder.response = response
    await session.commit()
    await session.refresh(responder)
    return responder


async def delete_responder(session: AsyncSession, responder: AutoResponder) -> None:
    await session.execute(
        AutoResponderRole.__table__.delete().where(AutoResponderRole.autoresponder_id == responder.id)
    )
    await session.delete(responder)
    await session.commit()


async def delete_all_responders(session: AsyncSession, guild_id: int) -> None:
    responders = await get_all_responders(session, guild_id)
    for responder in responders:
        await session.execute(
            AutoResponderRole.__table__.delete().where(AutoResponderRole.autoresponder_id == responder.id)
        )
        await session.delete(responder)
    await session.commit()


async def add_role_restriction(session: AsyncSession, autoresponder_id: int, role_id: int) -> None:
    existing = await session.execute(
        select(AutoResponderRole).where(
            AutoResponderRole.autoresponder_id == autoresponder_id, AutoResponderRole.role_id == role_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(AutoResponderRole(autoresponder_id=autoresponder_id, role_id=role_id))
    await session.commit()


async def remove_role_restriction(session: AsyncSession, autoresponder_id: int, role_id: int) -> bool:
    result = await session.execute(
        select(AutoResponderRole).where(
            AutoResponderRole.autoresponder_id == autoresponder_id, AutoResponderRole.role_id == role_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_role_restrictions(session: AsyncSession, autoresponder_id: int) -> list[int]:
    result = await session.execute(
        select(AutoResponderRole.role_id).where(AutoResponderRole.autoresponder_id == autoresponder_id)
    )
    return [row[0] for row in result.all()]


async def clear_role_restrictions(session: AsyncSession, autoresponder_id: int) -> None:
    await session.execute(
        AutoResponderRole.__table__.delete().where(AutoResponderRole.autoresponder_id == autoresponder_id)
    )
    await session.commit()