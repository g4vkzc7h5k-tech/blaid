"""Database access for Last.fm account linking."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.lastfm_models import LastfmAccount, LastfmFriend, LastfmSettings


async def get_account(session: AsyncSession, user_id: int) -> LastfmAccount | None:
    result = await session.execute(select(LastfmAccount).where(LastfmAccount.user_id == user_id))
    return result.scalar_one_or_none()


async def set_account(session: AsyncSession, user_id: int, username: str) -> LastfmAccount:
    existing = await get_account(session, user_id)
    if existing is not None:
        existing.username = username
        await session.commit()
        await session.refresh(existing)
        return existing

    row = LastfmAccount(user_id=user_id, username=username)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def unlink_account(session: AsyncSession, user_id: int) -> bool:
    existing = await get_account(session, user_id)
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True


# ---------------------------------------------------------- settings (mode/embed/color/react)

async def get_or_create_settings(session: AsyncSession, user_id: int) -> LastfmSettings:
    result = await session.execute(select(LastfmSettings).where(LastfmSettings.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = LastfmSettings(user_id=user_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def get_settings(session: AsyncSession, user_id: int) -> LastfmSettings | None:
    result = await session.execute(select(LastfmSettings).where(LastfmSettings.user_id == user_id))
    return result.scalar_one_or_none()


async def update_settings(session: AsyncSession, row: LastfmSettings, **fields) -> LastfmSettings:
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


# ---------------------------------------------------------- friends

async def add_friend(session: AsyncSession, user_id: int, friend_id: int) -> bool:
    result = await session.execute(
        select(LastfmFriend).where(LastfmFriend.user_id == user_id, LastfmFriend.friend_id == friend_id)
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(LastfmFriend(user_id=user_id, friend_id=friend_id))
    await session.commit()
    return True


async def remove_friend(session: AsyncSession, user_id: int, friend_id: int) -> bool:
    result = await session.execute(
        select(LastfmFriend).where(LastfmFriend.user_id == user_id, LastfmFriend.friend_id == friend_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_friends(session: AsyncSession, user_id: int) -> list[int]:
    result = await session.execute(select(LastfmFriend.friend_id).where(LastfmFriend.user_id == user_id))
    return [row[0] for row in result.all()]