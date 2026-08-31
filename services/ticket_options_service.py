"""
Ticket options builder: ,tickets options.

Navigation: Select a panel.. -> Select an option.. (+ Create new) ->
main option menu (Behavior/Form/Messages/Automation/Style/Back/Remove).
Behavior -> Categories/Naming/Permissions/Required Roles/Support Roles/
Trainee Roles/Button UX/Back.

THIS PHASE: the full navigation shell works end to end and doesn't
dead-end anywhere. Permissions is fully wired as the concrete example
of the real-checkbox-in-modal pattern. The remaining Behavior branches
(Button UX, Categories, Naming, Required/Support/Trainee Roles) and
the top-level Form/Messages/Automation/Style buttons are stubbed with
a clear "coming in the next phase" response rather than faking them.
"""

from __future__ import annotations

import discord

from database.database import get_session
from database.ticket_options_models import MESSAGE_TYPES
from repositories import ticket_options_repository, ticket_repository

_COMING_SOON = "This section is coming in the next phase - the navigation is in place, the settings screen isn't wired up yet."


async def start(ctx) -> None:
    async with get_session() as session:
        panels = await ticket_repository.get_panels_for_guild(session, ctx.guild.id)

    if not panels:
        await ctx.send(content=f"{ctx.author.mention} No panels found. Create a panel first using `,tix panel`.")
        return

    view = PanelSelectView(panels)
    await ctx.send(view=view)


class PanelSelectView(discord.ui.View):
    """Only lists existing panels - no 'create a panel' entry here,
    per spec (,tickets panel is the dedicated command for that)."""

    def __init__(self, panels: list):
        super().__init__(timeout=180)
        options = [discord.SelectOption(label=p.title, value=str(p.id)) for p in panels[:25]]
        select = discord.ui.Select(placeholder="Select a panel..", options=options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        panel_id = int(self._select.values[0])
        await _show_option_select(interaction, panel_id)


async def _show_option_select(interaction: discord.Interaction, panel_id: int) -> None:
    async with get_session() as session:
        options = await ticket_options_repository.get_options_for_panel(session, panel_id)

    view = OptionSelectView(panel_id, options)
    content = "Choose an option to manage, or create a new one."
    if interaction.response.is_done():
        await interaction.edit_original_response(content=content, view=view)
    else:
        await interaction.response.edit_message(content=content, view=view)


class OptionSelectView(discord.ui.View):
    def __init__(self, panel_id: int, options: list):
        super().__init__(timeout=180)
        self.panel_id = panel_id

        select_options = [discord.SelectOption(label="Create a new option", value="__create__", emoji="➕")]
        select_options += [discord.SelectOption(label=o.name, value=str(o.id)) for o in options[:24]]

        select = discord.ui.Select(placeholder="Select an option..", options=select_options)
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = self._select.values[0]
        if value == "__create__":
            await interaction.response.send_modal(CreateOptionModal(self.panel_id))
            return
        await _show_option_menu(interaction, int(value))


class CreateOptionModal(discord.ui.Modal, title="Create Option"):
    def __init__(self, panel_id: int):
        super().__init__()
        self.panel_id = panel_id
        self.name_input = discord.ui.TextInput(label="Option Name", max_length=100)
        self.label_input = discord.ui.TextInput(label="Button/Dropdown Label", max_length=80)
        self.emoji_input = discord.ui.TextInput(label="Emoji", max_length=64, required=False)
        self.add_item(self.name_input)
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, self.panel_id)
            option = await ticket_options_repository.create_option(
                session, panel.guild_id, self.panel_id,
                str(self.name_input), str(self.label_input), str(self.emoji_input) or None,
            )
        await _show_option_menu(interaction, option.id, as_new=True)


async def _show_option_menu(interaction: discord.Interaction, option_id: int, *, as_new: bool = False) -> None:
    async with get_session() as session:
        option = await ticket_options_repository.get_option(session, option_id)

    if option is None:
        await interaction.response.send_message("That option no longer exists.", ephemeral=True)
        return

    content = f"{option.name} — Label: **{option.label}**" + (f"  •  {option.emoji}" if option.emoji else "")
    view = OptionMenuView(option_id, option.panel_id)

    if as_new:
        # Called from a modal's on_submit - editing the original message
        # that opened the modal isn't reliable from here, so just send a
        # fresh response instead of trying (and silently failing) an edit.
        if interaction.response.is_done():
            await interaction.followup.send(content=content, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(content=content, view=view, ephemeral=True)
        return

    if interaction.response.is_done():
        await interaction.edit_original_response(content=content, view=view)
    else:
        await interaction.response.edit_message(content=content, view=view)


class OptionMenuView(discord.ui.View):
    def __init__(self, option_id: int, panel_id: int):
        super().__init__(timeout=180)
        self.option_id = option_id
        self.panel_id = panel_id

    @discord.ui.button(label="Behavior", style=discord.ButtonStyle.primary, row=0)
    async def behavior_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(content="Choose a behavior category to configure.", view=BehaviorMenuView(self.option_id))

    @discord.ui.button(label="Form", style=discord.ButtonStyle.primary, row=0)
    async def form_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        from repositories import ticket_forms_repository
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            forms = await ticket_forms_repository.get_forms_for_guild(session, option.guild_id) if option else []
        await interaction.response.send_modal(FormSelectModal(self.option_id, forms))

    @discord.ui.button(label="Messages", style=discord.ButtonStyle.primary, row=0)
    async def messages_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(MessagesModal(self.option_id))

    @discord.ui.button(label="Automation", style=discord.ButtonStyle.primary, row=1)
    async def automation_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(AutomationModal(self.option_id))

    @discord.ui.button(label="Style", style=discord.ButtonStyle.primary, row=1)
    async def style_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(StyleModal(self.option_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=2)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await _show_option_select(interaction, self.panel_id)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, row=2)
    async def remove_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        async with get_session() as session:
            await ticket_options_repository.delete_option(session, self.option_id)
        await _show_option_select(interaction, self.panel_id)


class BehaviorMenuView(discord.ui.View):
    def __init__(self, option_id: int):
        super().__init__(timeout=180)
        self.option_id = option_id

    @discord.ui.button(label="Button UX", style=discord.ButtonStyle.primary, row=0)
    async def button_ux(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(content="Choose a button to configure.", view=ButtonUXMenuView(self.option_id))

    @discord.ui.button(label="Categories", style=discord.ButtonStyle.primary, row=0)
    async def categories(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(CategoriesModal(self.option_id))

    @discord.ui.button(label="Naming", style=discord.ButtonStyle.primary, row=0)
    async def naming(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(NamingModal(self.option_id))

    @discord.ui.button(label="Permissions", style=discord.ButtonStyle.primary, row=1)
    async def permissions(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(PermissionsModal(self.option_id))

    @discord.ui.button(label="Required Roles", style=discord.ButtonStyle.primary, row=1)
    async def required_roles(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(RequiredRolesModal(self.option_id))

    @discord.ui.button(label="Support Roles", style=discord.ButtonStyle.primary, row=2)
    async def support_roles(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(SupportRolesModal(self.option_id))

    @discord.ui.button(label="Trainee Roles", style=discord.ButtonStyle.primary, row=2)
    async def trainee_roles(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(TraineeRolesModal(self.option_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await _show_option_menu(interaction, self.option_id)


class ButtonUXMenuView(discord.ui.View):
    """Behavior -> Button UX. Claim/Close/Reopen/Delete each open their
    own config modal (label, emoji, color, requires-reason)."""

    def __init__(self, option_id: int):
        super().__init__(timeout=180)
        self.option_id = option_id

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, row=0)
    async def claim_btn(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(ButtonConfigModal(self.option_id, "claim"))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.primary, row=0)
    async def close_btn(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(ButtonConfigModal(self.option_id, "close"))

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.primary, row=0)
    async def reopen_btn(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(ButtonConfigModal(self.option_id, "reopen"))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.primary, row=0)
    async def delete_btn(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(ButtonConfigModal(self.option_id, "delete"))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(content="Choose a behavior category to configure.", view=BehaviorMenuView(self.option_id))


class ButtonConfigModal(discord.ui.Modal):
    def __init__(self, option_id: int, action: str):
        super().__init__(title=f"{action.title()} Button")
        self.option_id = option_id
        self.action = action

        self.label_input = discord.ui.TextInput(label="Button Label", max_length=80, default=action.title())
        self.emoji_input = discord.ui.TextInput(label="Button Emoji", max_length=64, required=False)
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)

        self.color_select = discord.ui.Select(options=[
            discord.SelectOption(label="Blue", value="blue"),
            discord.SelectOption(label="Gray", value="gray"),
            discord.SelectOption(label="Green", value="green"),
            discord.SelectOption(label="Red", value="red"),
        ])
        self.add_item(discord.ui.Label(text="Button Color", component=self.color_select))

        self.requires_reason_checkbox = discord.ui.Checkbox(custom_id="requires_reason")
        self.add_item(discord.ui.Label(
            text="Requires Reason",
            description="Show a reason prompt before this action runs.",
            component=self.requires_reason_checkbox,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        color = self.color_select.values[0] if self.color_select.values else "gray"
        async with get_session() as session:
            await ticket_options_repository.set_button_config(
                session, self.option_id, self.action,
                label=str(self.label_input),
                emoji=str(self.emoji_input) or None,
                color=color,
                requires_reason=bool(self.requires_reason_checkbox.value),
            )
        await interaction.response.send_message(
            content=f"{self.action.title()} button updated.", ephemeral=True
        )


class RequiredRolesModal(discord.ui.Modal, title="Required Roles"):
    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.require_all_checkbox = discord.ui.Checkbox(custom_id="require_all_roles")
        self.add_item(discord.ui.Label(
            text="Require All Roles",
            description="Require every selected role instead of any.",
            component=self.require_all_checkbox,
        ))

        self.role_select = discord.ui.RoleSelect(min_values=0, max_values=25, placeholder="Select required roles...")
        self.add_item(discord.ui.Label(text="Required Roles", component=self.role_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option, require_all_roles=bool(self.require_all_checkbox.value)
                )
                for existing_role_id in await ticket_options_repository.get_required_roles(session, self.option_id):
                    await ticket_options_repository.remove_required_role(session, self.option_id, existing_role_id)
                for role in self.role_select.values:
                    await ticket_options_repository.add_required_role(session, self.option_id, role.id)
        await interaction.response.send_message(
            content="Required roles updated.", ephemeral=True
        )


class SupportRolesModal(discord.ui.Modal, title="Support Roles"):
    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.keep_visible_checkbox = discord.ui.Checkbox(custom_id="keep_staff_visible_on_claim")
        self.add_item(discord.ui.Label(
            text="Keep Staff Visible On Claim",
            description="Support roles see claimed tickets.",
            component=self.keep_visible_checkbox,
        ))

        self.can_speak_checkbox = discord.ui.Checkbox(custom_id="staff_can_speak_on_claim")
        self.can_speak_checkbox = discord.ui.Checkbox(custom_id="staff_can_speak_on_claim")
        self.add_item(discord.ui.Label(
            text="Staff Can Speak On Claim",
            description="Support roles can reply when claimed.",
            component=self.can_speak_checkbox,
        ))

        self.role_select = discord.ui.RoleSelect(min_values=0, max_values=25, placeholder="Select support roles...")
        self.add_item(discord.ui.Label(text="Support Roles", component=self.role_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    keep_staff_visible_on_claim=bool(self.keep_visible_checkbox.value),
                    staff_can_speak_on_claim=bool(self.can_speak_checkbox.value),
                )
                for existing_role_id in await ticket_options_repository.get_support_roles(session, self.option_id):
                    await ticket_options_repository.remove_support_role(session, self.option_id, existing_role_id)
                for role in self.role_select.values:
                    await ticket_options_repository.add_support_role(session, self.option_id, role.id)
        await interaction.response.send_message(
            content="Support roles updated.", ephemeral=True
        )


class TraineeRolesModal(discord.ui.Modal, title="Trainee Roles"):
    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.can_claim_checkbox = discord.ui.Checkbox(custom_id="trainees_can_claim")
        self.add_item(discord.ui.Label(text="Trainees Can Claim", component=self.can_claim_checkbox))

        self.can_close_checkbox = discord.ui.Checkbox(custom_id="trainees_can_close")
        self.add_item(discord.ui.Label(text="Trainees Can Close", component=self.can_close_checkbox))

        self.can_speak_checkbox = discord.ui.Checkbox(custom_id="trainees_can_speak")
        self.add_item(discord.ui.Label(text="Trainees Can Speak", component=self.can_speak_checkbox))

        self.role_select = discord.ui.RoleSelect(min_values=0, max_values=25, placeholder="Select trainee roles...")
        self.add_item(discord.ui.Label(text="Trainee Roles", component=self.role_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    trainees_can_claim=bool(self.can_claim_checkbox.value),
                    trainees_can_close=bool(self.can_close_checkbox.value),
                    trainees_can_speak=bool(self.can_speak_checkbox.value),
                )
                for existing_role_id in await ticket_options_repository.get_trainee_roles(session, self.option_id):
                    await ticket_options_repository.remove_trainee_role(session, self.option_id, existing_role_id)
                for role in self.role_select.values:
                    await ticket_options_repository.add_trainee_role(session, self.option_id, role.id)
        await interaction.response.send_message(
            content="Trainee roles updated.", ephemeral=True
        )


class FormSelectModal(discord.ui.Modal, title="Form"):
    def __init__(self, option_id: int, forms: list):
        super().__init__()
        self.option_id = option_id

        options = [discord.SelectOption(label="None (No Form)", value="__none__")]
        options += [discord.SelectOption(label=f.name, value=str(f.id)) for f in forms[:24]]
        self.form_select = discord.ui.Select(placeholder="Select a form..", options=options)
        self.add_item(discord.ui.Label(text="Select Form", component=self.form_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.form_select.values[0] if self.form_select.values else "__none__"
        form_id = None if value == "__none__" else int(value)

        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(session, option, form_id=form_id)
        await interaction.response.send_message(
            content="Form updated.", ephemeral=True
        )


class MessagesModal(discord.ui.Modal, title="Messages"):
    _MESSAGE_TYPE_LABELS = {
        "greeting": "Greeting", "greeting_dm": "Greeting DM", "claim": "Claim", "move": "Move",
        "close": "Close", "close_dm": "Close DM", "reopen": "Reopen", "reopen_dm": "Reopen DM",
        "auto_close": "Auto-Close", "auto_delete": "Auto-Delete", "inactivity": "Inactivity",
        "required_roles": "Required Roles",
    }

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.type_select = discord.ui.Select(
            options=[discord.SelectOption(label=self._MESSAGE_TYPE_LABELS[t], value=t) for t in MESSAGE_TYPES]
        )
        self.add_item(discord.ui.Label(text="Message Type", component=self.type_select))

        self.content_input = discord.ui.TextInput(
            label="Message Text", style=discord.TextStyle.paragraph, max_length=1000,
            placeholder="Supports {embed} script syntax and variables like {ticket.author.mention}",
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        message_type = self.type_select.values[0] if self.type_select.values else "greeting"
        async with get_session() as session:
            await ticket_options_repository.set_message(session, self.option_id, message_type, str(self.content_input))
        await interaction.response.send_message(
            content=f"{self._MESSAGE_TYPE_LABELS.get(message_type, message_type)} message updated.",
            ephemeral=True,
        )


class AutomationModal(discord.ui.Modal, title="Automation"):
    auto_close_input = discord.ui.TextInput(label="Auto-Close Timer (minutes)", required=False, max_length=10)
    auto_delete_input = discord.ui.TextInput(label="Auto-Delete Timer (minutes)", required=False, max_length=10)
    inactivity_input = discord.ui.TextInput(label="Inactivity Timer (minutes)", required=False, max_length=10)

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

    @staticmethod
    def _parse(raw: str) -> int | None:
        raw = raw.strip()
        if not raw:
            return None
        try:
            return max(0, int(raw))
        except ValueError:
            return None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    auto_close_timer=self._parse(str(self.auto_close_input)),
                    auto_delete_timer=self._parse(str(self.auto_delete_input)),
                    inactivity_timer=self._parse(str(self.inactivity_input)),
                )
        await interaction.response.send_message(
            content="Automation timers updated.", ephemeral=True
        )


class StyleModal(discord.ui.Modal, title="Style"):
    label_input = discord.ui.TextInput(label="Label", max_length=80)
    emoji_input = discord.ui.TextInput(label="Emoji", required=False, max_length=64)
    description_input = discord.ui.TextInput(label="Description", required=False, max_length=100)

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.style_select = discord.ui.Select(options=[
            discord.SelectOption(label="Blue", value="blue"),
            discord.SelectOption(label="Gray", value="gray"),
            discord.SelectOption(label="Green", value="green"),
            discord.SelectOption(label="Red", value="red"),
        ])
        self.add_item(discord.ui.Label(text="Button Style", component=self.style_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        style = self.style_select.values[0] if self.style_select.values else "blue"
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    label=str(self.label_input),
                    emoji=str(self.emoji_input) or None,
                    button_style=style,
                    button_description=str(self.description_input) or None,
                )
        await interaction.response.send_message(
            content="Style updated.", ephemeral=True
        )


class CategoriesModal(discord.ui.Modal, title="Categories"):
    """Category/channel names or IDs typed as text (not a live select)
    to stay on the well-established TextInput API rather than the very
    new select-in-modal components - lower risk, same result."""

    default_category_input = discord.ui.TextInput(label="Default Category", required=False, placeholder="Category name or ID")
    claim_category_input = discord.ui.TextInput(label="Claim Category (optional)", required=False, placeholder="Category name or ID")
    close_category_input = discord.ui.TextInput(label="Close Category (optional)", required=False, placeholder="Category name or ID")
    transcript_channel_input = discord.ui.TextInput(label="Transcript Channel", required=False, placeholder="Channel name or ID")

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

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

        for field_name, text_input in (
            ("default_category_id", self.default_category_input),
            ("claim_category_id", self.claim_category_input),
            ("close_category_id", self.close_category_input),
        ):
            raw = str(text_input).strip()
            if not raw:
                fields[field_name] = None
                continue
            category = self._resolve_category(guild, raw)
            if category is None:
                unresolved.append(raw)
            else:
                fields[field_name] = category.id

        raw_transcript = str(self.transcript_channel_input).strip()
        if not raw_transcript:
            fields["transcript_channel_id"] = None
        else:
            transcript_channel = self._resolve_text_channel(guild, raw_transcript)
            if transcript_channel is None:
                unresolved.append(raw_transcript)
            else:
                fields["transcript_channel_id"] = transcript_channel.id

        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(session, option, **fields)

        message = "Categories updated."
        if unresolved:
            message += f"\nCouldn't find: {', '.join(unresolved)} - left unchanged."
        await interaction.response.send_message(content=message, ephemeral=True)


class NamingModal(discord.ui.Modal, title="Naming"):
    channel_name_format_input = discord.ui.TextInput(
        label="Channel Name Format", placeholder="{ticket.case}-{ticket.author.name}", max_length=100,
    )
    claim_rename_input = discord.ui.TextInput(label="Claim Rename Template", required=False, max_length=100)
    close_rename_input = discord.ui.TextInput(label="Close Rename Template", required=False, max_length=100)

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    channel_name_format=str(self.channel_name_format_input) or option.channel_name_format,
                    claim_rename_template=str(self.claim_rename_input) or None,
                    close_rename_template=str(self.close_rename_input) or None,
                )
        await interaction.response.send_message(
            content="Naming updated.", ephemeral=True
        )


class PermissionsModal(discord.ui.Modal, title="Permissions"):
    """The fully-built example: two real Checkbox components, each
    wrapped in a Label, exactly the pattern every other 'click box'
    field in the remaining Behavior branches will follow."""

    def __init__(self, option_id: int):
        super().__init__()
        self.option_id = option_id

        self.creator_can_close_checkbox = discord.ui.Checkbox(custom_id="creator_can_close")
        self.add_item(discord.ui.Label(
            text="Creator Can Close",
            description="Let the ticket creator close their ticket.",
            component=self.creator_can_close_checkbox,
        ))

        self.close_on_leave_checkbox = discord.ui.Checkbox(custom_id="close_on_leave")
        self.add_item(discord.ui.Label(
            text="Close On Leave",
            description="Auto-close if creator leaves server.",
            component=self.close_on_leave_checkbox,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            option = await ticket_options_repository.get_option(session, self.option_id)
            if option is not None:
                await ticket_options_repository.update_option(
                    session, option,
                    creator_can_close=bool(self.creator_can_close_checkbox.value),
                    close_on_leave=bool(self.close_on_leave_checkbox.value),
                )
        await interaction.response.send_message(
            content="Permissions updated.", ephemeral=True
        )