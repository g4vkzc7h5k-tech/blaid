"""
Centralized variable engine.

Every command that accepts a custom message/embed (welcome, goodbye,
boost, level-up messages, ,createembed, and future ticket/invoke
messages) resolves its text through resolve_variables() instead of
doing its own str.replace() calls, so adding a new variable only
requires editing this one file.

Variable set mirrors what's documented for greed's scripting system
(https://docs.greed.best/resources/variables) - guild.*, user.*,
target_user.*, channel.*, and custom.reason.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord


def _ts(dt: datetime | None) -> str:
    return str(int(dt.timestamp())) if dt else "N/A"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _guild_vars(guild: discord.Guild | None) -> dict[str, str]:
    if guild is None:
        return {}

    text_channels = [c for c in guild.text_channels]
    voice_channels = [c for c in guild.voice_channels]
    category_channels = [c for c in guild.categories]

    return {
        "{guild.name}": guild.name,
        "{guild.id}": str(guild.id),
        "{guild.count}": f"{guild.member_count:,}" if guild.member_count else "0",
        "{guild.member_count}": f"{guild.member_count:,}" if guild.member_count else "0",
        "{guild.region}": "N/A",
        "{guild.shard}": "0",
        "{guild.owner_id}": str(guild.owner_id or ""),
        "{guild.created_at}": _ts(guild.created_at),
        "{guild.emoji_count}": str(len(guild.emojis)),
        "{guild.role_count}": str(len(guild.roles)),
        "{guild.boost_count}": str(guild.premium_subscription_count),
        "{guild.booster_count}": str(len([m for m in guild.members if m.premium_since])) if guild.members else str(guild.premium_subscription_count),
        "{guild.boost_tier}": f"Level {int(guild.premium_tier)}",
        "{guild.preferred_locale}": str(guild.preferred_locale) if guild.preferred_locale else "en-US",
        "{guild.key_features}": ", ".join(guild.features) if guild.features else "None",
        "{guild.icon}": guild.icon.url if guild.icon else "",
        "{guild.banner}": guild.banner.url if guild.banner else "",
        "{guild.splash}": guild.splash.url if guild.splash else "",
        "{guild.discovery}": guild.discovery_splash.url if guild.discovery_splash else "",
        "{guild.max_presences}": str(guild.max_presences or "N/A"),
        "{guild.max_members}": str(guild.max_members or "N/A"),
        "{guild.max_video_channel_users}": str(guild.max_video_channel_users or "N/A"),
        "{guild.afk_timeout}": str(guild.afk_timeout),
        "{guild.afk_channel}": f"#{guild.afk_channel.name}" if guild.afk_channel else "None",
        "{guild.channels}": ", ".join(c.name for c in guild.channels),
        "{guild.channels_count}": str(len(guild.channels)),
        "{guild.text_channels}": ", ".join(c.name for c in text_channels),
        "{guild.text_channels_count}": str(len(text_channels)),
        "{guild.voice_channels}": ", ".join(c.name for c in voice_channels),
        "{guild.voice_channels_count}": str(len(voice_channels)),
        "{guild.category_channels}": ", ".join(c.name for c in category_channels),
        "{guild.category_channels_count}": str(len(category_channels)),
        "{guild.vanity}": guild.vanity_url_code or "N/A",
    }


def _user_vars(prefix: str, member: discord.Member | discord.User | None, guild: discord.Guild | None) -> dict[str, str]:
    if member is None:
        return {}

    is_member = isinstance(member, discord.Member)

    result = {
        f"{{{prefix}}}": str(member),
        f"{{{prefix}.id}}": str(member.id),
        f"{{{prefix}.mention}}": member.mention,
        f"{{{prefix}.name}}": member.name,
        f"{{{prefix}.tag}}": f"#{member.discriminator}",
        f"{{{prefix}.avatar}}": member.avatar.url if member.avatar else member.default_avatar.url,
        f"{{{prefix}.display_avatar}}": member.display_avatar.url,
        f"{{{prefix}.created_at}}": _ts(member.created_at),
        f"{{{prefix}.created_at_timestamp}}": _ts(member.created_at),
        f"{{{prefix}.display_name}}": member.display_name,
        f"{{{prefix}.bot}}": "Yes" if member.bot else "No",
    }

    if is_member:
        guild_avatar_url = member.guild_avatar.url if member.guild_avatar else result[f"{{{prefix}.avatar}}"]
        boosting = member.premium_since is not None

        join_position = "N/A"
        join_position_suffix = "N/A"
        if guild is not None and guild.members and member.joined_at:
            ranked = sorted((m for m in guild.members if m.joined_at), key=lambda m: m.joined_at)
            if member in ranked:
                pos = ranked.index(member) + 1
                join_position = str(pos)
                join_position_suffix = _ordinal(pos)

        result.update({
            f"{{{prefix}.guild_avatar}}": guild_avatar_url,
            f"{{{prefix}.joined_at}}": _ts(member.joined_at),
            f"{{{prefix}.joined_at_timestamp}}": _ts(member.joined_at),
            f"{{{prefix}.boost}}": "Yes" if boosting else "No",
            f"{{{prefix}.boost_since}}": member.premium_since.strftime("%Y-%m-%d") if boosting else "N/A",
            f"{{{prefix}.boost_since_timestamp}}": _ts(member.premium_since) if boosting else "N/A",
            f"{{{prefix}.color}}": str(member.color),
            f"{{{prefix}.top_role}}": member.top_role.mention if member.top_role else "None",
            f"{{{prefix}.role_list}}": ", ".join(r.name for r in member.roles if r.name != "@everyone") or "None",
            f"{{{prefix}.role_text_list}}": ", ".join(r.mention for r in member.roles if r.name != "@everyone") or "None",
            f"{{{prefix}.join_position}}": join_position,
            f"{{{prefix}.join_position_suffix}}": join_position_suffix,
        })

    return result


def _channel_vars(channel: discord.abc.GuildChannel | None) -> dict[str, str]:
    if channel is None:
        return {}

    result = {
        "{channel.name}": getattr(channel, "name", ""),
        "{channel.id}": str(channel.id),
        "{channel.mention}": channel.mention if hasattr(channel, "mention") else f"#{getattr(channel, 'name', '')}",
        "{channel.type}": str(channel.type) if hasattr(channel, "type") else "",
        "{channel.position}": str(getattr(channel, "position", "")),
        "{channel.topic}": getattr(channel, "topic", None) or "",
        "{channel.slowmode_delay}": str(getattr(channel, "slowmode_delay", 0)),
    }

    category = getattr(channel, "category", None)
    result["{channel.category_id}"] = str(category.id) if category else "None"
    result["{channel.category_name}"] = category.name if category else "None"

    return result


def _custom_vars(reason: str | None) -> dict[str, str]:
    if reason is None:
        return {}
    return {"{custom.reason}": reason}


def _ticket_vars(
    case_number: int | None,
    creator: discord.Member | discord.User | None,
    claimed_by: discord.Member | discord.User | None,
    status: str | None,
    closed_by: discord.Member | discord.User | None = None,
    deleted_by: discord.Member | discord.User | None = None,
    opened_at: datetime | None = None,
    open_time: str | None = None,
    users: list[discord.Member | discord.User] | None = None,
) -> dict[str, str]:
    """Not part of greed's published variable set (their docs don't
    expose a separate ticket.* namespace - tickets just reuse the same
    {user.*}/{guild.*}/{channel.*} variables above). Added here as a
    small, clearly-labeled extra for ticket naming/messages, since
    something like a case number and "who opened this" has no other
    variable to express."""
    result: dict[str, str] = {}
    if case_number is not None:
        result["{ticket.case}"] = str(case_number)
        result["{ticket.id}"] = str(case_number)
    if creator is not None:
        result["{ticket.creator}"] = str(creator)
        result["{ticket.creator.id}"] = str(creator.id)
        result["{ticket.creator.name}"] = creator.name
        result["{ticket.creator.mention}"] = creator.mention
        # {ticket.author.*} - alias matching the "who opened this" wording
        # used in the naming example ({ticket.case}-{ticket.author.name}).
        result["{ticket.author}"] = str(creator)
        result["{ticket.author.id}"] = str(creator.id)
        result["{ticket.author.name}"] = creator.name
        result["{ticket.author.mention}"] = creator.mention
    if claimed_by is not None:
        result["{ticket.claimed_by}"] = str(claimed_by)
        result["{ticket.claimed_by.mention}"] = claimed_by.mention
    else:
        result["{ticket.claimed_by}"] = "Unclaimed"
        result["{ticket.claimed_by.mention}"] = "Unclaimed"
    if status is not None:
        result["{ticket.status}"] = status.title()
    if closed_by is not None:
        result["{ticket.closed_by}"] = str(closed_by)
        result["{ticket.closed_by.mention}"] = closed_by.mention
    else:
        result["{ticket.closed_by}"] = "N/A"
        result["{ticket.closed_by.mention}"] = "N/A"
    if deleted_by is not None:
        result["{ticket.deleted_by}"] = str(deleted_by)
        result["{ticket.deleted_by.mention}"] = deleted_by.mention
    else:
        result["{ticket.deleted_by}"] = "N/A"
        result["{ticket.deleted_by.mention}"] = "N/A"
    if opened_at is not None:
        result["{ticket.opened_at}"] = discord.utils.format_dt(opened_at, style="F")
    if open_time is not None:
        result["{ticket.open_time}"] = open_time
    if users:
        result["{ticket.users}"] = ", ".join(u.mention for u in users)
    else:
        result["{ticket.users}"] = "None"
    return result


def _twitch_vars(twitch: dict | None) -> dict[str, str]:
    if not twitch:
        return {}
    return {
        "{twitch.url}": twitch.get("url", ""),
        "{twitch.title}": twitch.get("title", ""),
        "{twitch.category}": twitch.get("category", ""),
        "{twitch.game}": twitch.get("category", ""),
        "{twitch.viewers}": str(twitch.get("viewers", "")),
        "{twitch.started}": twitch.get("started", ""),
        "{twitch.thumbnail}": twitch.get("thumbnail", ""),
        "{twitch.id}": str(twitch.get("id", "")),
        "{twitch.creator}": twitch.get("creator_name", ""),
        "{twitch.creator.name}": twitch.get("creator_name", ""),
        "{twitch.creator.url}": twitch.get("creator_url", ""),
    }


def _youtube_vars(youtube: dict | None) -> dict[str, str]:
    if not youtube:
        return {}
    return {
        "{youtube.url}": youtube.get("url", ""),
        "{youtube.title}": youtube.get("title", ""),
        "{youtube.channel}": youtube.get("channel_name", ""),
        "{youtube.channel.name}": youtube.get("channel_name", ""),
        "{youtube.channel.url}": youtube.get("channel_url", ""),
        "{youtube.thumbnail}": youtube.get("thumbnail", ""),
        "{youtube.id}": youtube.get("id", ""),
        "{youtube.published}": youtube.get("published", ""),
    }


def resolve_variables(
    text: str,
    *,
    guild: discord.Guild | None = None,
    member: discord.Member | discord.User | None = None,
    channel: discord.abc.GuildChannel | None = None,
    target_member: discord.Member | discord.User | None = None,
    reason: str | None = None,
    level: int | None = None,
    xp: int | None = None,
    ticket_case: int | None = None,
    ticket_creator: discord.Member | discord.User | None = None,
    ticket_claimed_by: discord.Member | discord.User | None = None,
    ticket_status: str | None = None,
    ticket_closed_by: discord.Member | discord.User | None = None,
    ticket_deleted_by: discord.Member | discord.User | None = None,
    ticket_opened_at: datetime | None = None,
    ticket_open_time: str | None = None,
    ticket_users: list[discord.Member | discord.User] | None = None,
    twitch: dict | None = None,
    youtube: dict | None = None,
    vanity: str | None = None,
) -> str:
    """Replace every known {variable} in `text`. Unknown/unmatched
    placeholders are left untouched rather than raising."""

    if guild is None and member is not None and isinstance(member, discord.Member):
        guild = member.guild

    replacements: dict[str, str] = {}
    replacements.update(_guild_vars(guild))
    replacements.update(_user_vars("user", member, guild))
    replacements.update(_user_vars("target_user", target_member, guild))
    replacements.update(_channel_vars(channel))
    replacements.update(_custom_vars(reason))
    replacements.update(_ticket_vars(
        ticket_case, ticket_creator, ticket_claimed_by, ticket_status,
        closed_by=ticket_closed_by, deleted_by=ticket_deleted_by,
        opened_at=ticket_opened_at, open_time=ticket_open_time, users=ticket_users,
    ))
    replacements.update(_twitch_vars(twitch))
    replacements.update(_youtube_vars(youtube))
    if vanity is not None:
        replacements["{vanity}"] = vanity

    if level is not None:
        replacements["{level}"] = str(level)
        replacements["{user.level}"] = str(level)
    if xp is not None:
        replacements["{xp}"] = str(xp)
        replacements["{user.xp}"] = str(xp)

    replacements["{date}"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    replacements["{time}"] = datetime.now(timezone.utc).strftime("%H:%M:%S")

    for placeholder in sorted(replacements, key=len, reverse=True):
        text = text.replace(placeholder, replacements[placeholder])

    return text