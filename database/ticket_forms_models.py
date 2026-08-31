"""Ticket form + field builder tables, and per-ticket stored answers."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

FIELD_TYPES = ["short_text", "long_text", "checkbox", "select", "role_select", "user_select", "channel_select"]


class TicketForm(Base):
    __tablename__ = "ticket_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    modal_title: Mapped[str] = mapped_column(String(45), default="Ticket Form")
    enable_filtering: Mapped[bool] = mapped_column(Boolean, default=False)


class TicketFormField(Base):
    __tablename__ = "ticket_form_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    form_id: Mapped[int] = mapped_column(Integer, index=True)

    field_type: Mapped[str] = mapped_column(String(20))  # see FIELD_TYPES
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    key: Mapped[str] = mapped_column(String(50))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class TicketFormResponse(Base):
    """One row per answered field, per ticket."""

    __tablename__ = "ticket_form_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, index=True)
    field_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(Text)