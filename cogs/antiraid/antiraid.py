"""
Antiraid - ,antiraid. Separate from antinuke (audit-log/staff-action
watching) - this watches new members and message bursts instead.

All commands need Manage Guild. The username-pattern module is
described in the reference as "Premium" but this bot has no actual
monetization/tier system, so it's implemented as a normal feature -
that label is cosmetic only, nothing gates it.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake, requires_premium
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import antiraid_repository
from services import antiraid_service

VALID_ACTIONS = ("ban", "kick", "timeout", "jail")


def _on_off(value: str) -> bool:
    return value.lower() in ("on", "true", "enable", "enabled")


class Antiraid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await antiraid_service.handle_member_join(member)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await antiraid_service.handle_message(message)

    # ---------------------------------------------------------- root

    @command_meta(
        category="Security",
        description="Protect your server against raids.",
        syntax=",antiraid",
        examples=[],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.group(name="antiraid", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def antiraid(self, ctx: commands.Context):
        await send_help(ctx, "antiraid")

    @antiraid.command(name="help")
    async def antiraid_help(self, ctx: commands.Context):
        await send_help(ctx, "antiraid")

    # ---------------------------------------------------------- toggle

    @command_meta(
        category="Security",
        description="Enable or disable the antiraid system.",
        syntax=",antiraid toggle (status)",
        examples=[",antiraid toggle on"],
        permissions=["Manage Guild"],
    )
    @antiraid.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def antiraid_toggle(self, ctx: commands.Context, status: str):
        value = _on_off(status)
        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, enabled=value)
        await ctx.success(f"{ctx.author.mention}: Antiraid is now **{'enabled' if value else 'disabled'}**.")

    # ---------------------------------------------------------- age

    @command_meta(
        category="Security",
        description="Kick or ban members with young accounts.",
        syntax=",antiraid age (status) [rest] [--flags]",
        examples=[",antiraid age on --do kick --threshold 3"],
        permissions=["Manage Guild"],
        flags=[
            ("--do (action)", "Punishment to apply (ban/kick/timeout/jail)."),
            ("--threshold (days)", "Minimum account age in days."),
        ],
    )
    @antiraid.command(name="age")
    @has_permission_or_fake("manage_guild")
    async def antiraid_age(self, ctx: commands.Context, status: str, *, rest: str = ""):
        value = _on_off(status)
        flags = antiraid_service.parse_flags(rest)
        updates: dict = {"age_enabled": value}

        if "do" in flags:
            action = flags["do"].lower()
            if action not in VALID_ACTIONS:
                await ctx.error(f"`--do` must be one of: {', '.join(VALID_ACTIONS)}.")
                return
            updates["age_action"] = action

        if "threshold" in flags:
            try:
                updates["age_threshold_days"] = max(0, int(flags["threshold"]))
            except ValueError:
                await ctx.error("`--threshold` must be a whole number of days.")
                return

        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, **updates)

        await ctx.success(f"{ctx.author.mention}: Updated the account-age module.")

    # ---------------------------------------------------------- avatar

    @command_meta(
        category="Security",
        description="Kick or ban members joining with a default avatar.",
        syntax=",antiraid avatar (status) [rest] [--flags]",
        examples=[",antiraid avatar on --do kick"],
        permissions=["Manage Guild"],
        flags=[("--do (action)", "Punishment to apply (ban/kick/timeout/jail).")],
    )
    @antiraid.command(name="avatar")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def antiraid_avatar(self, ctx: commands.Context, status: str, *, rest: str = ""):
        value = _on_off(status)
        flags = antiraid_service.parse_flags(rest)
        updates: dict = {"avatar_enabled": value}

        if "do" in flags:
            action = flags["do"].lower()
            if action not in VALID_ACTIONS:
                await ctx.error(f"`--do` must be one of: {', '.join(VALID_ACTIONS)}.")
                return
            updates["avatar_action"] = action

        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, **updates)

        await ctx.success(f"{ctx.author.mention}: Updated the default-avatar module.")

    # ---------------------------------------------------------- config

    @command_meta(
        category="Security",
        description="View the antiraid configuration.",
        syntax=",antiraid config",
        examples=[",antiraid config"],
        permissions=["Manage Guild"],
        aliases=["settings", "show"],
        require_args=False,
    )
    @antiraid.command(name="config", aliases=["settings", "show"])
    @has_permission_or_fake("manage_guild")
    async def antiraid_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await antiraid_repository.get_config(session, ctx.guild.id)

        if cfg is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Antiraid is not configured for this server.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        def flag(value: bool) -> str:
            return "✅" if value else "❌"

        description = (
            f"**Enabled:** {flag(cfg.enabled)}\n"
            f"**Locked down:** {flag(cfg.locked_down)}\n\n"
            f"**Age** {flag(cfg.age_enabled)} — action `{cfg.age_action}`, min `{cfg.age_threshold_days}`d\n"
            f"**Avatar** {flag(cfg.avatar_enabled)} — action `{cfg.avatar_action}`\n"
            f"**Mass-join** {flag(cfg.massjoin_enabled)} — action `{cfg.massjoin_action}`, "
            f"threshold `{cfg.massjoin_threshold}`, lock `{cfg.massjoin_lock}`, punish `{cfg.massjoin_punish}`\n"
            f"**Mass-mention** {flag(cfg.massmention_enabled)} — action `{cfg.massmention_action}`, "
            f"threshold `{cfg.massmention_threshold}`, window `{cfg.massmention_timeframe}s`, lock `{cfg.massmention_lock}`\n"
            f"**Unverified bots** {flag(cfg.unverifiedbots_enabled)} — action `{cfg.unverifiedbots_action}`"
        )
        embed = discord.Embed(title="Antiraid Configuration", description=description)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- massjoin

    @command_meta(
        category="Security",
        description="Configure mass-join protection.",
        syntax=",antiraid massjoin (status) [rest] [--flags]",
        examples=[",antiraid massjoin on --do kick --threshold 10 --lock on --punish on"],
        permissions=["Manage Guild"],
        flags=[
            ("--do (action)", "Punishment to apply (ban/kick/timeout/jail)."),
            ("--threshold (count)", "Joins within the window before punishing."),
            ("--lock (on|off)", "Also lock the server down."),
            ("--punish (on|off)", "Also punish recent joiners when a raid is detected."),
        ],
    )
    @antiraid.command(name="massjoin")
    @has_permission_or_fake("manage_guild")
    async def antiraid_massjoin(self, ctx: commands.Context, status: str, *, rest: str = ""):
        value = _on_off(status)
        flags = antiraid_service.parse_flags(rest)
        updates: dict = {"massjoin_enabled": value}

        if "do" in flags:
            action = flags["do"].lower()
            if action not in VALID_ACTIONS:
                await ctx.error(f"`--do` must be one of: {', '.join(VALID_ACTIONS)}.")
                return
            updates["massjoin_action"] = action

        if "threshold" in flags:
            try:
                updates["massjoin_threshold"] = max(2, int(flags["threshold"]))
            except ValueError:
                await ctx.error("`--threshold` must be a whole number.")
                return

        if "lock" in flags:
            updates["massjoin_lock"] = _on_off(flags["lock"])

        if "punish" in flags:
            updates["massjoin_punish"] = _on_off(flags["punish"])

        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, **updates)

        await ctx.success(f"{ctx.author.mention}: Updated the mass-join module.")

    # ---------------------------------------------------------- massmention

    @command_meta(
        category="Security",
        description="Detect mass mentions.",
        syntax=",antiraid massmention (status) [rest] [--flags]",
        examples=[",antiraid massmention on --threshold 5 --timeframe 10 --do timeout"],
        permissions=["Manage Guild"],
        flags=[
            ("--threshold (count)", "Mentions within the window before punishing."),
            ("--timeframe (seconds)", "Detection window."),
            ("--lock (on|off)", "Also lock the server down."),
            ("--do (action)", "Punishment to apply (ban/kick/timeout/jail)."),
        ],
    )
    @antiraid.command(name="massmention")
    @has_permission_or_fake("manage_guild")
    async def antiraid_massmention(self, ctx: commands.Context, status: str, *, rest: str = ""):
        value = _on_off(status)
        flags = antiraid_service.parse_flags(rest)
        updates: dict = {"massmention_enabled": value}

        if "threshold" in flags:
            try:
                updates["massmention_threshold"] = max(2, int(flags["threshold"]))
            except ValueError:
                await ctx.error("`--threshold` must be a whole number.")
                return

        if "timeframe" in flags:
            try:
                updates["massmention_timeframe"] = max(1, int(flags["timeframe"]))
            except ValueError:
                await ctx.error("`--timeframe` must be a whole number of seconds.")
                return

        if "lock" in flags:
            updates["massmention_lock"] = _on_off(flags["lock"])

        if "do" in flags:
            action = flags["do"].lower()
            if action not in VALID_ACTIONS:
                await ctx.error(f"`--do` must be one of: {', '.join(VALID_ACTIONS)}.")
                return
            updates["massmention_action"] = action

        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, **updates)

        await ctx.success(f"{ctx.author.mention}: Updated the mass-mention module.")

    # ---------------------------------------------------------- state

    @command_meta(
        category="Security",
        description="Manually toggle server lockdown.",
        syntax=",antiraid state",
        examples=[",antiraid state"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @antiraid.command(name="state")
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_roles=True)
    async def antiraid_state(self, ctx: commands.Context):
        new_state = await antiraid_service.toggle_lock_down(ctx.guild)
        if new_state:
            await ctx.success(f"{ctx.author.mention}: Server is now **locked down**.")
        else:
            await ctx.success(f"{ctx.author.mention}: Server lockdown **lifted**.")

    # ---------------------------------------------------------- unverifiedbots

    @command_meta(
        category="Security",
        description="Block unverified bots from joining.",
        syntax=",antiraid unverifiedbots (status) [rest] [--flags]",
        examples=[",antiraid unverifiedbots on --do kick"],
        permissions=["Manage Guild"],
        flags=[("--do (action)", "Punishment to apply (ban/kick/timeout/jail).")],
    )
    @antiraid.command(name="unverifiedbots")
    @has_permission_or_fake("manage_guild")
    async def antiraid_unverifiedbots(self, ctx: commands.Context, status: str, *, rest: str = ""):
        value = _on_off(status)
        flags = antiraid_service.parse_flags(rest)
        updates: dict = {"unverifiedbots_enabled": value}

        if "do" in flags:
            action = flags["do"].lower()
            if action not in VALID_ACTIONS:
                await ctx.error(f"`--do` must be one of: {', '.join(VALID_ACTIONS)}.")
                return
            updates["unverifiedbots_action"] = action

        async with get_session() as session:
            cfg = await antiraid_repository.get_or_create_config(session, ctx.guild.id)
            await antiraid_repository.update_config(session, cfg, **updates)

        await ctx.success(f"{ctx.author.mention}: Updated the unverified-bots module.")

    # ---------------------------------------------------------- username

    @command_meta(
        category="Security",
        description="Premium username-pattern filter.",
        syntax=",antiraid username (add | remove | list)",
        examples=[",antiraid username add freenitro", ",antiraid username list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @antiraid.group(name="username", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def antiraid_username(self, ctx: commands.Context):
        await send_help(ctx, "antiraid username")

    @antiraid_username.command(name="add")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def antiraid_username_add(self, ctx: commands.Context, *, pattern: str):
        pattern = pattern.lower().strip()
        async with get_session() as session:
            added = await antiraid_repository.add_username_pattern(session, ctx.guild.id, pattern)
        if added:
            await ctx.success(f"{ctx.author.mention}: Blocked usernames containing `{pattern}`.")
        else:
            await ctx.error(f"`{pattern}` is already blocked.")

    @antiraid_username.command(name="remove")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def antiraid_username_remove(self, ctx: commands.Context, *, pattern: str):
        pattern = pattern.lower().strip()
        async with get_session() as session:
            removed = await antiraid_repository.remove_username_pattern(session, ctx.guild.id, pattern)
        if removed:
            await ctx.success(f"{ctx.author.mention}: Unblocked `{pattern}`.")
        else:
            await ctx.error(f"`{pattern}` wasn't blocked.")

    @antiraid_username.command(name="list")
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def antiraid_username_list(self, ctx: commands.Context):
        async with get_session() as session:
            patterns = await antiraid_repository.get_username_patterns(session, ctx.guild.id)
        if not patterns:
            await ctx.info("No username patterns blocked.")
            return
        await ctx.send(embed=discord.Embed(
            title="Blocked Username Patterns", description=", ".join(f"`{p}`" for p in patterns)[:4000]
        ))

    # ---------------------------------------------------------- whitelist

    @command_meta(
        category="Security",
        description="Manage the antiraid whitelist.",
        syntax=",antiraid whitelist (view)",
        examples=[",antiraid whitelist"],
        permissions=["Manage Guild"],
        aliases=["wl"],
        require_args=False,
    )
    @antiraid.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def antiraid_whitelist(self, ctx: commands.Context):
        await self._show_whitelist(ctx)

    async def _show_whitelist(self, ctx: commands.Context) -> None:
        async with get_session() as session:
            entries = await antiraid_repository.get_whitelist(session, ctx.guild.id)
        if not entries:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: No antiraid modules or whitelisted users configured.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        lines = [
            f"<@&{e.target_id}>" if e.target_type == "role" else f"<@{e.target_id}>"
            for e in entries
        ]
        await ctx.send(embed=discord.Embed(title="Antiraid Whitelist", description="\n".join(lines)[:4000]))

    @antiraid_whitelist.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def antiraid_whitelist_view(self, ctx: commands.Context):
        await self._show_whitelist(ctx)

    @antiraid_whitelist.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def antiraid_whitelist_add(self, ctx: commands.Context, *, target: str):
        resolved, kind = await _resolve_role_or_member(ctx, target)
        if resolved is None:
            await ctx.error("Couldn't find that member or role.")
            return
        async with get_session() as session:
            added = await antiraid_repository.add_whitelist(session, ctx.guild.id, resolved.id, kind)
        if added:
            await ctx.success(f"{ctx.author.mention}: {resolved.mention} is now whitelisted from antiraid.")
        else:
            await ctx.error(f"{resolved.mention} is already whitelisted.")

    @antiraid_whitelist.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def antiraid_whitelist_remove(self, ctx: commands.Context, *, target: str):
        resolved, kind = await _resolve_role_or_member(ctx, target)
        if resolved is None:
            await ctx.error("Couldn't find that member or role.")
            return
        async with get_session() as session:
            removed = await antiraid_repository.remove_whitelist(session, ctx.guild.id, resolved.id)
        if removed:
            await ctx.success(f"{ctx.author.mention}: {resolved.mention} removed from the antiraid whitelist.")
        else:
            await ctx.error(f"{resolved.mention} wasn't whitelisted.")

    # ---------------------------------------------------------- list

    @command_meta(
        category="Security",
        description="Lists every enabled antiraid module and whitelisted user/role.",
        syntax=",antiraid list",
        examples=[",antiraid list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @antiraid.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def antiraid_list(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await antiraid_repository.get_config(session, ctx.guild.id)
            whitelist = await antiraid_repository.get_whitelist(session, ctx.guild.id)

        modules = []
        if cfg is not None:
            if cfg.age_enabled:
                modules.append("Age")
            if cfg.avatar_enabled:
                modules.append("Avatar")
            if cfg.massjoin_enabled:
                modules.append("Mass-join")
            if cfg.massmention_enabled:
                modules.append("Mass-mention")
            if cfg.unverifiedbots_enabled:
                modules.append("Unverified bots")

        if not modules and not whitelist:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: No antiraid modules or whitelisted users configured.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        lines = []
        if modules:
            lines.append(f"**Enabled modules:** {', '.join(modules)}")
        if whitelist:
            wl_lines = [f"<@&{e.target_id}>" if e.target_type == "role" else f"<@{e.target_id}>" for e in whitelist]
            lines.append(f"**Whitelisted:** {', '.join(wl_lines)}")

        await ctx.send(embed=discord.Embed(title="Antiraid Overview", description="\n\n".join(lines)))


async def _resolve_role_or_member(ctx: commands.Context, raw: str):
    try:
        return await commands.MemberConverter().convert(ctx, raw), "user"
    except commands.BadArgument:
        pass
    try:
        return await commands.RoleConverter().convert(ctx, raw), "role"
    except commands.BadArgument:
        return None, None


async def setup(bot: commands.Bot):
    await bot.add_cog(Antiraid(bot))