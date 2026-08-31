"""Role-assignment business logic for autorole, reaction roles, and button roles."""

from __future__ import annotations

import discord

from database.database import get_session
from repositories import roles_repository


async def apply_autoroles(member: discord.Member) -> None:
    async with get_session() as session:
        autoroles = await roles_repository.get_autoroles(session, member.guild.id)

    roles = [member.guild.get_role(a.role_id) for a in autoroles]
    roles = [r for r in roles if r is not None]
    if not roles:
        return

    try:
        await member.add_roles(*roles, reason="Autorole")
    except discord.Forbidden:
        pass


async def toggle_role(member: discord.Member, role_id: int) -> bool:
    """Adds the role if the member doesn't have it, removes it if they
    do. Returns True if the role was added, False if removed."""
    role = member.guild.get_role(role_id)
    if role is None:
        return False

    has_role = role in member.roles
    try:
        if has_role:
            await member.remove_roles(role, reason="Role toggle")
        else:
            await member.add_roles(role, reason="Role toggle")
    except discord.Forbidden:
        pass
    return not has_role


STYLE_MAP = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


class ButtonRolePanelView(discord.ui.View):
    """Persistent view for a button-role panel message. One button per
    configured role; custom_id encodes the message_id so a restart can
    re-register it from the database."""

    def __init__(self, message_id: int, buttons: list[tuple[str, str, int, str, str | None]]):
        # buttons: list of (custom_id, label, role_id, style, emoji)
        super().__init__(timeout=None)
        self.message_id = message_id
        for custom_id, label, role_id, style, emoji in buttons:
            button = discord.ui.Button(
                label=label, style=STYLE_MAP.get(style, discord.ButtonStyle.secondary),
                custom_id=custom_id, emoji=emoji,
            )
            button.callback = self._make_callback(role_id)
            self.add_item(button)

    def _make_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction):
            added = await toggle_role(interaction.user, role_id)
            role = interaction.guild.get_role(role_id)
            role_name = role.mention if role else "that role"
            verb = "Added" if added else "Removed"
            await interaction.response.send_message(f"{verb} {role_name}.", ephemeral=True)
        return callback