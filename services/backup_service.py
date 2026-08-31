"""
,backup - snapshots and restores a server's roles, channels, and a
handful of guild-level settings.

Snapshots are stored as JSON. Restore matches roles/channels by NAME
(Discord doesn't let us recreate the exact same IDs), so renaming
things between backup and restore means they'll be treated as
different items - that's an inherent limitation of any restore
system that isn't the original guild itself.

"merge" mode only adds what's missing (by name) - nothing existing is
touched or removed. "destructive" mode deletes every current
non-managed role and every channel first, then rebuilds everything
from the snapshot - this is irreversible without another backup.
"""

from __future__ import annotations

import asyncio
import json

import discord


def _serialize_overwrites(overwrites: dict) -> list[dict]:
    result = []
    for target, overwrite in overwrites.items():
        allow, deny = overwrite.pair()
        if isinstance(target, discord.Role):
            result.append({"type": "role", "name": target.name, "allow": allow.value, "deny": deny.value})
        elif isinstance(target, discord.Member):
            result.append({"type": "member", "id": target.id, "allow": allow.value, "deny": deny.value})
    return result


def snapshot_guild(guild: discord.Guild) -> dict:
    roles = []
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_default() or role.managed:
            continue
        roles.append({
            "name": role.name,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "permissions": role.permissions.value,
        })

    categories = []
    for cat in sorted(guild.categories, key=lambda c: c.position):
        categories.append({
            "name": cat.name,
            "overwrites": _serialize_overwrites(cat.overwrites),
        })

    channels = []
    for channel in sorted(guild.channels, key=lambda c: getattr(c, "position", 0)):
        if isinstance(channel, discord.CategoryChannel):
            continue

        entry = {
            "name": channel.name,
            "category_name": channel.category.name if channel.category else None,
            "overwrites": _serialize_overwrites(channel.overwrites),
        }
        if isinstance(channel, discord.TextChannel):
            entry.update({
                "type": "text", "topic": channel.topic, "nsfw": channel.nsfw,
                "slowmode_delay": channel.slowmode_delay,
            })
        elif isinstance(channel, discord.VoiceChannel):
            entry.update({"type": "voice", "bitrate": channel.bitrate, "user_limit": channel.user_limit})
        else:
            continue  # forum/stage/other exotic channel types not covered yet
        channels.append(entry)

    settings = {
        "name": guild.name,
        "verification_level": str(guild.verification_level),
        "explicit_content_filter": str(guild.explicit_content_filter),
        "afk_timeout": guild.afk_timeout,
        "afk_channel_name": guild.afk_channel.name if guild.afk_channel else None,
        "system_channel_name": guild.system_channel.name if guild.system_channel else None,
    }

    return {"settings": settings, "roles": roles, "categories": categories, "channels": channels}


def summarize(snapshot: dict) -> str:
    return (
        f"**Roles** {len(snapshot['roles'])}\n"
        f"**Categories** {len(snapshot['categories'])}\n"
        f"**Channels** {len(snapshot['channels'])}\n"
        f"**Server Name** {snapshot['settings']['name']}"
    )


async def wipe_guild(guild: discord.Guild) -> None:
    """destructive mode only - removes every non-managed, non-@everyone
    role and every channel, sequentially to stay rate-limit friendly."""
    for channel in list(guild.channels):
        try:
            await channel.delete(reason="Blaid backup restore (destructive)")
        except discord.HTTPException:
            pass
        await asyncio.sleep(0.5)

    for role in list(guild.roles):
        if role.is_default() or role.managed or role >= guild.me.top_role:
            continue
        try:
            await role.delete(reason="Blaid backup restore (destructive)")
        except discord.HTTPException:
            pass
        await asyncio.sleep(0.5)


async def restore_guild(guild: discord.Guild, snapshot: dict, mode: str) -> dict:
    """Returns a summary dict: {roles_created, categories_created,
    channels_created, errors}."""
    result = {"roles_created": 0, "categories_created": 0, "channels_created": 0, "errors": 0}

    if mode == "destructive":
        await wipe_guild(guild)

    # --- roles: created bottom-up so later ones end up higher, closer to backup order
    existing_role_names = {r.name for r in guild.roles}
    for role_data in snapshot["roles"]:
        if role_data["name"] in existing_role_names:
            continue
        try:
            await guild.create_role(
                name=role_data["name"],
                color=discord.Color(role_data["color"]),
                hoist=role_data["hoist"],
                mentionable=role_data["mentionable"],
                permissions=discord.Permissions(role_data["permissions"]),
                reason="Blaid backup restore",
            )
            result["roles_created"] += 1
        except discord.HTTPException:
            result["errors"] += 1
        await asyncio.sleep(0.5)

    role_by_name = {r.name: r for r in guild.roles}

    def _resolve_overwrites(entries: list[dict]) -> dict:
        overwrites = {}
        for entry in entries:
            allow = discord.Permissions(entry["allow"])
            deny = discord.Permissions(entry["deny"])
            ow = discord.PermissionOverwrite.from_pair(allow, deny)
            if entry["type"] == "role":
                target = role_by_name.get(entry["name"])
            else:
                target = guild.get_member(entry["id"])
            if target is not None:
                overwrites[target] = ow
        return overwrites

    # --- categories
    existing_category_names = {c.name: c for c in guild.categories}
    for cat_data in snapshot["categories"]:
        if cat_data["name"] in existing_category_names:
            continue
        try:
            await guild.create_category(
                cat_data["name"], overwrites=_resolve_overwrites(cat_data["overwrites"]),
                reason="Blaid backup restore",
            )
            result["categories_created"] += 1
        except discord.HTTPException:
            result["errors"] += 1
        await asyncio.sleep(0.5)

    category_by_name = {c.name: c for c in guild.categories}

    # --- channels
    existing_channel_names = {c.name for c in guild.channels if not isinstance(c, discord.CategoryChannel)}
    for chan_data in snapshot["channels"]:
        if chan_data["name"] in existing_channel_names:
            continue

        category = category_by_name.get(chan_data["category_name"]) if chan_data["category_name"] else None
        overwrites = _resolve_overwrites(chan_data["overwrites"])

        try:
            if chan_data["type"] == "text":
                await guild.create_text_channel(
                    chan_data["name"], category=category, topic=chan_data.get("topic"),
                    nsfw=chan_data.get("nsfw", False), slowmode_delay=chan_data.get("slowmode_delay", 0),
                    overwrites=overwrites, reason="Blaid backup restore",
                )
            else:
                await guild.create_voice_channel(
                    chan_data["name"], category=category, bitrate=chan_data.get("bitrate", 64000),
                    user_limit=chan_data.get("user_limit", 0), overwrites=overwrites,
                    reason="Blaid backup restore",
                )
            result["channels_created"] += 1
        except discord.HTTPException:
            result["errors"] += 1
        await asyncio.sleep(0.5)

    return result


def dumps(snapshot: dict) -> str:
    return json.dumps(snapshot)


def loads(data: str) -> dict:
    return json.loads(data)
