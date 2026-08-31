"""All database access for the chat filter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.filter_models import (
    FilterConfig,
    FilterExemptChannel,
    FilterModule,
    FilterStrike,
    FilterWhitelist,
    FilterWord,
)


# ---------------------------------------------------------- config

async def get_or_create_config(session: AsyncSession, guild_id: int) -> FilterConfig:
    result = await session.execute(select(FilterConfig).where(FilterConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = FilterConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


# ---------------------------------------------------------- modules

async def get_or_create_module(session: AsyncSession, guild_id: int, module_name: str) -> FilterModule:
    result = await session.execute(
        select(FilterModule).where(FilterModule.guild_id == guild_id, FilterModule.module_name == module_name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = FilterModule(guild_id=guild_id, module_name=module_name)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def update_module(session: AsyncSession, module: FilterModule, **fields) -> FilterModule:
    for key, value in fields.items():
        setattr(module, key, value)
    await session.commit()
    await session.refresh(module)
    return module


async def get_all_modules(session: AsyncSession, guild_id: int) -> dict[str, FilterModule]:
    result = await session.execute(select(FilterModule).where(FilterModule.guild_id == guild_id))
    return {row.module_name: row for row in result.scalars().all()}


# ---------------------------------------------------------- words / phrases / regex

async def add_word(session: AsyncSession, guild_id: int, value: str, kind: str, is_preset: bool = False) -> bool:
    existing = await session.execute(
        select(FilterWord).where(
            FilterWord.guild_id == guild_id, FilterWord.value == value, FilterWord.kind == kind
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    session.add(FilterWord(guild_id=guild_id, value=value, kind=kind, is_preset=is_preset))
    await session.commit()
    return True


async def remove_word(session: AsyncSession, guild_id: int, value: str, kind: str) -> bool:
    result = await session.execute(
        select(FilterWord).where(
            FilterWord.guild_id == guild_id, FilterWord.value == value, FilterWord.kind == kind
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_words(session: AsyncSession, guild_id: int, kind: str | None = None) -> list[FilterWord]:
    query = select(FilterWord).where(FilterWord.guild_id == guild_id)
    if kind is not None:
        query = query.where(FilterWord.kind == kind)
    result = await session.execute(query)
    return list(result.scalars().all())


async def clear_words(session: AsyncSession, guild_id: int, kind: str | None = None) -> int:
    words = await get_words(session, guild_id, kind)
    for word in words:
        await session.delete(word)
    await session.commit()
    return len(words)


async def remove_preset_words(session: AsyncSession, guild_id: int) -> int:
    result = await session.execute(
        select(FilterWord).where(FilterWord.guild_id == guild_id, FilterWord.is_preset.is_(True))
    )
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


# ---------------------------------------------------------- whitelist / exempt channels

async def add_whitelist(session: AsyncSession, guild_id: int, target_id: int, target_type: str) -> bool:
    existing = await session.execute(
        select(FilterWhitelist).where(FilterWhitelist.guild_id == guild_id, FilterWhitelist.target_id == target_id)
    )
    if existing.scalar_one_or_none() is not None:
        return False
    session.add(FilterWhitelist(guild_id=guild_id, target_id=target_id, target_type=target_type))
    await session.commit()
    return True


async def remove_whitelist(session: AsyncSession, guild_id: int, target_id: int) -> bool:
    result = await session.execute(
        select(FilterWhitelist).where(FilterWhitelist.guild_id == guild_id, FilterWhitelist.target_id == target_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_whitelisted(session: AsyncSession, guild_id: int, target_ids: list[int]) -> bool:
    if not target_ids:
        return False
    result = await session.execute(
        select(FilterWhitelist).where(
            FilterWhitelist.guild_id == guild_id, FilterWhitelist.target_id.in_(target_ids)
        )
    )
    return result.first() is not None


async def add_exempt_channel(session: AsyncSession, guild_id: int, channel_id: int) -> bool:
    existing = await session.execute(
        select(FilterExemptChannel).where(
            FilterExemptChannel.guild_id == guild_id, FilterExemptChannel.channel_id == channel_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    session.add(FilterExemptChannel(guild_id=guild_id, channel_id=channel_id))
    await session.commit()
    return True


async def remove_exempt_channel(session: AsyncSession, guild_id: int, channel_id: int) -> bool:
    result = await session.execute(
        select(FilterExemptChannel).where(
            FilterExemptChannel.guild_id == guild_id, FilterExemptChannel.channel_id == channel_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_exempt_channel(session: AsyncSession, guild_id: int, channel_id: int) -> bool:
    result = await session.execute(
        select(FilterExemptChannel).where(
            FilterExemptChannel.guild_id == guild_id, FilterExemptChannel.channel_id == channel_id
        )
    )
    return result.scalar_one_or_none() is not None


# ---------------------------------------------------------- strikes

async def get_strikes(session: AsyncSession, guild_id: int, user_id: int) -> int:
    result = await session.execute(
        select(FilterStrike).where(FilterStrike.guild_id == guild_id, FilterStrike.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return row.count if row else 0


async def add_strike(session: AsyncSession, guild_id: int, user_id: int) -> int:
    result = await session.execute(
        select(FilterStrike).where(FilterStrike.guild_id == guild_id, FilterStrike.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = FilterStrike(guild_id=guild_id, user_id=user_id, count=1)
        session.add(row)
    else:
        row.count += 1
    await session.commit()
    await session.refresh(row)
    return row.count


async def reset_strikes(session: AsyncSession, guild_id: int, user_id: int) -> None:
    result = await session.execute(
        select(FilterStrike).where(FilterStrike.guild_id == guild_id, FilterStrike.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()