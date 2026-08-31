"""Database access for ,bug reports."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.bug_models import BugReport


async def create_report(session: AsyncSession, guild_id: int | None, user_id: int, description: str) -> BugReport:
    report = BugReport(guild_id=guild_id, user_id=user_id, description=description)
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report