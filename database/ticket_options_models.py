"""
Ticket option tables: an "option" is one entry on a panel (its own
button/dropdown choice), with its own behavior, form, messages,
automation timers, and button style.

MESSAGE_TYPES / BUTTON_ACTIONS documented here so the cog and service
layer both import the same source of truth.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

MESSAGE_TYPES = [
    "greeting", "greeting_dm", "claim", "move", "close", "close_dm",
    "reopen", "reopen_dm", "auto_close", "auto_delete", "inactivity", "required_roles",
]
BUTTON_ACTIONS = ["claim", "close", "reopen", "delete"]
BUTTON_COLORS = ["blue", "gray", "green", "red"]


class TicketOption(Base):
    __tablename__ = "ticket_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    panel_id: Mapped[int] = mapped_column(Integer, index=True)

    name: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(80), default="Open Ticket")
    emoji: Mapped[str | None] = mapped_column(String(64), nullable=True)
    form_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Categories
    default_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    claim_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    close_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Naming
    channel_name_format: Mapped[str] = mapped_column(String(100), default="{ticket.case}-{ticket.author.name}")
    claim_rename_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    close_rename_template: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Permissions
    creator_can_close: Mapped[bool] = mapped_column(Boolean, default=True)
    close_on_leave: Mapped[bool] = mapped_column(Boolean, default=False)

    # Required roles
    require_all_roles: Mapped[bool] = mapped_column(Boolean, default=False)

    # Support roles
    keep_staff_visible_on_claim: Mapped[bool] = mapped_column(Boolean, default=True)
    staff_can_speak_on_claim: Mapped[bool] = mapped_column(Boolean, default=True)

    # Trainee roles
    trainees_can_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    trainees_can_close: Mapped[bool] = mapped_column(Boolean, default=False)
    trainees_can_speak: Mapped[bool] = mapped_column(Boolean, default=False)

    # Automation (minutes; None = disabled)
    auto_close_timer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_delete_timer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inactivity_timer: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Style
    button_style: Mapped[str] = mapped_column(String(20), default="blue")  # see BUTTON_COLORS
    button_description: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Where the transcript is sent on close/delete (falls back to the
    # panel's transcript_channel_id if unset here, then nowhere).
    transcript_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TicketOptionRequiredRole(Base):
    __tablename__ = "ticket_option_required_roles"
    option_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class TicketOptionSupportRole(Base):
    __tablename__ = "ticket_option_support_roles"
    option_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class TicketOptionTraineeRole(Base):
    __tablename__ = "ticket_option_trainee_roles"
    option_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class TicketOptionMessage(Base):
    """One row per (option, message_type). See MESSAGE_TYPES above."""

    __tablename__ = "ticket_option_messages"

    option_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    content: Mapped[str] = mapped_column(Text)


class TicketOptionButtonConfig(Base):
    """One row per (option, action). See BUTTON_ACTIONS above."""

    __tablename__ = "ticket_option_button_config"

    option_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(20), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    emoji: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="gray")
    requires_reason: Mapped[bool] = mapped_column(Boolean, default=False)