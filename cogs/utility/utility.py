"""General utility commands."""

from __future__ import annotations

import asyncio
import datetime
import io
import re

import aiohttp
import discord
from discord.ext import commands, tasks

from core import embeds as core_embeds
from core.checks import has_permission_or_fake, requires_premium
from core.command_meta import command_meta
from core.converters import Duration
from core.help_formatter import send_help
from core.helpers import format_duration
from database.database import get_session
from repositories import afk_repository, ai_usage_repository, bug_repository, funnel_repository, guild_stats_repository, imageonly_repository, namehistory_repository, reminder_repository
from services import ai_service, bible_service, caption_service, color_service, premium_service, quran_service, snipe_service, translate_service

_MESSAGE_LINK_RE = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


def _embed_to_script(embed: discord.Embed) -> str:
    """Reverse of core.script_parser.parse_script - turns a live embed
    back into Blade's {embed} script syntax."""
    lines = ["{embed}"]

    if embed.title:
        lines.append(f"{{title: {embed.title}}}")
    if embed.description:
        lines.append(f"{{description: {embed.description}}}")
    if embed.color is not None and embed.color.value:
        lines.append(f"{{color: #{embed.color.value:06X}}}")
    if embed.thumbnail and embed.thumbnail.url:
        lines.append(f"{{thumbnail: {embed.thumbnail.url}}}")
    if embed.image and embed.image.url:
        lines.append(f"{{image: {embed.image.url}}}")
    if embed.footer and (embed.footer.text or embed.footer.icon_url):
        parts = [embed.footer.text or ""]
        if embed.footer.icon_url:
            parts.append(embed.footer.icon_url)
        lines.append(f"{{footer: {' && '.join(parts)}}}")
    if embed.author and embed.author.name:
        author_parts = [f"name:{embed.author.name}"]
        if embed.author.icon_url:
            author_parts.append(f"icon:{embed.author.icon_url}")
        if embed.author.url:
            author_parts.append(f"url:{embed.author.url}")
        lines.append(f"{{author: {' && '.join(author_parts)}}}")
    for field in embed.fields:
        inline_part = " && inline" if field.inline else ""
        lines.append(f"{{field: {field.name} && {field.value}{inline_part}}}")

    return "\n".join(lines)


class InviteView(discord.ui.LayoutView):
    """Components V2 layout for ,invite - text + thumbnail side by side,
    button underneath, all inside one seamless container (matching the
    reference look). Requires discord.py 2.6+; this is genuinely newer
    API surface I haven't been able to test live - if the container
    renders oddly or errors, that's the first thing to check."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay("**blaid**"),
                discord.ui.TextDisplay("> Invite **blaid** to your server"),
                accessory=discord.ui.Thumbnail(media=bot.user.display_avatar.url),
            ),
            discord.ui.ActionRow(
                discord.ui.Button(
                    label="Invite",
                    style=discord.ButtonStyle.link,
                    url="https://discord.com/oauth2/authorize?client_id=1499768350773874830&permissions=8&integration_type=0&scope=bot+applications.commands",
                )
            ),
        )
        self.add_item(container)


def _relative_time(dt: discord.utils.datetime.datetime) -> str:
    """'20 April 2026' -> '4 months ago' style, matching the boxed
    footer text in ,serverinfo (not Discord's own <t:...:R> styling,
    which doesn't render as a grey inline-code box)."""
    delta = discord.utils.utcnow() - dt
    days = delta.days

    if days >= 365:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    if days >= 30:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} ago"

    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    minutes = delta.seconds // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''} ago"


class InvitesView(discord.ui.LayoutView):
    """Components V2 layout for ,invites - title, list, page counter,
    and the prev/next/close button row all inside one seamless
    container, matching the reference look exactly."""

    def __init__(self, guild_name: str, invites: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.guild_name = guild_name
        self.all_invites = invites
        self.author_id = author_id

        self.pages = [invites[i:i + 5] for i in range(0, len(invites), 5)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [
            f"[{inv.code}]({inv.url}) by **{inv.inviter or 'Unknown'}** Â· {inv.uses} uses Â· {inv.channel.mention}"
            for inv in chunk
        ] or ["No invites found."]

        components = [
            discord.ui.TextDisplay(f"# Invites for {guild_name}"),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = InvitesView(self.guild_name, self.all_invites, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = InvitesView(self.guild_name, self.all_invites, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class InRoleView(discord.ui.LayoutView):
    """Components V2 layout for ,inrole - same seamless-card look as
    ,invites, but no search button (not requested here)."""

    def __init__(self, role: discord.Role, members: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.role = role
        self.all_members = members
        self.author_id = author_id

        self.pages = [members[i:i + 10] for i in range(0, len(members), 10)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [f"{m.mention} Â· {m.name}" for m in chunk] or ["No members found."]

        components = [
            discord.ui.TextDisplay(f"# Members with {role.name}"),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = InRoleView(self.role, self.all_members, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = InRoleView(self.role, self.all_members, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class NewUsersView(discord.ui.LayoutView):
    """Components V2 layout for ,newusers - same seamless-card look as
    ,inrole, no search button."""

    def __init__(self, members: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.all_members = members
        self.author_id = author_id

        self.pages = [members[i:i + 10] for i in range(0, len(members), 10)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [f"{m.mention} Â· {m.name}" for m in chunk] or ["No members found."]

        components = [
            discord.ui.TextDisplay(f"# {len(members)} Newest Members"),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = NewUsersView(self.all_members, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = NewUsersView(self.all_members, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class PermissionsView(discord.ui.LayoutView):
    """Components V2 layout for ,permissions - title+count with avatar
    thumbnail, permission list, no search button."""

    def __init__(self, member: discord.Member, permission_names: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.member = member
        self.all_permissions = permission_names
        self.author_id = author_id

        self.pages = [permission_names[i:i + 10] for i in range(0, len(permission_names), 10)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [f"**{name}**" for name in chunk] or ["No permissions found."]

        components = [
            discord.ui.Section(
                discord.ui.TextDisplay(f"# {member.display_name}'s permissions â {len(permission_names)}"),
                accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
            ),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = PermissionsView(self.member, self.all_permissions, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = PermissionsView(self.member, self.all_permissions, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class NameHistoryView(discord.ui.LayoutView):
    """Components V2 layout for ,namehistory - title+avatar via Section,
    name list, no search button."""

    def __init__(self, member: discord.Member, entries: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.member = member
        self.all_entries = entries
        self.author_id = author_id

        self.pages = [entries[i:i + 6] for i in range(0, len(entries), 6)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [f"**{e.name}** Â· {_relative_time(e.recorded_at)}" for e in chunk] or ["No name history found."]

        components = [
            discord.ui.Section(
                discord.ui.TextDisplay(f"# {member.display_name}'s names"),
                accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
            ),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = NameHistoryView(self.member, self.all_entries, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = NameHistoryView(self.member, self.all_entries, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class EmojisView(discord.ui.LayoutView):
    """Components V2 layout for ,emojis - same seamless-card pattern
    as ,inrole/,newusers/,permissions, no search button."""

    def __init__(self, guild: discord.Guild, emojis: list, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.guild = guild
        self.all_emojis = emojis
        self.author_id = author_id

        self.pages = [emojis[i:i + 10] for i in range(0, len(emojis), 10)] or [[]]
        self.page = max(0, min(page, len(self.pages) - 1))
        total = len(self.pages)

        chunk = self.pages[self.page]
        lines = [f"{emoji} {emoji.name}" for emoji in chunk] or ["No emojis found."]

        components = [
            discord.ui.TextDisplay(f"# Emojis in {guild.name} â {len(emojis)}/{guild.emoji_limit}"),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay("\n".join(lines)),
            discord.ui.Separator(visible=True),
            discord.ui.TextDisplay(f"Page {self.page + 1}/{total}"),
        ]

        prev_button = discord.ui.Button(
            emoji="<:emoji_14:1541283003416969436>", style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0 or total <= 1),
        )
        next_button = discord.ui.Button(
            emoji="<:emoji_14:1541282992209666138>", style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total - 1 or total <= 1),
        )
        close_button = discord.ui.Button(emoji="<:emoji_16:1541283158857613332>", style=discord.ButtonStyle.danger)

        prev_button.callback = self._on_prev
        next_button.callback = self._on_next
        close_button.callback = self._on_close

        components.append(discord.ui.ActionRow(prev_button, next_button, close_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        new_view = EmojisView(self.guild, self.all_emojis, self.author_id, self.page - 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        new_view = EmojisView(self.guild, self.all_emojis, self.author_id, self.page + 1)
        await interaction.response.edit_message(view=new_view)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._poll_reminders.start()

    def cog_unload(self) -> None:
        self._poll_reminders.cancel()

    @tasks.loop(seconds=30)
    async def _poll_reminders(self):
        now = discord.utils.utcnow()
        async with get_session() as session:
            due = await reminder_repository.get_due(session, now)

        for item in due:
            description = item.description or "No description"
            embed = discord.Embed(description=f"â° Reminder: {description}")
            sent = False

            channel = self.bot.get_channel(item.channel_id)
            if channel is not None:
                try:
                    await channel.send(content=f"<@{item.user_id}>", embed=embed)
                    sent = True
                except discord.HTTPException:
                    pass

            if not sent:
                user = self.bot.get_user(item.user_id)
                if user is not None:
                    try:
                        await user.send(embed=embed)
                    except discord.HTTPException:
                        pass

            async with get_session() as session:
                await reminder_repository.delete_reminder(session, item.id)

    @_poll_reminders.before_loop
    async def _before_poll_reminders(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        async with get_session() as session:
            image_only = await imageonly_repository.is_enabled(session, message.channel.id)
        if image_only and not message.attachments:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return

        async with get_session() as session:
            afk = await afk_repository.remove_afk(session, message.guild.id, message.author.id)
            await funnel_repository.mark_spoken(session, message.guild.id, message.author.id)

        if afk is not None:
            set_at = afk.set_at
            if set_at.tzinfo is None:
                set_at = set_at.replace(tzinfo=datetime.timezone.utc)
            seconds = int((discord.utils.utcnow() - set_at).total_seconds())
            embed = discord.Embed(
                description=f"{message.author.mention}: ð **Welcome back,** you went away for **{format_duration(seconds)}**."
            )
            await message.channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            await guild_stats_repository.record_join(session, member.guild.id)
            await namehistory_repository.record_name(session, member.id, member.name)
            await funnel_repository.record_join(session, member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.name == after.name:
            return
        async with get_session() as session:
            await namehistory_repository.record_name(session, after.id, after.name)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        async with get_session() as session:
            await guild_stats_repository.record_leave(session, member.guild.id)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        snipe_service.record_delete(message.channel.id, message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        snipe_service.record_edit(before.channel.id, before, after)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        reactor = self.bot.get_user(payload.user_id)
        if reactor is None:
            try:
                reactor = await self.bot.fetch_user(payload.user_id)
            except discord.HTTPException:
                return
        if reactor.bot:
            return
        snipe_service.record_reaction_remove(channel.id, str(payload.emoji), str(message.author), reactor)

    @command_meta(
        category="Utility",
        description="Shows information about a member.",
        syntax=",userinfo [member]",
        examples=[",userinfo", ",userinfo @User"],
        require_args=False,
    )
    @commands.command(name="userinfo", aliases=["ui", "whois"], with_app_command=False)
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        created_str = member.created_at.strftime("%d %B %Y")
        created_relative = _relative_time(member.created_at)

        if member.joined_at:
            joined_str = member.joined_at.strftime("%d %B %Y")
            joined_relative = _relative_time(member.joined_at)
        else:
            joined_str = "Unknown"
            joined_relative = None

        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]

        join_position = "Unknown"
        joined_members = sorted((m for m in ctx.guild.members if m.joined_at), key=lambda m: m.joined_at)
        if member in joined_members:
            join_position = str(joined_members.index(member) + 1)

        lines = [
            "**Created**",
            f"> `{created_str}` `({created_relative})`",
            "",
            "**Joined**",
            f"> `{joined_str}`" + (f" `({joined_relative})`" if joined_relative else ""),
            "",
            f"**Roles ({len(roles)})**",
            " ".join(roles)[:1024] if roles else "None",
        ]

        embed = discord.Embed(description="\n".join(lines))
        embed.set_author(name=f"{member.display_name} (@{member.name})", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id} â¢ Join Position: {join_position}")

        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Shows detailed information about this server.",
        syntax=",serverinfo",
        examples=[",serverinfo"],
        require_args=False,
    )
    @commands.command(name="serverinfo", aliases=["si"], with_app_command=False)
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild

        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_owner()
            except discord.HTTPException:
                owner = None

        created = guild.created_at
        relative = _relative_time(created)
        created_str = created.strftime("%d %B %Y")

        categories = len(guild.categories)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        channels_total = categories + text_channels + voice_channels

        stickers_count = len(guild.stickers)
        emojis_count = len(guild.emojis)
        roles_count = len(guild.roles)
        counts_total = stickers_count + emojis_count + roles_count

        boosters = len([m for m in guild.members if m.premium_since]) if guild.members else guild.premium_subscription_count

        icon_display = f"[Icon]({guild.icon.url})" if guild.icon else "`none`"
        banner_display = f"[Banner]({guild.banner.url})" if guild.banner else "`none`"
        splash_display = f"[Splash]({guild.splash.url})" if guild.splash else "`none`"

        mfa_display = "enabled" if guild.mfa_level else "disabled"
        vanity_display = guild.vanity_url_code or "N/A"

        lines = [
            "**Created**",
            f"> `{created_str}` `({relative})`",
            "",
            f"**Counts ({counts_total})**",
            f"> Stickers: `{stickers_count}`",
            f"> Emojis: `{emojis_count}`",
            f"> Roles: `{roles_count}`",
            "",
            f"**Channels ({channels_total})**",
            f"> Categories: `{categories}`",
            f"> Text: `{text_channels}`",
            f"> Voice: `{voice_channels}`",
            "",
            f"**Members ({guild.member_count})**",
            f"> Total: `{guild.member_count}`",
            f"> Boosters: `{boosters}`",
            "",
            "**Boosts**",
            f"> Level: `{int(guild.premium_tier)}`",
            f"> Boosts: `{guild.premium_subscription_count}`",
            f"> Boosters: `{boosters}`",
            "",
            "**Design**",
            f"> Icon: {icon_display}",
            f"> Banner: {banner_display}",
            f"> Splash: {splash_display}",
            "",
            "**System**",
            f"> Verification: `{str(guild.verification_level)}`",
            f"> Mfa level: `{mfa_display}`",
            f"> Vanity: `{vanity_display}`",
        ]

        embed = discord.Embed(title=guild.name, description="\n".join(lines))
        if owner is not None:
            embed.set_author(name=f"owned by {owner.display_name} â {guild.owner_id}", icon_url=owner.display_avatar.url)
        else:
            embed.set_author(name=f"owned by {guild.owner_id}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"ID: {guild.id}")

        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a member's avatar at full size.",
        syntax=",avatar [member]",
        examples=[",avatar", ",avatar @User"],
        require_args=False,
    )
    @commands.command(name="avatar", aliases=["av"], with_app_command=False)
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}'s Avatar")
        embed.set_image(url=member.display_avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a member's profile banner at full size.",
        syntax=",banner [member]",
        examples=[",banner", ",banner @User"],
        require_args=False,
    )
    @commands.command(name="banner", with_app_command=False)
    async def banner(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)  # banner isn't populated on cached Member/User objects

        if user.banner is None:
            await ctx.info(f"**{member.display_name}** has no banner set.")
            return

        embed = discord.Embed(title=f"{member.display_name}'s Banner")
        embed.set_image(url=user.banner.url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a member's server-specific banner, if they've set one for this server.",
        syntax=",serverbanner [member]",
        examples=[",serverbanner", ",serverbanner @User"],
        require_args=False,
    )
    @commands.command(name="serverbanner", aliases=["sbanner", "sb"], with_app_command=False)
    @commands.guild_only()
    async def serverbanner(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        # Per-server banners are a newer/less certain part of discord.py's
        # API surface than per-server avatars - check for the attribute
        # defensively rather than assume it exists on every version.
        guild_banner = getattr(member, "guild_banner", None)
        if guild_banner is not None:
            image_url = guild_banner.url
        else:
            user = await self.bot.fetch_user(member.id)
            if user.banner is None:
                await ctx.info(f"**{member.display_name}** has no banner set.")
                return
            image_url = user.banner.url

        embed = discord.Embed(title=f"{member.display_name}'s Server Banner")
        embed.set_image(url=image_url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a member's server-specific avatar, if they've set one for this server.",
        syntax=",serveravatar [member]",
        examples=[",serveravatar", ",serveravatar @User"],
        require_args=False,
    )
    @commands.command(name="serveravatar", aliases=["savatar", "sav"], with_app_command=False)
    @commands.guild_only()
    async def serveravatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        if member.guild_avatar is None:
            await ctx.info(f"**{member.display_name}** has no server-specific avatar set.")
            return

        embed = discord.Embed(title=f"{member.display_name}'s Server Avatar")
        embed.set_image(url=member.guild_avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows the server's member count, broken down by humans and bots.",
        syntax=",membercount",
        examples=[",membercount"],
        require_args=False,
    )
    @commands.command(name="membercount", aliases=["mc"], with_app_command=False)
    @commands.guild_only()
    async def membercount(self, ctx: commands.Context):
        guild = ctx.guild
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        embed = discord.Embed(
            description=(
                f"**Total** `{guild.member_count}`\n"
                f"**Humans** `{humans}`\n"
                f"**Bots** `{bots}`"
            )
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Shows information about the bot itself.",
        syntax=",botinfo",
        examples=[",botinfo"],
        require_args=False,
    )
    @commands.command(name="botinfo", aliases=["bi", "info"], with_app_command=False)
    async def botinfo(self, ctx: commands.Context):
        from core.command_meta import registry

        command_count = registry.count()
        server_count = len(self.bot.guilds)
        user_count = sum(g.member_count for g in self.bot.guilds if g.member_count)

        created_relative = _relative_time(self.bot.user.created_at)
        launched_relative = _relative_time(self.bot.started_at)
        latency_ms = round(self.bot.latency * 1000)

        try:
            import psutil
            memory_gb = psutil.Process().memory_info().rss / (1024 ** 3)
            memory_display = f"{memory_gb:.1f}GB" if memory_gb >= 1 else f"{memory_gb * 1024:.0f}MB"
        except Exception:
            memory_display = "N/A"

        lines = [
            f"Utilizing `{command_count:,}` commands",
            "",
            "**Bot**",
            f"Users: `{user_count:,}`",
            f"Servers: `{server_count:,}`",
            f"Created: `{created_relative}`",
            "**System**",
            f"Latency: `{latency_ms}ms`",
            f"Memory: `{memory_display}`",
            f"Launched: `{launched_relative}`",
            "",
            "Built with discord.py",
        ]

        embed = discord.Embed(description="\n".join(lines))
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Copies an embed's script code - reply to a message with an embed, or pass a message link.",
        syntax=",copyembed [message_link]",
        examples=[",copyembed", ",copyembed https://discord.com/channels/123/456/789"],
        require_args=False,
    )
    @commands.command(name="copyembed", with_app_command=False)
    async def copyembed(self, ctx: commands.Context, *, message_link: str = None):
        target_message = None

        if ctx.message.reference is not None:
            resolved = ctx.message.reference.resolved
            if isinstance(resolved, discord.Message):
                target_message = resolved
            else:
                try:
                    target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                except discord.HTTPException:
                    target_message = None

        if target_message is None and message_link:
            match = _MESSAGE_LINK_RE.search(message_link)
            if not match:
                await ctx.error("That doesn't look like a valid message link.")
                return
            _guild_id, channel_id, message_id = (int(g) for g in match.groups())
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                await ctx.error("I can't see that channel.")
                return
            try:
                target_message = await channel.fetch_message(message_id)
            except discord.HTTPException:
                await ctx.error("Couldn't find that message.")
                return

        if target_message is None:
            await ctx.error("Reply to a message with an embed, or provide a message link.")
            return

        if not target_message.embeds:
            await ctx.error("That message has no embed.")
            return

        script = _embed_to_script(target_message.embeds[0])
        await ctx.send(embed=discord.Embed(description=f"```{script}```"))

    @command_meta(
        category="General",
        description="Shows the bot's current latency.",
        syntax=",ping",
        examples=[",ping"],
        require_args=False,
    )
    @commands.command(name="ping", with_app_command=False)
    async def ping(self, ctx: commands.Context):
        latency_ms = round(self.bot.latency * 1000)
        embed = discord.Embed(description=f"{ctx.author.mention} Latency: `{latency_ms}ms`")
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Shows how long Blaid has been online.",
        syntax=",uptime",
        examples=[",uptime"],
        require_args=False,
    )
    @commands.command(name="uptime", with_app_command=False)
    async def uptime(self, ctx: commands.Context):
        delta = discord.utils.utcnow() - self.bot.started_at
        total_seconds = int(delta.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        await ctx.info(f"Online for `{days}d {hours}h {minutes}m`.")

    @command_meta(
        category="Utility",
        description="Translates a message to English - reply to a message, or type the text directly. Detects the source language automatically.",
        syntax=",translate [text]",
        examples=[",translate Bonjour le monde", ",translate (as a reply to a message)"],
        require_args=False,
    )
    @commands.command(name="translate", aliases=["tr"], with_app_command=False)
    async def translate(self, ctx: commands.Context, *, text: str = None):
        if text is None and ctx.message.reference is not None:
            resolved = ctx.message.reference.resolved
            if isinstance(resolved, discord.Message):
                text = resolved.content

        if not text:
            await ctx.error("Reply to a message, or provide text to translate.")
            return

        result = await translate_service.translate(text, target="en")
        if result is None:
            await ctx.error("Couldn't translate that - it may already be in English, or the translation service is unavailable.")
            return

        translated_text, source_code = result
        embed = discord.Embed(description=translated_text)
        embed.set_footer(text=f"{translate_service.language_name(source_code)} to {translate_service.language_name('en')}")
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- ai

    @command_meta(
        category="Utility",
        description="Asks a question to an AI and shows its response.",
        syntax=",ai <question>",
        examples=[",ai What's the capital of France?"],
        require_args=False,
    )
    @commands.hybrid_command(name="ai")
    @commands.guild_only()
    async def ai(self, ctx: commands.Context, *, question: str = None):
        if question is None:
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}: You need to provide `question`."))
            return

        async with get_session() as session:
            used_today = await ai_usage_repository.get_usage_today(session, ctx.guild.id, ctx.author.id)
        allowed, limit = await premium_service.check_limit(ctx.guild.id, "ai_questions_per_day", used_today)
        if not allowed:
            is_prem = await premium_service.is_premium(ctx.guild.id, "server")
            await ctx.error(premium_service.limit_reached_message("AI questions today", limit, is_prem))
            return

        async with ctx.typing():
            answer = await ai_service.ask(question)

        if answer is None:
            await ctx.error("The AI didn't respond.")
            return

        async with get_session() as session:
            await ai_usage_repository.increment_usage_today(session, ctx.guild.id, ctx.author.id)

        embed = discord.Embed(description=answer[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- bug

    @command_meta(
        category="General",
        description="Reports a bug directly to the developer.",
        syntax=",bug <description>",
        examples=[",bug ,avatar throws an error when the user has no avatar set"],
        require_args=False,
    )
    @commands.command(name="bug", with_app_command=False)
    async def bug(self, ctx: commands.Context, *, description: str = None):
        if description is None:
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}: You need to provide `description`."))
            return

        async with get_session() as session:
            report = await bug_repository.create_report(
                session, ctx.guild.id if ctx.guild else None, ctx.author.id, description
            )

        embed = discord.Embed(
            title=f"Bug report #{report.id} submitted.",
            description="-# Thanks! Our team will review it.",
            color=core_embeds.COLOR_SUCCESS,
        )
        await ctx.send(embed=embed)

        channel = self.bot.get_channel(1544118616574660698)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(1544118616574660698)
            except discord.HTTPException:
                channel = None

        if channel is not None:
            report_embed = discord.Embed(
                title=f"New Bug Report #{report.id}",
                description=description,
                color=core_embeds.COLOR_INFO,
            )
            report_embed.set_author(name=f"{ctx.author} ({ctx.author.id})", icon_url=ctx.author.display_avatar.url)
            report_embed.add_field(name="Server", value=f"{ctx.guild.name} ({ctx.guild.id})" if ctx.guild else "DM", inline=False)
            report_embed.timestamp = discord.utils.utcnow()
            try:
                await channel.send(embed=report_embed)
            except discord.HTTPException:
                pass

    # ---------------------------------------------------------- afk

    @command_meta(
        category="Information",
        description="Marks you as AFK, with an optional status. Clears automatically the next time you send a message.",
        syntax=",afk [text]",
        examples=[",afk", ",afk In a meeting"],
        require_args=False,
    )
    @commands.hybrid_command(name="afk")
    @commands.guild_only()
    async def afk(self, ctx: commands.Context, *, text: str = None):
        status = (text or "AFK")[:256]

        async with get_session() as session:
            await afk_repository.set_afk(session, ctx.guild.id, ctx.author.id, status)

        await ctx.success(f"{ctx.author.mention}: **You're now afk** with the status: `{status}`")

    # ---------------------------------------------------------- bans

    @command_meta(
        category="Information",
        description="Lists every active ban in this server.",
        syntax=",bans",
        examples=[",bans"],
        require_args=False,
    )
    @commands.command(name="bans", with_app_command=False)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def bans(self, ctx: commands.Context):
        entries = [entry async for entry in ctx.guild.bans(limit=None)]

        if not entries:
            await ctx.warn(f"{ctx.author.mention}: This server has no bans.")
            return

        chunks = [entries[i:i + 10] for i in range(0, len(entries), 10)]
        pages = []

        for chunk in chunks:
            start_index = len(pages) * 10
            lines = [
                f"`{start_index + i + 1:02d}` {entry.user} ({entry.user.id})"
                for i, entry in enumerate(chunk)
            ]
            embed = discord.Embed(title=f"Bans for {ctx.guild.name}", description="\n".join(lines))
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            pages.append(embed)

        from core.paginator import Paginator
        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    # ---------------------------------------------------------- bible

    @command_meta(
        category="Information",
        description="Shows a random Bible verse.",
        syntax=",bible",
        examples=[",bible"],
        require_args=False,
    )
    @commands.command(name="bible", with_app_command=False)
    async def bible(self, ctx: commands.Context):
        verse = await bible_service.get_random_verse()
        if verse is None:
            await ctx.error("Couldn't fetch a verse right now - try again in a moment.")
            return

        description = (
            f"## **Random Bible Verse**\n\n"
            f"> -# {verse['text']}\n\n"
            f"**Reference**\n{verse['reference']} ({verse['translation_name']})"
        )
        embed = discord.Embed(description=description)
        embed.set_footer(text="bible-api.com")
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- quran

    @command_meta(
        category="Information",
        description="Shows a random Quran verse.",
        syntax=",quran",
        examples=[",quran"],
        require_args=False,
    )
    @commands.command(name="quran", with_app_command=False)
    async def quran(self, ctx: commands.Context):
        verse = await quran_service.get_random_verse()
        if verse is None:
            await ctx.error("Couldn't fetch a verse right now - try again in a moment.")
            return

        description = (
            f"## **Random Quran Verse**\n\n"
            f"> -# {verse['text']}\n\n"
            f"**Reference**\n{verse['reference']} ({verse['translation_name']})"
        )
        embed = discord.Embed(description=description)
        embed.set_footer(text="alquran.cloud")
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- roleinfo

    @command_meta(
        category="Information",
        description="Shows information about a role.",
        syntax=",roleinfo <role>",
        examples=[",roleinfo @Moderator"],
        require_args=False,
    )
    @commands.command(name="roleinfo", with_app_command=False)
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, role: discord.Role = None):
        if role is None:
            await ctx.warn(f"{ctx.author.mention}: You need to provide `role`.")
            return

        color_hex = f"#{role.color.value:06X}" if role.color.value else "None"
        timestamp = int(role.created_at.timestamp())

        description = (
            f"**Role ID** `{role.id}`\n\n"
            f"**Guild** {ctx.guild.name} (`{ctx.guild.id}`)\n\n"
            f"**Color** `{color_hex}`\n\n"
            f"**Created** <t:{timestamp}:F> (<t:{timestamp}:R>)"
        )

        embed = discord.Embed(description=description)
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        dangerous_permissions = [
            "administrator", "ban_members", "kick_members", "manage_guild", "manage_roles",
            "manage_channels", "manage_webhooks", "manage_messages", "manage_nicknames",
            "mention_everyone", "moderate_members",
        ]
        if any(getattr(role.permissions, perm, False) for perm in dangerous_permissions):
            embed.set_footer(text="Dangerous Permissions!")

        await ctx.send(embed=embed)

    # ---------------------------------------------------------- invites

    @command_meta(
        category="Information",
        description="Lists every active invite in this server.",
        syntax=",invites",
        examples=[",invites"],
        permissions=["Manage Guild"],
        aliases=["serverinvites", "invs"],
        require_args=False,
    )
    @commands.command(name="invites", aliases=["serverinvites", "invs"], with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_guild=True)
    @commands.guild_only()
    async def invites(self, ctx: commands.Context):
        invite_list = await ctx.guild.invites()

        if not invite_list:
            await ctx.warn(f"{ctx.author.mention}: This server has **no** active invites.")
            return

        view = InvitesView(ctx.guild.name, invite_list, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- inrole

    @command_meta(
        category="Information",
        description="Lists every member with a given role.",
        syntax=",inrole <role>",
        examples=[",inrole @Moderator"],
        aliases=["ir"],
    )
    @commands.command(name="inrole", aliases=["ir"], with_app_command=False)
    @commands.guild_only()
    async def inrole(self, ctx: commands.Context, role: discord.Role):
        members = [m for m in ctx.guild.members if role in m.roles]

        if not members:
            await ctx.warn(f"{ctx.author.mention}: This role has **no** members.")
            return

        view = InRoleView(role, members, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- newusers

    @command_meta(
        category="Information",
        description="Lists this server's members, newest joins first.",
        syntax=",newusers",
        examples=[",newusers"],
        aliases=["newmembers"],
        require_args=False,
    )
    @commands.command(name="newusers", aliases=["newmembers"], with_app_command=False)
    @commands.guild_only()
    async def newusers(self, ctx: commands.Context):
        members = sorted((m for m in ctx.guild.members if m.joined_at), key=lambda m: m.joined_at, reverse=True)

        if not members:
            await ctx.warn(f"{ctx.author.mention}: Couldn't find any members.")
            return

        view = NewUsersView(members, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- permissions

    @command_meta(
        category="Information",
        description="Shows every permission a member has in this server.",
        syntax=",permissions [member]",
        examples=[",permissions", ",permissions @User"],
        aliases=["perms"],
        require_args=False,
    )
    @commands.command(name="permissions", aliases=["perms"], with_app_command=False)
    @commands.guild_only()
    async def permissions(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        names = [perm.replace("_", " ").title() for perm, value in member.guild_permissions if value]

        view = PermissionsView(member, names, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- namehistory

    @command_meta(
        category="Information",
        description="Shows a member's username history.",
        syntax=",namehistory [member]",
        examples=[",namehistory", ",namehistory @User"],
        require_args=False,
    )
    @commands.command(name="namehistory", with_app_command=False)
    @commands.guild_only()
    async def namehistory(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        async with get_session() as session:
            entries = await namehistory_repository.get_name_history(session, member.id)

        view = NameHistoryView(member, entries, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- color

    @command_meta(
        category="Information",
        description="Shows a color's hex/RGB/websafe values, based on a member's avatar or a hex code.",
        syntax=",color [member or hex]",
        examples=[",color", ",color @User", ",color #ff5500"],
        aliases=["hex", "colour", "clr"],
        require_args=False,
    )
    @commands.command(name="color", aliases=["hex", "colour", "clr"], with_app_command=False)
    async def color(self, ctx: commands.Context, *, target: str = None):
        rgb = None
        title_name = None
        member = None

        if target:
            cleaned = target.strip().lstrip("#")
            if len(cleaned) == 6:
                try:
                    value = int(cleaned, 16)
                    rgb = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
                    title_name = f"#{cleaned.upper()}"
                except ValueError:
                    rgb = None

        if rgb is None:
            if target:
                try:
                    member = await commands.MemberConverter().convert(ctx, target)
                except commands.BadArgument:
                    await ctx.error("Provide a member or a valid hex code, e.g. `#ff5500`.")
                    return
            else:
                member = ctx.author

            rgb = await color_service.get_average_color(member.display_avatar.url)
            if rgb is None:
                await ctx.error("Couldn't read that avatar's color.")
                return
            title_name = member.display_name

        r, g, b = rgb
        hex_code = f"#{r:02X}{g:02X}{b:02X}"
        websafe_r, websafe_g, websafe_b = color_service.nearest_websafe(rgb)
        websafe_hex = f"#{websafe_r:02X}{websafe_g:02X}{websafe_b:02X}"

        description = (
            f"Hex: `{hex_code}`\n"
            f"RGB: `rgb({r}, {g}, {b})`\n"
            f"Websafe: `{websafe_hex}`"
        )

        buffer = color_service.make_swatch_image(rgb)
        file = discord.File(buffer, filename="color.png")

        embed = discord.Embed(
            title=f"{title_name}'s color",
            description=description,
            color=discord.Color.from_rgb(r, g, b),
        )
        embed.set_image(url="attachment://color.png")

        await ctx.send(embed=embed, file=file)

    # ---------------------------------------------------------- emojis

    @command_meta(
        category="Information",
        description="Lists this server's custom emojis.",
        syntax=",emojis",
        examples=[",emojis"],
        require_args=False,
    )
    @commands.command(name="emojis", with_app_command=False)
    @commands.guild_only()
    async def emojis(self, ctx: commands.Context):
        emojis = ctx.guild.emojis
        view = EmojisView(ctx.guild, emojis, ctx.author.id)
        await ctx.send(view=view)

    # ---------------------------------------------------------- emoji (management)

    EMOJI_TOKEN_RE = re.compile(r"<(a?):(\w+):(\d+)>")

    def _parse_emoji_tokens(self, text: str) -> list[tuple[bool, str, int]]:
        """Returns a list of (animated, name, id) for every custom emoji
        token found in the text - works for emoji from ANY server, not
        just this one, since it's just parsing the raw <a:name:id> form."""
        return [(bool(a), name, int(eid)) for a, name, eid in self.EMOJI_TOKEN_RE.findall(text)]

    @staticmethod
    def _emoji_cdn_url(animated: bool, emoji_id: int) -> str:
        ext = "gif" if animated else "png"
        return f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"

    @command_meta(
        category="Utility",
        description="Manage this server's custom emojis.",
        syntax=",emoji",
        examples=[],
        permissions=["Manage Guild Expressions"],
        require_args=False,
    )
    @commands.group(name="emoji", invoke_without_command=True)
    @has_permission_or_fake("manage_expressions")
    @commands.guild_only()
    async def emoji(self, ctx: commands.Context):
        await send_help(ctx, "emoji")

    @emoji.command(name="help")
    async def emoji_help(self, ctx: commands.Context):
        await send_help(ctx, "emoji")

    @command_meta(
        category="Utility",
        description="Add a new emoji to the server from an image.",
        syntax=",emoji add [image] [name]",
        examples=[",emoji add pepe"],
        permissions=["Manage Guild Expressions"],
        require_args=False,
    )
    @emoji.command(name="add")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_add(self, ctx: commands.Context, *, name: str = None):
        image_bytes = None
        default_name = "emoji"

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            image_bytes = await attachment.read()
            default_name = attachment.filename.rsplit(".", 1)[0]
        elif name:
            tokens = name.split()
            if tokens and tokens[0].startswith("http"):
                url = tokens.pop(0)
                name = " ".join(tokens) if tokens else None
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
                    pass

        if image_bytes is None:
            await ctx.error("Attach an image, or provide a direct image URL.")
            return

        final_name = (name or default_name).strip().replace(" ", "_")[:32] or "emoji"

        try:
            new_emoji = await ctx.guild.create_custom_emoji(name=final_name, image=image_bytes, reason=f"Added by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Couldn't add that emoji. ({exc})")
            return

        await ctx.success(f"Added `{new_emoji.name}` to the server.")

    @command_meta(
        category="Utility",
        description="Add multiple new emojis to the server from attached images at once.",
        syntax=",emoji addmany [images]",
        examples=[",emoji addmany"],
        permissions=["Manage Guild Expressions"],
        require_args=False,
    )
    @emoji.command(name="addmany")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_addmany(self, ctx: commands.Context):
        if not ctx.message.attachments:
            await ctx.error("Attach at least one image.")
            return

        added, failed = [], 0
        for attachment in ctx.message.attachments[:25]:
            try:
                image_bytes = await attachment.read()
                name = attachment.filename.rsplit(".", 1)[0].replace(" ", "_")[:32] or "emoji"
                new_emoji = await ctx.guild.create_custom_emoji(name=name, image=image_bytes, reason=f"Added by {ctx.author}")
                added.append(new_emoji.name)
            except discord.HTTPException:
                failed += 1

        if not added:
            await ctx.error("Couldn't add any of those emojis.")
            return

        summary = f"Added {len(added)} emoji(s): {', '.join(f'`{n}`' for n in added)}"
        if failed:
            summary += f" ({failed} failed)"
        await ctx.success(summary)

    @command_meta(
        category="Utility",
        description="Shows an enlarged view of an emoji.",
        syntax=",emoji enlarge [emoji]",
        examples=[",emoji enlarge ð"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="enlarge")
    @has_permission_or_fake("manage_expressions")
    async def emoji_enlarge(self, ctx: commands.Context, *, emoji: str):
        tokens = self._parse_emoji_tokens(emoji)
        if not tokens:
            await ctx.error("That's not a custom emoji I can enlarge.")
            return

        animated, name, emoji_id = tokens[0]
        embed = discord.Embed(title=name)
        embed.set_image(url=self._emoji_cdn_url(animated, emoji_id))
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Lists this server's custom emojis.",
        syntax=",emoji list",
        examples=[",emoji list"],
        permissions=["Manage Guild Expressions"],
        require_args=False,
    )
    @emoji.command(name="list")
    @has_permission_or_fake("manage_expressions")
    async def emoji_list(self, ctx: commands.Context):
        view = EmojisView(ctx.guild, ctx.guild.emojis, ctx.author.id)
        await ctx.send(view=view)

    @command_meta(
        category="Utility",
        description="Remove an emoji from the server.",
        syntax=",emoji remove <emoji>",
        examples=[",emoji remove <:pepe:123456789012345678>"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="remove")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_remove(self, ctx: commands.Context, *, emoji: str):
        tokens = self._parse_emoji_tokens(emoji)
        if not tokens:
            await ctx.error("Provide a custom emoji from this server.")
            return

        _, _, emoji_id = tokens[0]
        target = discord.utils.get(ctx.guild.emojis, id=emoji_id)
        if target is None:
            await ctx.error("That emoji isn't from this server.")
            return

        name = target.name
        try:
            await target.delete(reason=f"Removed by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Couldn't remove that emoji. ({exc})")
            return

        await ctx.success(f"Removed `{name}` from the server.")

    @command_meta(
        category="Utility",
        description="Remove multiple emojis from the server at once.",
        syntax=",emoji removemany <emojis>",
        examples=[",emoji removemany <:pepe:123> <:kek:456>"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="removemany")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_removemany(self, ctx: commands.Context, *, emojis: str):
        tokens = self._parse_emoji_tokens(emojis)
        if not tokens:
            await ctx.error("Provide at least one custom emoji from this server.")
            return

        removed, failed = [], 0
        for _, _, emoji_id in tokens:
            target = discord.utils.get(ctx.guild.emojis, id=emoji_id)
            if target is None:
                failed += 1
                continue
            try:
                name = target.name
                await target.delete(reason=f"Removed by {ctx.author}")
                removed.append(name)
            except discord.HTTPException:
                failed += 1

        if not removed:
            await ctx.error("Couldn't remove any of those emojis.")
            return

        summary = f"Removed {len(removed)} emoji(s): {', '.join(f'`{n}`' for n in removed)}"
        if failed:
            summary += f" ({failed} failed)"
        await ctx.success(summary)

    @command_meta(
        category="Utility",
        description="Rename an emoji.",
        syntax=",emoji rename <emoji> <new_name>",
        examples=[",emoji rename <:pepe:123456789012345678> pepega"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="rename")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_rename(self, ctx: commands.Context, emoji: str, *, new_name: str):
        tokens = self._parse_emoji_tokens(emoji)
        if not tokens:
            await ctx.error("Provide a custom emoji from this server.")
            return

        _, _, emoji_id = tokens[0]
        target = discord.utils.get(ctx.guild.emojis, id=emoji_id)
        if target is None:
            await ctx.error("That emoji isn't from this server.")
            return

        clean_name = new_name.strip().replace(" ", "_")[:32]
        try:
            await target.edit(name=clean_name, reason=f"Renamed by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Couldn't rename that emoji. ({exc})")
            return

        await ctx.success(f"Renamed to `{clean_name}`.")

    @command_meta(
        category="Utility",
        description="Steal an emoji from another server and add it to this one.",
        syntax=",emoji steal [emoji] [name]",
        examples=[",emoji steal <:pepe:123456789012345678>", ",emoji steal <:pepe:123456789012345678> pepega"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="steal")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_steal(self, ctx: commands.Context, *, args: str):
        tokens = self._parse_emoji_tokens(args)
        if not tokens:
            await ctx.error("Provide a custom emoji to steal.")
            return

        animated, original_name, emoji_id = tokens[0]
        remaining = self.EMOJI_TOKEN_RE.sub("", args).strip()
        final_name = (remaining or original_name).replace(" ", "_")[:32]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._emoji_cdn_url(animated, emoji_id), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        await ctx.error("Couldn't download that emoji.")
                        return
                    image_bytes = await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
            await ctx.error("Couldn't download that emoji.")
            return

        try:
            new_emoji = await ctx.guild.create_custom_emoji(name=final_name, image=image_bytes, reason=f"Stolen by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Couldn't add that emoji. ({exc})")
            return

        await ctx.success(f"Added `{new_emoji.name}` to the server.")

    @command_meta(
        category="Utility",
        description="Steal multiple emojis from other servers at once.",
        syntax=",emoji stealmany <emojis>",
        examples=[",emoji stealmany <:pepe:123> <:kek:456>"],
        permissions=["Manage Guild Expressions"],
    )
    @emoji.command(name="stealmany")
    @has_permission_or_fake("manage_expressions")
    @commands.bot_has_permissions(manage_expressions=True)
    async def emoji_stealmany(self, ctx: commands.Context, *, emojis: str):
        tokens = self._parse_emoji_tokens(emojis)
        if not tokens:
            await ctx.error("Provide at least one custom emoji to steal.")
            return

        added, failed = [], 0
        for animated, original_name, emoji_id in tokens[:25]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self._emoji_cdn_url(animated, emoji_id), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            failed += 1
                            continue
                        image_bytes = await resp.read()
                new_emoji = await ctx.guild.create_custom_emoji(
                    name=original_name.replace(" ", "_")[:32], image=image_bytes, reason=f"Stolen by {ctx.author}"
                )
                added.append(new_emoji.name)
            except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError, discord.HTTPException):
                failed += 1

        if not added:
            await ctx.error("Couldn't steal any of those emojis.")
            return

        summary = f"Added {len(added)} emoji(s): {', '.join(f'`{n}`' for n in added)}"
        if failed:
            summary += f" ({failed} failed)"
        await ctx.success(summary)

    # ---------------------------------------------------------- funnel

    @command_meta(
        category="Information",
        description="See how many new members speak, and how many stay.",
        syntax=",funnel [days]",
        examples=[",funnel 10"],
        aliases=["retention", "joins"],
        require_args=False,
    )
    @commands.command(name="funnel", aliases=["retention", "joins"], with_app_command=False)
    @requires_premium("server")
    @commands.guild_only()
    async def funnel(self, ctx: commands.Context, days: int = 7):
        days = max(1, days)
        since = discord.utils.utcnow() - datetime.timedelta(days=days)

        async with get_session() as session:
            records = await funnel_repository.get_records_since(session, ctx.guild.id, since)

        total_joined = len(records)
        spoke = sum(1 for r in records if r.has_spoken)
        stayed = sum(1 for r in records if ctx.guild.get_member(r.user_id) is not None)

        spoke_pct = (spoke / total_joined * 100) if total_joined else 0
        stayed_pct = (stayed / total_joined * 100) if total_joined else 0

        description = (
            f"**Joined:** `{total_joined}`\n"
            f"**Spoke:** `{spoke}` (`{spoke_pct:.0f}%`)\n"
            f"**Stayed:** `{stayed}` (`{stayed_pct:.0f}%`)"
        )
        embed = discord.Embed(title=f"Funnel â last {days} day(s)", description=description)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- inviteinfo

    @command_meta(
        category="Information",
        description="Shows information about a Discord invite.",
        syntax=",inviteinfo <invite>",
        examples=[",inviteinfo discord.gg/example", ",inviteinfo example"],
        permissions=["Manage Guild"],
        aliases=["ii"],
        require_args=False,
    )
    @commands.command(name="inviteinfo", aliases=["ii"], with_app_command=False)
    @has_permission_or_fake("manage_guild")
    async def inviteinfo(self, ctx: commands.Context, invite: str = None):
        if not invite:
            embed = discord.Embed(
                description=f"â ï¸ {ctx.author.mention}: You need to provide `invite`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        code = invite.strip().rstrip("/").split("/")[-1]

        try:
            inv = await self.bot.fetch_invite(code, with_counts=True, with_expiration=True)
        except discord.NotFound:
            await ctx.error("That invite doesn't exist or has expired.")
            return
        except discord.HTTPException:
            await ctx.error("Couldn't fetch that invite.")
            return

        created_display = "Unknown"
        if inv.created_at:
            created_display = (
                f"{discord.utils.format_dt(inv.created_at, style='R')} "
                f"({discord.utils.format_dt(inv.created_at, style='F')})"
            )

        expires_display = "Never" if inv.expires_at is None else discord.utils.format_dt(inv.expires_at, style="R")

        description = (
            f"**Created** {created_display}\n\n"
            f"**Invite**\n"
            f"> Code: {inv.code}\n"
            f"> Expires: {expires_display}\n\n"
            f"**Server**\n"
            f"> Members: `{inv.approximate_member_count if inv.approximate_member_count is not None else 'Unknown'}`\n"
            f"> Online: `{inv.approximate_presence_count if inv.approximate_presence_count is not None else 'Unknown'}`"
        )
        embed = discord.Embed(description=description)
        guild_name = inv.guild.name if inv.guild else "Unknown Server"
        guild_icon = inv.guild.icon.url if inv.guild and inv.guild.icon else None
        embed.set_author(name=guild_name, icon_url=guild_icon)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- reminder

    @command_meta(
        category="Utility",
        description="Set and manage personal reminders.",
        syntax=",reminder <duration> [description]",
        examples=[",reminder 1h", ",reminder 1h Check the oven"],
        aliases=["remind", "remindme"],
        require_args=False,
    )
    @commands.group(name="reminder", aliases=["remind", "remindme"], invoke_without_command=True, with_app_command=False)
    async def reminder(self, ctx: commands.Context, duration: Duration = None, *, description: str = None):
        if duration is None:
            embed = discord.Embed(
                description=f"â ï¸ {ctx.author.mention}: You need to provide `duration`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        remind_at = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
        async with get_session() as session:
            await reminder_repository.create_reminder(
                session, ctx.author.id, ctx.channel.id, ctx.guild.id if ctx.guild else None, description, remind_at,
            )

        await ctx.success(f"I'll remind you {discord.utils.format_dt(remind_at, style='R')}.")

    @command_meta(
        category="Utility",
        description="List your reminders.",
        syntax=",reminder list",
        examples=[",reminder list"],
        require_args=False,
    )
    @reminder.command(name="list")
    async def reminder_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await reminder_repository.get_for_user(session, ctx.author.id)

        if not rows:
            await ctx.info("You have no reminders.")
            return

        lines = [
            f"`{i}` {r.description or 'No description'} â {discord.utils.format_dt(r.remind_at, style='R')}"
            for i, r in enumerate(rows, start=1)
        ]
        embed = discord.Embed(title="Your Reminders", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Remove a reminder by its number in `reminder list`.",
        syntax=",reminder remove <index>",
        examples=[",reminder remove 2"],
    )
    @reminder.command(name="remove")
    async def reminder_remove(self, ctx: commands.Context, index: int):
        async with get_session() as session:
            rows = await reminder_repository.get_for_user(session, ctx.author.id)
            if not (1 <= index <= len(rows)):
                await ctx.error(f"No reminder at index `{index}`.")
                return
            target = rows[index - 1]
            await reminder_repository.delete_reminder(session, target.id)

        await ctx.success(f"Removed reminder `{index}`.")

    # ---------------------------------------------------------- caption

    @command_meta(
        category="Utility",
        description="Adds a meme-style caption above an image or GIF - attach a file directly, or reply to a message that has one.",
        syntax=",caption <text> [file]",
        examples=[",caption when the code compiles first try"],
        permissions=["Attach Files", "Embed Links"],
        aliases=["cap"],
        require_args=False,
    )
    @commands.command(name="caption", aliases=["cap"], with_app_command=False)
    @has_permission_or_fake("attach_files")
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def caption(self, ctx: commands.Context, image: discord.Attachment | None = None, *, text: str = None):
        if image is None and ctx.message.reference is not None:
            resolved = ctx.message.reference.resolved
            if isinstance(resolved, discord.Message) and resolved.attachments:
                image = resolved.attachments[0]

        if image is None or not text:
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}: Attach an image or GIF to caption."))
            return

        image_bytes = await image.read()
        buffer = caption_service.build_caption_image(image_bytes, text)
        if buffer is None:
            await ctx.error("Couldn't process that image.")
            return

        file = discord.File(buffer, filename="caption.png")
        embed = discord.Embed()
        embed.set_image(url="attachment://caption.png")
        await ctx.send(embed=embed, file=file)

    # ---------------------------------------------------------- reverse

    @command_meta(
        category="Information",
        description="Reverse image search using Google.",
        syntax=",reverse [image]",
        examples=[",reverse"],
        aliases=["reversesearch"],
        require_args=False,
    )
    @commands.command(name="reverse", aliases=["reversesearch"], with_app_command=False)
    async def reverse(self, ctx: commands.Context, image: discord.Attachment | None = None):
        if image is None and ctx.message.reference is not None:
            resolved = ctx.message.reference.resolved
            if isinstance(resolved, discord.Message) and resolved.attachments:
                image = resolved.attachments[0]

        if image is None:
            await ctx.error(f"{ctx.author.mention}: Please attach an image to search")
            return

        from urllib.parse import quote
        search_url = f"https://www.google.com/searchbyimage?image_url={quote(image.url, safe='')}"

        rgb = await color_service.get_average_color(image.url)
        color = discord.Color.from_rgb(*rgb) if rgb else discord.Color.default()

        description = (
            f"**Results**\n"
            f"> Google Reverse Image Search: [Click here]({search_url})\n\n"
            f"Source: Google"
        )
        embed = discord.Embed(title="Reverse Image Search", description=description, color=color)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- pin

    @command_meta(
        category="Utility",
        description="Pins a message. With no argument, pins the message sent right before this command.",
        syntax=",pin [message]",
        examples=[",pin", ",pin 123456789012345678"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @commands.command(name="pin", with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def pin(self, ctx: commands.Context, message: discord.Message = None):
        target = message

        if target is None:
            async for msg in ctx.channel.history(limit=2, before=ctx.message):
                target = msg
                break

        if target is None:
            await ctx.error("Couldn't find a message to pin.")
            return

        try:
            await target.pin(reason=f"Pinned by {ctx.author}")
        except discord.HTTPException:
            await ctx.error("Couldn't pin that message - it may already be pinned, or the pin limit was reached.")

    # ---------------------------------------------------------- customize

    @command_meta(
        category="Server",
        description="Customize how the bot appears in this server.",
        syntax=",customize",
        examples=[],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.group(name="customize", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    @commands.guild_only()
    async def customize(self, ctx: commands.Context):
        await send_help(ctx, "customize")

    @customize.command(name="help")
    async def customize_help(self, ctx: commands.Context):
        await send_help(ctx, "customize")

    @staticmethod
    async def _resolve_image_bytes(ctx: commands.Context, image: str = None) -> bytes | None:
        """Accepts a direct attachment on the invoking message, or a URL
        string. Returns None if neither was given."""
        if ctx.message.attachments:
            return await ctx.message.attachments[0].read()
        if image:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
                pass
        return None

    @command_meta(
        category="Server",
        description="Set the bot´s nickname in this server.",
        syntax=",customize name [name]",
        examples=[",customize name Blaid", ",customize name"],
        permissions=["Administrator"],
        require_args=False,
    )
    @customize.command(name="name")
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    async def customize_name(self, ctx: commands.Context, *, name: str = None):
        try:
            await ctx.guild.me.edit(nick=name)
        except discord.Forbidden:
            await ctx.error("I don't have permission to change my own nickname in this server.")
            return
        except discord.HTTPException as exc:
            await ctx.error(f"Couldn't update my name. ({exc})")
            return

        await ctx.success(f"Set my name for this server to `{name}`." if name else "Reset my name for this server.")

    @command_meta(
        category="Server",
        description="Set the bot´s server avatar (attach an image or pass a URL; omit to clear).",
        syntax=",customize avatar [image or url]",
        examples=[",customize avatar", ",customize avatar https://example.com/image.png"],
        permissions=["Administrator"],
        require_args=False,
    )
    @customize.command(name="avatar")
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    async def customize_avatar(self, ctx: commands.Context, *, image: str = None):
        image_bytes = await self._resolve_image_bytes(ctx, image)

        try:
            await ctx.guild.me.edit(avatar=image_bytes)
        except TypeError:
            await ctx.error(
                "This bot's discord.py version doesn't support per-server avatars yet, even though Discord added "
                "the feature - the library needs to catch up. Nothing was changed."
            )
            return
        except discord.Forbidden:
            await ctx.error("I don't have permission to change my avatar in this server.")
            return
        except discord.HTTPException as exc:
            await ctx.error(f"Discord rejected that avatar change. ({exc})")
            return

        await ctx.success("Updated my avatar for this server." if image_bytes else "Reset my avatar for this server.")

    @command_meta(
        category="Server",
        description="Set the bot´s server banner (attach an image or pass a URL; omit to clear).",
        syntax=",customize banner [image or url]",
        examples=[",customize banner", ",customize banner https://example.com/image.png"],
        permissions=["Administrator"],
        require_args=False,
    )
    @customize.command(name="banner")
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    async def customize_banner(self, ctx: commands.Context, *, image: str = None):
        image_bytes = await self._resolve_image_bytes(ctx, image)

        try:
            await ctx.guild.me.edit(banner=image_bytes)
        except TypeError:
            await ctx.error(
                "This bot's discord.py version doesn't support per-server banners yet, even though Discord added "
                "the feature - the library needs to catch up. Nothing was changed."
            )
            return
        except discord.Forbidden:
            await ctx.error("I don't have permission to change my banner in this server.")
            return
        except discord.HTTPException as exc:
            await ctx.error(f"Discord rejected that banner change. ({exc})")
            return

        await ctx.success("Updated my banner for this server." if image_bytes else "Reset my banner for this server.")

    @command_meta(
        category="Server",
        description="Set the bot´s About Me in this server (omit to clear).",
        syntax=",customize bio [bio]",
        examples=[",customize bio Your friendly server assistant.", ",customize bio"],
        permissions=["Administrator"],
        require_args=False,
    )
    @customize.command(name="bio")
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    async def customize_bio(self, ctx: commands.Context, *, bio: str = None):
        try:
            await ctx.guild.me.edit(bio=bio)
        except TypeError:
            await ctx.error(
                "This bot's discord.py version doesn't support per-server bios yet, even though Discord added "
                "the feature - the library needs to catch up. Nothing was changed."
            )
            return
        except discord.Forbidden:
            await ctx.error("I don't have permission to change my bio in this server.")
            return
        except discord.HTTPException as exc:
            await ctx.error(f"Discord rejected that bio change. ({exc})")
            return

        await ctx.success("Updated my bio for this server." if bio else "Reset my bio for this server.")

    @command_meta(
        category="Server",
        description="Reset all bot customization in this server.",
        syntax=",customize reset",
        examples=[",customize reset"],
        permissions=["Administrator"],
        require_args=False,
    )
    @customize.command(name="reset")
    @commands.has_permissions(administrator=True)
    @requires_premium("customize")
    async def customize_reset(self, ctx: commands.Context):
        errors = []
        try:
            await ctx.guild.me.edit(nick=None)
        except discord.HTTPException as exc:
            errors.append(f"name ({exc})")
        try:
            await ctx.guild.me.edit(avatar=None)
        except (TypeError, discord.HTTPException) as exc:
            errors.append(f"avatar ({exc})")
        try:
            await ctx.guild.me.edit(banner=None)
        except (TypeError, discord.HTTPException) as exc:
            errors.append(f"banner ({exc})")
        try:
            await ctx.guild.me.edit(bio=None)
        except (TypeError, discord.HTTPException) as exc:
            errors.append(f"bio ({exc})")

        if errors:
            await ctx.error(f"Reset most things, but ran into issues with: {', '.join(errors)}")
        else:
            await ctx.success("Reset my name, avatar, banner, and bio for this server.")

    # ---------------------------------------------------------- imageonly

    @command_meta(
        category="Utility",
        description="Toggle image-only mode in a channel (deletes messages with no attachment).",
        syntax=",imageonly [channel]",
        examples=[",imageonly #channel"],
        permissions=["Manage Guild"],
        aliases=["imgonly"],
        require_args=False,
    )
    @commands.command(name="imageonly", aliases=["imgonly"], with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def imageonly(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel

        async with get_session() as session:
            already = await imageonly_repository.is_enabled(session, channel.id)
            if already:
                await imageonly_repository.disable(session, channel.id)
            else:
                await imageonly_repository.enable(session, ctx.guild.id, channel.id)

        if already:
            await ctx.success(f"{ctx.author.mention}: Disabled image-only mode in {channel.mention}")
        else:
            await ctx.success(
                f"{ctx.author.mention}: Enabled image-only mode in {channel.mention}\n"
                f"-# Messages without an attachment will be removed"
            )

    # ---------------------------------------------------------- boomer

    @command_meta(
        category="Information",
        description="Shows the oldest Discord account in this server.",
        syntax=",boomer",
        examples=[",boomer"],
        require_args=False,
    )
    @commands.command(name="boomer", with_app_command=False)
    @commands.guild_only()
    async def boomer(self, ctx: commands.Context):
        oldest = min(ctx.guild.members, key=lambda m: m.created_at)
        timestamp = int(oldest.created_at.timestamp())

        description = (
            f"**{oldest} ({oldest.id})**\n\n"
            f"> Created: <t:{timestamp}:F> (<t:{timestamp}:R>)"
        )
        embed = discord.Embed(title=f"Oldest member in {ctx.guild.name}", description=description)
        embed.set_thumbnail(url=oldest.display_avatar.url)
        embed.set_author(name=ctx.guild.name)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- channelinfo

    @command_meta(
        category="Information",
        description="Shows information about a channel.",
        syntax=",channelinfo [channel]",
        examples=[",channelinfo", ",channelinfo #general"],
        require_args=False,
    )
    @commands.command(name="channelinfo", with_app_command=False)
    @commands.guild_only()
    async def channelinfo(self, ctx: commands.Context, channel: discord.TextChannel | discord.VoiceChannel = None):
        channel = channel or ctx.channel
        timestamp = int(channel.created_at.timestamp())

        is_voice = isinstance(channel, discord.VoiceChannel)
        category_label = "Voice channels" if is_voice else "Text channels"
        nsfw_label = "Yes" if getattr(channel, "nsfw", False) else "No"
        slowmode = getattr(channel, "slowmode_delay", 0) or 0

        description = (
            f"**Created**\n"
            f"<t:{timestamp}:F> (<t:{timestamp}:R>)\n\n"
            f"**Details**\n"
            f"> NSFW: {nsfw_label}\n"
            f"> Category: {category_label}\n"
            f"> Slowmode: `{slowmode}`"
        )

        embed = discord.Embed(title=f"#{channel.name} - ({channel.id})", description=description)
        embed.set_author(name=ctx.guild.name)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- firstmessage

    @command_meta(
        category="Information",
        description="Jumps to the first message ever sent in a channel.",
        syntax=",firstmessage [channel]",
        examples=[",firstmessage", ",firstmessage #general"],
        aliases=["firstmsg"],
        require_args=False,
    )
    @commands.command(name="firstmessage", aliases=["firstmsg"], with_app_command=False)
    @requires_premium("server")
    @commands.guild_only()
    async def firstmessage(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel

        messages = [message async for message in channel.history(limit=1, oldest_first=True)]
        if not messages:
            await ctx.error(f"{channel.mention} has no messages.")
            return

        first = messages[0]
        embed = discord.Embed(description=f"Jump to {first.author.mention}'s [first message]({first.jump_url})")
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- invite

    @command_meta(
        category="Information",
        description="Sends an invite link to add Blaid to your server.",
        syntax=",invite",
        examples=[",invite"],
        aliases=["inv"],
        require_args=False,
    )
    @commands.command(name="invite", aliases=["inv"], with_app_command=False)
    async def invite(self, ctx: commands.Context):
        view = InviteView(self.bot)
        await ctx.send(view=view)

    # ---------------------------------------------------------- snipe

    @command_meta(
        category="Utility",
        description="Shows the most recently deleted message in this channel (or the Nth most recent, if given).",
        syntax=",snipe [number]",
        examples=[",snipe", ",snipe 2"],
        permissions=["Manage Messages"],
        aliases=["s"],
        require_args=False,
    )
    @commands.command(name="snipe", aliases=["s"], with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.guild_only()
    async def snipe(self, ctx: commands.Context, number: int = 1):
        entry, total = snipe_service.get_deleted(ctx.channel.id, number)
        if entry is None:
            await ctx.info("Nothing to snipe here.")
            return

        embed = discord.Embed(
            description=f"**{entry.author_name}** said this <t:{int(entry.timestamp.timestamp())}:R>:\n{entry.content}"
        )
        embed.set_footer(text=f"{entry.author_name} â¢ {number}/{total} deleted messages", icon_url=entry.author_icon)
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Shows the most recently edited message in this channel (or the Nth most recent, if given).",
        syntax=",editsnipe [number]",
        examples=[",editsnipe", ",editsnipe 2"],
        permissions=["Manage Messages"],
        aliases=["es"],
        require_args=False,
    )
    @commands.command(name="editsnipe", aliases=["es"], with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.guild_only()
    async def editsnipe(self, ctx: commands.Context, number: int = 1):
        entry, total = snipe_service.get_edited(ctx.channel.id, number)
        if entry is None:
            await ctx.info("Nothing to snipe here.")
            return

        embed = discord.Embed(
            description=(
                f"**{entry.author_name}** edited this message <t:{int(entry.timestamp.timestamp())}:R>:\n\n"
                f"**Before**\n{entry.before}\n\n**After**\n{entry.after}"
            )
        )
        embed.set_footer(text=f"{entry.author_name} â¢ {number}/{total} edited messages", icon_url=entry.author_icon)
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Shows the most recently removed reaction in this channel (or the Nth most recent, if given).",
        syntax=",reactionsnipe [number]",
        examples=[",reactionsnipe", ",reactionsnipe 2"],
        permissions=["Manage Messages"],
        aliases=["rs"],
        require_args=False,
    )
    @commands.command(name="reactionsnipe", aliases=["rs"], with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.guild_only()
    async def reactionsnipe(self, ctx: commands.Context, number: int = 1):
        entry, total = snipe_service.get_reaction(ctx.channel.id, number)
        if entry is None:
            await ctx.info("Nothing to snipe here.")
            return

        embed = discord.Embed(
            description=(
                f"**{entry.reactor_name}** removed {entry.emoji} from a message by "
                f"**{entry.message_author_name}** <t:{int(entry.timestamp.timestamp())}:R>"
            )
        )
        embed.set_footer(text=f"{entry.reactor_name} â¢ {number}/{total} removed reactions", icon_url=entry.reactor_icon)
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Clears all snipe data (deleted/edited messages, removed reactions) for this channel.",
        syntax=",clearsnipe",
        examples=[",clearsnipe"],
        permissions=["Manage Messages"],
        aliases=["cs"],
        require_args=False,
    )
    @commands.command(name="clearsnipe", aliases=["cs"], with_app_command=False)
    @has_permission_or_fake("manage_messages")
    @commands.guild_only()
    async def clearsnipe(self, ctx: commands.Context):
        snipe_service.clear_channel(ctx.channel.id)
        await ctx.message.add_reaction("â")

    # ---------------------------------------------------------- ,guild

    @command_meta(
        category="Information",
        description="Shows information about this server - banner, icon, splash, and stats.",
        syntax=",guild",
        examples=[],
        aliases=["server"],
        require_args=False,
    )
    @commands.group(name="guild", aliases=["server"], invoke_without_command=True, with_app_command=False)
    @commands.guild_only()
    async def guild(self, ctx: commands.Context):
        await send_help(ctx, "guild")

    @guild.command(name="help")
    async def guild_help(self, ctx: commands.Context):
        await send_help(ctx, "guild")

    @command_meta(
        category="Information",
        description="Shows a server's banner. Optionally give another server's ID, if the bot is also in that server.",
        syntax=",guild banner [server_id]",
        examples=[",guild banner", ",guild banner 123456789012345678"],
        require_args=False,
    )
    @guild.command(name="banner")
    async def guild_banner(self, ctx: commands.Context, server_id: int = None):
        target = self.bot.get_guild(server_id) if server_id else ctx.guild
        if target is None:
            await ctx.error("I'm not in a server with that ID.")
            return
        if target.banner is None:
            await ctx.info(f"**{target.name}** has no banner set.")
            return
        embed = discord.Embed(title=f"{target.name}'s Banner")
        embed.set_image(url=target.banner.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a server's icon. Optionally give another server's ID, if the bot is also in that server.",
        syntax=",guild icon [server_id]",
        examples=[",guild icon", ",guild icon 123456789012345678"],
        require_args=False,
    )
    @guild.command(name="icon")
    async def guild_icon(self, ctx: commands.Context, server_id: int = None):
        target = self.bot.get_guild(server_id) if server_id else ctx.guild
        if target is None:
            await ctx.error("I'm not in a server with that ID.")
            return
        if target.icon is None:
            await ctx.info(f"**{target.name}** has no icon set.")
            return
        embed = discord.Embed(title=f"{target.name}'s Icon")
        embed.set_image(url=target.icon.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows a server's invite splash image. Optionally give another server's ID, if the bot is also in that server.",
        syntax=",guild splash [server_id]",
        examples=[",guild splash", ",guild splash 123456789012345678"],
        require_args=False,
    )
    @guild.command(name="splash")
    async def guild_splash(self, ctx: commands.Context, server_id: int = None):
        target = self.bot.get_guild(server_id) if server_id else ctx.guild
        if target is None:
            await ctx.error("I'm not in a server with that ID.")
            return
        if target.splash is None:
            await ctx.info(f"**{target.name}** has no invite splash set.")
            return
        embed = discord.Embed(title=f"{target.name}'s Splash")
        embed.set_image(url=target.splash.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Information",
        description="Shows this server's stats - total members, and today's joins/leaves.",
        syntax=",guild stats",
        examples=[",guild stats"],
        require_args=False,
    )
    @guild.command(name="stats")
    @commands.guild_only()
    async def guild_stats(self, ctx: commands.Context):
        async with get_session() as session:
            joins, leaves = await guild_stats_repository.get_today(session, ctx.guild.id)

        embed = discord.Embed(
            title=f"Stats for {ctx.guild.name}",
            description=(
                f"> **Total Members:** `{ctx.guild.member_count}`\n\n"
                f"> **Joins:** `{joins}`\n\n"
                f"> **Leaves:** `{leaves}`"
            ),
        )
        embed.set_author(name=ctx.guild.name)
        await ctx.send(embed=embed)

    @command_meta(
        category="Utility",
        description="Previews the message sent to a server (and DMed to whoever added the bot) when Blaid joins a new server. Bot owner only.",
        syntax=",previewjoin",
        examples=[",previewjoin"],
        permissions=["Bot Owner"],
        require_args=False,
    )
    @commands.command(name="previewjoin", with_app_command=False)
    @commands.is_owner()
    async def previewjoin(self, ctx: commands.Context):
        from services.onboarding_service import build_join_embed, build_join_view
        embed = build_join_embed(self.bot, ctx.guild)
        view = build_join_view()
        await ctx.send(embed=embed, view=view)

    @command_meta(
        category="Utility",
        description="Syncs slash commands with Discord - run this once after adding/changing commands. Bot owner only.",
        syntax=",sync [scope]",
        examples=[",sync", ",sync global"],
        permissions=["Bot Owner"],
        require_args=False,
    )
    @commands.command(name="sync", with_app_command=False)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, scope: str = "guild"):
        if scope.lower() == "global":
            synced = await self.bot.tree.sync()
            await ctx.success(f"Synced {len(synced)} command(s) globally (can take up to an hour to show up everywhere).")
            return

        if ctx.guild is None:
            await ctx.error("Run `,sync global` in DMs, or run this in a server for an instant per-guild sync.")
            return

        self.bot.tree.copy_global_to(guild=ctx.guild)
        synced = await self.bot.tree.sync(guild=ctx.guild)
        await ctx.success(f"Synced {len(synced)} command(s) to this server (shows up immediately).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
