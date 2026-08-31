"""
Ticket forms builder: ,tickets forms.

Uses discord.py 2.7's native modal Checkbox/Select support (a Label
wraps each of these inside a Modal - discord.py's own API, only
available on 2.7+, which is why requirements.txt now pins that
minimum). This is very recently added to discord.py, so if the exact
Label/Checkbox constructor signature below doesn't match what actually
shipped, that's the first thing to check against a traceback.
"""

from __future__ import annotations

import discord

from database.database import get_session
from database.ticket_forms_models import FIELD_TYPES
from repositories import ticket_forms_repository

FIELD_TYPE_LABELS = {
    "short_text": "Short Text",
    "long_text": "Long Text",
    "checkbox": "Checkbox",
    "select": "Select",
    "role_select": "Role Select",
    "user_select": "User Select",
    "channel_select": "Channel Select",
}


def _slugify_key(label: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in label).strip("_")[:50] or "field"


class CreateFormModal(discord.ui.Modal, title="Create Form"):
    def __init__(self, guild_id: int, on_created):
        super().__init__()
        self.guild_id = guild_id
        self.on_created = on_created

        self.name_input = discord.ui.TextInput(label="Form Name", max_length=100)
        self.modal_title_input = discord.ui.TextInput(label="Modal Title", max_length=45)
        self.add_item(self.name_input)
        self.add_item(self.modal_title_input)

        self.filter_checkbox = discord.ui.Checkbox(custom_id="enable_filtering")
        self.add_item(discord.ui.Label(
            text="Enable Filtering",
            description="Run server word filters on answers.",
            component=self.filter_checkbox,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            form = await ticket_forms_repository.create_form(
                session, self.guild_id, str(self.name_input), str(self.modal_title_input),
                bool(self.filter_checkbox.value),
            )
        await self.on_created(interaction, form.id)


class CreateFieldModal(discord.ui.Modal, title="Create Field"):
    def __init__(self, form_id: int, on_created):
        super().__init__()
        self.form_id = form_id
        self.on_created = on_created

        self.type_select = discord.ui.Select(
            options=[discord.SelectOption(label=label, value=key) for key, label in FIELD_TYPE_LABELS.items()]
        )
        self.add_item(discord.ui.Label(text="Field Type", component=self.type_select))

        self.label_input = discord.ui.TextInput(label="Label", max_length=100)
        self.description_input = discord.ui.TextInput(label="Description", max_length=200, required=False)
        self.key_input = discord.ui.TextInput(label="Key", max_length=50, required=False)
        self.add_item(self.label_input)
        self.add_item(self.description_input)
        self.add_item(self.key_input)

        self.required_checkbox = discord.ui.Checkbox(custom_id="field_required")
        self.add_item(discord.ui.Label(text="Required", component=self.required_checkbox))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        field_type = self.type_select.values[0] if self.type_select.values else "short_text"
        key = str(self.key_input) or _slugify_key(str(self.label_input))

        async with get_session() as session:
            field = await ticket_forms_repository.add_field(
                session, self.form_id,
                field_type=field_type,
                label=str(self.label_input),
                description=str(self.description_input) or None,
                key=key,
                required=bool(self.required_checkbox.value),
            )
        await self.on_created(interaction, field.id)


class FormSelectView(discord.ui.View):
    """,tickets forms - top-level 'Select a form..' dropdown, with
    'Create a new form' always pinned first."""

    def __init__(self, guild_id: int, forms: list):
        super().__init__(timeout=180)
        self.guild_id = guild_id

        options = [discord.SelectOption(label="Create a new form", value="__create__", emoji="➕")]
        options += [discord.SelectOption(label=f.name, value=str(f.id)) for f in forms[:24]]

        select = discord.ui.Select(placeholder="Select a form..", options=options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = self._select.values[0]
        if value == "__create__":
            await interaction.response.send_modal(CreateFormModal(self.guild_id, lambda i, fid: _show_form_detail(i, fid, as_new=True)))
            return
        await _show_form_detail(interaction, int(value))


async def _show_form_detail(interaction: discord.Interaction, form_id: int, *, as_new: bool = False) -> None:
    async with get_session() as session:
        form = await ticket_forms_repository.get_form(session, form_id)
        fields = await ticket_forms_repository.get_fields(session, form_id)

    if form is None:
        await interaction.response.send_message("That form no longer exists.", ephemeral=True)
        return

    lines = [f"`{i+1}.` **{f.label}** ({FIELD_TYPE_LABELS.get(f.field_type, f.field_type)})" for i, f in enumerate(fields)]
    body = "\n".join(lines) if lines else "No fields yet."
    content = (
        f"**{form.name}**\n{body}\n\n"
        f"Modal Title: {form.modal_title}  •  Filtering: {'Enabled' if form.enable_filtering else 'Disabled'}"
    )

    view = FormDetailView(form_id)

    if as_new:
        # Called from a modal's on_submit - see the matching note in
        # ticket_options_service.py for why this can't safely edit.
        if interaction.response.is_done():
            await interaction.followup.send(content=content, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(content=content, view=view, ephemeral=True)
        return

    if interaction.response.is_done():
        await interaction.edit_original_response(content=content, view=view)
    else:
        await interaction.response.edit_message(content=content, view=view)


class FormDetailView(discord.ui.View):
    def __init__(self, form_id: int):
        super().__init__(timeout=180)
        self.form_id = form_id

    @discord.ui.button(label="Field", style=discord.ButtonStyle.primary)
    async def field_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        async with get_session() as session:
            fields = await ticket_forms_repository.get_fields(session, self.form_id)
        view = FieldSelectView(self.form_id, fields)
        await interaction.response.edit_message(content="Choose a field to edit, or create a new one.", view=view)

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.primary)
    async def settings_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(FormSettingsModal(self.form_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        async with get_session() as session:
            form = await ticket_forms_repository.get_form(session, self.form_id)
            forms = await ticket_forms_repository.get_forms_for_guild(session, form.guild_id) if form else []
        view = FormSelectView(form.guild_id if form else 0, forms)
        await interaction.response.edit_message(content="Select a form to manage, or create a new one.", view=view)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        async with get_session() as session:
            form = await ticket_forms_repository.get_form(session, self.form_id)
            guild_id = form.guild_id if form else 0
            await ticket_forms_repository.delete_form(session, self.form_id)
            forms = await ticket_forms_repository.get_forms_for_guild(session, guild_id)
        view = FormSelectView(guild_id, forms)
        await interaction.response.edit_message(content="Form removed. Select a form, or create a new one.", view=view)


class FormSettingsModal(discord.ui.Modal, title="Form Settings"):
    def __init__(self, form_id: int):
        super().__init__()
        self.form_id = form_id
        self.filter_checkbox = discord.ui.Checkbox(custom_id="enable_filtering")
        self.add_item(discord.ui.Label(
            text="Enable Filtering",
            description="Enable word filtering for form submissions.",
            component=self.filter_checkbox,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            form = await ticket_forms_repository.get_form(session, self.form_id)
            if form is not None:
                await ticket_forms_repository.update_form(session, form, enable_filtering=bool(self.filter_checkbox.value))
        await interaction.response.send_message(content="Form settings updated.", ephemeral=True)


class FieldSelectView(discord.ui.View):
    def __init__(self, form_id: int, fields: list):
        super().__init__(timeout=180)
        self.form_id = form_id

        options = [discord.SelectOption(label="Create a new field", value="__create__", emoji="➕")]
        options += [discord.SelectOption(label=f.label, value=str(f.id)) for f in fields[:24]]

        select = discord.ui.Select(placeholder="Select a field..", options=options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = self._select.values[0]
        if value == "__create__":
            await interaction.response.send_modal(CreateFieldModal(self.form_id, self._after_field_created))
            return
        await interaction.response.send_message(
            "Field editing uses the same form as creating a field - re-run `,tickets forms` and create a replacement field for now.",
            ephemeral=True,
        )

    async def _after_field_created(self, interaction: discord.Interaction, field_id: int) -> None:
        async with get_session() as session:
            field = await ticket_forms_repository.get_field(session, field_id)
            fields = await ticket_forms_repository.get_fields(session, field.form_id) if field else []
        view = FieldSelectView(field.form_id if field else 0, fields)
        await interaction.response.send_message(content="Field created. Choose a field, or create another.", view=view, ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await _show_form_detail(interaction, self.form_id)


async def start(ctx) -> None:
    async with get_session() as session:
        forms = await ticket_forms_repository.get_forms_for_guild(session, ctx.guild.id)
    view = FormSelectView(ctx.guild.id, forms)
    await ctx.send(content="Select a form to manage, or create a new one.", view=view)