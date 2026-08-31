"""
Snipe tracking - deleted messages, edited messages, and removed
reactions, per channel. Deliberately in-memory only (not persisted to
the database) - snipe data is meant to be short-lived/ephemeral by
convention, and is lost on a bot restart. Keeps the last MAX_PER_CHANNEL
entries per channel per kind, most recent first.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import discord

MAX_PER_CHANNEL = 50


@dataclass
class DeletedSnipe:
    content: str
    author_name: str
    author_icon: str
    timestamp: datetime.datetime


@dataclass
class EditSnipe:
    before: str
    after: str
    author_name: str
    author_icon: str
    timestamp: datetime.datetime


@dataclass
class ReactionSnipe:
    emoji: str
    message_author_name: str
    reactor_name: str
    reactor_icon: str
    timestamp: datetime.datetime


_deleted: dict[int, list[DeletedSnipe]] = {}
_edited: dict[int, list[EditSnipe]] = {}
_reactions: dict[int, list[ReactionSnipe]] = {}


def record_delete(channel_id: int, message: discord.Message) -> None:
    entry = DeletedSnipe(
        content=message.content or "*No text content*",
        author_name=str(message.author),
        author_icon=message.author.display_avatar.url,
        timestamp=discord.utils.utcnow(),
    )
    bucket = _deleted.setdefault(channel_id, [])
    bucket.insert(0, entry)
    del bucket[MAX_PER_CHANNEL:]


def record_edit(channel_id: int, before: discord.Message, after: discord.Message) -> None:
    entry = EditSnipe(
        before=before.content or "*No text content*",
        after=after.content or "*No text content*",
        author_name=str(before.author),
        author_icon=before.author.display_avatar.url,
        timestamp=discord.utils.utcnow(),
    )
    bucket = _edited.setdefault(channel_id, [])
    bucket.insert(0, entry)
    del bucket[MAX_PER_CHANNEL:]


def record_reaction_remove(channel_id: int, emoji: str, message_author_name: str, reactor: discord.abc.User) -> None:
    entry = ReactionSnipe(
        emoji=emoji,
        message_author_name=message_author_name,
        reactor_name=str(reactor),
        reactor_icon=reactor.display_avatar.url,
        timestamp=discord.utils.utcnow(),
    )
    bucket = _reactions.setdefault(channel_id, [])
    bucket.insert(0, entry)
    del bucket[MAX_PER_CHANNEL:]


def get_deleted(channel_id: int, index: int) -> tuple[DeletedSnipe | None, int]:
    items = _deleted.get(channel_id, [])
    if not items or index < 1 or index > len(items):
        return None, len(items)
    return items[index - 1], len(items)


def get_edited(channel_id: int, index: int) -> tuple[EditSnipe | None, int]:
    items = _edited.get(channel_id, [])
    if not items or index < 1 or index > len(items):
        return None, len(items)
    return items[index - 1], len(items)


def get_reaction(channel_id: int, index: int) -> tuple[ReactionSnipe | None, int]:
    items = _reactions.get(channel_id, [])
    if not items or index < 1 or index > len(items):
        return None, len(items)
    return items[index - 1], len(items)


def clear_channel(channel_id: int) -> None:
    _deleted.pop(channel_id, None)
    _edited.pop(channel_id, None)
    _reactions.pop(channel_id, None)