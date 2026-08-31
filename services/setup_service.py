"""
Setup service.

Creates the minimal moderation infrastructure Blade needs:
- a "blaid-mod" category
- a "Jailed" role that can see nothing except the jail channel
- "imute" and "rmute" roles (deny Attach Files/Embed Links, and Add
  Reactions respectively, in every channel)
- a jail channel (visible only to the jailed role, the server owner, and the bot)
- a single logs channel used for every moderation modlog entry

reset_setup() tears all of it back down: unjails everyone, deletes
the jail/imute/rmute roles, and deletes the jail/logs channels (and
the now-empty category).
"""

from __future__ import annotations

import discord

from database.database import get_session
from repositories import guild_config_repository, moderation_repository


class SetupHierarchyError(Exception):
    """Raised when Blade's top role isn't above jail/imute/rmute."""


async def _deny_jail_role_everywhere(guild: discord.Guild, jail_role: discord.Role, jail_channel_id: int | None) -> None:
    """So the jailed role truly can't see anything except jail."""
    for channel in guild.channels:
        if jail_channel_id is not None and channel.id == jail_channel_id:
            continue
        try:
            await channel.set_permissions(jail_role, view_channel=False, reason="Blaid setup: jail isolation")
        except discord.Forbidden:
            pass


async def _deny_role_permissions_everywhere(guild: discord.Guild, role: discord.Role, **denied) -> None:
    """Denies the given permission kwargs (e.g. attach_files=False) for
    this role in every channel - used for imute/rmute."""
    for channel in guild.channels:
        try:
            await channel.set_permissions(role, reason="Blaid setup: role isolation", **denied)
        except discord.Forbidden:
            pass


async def run_setup(guild: discord.Guild, executor: discord.Member) -> None:
    async with get_session() as session:
        cfg = await guild_config_repository.get_or_create(session, guild.id)
        is_first_time_setup = not cfg.setup_complete

        # --- Jail role ---
        jail_role = guild.get_role(cfg.jail_role_id) if cfg.jail_role_id else None
        if jail_role is None:
            jail_role = discord.utils.get(guild.roles, name="Jailed")
        if jail_role is None:
            jail_role = await guild.create_role(
                name="Jailed", permissions=discord.Permissions.none(), reason="Blaid setup"
            )
        cfg.jail_role_id = jail_role.id

        # --- imute role ---
        imute_role = guild.get_role(cfg.imute_role_id) if cfg.imute_role_id else None
        if imute_role is None:
            imute_role = discord.utils.get(guild.roles, name="imute")
        if imute_role is None:
            imute_role = await guild.create_role(
                name="imute", permissions=discord.Permissions.none(), reason="Blaid setup"
            )
        cfg.imute_role_id = imute_role.id

        # --- rmute role ---
        rmute_role = guild.get_role(cfg.rmute_role_id) if cfg.rmute_role_id else None
        if rmute_role is None:
            rmute_role = discord.utils.get(guild.roles, name="rmute")
        if rmute_role is None:
            rmute_role = await guild.create_role(
                name="rmute", permissions=discord.Permissions.none(), reason="Blaid setup"
            )
        cfg.rmute_role_id = rmute_role.id

        await session.commit()

        # --- Hierarchy check - Blade must sit above all three ---
        # Local position data (guild.me.top_role, cached Role objects,
        # even a fresh fetch_roles() call) has proven unreliable here -
        # a known discord.py caching issue (Rapptz/discord.py#4087).
        # Instead of comparing positions locally, ask Discord itself:
        # a harmless no-op position edit on each role will fail with
        # Forbidden if and only if Blade doesn't actually outrank it -
        # that's Discord's own real-time, authoritative check.
        for role in (jail_role, imute_role, rmute_role):
            try:
                await role.edit(position=role.position, reason="Blaid setup: hierarchy check")
            except discord.Forbidden:
                raise SetupHierarchyError()
            except discord.HTTPException:
                pass

        # --- Category ---
        category = guild.get_channel(cfg.category_id) if cfg.category_id else None
        if category is None:
            category = discord.utils.get(guild.categories, name="blaid-mod")
        if category is None:
            category = await guild.create_category("blaid-mod", reason="Blaid setup")
        cfg.category_id = category.id

        # --- Jail channel ---
        jail_channel = guild.get_channel(cfg.jail_channel_id) if cfg.jail_channel_id else None
        if jail_channel is None:
            owner = guild.get_member(guild.owner_id) if guild.owner_id else None
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            if owner is not None:
                overwrites[owner] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            jail_channel = await guild.create_text_channel(
                "jail", category=category, overwrites=overwrites, reason="Blaid setup"
            )
        cfg.jail_channel_id = jail_channel.id

        # --- Deny the jailed role everywhere except jail ---
        await _deny_jail_role_everywhere(guild, jail_role, cfg.jail_channel_id)

        # --- Deny imute/rmute permissions everywhere ---
        await _deny_role_permissions_everywhere(guild, imute_role, attach_files=False, embed_links=False)
        await _deny_role_permissions_everywhere(guild, rmute_role, add_reactions=False)

        # --- Logs channel ---
        logs_channel = guild.get_channel(cfg.logs_channel_id) if cfg.logs_channel_id else None
        if logs_channel is None:
            logs_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            logs_channel = await guild.create_text_channel(
                "logs", category=category, overwrites=logs_overwrites, reason="Blaid setup"
            )
        cfg.logs_channel_id = logs_channel.id

        cfg.setup_complete = True
        await session.commit()

    # The logs channel now exists, so this should be the very first
    # entry that lands in it - Case #1 / Setup - on a genuine first-time
    # setup. Clear out any stray cases logged before setup finally
    # succeeded (e.g. from testing commands during earlier failed
    # attempts) so the numbering actually starts clean.
    if is_first_time_setup:
        async with get_session() as session:
            await moderation_repository.delete_all_cases_for_guild(session, guild.id)

    from services.moderation_service import log_and_announce

    await log_and_announce(
        guild, "setup", executor,
        target_mention=None, reason="Moderation setup completed",
    )


async def reset_setup(guild: discord.Guild) -> None:
    async with get_session() as session:
        cfg = await guild_config_repository.get(session, guild.id)
        if cfg is None:
            return

        jail_role_id = cfg.jail_role_id
        imute_role_id = cfg.imute_role_id
        rmute_role_id = cfg.rmute_role_id
        jail_channel_id = cfg.jail_channel_id
        logs_channel_id = cfg.logs_channel_id
        category_id = cfg.category_id

        cfg.jail_role_id = None
        cfg.imute_role_id = None
        cfg.rmute_role_id = None
        cfg.jail_channel_id = None
        cfg.logs_channel_id = None
        cfg.category_id = None
        cfg.setup_complete = False
        await session.commit()

    # Unjail/un-imute/un-rmute everyone, then delete each role.
    for role_id in (jail_role_id, imute_role_id, rmute_role_id):
        if not role_id:
            continue
        role = guild.get_role(role_id)
        if role is not None:
            for member in list(role.members):
                try:
                    await member.remove_roles(role, reason="Blaid: moderation setup reset")
                except discord.Forbidden:
                    pass
            try:
                await role.delete(reason="Blaid: moderation setup reset")
            except discord.Forbidden:
                pass

    for channel_id in (jail_channel_id, logs_channel_id):
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                try:
                    await channel.delete(reason="Blaid: moderation setup reset")
                except discord.Forbidden:
                    pass

    if category_id:
        category = guild.get_channel(category_id)
        if category is not None:
            try:
                await category.delete(reason="Blaid: moderation setup reset")
            except discord.Forbidden:
                pass
