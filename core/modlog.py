"""
Builds the standardized "Modlog Entry" embed posted to a guild's logs
channel. Used by ,setup (Case #1 / Setup) and by every moderation
command that punishes a member (ban, kick, timeout, etc.) - one
format, one place, so the log channel is always consistent.
"""

from __future__ import annotations

import datetime

import discord


def build_modlog_embed(
    case_number: int,
    action_type: str,
    moderator: discord.abc.User,
    *,
    target_mention: str | None = None,
    reason: str | None = None,
    timestamp: datetime.datetime,
) -> discord.Embed:
    embed = discord.Embed()
    embed.set_author(name="Modlog Entry", icon_url=moderator.display_avatar.url)

    action_label = action_type.replace("_", " ").title()
    lines = [
        "**Information**",
        f"**Case #{case_number} / {action_label}**",
        f"**User**: {target_mention or 'N/A'}",
        f"**Moderator**: {moderator} ({moderator.id})",
        f"**Reason**: {reason or 'No reason provided'}",
        f"**Time**: <t:{int(timestamp.timestamp())}:R>",
    ]
    embed.description = "\n".join(lines)
    embed.timestamp = timestamp

    return embed