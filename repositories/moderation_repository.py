"""All database access for moderation cases. Never build a Select/Insert
against ModerationCase anywhere outside this file."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.moderation_models import HardbanRecord, JailRecord, ModerationCase, WarnPunishment


async def next_case_number(session: AsyncSession, guild_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(ModerationCase.guild_id == guild_id)
    )
    return (result.scalar_one() or 0) + 1


async def delete_all_cases_for_guild(session: AsyncSession, guild_id: int) -> int:
    """Used once, by a genuinely first-time ,setup, to guarantee the
    setup entry itself becomes case #1 - clears out any stray cases
    logged before the guild had a working modlog (e.g. from testing
    commands while setup kept failing)."""
    result = await session.execute(select(ModerationCase).where(ModerationCase.guild_id == guild_id))
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


async def create_case(
    session: AsyncSession,
    *,
    guild_id: int,
    user_id: int,
    moderator_id: int,
    action_type: str,
    reason: str | None,
    duration_seconds: int | None = None,
) -> ModerationCase:
    case = ModerationCase(
        guild_id=guild_id,
        case_number=await next_case_number(session, guild_id),
        user_id=user_id,
        moderator_id=moderator_id,
        action_type=action_type,
        reason=reason,
        duration_seconds=duration_seconds,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def get_cases_for_user(
    session: AsyncSession, guild_id: int, user_id: int
) -> list[ModerationCase]:
    result = await session.execute(
        select(ModerationCase)
        .where(ModerationCase.guild_id == guild_id, ModerationCase.user_id == user_id)
        .order_by(ModerationCase.created_at.desc())
    )
    return list(result.scalars().all())


async def get_warnings_for_user(
    session: AsyncSession, guild_id: int, user_id: int
) -> list[ModerationCase]:
    result = await session.execute(
        select(ModerationCase)
        .where(
            ModerationCase.guild_id == guild_id,
            ModerationCase.user_id == user_id,
            ModerationCase.action_type == "warn",
            ModerationCase.active == True,  # noqa: E712
        )
        .order_by(ModerationCase.created_at.desc())
    )
    return list(result.scalars().all())


async def get_active_warning_count(session: AsyncSession, guild_id: int, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(
            ModerationCase.guild_id == guild_id,
            ModerationCase.user_id == user_id,
            ModerationCase.action_type == "warn",
            ModerationCase.active == True,  # noqa: E712
        )
    )
    return result.scalar_one() or 0


async def clear_warnings(session: AsyncSession, guild_id: int, user_id: int) -> int:
    """Soft-deletes (active=False) every active warn case for a user.
    Returns how many were cleared."""
    result = await session.execute(
        select(ModerationCase).where(
            ModerationCase.guild_id == guild_id,
            ModerationCase.user_id == user_id,
            ModerationCase.action_type == "warn",
            ModerationCase.active == True,  # noqa: E712
        )
    )
    cases = list(result.scalars().all())
    for case in cases:
        case.active = False
    await session.commit()
    return len(cases)


async def remove_warning(session: AsyncSession, guild_id: int, user_id: int, case_number: int) -> bool:
    """Soft-deletes one specific warn case by its case number."""
    result = await session.execute(
        select(ModerationCase).where(
            ModerationCase.guild_id == guild_id,
            ModerationCase.user_id == user_id,
            ModerationCase.case_number == case_number,
            ModerationCase.action_type == "warn",
        )
    )
    case = result.scalar_one_or_none()
    if case is None or not case.active:
        return False
    case.active = False
    await session.commit()
    return True


# ---------------------------------------------------------- warn punishment tiers

async def add_warn_punishment(session: AsyncSession, guild_id: int, count: int, punishment: str) -> None:
    result = await session.execute(
        select(WarnPunishment).where(WarnPunishment.guild_id == guild_id, WarnPunishment.count == count)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(WarnPunishment(guild_id=guild_id, count=count, punishment=punishment))
    else:
        row.punishment = punishment
    await session.commit()


async def remove_warn_punishment(session: AsyncSession, guild_id: int, count: int) -> bool:
    result = await session.execute(
        select(WarnPunishment).where(WarnPunishment.guild_id == guild_id, WarnPunishment.count == count)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_warn_punishment_for_count(session: AsyncSession, guild_id: int, count: int) -> WarnPunishment | None:
    result = await session.execute(
        select(WarnPunishment).where(WarnPunishment.guild_id == guild_id, WarnPunishment.count == count)
    )
    return result.scalar_one_or_none()


async def get_all_warn_punishments(session: AsyncSession, guild_id: int) -> list[WarnPunishment]:
    result = await session.execute(
        select(WarnPunishment).where(WarnPunishment.guild_id == guild_id).order_by(WarnPunishment.count)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------- jail records

async def create_jail_record(session: AsyncSession, guild_id: int, user_id: int, unjail_at) -> JailRecord:
    result = await session.execute(
        select(JailRecord).where(JailRecord.guild_id == guild_id, JailRecord.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.unjail_at = unjail_at
        await session.commit()
        await session.refresh(existing)
        return existing

    record = JailRecord(guild_id=guild_id, user_id=user_id, unjail_at=unjail_at)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_jail_record(session: AsyncSession, guild_id: int, user_id: int) -> JailRecord | None:
    result = await session.execute(
        select(JailRecord).where(JailRecord.guild_id == guild_id, JailRecord.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_jail_record(session: AsyncSession, guild_id: int, user_id: int) -> None:
    record = await get_jail_record(session, guild_id, user_id)
    if record is not None:
        await session.delete(record)
        await session.commit()


async def get_all_timed_jail_records(session: AsyncSession) -> list[JailRecord]:
    result = await session.execute(select(JailRecord).where(JailRecord.unjail_at.is_not(None)))
    return list(result.scalars().all())


# ---------------------------------------------------------- hardban records

async def mark_hardban(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(HardbanRecord).where(HardbanRecord.guild_id == guild_id, HardbanRecord.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        session.add(HardbanRecord(guild_id=guild_id, user_id=user_id))
        await session.commit()


async def is_hardban(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(HardbanRecord).where(HardbanRecord.guild_id == guild_id, HardbanRecord.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def clear_hardban(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(HardbanRecord).where(HardbanRecord.guild_id == guild_id, HardbanRecord.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()