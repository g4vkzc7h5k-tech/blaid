"""All database access for ticket forms and fields."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.ticket_forms_models import TicketForm, TicketFormField, TicketFormResponse


async def create_form(session: AsyncSession, guild_id: int, name: str, modal_title: str, enable_filtering: bool) -> TicketForm:
    form = TicketForm(guild_id=guild_id, name=name, modal_title=modal_title, enable_filtering=enable_filtering)
    session.add(form)
    await session.commit()
    await session.refresh(form)
    return form


async def get_form(session: AsyncSession, form_id: int) -> TicketForm | None:
    result = await session.execute(select(TicketForm).where(TicketForm.id == form_id))
    return result.scalar_one_or_none()


async def get_forms_for_guild(session: AsyncSession, guild_id: int) -> list[TicketForm]:
    result = await session.execute(select(TicketForm).where(TicketForm.guild_id == guild_id))
    return list(result.scalars().all())


async def update_form(session: AsyncSession, form: TicketForm, **fields) -> TicketForm:
    for key, value in fields.items():
        setattr(form, key, value)
    await session.commit()
    await session.refresh(form)
    return form


async def delete_form(session: AsyncSession, form_id: int) -> None:
    form = await get_form(session, form_id)
    if form is None:
        return
    await session.execute(TicketFormField.__table__.delete().where(TicketFormField.form_id == form_id))
    await session.delete(form)
    await session.commit()


async def add_field(session: AsyncSession, form_id: int, **kwargs) -> TicketFormField:
    existing = await get_fields(session, form_id)
    field = TicketFormField(form_id=form_id, position=len(existing), **kwargs)
    session.add(field)
    await session.commit()
    await session.refresh(field)
    return field


async def get_field(session: AsyncSession, field_id: int) -> TicketFormField | None:
    result = await session.execute(select(TicketFormField).where(TicketFormField.id == field_id))
    return result.scalar_one_or_none()


async def get_fields(session: AsyncSession, form_id: int) -> list[TicketFormField]:
    result = await session.execute(
        select(TicketFormField).where(TicketFormField.form_id == form_id).order_by(TicketFormField.position)
    )
    return list(result.scalars().all())


async def remove_field(session: AsyncSession, field_id: int) -> bool:
    field = await get_field(session, field_id)
    if field is None:
        return False
    await session.delete(field)
    await session.commit()
    return True


async def save_response(session: AsyncSession, ticket_id: int, field_id: int, value: str) -> None:
    session.add(TicketFormResponse(ticket_id=ticket_id, field_id=field_id, value=value))
    await session.commit()


async def get_responses(session: AsyncSession, ticket_id: int) -> list[TicketFormResponse]:
    result = await session.execute(select(TicketFormResponse).where(TicketFormResponse.ticket_id == ticket_id))
    return list(result.scalars().all())