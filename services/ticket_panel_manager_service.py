"""
,tickets panel management menu - replaces the old "type a title|description
and it posts immediately" behavior. Now: pick an existing panel (or
create one), then configure it through a Behaviour/Category/Display/
Messages button menu before actually sending it.

Every step here sends PLAIN CONTENT, never an embed - matching the
"no embed, just the dropdown/menu" look requested. Only the actual
posted ticket panel (via Send Panel) still uses build_panel_view's
normal embed+button, since that's the panel members will use.

Channel/category fields use TextInput (name or ID typed as text)
rather than a live channel-select-in-modal, matching the same
established, lower-risk choice already made in
ticket_options_service.CategoriesModal - select-in-modal is proven
reliable in this codebase only for fixed option lists (colors, message
types, etc.), not dynamic guild-object pickers.
"""

from __future__ import annotations

import discord

from database.database import get_session
from repositories import ticket_repository

CHANNEL_NAME_FORMATS = ["case_number", "username", "username_and_case"]
MODES = ["dropdown", "buttons"]


async def start(ctx) -> None:
    async with get_session() as session:
        panels = await ticket_repository.get_panels_for_guild(session, ctx.guild.id)

    view = PanelPickView(panels)
    await ctx.send(view=view)


class PanelPickView(discord.ui.View):
    def __init__(self, panels: list):
        super().__init__(timeout=180)

        options = [discord.SelectOption(label=p.title, value=str(p.id)) for p in panels[:24]]
        options.append(discord.SelectOption(label="Create a new Panel", value="__create__", emoji="➕"))

        select = discord.ui.Select(placeholder="Select a panel...", options=options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = self._select.values[0]
        if value == "__create__":
            from services import premium_service

            async with get_session() as session:
                existing = await ticket_repository.get_panels_for_guild(session, interaction.guild.id)
            allowed, limit = await premium_service.check_limit(interaction.guild.id, "ticket_panels", len(existing))
            if not allowed:
                is_prem = await premium_service.is_premium(interaction.guild.id, "server")
                await interaction.response.send_message(
                    premium_service.limit_reached_message("ticket panels", limit, is_prem), ephemeral=True
                )
                return
            await interaction.response.send_modal(CreatePanelModal())
            return
        await _show_panel_menu(interaction, int(value))


class CreatePanelModal(discord.ui.Modal, title="Create Panel"):
    name_input = discord.ui.TextInput(label="Panel Name", max_length=100)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            panel = await ticket_repository.create_panel(
                session,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                title=str(self.name_input),
            )

        view = PanelMenuView(panel.id)
        await interaction.response.send_message(content=panel.title, view=view, ephemeral=True)


async def _show_panel_menu(interaction: discord.Interaction, panel_id: int) -> None:
    async with get_session() as session:
        panel = await ticket_repository.get_panel(session, panel_id)

    if panel is None:
        await interaction.response.send_message("That panel no longer exists.", ephemeral=True)
        return

    view = PanelMenuView(panel_id)
    if interaction.response.is_done():
        await interaction.edit_original_response(content=panel.title, view=view)
    else:
        await interaction.response.edit_message(content=panel.title, view=view)


class PanelMenuView(discord.ui.View):
    def __init__(self, panel_id: int):
        super().__init__(timeout=300)
        self.panel_id = panel_id

    @discord.ui.button(label="Behaviour", style=discord.ButtonStyle.primary, row=0)
    async def behaviour(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(BehaviourModal(self.panel_id))

    @discord.ui.button(label="Category", style=discord.ButtonStyle.primary, row=0)
    async def category(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(CategoryModal(self.panel_id))

    @discord.ui.button(label="Display", style=discord.ButtonStyle.primary, row=0)
    async def display(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(DisplayModal(self.panel_id))

    @discord.ui.button(label="Messages", style=discord.ButtonStyle.primary, row=1)
    async def messages(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(MessagesModal(self.panel_id))

    @discord.ui.button(label="Send Panel", style=discord.ButtonStyle.success, row=2)
    async def send_panel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        from services.ticket_service import build_panel_view

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)

        if panel is None:
            await interaction.response.send_message("That panel no longer exists.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(panel.channel_id) or interaction.channel
        embed = discord.Embed(title=panel.title, description=panel.description)
        view = await build_panel_view(panel.id)
        message = await channel.send(embed=embed, view=view)

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            await ticket_repository.update_panel(session, panel, message_id=message.id, channel_id=channel.id)

        await interaction.response.send_message(f"Panel sent to {channel.mention}.", ephemeral=True)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, row=2)
    async def remove(self, interaction: discord.Interaction, _button: discord.ui.Button):
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None:
                await ticket_repository.delete_panel(session, panel)

        await interaction.response.edit_message(content="Panel removed.", view=None)

    @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.secondary, row=2)
    async def edit_name(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(EditNameModal(self.panel_id))


class EditNameModal(discord.ui.Modal, title="Edit Name"):
    name_input = discord.ui.TextInput(label="Panel Name", max_length=100)

    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None:
                panel = await ticket_repository.update_panel(session, panel, title=str(self.name_input))

        view = PanelMenuView(self.panel_id)
        await interaction.response.edit_message(content=panel.title if panel else "Panel", view=view)


class BehaviourModal(discord.ui.Modal, title="Panel Behaviour Settings"):
    delete_delay_input = discord.ui.TextInput(
        label="Delete Delay", required=False, placeholder="e.g., 0s, 5m, 1h",
    )
    max_open_input = discord.ui.TextInput(label="Maximum Open Tickets", default="1")

    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id

        self.auto_pin_checkbox = discord.ui.Checkbox(custom_id="auto_pin_controls")
        self.add_item(discord.ui.Label(
            text="Auto-Pin Controls",
            description="Automatically pin ticket control messages",
            component=self.auto_pin_checkbox,
        ))

        self.claims_checkbox = discord.ui.Checkbox(custom_id="claims_enabled")
        self.add_item(discord.ui.Label(
            text="Claims Enabled",
            description="Allow staff to claim tickets",
            component=self.claims_checkbox,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from core.helpers import InvalidDuration, parse_duration

        raw_delay = str(self.delete_delay_input).strip()
        delay_seconds = 0
        if raw_delay:
            try:
                delay_seconds = parse_duration(raw_delay)
            except InvalidDuration:
                await interaction.response.send_message(
                    f"Couldn't parse delete delay `{raw_delay}` - try something like `5m` or `1h`.", ephemeral=True
                )
                return

        try:
            max_open = max(1, int(str(self.max_open_input)))
        except ValueError:
            max_open = 1

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None:
                await ticket_repository.update_panel(
                    session, panel,
                    delete_delay_seconds=delay_seconds,
                    max_open_tickets=max_open,
                    auto_pin_controls=bool(self.auto_pin_checkbox.value),
                    claims_enabled=bool(self.claims_checkbox.value),
                )

        await interaction.response.send_message("Behaviour updated.", ephemeral=True)


class CategoryModal(discord.ui.Modal, title="Panel Categories & Channels"):
    panel_channel_input = discord.ui.TextInput(label="Panel Channel", placeholder="Channel name or ID")
    log_channel_input = discord.ui.TextInput(label="Log Channel", placeholder="Channel name or ID")
    default_category_input = discord.ui.TextInput(label="Default Category", placeholder="Category name or ID")
    closed_category_input = discord.ui.TextInput(label="Closed Category", placeholder="Category name or ID")

    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id

    @staticmethod
    def _resolve_category(guild: discord.Guild, raw: str) -> discord.CategoryChannel | None:
        raw = raw.strip()
        if not raw:
            return None
        if raw.isdigit():
            channel = guild.get_channel(int(raw))
            if isinstance(channel, discord.CategoryChannel):
                return channel
        return discord.utils.get(guild.categories, name=raw)

    @staticmethod
    def _resolve_text_channel(guild: discord.Guild, raw: str) -> discord.TextChannel | None:
        raw = raw.strip()
        if not raw:
            return None
        if raw.isdigit():
            channel = guild.get_channel(int(raw))
            if isinstance(channel, discord.TextChannel):
                return channel
        return discord.utils.get(guild.text_channels, name=raw)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        unresolved = []
        fields = {}

        panel_channel = self._resolve_text_channel(guild, str(self.panel_channel_input))
        if panel_channel is None:
            unresolved.append(str(self.panel_channel_input))
        else:
            fields["channel_id"] = panel_channel.id

        log_channel = self._resolve_text_channel(guild, str(self.log_channel_input))
        if log_channel is None:
            unresolved.append(str(self.log_channel_input))
        else:
            fields["log_channel_id"] = log_channel.id

        default_category = self._resolve_category(guild, str(self.default_category_input))
        if default_category is None:
            unresolved.append(str(self.default_category_input))
        else:
            fields["category_id"] = default_category.id

        closed_category = self._resolve_category(guild, str(self.closed_category_input))
        if closed_category is None:
            unresolved.append(str(self.closed_category_input))
        else:
            fields["closed_category_id"] = closed_category.id

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None and fields:
                await ticket_repository.update_panel(session, panel, **fields)

        message = "Categories & channels updated."
        if unresolved:
            message += f"\nCouldn't find: {', '.join(unresolved)} - left unchanged."
        await interaction.response.send_message(message, ephemeral=True)


class DisplayModal(discord.ui.Modal, title="Panel Display Settings"):
    case_padding_input = discord.ui.TextInput(label="Case Padding", default="0", required=False)
    dropdown_placeholder_input = discord.ui.TextInput(
        label="Dropdown Placeholder", required=False, placeholder="Enter placeholder text",
    )

    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id

        self.format_select = discord.ui.Select(options=[
            discord.SelectOption(label="Case Number", value="case_number"),
            discord.SelectOption(label="Username", value="username"),
            discord.SelectOption(label="Username & Case", value="username_and_case"),
        ])
        self.add_item(discord.ui.Label(text="Channel Name Format", component=self.format_select))

        self.mode_select = discord.ui.Select(options=[
            discord.SelectOption(label="Dropdown", value="dropdown"),
            discord.SelectOption(label="Buttons", value="buttons"),
        ])
        self.add_item(discord.ui.Label(text="Mode", component=self.mode_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            padding = max(0, int(str(self.case_padding_input) or "0"))
        except ValueError:
            padding = 0

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None:
                await ticket_repository.update_panel(
                    session, panel,
                    channel_name_format=self.format_select.values[0] if self.format_select.values else panel.channel_name_format,
                    case_padding=padding,
                    dropdown_placeholder=str(self.dropdown_placeholder_input) or None,
                    mode=self.mode_select.values[0] if self.mode_select.values else panel.mode,
                )

        await interaction.response.send_message("Display settings updated.", ephemeral=True)


class MessagesModal(discord.ui.Modal, title="Panel Messages"):
    """HONEST GAP: panels don't yet have the full per-event message
    system that ticket options already have (greeting/claim/close/etc)
    - this edits the panel's own posted message (title/description)
    only. Message Type currently has a single option for that reason."""

    content_input = discord.ui.TextInput(
        label="Content", style=discord.TextStyle.paragraph, max_length=4000, required=False,
    )

    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id

        self.type_select = discord.ui.Select(options=[
            discord.SelectOption(label="Panel Message", value="panel_message"),
        ])
        self.add_item(discord.ui.Label(text="Message Type", component=self.type_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        content = str(self.content_input).strip()
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            if panel is not None and content:
                await ticket_repository.update_panel(session, panel, description=content)

        await interaction.response.send_message("Messages updated.", ephemeral=True)
