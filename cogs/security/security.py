"""Security: antinuke (admins, per-module thresholds, whitelist),
honeypot, join gate, and fake permissions."""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake, is_owner_or_antinuke_admin, is_server_owner, requires_premium
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.paginator import Paginator
from database.database import get_session
from database.security_models import ANTINUKE_MODULES, ANTINUKE_PUNISHMENTS
from repositories import denyperm_repository, security_repository
from services import security_service

def _build_honeypot_view(caught_count: int) -> discord.ui.LayoutView:
    """The pinned Components V2 warning message inside the honeypot
    channel - a disabled, display-only 'Caught: N' button, no
    interaction ever fires on it."""

    class HoneypotView(discord.ui.LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            caught_button = discord.ui.Button(
                label=f"Caught: {caught_count}", style=discord.ButtonStyle.secondary, disabled=True,
            )
            container = discord.ui.Container(
                discord.ui.TextDisplay("# Don't send messages in this channel."),
                discord.ui.TextDisplay(
                    "This channel is a **honeypot** for compromised accounts and selfbots. Legit members "
                    "have no reason to type here. Any message will be treated as evidence of a hijacked "
                    "account and the sender will be **BANNED** immediately, automatically, and without warning."
                ),
                discord.ui.ActionRow(caught_button),
            )
            self.add_item(container)

    return HoneypotView()


MODULE_FLAGS = [
    ("--do (punishment)", "Set punishment type: ban, kick, timeout, strip, stripstaff, jail"),
    ("--threshold (number)", "Number of actions before punishment"),
    ("--command (on/off)", "Track bot commands in addition to audit log"),
]


def _parse_module_flags(rest: str) -> dict:
    tokens = rest.split()
    result = {"status": None, "do": None, "threshold": None, "command": None}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--do" and i + 1 < len(tokens):
            result["do"] = tokens[i + 1].lower()
            i += 2
        elif tok == "--threshold" and i + 1 < len(tokens):
            result["threshold"] = tokens[i + 1]
            i += 2
        elif tok == "--command" and i + 1 < len(tokens):
            result["command"] = tokens[i + 1].lower()
            i += 2
        elif not tok.startswith("--") and result["status"] is None:
            result["status"] = tok.lower()
            i += 1
        else:
            i += 1
    return result


async def _run_module_command(ctx: commands.Context, module_name: str, rest: str) -> None:
    flags = _parse_module_flags(rest)
    detail_parts = []

    async with get_session() as session:
        module = await security_repository.get_or_create_module(session, ctx.guild.id, module_name)
        any_change = False

        if flags["status"] is not None:
            if flags["status"] in ("on", "enable", "enabled", "true"):
                module = await security_repository.update_module(session, module, enabled=True)
                any_change = True
            elif flags["status"] in ("off", "disable", "disabled", "false"):
                module = await security_repository.update_module(session, module, enabled=False)
                any_change = True
            else:
                await ctx.error(f"Status must be `on` or `off`, not `{flags['status']}`.")
                return

        if flags["do"] is not None:
            if flags["do"] not in ANTINUKE_PUNISHMENTS:
                await ctx.error(f"Punishment must be one of: {', '.join(ANTINUKE_PUNISHMENTS)}.")
                return
            module = await security_repository.update_module(session, module, punishment=flags["do"])
            detail_parts.append(f"Punishment is set to **{flags['do']}**")
            any_change = True

        if flags["threshold"] is not None:
            try:
                threshold_value = max(1, int(flags["threshold"]))
            except ValueError:
                await ctx.error("Threshold must be a number.")
                return
            module = await security_repository.update_module(session, module, threshold=threshold_value)
            detail_parts.append(f"threshold is set to **{threshold_value}**")
            any_change = True

        if flags["command"] is not None:
            track = flags["command"] in ("on", "enable", "enabled", "true")
            module = await security_repository.update_module(session, module, track_commands=track)
            detail_parts.append(f"command execution detection is **{'on' if track else 'off'}**")
            any_change = True

    if not any_change:
        embed = discord.Embed(
            title=f"Antinuke — {module_name}",
            description=(
                f"Status: **{'Enabled' if module.enabled else 'Disabled'}**\n"
                f"Punishment: `{module.punishment}`\n"
                f"Threshold: `{module.threshold}`\n"
                f"Command Tracking: **{'On' if module.track_commands else 'Off'}**"
            ),
        )
        await ctx.send(embed=embed)
        return

    message = f"{ctx.author.mention}: Updated **{module_name}** antinuke module."
    if detail_parts:
        if len(detail_parts) == 1:
            detail_sentence = detail_parts[0] + "."
        else:
            detail_sentence = f"{', '.join(detail_parts[:-1])} and {detail_parts[-1]}."
        message += f" {detail_sentence}"

    await ctx.success(message)


class AntinukeAdminConfirmView(discord.ui.View):
    """Green Confirm / red Cancel for ,antinuke admin - only the
    command author can answer."""

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

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- listeners

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        guild = entry.guild
        if guild is not None:
            await security_service.handle_audit_log_entry(entry, guild)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        await security_service.handle_command_used(ctx)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await security_service.handle_bot_join(member)

        async with get_session() as session:
            cfg = await security_repository.get_or_create_antinuke_config(session, member.guild.id)

        if not cfg.join_gate_enabled:
            return

        account_age = discord.utils.utcnow() - member.created_at
        min_age = datetime.timedelta(hours=cfg.join_gate_min_account_age_hours)
        if account_age < min_age:
            try:
                await member.kick(reason="Join gate: account too new")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, message.guild.id)

        if not cfg.enabled or not cfg.channel_id or message.channel.id != cfg.channel_id:
            return

        member = message.author
        reason = "Honeypot channel triggered"
        delete_seconds = cfg.purge_days * 86400

        try:
            if cfg.action == "kick":
                await member.kick(reason=reason)
            elif cfg.action == "softban":
                await member.ban(reason=reason, delete_message_seconds=delete_seconds)
                await message.guild.unban(member, reason="Honeypot softban cleanup")
            else:
                await member.ban(reason=reason, delete_message_seconds=delete_seconds)
        except discord.Forbidden:
            pass

        async with get_session() as session:
            new_count = await security_repository.increment_honeypot_caught(session, message.guild.id)

        if cfg.message_id:
            try:
                pinned_message = await message.channel.fetch_message(cfg.message_id)
                await pinned_message.edit(view=_build_honeypot_view(new_count))
            except discord.HTTPException:
                pass

        if cfg.log_channel_id:
            log_channel = message.guild.get_channel(cfg.log_channel_id)
            if log_channel is not None:
                verb = "softbanned" if cfg.action == "softban" else f"{cfg.action}ed"
                log_embed = discord.Embed(description=f"**{member}** (`{member.id}`) triggered the honeypot and was **{verb}**.")
                log_embed.timestamp = discord.utils.utcnow()
                try:
                    await log_channel.send(embed=log_embed)
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------- ,antinuke root

    @command_meta(
        category="Security",
        description="Configures antinuke protection for this server - per-module thresholds, admins, and whitelist.",
        syntax=",antinuke",
        examples=[],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an"],
        require_args=False,
    )
    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True)
    @commands.guild_only()
    async def antinuke(self, ctx: commands.Context):
        await send_help(ctx, "antinuke")

    @antinuke.command(name="help")
    async def antinuke_help(self, ctx: commands.Context):
        await send_help(ctx, "antinuke")

    # ---------------------------------------------------------- ,antinuke admin / admins

    @command_meta(
        category="Security",
        description="Toggles a user as an antinuke admin, with a confirmation prompt.",
        syntax=",antinuke admin <user>",
        examples=[",antinuke admin @User"],
        permissions=["Server Owner"],
        aliases=["an admin"],
    )
    @antinuke.command(name="admin")
    @is_server_owner()
    async def antinuke_admin(self, ctx: commands.Context, user: discord.Member):
        async with get_session() as session:
            already_admin = await security_repository.is_antinuke_admin(session, ctx.guild.id, user.id)

        action_word = "remove" if already_admin else "add"
        confirm_embed = discord.Embed(
            description=f"{ctx.author.mention} Are you sure you want to {action_word} **{user}** as an antinuke admin?"
        )
        view = AntinukeAdminConfirmView(ctx.author.id)
        message = await ctx.send(embed=confirm_embed, view=view)
        view.message = message

        await view.wait()

        if view.confirmed is None:
            return  # timed out - on_timeout already disabled the buttons

        if not view.confirmed:
            cancelled_embed = discord.Embed(description=f"{ctx.author.mention} Cancelled.")
            await message.edit(embed=cancelled_embed, view=None)
            return

        working_embed = discord.Embed(description="Working...")
        await message.edit(embed=working_embed, view=None)

        async with get_session() as session:
            if already_admin:
                await security_repository.remove_antinuke_admin(session, ctx.guild.id, user.id)
            else:
                await security_repository.add_antinuke_admin(session, ctx.guild.id, user.id)

        verb = "Removed" if already_admin else "Added"
        done_embed = discord.Embed(description=f"{ctx.author.mention} {verb} **{user}** as an antinuke admin.")
        await message.edit(embed=done_embed)

    @command_meta(
        category="Security",
        description="Lists every antinuke admin in this server.",
        syntax=",antinuke admins",
        examples=[",antinuke admins"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an admins"],
        require_args=False,
    )
    @antinuke.command(name="admins")
    @is_owner_or_antinuke_admin()
    async def antinuke_admins(self, ctx: commands.Context):
        async with get_session() as session:
            admin_ids = await security_repository.get_antinuke_admins(session, ctx.guild.id)

        if not admin_ids:
            await ctx.info("No antinuke admins configured yet.")
            return

        lines = [f"<@{uid}>" for uid in admin_ids]
        await ctx.send(embed=discord.Embed(title="Antinuke Admins", description="\n".join(lines)))

    # ---------------------------------------------------------- ,antinuke config / list / enable / disable

    @command_meta(
        category="Security",
        description="Shows the configuration of every antinuke module.",
        syntax=",antinuke config",
        examples=[",antinuke config"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an config"],
        require_args=False,
    )
    @antinuke.command(name="config")
    @is_owner_or_antinuke_admin()
    async def antinuke_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_antinuke_config(session, ctx.guild.id)
            modules = await security_repository.get_all_modules(session, ctx.guild.id)

        if not cfg.enabled:
            await ctx.send(embed=discord.Embed(description="🔒 **Antinuke is disabled.** Run `,antinuke enable` to turn it on."))
            return

        lines = []
        for name in ANTINUKE_MODULES:
            module = modules.get(name)
            if module is None or not module.enabled:
                lines.append(f"🔴 **{name}** — disabled")
            else:
                lines.append(f"🟢 **{name}** — `{module.punishment}` at `{module.threshold}`")

        embed = discord.Embed(title="Antinuke Configuration", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Security",
        description="Lists every antinuke module name.",
        syntax=",antinuke list",
        examples=[",antinuke list"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an list"],
        require_args=False,
    )
    @antinuke.command(name="list")
    @is_owner_or_antinuke_admin()
    async def antinuke_list(self, ctx: commands.Context):
        lines = [f"`{i + 1:02d}` **{name}**" for i, name in enumerate(ANTINUKE_MODULES)]
        embed = discord.Embed(title="Antinuke Modules", description="\n".join(lines))
        embed.set_footer(text=f"{len(ANTINUKE_MODULES)} modules")
        await ctx.send(embed=embed)

    @command_meta(
        category="Security",
        description="Enables antinuke protection for this server.",
        syntax=",antinuke enable",
        examples=[",antinuke enable"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an enable"],
        require_args=False,
    )
    @antinuke.command(name="enable")
    @is_owner_or_antinuke_admin()
    async def antinuke_enable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_antinuke_config(session, ctx.guild.id)
            cfg.enabled = True
            await session.commit()
        await ctx.success("Antinuke enabled.")

    @command_meta(
        category="Security",
        description="Disables antinuke protection for this server.",
        syntax=",antinuke disable",
        examples=[",antinuke disable"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an disable"],
        require_args=False,
    )
    @antinuke.command(name="disable")
    @is_owner_or_antinuke_admin()
    async def antinuke_disable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_antinuke_config(session, ctx.guild.id)
            cfg.enabled = False
            await session.commit()
        await ctx.success("Antinuke disabled.")

    @command_meta(
        category="Security",
        description="Whitelists a user or bot from antinuke punishment - bots must be whitelisted or they're kicked on join.",
        syntax=",antinuke whitelist <user_id>",
        examples=[",antinuke whitelist 123456789012345678"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an whitelist"],
    )
    @antinuke.command(name="whitelist")
    @is_owner_or_antinuke_admin()
    async def antinuke_whitelist(self, ctx: commands.Context, user_id: int):
        async with get_session() as session:
            already = await security_repository.is_whitelisted(session, ctx.guild.id, user_id)
            if already:
                await security_repository.remove_whitelist(session, ctx.guild.id, user_id)
            else:
                await security_repository.add_whitelist(session, ctx.guild.id, user_id)

        if already:
            await ctx.success(f"<@{user_id}> removed from the antinuke whitelist.")
        else:
            await ctx.success(f"<@{user_id}> is now whitelisted from antinuke.")

    # ---------------------------------------------------------- modules

    @command_meta(
        category="Security",
        description="Punishes members who ban too many users too quickly.",
        syntax=",antinuke ban (status) [flags]",
        examples=[",antinuke ban on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an ban"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="ban")
    @is_owner_or_antinuke_admin()
    async def antinuke_ban(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "ban", rest)

    @command_meta(
        category="Security",
        description="Kicks any bot added to the server that isn't whitelisted.",
        syntax=",antinuke botadd (status) [flags]",
        examples=[",antinuke botadd on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an botadd"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="botadd")
    @is_owner_or_antinuke_admin()
    async def antinuke_botadd(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "botadd", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete/update too many channels too quickly.",
        syntax=",antinuke channel (status) [flags]",
        examples=[",antinuke channel on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an channel"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="channel")
    @is_owner_or_antinuke_admin()
    async def antinuke_channel(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "channel", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete/update too many emojis too quickly.",
        syntax=",antinuke emoji (status) [flags]",
        examples=[",antinuke emoji on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an emoji"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="emoji")
    @is_owner_or_antinuke_admin()
    async def antinuke_emoji(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "emoji", rest)

    @command_meta(
        category="Security",
        description="Punishes members who make too many server setting changes too quickly.",
        syntax=",antinuke guildupdate (status) [flags]",
        examples=[",antinuke guildupdate on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an guildupdate"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="guildupdate")
    @is_owner_or_antinuke_admin()
    async def antinuke_guildupdate(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "guildupdate", rest)

    @command_meta(
        category="Security",
        description="Punishes members who update integrations too quickly.",
        syntax=",antinuke integration (status) [flags]",
        examples=[",antinuke integration on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an integration"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="integration")
    @is_owner_or_antinuke_admin()
    async def antinuke_integration(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "integration", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create too many integrations too quickly.",
        syntax=",antinuke integrationcreate (status) [flags]",
        examples=[",antinuke integrationcreate on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an integrationcreate"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="integrationcreate")
    @is_owner_or_antinuke_admin()
    async def antinuke_integrationcreate(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "integrationcreate", rest)

    @command_meta(
        category="Security",
        description="Punishes members who delete too many integrations too quickly.",
        syntax=",antinuke integrationdelete (status) [flags]",
        examples=[",antinuke integrationdelete on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an integrationdelete"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="integrationdelete")
    @is_owner_or_antinuke_admin()
    async def antinuke_integrationdelete(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "integrationdelete", rest)

    @command_meta(
        category="Security",
        description="Punishes members who update too many integrations too quickly.",
        syntax=",antinuke integrationupdate (status) [flags]",
        examples=[",antinuke integrationupdate on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an integrationupdate"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="integrationupdate")
    @is_owner_or_antinuke_admin()
    async def antinuke_integrationupdate(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "integrationupdate", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete too many invites too quickly.",
        syntax=",antinuke invite (status) [flags]",
        examples=[",antinuke invite on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an invite"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="invite")
    @is_owner_or_antinuke_admin()
    async def antinuke_invite(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "invite", rest)

    @command_meta(
        category="Security",
        description="Punishes members who kick too many users too quickly.",
        syntax=",antinuke kick (status) [flags]",
        examples=[",antinuke kick on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an kick"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="kick")
    @is_owner_or_antinuke_admin()
    async def antinuke_kick(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "kick", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete/update too many roles too quickly.",
        syntax=",antinuke role (status) [flags]",
        examples=[",antinuke role on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an role"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="role")
    @is_owner_or_antinuke_admin()
    async def antinuke_role(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "role", rest)

    @command_meta(
        category="Security",
        description="Punishes members who add/remove too many soundboard sounds too quickly.",
        syntax=",antinuke soundboard (status) [flags]",
        examples=[",antinuke soundboard on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an soundboard"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="soundboard")
    @is_owner_or_antinuke_admin()
    @requires_premium("server")
    async def antinuke_soundboard(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "soundboard", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete/update too many stickers too quickly.",
        syntax=",antinuke sticker (status) [flags]",
        examples=[",antinuke sticker on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an sticker"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="sticker")
    @is_owner_or_antinuke_admin()
    async def antinuke_sticker(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "sticker", rest)

    @command_meta(
        category="Security",
        description="Punishes members who change the server's vanity invite too quickly.",
        syntax=",antinuke vanity (status) [flags]",
        examples=[",antinuke vanity on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an vanity"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="vanity")
    @is_owner_or_antinuke_admin()
    @requires_premium("server")
    async def antinuke_vanity(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "vanity", rest)

    @command_meta(
        category="Security",
        description="Punishes members who create/delete/update too many webhooks too quickly.",
        syntax=",antinuke webhook (status) [flags]",
        examples=[",antinuke webhook on --do ban --threshold 3 --command on"],
        permissions=["⚠️ Antinuke Admin"],
        aliases=["an webhook"],
        flags=MODULE_FLAGS,
        require_args=False,
    )
    @antinuke.command(name="webhook")
    @is_owner_or_antinuke_admin()
    async def antinuke_webhook(self, ctx: commands.Context, *, rest: str = ""):
        await _run_module_command(ctx, "webhook", rest)

    # ---------------------------------------------------------- honeypot / joingate

    @command_meta(
        category="Security",
        description="Configures a honeypot channel - anyone who posts there gets caught automatically.",
        syntax=",honeypot",
        examples=[],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.group(name="honeypot", invoke_without_command=True)
    @has_permission_or_fake("administrator")
    @commands.guild_only()
    async def honeypot(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)

        if not cfg.channel_id or not cfg.enabled:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: No honeypot is configured. Run `honeypot setup` to create one.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        await self._send_honeypot_config_embed(ctx, cfg)

    @honeypot.command(name="help")
    async def honeypot_help(self, ctx: commands.Context):
        await send_help(ctx, "honeypot")

    async def _send_honeypot_config_embed(self, ctx: commands.Context, cfg) -> None:
        channel = ctx.guild.get_channel(cfg.channel_id)
        channel_display = channel.mention if channel else f"`{cfg.channel_id}` (deleted)"
        log_channel = ctx.guild.get_channel(cfg.log_channel_id) if cfg.log_channel_id else None
        log_display = log_channel.mention if log_channel else "None"
        enabled_display = "✅" if cfg.enabled else "❌"

        description = (
            f"**Channel:** {channel_display}\n\n"
            f"**Action** {cfg.action}\n\n"
            f"**Purge on removal:** {cfg.purge_days}d\n\n"
            f"**Log channel:** {log_display}\n\n"
            f"**Enabled:** {enabled_display}\n\n"
            f"**Total caught:** {cfg.caught_count}"
        )
        embed = discord.Embed(title="Honeypot configuration", description=description)
        await ctx.send(embed=embed)

    @command_meta(
        category="Security",
        description="Creates and arms a honeypot channel - anyone who posts there gets caught automatically.",
        syntax=",honeypot setup",
        examples=[",honeypot setup"],
        permissions=["Administrator"],
        require_args=False,
    )
    @honeypot.command(name="setup")
    @has_permission_or_fake("administrator")
    @commands.bot_has_permissions(manage_channels=True, manage_messages=True)
    async def honeypot_setup(self, ctx: commands.Context):
        try:
            channel = await ctx.guild.create_text_channel(name="honeypot", category=None, reason=f"Honeypot created by {ctx.author}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to create channels.")
            return

        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
            await security_repository.update_honeypot_config(
                session, cfg, channel_id=channel.id, enabled=True, caught_count=0, message_id=None,
            )

        view = _build_honeypot_view(0)
        message = None
        try:
            message = await channel.send(view=view)
            await message.pin(reason="Honeypot warning message")
        except discord.HTTPException:
            pass

        if message is not None:
            async with get_session() as session:
                cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
                await security_repository.update_honeypot_config(session, cfg, message_id=message.id)

        await ctx.success(
            f"{ctx.author.mention}: Honeypot armed in {channel.mention}. Anyone who posts there will be banned. "
            f"Change this with `honeypot action (ban|kick|softban)`"
        )

    @command_meta(
        category="Security",
        description="Sets the action taken against anyone who triggers the honeypot.",
        syntax=",honeypot action <ban|kick|softban>",
        examples=[",honeypot action softban"],
        permissions=["Administrator"],
    )
    @honeypot.command(name="action")
    @has_permission_or_fake("administrator")
    async def honeypot_action(self, ctx: commands.Context, action: str):
        action = action.lower()
        if action not in ("ban", "kick", "softban"):
            await ctx.error("Action must be `ban`, `kick`, or `softban`.")
            return
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
            await security_repository.update_honeypot_config(session, cfg, action=action)
        await ctx.success(f"{ctx.author.mention}: Honeypot action set to **{action}**.")

    @command_meta(
        category="Security",
        description="Shows the current honeypot configuration.",
        syntax=",honeypot config",
        examples=[",honeypot config"],
        permissions=["Administrator"],
        require_args=False,
    )
    @honeypot.command(name="config")
    @has_permission_or_fake("administrator")
    async def honeypot_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)

        if not cfg.channel_id or not cfg.enabled:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: No honeypot is configured. Run `honeypot setup` to create one.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        await self._send_honeypot_config_embed(ctx, cfg)

    @command_meta(
        category="Security",
        description="Disables the honeypot without deleting its configuration or channel.",
        syntax=",honeypot disable",
        examples=[",honeypot disable"],
        permissions=["Administrator"],
        require_args=False,
    )
    @honeypot.command(name="disable")
    @has_permission_or_fake("administrator")
    async def honeypot_disable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
            await security_repository.update_honeypot_config(session, cfg, enabled=False)
        await ctx.success(f"{ctx.author.mention}: Honeypot disabled.")

    @command_meta(
        category="Security",
        description="Sets how many days of the offender's messages to purge on ban/softban (0-7).",
        syntax=",honeypot history <days>",
        examples=[",honeypot history 3"],
        permissions=["Administrator"],
    )
    @honeypot.command(name="history")
    @has_permission_or_fake("administrator")
    async def honeypot_history(self, ctx: commands.Context, days: int):
        days = max(0, min(days, 7))
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
            await security_repository.update_honeypot_config(session, cfg, purge_days=days)
        await ctx.success(f"{ctx.author.mention}: Set the purge window to `{days}` day(s).")

    @command_meta(
        category="Security",
        description="Sets the channel where honeypot catches are logged.",
        syntax=",honeypot logs <channel>",
        examples=[",honeypot logs #mod-logs"],
        permissions=["Administrator"],
    )
    @honeypot.command(name="logs")
    @has_permission_or_fake("administrator")
    async def honeypot_logs(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await security_repository.get_or_create_honeypot_config(session, ctx.guild.id)
            await security_repository.update_honeypot_config(session, cfg, log_channel_id=channel.id)
        await ctx.success(f"{ctx.author.mention}: Honeypot catches will now be logged to {channel.mention}.")

    @command_meta(
        category="Security",
        description="Removes the honeypot configuration (leaves the channel intact).",
        syntax=",honeypot remove",
        examples=[",honeypot remove"],
        permissions=["Administrator"],
        require_args=False,
    )
    @honeypot.command(name="remove")
    @has_permission_or_fake("administrator")
    async def honeypot_remove(self, ctx: commands.Context):
        async with get_session() as session:
            removed = await security_repository.delete_honeypot_config(session, ctx.guild.id)
        if removed:
            await ctx.success(f"{ctx.author.mention}: Removed the honeypot configuration. The channel has been left intact.")
        else:
            await ctx.error("No honeypot is configured.")


    # ---------------------------------------------------------- ,fakepermissions

    @command_meta(
        category="Security",
        description="Shows every Discord permission name that can be granted through fake permissions.",
        syntax=",fakepermissions",
        examples=[",fakepermissions"],
        permissions=["Server Owner"],
        aliases=["fp"],
        require_args=False,
    )
    @commands.group(name="fakepermissions", aliases=["fp"], invoke_without_command=True)
    @commands.guild_only()
    @is_server_owner()
    async def fakepermissions(self, ctx: commands.Context):
        names = sorted(discord.Permissions.VALID_FLAGS.keys())
        chunks = [names[i:i + 15] for i in range(0, len(names), 15)]

        pages = []
        for chunk_index, chunk in enumerate(chunks):
            start = chunk_index * 15
            lines = [f"`{start + i + 1:02d}` **{name}**" for i, name in enumerate(chunk)]
            embed = discord.Embed(
                title="Fakepermissions",
                description=(
                    "Each line is a Discord permission name you can grant with `fakepermissions add`.\n\n"
                    + "\n".join(lines)
                ),
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text=f"{len(names)} entries")
            pages.append(embed)

        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    @command_meta(
        category="Security",
        description=(
            "Grants a role a fake permission - lets it use bot commands gated on that permission, without "
            "actually granting it in Discord (e.g. ban_members lets it ,ban through the bot, but not ban "
            "through Discord itself)."
        ),
        syntax=",fakepermissions add <role> <permission>",
        examples=[",fakepermissions add @Staff ban_members"],
        permissions=["Server Owner"],
    )
    @fakepermissions.command(name="add")
    @is_server_owner()
    async def fakepermissions_add(self, ctx: commands.Context, role: discord.Role, permission: str):
        permission = permission.lower()
        if permission not in discord.Permissions.VALID_FLAGS:
            await ctx.error(f"`{permission}` is not a valid permission name. Run `,fakepermissions` to see the list.")
            return

        async with get_session() as session:
            denied = await denyperm_repository.is_permission_denied(session, ctx.guild.id, permission)
        if denied:
            await ctx.error(f"`{permission}` is blocked from being assigned via role commands. Run `,denyperm remove {permission}` first if this was intended.")
            return

        async with get_session() as session:
            added = await security_repository.add_fake_permission(session, ctx.guild.id, role.id, permission)

        if added:
            await ctx.success(f"{role.mention} now has the fake permission `{permission}`.")
        else:
            await ctx.error(f"{role.mention} already has the fake permission `{permission}`.")

    @command_meta(
        category="Security",
        description="Removes a fake permission from a role.",
        syntax=",fakepermissions remove <role> <permission>",
        examples=[",fakepermissions remove @Staff ban_members"],
        permissions=["Server Owner"],
    )
    @fakepermissions.command(name="remove")
    @is_server_owner()
    async def fakepermissions_remove(self, ctx: commands.Context, role: discord.Role, permission: str):
        permission = permission.lower()
        async with get_session() as session:
            removed = await security_repository.remove_fake_permission(session, ctx.guild.id, role.id, permission)

        if removed:
            await ctx.success(f"Removed the fake permission `{permission}` from {role.mention}.")
        else:
            await ctx.error(f"{role.mention} doesn't have the fake permission `{permission}`.")

    @command_meta(
        category="Security",
        description="Lists fake permissions - for a specific role, or every role that has any if none is given.",
        syntax=",fakepermissions list [role]",
        examples=[",fakepermissions list", ",fakepermissions list @Staff"],
        permissions=["Server Owner"],
        require_args=False,
    )
    @fakepermissions.command(name="list")
    @is_server_owner()
    async def fakepermissions_list(self, ctx: commands.Context, role: discord.Role = None):
        async with get_session() as session:
            if role is not None:
                perms = await security_repository.get_fake_permissions_for_role(session, ctx.guild.id, role.id)
                if not perms:
                    await ctx.info(f"{role.mention} has no fake permissions.")
                    return
                lines = [f"`{i + 1:02d}` **{p}**" for i, p in enumerate(perms)]
                embed = discord.Embed(title=f"Fake Permissions — {role.name}", description="\n".join(lines))
                await ctx.send(embed=embed)
                return

            entries = await security_repository.get_all_fake_permissions(session, ctx.guild.id)

        if not entries:
            await ctx.info("No fake permissions have been granted in this server.")
            return

        by_role: dict[int, list[str]] = {}
        for entry in entries:
            by_role.setdefault(entry.role_id, []).append(entry.permission)

        lines = []
        for role_id, perms in by_role.items():
            role_obj = ctx.guild.get_role(role_id)
            role_name = role_obj.mention if role_obj else f"`{role_id}`"
            lines.append(f"{role_name}: {', '.join(sorted(perms))}")

        embed = discord.Embed(title="Fake Permissions", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Security",
        description="Removes every fake permission granted in this server.",
        syntax=",fakepermissions reset",
        examples=[",fakepermissions reset"],
        permissions=["Server Owner"],
        require_args=False,
    )
    @fakepermissions.command(name="reset")
    @is_server_owner()
    async def fakepermissions_reset(self, ctx: commands.Context):
        async with get_session() as session:
            await security_repository.reset_fake_permissions(session, ctx.guild.id)
        await ctx.success("All fake permissions have been reset.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Security(bot))
