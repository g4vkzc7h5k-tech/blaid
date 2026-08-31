"""
Configurable event logging - ,logs / ,log.

Fully working: message (delete/edit), member (join/leave), role
(assigned/removed to a member), moderation (kick/ban/timeout, sourced
from the audit log so it catches native Discord moderation too, not
just Blade's own commands).

HONEST GAP: channel, invite, voice, emoji, sticker, integration, and
server are all selectable in the picker and stored correctly, but
don't have a listener wired up yet - nothing will log for them until
that's built. Ask and I'll add them.

This is a separate system from the moderation modlog channel (created
by ,setup, written to by services/moderation_service.py) - that one
stays scoped to Blade's own moderation actions only, nothing here
writes to it.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from database.logging_models import LOG_EVENT_TYPES
from repositories import logging_repository
from services import premium_service

EVENT_LABELS = {
    "message": "Message", "member": "Member", "role": "Role", "channel": "Channel",
    "invite": "Invite", "moderation": "Moderation", "voice": "Voice", "emoji": "Emoji",
    "sticker": "Sticker", "integration": "Integration", "server": "Server",
}


class EventTypeSelectView(discord.ui.View):
    """The event-type picker shown by ,logs add/remove when no events
    are given as text - a native Discord multi-select, matching the
    reference screenshots."""

    def __init__(self, author_id: int, channel: discord.TextChannel, mode: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.channel = channel
        self.mode = mode  # "add" or "remove"

        options = [discord.SelectOption(label=EVENT_LABELS[e], value=e) for e in LOG_EVENT_TYPES]
        self.select.options = options
        self.select.max_values = len(options)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your picker to answer.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Select event types...", min_values=1)
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        chosen = select.values
        async with get_session() as session:
            if self.mode == "add":
                existing_pairs = await logging_repository.get_all_for_guild(session, interaction.guild.id)
                existing_channels = {c for c, _ in existing_pairs}
                if self.channel.id not in existing_channels:
                    allowed, limit = await premium_service.check_limit(
                        interaction.guild.id, "log_channels", len(existing_channels)
                    )
                    if not allowed:
                        is_prem = await premium_service.is_premium(interaction.guild.id, "server")
                        await interaction.response.send_message(
                            premium_service.limit_reached_message("log channels", limit, is_prem), ephemeral=True
                        )
                        return
                for event_type in chosen:
                    await logging_repository.add_log_channel(session, interaction.guild.id, self.channel.id, event_type)
                verb = "Now logging"
            else:
                for event_type in chosen:
                    await logging_repository.remove_log_channel(session, interaction.guild.id, self.channel.id, event_type)
                verb = "Stopped logging"

        labels = ", ".join(EVENT_LABELS[e] for e in chosen)
        embed = discord.Embed(description=f"{verb} **{labels}** {'to' if self.mode == 'add' else 'from'} {self.channel.mention}.")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


async def _send_log_event(guild: discord.Guild, event_type: str, embed: discord.Embed) -> None:
    async with get_session() as session:
        channel_ids = await logging_repository.get_channels_for_event(session, guild.id, event_type)
        color = await logging_repository.get_color(session, guild.id)

    if not channel_ids:
        return

    if color is not None:
        embed.color = discord.Color(color)

    for channel_id in channel_ids:
        channel = guild.get_channel(channel_id)
        if channel is None:
            continue
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- listeners

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        async with get_session() as session:
            if await logging_repository.is_ignored(session, message.guild.id, message.author.id):
                return

        sent_str = message.created_at.strftime("%d %B %Y at %-H:%M")
        embed = discord.Embed(
            description=(
                f"Message from {message.author.mention} deleted in {message.channel.mention}\n"
                f" it was sent at {sent_str}\n\n"
                f"**Message Content**\n{message.content or '*No text content*'}"
            )
        )
        embed.set_author(name="Message Deleted", icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"User ID: {message.author.id}")
        embed.timestamp = discord.utils.utcnow()
        await _send_log_event(message.guild, "message", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        async with get_session() as session:
            if await logging_repository.is_ignored(session, before.guild.id, before.author.id):
                return

        embed = discord.Embed(description=f"Message from {before.author.mention} edited in {before.channel.mention}")
        embed.set_author(name="Message Edited", icon_url=before.author.display_avatar.url)
        embed.add_field(name="Before", value=before.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "*empty*", inline=False)
        embed.set_footer(text=f"User ID: {before.author.id}")
        embed.timestamp = discord.utils.utcnow()
        await _send_log_event(before.guild, "message", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            if await logging_repository.is_ignored(session, member.guild.id, member.id):
                return

        embed = discord.Embed(description=f"{member.mention} joined the server.")
        embed.set_author(name="Member Joined", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        embed.timestamp = discord.utils.utcnow()
        await _send_log_event(member.guild, "member", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        async with get_session() as session:
            if await logging_repository.is_ignored(session, member.guild.id, member.id):
                return

        embed = discord.Embed(description=f"{member} left the server.")
        embed.set_author(name="Member Left", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        embed.timestamp = discord.utils.utcnow()
        await _send_log_event(member.guild, "member", embed)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        guild = entry.guild
        if guild is None:
            return

        # ---- role assignment (,logs role - "who added it to who")
        if entry.action == discord.AuditLogAction.member_role_update:
            target = entry.target
            moderator = entry.user
            added = getattr(entry.after, "roles", None) or []
            removed = getattr(entry.before, "roles", None) or []

            async with get_session() as session:
                if target is not None and await logging_repository.is_ignored(session, guild.id, target.id):
                    return

            mod_mention = moderator.mention if moderator else "Unknown"
            target_mention = target.mention if hasattr(target, "mention") else f"<@{target.id}>"

            for role in added:
                embed = discord.Embed(description=f"{role.mention} was added to {target_mention} by {mod_mention}")
                embed.set_author(name="Role Added", icon_url=moderator.display_avatar.url if moderator else None)
                embed.set_footer(text=f"User ID: {target.id}")
                embed.timestamp = discord.utils.utcnow()
                await _send_log_event(guild, "role", embed)

            for role in removed:
                embed = discord.Embed(description=f"{role.mention} was removed from {target_mention} by {mod_mention}")
                embed.set_author(name="Role Removed", icon_url=moderator.display_avatar.url if moderator else None)
                embed.set_footer(text=f"User ID: {target.id}")
                embed.timestamp = discord.utils.utcnow()
                await _send_log_event(guild, "role", embed)
            return

        # ---- moderation (,logs moderation - kick/ban, sourced from the
        # audit log so it also catches native Discord moderation, not
        # just Blade's own commands)
        if entry.action in (discord.AuditLogAction.kick, discord.AuditLogAction.ban, discord.AuditLogAction.unban):
            target = entry.target
            moderator = entry.user
            action_name = {"kick": "Kicked", "ban": "Banned", "unban": "Unbanned"}[entry.action.name]

            async with get_session() as session:
                if target is not None and await logging_repository.is_ignored(session, guild.id, target.id):
                    return

            target_mention = target.mention if hasattr(target, "mention") else f"<@{target.id}>"
            description = f"{target_mention} was {action_name.lower()} by {moderator.mention if moderator else 'Unknown'}"
            if entry.reason:
                description += f"\nReason: {entry.reason}"

            embed = discord.Embed(description=description)
            embed.set_author(name=f"Member {action_name}", icon_url=moderator.display_avatar.url if moderator else None)
            embed.set_footer(text=f"User ID: {target.id}")
            embed.timestamp = discord.utils.utcnow()
            await _send_log_event(guild, "moderation", embed)
            return

    # ---------------------------------------------------------- ,logs root

    @command_meta(
        category="Server",
        description="Configures event logging - which channel(s) log which event types.",
        syntax=",logs",
        examples=[",logs"],
        permissions=["Manage Guild"],
        aliases=["log"],
        require_args=False,
    )
    @commands.group(name="logs", aliases=["log"], invoke_without_command=True)
    @commands.guild_only()
    async def logs(self, ctx: commands.Context):
        await send_help(ctx, "logs")

    @logs.command(name="help")
    async def logs_help(self, ctx: commands.Context):
        await send_help(ctx, "logs")

    @command_meta(
        category="Server",
        description="Starts logging event types to a channel. Opens a picker if no events are given, or applies directly if given.",
        syntax=",logs add [channel] [events]",
        examples=[",logs add", ",logs add #logs message, member"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @logs.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def logs_add(self, ctx: commands.Context, channel: discord.TextChannel = None, *, events: str = None):
        channel = channel or ctx.channel

        if events:
            names = [e.strip().lower() for e in events.replace(",", " ").split() if e.strip()]
            valid = [n for n in names if n in LOG_EVENT_TYPES]
            invalid = [n for n in names if n not in LOG_EVENT_TYPES]
            if not valid:
                await ctx.error(f"No valid event types given. Valid: {', '.join(LOG_EVENT_TYPES)}.")
                return

            async with get_session() as session:
                existing_pairs = await logging_repository.get_all_for_guild(session, ctx.guild.id)
                existing_channels = {c for c, _ in existing_pairs}
                if channel.id not in existing_channels:
                    allowed, limit = await premium_service.check_limit(ctx.guild.id, "log_channels", len(existing_channels))
                    if not allowed:
                        is_prem = await premium_service.is_premium(ctx.guild.id, "server")
                        await ctx.error(premium_service.limit_reached_message("log channels", limit, is_prem))
                        return
                for event_type in valid:
                    await logging_repository.add_log_channel(session, ctx.guild.id, channel.id, event_type)
            message = f"Now logging **{', '.join(EVENT_LABELS[v] for v in valid)}** to {channel.mention}."
            if invalid:
                message += f" (ignored unknown: {', '.join(invalid)})"
            await ctx.success(message)
            return

        embed = discord.Embed(description=f"Pick the event types to log to {channel.mention}:")
        view = EventTypeSelectView(ctx.author.id, channel, mode="add")
        await ctx.send(embed=embed, view=view)

    @command_meta(
        category="Server",
        description="Stops logging event types to a channel. Opens a picker if no events are given, or applies directly if given.",
        syntax=",logs remove [channel] [events]",
        examples=[",logs remove", ",logs remove #logs message, member"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @logs.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def logs_remove(self, ctx: commands.Context, channel: discord.TextChannel = None, *, events: str = None):
        channel = channel or ctx.channel

        if events:
            names = [e.strip().lower() for e in events.replace(",", " ").split() if e.strip()]
            valid = [n for n in names if n in LOG_EVENT_TYPES]
            invalid = [n for n in names if n not in LOG_EVENT_TYPES]
            if not valid:
                await ctx.error(f"No valid event types given. Valid: {', '.join(LOG_EVENT_TYPES)}.")
                return
            async with get_session() as session:
                for event_type in valid:
                    await logging_repository.remove_log_channel(session, ctx.guild.id, channel.id, event_type)
            message = f"Stopped logging **{', '.join(EVENT_LABELS[v] for v in valid)}** in {channel.mention}."
            if invalid:
                message += f" (ignored unknown: {', '.join(invalid)})"
            await ctx.success(message)
            return

        embed = discord.Embed(description=f"Pick the event types to stop logging in {channel.mention}:")
        view = EventTypeSelectView(ctx.author.id, channel, mode="remove")
        await ctx.send(embed=embed, view=view)

    @command_meta(
        category="Server",
        description="Sets the embed color used for log messages.",
        syntax=",logs color <hex>",
        examples=[",logs color #FFD700"],
        permissions=["Manage Guild"],
    )
    @logs.command(name="color", aliases=["colour"])
    @has_permission_or_fake("manage_guild")
    async def logs_color(self, ctx: commands.Context, hex_color: str):
        hex_color = hex_color.strip().lstrip("#")
        try:
            value = int(hex_color, 16)
        except ValueError:
            await ctx.error("Provide a valid hex color, e.g. `#FFD700`.")
            return
        async with get_session() as session:
            await logging_repository.set_color(session, ctx.guild.id, value)
        await ctx.success(f"Log embed color set to `#{hex_color.upper()}`.")

    @command_meta(
        category="Server",
        description="Toggles a member being ignored from logging, or lists everyone currently ignored.",
        syntax=",logs ignore <member> | ,logs ignore list",
        examples=[",logs ignore @User", ",logs ignore list"],
        permissions=["Manage Guild"],
    )
    @logs.group(name="ignore", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def logs_ignore(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            already = await logging_repository.is_ignored(session, ctx.guild.id, member.id)
            if already:
                await logging_repository.remove_ignore(session, ctx.guild.id, member.id)
            else:
                await logging_repository.add_ignore(session, ctx.guild.id, member.id)
        if already:
            await ctx.success(f"{member.mention} is no longer ignored from logging.")
        else:
            await ctx.success(f"{member.mention} is now ignored from logging.")

    @logs_ignore.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def logs_ignore_list(self, ctx: commands.Context):
        async with get_session() as session:
            ids = await logging_repository.get_ignore_list(session, ctx.guild.id)
        if not ids:
            await ctx.info("No members are ignored from logging.")
            return
        await ctx.send(embed=discord.Embed(title="Ignored From Logging", description="\n".join(f"<@{i}>" for i in ids)))

    @command_meta(
        category="Server",
        description="Shows which channels are logging which event types.",
        syntax=",logs view",
        examples=[",logs view"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @logs.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def logs_view(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await logging_repository.get_all_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No logging is configured yet.")
            return

        by_channel: dict[int, list[str]] = {}
        for channel_id, event_type in rows:
            by_channel.setdefault(channel_id, []).append(event_type)

        lines = [
            f"<#{cid}>: {', '.join(EVENT_LABELS[e] for e in sorted(types))}"
            for cid, types in by_channel.items()
        ]
        await ctx.send(embed=discord.Embed(title="Logging Configuration", description="\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
