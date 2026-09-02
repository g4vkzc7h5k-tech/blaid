"""Core moderation commands."""

from __future__ import annotations

import datetime
import re

import discord
from discord.ext import commands

from core import embeds
from core.checks import bot_can_act_on, check_owner_or_antinuke_admin, has_permission_or_fake, is_owner_or_antinuke_admin, requires_premium, validate_moderation_target
from core.command_meta import command_meta
from core.converters import Duration
from core.helpers import InvalidDuration, format_duration, parse_duration
from core.help_formatter import send_help
from core.paginator import Paginator
from database.database import get_session
from repositories import denyperm_repository, guild_config_repository, lockdown_repository, moderation_repository, nickname_repository, verification_repository
from services import moderation_service, security_service

_MESSAGE_LINK_RE = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


async def _resolve_message(ctx: commands.Context, ref: str) -> discord.Message | None:
    """Accepts a raw message ID or a full message link and returns the
    resolved discord.Message, or None if it can't be found."""
    ref = ref.strip()

    match = _MESSAGE_LINK_RE.search(ref)
    if match:
        _guild_id, channel_id, message_id = (int(g) for g in match.groups())
        channel = ctx.guild.get_channel(channel_id) or ctx.channel
        try:
            return await channel.fetch_message(message_id)
        except discord.HTTPException:
            return None

    if ref.isdigit():
        try:
            return await ctx.channel.fetch_message(int(ref))
        except discord.HTTPException:
            return None

    return None


async def _run_purge(ctx: commands.Context, amount: int, predicate) -> None:
    """Shared purge runner - deletes the invoking command message first
    (always), then scans up to `amount` messages, deleting any that
    match `predicate` (or everything, if predicate is None)."""
    amount = max(1, min(amount, 500))
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    check = predicate if predicate is not None else (lambda message: True)
    deleted = await ctx.channel.purge(limit=amount, check=check)
    confirmation = await ctx.send(embed=discord.Embed(description=f"Deleted {len(deleted)} message(s)."))
    await confirmation.delete(delay=2)


class NukeConfirmView(discord.ui.View):
    """Red Nuke / grey Cancel - only the command author can answer."""

    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.confirmed: bool | None = None
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your confirmation to answer.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Nuke", style=discord.ButtonStyle.danger)
    async def nuke_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick:
            return
        async with get_session() as session:
            forced = await nickname_repository.get_forced_nickname(session, after.guild.id, after.id)
        if forced is not None and after.nick != forced:
            try:
                await after.edit(nick=forced, reason="Forced nickname")
            except discord.Forbidden:
                pass

    # ---------------------------------------------------------- ban / hardban

    @command_meta(
        category="Moderation",
        description="Permanently bans a member from the server.",
        syntax=",ban <member> [reason]",
        examples=[",ban @User Breaking the rules"],
        permissions=["Ban Members"],
    )
    @commands.hybrid_command(name="ban")
    @has_permission_or_fake("ban_members")
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot ban this member - their role is above mine.")
            return

        await moderation_service.send_punishment_dm(member, ctx.guild, "banned", ctx.author, reason)
        await ctx.guild.ban(member, reason=f"{ctx.author}: {reason}")
        await moderation_service.log_and_announce(
            ctx.guild, "ban", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )
        await ctx.message.add_reaction("👍")

    @command_meta(
        category="Moderation",
        description="Unbans a previously banned user by ID. If they were banned via ,hardban, only the server owner or an antinuke admin can unban them.",
        syntax=",unban <user_id> [reason]",
        examples=[",unban 123456789012345678 Appeal accepted"],
        permissions=["Ban Members"],
    )
    @commands.hybrid_command(name="unban")
    @has_permission_or_fake("ban_members")
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        async with get_session() as session:
            hardbanned = await moderation_repository.is_hardban(session, ctx.guild.id, user_id)

        if hardbanned and not await check_owner_or_antinuke_admin(ctx):
            await ctx.error("This user was hardbanned - only the server owner or an antinuke admin can unban them.")
            return

        user = discord.Object(id=user_id)
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except discord.NotFound:
            await ctx.error("That user is not banned.")
            return

        try:
            fetched_user = await self.bot.fetch_user(user_id)
            await moderation_service.send_punishment_dm(fetched_user, ctx.guild, "unbanned", ctx.author, reason)
        except discord.HTTPException:
            pass

        if hardbanned:
            async with get_session() as session:
                await moderation_repository.clear_hardban(session, ctx.guild.id, user_id)

        await moderation_service.log_and_announce(
            ctx.guild, "unban", ctx.author,
            target_id=user_id, target_mention=f"<@{user_id}>", reason=reason,
        )
        await ctx.message.add_reaction("👍")

    @command_meta(
        category="Moderation",
        description="Bans a member and deletes their last 7 days of messages. Server owner or antinuke admins only. Unbanning them later also requires the same permission.",
        syntax=",hardban <member> [reason]",
        examples=[",hardban @User Nuke attempt"],
        permissions=["Server Owner / Antinuke Admin"],
    )
    @commands.hybrid_command(name="hardban")
    @is_owner_or_antinuke_admin()
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def hardban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot ban this member - their role is above mine.")
            return

        await moderation_service.send_punishment_dm(member, ctx.guild, "banned", ctx.author, reason)
        await ctx.guild.ban(member, reason=f"{ctx.author}: {reason}", delete_message_seconds=604800)

        async with get_session() as session:
            await moderation_repository.mark_hardban(session, ctx.guild.id, member.id)

        await moderation_service.log_and_announce(
            ctx.guild, "hardban", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )
        await ctx.message.add_reaction("👍")


    # ---------------------------------------------------------- softban

    @command_meta(
        category="Moderation",
        description="Ban then immediately unban a user to delete their recent messages.",
        syntax=",softban <member> [reason]",
        examples=[",softban @User Spamming"],
        permissions=["Ban Members"],
    )
    @commands.command(name="softban", with_app_command=False)
    @has_permission_or_fake("ban_members")
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot softban this member - their role is above mine.")
            return

        await moderation_service.try_dm(member, f"You were softbanned from **{ctx.guild.name}**.\nReason: {reason}")

        try:
            await ctx.guild.ban(member, reason=f"{ctx.author}: {reason} (softban)", delete_message_seconds=86400)
            await ctx.guild.unban(discord.Object(id=member.id), reason=f"{ctx.author}: softban cleanup")
        except discord.Forbidden:
            await ctx.error("I don't have permission to do that.")
            return

        await moderation_service.log_and_announce(
            ctx.guild, "softban", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        embed = discord.Embed(
            description=f"{ctx.author.mention}: **{member}** has been softbanned.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


    # ---------------------------------------------------------- staffstrip

    @command_meta(
        category="Moderation",
        description="Strip staff roles from a member.",
        syntax=",staffstrip <member> [reason]",
        examples=[",staffstrip @User Account compromised"],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.command(name="staffstrip", with_app_command=False)
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def staffstrip(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = "No reason provided"):
        if member is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: You need to provide `member`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot strip roles from this member - their role is above mine.")
            return

        removed = await security_service.strip_staff_roles(ctx.guild, member, reason=f"{ctx.author}: {reason}")

        if not removed:
            await ctx.error(f"**{member}** has no staff roles I can remove.")
            return

        await moderation_service.log_and_announce(
            ctx.guild, "staffstrip", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        role_list = ", ".join(r.mention for r in removed)
        embed = discord.Embed(
            description=f"{ctx.author.mention}: Stripped staff roles from **{member}**: {role_list}",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


    # ---------------------------------------------------------- strip

    @command_meta(
        category="Moderation",
        description="Strip dangerous and staff roles from a member.",
        syntax=",strip <member> [reason]",
        examples=[",strip @User Account compromised"],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.command(name="strip", with_app_command=False)
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def strip(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = "No reason provided"):
        if member is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: You need to provide `member`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot strip roles from this member - their role is above mine.")
            return

        removed = await security_service.strip_all_roles(ctx.guild, member, reason=f"{ctx.author}: {reason}")

        if not removed:
            await ctx.error(f"**{member}** has no roles I can remove.")
            return

        await moderation_service.log_and_announce(
            ctx.guild, "strip", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        role_list = ", ".join(r.mention for r in removed)
        embed = discord.Embed(
            description=f"{ctx.author.mention}: Stripped roles from **{member}**: {role_list}",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- forcenickname

    @command_meta(
        category="Moderation",
        description="Forces a nickname on a member, reverting any change they make. Run again with no nickname to remove the force.",
        syntax=",forcenickname <member> [nickname]",
        examples=[",forcenickname @User Timeout", ",forcenickname @User"],
        permissions=["Manage Guild"],
        aliases=["fn"],
        require_args=False,
    )
    @commands.hybrid_command(name="forcenickname", aliases=["fn"])
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.guild_only()
    async def forcenickname(self, ctx: commands.Context, member: discord.Member, *, nickname: str = None):
        if nickname is None:
            async with get_session() as session:
                removed = await nickname_repository.remove_forced_nickname(session, ctx.guild.id, member.id)
            if removed:
                await ctx.success(f"{ctx.author.mention}: Removed the forced nickname from **{member}** - they can change it again.")
            else:
                await ctx.info(f"{ctx.author.mention}: **{member}** doesn't have a forced nickname.")
            return

        try:
            await member.edit(nick=nickname[:32], reason=f"Forced nickname by {ctx.author}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to change that member's nickname.")
            return

        async with get_session() as session:
            await nickname_repository.set_forced_nickname(session, ctx.guild.id, member.id, nickname[:32])

        await ctx.success(f"{ctx.author.mention}: **{member}**'s nickname is now forced to `{nickname[:32]}`.")

    # ---------------------------------------------------------- picperms

    @command_meta(
        category="Moderation",
        description="Toggles Embed Links and Attach Files permissions for a member, scoped to the current channel only. Run again to revoke.",
        syntax=",picperms <member>",
        examples=[",picperms @User"],
        permissions=["Manage Roles"],
        aliases=["pic", "pictureperms", "picture"],
    )
    @commands.hybrid_command(name="picperms", aliases=["pic", "pictureperms", "picture"])
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def picperms(self, ctx: commands.Context, member: discord.Member):
        overwrite = ctx.channel.overwrites_for(member)
        has_perms = bool(overwrite.embed_links and overwrite.attach_files)

        if has_perms:
            overwrite.embed_links = None
            overwrite.attach_files = None
            await ctx.channel.set_permissions(
                member, overwrite=overwrite, reason=f"Picture permissions revoked by {ctx.author}"
            )
            await moderation_service.log_and_announce(
                ctx.guild, "picperms_revoke", ctx.author,
                target_id=member.id, target_mention=member.mention,
                reason=f"Revoked picture permissions for {member} in {ctx.channel.mention}",
            )
            await ctx.success(f"{ctx.author.mention}: Revoked picture permissions from {member.mention} in {ctx.channel.mention}.")
        else:
            overwrite.embed_links = True
            overwrite.attach_files = True
            await ctx.channel.set_permissions(
                member, overwrite=overwrite, reason=f"Picture permissions granted by {ctx.author}"
            )
            await moderation_service.log_and_announce(
                ctx.guild, "picperms_grant", ctx.author,
                target_id=member.id, target_mention=member.mention,
                reason=f"Granted picture permissions for {member} in {ctx.channel.mention}",
            )
            await ctx.success(f"{ctx.author.mention}: Granted picture permissions to {member.mention} in {ctx.channel.mention}.")

    # ---------------------------------------------------------- denyperm

    @command_meta(
        category="Moderation",
        description="Blocks permissions from being assigned via role commands (currently enforced by ,fakepermissions add).",
        syntax=",denyperm",
        examples=[",denyperm"],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.hybrid_group(name="denyperm", invoke_without_command=True)
    @has_permission_or_fake("administrator")
    @commands.guild_only()
    async def denyperm(self, ctx: commands.Context):
        async with get_session() as session:
            denied = await denyperm_repository.get_denied_permissions(session, ctx.guild.id)

        if not denied:
            await ctx.warn(f"{ctx.author.mention}: No permissions are blocked from role assignment.")
            return

        await ctx.send(embed=discord.Embed(
            description=f"{ctx.author.mention}: **Blocked Permissions**: {', '.join(f'`{p}`' for p in denied)}"
        ))

    @denyperm.command(name="help")
    async def denyperm_help(self, ctx: commands.Context):
        await send_help(ctx, "denyperm")

    @command_meta(
        category="Moderation",
        description="Blocks a permission from being assigned via role commands.",
        syntax=",denyperm add <permission>",
        examples=[",denyperm add administrator"],
        permissions=["Administrator"],
    )
    @denyperm.command(name="add")
    @has_permission_or_fake("administrator")
    async def denyperm_add(self, ctx: commands.Context, permission: str):
        permission = permission.lower()
        if permission not in discord.Permissions.VALID_FLAGS:
            await ctx.error(f"`{permission}` is not a valid permission name. Run `,denyperm available` to see the list.")
            return

        async with get_session() as session:
            added = await denyperm_repository.add_denied_permission(session, ctx.guild.id, permission)

        if added:
            await ctx.success(f"{ctx.author.mention}: Blocked **{permission}** from being assigned via role commands.")
        else:
            await ctx.error(f"`{permission}` is already blocked.")

    @command_meta(
        category="Moderation",
        description="Removes a permission from the block list.",
        syntax=",denyperm remove <permission>",
        examples=[",denyperm remove administrator"],
        permissions=["Administrator"],
    )
    @denyperm.command(name="remove")
    @has_permission_or_fake("administrator")
    async def denyperm_remove(self, ctx: commands.Context, permission: str):
        permission = permission.lower()
        async with get_session() as session:
            removed = await denyperm_repository.remove_denied_permission(session, ctx.guild.id, permission)

        if removed:
            await ctx.success(f"{ctx.author.mention}: **{permission}** can be assigned via role commands again.")
        else:
            await ctx.error(f"`{permission}` isn't blocked.")

    @command_meta(
        category="Moderation",
        description="Clears every blocked permission.",
        syntax=",denyperm clear",
        examples=[",denyperm clear"],
        permissions=["Administrator"],
        require_args=False,
    )
    @denyperm.command(name="clear")
    @has_permission_or_fake("administrator")
    async def denyperm_clear(self, ctx: commands.Context):
        async with get_session() as session:
            count = await denyperm_repository.clear_denied_permissions(session, ctx.guild.id)
        await ctx.success(f"{ctx.author.mention}: Cleared {count} blocked permission(s).")

    @command_meta(
        category="Moderation",
        description="Shows every valid Discord permission name that can be blocked.",
        syntax=",denyperm available",
        examples=[",denyperm available"],
        permissions=["Administrator"],
        require_args=False,
    )
    @denyperm.command(name="available")
    @has_permission_or_fake("administrator")
    async def denyperm_available(self, ctx: commands.Context):
        names = sorted(discord.Permissions.VALID_FLAGS.keys())
        await ctx.send(embed=discord.Embed(
            description=f"{ctx.author.mention}: **Available Permissions**: {', '.join(f'`{n}`' for n in names)}"
        ))

    # ---------------------------------------------------------- kick

    @command_meta(
        category="Moderation",
        description="Kicks a member from the server.",
        syntax=",kick <member> [reason]",
        examples=[",kick @User Spamming"],
        permissions=["Kick Members"],
    )
    @commands.hybrid_command(name="kick")
    @has_permission_or_fake("kick_members")
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot kick this member - their role is above mine.")
            return

        await moderation_service.try_dm(member, f"You were kicked from **{ctx.guild.name}**.\nReason: {reason}")
        await ctx.guild.kick(member, reason=f"{ctx.author}: {reason}")
        await moderation_service.log_and_announce(
            ctx.guild, "kick", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )
        custom_text = await moderation_service.get_invoke_text(ctx.guild.id, "kick", guild=ctx.guild, member=member, reason=reason)
        await ctx.success(custom_text or f"Kicked **{member}**.\nReason: {reason}")

    # ---------------------------------------------------------- warn

    @command_meta(
        category="Moderation",
        description="Warns a member and records it in their case history. Auto-punishments can be configured via ,warn punishment.",
        syntax=",warn <member> <reason>",
        examples=[",warn @User Please follow the rules"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @commands.hybrid_group(name="warn", invoke_without_command=True)
    @has_permission_or_fake("moderate_members")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        if member is None:
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}: You need to provide `member`."))
            return
        if reason is None:
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention}: You need to provide `reason`."))
            return

        validate_moderation_target(ctx, member)

        await moderation_service.log_and_announce(
            ctx.guild, "warn", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )
        await moderation_service.try_dm(member, f"You were warned in **{ctx.guild.name}**.\nReason: {reason}")
        custom_text = await moderation_service.get_invoke_text(ctx.guild.id, "warn", guild=ctx.guild, member=member, reason=reason)
        await ctx.success(custom_text or f"Warned **{member}**.\nReason: {reason}")

        async with get_session() as session:
            count = await moderation_repository.get_active_warning_count(session, ctx.guild.id, member.id)
            tier = await moderation_repository.get_warn_punishment_for_count(session, ctx.guild.id, count)

        if tier is not None and bot_can_act_on(ctx, member):
            auto_reason = f"Reached {count} warning(s)"
            try:
                if tier.punishment == "kick":
                    await member.kick(reason=auto_reason)
                    await moderation_service.log_and_announce(
                        ctx.guild, "kick", self.bot.user,
                        target_id=member.id, target_mention=member.mention, reason=auto_reason,
                    )
                elif tier.punishment == "ban":
                    await member.ban(reason=auto_reason)
                    await moderation_service.log_and_announce(
                        ctx.guild, "ban", self.bot.user,
                        target_id=member.id, target_mention=member.mention, reason=auto_reason,
                    )
                elif tier.punishment.startswith("timeout:"):
                    seconds = int(tier.punishment.split(":", 1)[1])
                    until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
                    await member.timeout(until, reason=auto_reason)
                    await moderation_service.log_and_announce(
                        ctx.guild, "timeout", self.bot.user,
                        target_id=member.id, target_mention=member.mention, reason=auto_reason, duration_seconds=seconds,
                    )
            except discord.Forbidden:
                pass

    @warn.command(name="help")
    async def warn_help(self, ctx: commands.Context):
        await send_help(ctx, "warn")

    @command_meta(
        category="Moderation",
        description="Clears all active warnings for a member, or yourself if none is given.",
        syntax=",warn clear [member]",
        examples=[",warn clear", ",warn clear @User"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @warn.command(name="clear")
    @has_permission_or_fake("moderate_members")
    async def warn_clear(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        async with get_session() as session:
            count = await moderation_repository.clear_warnings(session, ctx.guild.id, target.id)
        await ctx.success(f"Cleared {count} warning(s) for **{target}**.")

    @command_meta(
        category="Moderation",
        description="Shows a member's active warnings.",
        syntax=",warn list [member]",
        examples=[",warn list", ",warn list @User"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @warn.command(name="list")
    @has_permission_or_fake("moderate_members")
    async def warn_list(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        async with get_session() as session:
            history = await moderation_repository.get_warnings_for_user(session, ctx.guild.id, target.id)

        if not history:
            embed = discord.Embed(
                description=f"{ctx.author.mention}: **{target.display_name}** **(@{target.name})** has no warnings."
            )
            await ctx.send(embed=embed)
            return

        lines = [f"`#{case.case_number}` {case.reason} — <t:{int(case.created_at.timestamp())}:R>" for case in history]
        await ctx.send(embed=discord.Embed(
            title=f"Warnings — {target}",
            description="\n".join(lines)[:4000],
        ))

    @command_meta(
        category="Moderation",
        description="Removes one specific warning from a member by its case number.",
        syntax=",warn remove <member> <case_number>",
        examples=[",warn remove @User 12"],
        permissions=["Moderate Members"],
    )
    @warn.command(name="remove")
    @has_permission_or_fake("moderate_members")
    async def warn_remove(self, ctx: commands.Context, member: discord.Member, case_number: int):
        async with get_session() as session:
            removed = await moderation_repository.remove_warning(session, ctx.guild.id, member.id, case_number)
        if removed:
            await ctx.success(f"Removed warning `#{case_number}` from **{member}**.")
        else:
            await ctx.error(f"No active warning `#{case_number}` found for **{member}**.")

    @command_meta(
        category="Moderation",
        description="Shows every configured warn auto-punishment tier.",
        syntax=",warn punishment",
        examples=[",warn punishment"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @warn.group(name="punishment", invoke_without_command=True)
    @has_permission_or_fake("moderate_members")
    async def warn_punishment(self, ctx: commands.Context):
        async with get_session() as session:
            tiers = await moderation_repository.get_all_warn_punishments(session, ctx.guild.id)
        if not tiers:
            await ctx.info("No warn auto-punishments configured.")
            return
        lines = [f"`{t.count}` warnings → **{t.punishment.replace('timeout:', 'timeout ')}**" for t in tiers]
        await ctx.send(embed=discord.Embed(title="Warn Punishments", description="\n".join(lines)))

    @command_meta(
        category="Moderation",
        description="Sets an auto-punishment applied when a member reaches a given number of warnings.",
        syntax=",warn punishment add <count> <kick|ban|timeout <duration>>",
        examples=[",warn punishment add 3 kick", ",warn punishment add 5 timeout 1h"],
        permissions=["Moderate Members"],
    )
    @warn_punishment.command(name="add")
    @has_permission_or_fake("moderate_members")
    async def warn_punishment_add(self, ctx: commands.Context, count: int, *, punishment: str):
        punishment = punishment.strip().lower()

        if punishment in ("kick", "ban"):
            stored = punishment
            display = punishment
        elif punishment.startswith("timeout"):
            duration_part = punishment[len("timeout"):].strip()
            try:
                seconds = parse_duration(duration_part) if duration_part else 0
            except InvalidDuration:
                seconds = 0
            if not seconds:
                await ctx.error("Provide a duration for timeout, e.g. `,warn punishment add 3 timeout 10m`.")
                return
            stored = f"timeout:{seconds}"
            display = f"timeout for `{format_duration(seconds)}`"
        else:
            await ctx.error("Punishment must be `kick`, `ban`, or `timeout <duration>`.")
            return

        async with get_session() as session:
            await moderation_repository.add_warn_punishment(session, ctx.guild.id, count, stored)
        await ctx.success(f"At `{count}` warning(s), members will now be **{display}**.")

    @command_meta(
        category="Moderation",
        description="Removes the auto-punishment configured for a given warning count.",
        syntax=",warn punishment remove <count>",
        examples=[",warn punishment remove 3"],
        permissions=["Moderate Members"],
    )
    @warn_punishment.command(name="remove")
    @has_permission_or_fake("moderate_members")
    async def warn_punishment_remove(self, ctx: commands.Context, count: int):
        async with get_session() as session:
            removed = await moderation_repository.remove_warn_punishment(session, ctx.guild.id, count)
        if removed:
            await ctx.success(f"Removed the auto-punishment for `{count}` warning(s).")
        else:
            await ctx.error(f"No auto-punishment configured for `{count}` warning(s).")

    # ---------------------------------------------------------- timeout

    @command_meta(
        category="Moderation",
        description="Times out a member for a given duration.",
        syntax=",timeout <member> <duration> [reason]",
        examples=[",timeout @User 10m Cooling off"],
        permissions=["Moderate Members"],
        aliases=["to"],
    )
    @commands.hybrid_command(name="timeout", aliases=["to"])
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: Duration, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot time out this member - their role is above mine.")
            return

        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
        await moderation_service.send_punishment_dm(
            member, ctx.guild, "timedout", ctx.author, reason, duration=format_duration(duration)
        )
        await member.timeout(until, reason=f"{ctx.author}: {reason}")

        await moderation_service.log_and_announce(
            ctx.guild, "timeout", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason, duration_seconds=duration,
        )
        custom_text = await moderation_service.get_invoke_text(ctx.guild.id, "timeout", guild=ctx.guild, member=member, reason=reason)
        await ctx.success(custom_text or f"Timed out **{member}** for `{format_duration(duration)}`.\nReason: {reason}")

    @command_meta(
        category="Moderation",
        description="Removes an active timeout from a member.",
        syntax=",untimeout <member> [reason]",
        examples=[",untimeout @User"],
        permissions=["Moderate Members"],
    )
    @commands.hybrid_command(name="untimeout")
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def untimeout(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await moderation_service.send_punishment_dm(member, ctx.guild, "untimedout", ctx.author, reason)
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        await moderation_service.log_and_announce(
            ctx.guild, "untimeout", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )
        custom_text = await moderation_service.get_invoke_text(ctx.guild.id, "untimeout", guild=ctx.guild, member=member, reason=reason)
        await ctx.success(custom_text or f"Removed timeout from **{member}**.")

    # ---------------------------------------------------------- jail / unjail

    @command_meta(
        category="Moderation",
        description="Jails a member using the jail role created by ,setup. Omit the duration for an indefinite jail.",
        syntax=",jail <member> [duration] [reason]",
        examples=[",jail @User 1h Spamming", ",jail @User Repeated warnings"],
        permissions=["Moderate Members"],
        aliases=["mute"],
    )
    @commands.hybrid_command(name="jail", aliases=["mute"])
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def jail(self, ctx: commands.Context, member: discord.Member, *, rest: str = ""):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot jail this member - their role is above mine.")
            return

        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None or not cfg.jail_role_id:
            await ctx.error("No jail role found. Run `,setup` first.")
            return

        jail_role = ctx.guild.get_role(cfg.jail_role_id)
        if jail_role is None:
            await ctx.error("The jail role no longer exists. Run `,setup` again.")
            return

        duration_seconds: int | None = None
        reason = "No reason provided"

        rest = rest.strip()
        if rest:
            first_word, _, remainder = rest.partition(" ")
            try:
                duration_seconds = parse_duration(first_word)
                reason = remainder.strip() or "No reason provided"
            except InvalidDuration:
                reason = rest

        try:
            await member.add_roles(jail_role, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to add that role.")
            return

        duration_display = format_duration(duration_seconds) if duration_seconds is not None else "Indefinite"
        await moderation_service.send_punishment_dm(member, ctx.guild, "jailed", ctx.author, reason, duration=duration_display)

        async with get_session() as session:
            unjail_at = None
            if duration_seconds is not None:
                unjail_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
            await moderation_repository.create_jail_record(session, ctx.guild.id, member.id, unjail_at)

        await moderation_service.log_and_announce(
            ctx.guild, "jail", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason, duration_seconds=duration_seconds,
        )

        if duration_seconds is not None:
            moderation_service.schedule_unjail(self.bot, ctx.guild.id, member.id, duration_seconds)
            time_display = f"**{format_duration(duration_seconds)}**"
        else:
            time_display = "**Indefinite**"

        embed = discord.Embed(
            description=f"{ctx.author.mention}: **{member}** is now jailed for {time_display}",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @command_meta(
        category="Moderation",
        description="Removes the jail role from a member.",
        syntax=",unjail <member> [reason]",
        examples=[",unjail @User Appeal accepted"],
        permissions=["Moderate Members"],
        aliases=["unmute"],
    )
    @commands.hybrid_command(name="unjail", aliases=["unmute"])
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unjail(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None:
            await ctx.error("No jail role found. Run `,setup` first.")
            return

        removed_labels = []

        jail_role = ctx.guild.get_role(cfg.jail_role_id) if cfg.jail_role_id else None
        if jail_role is not None and jail_role in member.roles:
            try:
                await member.remove_roles(jail_role, reason=f"{ctx.author}: {reason}")
                removed_labels.append("jailed")
            except discord.Forbidden:
                pass

        imute_role = ctx.guild.get_role(cfg.imute_role_id) if cfg.imute_role_id else None
        if imute_role is not None and imute_role in member.roles:
            try:
                await member.remove_roles(imute_role, reason=f"{ctx.author}: {reason}")
                removed_labels.append("imuted")
            except discord.Forbidden:
                pass

        rmute_role = ctx.guild.get_role(cfg.rmute_role_id) if cfg.rmute_role_id else None
        if rmute_role is not None and rmute_role in member.roles:
            try:
                await member.remove_roles(rmute_role, reason=f"{ctx.author}: {reason}")
                removed_labels.append("rmuted")
            except discord.Forbidden:
                pass

        if not removed_labels:
            await ctx.error(f"**{member}** isn't jailed, imuted, or rmuted.")
            return

        if "jailed" in removed_labels:
            await moderation_service.send_punishment_dm(member, ctx.guild, "unjailed", ctx.author, reason)

        moderation_service.cancel_scheduled_unjail(ctx.guild.id, member.id)
        async with get_session() as session:
            await moderation_repository.delete_jail_record(session, ctx.guild.id, member.id)

        await moderation_service.log_and_announce(
            ctx.guild, "unjail", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        if len(removed_labels) == 1:
            status = removed_labels[0]
        else:
            status = ", ".join(removed_labels[:-1]) + f" or {removed_labels[-1]}"
        embed = discord.Embed(
            description=f"{ctx.author.mention}: **{member}** is no longer {status}.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- imute / rmute

    @command_meta(
        category="Moderation",
        description="Blocks a member from sending images/embeds. Only ,unjail or ,unmute can remove it.",
        syntax=",imute <member> [reason]",
        examples=[",imute @User Stop posting images"],
        permissions=["Moderate Members"],
    )
    @commands.hybrid_group(name="imute", invoke_without_command=True)
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def imute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot imute this member - their role is above mine.")
            return

        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None or not cfg.imute_role_id:
            await ctx.error("No imute role found. Run `,setup` first.")
            return

        imute_role = ctx.guild.get_role(cfg.imute_role_id)
        if imute_role is None:
            await ctx.error("The imute role no longer exists. Run `,setup` again.")
            return

        try:
            await member.add_roles(imute_role, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to add that role.")
            return

        await moderation_service.log_and_announce(
            ctx.guild, "imute", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        embed = discord.Embed(
            description=f"{ctx.author.mention}: **{member}** is now imuted.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @command_meta(
        category="Moderation",
        description="List all imuted members.",
        syntax=",imute list",
        examples=[",imute list"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @imute.command(name="list")
    @has_permission_or_fake("moderate_members")
    async def imute_list(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None or not cfg.imute_role_id:
            await ctx.error("No imute role found. Run `,setup` first.")
            return

        role = ctx.guild.get_role(cfg.imute_role_id)
        if role is None or not role.members:
            await ctx.info("No members are currently imuted.")
            return

        lines = [f"`{i:02d}` {m.mention}" for i, m in enumerate(role.members, start=1)]
        embed = discord.Embed(title="Imuted Members", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Moderation",
        description="Blocks a member from adding reactions. Only ,unjail or ,unmute can remove it.",
        syntax=",rmute <member> [reason]",
        examples=[",rmute @User Stop reacting to everything"],
        permissions=["Moderate Members"],
    )
    @commands.hybrid_group(name="rmute", invoke_without_command=True)
    @has_permission_or_fake("moderate_members")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def rmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        validate_moderation_target(ctx, member)
        if not bot_can_act_on(ctx, member):
            await ctx.error("I cannot rmute this member - their role is above mine.")
            return

        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None or not cfg.rmute_role_id:
            await ctx.error("No rmute role found. Run `,setup` first.")
            return

        rmute_role = ctx.guild.get_role(cfg.rmute_role_id)
        if rmute_role is None:
            await ctx.error("The rmute role no longer exists. Run `,setup` again.")
            return

        try:
            await member.add_roles(rmute_role, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to add that role.")
            return

        await moderation_service.log_and_announce(
            ctx.guild, "rmute", ctx.author,
            target_id=member.id, target_mention=member.mention, reason=reason,
        )

        embed = discord.Embed(
            description=f"{ctx.author.mention}: **{member}** is now rmuted.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @command_meta(
        category="Moderation",
        description="List all rmuted members.",
        syntax=",rmute list",
        examples=[",rmute list"],
        permissions=["Moderate Members"],
        require_args=False,
    )
    @rmute.command(name="list")
    @has_permission_or_fake("moderate_members")
    async def rmute_list(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await guild_config_repository.get(session, ctx.guild.id)
        if cfg is None or not cfg.rmute_role_id:
            await ctx.error("No rmute role found. Run `,setup` first.")
            return

        role = ctx.guild.get_role(cfg.rmute_role_id)
        if role is None or not role.members:
            await ctx.info("No members are currently rmuted.")
            return

        lines = [f"`{i:02d}` {m.mention}" for i, m in enumerate(role.members, start=1)]
        embed = discord.Embed(title="Rmuted Members", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- verification gate

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            cfg = await verification_repository.get_config(session, member.guild.id)

        if cfg is None or not cfg.enabled or not cfg.role_id:
            return

        account_age_days = (discord.utils.utcnow() - member.created_at).days
        if account_age_days >= cfg.threshold_days:
            return

        role = member.guild.get_role(cfg.role_id)
        if role is None:
            return

        try:
            await member.add_roles(role, reason="Verification gate: new account")
        except discord.Forbidden:
            return

        channel = member.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        if channel is not None:
            embed = discord.Embed(
                description=(
                    f"{member.mention}: Your account is too new to join freely (created **{account_age_days}** "
                    f"day(s) ago). A moderator will review you shortly - please wait here."
                ),
                color=discord.Color.orange(),
            )
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @command_meta(
        category="Moderation",
        description="Hold risky new accounts in a role until a moderator approves them.",
        syntax=",verification",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["verifygate"],
        require_args=False,
    )
    @commands.group(name="verification", aliases=["verifygate"], invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    @commands.guild_only()
    async def verification(self, ctx: commands.Context):
        await send_help(ctx, "verification")

    @verification.command(name="help")
    async def verification_help(self, ctx: commands.Context):
        await send_help(ctx, "verification")

    @command_meta(
        category="Moderation",
        description="Create a quarantine role locked to a channel, then turn the verification gate on.",
        syntax=",verification setup <channel> [threshold]",
        examples=[",verification setup #verify", ",verification setup #verify 14"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @verification.command(name="setup")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def verification_setup(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int = 7):
        threshold = max(1, threshold)

        role = discord.utils.get(ctx.guild.roles, name="Unverified")
        if role is None:
            role = await ctx.guild.create_role(
                name="Unverified", permissions=discord.Permissions.none(), reason="Verification gate setup"
            )

        for ch in ctx.guild.channels:
            if ch.id == channel.id:
                continue
            try:
                await ch.set_permissions(role, view_channel=False, reason="Verification gate setup")
            except discord.Forbidden:
                pass

        try:
            await channel.set_permissions(
                role, view_channel=True, send_messages=False, reason="Verification gate setup"
            )
        except discord.Forbidden:
            pass

        async with get_session() as session:
            cfg = await verification_repository.get_or_create_config(session, ctx.guild.id)
            await verification_repository.update_config(
                session, cfg, channel_id=channel.id, role_id=role.id, threshold_days=threshold, enabled=True,
            )

        await ctx.success(
            f"{ctx.author.mention}: Verification gate armed. New accounts younger than **{threshold}** day(s) "
            f"will be held in {role.mention} and directed to {channel.mention} until a moderator runs "
            f"`,verification approve`."
        )

    @command_meta(
        category="Moderation",
        description="Turn off the verification gate (keeps the role/channel configured).",
        syntax=",verification off",
        examples=[",verification off"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @verification.command(name="off")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def verification_off(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await verification_repository.get_or_create_config(session, ctx.guild.id)
            await verification_repository.update_config(session, cfg, enabled=False)

        await ctx.success(f"{ctx.author.mention}: Verification gate turned off.")

    @command_meta(
        category="Moderation",
        description="Approve a held member - removes the quarantine role and gives them full access.",
        syntax=",verification approve <member>",
        examples=[",verification approve @User"],
        permissions=["Manage Guild"],
    )
    @verification.command(name="approve")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def verification_approve(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            cfg = await verification_repository.get_config(session, ctx.guild.id)
        if cfg is None or not cfg.role_id:
            await ctx.error("Verification isn't set up. Run `,verification setup` first.")
            return

        role = ctx.guild.get_role(cfg.role_id)
        if role is None or role not in member.roles:
            await ctx.error(f"**{member}** isn't pending verification.")
            return

        try:
            await member.remove_roles(role, reason=f"Verification approved by {ctx.author}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to remove that role.")
            return

        await ctx.success(f"{ctx.author.mention}: Approved **{member}** - they now have full access.")

    @command_meta(
        category="Moderation",
        description="Deny and kick a held member who failed verification.",
        syntax=",verification deny <member> [reason]",
        examples=[",verification deny @User Suspicious account"],
        permissions=["Manage Guild"],
    )
    @verification.command(name="deny")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def verification_deny(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Failed verification"):
        async with get_session() as session:
            cfg = await verification_repository.get_config(session, ctx.guild.id)
        if cfg is None or not cfg.role_id:
            await ctx.error("Verification isn't set up. Run `,verification setup` first.")
            return

        role = ctx.guild.get_role(cfg.role_id)
        if role is None or role not in member.roles:
            await ctx.error(f"**{member}** isn't pending verification.")
            return

        try:
            await member.kick(reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to kick that member.")
            return

        await ctx.success(f"{ctx.author.mention}: Denied and kicked **{member}**.")

    @command_meta(
        category="Moderation",
        description="Show the verification gate configuration.",
        syntax=",verification config",
        examples=[",verification config"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @verification.command(name="config")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def verification_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await verification_repository.get_config(session, ctx.guild.id)

        if cfg is None or not cfg.role_id:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Verification isn't configured. Run `verification setup` first.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        channel = ctx.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        role = ctx.guild.get_role(cfg.role_id)
        description = (
            f"**Channel:** {channel.mention if channel else 'None'}\n"
            f"**Role:** {role.mention if role else 'None'}\n"
            f"**Threshold:** {cfg.threshold_days} day(s)\n"
            f"**Enabled:** {'✅' if cfg.enabled else '❌'}"
        )
        embed = discord.Embed(title="Verification Gate Configuration", description=description)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- warnings

    @command_meta(
        category="Moderation",
        description="Shows a member's warnings. With no argument, shows your own.",
        syntax=",warnings [member]",
        examples=[",warnings", ",warnings @User"],
        permissions=["View Audit Log"],
        require_args=False,
    )
    @commands.command(name="warnings", with_app_command=False)
    @has_permission_or_fake("view_audit_log")
    @commands.guild_only()
    async def warnings(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        async with get_session() as session:
            warns = await moderation_repository.get_warnings_for_user(session, ctx.guild.id, member.id)

        if not warns:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: **{member.display_name}** (**@{member.name}**) has no warnings.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        chunks = [warns[i:i + 10] for i in range(0, len(warns), 10)]
        pages = []
        for chunk in chunks:
            lines = []
            for w in chunk:
                timestamp = discord.utils.format_dt(w.created_at, style="R") if w.created_at else "Unknown"
                lines.append(f"**Case #{w.case_number}** — {w.reason or 'No reason provided'} ({timestamp})")
            embed = discord.Embed(
                title=f"{member.display_name}'s Warnings ({len(warns)} total)",
                description="\n".join(lines),
            )
            pages.append(embed)

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            paginator = Paginator(pages, author_id=ctx.author.id)
            await paginator.start(ctx)

    @command_meta(
        category="Moderation",
        description="Bulk-deletes a number of recent messages in the current channel. With no amount, deletes every message it can in the channel (up to Discord's 14-day bulk-delete limit).",
        syntax=",purge <amount>",
        examples=[",purge 50", ",purge"],
        permissions=["Manage Messages"],
        aliases=["p", "c", "clear"],
        require_args=False,
    )
    @commands.hybrid_group(name="purge", aliases=["p", "c", "clear"], invoke_without_command=True)
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def purge(self, ctx: commands.Context, amount: int = None):
        if amount is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            deleted = await ctx.channel.purge(limit=5000)
            confirmation = await ctx.send(embed=discord.Embed(description=f"Deleted {len(deleted)} message(s)."))
            await confirmation.delete(delay=2)
            return
        await _run_purge(ctx, amount, None)

    @purge.command(name="help")
    async def purge_help(self, ctx: commands.Context):
        await send_help(ctx, "purge")

    @command_meta(
        category="Moderation",
        description="Deletes every message sent after a given message (ID or link), up to Discord's 2-week bulk-delete limit.",
        syntax=",purge after <message>",
        examples=[",purge after 123456789012345678"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="after")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_after(self, ctx: commands.Context, message: str):
        target = await _resolve_message(ctx, message)
        if target is None:
            await ctx.error("Couldn't find that message - provide a message ID or link.")
            return
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        deleted = await ctx.channel.purge(after=target, limit=1000)
        msg = await ctx.send(embed=discord.Embed(description=f"Deleted {len(deleted)} message(s)."))
        await msg.delete(delay=2)

    @command_meta(
        category="Moderation",
        description="Deletes every message sent before a given message (ID or link), up to Discord's 2-week bulk-delete limit.",
        syntax=",purge before <message>",
        examples=[",purge before 123456789012345678"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="before")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_before(self, ctx: commands.Context, message: str):
        target = await _resolve_message(ctx, message)
        if target is None:
            await ctx.error("Couldn't find that message - provide a message ID or link.")
            return
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        deleted = await ctx.channel.purge(before=target, limit=1000)
        msg = await ctx.send(embed=discord.Embed(description=f"Deleted {len(deleted)} message(s)."))
        await msg.delete(delay=2)

    @command_meta(
        category="Moderation",
        description="Deletes every message between two given messages (ID or link), up to Discord's 2-week bulk-delete limit.",
        syntax=",purge between <message1> <message2>",
        examples=[",purge between 123456789012345678 123456789012399999"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="between")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_between(self, ctx: commands.Context, message1: str, message2: str):
        first = await _resolve_message(ctx, message1)
        second = await _resolve_message(ctx, message2)
        if first is None or second is None:
            await ctx.error("Couldn't find one of those messages - provide message IDs or links.")
            return

        earlier, later = (first, second) if first.created_at < second.created_at else (second, first)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        deleted = await ctx.channel.purge(after=earlier, before=later, limit=1000)
        msg = await ctx.send(embed=discord.Embed(description=f"Deleted {len(deleted)} message(s)."))
        await msg.delete(delay=2)

    @command_meta(
        category="Moderation",
        description="Deletes recent messages from everyone except a given member.",
        syntax=",purge except <member> [amount]",
        examples=[",purge except @User", ",purge except @User 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="except")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_except(self, ctx: commands.Context, member: discord.Member, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: m.author.id != member.id)

    @command_meta(
        category="Moderation",
        description="Clears all reactions from the last N messages, without deleting the messages themselves.",
        syntax=",purge reactions [amount]",
        examples=[",purge reactions", ",purge reactions 50"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="reactions")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_reactions(self, ctx: commands.Context, amount: int = 100):
        amount = max(1, min(amount, 500))
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        cleared = 0
        async for msg in ctx.channel.history(limit=amount):
            if msg.reactions:
                try:
                    await msg.clear_reactions()
                    cleared += 1
                except discord.HTTPException:
                    pass

        confirmation = await ctx.send(embed=discord.Embed(description=f"Cleared reactions from {cleared} message(s)."))
        await confirmation.delete(delay=2)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages sent by bots (not webhooks).',
        syntax=",purge bots [amount]",
        examples=[",purge bots", ",purge bots 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="bots")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: m.author.bot and m.webhook_id is None)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages sent by humans.',
        syntax=",purge humans [amount]",
        examples=[",purge humans", ",purge humans 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="humans")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_humans(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: not m.author.bot)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing an embed.',
        syntax=",purge embeds [amount]",
        examples=[",purge embeds", ",purge embeds 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="embeds")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: len(m.embeds) > 0)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing a custom emoji.',
        syntax=",purge emojis [amount]",
        examples=[",purge emojis", ",purge emojis 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="emojis")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_emojis(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: re.search(r"<a?:\w+:\d+>", m.content) is not None)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages with a file attachment.',
        syntax=",purge files [amount]",
        examples=[",purge files", ",purge files 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="files")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_files(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: len(m.attachments) > 0)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages with an image attachment.',
        syntax=",purge images [amount]",
        examples=[",purge images", ",purge images 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="images")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_images(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: any((a.content_type or "").startswith("image/") for a in m.attachments))

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing a Discord invite link.',
        syntax=",purge invites [amount]",
        examples=[",purge invites", ",purge invites 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="invites")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_invites(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: re.search(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", m.content, re.I) is not None)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing a link.',
        syntax=",purge links [amount]",
        examples=[",purge links", ",purge links 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="links")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_links(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: re.search(r"https?://\S+", m.content, re.I) is not None)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages that mention a user, role, or everyone.',
        syntax=",purge mentions [amount]",
        examples=[",purge mentions", ",purge mentions 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="mentions")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_mentions(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: bool(m.mentions) or bool(m.role_mentions) or m.mention_everyone)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing a sticker.',
        syntax=",purge stickers [amount]",
        examples=[",purge stickers", ",purge stickers 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="stickers")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_stickers(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: len(m.stickers) > 0)

    @command_meta(
        category="Moderation",
        description='Deletes recent system messages (joins, boosts, pins, etc.).',
        syntax=",purge system [amount]",
        examples=[",purge system", ",purge system 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="system")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_system(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: m.type not in (discord.MessageType.default, discord.MessageType.reply))

    @command_meta(
        category="Moderation",
        description='Deletes recent voice messages.',
        syntax=",purge voice [amount]",
        examples=[",purge voice", ",purge voice 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="voice")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_voice(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: any(getattr(a, "is_voice_message", lambda: False)() for a in m.attachments))

    @command_meta(
        category="Moderation",
        description='Deletes recent messages sent by a webhook.',
        syntax=",purge webhooks [amount]",
        examples=[",purge webhooks", ",purge webhooks 100"],
        permissions=["Manage Messages"],
        require_args=False,
    )
    @purge.command(name="webhooks")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_webhooks(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: m.webhook_id is not None)

    @command_meta(
        category="Moderation",
        description='Deletes recent messages containing a given term.',
        syntax=",purge contains <amount> <term>",
        examples=[",purge contains 100 hello"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="contains")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, ctx: commands.Context, amount: int, *, term: str):
        await _run_purge(ctx, amount, lambda m: term.lower() in m.content.lower())

    @command_meta(
        category="Moderation",
        description='Deletes recent messages starting with a given term.',
        syntax=",purge startswith <amount> <term>",
        examples=[",purge startswith 100 hello"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="startswith")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_startswith(self, ctx: commands.Context, amount: int, *, term: str):
        await _run_purge(ctx, amount, lambda m: m.content.lower().startswith(term.lower()))

    @command_meta(
        category="Moderation",
        description='Deletes recent messages ending with a given term.',
        syntax=",purge endswith <amount> <term>",
        examples=[",purge endswith 100 hello"],
        permissions=["Manage Messages"],
    )
    @purge.command(name="endswith")
    @has_permission_or_fake("manage_messages")
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_endswith(self, ctx: commands.Context, amount: int, *, term: str):
        await _run_purge(ctx, amount, lambda m: m.content.lower().endswith(term.lower()))

    @command_meta(
        category="Moderation",
        description="Deletes your own recent messages in this channel.",
        syntax=",selfpurge [amount]",
        examples=[",selfpurge", ",selfpurge 50"],
        permissions=["Manage Messages"],
        aliases=["sp"],
        require_args=False,
    )
    @commands.hybrid_command(name="selfpurge", aliases=["sp"])
    @has_permission_or_fake("manage_messages")
    @requires_premium("server")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def selfpurge(self, ctx: commands.Context, amount: int = 100):
        await _run_purge(ctx, amount, lambda m: m.author.id == ctx.author.id)

    # ---------------------------------------------------------- lockdown / unlock

    @staticmethod
    async def _resolve_role_or_channel(ctx: commands.Context, raw: str):
        try:
            return await commands.RoleConverter().convert(ctx, raw), "role"
        except commands.BadArgument:
            pass
        try:
            return await commands.TextChannelConverter().convert(ctx, raw), "channel"
        except commands.BadArgument:
            return None, None

    @command_meta(
        category="Moderation",
        description="Locks the current channel, preventing @everyone (or a given role) from sending messages.",
        syntax=",lockdown [role]",
        examples=[",lockdown", ",lockdown @Members"],
        permissions=["Manage Roles"],
        aliases=["lock"],
        require_args=False,
    )
    @commands.hybrid_group(name="lockdown", aliases=["lock"], invoke_without_command=True)
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def lockdown(self, ctx: commands.Context, role: discord.Role = None):
        target = role or ctx.guild.default_role
        overwrite = ctx.channel.overwrites_for(target)

        if overwrite.send_messages is False:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: {ctx.channel.mention} is already locked.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        overwrite.send_messages = False
        await ctx.channel.set_permissions(target, overwrite=overwrite, reason=f"Locked by {ctx.author}")
        await moderation_service.log_action(
            guild_id=ctx.guild.id, user_id=ctx.channel.id, moderator_id=ctx.author.id,
            action_type="lock", reason=None,
        )
        await ctx.message.add_reaction("🔒")

    @lockdown.command(name="help")
    async def lockdown_help(self, ctx: commands.Context):
        await send_help(ctx, "lockdown")

    @command_meta(
        category="Moderation",
        description="Locks every text channel in the server (skipping any ignored channels), preventing @everyone (or a given role) from sending messages.",
        syntax=",lockdown all [role]",
        examples=[",lockdown all", ",lockdown all @Members"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @lockdown.command(name="all")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def lockdown_all(self, ctx: commands.Context, role: discord.Role = None):
        target = role or ctx.guild.default_role

        async with get_session() as session:
            ignored_channel_ids = await lockdown_repository.get_ignored_channel_ids(session, ctx.guild.id)
            ignored_role_ids = await lockdown_repository.get_ignored_role_ids(session, ctx.guild.id)

        locked = 0
        for channel in ctx.guild.text_channels:
            if channel.id in ignored_channel_ids:
                continue

            overwrite = channel.overwrites_for(target)
            if overwrite.send_messages is not False:
                overwrite.send_messages = False
                try:
                    await channel.set_permissions(target, overwrite=overwrite, reason=f"Lockdown all by {ctx.author}")
                    locked += 1
                except discord.HTTPException:
                    pass

            for ignored_role_id in ignored_role_ids:
                ignored_role = ctx.guild.get_role(ignored_role_id)
                if ignored_role is None:
                    continue
                role_overwrite = channel.overwrites_for(ignored_role)
                role_overwrite.send_messages = True
                try:
                    await channel.set_permissions(ignored_role, overwrite=role_overwrite, reason="Lockdown ignore role")
                except discord.HTTPException:
                    pass

        await ctx.message.add_reaction("🔒")

    @command_meta(
        category="Moderation",
        description="Adds a role or channel to the lockdown ignore list - an ignored role stays able to send messages during a lockdown; an ignored channel is skipped entirely by ,lockdown all.",
        syntax=",lockdown ignore <role|channel>",
        examples=[",lockdown ignore @Staff", ",lockdown ignore #announcements"],
        permissions=["Manage Roles"],
    )
    @lockdown.group(name="ignore", invoke_without_command=True)
    @has_permission_or_fake("manage_roles")
    async def lockdown_ignore(self, ctx: commands.Context, *, target: str):
        resolved, kind = await self._resolve_role_or_channel(ctx, target)
        if resolved is None:
            await ctx.error("Couldn't find that role or channel.")
            return

        async with get_session() as session:
            added = await lockdown_repository.add_ignore(session, ctx.guild.id, resolved.id, kind)

        if added:
            await ctx.success(f"{resolved.mention} will now be ignored during lockdowns.")
        else:
            await ctx.error(f"{resolved.mention} is already ignored.")

    @command_meta(
        category="Moderation",
        description="Removes a role or channel from the lockdown ignore list.",
        syntax=",lockdown ignore remove <role|channel>",
        examples=[",lockdown ignore remove @Staff"],
        permissions=["Manage Roles"],
    )
    @lockdown_ignore.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def lockdown_ignore_remove(self, ctx: commands.Context, *, target: str):
        resolved, kind = await self._resolve_role_or_channel(ctx, target)
        if resolved is None:
            await ctx.error("Couldn't find that role or channel.")
            return

        async with get_session() as session:
            removed = await lockdown_repository.remove_ignore(session, ctx.guild.id, resolved.id)

        if removed:
            await ctx.success(f"{resolved.mention} removed from the lockdown ignore list.")
        else:
            await ctx.error(f"{resolved.mention} wasn't ignored.")

    @command_meta(
        category="Moderation",
        description="Lists every role/channel on the lockdown ignore list.",
        syntax=",lockdown ignore list",
        examples=[",lockdown ignore list"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @lockdown_ignore.command(name="list")
    @has_permission_or_fake("manage_roles")
    async def lockdown_ignore_list(self, ctx: commands.Context):
        async with get_session() as session:
            entries = await lockdown_repository.get_ignore_list(session, ctx.guild.id)

        if not entries:
            await ctx.info("No ignored roles or channels.")
            return

        lines = [
            f"<@&{e.target_id}>" if e.target_type == "role" else f"<#{e.target_id}>"
            for e in entries
        ]
        await ctx.send(embed=discord.Embed(title="Lockdown Ignore List", description="\n".join(lines)))

    @command_meta(
        category="Moderation",
        description="Unlocks the current channel, restoring @everyone's (or a given role's) send permission.",
        syntax=",unlock [role]",
        examples=[",unlock", ",unlock @Members"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @commands.hybrid_command(name="unlock")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, role: discord.Role = None):
        target = role or ctx.guild.default_role
        overwrite = ctx.channel.overwrites_for(target)

        if overwrite.send_messages is not False:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: {ctx.channel.mention} is already unlocked.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        overwrite.send_messages = None
        await ctx.channel.set_permissions(target, overwrite=overwrite, reason=f"Unlocked by {ctx.author}")
        await moderation_service.log_action(
            guild_id=ctx.guild.id, user_id=ctx.channel.id, moderator_id=ctx.author.id,
            action_type="unlock", reason=None,
        )
        await ctx.message.add_reaction("🔓")

    # ---------------------------------------------------------- slowmode

    @command_meta(
        category="Moderation",
        description="Sets slowmode delay for the current channel.",
        syntax=",slowmode <duration>",
        examples=[",slowmode 10s", ",slowmode 0"],
        permissions=["Manage Channels"],
    )
    @commands.hybrid_command(name="slowmode")
    @has_permission_or_fake("manage_channels")
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(self, ctx: commands.Context, duration: str):
        seconds = 0 if duration.strip() == "0" else parse_duration(duration)
        seconds = max(0, min(seconds, 21600))
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.success(f"Slowmode set to `{format_duration(seconds)}`." if seconds else "Slowmode disabled.")

    # ---------------------------------------------------------- history / modlog

    @command_meta(
        category="Moderation",
        description="Shows every punishment on record for a member (yourself, if none given).",
        syntax=",history [member]",
        examples=[",history", ",history @User"],
        permissions=["View Audit Log"],
        aliases=["modlog"],
        require_args=False,
    )
    @commands.hybrid_command(name="history", aliases=["modlog"])
    @has_permission_or_fake("view_audit_log")
    @commands.guild_only()
    async def history(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        async with get_session() as session:
            cases = await moderation_repository.get_cases_for_user(session, ctx.guild.id, member.id)

        if not cases:
            await ctx.info(f"**{member}** has no punishment history.")
            return

        chunks = [cases[i:i + 10] for i in range(0, len(cases), 10)]
        pages = []

        for chunk in chunks:
            lines = []
            for case in chunk:
                moderator = ctx.guild.get_member(case.moderator_id) or self.bot.get_user(case.moderator_id)
                moderator_display = f"{moderator} ({case.moderator_id})" if moderator else f"Unknown ({case.moderator_id})"
                punished_at = case.created_at.strftime("%d %B %Y at %-H:%M")
                reason = case.reason or "No Reason Provided"

                lines.append(
                    f"**Case Log #{case.case_number} / {case.action_type}**\n"
                    f"**Punished** {punished_at}\n"
                    f"**Moderator** {moderator_display}\n"
                    f"**Reason** {reason}"
                )

            embed = discord.Embed(
                title=f"Punishment History for {member}",
                description="\n\n".join(lines),
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            pages.append(embed)

        total = len(cases)
        for embed in pages:
            embed.set_footer(text=f"{total} punishment{'s' if total != 1 else ''}")

        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    # ---------------------------------------------------------- nsfw / sfw

    @command_meta(
        category="Moderation",
        description="Toggles the current channel's age restriction - marks it NSFW, or back to SFW if it already is.",
        syntax=",nsfw",
        examples=[",nsfw"],
        permissions=["Manage Channels"],
        require_args=False,
    )
    @commands.hybrid_command(name="nsfw")
    @has_permission_or_fake("manage_channels")
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def nsfw(self, ctx: commands.Context):
        new_state = not ctx.channel.is_nsfw()
        await ctx.channel.edit(nsfw=new_state, reason=f"Toggled by {ctx.author}")
        label = "NSFW" if new_state else "SFW"
        await ctx.success(f"{ctx.author.mention}: Marked {ctx.channel.mention} as **{label}**")

    @command_meta(
        category="Moderation",
        description="Marks a channel as SFW (removes age restriction).",
        syntax=",sfw",
        examples=[",sfw"],
        permissions=["Manage Channels"],
        require_args=False,
    )
    @commands.hybrid_command(name="sfw")
    @has_permission_or_fake("manage_channels")
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def sfw(self, ctx: commands.Context):
        await ctx.channel.edit(nsfw=False, reason=f"Marked SFW by {ctx.author}")
        await ctx.success(f"{ctx.author.mention}: Marked {ctx.channel.mention} as **SFW**")

    # ---------------------------------------------------------- nuke

    @command_meta(
        category="Moderation",
        description="Deletes and instantly recreates the current channel - identical name, position, category, permissions, and settings. Server owner or antinuke admins only.",
        syntax=",nuke",
        examples=[",nuke"],
        permissions=["Server Owner / Antinuke Admin"],
        require_args=False,
    )
    @commands.hybrid_command(name="nuke")
    @is_owner_or_antinuke_admin()
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.error("This can only be used in a regular text channel.")
            return

        confirm_embed = discord.Embed(
            description=f"{ctx.author.mention} Are you sure that you want to **nuke** this **channel**?"
        )
        view = NukeConfirmView(ctx.author.id)
        message = await ctx.send(embed=confirm_embed, view=view)
        view.message = message

        await view.wait()

        if view.confirmed is None:
            return  # timed out - on_timeout already disabled the buttons

        if not view.confirmed:
            cancelled_embed = discord.Embed(description=f"{ctx.author.mention} Cancelled.")
            await message.edit(embed=cancelled_embed, view=None)
            return

        channel = ctx.channel
        position = channel.position
        reason = f"Nuked by {ctx.author}"

        new_channel = await channel.clone(reason=reason)
        await channel.delete(reason=reason)
        try:
            await new_channel.edit(position=position)
        except discord.HTTPException:
            pass

        await new_channel.send(f"This channel was nuked by {ctx.author}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
