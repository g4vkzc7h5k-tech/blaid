"""
Shared SQLAlchemy declarative base.

Every model in the project (moderation, levels, tickets, logging,
automod, voicemaster, giveaways, welcome/goodbye/boost, roles, etc.)
MUST import Base from this exact module. Never create a second
declarative_base() anywhere else in the project - doing so would
split metadata and break create_all()/migrations.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all Blade database models."""
    pass
