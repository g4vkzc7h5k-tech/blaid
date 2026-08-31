"""All database access for ticket options and their sub-config."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.ticket_options_models import (
    TicketOption,
    TicketOptionButtonConfig,
    TicketOptionMessage,
    TicketOptionRequiredRole,
    TicketOptionSupportRole,
    TicketOptionTraineeRole,
)


async def create_option(session: AsyncSession, guild_id: int, panel_id: int, name: str, label: str, emoji: str | None) -> TicketOption:
    option = TicketOption(guild_id=guild_id, panel_id=panel_id, name=name, label=label, emoji=emoji)
    session.add(option)
    await session.commit()
    await session.refresh(option)
    return option


async def get_option(session: AsyncSession, option_id: int) -> TicketOption | None:
    result = await session.execute(select(TicketOption).where(TicketOption.id == option_id))
    return result.scalar_one_or_none()


async def get_options_for_panel(session: AsyncSession, panel_id: int) -> list[TicketOption]:
    result = await session.execute(select(TicketOption).where(TicketOption.panel_id == panel_id))
    return list(result.scalars().all())


async def update_option(session: AsyncSession, option: TicketOption, **fields) -> TicketOption:
    for key, value in fields.items():
        setattr(option, key, value)
    await session.commit()
    await session.refresh(option)
    return option


async def delete_option(session: AsyncSession, option_id: int) -> None:
    option = await get_option(session, option_id)
    if option is None:
        return
    for table in (TicketOptionRequiredRole, TicketOptionSupportRole, TicketOptionTraineeRole):
        await session.execute(table.__table__.delete().where(table.option_id == option_id))
    await session.execute(TicketOptionMessage.__table__.delete().where(TicketOptionMessage.option_id == option_id))
    await session.execute(TicketOptionButtonConfig.__table__.delete().where(TicketOptionButtonConfig.option_id == option_id))
    await session.delete(option)
    await session.commit()


# ---------------------------------------------------------- role lists (required/support/trainee)

async def _add_role(session: AsyncSession, model, option_id: int, role_id: int) -> None:
    existing = await session.execute(select(model).where(model.option_id == option_id, model.role_id == role_id))
    if existing.scalar_one_or_none() is not None:
        return
    session.add(model(option_id=option_id, role_id=role_id))
    await session.commit()


async def _remove_role(session: AsyncSession, model, option_id: int, role_id: int) -> bool:
    result = await session.execute(select(model).where(model.option_id == option_id, model.role_id == role_id))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def _get_roles(session: AsyncSession, model, option_id: int) -> list[int]:
    result = await session.execute(select(model.role_id).where(model.option_id == option_id))
    return [row[0] for row in result.all()]


async def add_required_role(session, option_id, role_id):
    return await _add_role(session, TicketOptionRequiredRole, option_id, role_id)


async def remove_required_role(session, option_id, role_id):
    return await _remove_role(session, TicketOptionRequiredRole, option_id, role_id)


async def get_required_roles(session, option_id):
    return await _get_roles(session, TicketOptionRequiredRole, option_id)


async def add_support_role(session, option_id, role_id):
    return await _add_role(session, TicketOptionSupportRole, option_id, role_id)


async def remove_support_role(session, option_id, role_id):
    return await _remove_role(session, TicketOptionSupportRole, option_id, role_id)


async def get_support_roles(session, option_id):
    return await _get_roles(session, TicketOptionSupportRole, option_id)


async def add_trainee_role(session, option_id, role_id):
    return await _add_role(session, TicketOptionTraineeRole, option_id, role_id)


async def remove_trainee_role(session, option_id, role_id):
    return await _remove_role(session, TicketOptionTraineeRole, option_id, role_id)


async def get_trainee_roles(session, option_id):
    return await _get_roles(session, TicketOptionTraineeRole, option_id)


# ---------------------------------------------------------- messages

async def set_message(session: AsyncSession, option_id: int, message_type: str, content: str) -> None:
    result = await session.execute(
        select(TicketOptionMessage).where(TicketOptionMessage.option_id == option_id, TicketOptionMessage.message_type == message_type)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.content = content
        await session.commit()
        return
    session.add(TicketOptionMessage(option_id=option_id, message_type=message_type, content=content))
    await session.commit()


async def get_message(session: AsyncSession, option_id: int, message_type: str) -> str | None:
    result = await session.execute(
        select(TicketOptionMessage).where(TicketOptionMessage.option_id == option_id, TicketOptionMessage.message_type == message_type)
    )
    row = result.scalar_one_or_none()
    return row.content if row else None


# ---------------------------------------------------------- button config

async def set_button_config(session: AsyncSession, option_id: int, action: str, **fields) -> TicketOptionButtonConfig:
    result = await session.execute(
        select(TicketOptionButtonConfig).where(TicketOptionButtonConfig.option_id == option_id, TicketOptionButtonConfig.action == action)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        await session.commit()
        await session.refresh(existing)
        return existing

    fields.setdefault("label", action.title())
    config = TicketOptionButtonConfig(option_id=option_id, action=action, **fields)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_button_config(session: AsyncSession, option_id: int, action: str) -> TicketOptionButtonConfig | None:
    result = await session.execute(
        select(TicketOptionButtonConfig).where(TicketOptionButtonConfig.option_id == option_id, TicketOptionButtonConfig.action == action)
    )
    return result.scalar_one_or_none()