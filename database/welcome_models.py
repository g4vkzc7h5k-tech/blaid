"""Welcome, goodbye and boost message configuration."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class WelcomeConfig(Base):
    __tablename__ = "welcome_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str] = mapped_column(
        Text,
        default=(
            "{content: {user.mention}}\n"
            "{embed}\n"
            "{color: #5865F2}\n"
            "{title: Welcome to {guild.name}!}\n"
            "{description: Hey {user.mention}, welcome aboard! You're member #{guild.count}. "
            "We're glad to have you here — take a moment to look around and make yourself at home.}\n"
            "{thumbnail: {user.avatar}}\n"
            "{footer: {guild.name} && {guild.icon}}"
        ),
    )


class GoodbyeConfig(Base):
    __tablename__ = "goodbye_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str] = mapped_column(
        Text,
        default=(
            "{embed}\n"
            "{color: #ED4245}\n"
            "{title: Goodbye!}\n"
            "{description: {user.tag} has left {guild.name}. We're now {guild.count} members.}\n"
            "{thumbnail: {user.avatar}}\n"
            "{footer: {guild.name} && {guild.icon}}"
        ),
    )


class BoostConfig(Base):
    __tablename__ = "boost_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str] = mapped_column(
        Text,
        default=(
            "{content: {user.mention}}\n"
            "{embed}\n"
            "{color: #FF73FA}\n"
            "{title: Thank You For Boosting!}\n"
            "{description: {user.mention} just boosted {guild.name}! We really appreciate your support — "
            "thank you for helping make this server even better.}\n"
            "{thumbnail: {user.avatar}}\n"
            "{footer: {guild.name} && {guild.icon}}"
        ),
    )