"""
Ticket business logic.

Everything that changes a ticket's state - claiming, closing, reopening,
deleting, moving - goes through the do_* functions here, whether it was
triggered by a text command or a control-panel button. That's the same
"one implementation, shared by every entry point" pattern used for
VoiceMaster and moderation elsewhere in Blade.
"""

from __future__ import annotations

import asyncio
import datetime
import os

import discord

from core.helpers import format_duration
from database.database import get_session
from database.ticket_options_models import BUTTON_ACTIONS
from database.tickets_models import Ticket, TicketPanel
from repositories import ticket_options_repository, ticket_repository

TRANSCRIPT_DIR = "data/transcripts"

_BUTTON_STYLE_MAP = {
    "blue": discord.ButtonStyle.primary,
    "gray": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}

_DEFAULT_MESSAGES = {
    # {embed} script syntax so these render as embeds by default. The
    # greeting alone puts the ping in {content} (outside the embed),
    # since mentions inside an embed don't reliably notify.
    "greeting": (
        "{content: {ticket.author.mention}}\n"
        "{embed}\n"
        "{color: #5865F2}\n"
        "{title: Ticket }\n"
        "{description: Thank you for contacting support. Please explain your issue and a staff member will assist you shortly.}\n"
        "{footer: Ticket #{ticket.case} && {guild.icon}}"
    ),
    "claim": "{embed}\n{description: {user.mention} has claimed this ticket.}",
    "move": "{embed}\n{description: This ticket has been moved.}",
    "close": "{embed}\n{description: This ticket has been closed by {user.mention}.}",
    "reopen": "{embed}\n{description: This ticket has been reopened by {user.mention}.}",
    "auto_close": "{embed}\n{description: This ticket was automatically closed.}",
    "auto_delete": "{embed}\n{description: This ticket has been automatically deleted.}",
    "inactivity": "{embed}\n{description: This ticket has been closed due to inactivity.}",
    "required_roles": "You don't have the required role(s) to open this ticket type.",
}

# ticket_id -> asyncio.Task, for auto-close/auto-delete (DB-persisted
# deadlines, resumed on startup - see resume_ticket_timers).
_auto_close_tasks: dict[int, asyncio.Task] = {}
_auto_delete_tasks: dict[int, asyncio.Task] = {}

# channel_id -> asyncio.Task, for the inactivity timer. NOT persisted
# across restarts (documented gap) - a restart simply loses the
# countdown until the next message in the channel restarts it.
_inactivity_tasks: dict[int, asyncio.Task] = {}


# ---------------------------------------------------------- panel views (open flow)

class TicketPanelView(discord.ui.View):
    """Persistent view attached to a panel message that has no options
    configured - the simple single-button flow. `panel_id` is baked
    into the button's custom_id so it survives bot restarts."""

    def __init__(self, panel_id: int, button_label: str = "Open Ticket"):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        button = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.primary,
            custom_id=f"blade_ticket_open:{panel_id}",
        )
        button.callback = self._open_ticket
        self.add_item(button)

    async def _open_ticket(self, interaction: discord.Interaction) -> None:
        await open_ticket(interaction, self.panel_id)


class OptionButtonView(discord.ui.View):
    """Persistent view for a panel with exactly one option configured -
    still a single button, but styled/labelled from the option."""

    def __init__(self, panel_id: int, option) -> None:
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label=option.label,
            emoji=option.emoji or None,
            style=_BUTTON_STYLE_MAP.get(option.button_style, discord.ButtonStyle.primary),
            custom_id=f"blade_ticket_option_open:{panel_id}:{option.id}",
        )
        button.callback = self._open
        self.add_item(button)
        self.option_id = option.id

    async def _open(self, interaction: discord.Interaction) -> None:
        await open_ticket_with_option(interaction, self.option_id)


class OptionSelectPanelView(discord.ui.View):
    """Persistent view for a panel with 2+ options - a single dropdown
    listing every option."""

    def __init__(self, panel_id: int, options: list) -> None:
        super().__init__(timeout=None)
        select_options = [
            discord.SelectOption(label=o.label, value=str(o.id), emoji=o.emoji or None)
            for o in options[:25]
        ]
        select = discord.ui.Select(
            placeholder="Select a ticket type...",
            options=select_options,
            custom_id=f"blade_ticket_panelselect:{panel_id}",
        )
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        option_id = int(self._select.values[0])
        await open_ticket_with_option(interaction, option_id)


async def build_panel_view(panel_id: int) -> discord.ui.View:
    """Builds the correct view for a panel's current state - a plain
    button if it has no options, a single styled button if it has
    exactly one, or a dropdown if it has several. Call this any time a
    panel is (re)sent, and again on every bot startup so persistent
    views stay in sync with the panel's current option list."""
    async with get_session() as session:
        panel = await ticket_repository.get_panel(session, panel_id)
        options = await ticket_options_repository.get_options_for_panel(session, panel_id)

    if not options:
        return TicketPanelView(panel_id, panel.button_label if panel else "Open Ticket")
    if len(options) == 1:
        return OptionButtonView(panel_id, options[0])
    return OptionSelectPanelView(panel_id, options)


async def open_ticket(interaction: discord.Interaction, panel_id: int) -> None:
    """The simple, no-options flow. Now shares the exact same creation
    logic as the options-aware flow (embed greeting, control buttons,
    category fallback) - just with option=None, so a plain panel with
    zero configured options still gets sensible defaults instead of a
    bare text message."""
    guild = interaction.guild
    async with get_session() as session:
        panel = await ticket_repository.get_panel(session, panel_id)
        blacklisted = await ticket_repository.is_blacklisted(session, guild.id, interaction.user.id)

    if panel is None:
        await interaction.response.send_message("This ticket panel no longer exists.", ephemeral=True)
        return

    if blacklisted:
        await interaction.response.send_message("You are blacklisted from opening tickets.", ephemeral=True)
        return

    support_role_ids = [panel.support_role_id] if panel.support_role_id else []
    await _create_ticket_channel(interaction, panel=panel, option=None, support_role_ids=support_role_ids, form_answers=None)


# ---------------------------------------------------------- options-aware open flow

async def open_ticket_with_option(interaction: discord.Interaction, option_id: int) -> None:
    """The options-aware flow: checks the blacklist and required roles,
    then either shows the option's form (if it has one) before creating
    the channel, or creates it immediately."""
    guild = interaction.guild
    member = interaction.user

    async with get_session() as session:
        option = await ticket_options_repository.get_option(session, option_id)
        if option is None:
            await interaction.response.send_message("This ticket option no longer exists.", ephemeral=True)
            return

        panel = await ticket_repository.get_panel(session, option.panel_id)
        blacklisted = await ticket_repository.is_blacklisted(session, guild.id, member.id)
        required_role_ids = await ticket_options_repository.get_required_roles(session, option_id)
        support_role_ids = await ticket_options_repository.get_support_roles(session, option_id)

    if blacklisted:
        await interaction.response.send_message("You are blacklisted from opening tickets.", ephemeral=True)
        return

    if required_role_ids:
        member_role_ids = {r.id for r in member.roles}
        has_access = (
            set(required_role_ids).issubset(member_role_ids)
            if option.require_all_roles
            else bool(member_role_ids & set(required_role_ids))
        )
        if not has_access:
            async with get_session() as session:
                denial_text = await ticket_options_repository.get_message(session, option_id, "required_roles")
            await interaction.response.send_message(
                denial_text or _DEFAULT_MESSAGES["required_roles"], ephemeral=True
            )
            return

    if option.form_id:
        from repositories import ticket_forms_repository
        async with get_session() as session:
            form = await ticket_forms_repository.get_form(session, option.form_id)
            fields = await ticket_forms_repository.get_fields(session, option.form_id)
        await interaction.response.send_modal(TicketFormModal(panel, option, form, fields, support_role_ids))
        return

    await _create_ticket_channel(interaction, panel=panel, option=option, support_role_ids=support_role_ids, form_answers=None)


class TicketFormModal(discord.ui.Modal):
    """Dynamically built from a form's configured fields. Discord modals
    cap out at 5 components, so only the first 5 fields are shown.

    KNOWN GAP: the plain "select" field type has no stored option list
    in the schema yet (role/user/channel selects auto-populate from the
    server so those work fully) - it falls back to a short text field
    for now rather than silently misbehaving.
    """

    def __init__(self, panel, option, form, fields: list, support_role_ids: list[int]):
        super().__init__(title=(form.modal_title if form else "Ticket Form")[:45])
        self.panel = panel
        self.option = option
        self.support_role_ids = support_role_ids
        self.inputs: list[tuple] = []

        for field in fields[:5]:
            if field.field_type == "long_text":
                component = discord.ui.TextInput(
                    label=field.label[:45], style=discord.TextStyle.paragraph,
                    required=field.required, max_length=1000,
                )
                self.add_item(component)
            elif field.field_type == "checkbox":
                component = discord.ui.Checkbox(custom_id=f"field_{field.id}")
                self.add_item(discord.ui.Label(text=field.label, description=field.description, component=component))
            elif field.field_type == "role_select":
                component = discord.ui.RoleSelect(min_values=1 if field.required else 0, max_values=1)
                self.add_item(discord.ui.Label(text=field.label, component=component))
            elif field.field_type == "user_select":
                component = discord.ui.UserSelect(min_values=1 if field.required else 0, max_values=1)
                self.add_item(discord.ui.Label(text=field.label, component=component))
            elif field.field_type == "channel_select":
                component = discord.ui.ChannelSelect(min_values=1 if field.required else 0, max_values=1)
                self.add_item(discord.ui.Label(text=field.label, component=component))
            else:  # short_text, and "select" until it has a stored option list
                component = discord.ui.TextInput(label=field.label[:45], required=field.required, max_length=200)
                self.add_item(component)

            self.inputs.append((field, component))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = []
        for field, component in self.inputs:
            if isinstance(component, discord.ui.Checkbox):
                value = "Yes" if component.value else "No"
            elif isinstance(component, (discord.ui.RoleSelect, discord.ui.UserSelect, discord.ui.ChannelSelect)):
                value = ", ".join(str(v) for v in component.values) if component.values else "None"
            else:
                value = str(component)
            answers.append((field.label, value))

        await _create_ticket_channel(interaction, panel=self.panel, option=self.option, support_role_ids=self.support_role_ids, form_answers=answers)


async def _create_ticket_channel(
    interaction: discord.Interaction, *, panel, option, support_role_ids: list[int], form_answers: list[tuple] | None
) -> None:
    """Shared by both the simple (option=None) and options-aware flows.
    Every default (embed greeting, control buttons, category fallback)
    applies regardless of whether an option is configured."""
    from core.script_parser import parse_script
    from core.variables import resolve_variables

    guild = interaction.guild
    member = interaction.user
    bot = interaction.client

    category = None
    if option is not None and option.default_category_id:
        category = guild.get_channel(option.default_category_id)
    if category is None and panel.category_id:
        category = guild.get_channel(panel.category_id)
    if category is None:
        # Nothing configured anywhere - default to whatever category the
        # panel's own channel is in.
        panel_channel = guild.get_channel(panel.channel_id)
        if panel_channel is not None:
            category = panel_channel.category

    async with get_session() as session:
        case_number = await ticket_repository.next_case_number(session, guild.id)

    name_format = option.channel_name_format if option is not None else "{ticket.case}-{ticket.author.name}"
    name = resolve_variables(
        name_format, guild=guild, member=member,
        ticket_case=case_number, ticket_creator=member,
    )[:100]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for role_id in support_role_ids:
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel = await guild.create_text_channel(
        name=name, category=category, overwrites=overwrites, reason=f"Ticket opened by {member}"
    )

    greeting = None
    greeting_dm = None
    if option is not None:
        async with get_session() as session:
            greeting = await ticket_options_repository.get_message(session, option.id, "greeting")
            greeting_dm = await ticket_options_repository.get_message(session, option.id, "greeting_dm")

    async with get_session() as session:
        ticket = await ticket_repository.create_ticket(
            session, guild_id=guild.id, channel_id=channel.id, panel_id=panel.id,
            option_id=option.id if option is not None else None, creator_id=member.id, case_number=case_number,
        )

    greeting_text = resolve_variables(
        greeting or _DEFAULT_MESSAGES["greeting"],
        guild=guild, member=member, channel=channel,
        ticket_case=case_number, ticket_creator=member, ticket_status="open",
    )
    parsed = parse_script(greeting_text)
    if parsed.embed is not None or parsed.content:
        await channel.send(content=parsed.content, embed=parsed.embed)
    else:
        await channel.send(greeting_text)

    if form_answers:
        answers_embed = discord.Embed(title="Form Responses")
        for label, value in form_answers:
            answers_embed.add_field(name=label, value=value or "—", inline=False)
        await channel.send(embed=answers_embed)

    if greeting_dm:
        resolved_dm = resolve_variables(
            greeting_dm, guild=guild, member=member, ticket_case=case_number,
            ticket_creator=member, ticket_status="open",
        )
        parsed_dm = parse_script(resolved_dm)
        try:
            if parsed_dm.embed is not None or parsed_dm.content:
                await member.send(content=parsed_dm.content, embed=parsed_dm.embed)
            else:
                await member.send(resolved_dm)
        except discord.HTTPException:
            pass

    # Control panel - styled Claim/Close/Reopen/Delete buttons from
    # this option's Button UX config (or sensible defaults when there's
    # no option at all).
    button_configs = {}
    if option is not None:
        async with get_session() as session:
            for action in BUTTON_ACTIONS:
                cfg = await ticket_options_repository.get_button_config(session, option.id, action)
                if cfg is not None:
                    button_configs[action] = cfg
    control_view = TicketControlView(ticket.id, button_configs)
    control_message = await channel.send(view=control_view)

    auto_close_at = None
    if option is not None and option.auto_close_timer:
        auto_close_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=option.auto_close_timer)

    async with get_session() as session:
        fresh = await ticket_repository.get_ticket(session, ticket.id)
        await ticket_repository.update_ticket(
            session, fresh, control_message_id=control_message.id, auto_close_at=auto_close_at
        )

    if auto_close_at is not None:
        schedule_auto_close(bot, ticket.id, option.auto_close_timer * 60)

    if interaction.response.is_done():
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------- messages + permissions

async def get_option_for_ticket(ticket: Ticket):
    """Public wrapper - looks up the TicketOption a ticket was opened
    through, or None for tickets from the simple no-options flow."""
    return await _get_option_for_ticket(ticket)


async def _get_option_for_ticket(ticket: Ticket):
    if ticket.option_id is None:
        return None
    async with get_session() as session:
        return await ticket_options_repository.get_option(session, ticket.option_id)


async def _send_ticket_message(
    channel: discord.TextChannel, ticket: Ticket, option, message_type: str, *, actor=None, reason: str | None = None
) -> None:
    from core.script_parser import parse_script
    from core.variables import resolve_variables

    content = None
    if option is not None:
        async with get_session() as session:
            content = await ticket_options_repository.get_message(session, option.id, message_type)
    content = content or _DEFAULT_MESSAGES.get(message_type, "")
    if not content:
        return

    guild = channel.guild
    creator = guild.get_member(ticket.creator_id)
    claimer = guild.get_member(ticket.claimed_by) if ticket.claimed_by else None

    resolved = resolve_variables(
        content, guild=guild, member=actor or creator, channel=channel, reason=reason,
        ticket_case=ticket.case_number, ticket_creator=creator, ticket_claimed_by=claimer, ticket_status=ticket.status,
    )
    parsed = parse_script(resolved)
    if parsed.embed is not None or parsed.content:
        await channel.send(content=parsed.content, embed=parsed.embed)
    else:
        await channel.send(resolved)


DEFAULT_TICKET_DM = {
    "close_dm": "Your ticket in **{guild.name}** was closed by {user.mention}.\nReason: {custom.reason}",
}


async def _send_ticket_dm(
    ticket: Ticket, option, message_type: str, *, guild: discord.Guild, actor=None, reason: str | None = None
) -> None:
    content = None
    if option is not None:
        async with get_session() as session:
            content = await ticket_options_repository.get_message(session, option.id, message_type)

    if not content:
        content = DEFAULT_TICKET_DM.get(message_type)
    if not content:
        return

    from core.script_parser import parse_script
    from core.variables import resolve_variables

    creator = guild.get_member(ticket.creator_id)
    if creator is None:
        return

    resolved = resolve_variables(
        content, guild=guild, member=actor or creator, reason=reason,
        ticket_case=ticket.case_number, ticket_creator=creator, ticket_status=ticket.status,
    )
    parsed = parse_script(resolved)
    try:
        if parsed.embed is not None or parsed.content:
            await creator.send(content=parsed.content, embed=parsed.embed)
        else:
            await creator.send(resolved)
    except discord.HTTPException:
        pass


def _has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    member_role_ids = {r.id for r in member.roles}
    return bool(member_role_ids & set(role_ids))


async def can_claim(member: discord.Member, ticket: Ticket, option) -> bool:
    if member.guild_permissions.manage_guild:
        return True
    if option is None:
        return True
    async with get_session() as session:
        support_roles = await ticket_options_repository.get_support_roles(session, option.id)
        trainee_roles = await ticket_options_repository.get_trainee_roles(session, option.id)
    if support_roles and _has_any_role(member, support_roles):
        return True
    if option.trainees_can_claim and trainee_roles and _has_any_role(member, trainee_roles):
        return True
    return False


async def can_close(member: discord.Member, ticket: Ticket, option) -> bool:
    if member.guild_permissions.manage_guild:
        return True
    creator_can_close = option.creator_can_close if option is not None else True
    if member.id == ticket.creator_id and creator_can_close:
        return True
    if option is None:
        return False
    async with get_session() as session:
        support_roles = await ticket_options_repository.get_support_roles(session, option.id)
        trainee_roles = await ticket_options_repository.get_trainee_roles(session, option.id)
    if support_roles and _has_any_role(member, support_roles):
        return True
    if option.trainees_can_close and trainee_roles and _has_any_role(member, trainee_roles):
        return True
    return False


# ---------------------------------------------------------- central actions

async def _deliver_transcript(guild: discord.Guild, ticket: Ticket, option, path: str | None) -> None:
    """Sends the transcript to the option's (or falling back to the
    panel's) configured transcript channel. Does nothing if none is set -
    the transcript is still saved to disk and tracked on the ticket
    either way, just not announced anywhere."""
    if not path:
        return

    channel_id = option.transcript_channel_id if option is not None else None
    if channel_id is None and ticket.panel_id is not None:
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, ticket.panel_id)
        if panel is not None:
            channel_id = panel.transcript_channel_id

    if channel_id is None:
        return

    transcript_channel = guild.get_channel(channel_id)
    if transcript_channel is None:
        return

    try:
        await transcript_channel.send(
            embed=discord.Embed(description=f"Transcript for ticket `#{ticket.case_number}`"),
            file=discord.File(path),
        )
    except (discord.HTTPException, FileNotFoundError):
        pass


async def _close_and_deliver_transcript(channel: discord.TextChannel, ticket: Ticket, option) -> None:
    path = await close_ticket(channel)
    await _deliver_transcript(channel.guild, ticket, option, path)


async def do_claim(channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option) -> tuple[bool, str]:
    if ticket.status == "closed":
        return False, "This ticket is closed."
    if not await can_claim(actor, ticket, option):
        return False, "You don't have permission to claim this ticket."
    await claim_ticket(channel, actor)
    await _send_ticket_message(channel, ticket, option, "claim", actor=actor)
    return True, f"Ticket claimed by {actor.mention}."


async def do_unclaim(channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option) -> tuple[bool, str]:
    if ticket.claimed_by is None:
        return False, "This ticket isn't claimed."
    if not (actor.guild_permissions.manage_guild or actor.id == ticket.claimed_by):
        return False, "You don't have permission to unclaim this ticket."
    await unclaim_ticket(channel)
    return True, "Ticket unclaimed."


async def _send_log(channel: discord.TextChannel, ticket: Ticket) -> None:
    """Sends the ticket-closed log to the panel's configured log
    channel, if logging is enabled for that panel."""
    if not ticket.panel_id:
        return

    async with get_session() as session:
        panel = await ticket_repository.get_panel(session, ticket.panel_id)

    if panel is None or not panel.logs_enabled or not panel.log_channel_id:
        return

    log_channel = channel.guild.get_channel(panel.log_channel_id)
    if log_channel is None:
        return

    guild = channel.guild
    creator = guild.get_member(ticket.creator_id)
    claimed_by = guild.get_member(ticket.claimed_by) if ticket.claimed_by else None
    closed_by = guild.get_member(ticket.closed_by) if ticket.closed_by else None
    deleted_by = guild.get_member(ticket.deleted_by) if ticket.deleted_by else None

    users = [
        target for target, overwrite in channel.overwrites.items()
        if isinstance(target, discord.Member) and overwrite.view_channel and target.id != guild.me.id
    ]

    open_time = "Unknown"
    if ticket.created_at is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
        created = ticket.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        open_time = format_duration(int((now - created).total_seconds()))

    from core.script_parser import parse_script
    from core.variables import resolve_variables

    resolved = resolve_variables(
        panel.log_message_template, guild=guild,
        ticket_case=ticket.case_number, ticket_creator=creator, ticket_claimed_by=claimed_by,
        ticket_status=ticket.status, ticket_closed_by=closed_by, ticket_deleted_by=deleted_by,
        ticket_opened_at=ticket.created_at, ticket_open_time=open_time, ticket_users=users,
    )
    parsed = parse_script(resolved)

    try:
        if parsed.embed is not None:
            await log_channel.send(content=parsed.content, embed=parsed.embed)
        else:
            await log_channel.send(resolved)
    except discord.HTTPException:
        pass


async def do_close(
    bot, channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option, *, reason: str | None = None
) -> tuple[bool, str]:
    if ticket.status == "closed":
        return False, "This ticket is already closed."
    if not await can_close(actor, ticket, option):
        return False, "You don't have permission to close this ticket."

    await _send_ticket_message(channel, ticket, option, "close", actor=actor, reason=reason)
    await _send_ticket_dm(ticket, option, "close_dm", guild=channel.guild, actor=actor, reason=reason)

    await _close_and_deliver_transcript(channel, ticket, option)
    cancel_auto_close(ticket.id)

    async with get_session() as session:
        fresh = await ticket_repository.get_ticket(session, ticket.id)
        if fresh is not None:
            await ticket_repository.update_ticket(session, fresh, closed_by=actor.id)

    try:
        await channel.edit(name=f"closed-{channel.name}"[:100])
    except discord.HTTPException:
        pass

    if option is not None and option.auto_delete_timer:
        delete_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=option.auto_delete_timer)
        async with get_session() as session:
            fresh = await ticket_repository.get_ticket(session, ticket.id)
            await ticket_repository.update_ticket(session, fresh, auto_delete_at=delete_at, auto_close_at=None)
        schedule_auto_delete(bot, ticket.id, option.auto_delete_timer * 60)

    return True, "Ticket closed."


async def do_reopen(channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option) -> tuple[bool, str]:
    if ticket.status != "closed":
        return False, "This ticket is not closed."
    if not (actor.guild_permissions.manage_guild or actor.id == ticket.creator_id):
        return False, "You don't have permission to reopen this ticket."

    creator = channel.guild.get_member(ticket.creator_id)
    await reopen_ticket(channel, creator)
    cancel_auto_delete(ticket.id)

    async with get_session() as session:
        fresh = await ticket_repository.get_ticket(session, ticket.id)
        if fresh is not None:
            await ticket_repository.update_ticket(session, fresh, auto_delete_at=None)

    await _send_ticket_message(channel, ticket, option, "reopen", actor=actor)
    await _send_ticket_dm(ticket, option, "reopen_dm", guild=channel.guild, actor=actor)

    new_name = channel.name
    if new_name.startswith("closed-"):
        new_name = new_name[len("closed-"):]
    try:
        await channel.edit(name=new_name[:100])
    except discord.HTTPException:
        pass

    return True, "Ticket reopened."


async def do_delete(channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option) -> tuple[bool, str]:
    if not actor.guild_permissions.manage_guild:
        return False, "You don't have permission to delete this ticket."

    cancel_auto_close(ticket.id)
    cancel_auto_delete(ticket.id)

    path = await get_transcript(channel)
    await _deliver_transcript(channel.guild, ticket, option, path)

    async with get_session() as session:
        fresh = await ticket_repository.get_ticket(session, ticket.id)
        if fresh is not None:
            await ticket_repository.update_ticket(session, fresh, status="closed", deleted_by=actor.id)
            ticket = fresh

    await _send_log(channel, ticket)

    try:
        await channel.delete(reason=f"Ticket deleted by {actor}")
    except discord.Forbidden:
        return False, "I don't have permission to delete this channel."
    return True, "Ticket deleted."


async def do_move(
    channel: discord.TextChannel, actor: discord.Member, ticket: Ticket, option, category: discord.CategoryChannel
) -> tuple[bool, str]:
    if not actor.guild_permissions.manage_guild:
        return False, "You don't have permission to move this ticket."
    try:
        await channel.edit(category=category)
    except discord.Forbidden:
        return False, "I don't have permission to move this channel."
    await _send_ticket_message(channel, ticket, option, "move", actor=actor)
    return True, f"Ticket moved to **{category.name}**."


# ---------------------------------------------------------- control panel (per-ticket buttons)

_ACTION_LABELS_DEFAULT = {"claim": "Claim", "close": "Close", "reopen": "Reopen", "delete": "Delete"}
_ACTION_STYLE_DEFAULT = {"claim": "blue", "close": "red", "reopen": "green", "delete": "gray"}


class ReasonModal(discord.ui.Modal, title="Reason"):
    reason_input = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=300)

    def __init__(self, ticket_id: int, action: str):
        super().__init__()
        self.ticket_id = ticket_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await _handle_control_action(interaction, self.ticket_id, self.action, reason=str(self.reason_input))


class TicketControlView(discord.ui.View):
    """Per-ticket persistent view. Rebuilt with the option's current
    Button UX config any time the ticket is created or the bot restarts
    (registered via message_id, same pattern as ticket panels)."""

    def __init__(self, ticket_id: int, button_configs: dict):
        super().__init__(timeout=None)
        for action in BUTTON_ACTIONS:
            cfg = button_configs.get(action)
            label = cfg.label if cfg else _ACTION_LABELS_DEFAULT[action]
            emoji = cfg.emoji if cfg else None
            color = cfg.color if cfg else _ACTION_STYLE_DEFAULT[action]
            requires_reason = bool(cfg.requires_reason) if cfg else False

            button = discord.ui.Button(
                label=label,
                emoji=emoji or None,
                style=_BUTTON_STYLE_MAP.get(color, discord.ButtonStyle.secondary),
                custom_id=f"blade_ticket_ctrl:{ticket_id}:{action}",
            )
            button.callback = self._make_callback(ticket_id, action, requires_reason)
            self.add_item(button)

    def _make_callback(self, ticket_id: int, action: str, requires_reason: bool):
        async def _callback(interaction: discord.Interaction):
            if requires_reason:
                await interaction.response.send_modal(ReasonModal(ticket_id, action))
            else:
                await _handle_control_action(interaction, ticket_id, action, reason=None)
        return _callback


async def build_ticket_control_view(ticket_id: int, option_id: int | None) -> discord.ui.View:
    button_configs = {}
    if option_id is not None:
        async with get_session() as session:
            for action in BUTTON_ACTIONS:
                cfg = await ticket_options_repository.get_button_config(session, option_id, action)
                if cfg is not None:
                    button_configs[action] = cfg
    return TicketControlView(ticket_id, button_configs)


async def _handle_control_action(interaction: discord.Interaction, ticket_id: int, action: str, *, reason: str | None) -> None:
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket(session, ticket_id)
    if ticket is None:
        await interaction.response.send_message("This ticket no longer exists.", ephemeral=True)
        return

    channel = interaction.channel
    option = await _get_option_for_ticket(ticket)
    actor = interaction.user

    if action == "claim":
        success, message = await do_claim(channel, actor, ticket, option)
    elif action == "close":
        success, message = await do_close(interaction.client, channel, actor, ticket, option, reason=reason)
    elif action == "reopen":
        success, message = await do_reopen(channel, actor, ticket, option)
    elif action == "delete":
        success, message = await do_delete(channel, actor, ticket, option)
    else:
        success, message = False, "Unknown action."

    embed = discord.Embed(description=message)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.NotFound:
        # Expected for a successful "delete" action - the channel the
        # interaction belonged to is already gone by the time we try
        # to respond, so there's nowhere left to show this anyway.
        pass


# ---------------------------------------------------------- auto-close / auto-delete scheduling

def schedule_auto_close(bot: discord.Client, ticket_id: int, delay_seconds: float) -> None:
    existing = _auto_close_tasks.get(ticket_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _auto_close_tasks[ticket_id] = bot.loop.create_task(_auto_close_worker(bot, ticket_id, delay_seconds))


def cancel_auto_close(ticket_id: int) -> None:
    task = _auto_close_tasks.pop(ticket_id, None)
    if task is not None and not task.done():
        task.cancel()


async def _auto_close_worker(bot: discord.Client, ticket_id: int, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
    except asyncio.CancelledError:
        return

    async with get_session() as session:
        ticket = await ticket_repository.get_ticket(session, ticket_id)
    if ticket is None or ticket.status == "closed":
        _auto_close_tasks.pop(ticket_id, None)
        return

    guild = bot.get_guild(ticket.guild_id)
    channel = guild.get_channel(ticket.channel_id) if guild else None
    option = await _get_option_for_ticket(ticket)

    if channel is not None:
        await _send_ticket_message(channel, ticket, option, "auto_close")
        await _close_and_deliver_transcript(channel, ticket, option)
        try:
            await channel.edit(name=f"closed-{channel.name}"[:100])
        except discord.HTTPException:
            pass

        if option is not None and option.auto_delete_timer:
            delete_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=option.auto_delete_timer)
            async with get_session() as session:
                fresh = await ticket_repository.get_ticket(session, ticket_id)
                await ticket_repository.update_ticket(session, fresh, auto_delete_at=delete_at, auto_close_at=None)
            schedule_auto_delete(bot, ticket_id, option.auto_delete_timer * 60)

    _auto_close_tasks.pop(ticket_id, None)


def schedule_auto_delete(bot: discord.Client, ticket_id: int, delay_seconds: float) -> None:
    existing = _auto_delete_tasks.get(ticket_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _auto_delete_tasks[ticket_id] = bot.loop.create_task(_auto_delete_worker(bot, ticket_id, delay_seconds))


def cancel_auto_delete(ticket_id: int) -> None:
    task = _auto_delete_tasks.pop(ticket_id, None)
    if task is not None and not task.done():
        task.cancel()


async def _auto_delete_worker(bot: discord.Client, ticket_id: int, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
    except asyncio.CancelledError:
        return

    async with get_session() as session:
        ticket = await ticket_repository.get_ticket(session, ticket_id)
    if ticket is None:
        _auto_delete_tasks.pop(ticket_id, None)
        return

    guild = bot.get_guild(ticket.guild_id)
    channel = guild.get_channel(ticket.channel_id) if guild else None
    if channel is not None:
        option = await _get_option_for_ticket(ticket)
        await _send_ticket_message(channel, ticket, option, "auto_delete")
        try:
            await channel.delete(reason="Auto-delete timer expired")
        except discord.HTTPException:
            pass

    _auto_delete_tasks.pop(ticket_id, None)


async def resume_ticket_timers(bot: discord.Client) -> tuple[int, int]:
    """Call on startup: reschedules every still-pending auto-close and
    auto-delete deadline so a restart never silently drops them."""
    async with get_session() as session:
        pending_close = await ticket_repository.get_tickets_with_pending_auto_close(session)
        pending_delete = await ticket_repository.get_tickets_with_pending_auto_delete(session)

    now = datetime.datetime.now(datetime.timezone.utc)
    for ticket in pending_close:
        auto_close_at = ticket.auto_close_at
        if auto_close_at.tzinfo is None:
            auto_close_at = auto_close_at.replace(tzinfo=datetime.timezone.utc)
        remaining = (auto_close_at - now).total_seconds()
        schedule_auto_close(bot, ticket.id, max(0, remaining))
    for ticket in pending_delete:
        auto_delete_at = ticket.auto_delete_at
        if auto_delete_at.tzinfo is None:
            auto_delete_at = auto_delete_at.replace(tzinfo=datetime.timezone.utc)
        remaining = (auto_delete_at - now).total_seconds()
        schedule_auto_delete(bot, ticket.id, max(0, remaining))

    return len(pending_close), len(pending_delete)


async def resume_ticket_control_views(bot: discord.Client) -> int:
    """Call on startup: re-registers every open ticket's control-panel
    buttons as a persistent, message_id-bound view."""
    async with get_session() as session:
        tickets = await ticket_repository.get_open_tickets_with_control_message(session)

    for ticket in tickets:
        view = await build_ticket_control_view(ticket.id, ticket.option_id)
        bot.add_view(view, message_id=ticket.control_message_id)

    return len(tickets)


# ---------------------------------------------------------- inactivity (in-memory only)

def reset_inactivity_timer(bot: discord.Client, ticket_id: int, channel_id: int, delay_seconds: float) -> None:
    existing = _inactivity_tasks.get(channel_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _inactivity_tasks[channel_id] = bot.loop.create_task(_inactivity_worker(bot, ticket_id, channel_id, delay_seconds))


def cancel_inactivity_timer(channel_id: int) -> None:
    task = _inactivity_tasks.pop(channel_id, None)
    if task is not None and not task.done():
        task.cancel()


async def _inactivity_worker(bot: discord.Client, ticket_id: int, channel_id: int, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
    except asyncio.CancelledError:
        return

    async with get_session() as session:
        ticket = await ticket_repository.get_ticket(session, ticket_id)
    if ticket is None or ticket.status == "closed":
        _inactivity_tasks.pop(channel_id, None)
        return

    guild = bot.get_guild(ticket.guild_id)
    channel = guild.get_channel(channel_id) if guild else None
    if channel is not None:
        option = await _get_option_for_ticket(ticket)
        await _send_ticket_message(channel, ticket, option, "inactivity")
        await _close_and_deliver_transcript(channel, ticket, option)
        try:
            await channel.edit(name=f"closed-{channel.name}"[:100])
        except discord.HTTPException:
            pass

    _inactivity_tasks.pop(channel_id, None)


async def handle_ticket_activity(bot: discord.Client, message: discord.Message) -> None:
    """Call from an on_message listener for every non-bot message. Resets
    the inactivity timer if this channel is an open ticket whose option
    has one configured."""
    if message.author.bot or message.guild is None:
        return
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, message.channel.id)
    if ticket is None or ticket.status == "closed":
        return
    option = await _get_option_for_ticket(ticket)
    if option is not None and option.inactivity_timer:
        reset_inactivity_timer(bot, ticket.id, message.channel.id, option.inactivity_timer * 60)


async def handle_member_leave(guild: discord.Guild, member: discord.Member) -> None:
    """Call from an on_member_remove listener. Auto-closes any open
    ticket the departing member created, for options with
    close_on_leave enabled."""
    async with get_session() as session:
        tickets = await ticket_repository.get_open_tickets_for_creator(session, guild.id, member.id)

    for ticket in tickets:
        option = await _get_option_for_ticket(ticket)
        if option is None or not option.close_on_leave:
            continue
        channel = guild.get_channel(ticket.channel_id)
        if channel is None:
            continue
        cancel_auto_close(ticket.id)
        cancel_inactivity_timer(channel.id)
        await _send_ticket_message(channel, ticket, option, "close")
        await _close_and_deliver_transcript(channel, ticket, option)
        try:
            await channel.edit(name=f"closed-{channel.name}"[:100])
        except discord.HTTPException:
            pass


# ---------------------------------------------------------- low-level DB-backed helpers

async def claim_ticket(channel: discord.TextChannel, staff: discord.Member) -> Ticket | None:
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel.id)
        if ticket is None:
            return None
        return await ticket_repository.update_ticket(session, ticket, claimed_by=staff.id, status="claimed")


async def unclaim_ticket(channel: discord.TextChannel) -> Ticket | None:
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel.id)
        if ticket is None:
            return None
        return await ticket_repository.update_ticket(session, ticket, claimed_by=None, status="open")


async def reopen_ticket(channel: discord.TextChannel, creator: discord.Member | None) -> Ticket | None:
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel.id)
        if ticket is None:
            return None
        ticket = await ticket_repository.update_ticket(session, ticket, status="open", closed_at=None)

    if creator is not None:
        try:
            await channel.set_permissions(creator, view_channel=True, send_messages=True)
        except discord.Forbidden:
            pass

    return ticket


async def _write_transcript(channel: discord.TextChannel, ticket: Ticket) -> str:
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    path = os.path.join(TRANSCRIPT_DIR, f"ticket-{ticket.id}.txt")

    lines = []
    async for message in channel.history(limit=None, oldest_first=True):
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{timestamp}] {message.author}: {message.content}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


async def get_transcript(channel: discord.TextChannel) -> str | None:
    """Generates a transcript without closing the ticket - used by
    ,tickets transcript on a still-open ticket."""
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel.id)
        if ticket is None:
            return None
        path = await _write_transcript(channel, ticket)
        await ticket_repository.update_ticket(session, ticket, transcript_path=path)
    return path


async def close_ticket(channel: discord.TextChannel) -> str | None:
    """Writes a plaintext transcript to disk and marks the ticket closed.
    Returns the transcript file path, or None if this wasn't a ticket channel."""
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel.id)
        if ticket is None:
            return None

        path = await _write_transcript(channel, ticket)

        await ticket_repository.update_ticket(
            session, ticket, status="closed", transcript_path=path,
            closed_at=datetime.datetime.now(datetime.timezone.utc),
        )

    return path