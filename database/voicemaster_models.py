"""VoiceMaster tables: setup config, live temp channels, and per-channel
permit/reject lists."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class VoiceMasterConfig(Base):
    __tablename__ = "voicemaster_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interface_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interface_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    join_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # "Join To Create"

    # Server-owner-only override: temp channels get created here instead
    # of `category_id` when set, without touching the original setup.
    owner_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    join_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    default_name: Mapped[str] = mapped_column(String(64), default="{user.name}'s Channel")


class TempVoiceChannel(Base):
    __tablename__ = "temp_voice_channels"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger)

    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    user_limit: Mapped[int] = mapped_column(Integer, default=0)
    bitrate: Mapped[int] = mapped_column(Integer, default=64000)


class VoiceMasterPermit(Base):
    """Users explicitly permitted into a locked/hidden temp channel."""

    __tablename__ = "voicemaster_permits"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class VoiceMasterReject(Base):
    """Users explicitly rejected/banned from a temp channel."""

    __tablename__ = "voicemaster_rejects"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class VoiceMasterExtraHub(Base):
    """Additional Join To Create channels beyond the primary one set up
    by ,voicemaster setup - added via the simpler ,jointocreate command,
    gated by the jointocreate_hubs premium limit."""

    __tablename__ = "voicemaster_extra_hubs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
