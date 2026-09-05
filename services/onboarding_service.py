"""Builds the embed shown when Blade joins a new server - posted in a
random channel the bot can talk in, and DMed to whoever added it."""

from __future__ import annotations

import discord

DOCS_URL = "https://blaid.best/docs.html"
SUPPORT_URL = "https://discord.gg/blaid"


def build_join_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    from core.command_meta import registry

    command_count = registry.count()
    name = bot.user.name
    description = (
        f"Thank you for adding **{name}** to **{guild.name}**. {name} is a multipurpose "
        f"Discord bot with over **{command_count:,}** commands aimed at making your Discord "
        f"experience seamless, hassle-free and fun. If you need help you can "
        f"[join our support server to receive help]({SUPPORT_URL}).\n\n"
        f"**{name}'s default prefix is set to:** `,` If you would like to change this prefix, "
        f"simply run `,prefix set (prefix)` and **ensure** that the bot has the necessary permissions.\n\n"
        f"**Quick Start Guide:**\n"
        f"> `,setup` — Creates a jail and log channel along with the jail role\n"
        f"> `,voicemaster setup` — Creates join to create voice channels\n"
        f"> `,filter add` — Adds a word to the chat filter to start moderating automatically\n"
        f"> `,help antinuke` — Shows how to protect your server from nukes and raids"
    )
    return discord.Embed(description=description)


def build_join_view() -> discord.ui.View:
    """Link buttons shown alongside the join embed - Documentation and
    Discord Server, both plain link buttons (no callback needed)."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Documentation", style=discord.ButtonStyle.link, url=DOCS_URL))
    view.add_item(discord.ui.Button(label="Discord Server", style=discord.ButtonStyle.link, url=SUPPORT_URL))
    return view


def _pick_channel(guild: discord.Guild) -> discord.TextChannel | None:
    import random

    sendable = [
        c for c in guild.text_channels
        if c.permissions_for(guild.me).send_messages
    ]
    return random.choice(sendable) if sendable else None


async def _find_inviter(guild: discord.Guild) -> discord.User | None:
    if not guild.me.guild_permissions.view_audit_log:
        return None

    import asyncio
    # Discord's audit log can lag a second or two behind the actual
    # join event - without this delay, the bot_add entry sometimes
    # isn't queryable yet, and the DM silently never goes out.
    await asyncio.sleep(2)
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
            if entry.target is not None and entry.target.id == guild.me.id:
                return entry.user
    except discord.Forbidden:
        return None
    return None


async def handle_guild_join(bot: discord.Client, guild: discord.Guild) -> None:
    embed = build_join_embed(bot, guild)
    view = build_join_view()

    channel = _pick_channel(guild)
    if channel is not None:
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            pass

    inviter = await _find_inviter(guild)
    if inviter is not None:
        try:
            await inviter.send(embed=embed, view=view)
        except discord.HTTPException:
            pass
