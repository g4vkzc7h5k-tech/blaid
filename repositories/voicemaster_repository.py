"""All database access for VoiceMaster."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.voicemaster_models import (
    TempVoiceChannel,
    VoiceMasterConfig,
    VoiceMasterExtraHub,
    VoiceMasterPermit,
    VoiceMasterReject,
)


async def get_extra_hubs(session: AsyncSession, guild_id: int) -> list[int]:
    result = await session.execute(select(VoiceMasterExtraHub.channel_id).where(VoiceMasterExtraHub.guild_id == guild_id))
    return [row[0] for row in result.all()]


async def add_extra_hub(session: AsyncSession, guild_id: int, channel_id: int) -> None:
    session.add(VoiceMasterExtraHub(guild_id=guild_id, channel_id=channel_id))
    await session.commit()


async def remove_extra_hub(session: AsyncSession, guild_id: int, channel_id: int) -> bool:
    result = await session.execute(
        select(VoiceMasterExtraHub).where(
            VoiceMasterExtraHub.guild_id == guild_id, VoiceMasterExtraHub.channel_id == channel_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


# ---------------------------------------------------------- config

async def get_config(session: AsyncSession, guild_id: int) -> VoiceMasterConfig | None:
    result = await session.execute(select(VoiceMasterConfig).where(VoiceMasterConfig.guild_id == guild_id))
    return result.scalar_one_or_none()


async def get_or_create_config(session: AsyncSession, guild_id: int) -> VoiceMasterConfig:
    cfg = await get_config(session, guild_id)
    if cfg is None:
        cfg = VoiceMasterConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def reset_config(session: AsyncSession, guild_id: int) -> None:
    cfg = await get_config(session, guild_id)
    if cfg is not None:
        await session.delete(cfg)
        await session.commit()


# ---------------------------------------------------------- temp channels

async def create_temp_channel(
    session: AsyncSession, channel_id: int, guild_id: int, owner_id: int, *, user_limit: int = 0, bitrate: int = 64000
) -> TempVoiceChannel:
    temp = TempVoiceChannel(
        channel_id=channel_id, guild_id=guild_id, owner_id=owner_id, user_limit=user_limit, bitrate=bitrate
    )
    session.add(temp)
    await session.commit()
    await session.refresh(temp)
    return temp


async def get_temp_channel(session: AsyncSession, channel_id: int) -> TempVoiceChannel | None:
    result = await session.execute(select(TempVoiceChannel).where(TempVoiceChannel.channel_id == channel_id))
    return result.scalar_one_or_none()


async def get_temp_channel_for_owner(session: AsyncSession, guild_id: int, owner_id: int) -> TempVoiceChannel | None:
    result = await session.execute(
        select(TempVoiceChannel).where(TempVoiceChannel.guild_id == guild_id, TempVoiceChannel.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def get_all_temp_channels(session: AsyncSession, guild_id: int) -> list[TempVoiceChannel]:
    result = await session.execute(select(TempVoiceChannel).where(TempVoiceChannel.guild_id == guild_id))
    return list(result.scalars().all())


async def set_owner(session: AsyncSession, temp: TempVoiceChannel, owner_id: int) -> None:
    temp.owner_id = owner_id
    await session.commit()


async def set_locked(session: AsyncSession, temp: TempVoiceChannel, locked: bool) -> None:
    temp.locked = locked
    await session.commit()


async def set_hidden(session: AsyncSession, temp: TempVoiceChannel, hidden: bool) -> None:
    temp.hidden = hidden
    await session.commit()


async def set_user_limit(session: AsyncSession, temp: TempVoiceChannel, limit: int) -> None:
    temp.user_limit = limit
    await session.commit()


async def set_bitrate(session: AsyncSession, temp: TempVoiceChannel, bitrate: int) -> None:
    temp.bitrate = bitrate
    await session.commit()


async def delete_temp_channel(session: AsyncSession, channel_id: int) -> None:
    temp = await get_temp_channel(session, channel_id)
    if temp is not None:
        await session.execute(VoiceMasterPermit.__table__.delete().where(VoiceMasterPermit.channel_id == channel_id))
        await session.execute(VoiceMasterReject.__table__.delete().where(VoiceMasterReject.channel_id == channel_id))
        await session.delete(temp)
        await session.commit()


async def delete_all_temp_channels(session: AsyncSession, guild_id: int) -> list[int]:
    """Deletes every temp-channel DB record for a guild (used by reset)
    and returns the channel IDs that were removed, so the caller can
    also delete the actual Discord channels."""
    channels = await get_all_temp_channels(session, guild_id)
    channel_ids = [c.channel_id for c in channels]
    for channel_id in channel_ids:
        await session.execute(VoiceMasterPermit.__table__.delete().where(VoiceMasterPermit.channel_id == channel_id))
        await session.execute(VoiceMasterReject.__table__.delete().where(VoiceMasterReject.channel_id == channel_id))
    for channel in channels:
        await session.delete(channel)
    await session.commit()
    return channel_ids


# ---------------------------------------------------------- permit / reject

async def add_permit(session: AsyncSession, channel_id: int, user_id: int) -> None:
    existing = await session.execute(
        select(VoiceMasterPermit).where(VoiceMasterPermit.channel_id == channel_id, VoiceMasterPermit.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(VoiceMasterPermit(channel_id=channel_id, user_id=user_id))
    await session.commit()


async def remove_permit(session: AsyncSession, channel_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(VoiceMasterPermit).where(VoiceMasterPermit.channel_id == channel_id, VoiceMasterPermit.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_permitted(session: AsyncSession, channel_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(VoiceMasterPermit).where(VoiceMasterPermit.channel_id == channel_id, VoiceMasterPermit.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def add_reject(session: AsyncSession, channel_id: int, user_id: int) -> None:
    existing = await session.execute(
        select(VoiceMasterReject).where(VoiceMasterReject.channel_id == channel_id, VoiceMasterReject.user_id == user_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(VoiceMasterReject(channel_id=channel_id, user_id=user_id))
    await session.commit()


async def remove_reject(session: AsyncSession, channel_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(VoiceMasterReject).where(VoiceMasterReject.channel_id == channel_id, VoiceMasterReject.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def is_rejected(session: AsyncSession, channel_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(VoiceMasterReject).where(VoiceMasterReject.channel_id == channel_id, VoiceMasterReject.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None
