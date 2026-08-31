"""Auto-post profile pictures to a channel on an interval - ,autopfp.
Only "anime" (illustrated, waifu.pics) and "cats" (TheCatAPI)
categories - see the conversation for why the other originally
requested categories were declined."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

VALID_CATEGORIES = ("cats",)  # "anime" removed for now - see conversation: every free anime image
# API tried (waifu.pics, nekos.best, waifu.im) failed from this host, likely a
# shared-IP reputation/rate-limit issue on PebbleHost's side, not a code bug.
DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 120
MAX_INTERVAL_SECONDS = 86400


class AutoPfpChannel(Base):
    __tablename__ = "autopfp_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    categories: Mapped[str] = mapped_column(String(64))  # comma-separated subset of VALID_CATEGORIES
    interval_seconds: Mapped[int] = mapped_column(Integer, default=DEFAULT_INTERVAL_SECONDS)
    next_post_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))