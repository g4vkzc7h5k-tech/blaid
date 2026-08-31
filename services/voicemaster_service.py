"""
VoiceMaster central service.

Every VoiceMaster command, interface button, and voice-state listener
routes through the functions in this file - there is exactly one
implementation of "lock a channel", "claim a channel", etc., shared by
the command layer and the button layer, per the spec's requirement
that nothing be duplicated between them.
"""

from __future__ import annotations

import discord

from database.database import get_session
from repositories import voicemaster_repository
from core.variables import resolve_variables

ICONS = {
    "lock": "<:emoji_5:1543849590510587966>",
    "unlock": "<:emoji_6:1543849619241304164>",
    "hide": "<:emoji_11:1543849750871146586>",
    "rename": "<:emoji_13:1543853047866982430>",
    "claim": "<:emoji_10:1543849724170215425>",
    "limit": "<:emoji_9:1543849701689004073>",
    "delete": "<:emoji_8:1543849676791611462>",
}


# ---------------------------------------------------------- setup / reset

async def run_setup(guild: discord.Guild) -> dict[str, bool]:
    async with get_session() as session:
        cfg = await voicemaster_repository.get_or_create_config(session, guild.id)

        category = guild.get_channel(cfg.category_id) if cfg.category_id else None
        if category is None:
            category = discord.utils.get(guild.categories, name="VoiceMaster")
        if category is None:
            category = await guild.create_category("VoiceMaster", reason="VoiceMaster setup")
        cfg.category_id = category.id

        interface_channel = guild.get_channel(cfg.interface_channel_id) if cfg.interface_channel_id else None
        if interface_channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True),
                guild.me: discord.PermissionOverwrite(send_messages=True, view_channel=True),
            }
            interface_channel = await guild.create_text_channel(
                "interface", category=category, overwrites=overwrites, reason="VoiceMaster setup"
            )
        cfg.interface_channel_id = interface_channel.id

        join_channel = guild.get_channel(cfg.join_channel_id) if cfg.join_channel_id else None
        if join_channel is None:
            join_channel = discord.utils.get(category.voice_channels, name="Join To Create")
        if join_channel is None:
            join_channel = await guild.create_voice_channel("Join To Create", category=category, reason="VoiceMaster setup")
        cfg.join_channel_id = join_channel.id

        await session.commit()

    message_id = await send_interface(interface_channel)
    if message_id is not None:
        async with get_session() as session:
            cfg = await voicemaster_repository.get_or_create_config(session, guild.id)
            cfg.interface_message_id = message_id
            await session.commit()

    return {
        "Category": True,
        "Interface Channel": True,
        "Join To Create Channel": True,
    }


async def reset(guild: discord.Guild) -> None:
    async with get_session() as session:
        cfg = await voicemaster_repository.get_config(session, guild.id)
        if cfg is None:
            return

        category_id = cfg.category_id
        interface_channel_id = cfg.interface_channel_id
        join_channel_id = cfg.join_channel_id

        temp_channel_ids = await voicemaster_repository.delete_all_temp_channels(session, guild.id)
        await voicemaster_repository.reset_config(session, guild.id)

    for channel_id in temp_channel_ids:
        channel = guild.get_channel(channel_id)
        if channel is not None:
            try:
                await channel.delete(reason="VoiceMaster reset")
            except discord.HTTPException:
                pass

    for channel_id in (join_channel_id, interface_channel_id):
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                try:
                    await channel.delete(reason="VoiceMaster reset")
                except discord.HTTPException:
                    pass

    if category_id:
        category = guild.get_channel(category_id)
        if category is not None:
            try:
                await category.delete(reason="VoiceMaster reset")
            except discord.HTTPException:
                pass


# ---------------------------------------------------------- interface

def build_interface_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="VoiceMaster Interface",
        description=(
            "**Manage your voice channel by using the buttons below.**\n\n"
            "**Button usage:**\n"
            f"{ICONS['lock']} `Lock` the voice channel\n"
            f"{ICONS['unlock']} `Unlock` the voice channel\n"
            f"{ICONS['hide']} `Hide` the voice channel\n"
            f"{ICONS['rename']} `Rename` the voice channel\n"
            f"{ICONS['claim']} `Claim` the voice channel\n"
            f"{ICONS['limit']} `Limit` the user limit\n"
            f"{ICONS['delete']} `Delete` the voice channel"
        ),
    )
    if guild.icon:
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
        embed.set_thumbnail(url=guild.icon.url)
    else:
        embed.set_author(name=guild.name)
    return embed


async def send_interface(channel: discord.abc.Messageable) -> int | None:
    """Sends the interface embed + buttons into any channel (the main
    interface channel, or a freshly created temp voice channel's own
    chat). Returns the sent message's ID."""
    guild = getattr(channel, "guild", None)
    embed = build_interface_embed(guild) if guild else discord.Embed(title="VoiceMaster Interface")
    view = InterfaceView()
    try:
        message = await channel.send(embed=embed, view=view)
    except discord.HTTPException:
        return None
    return message.id


# ---------------------------------------------------------- temp channel lifecycle

async def create_temp_channel(member: discord.Member, join_channel: discord.VoiceChannel) -> discord.VoiceChannel | None:
    guild = member.guild
    async with get_session() as session:
        cfg = await voicemaster_repository.get_or_create_config(session, guild.id)

    target_category_id = cfg.owner_category_id or cfg.category_id
    category = guild.get_channel(target_category_id) if target_category_id else join_channel.category

    name = resolve_variables(cfg.default_name, member=member)[:100]

    overwrites = {
        member: discord.PermissionOverwrite(manage_channels=True, manage_roles=True, connect=True, view_channel=True),
    }

    try:
        new_channel = await guild.create_voice_channel(
            name=name, category=category, overwrites=overwrites, reason=f"VoiceMaster: created for {member}"
        )
        await member.move_to(new_channel)
    except discord.HTTPException:
        return None

    async with get_session() as session:
        await voicemaster_repository.create_temp_channel(session, new_channel.id, guild.id, member.id)

    if cfg.join_role_id:
        role = guild.get_role(cfg.join_role_id)
        if role is not None:
            try:
                await member.add_roles(role, reason="VoiceMaster join role")
            except discord.Forbidden:
                pass

    await send_interface(new_channel)
    return new_channel


async def cleanup_if_empty(channel: discord.VoiceChannel) -> None:
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        if temp is not None and len(channel.members) == 0:
            await voicemaster_repository.delete_temp_channel(session, channel.id)
            try:
                await channel.delete(reason="VoiceMaster: empty temp channel")
            except discord.NotFound:
                pass


async def apply_join_role(member: discord.Member, channel: discord.VoiceChannel) -> None:
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        if temp is None:
            return
        cfg = await voicemaster_repository.get_config(session, member.guild.id)

    if cfg is not None and cfg.join_role_id:
        role = member.guild.get_role(cfg.join_role_id)
        if role is not None and role not in member.roles:
            try:
                await member.add_roles(role, reason="VoiceMaster join role")
            except discord.Forbidden:
                pass


# ---------------------------------------------------------- owner actions
# Every function below returns (success: bool, message: str).

async def _get_owned(guild: discord.Guild, actor: discord.Member, *, require_owner: bool = True):
    """Resolves the actor's current voice channel + its temp-channel
    record, checking ownership if required. Returns (channel, temp,
    error_message) - error_message is None on success."""
    if actor.voice is None or actor.voice.channel is None:
        return None, None, "You need to be in a voice channel to use this."

    channel = actor.voice.channel
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)

    if temp is None:
        return None, None, "This is not a VoiceMaster channel."

    if require_owner and temp.owner_id != actor.id:
        return None, None, "You don't own this voice channel."

    return channel, temp, None


async def lock(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_locked(session, temp, True)
    try:
        await channel.set_permissions(guild.default_role, connect=False)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, "Channel locked."


async def unlock(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_locked(session, temp, False)
    try:
        await channel.set_permissions(guild.default_role, connect=None)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, "Channel unlocked."


async def hide(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_hidden(session, temp, True)
    try:
        await channel.set_permissions(guild.default_role, view_channel=False)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, "Channel hidden."


async def reveal(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_hidden(session, temp, False)
    try:
        await channel.set_permissions(guild.default_role, view_channel=None)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, "Channel revealed."


async def rename(guild: discord.Guild, actor: discord.Member, new_name: str) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    new_name = new_name.strip()[:100]
    if not new_name:
        return False, "Name cannot be empty."
    try:
        await channel.edit(name=new_name)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, f"Channel renamed to `{new_name}`."


async def set_limit(guild: discord.Guild, actor: discord.Member, limit: int) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    limit = max(0, min(limit, 99))
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_user_limit(session, temp, limit)
    try:
        await channel.edit(user_limit=limit)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, f"User limit set to `{limit or 'unlimited'}`."


async def set_bitrate(guild: discord.Guild, actor: discord.Member, kbps: int) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    max_kbps = guild.bitrate_limit // 1000
    kbps = max(8, min(kbps, max_kbps))
    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_bitrate(session, temp, kbps * 1000)
    try:
        await channel.edit(bitrate=kbps * 1000)
    except discord.Forbidden:
        return False, "I don't have permission to edit that channel."
    return True, f"Bitrate set to `{kbps}kbps`."


async def delete_channel(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        await voicemaster_repository.delete_temp_channel(session, channel.id)
    try:
        await channel.delete(reason=f"VoiceMaster: deleted by owner {actor}")
    except discord.Forbidden:
        return False, "I don't have permission to delete that channel."
    return True, "Channel deleted."


async def claim(guild: discord.Guild, actor: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor, require_owner=False)
    if error:
        return False, error

    if temp.owner_id == actor.id:
        return False, "You already own this channel."

    current_owner = guild.get_member(temp.owner_id)
    if current_owner is not None and current_owner in channel.members:
        return False, "The current owner is still in the channel."

    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)
        await voicemaster_repository.set_owner(session, temp, actor.id)

    try:
        await channel.set_permissions(actor, manage_channels=True, manage_roles=True, connect=True, view_channel=True)
    except discord.Forbidden:
        pass

    return True, "You are now the owner of this channel."


async def permit_user(guild: discord.Guild, actor: discord.Member, target: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        await voicemaster_repository.add_permit(session, channel.id, target.id)
    try:
        await channel.set_permissions(target, connect=True, view_channel=True)
    except discord.Forbidden:
        pass
    return True, f"{target.mention} is now permitted to join."


async def reject_user(guild: discord.Guild, actor: discord.Member, target: discord.Member) -> tuple[bool, str]:
    channel, temp, error = await _get_owned(guild, actor)
    if error:
        return False, error
    async with get_session() as session:
        await voicemaster_repository.add_reject(session, channel.id, target.id)
    try:
        await channel.set_permissions(target, connect=False, view_channel=False)
    except discord.Forbidden:
        pass
    if target in channel.members:
        try:
            await target.move_to(None)
        except discord.Forbidden:
            pass
    return True, f"{target.mention} has been rejected from this channel."


async def get_status_embed(guild: discord.Guild, actor: discord.Member) -> tuple[discord.Embed | None, str | None]:
    channel, temp, error = await _get_owned(guild, actor, require_owner=False)
    if error:
        return None, error

    async with get_session() as session:
        temp = await voicemaster_repository.get_temp_channel(session, channel.id)

    embed = discord.Embed(title=f"VoiceMaster Status — {channel.name}")
    embed.add_field(name="Owner", value=f"<@{temp.owner_id}>", inline=True)
    embed.add_field(name="Locked", value="Yes" if temp.locked else "No", inline=True)
    embed.add_field(name="Hidden", value="Yes" if temp.hidden else "No", inline=True)
    embed.add_field(name="User Limit", value=str(temp.user_limit) if temp.user_limit else "Unlimited", inline=True)
    embed.add_field(name="Bitrate", value=f"{temp.bitrate // 1000}kbps", inline=True)
    embed.add_field(name="Members", value=str(len(channel.members)), inline=True)
    return embed, None


# ---------------------------------------------------------- interactive UI

class RenameModal(discord.ui.Modal, title="Rename Voice Channel"):
    name = discord.ui.TextInput(label="New channel name", max_length=100)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        success, message = await rename(interaction.guild, interaction.user, str(self.name))
        embed = discord.Embed(description=message)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LimitModal(discord.ui.Modal, title="Set User Limit"):
    limit = discord.ui.TextInput(label="User limit (0 = unlimited)", max_length=2)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            limit_value = int(str(self.limit))
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(description="Please enter a whole number."), ephemeral=True
            )
            return
        success, message = await set_limit(interaction.guild, interaction.user, limit_value)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)


class InterfaceView(discord.ui.View):
    """One persistent, guild-agnostic view. Every button figures out
    the clicking user's current voice channel at click-time - nothing
    is baked into the custom_id, so a single registered instance
    serves every guild and every temp channel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="<:emoji_11:1541277626369446009>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_lock")
    async def lock_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        success, message = await lock(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)

    @discord.ui.button(emoji="<:emoji_10:1541277608354783403>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_unlock")
    async def unlock_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        success, message = await unlock(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)

    @discord.ui.button(emoji="<:emoji_4:1541277464838283354>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_hide")
    async def hide_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        success, message = await hide(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)

    @discord.ui.button(emoji="<:emoji_8:1541277569620508702>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_rename")
    async def rename_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        channel, temp, error = await _get_owned(interaction.guild, interaction.user)
        if error:
            await interaction.response.send_message(embed=discord.Embed(description=error), ephemeral=True)
            return
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(emoji="<:emoji_5:1541277485164003338>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_claim")
    async def claim_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        success, message = await claim(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)

    @discord.ui.button(emoji="<:emoji_6:1541277509210079293>", style=discord.ButtonStyle.secondary, custom_id="blade_vm_limit")
    async def limit_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        channel, temp, error = await _get_owned(interaction.guild, interaction.user)
        if error:
            await interaction.response.send_message(embed=discord.Embed(description=error), ephemeral=True)
            return
        await interaction.response.send_modal(LimitModal())

    @discord.ui.button(emoji="<:emoji_7:1541277526478037083>", style=discord.ButtonStyle.danger, custom_id="blade_vm_delete")
    async def delete_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        success, message = await delete_channel(interaction.guild, interaction.user)
        await interaction.response.send_message(embed=discord.Embed(description=message), ephemeral=True)