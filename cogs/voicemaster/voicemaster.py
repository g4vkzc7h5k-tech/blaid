"""VoiceMaster commands, aliases (,vm ,vc), and the voice-state
listener that creates/cleans up temp channels. All actual logic lives
in services/voicemaster_service.py - this file is just the command
layer + event wiring on top of it."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake, is_server_owner
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import voicemaster_repository
from services import premium_service, voicemaster_service


def _owner_or_admin():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
            return True
        raise commands.MissingPermissions(["administrator"])

    return commands.check(predicate)


class VoiceMaster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Persistent interface view - one instance serves every guild,
        # every temp channel, forever, and survives restarts.
        self.bot.add_view(voicemaster_service.InterfaceView())

    # ---------------------------------------------------------- listener

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        async with get_session() as session:
            cfg = await voicemaster_repository.get_config(session, member.guild.id)
            extra_hubs = await voicemaster_repository.get_extra_hubs(session, member.guild.id)

        hub_ids = set(extra_hubs)
        if cfg is not None and cfg.join_channel_id:
            hub_ids.add(cfg.join_channel_id)

        if after.channel and after.channel.id in hub_ids:
            await voicemaster_service.create_temp_channel(member, after.channel)

        elif after.channel is not None:
            await voicemaster_service.apply_join_role(member, after.channel)

        if before.channel is not None and (after.channel is None or after.channel.id != before.channel.id):
            await voicemaster_service.cleanup_if_empty(before.channel)

    # ---------------------------------------------------------- group root

    @command_meta(
        category="Voice",
        description="Sets up VoiceMaster: a category, an interface channel, and a Join To Create channel.",
        syntax=",voicemaster setup",
        examples=[",voicemaster setup"],
        permissions=["Manage Guild"],
        aliases=["vm", "vc"],
        require_args=False,
    )
    @commands.hybrid_group(name="voicemaster", aliases=["vm", "vc"], invoke_without_command=True)
    @commands.guild_only()
    async def voicemaster(self, ctx: commands.Context):
        await send_help(ctx, "voicemaster")

    @voicemaster.command(name="help")
    async def voicemaster_help(self, ctx: commands.Context):
        await send_help(ctx, "voicemaster")

    @voicemaster.command(name="setup")
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def voicemaster_setup(self, ctx: commands.Context):
        await voicemaster_service.run_setup(ctx.guild)
        embed = discord.Embed(description=f"{ctx.author.mention} **VoiceMaster Interface** has been **setup.**")
        await ctx.send(embed=embed)

    @command_meta(
        category="Voice",
        description="Creates an additional Join To Create channel (up to your plan's hub limit) - no interface, just the channel.",
        syntax=",jointocreate",
        examples=[",jointocreate"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.command(name="jointocreate", with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def jointocreate(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await voicemaster_repository.get_config(session, ctx.guild.id)
        if cfg is None or not cfg.join_channel_id:
            await ctx.error("Run `,voicemaster setup` first.")
            return

        async with get_session() as session:
            extra_hubs = await voicemaster_repository.get_extra_hubs(session, ctx.guild.id)

        allowed, limit = await premium_service.check_limit(ctx.guild.id, "jointocreate_hubs", len(extra_hubs) + 1)
        if not allowed:
            is_prem = await premium_service.is_premium(ctx.guild.id, "server")
            await ctx.error(premium_service.limit_reached_message("Join to Create hubs", limit, is_prem))
            return

        category = ctx.guild.get_channel(cfg.category_id) if cfg.category_id else None
        try:
            channel = await ctx.guild.create_voice_channel(
                "Join to Create", category=category, reason=f"Extra hub by {ctx.author}"
            )
        except discord.Forbidden:
            await ctx.error("I don't have permission to create a voice channel.")
            return

        async with get_session() as session:
            await voicemaster_repository.add_extra_hub(session, ctx.guild.id, channel.id)

        await ctx.success(f"Created {channel.mention} as an additional Join to Create channel.")

    @command_meta(
        category="Voice",
        description="Completely removes VoiceMaster: category, interface, Join To Create, temp channels, and all configuration.",
        syntax=",voicemaster reset",
        examples=[",voicemaster reset"],
        permissions=["Server Owner", "Administrator"],
        require_args=False,
    )
    @voicemaster.command(name="reset")
    @_owner_or_admin()
    async def voicemaster_reset(self, ctx: commands.Context):
        await voicemaster_service.reset(ctx.guild)
        embed = discord.Embed(description=f"{ctx.author.mention} **VoiceMaster** has been **reset.**")
        await ctx.send(embed=embed)

    @command_meta(
        category="Voice",
        description="Administrator only. Resends the VoiceMaster interface into the current channel if the original message was deleted.",
        syntax=",voicemaster sendinterface",
        examples=[",voicemaster sendinterface"],
        permissions=["Administrator"],
        require_args=False,
    )
    @voicemaster.command(name="sendinterface")
    @has_permission_or_fake("administrator")
    async def voicemaster_sendinterface(self, ctx: commands.Context):
        await voicemaster_service.send_interface(ctx.channel)
        await ctx.success("Interface sent.")

    # ---------------------------------------------------------- server-owner config

    @command_meta(
        category="Voice",
        description="Server owner only. Sets the category temp voice channels are created in.",
        syntax=",voicemaster category <category>",
        examples=[",voicemaster category Voice Channels"],
        permissions=["Server Owner"],
    )
    @voicemaster.command(name="category")
    @is_server_owner()
    async def voicemaster_category(self, ctx: commands.Context, *, category: discord.CategoryChannel):
        async with get_session() as session:
            cfg = await voicemaster_repository.get_or_create_config(session, ctx.guild.id)
            cfg.owner_category_id = category.id
            await session.commit()
        await ctx.success(f"New temp voice channels will now be created in **{category.name}**.")

    @command_meta(
        category="Voice",
        description="Server owner only. Sets a role members receive when they join a temp voice channel.",
        syntax=",voicemaster joinrole <role>",
        examples=[",voicemaster joinrole @In Voice"],
        permissions=["Server Owner"],
    )
    @voicemaster.command(name="joinrole")
    @is_server_owner()
    async def voicemaster_joinrole(self, ctx: commands.Context, *, role: discord.Role):
        async with get_session() as session:
            cfg = await voicemaster_repository.get_or_create_config(session, ctx.guild.id)
            cfg.join_role_id = role.id
            await session.commit()
        await ctx.success(f"Members will now receive {role.mention} when joining a temp voice channel.")

    # ---------------------------------------------------------- owner actions (text commands)

    @command_meta(
        category="Voice",
        description="Locks your voice channel so no one new can join.",
        syntax=",voicemaster lock",
        examples=[",voicemaster lock"],
        require_args=False,
    )
    @voicemaster.command(name="lock")
    async def voicemaster_lock(self, ctx: commands.Context):
        success, message = await voicemaster_service.lock(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Unlocks your voice channel.",
        syntax=",voicemaster unlock",
        examples=[",voicemaster unlock"],
        require_args=False,
    )
    @voicemaster.command(name="unlock")
    async def voicemaster_unlock(self, ctx: commands.Context):
        success, message = await voicemaster_service.unlock(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Hides your voice channel from everyone who isn't already in it.",
        syntax=",voicemaster hide",
        examples=[",voicemaster hide"],
        require_args=False,
    )
    @voicemaster.command(name="hide")
    async def voicemaster_hide(self, ctx: commands.Context):
        success, message = await voicemaster_service.hide(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Makes a previously hidden voice channel visible again.",
        syntax=",voicemaster reveal",
        examples=[",voicemaster reveal"],
        require_args=False,
    )
    @voicemaster.command(name="reveal")
    async def voicemaster_reveal(self, ctx: commands.Context):
        success, message = await voicemaster_service.reveal(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Renames your voice channel.",
        syntax=",voicemaster rename <name>",
        examples=[",voicemaster rename Chill Zone"],
    )
    @voicemaster.command(name="rename")
    async def voicemaster_rename(self, ctx: commands.Context, *, name: str):
        success, message = await voicemaster_service.rename(ctx.guild, ctx.author, name)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Sets the user limit on your voice channel.",
        syntax=",voicemaster limit <number>",
        examples=[",voicemaster limit 5"],
    )
    @voicemaster.command(name="limit")
    async def voicemaster_limit(self, ctx: commands.Context, limit: int):
        success, message = await voicemaster_service.set_limit(ctx.guild, ctx.author, limit)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Sets the bitrate (in kbps) of your voice channel.",
        syntax=",voicemaster bitrate <kbps>",
        examples=[",voicemaster bitrate 96"],
    )
    @voicemaster.command(name="bitrate")
    async def voicemaster_bitrate(self, ctx: commands.Context, kbps: int):
        success, message = await voicemaster_service.set_bitrate(ctx.guild, ctx.author, kbps)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Deletes your voice channel.",
        syntax=",voicemaster delete",
        examples=[",voicemaster delete"],
        require_args=False,
    )
    @voicemaster.command(name="delete")
    async def voicemaster_delete(self, ctx: commands.Context):
        success, message = await voicemaster_service.delete_channel(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Claims ownership of a voice channel whose owner has left.",
        syntax=",voicemaster claim",
        examples=[",voicemaster claim"],
        require_args=False,
    )
    @voicemaster.command(name="claim")
    async def voicemaster_claim(self, ctx: commands.Context):
        success, message = await voicemaster_service.claim(ctx.guild, ctx.author)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Permits a member to join your locked/hidden voice channel.",
        syntax=",voicemaster permit <user>",
        examples=[",voicemaster permit @User"],
    )
    @voicemaster.command(name="permit")
    async def voicemaster_permit(self, ctx: commands.Context, user: discord.Member):
        success, message = await voicemaster_service.permit_user(ctx.guild, ctx.author, user)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Rejects a member from your voice channel, removing and blocking them.",
        syntax=",voicemaster reject <user>",
        examples=[",voicemaster reject @User"],
    )
    @voicemaster.command(name="reject")
    async def voicemaster_reject(self, ctx: commands.Context, user: discord.Member):
        success, message = await voicemaster_service.reject_user(ctx.guild, ctx.author, user)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Voice",
        description="Shows the current settings of your voice channel.",
        syntax=",voicemaster status",
        examples=[",voicemaster status"],
        require_args=False,
    )
    @voicemaster.command(name="status")
    async def voicemaster_status(self, ctx: commands.Context):
        embed, error = await voicemaster_service.get_status_embed(ctx.guild, ctx.author)
        if error:
            await ctx.error(error)
            return
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceMaster(bot))
