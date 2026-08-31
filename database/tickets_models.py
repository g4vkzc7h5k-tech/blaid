"""Ticket system tables: panels and open/closed tickets."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

DEFAULT_LOG_MESSAGE = (
    "**Ticket Closed**\n\n"
    "**ID** {ticket.case}\n"
    "**Opened By** {ticket.creator.mention}\n"
    "**Closed By** {ticket.closed_by.mention}\n"
    "**Deleted By** {ticket.deleted_by.mention}\n"
    "**Open Time** {ticket.open_time}\n"
    "**Claimed By** {ticket.claimed_by.mention}\n"
    "**Users** {ticket.users}"
)


class TicketPanel(Base):
    __tablename__ = "ticket_panels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)

    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    title: Mapped[str] = mapped_column(String(128), default="Support")
    description: Mapped[str] = mapped_column(Text, default="Click below to open a ticket.")
    button_label: Mapped[str] = mapped_column(String(64), default="Open Ticket")

    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    support_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transcript_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ---- ,tickets panel management menu (Behaviour / Category / Display)
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closed_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delete_delay_seconds: Mapped[int] = mapped_column(Integer, default=0)
    max_open_tickets: Mapped[int] = mapped_column(Integer, default=1)
    auto_pin_controls: Mapped[bool] = mapped_column(Boolean, default=False)
    claims_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_name_format: Mapped[str] = mapped_column(String(32), default="case_number")
    case_padding: Mapped[int] = mapped_column(Integer, default=0)
    dropdown_placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="dropdown")

    # ---- ,tickets logs
    logs_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    log_message_template: Mapped[str] = mapped_column(Text, default=DEFAULT_LOG_MESSAGE)

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_number: Mapped[int] = mapped_column(Integer, default=1)  # per-guild sequential number
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    panel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    creator_id: Mapped[int] = mapped_column(BigInteger)
    claimed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="open")  # open, claimed, closed
    transcript_path: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # The per-ticket control panel message (Claim/Close/Reopen/Delete
    # buttons styled from the option's Button UX config) - stored so it
    # can be re-registered as a persistent view on restart.
    control_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Absolute deadlines computed from the option's Automation timers at
    # creation/close time, so a restart can resume them exactly.
    auto_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_delete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketBlacklist(Base):
    """Users blocked from opening new tickets."""

    __tablename__ = "ticket_blacklist"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)