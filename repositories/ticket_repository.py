"""All database access for tickets and ticket panels."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.tickets_models import Ticket, TicketBlacklist, TicketPanel


async def create_panel(session: AsyncSession, **kwargs) -> TicketPanel:
    panel = TicketPanel(**kwargs)
    session.add(panel)
    await session.commit()
    await session.refresh(panel)
    return panel


async def get_panel(session: AsyncSession, panel_id: int) -> TicketPanel | None:
    result = await session.execute(select(TicketPanel).where(TicketPanel.id == panel_id))
    return result.scalar_one_or_none()


async def get_panels_for_guild(session: AsyncSession, guild_id: int) -> list[TicketPanel]:
    result = await session.execute(select(TicketPanel).where(TicketPanel.guild_id == guild_id))
    return list(result.scalars().all())


async def update_panel(session: AsyncSession, panel: TicketPanel, **fields) -> TicketPanel:
    for key, value in fields.items():
        setattr(panel, key, value)
    await session.commit()
    await session.refresh(panel)
    return panel


async def delete_panel(session: AsyncSession, panel: TicketPanel) -> None:
    await session.delete(panel)
    await session.commit()


async def next_case_number(session: AsyncSession, guild_id: int) -> int:
    result = await session.execute(select(func.count()).where(Ticket.guild_id == guild_id))
    return (result.scalar_one() or 0) + 1


async def create_ticket(session: AsyncSession, **kwargs) -> Ticket:
    kwargs.setdefault("case_number", await next_case_number(session, kwargs["guild_id"]))
    ticket = Ticket(**kwargs)
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_ticket_by_channel(session: AsyncSession, channel_id: int) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.channel_id == channel_id))
    return result.scalar_one_or_none()


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()


async def get_open_tickets_for_creator(session: AsyncSession, guild_id: int, creator_id: int) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(
            Ticket.guild_id == guild_id, Ticket.creator_id == creator_id, Ticket.status != "closed"
        )
    )
    return list(result.scalars().all())


async def get_tickets_with_pending_auto_close(session: AsyncSession) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(Ticket.auto_close_at.is_not(None), Ticket.status != "closed")
    )
    return list(result.scalars().all())


async def get_tickets_with_pending_auto_delete(session: AsyncSession) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(Ticket.auto_delete_at.is_not(None), Ticket.status == "closed")
    )
    return list(result.scalars().all())


async def get_open_tickets_with_control_message(session: AsyncSession) -> list[Ticket]:
    """Every non-closed ticket that has a control panel message to
    re-register as a persistent view on startup."""
    result = await session.execute(
        select(Ticket).where(Ticket.control_message_id.is_not(None), Ticket.status != "closed")
    )
    return list(result.scalars().all())


async def get_open_tickets(session: AsyncSession, guild_id: int) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(Ticket.guild_id == guild_id, Ticket.status != "closed")
    )
    return list(result.scalars().all())


async def get_all_tickets(session: AsyncSession, guild_id: int) -> list[Ticket]:
    result = await session.execute(select(Ticket).where(Ticket.guild_id == guild_id))
    return list(result.scalars().all())


async def count_tickets(session: AsyncSession, guild_id: int) -> dict[str, int]:
    all_tickets = await get_all_tickets(session, guild_id)
    return {
        "total": len(all_tickets),
        "open": len([t for t in all_tickets if t.status != "closed"]),
        "closed": len([t for t in all_tickets if t.status == "closed"]),
        "claimed": len([t for t in all_tickets if t.status == "claimed"]),
    }


async def update_ticket(session: AsyncSession, ticket: Ticket, **fields) -> Ticket:
    for key, value in fields.items():
        setattr(ticket, key, value)
    await session.commit()
    await session.refresh(ticket)
    return ticket


# ---------------------------------------------------------- blacklist

async def add_blacklist(session: AsyncSession, guild_id: int, user_id: int) -> None:
    existing = await session.execute(
        select(TicketBlacklist).where(TicketBlacklist.guild_id == guild_id, TicketBlacklist.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(TicketBlacklist(guild_id=guild_id, user_id=user_id))
    await session.commit()


async def remove_blacklist(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(TicketBlacklist).where(TicketBlacklist.guild_id == guild_id, TicketBlacklist.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_blacklisted(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(TicketBlacklist).where(TicketBlacklist.guild_id == guild_id, TicketBlacklist.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None