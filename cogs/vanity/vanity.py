"""Reward members who put your vanity in their custom status -
,vanity (alias ,van). Category "Server". All subcommands need Manage
Guild.

Needs the Presence intent (enabled in core/bot.py) AND "Presence
Intent" toggled on for this bot in the Discord Developer Portal
(Bot settings page) - without both, custom statuses are invisible
and this feature silently never triggers."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.vanity_models import DEFAULT_MESSAGE
from repositories import vanity_repository

VARIABLES_DESCRIPTION = (
    "**What they are repping** `{vanity}`\n\n"
    "**The member** `{user.mention}` `{user.name}` `{user.display_name}` `{user.id}` `{user.avatar}` "
    "`{user.joined_at}` `{user.top_role}` `{user.join_position}` `{user.boost}`\n\n"
    "**The server** `{guild.name}` `{guild.id}` `{guild.icon}` `{guild.member_count}` `{guild.boost_count}` "
    "`{guild.boost_tier}`"
)


class Vanity(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _get_custom_status(member: discord.Member) -> str:
        for activity in member.activities:
            if isinstance(activity, discord.CustomActivity) and activity.name:
                return activity.name
        return ""

    @staticmethod
    def _matches(status_text: str, pattern: str, strict: bool) -> bool:
        if strict:
            return status_text == pattern
        return pattern.lower() in status_text.lower()

    async def _award(self, member: discord.Member, cfg, status_text: str) -> None:
        async with get_session() as session:
            role_ids = await vanity_repository.get_roles(session, member.guild.id)

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role is not None:
                try:
                    await member.add_roles(role, reason="Vanity reward")
                except discord.HTTPException:
                    pass

        async with get_session() as session:
            await vanity_repository.mark_awarded(session, member.guild.id, member.id)

        channel = member.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        if channel is not None:
            resolved = resolve_variables(cfg.message_template, guild=member.guild, member=member, vanity=status_text)
            parsed = parse_script(resolved)
            try:
                if parsed.embed is not None:
                    await channel.send(content=parsed.content, embed=parsed.embed)
                else:
                    await channel.send(resolved)
            except discord.HTTPException:
                pass

    async def _revoke(self, member: discord.Member) -> None:
        async with get_session() as session:
            role_ids = await vanity_repository.get_roles(session, member.guild.id)

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role is not None and role in member.roles:
                try:
                    await member.remove_roles(role, reason="No longer repping vanity")
                except discord.HTTPException:
                    pass

        async with get_session() as session:
            await vanity_repository.unmark_awarded(session, member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.guild is None:
            return

        async with get_session() as session:
            cfg = await vanity_repository.get_config(session, after.guild.id)
        if cfg is None or not cfg.pattern:
            return

        status_text = self._get_custom_status(after)
        matched = self._matches(status_text, cfg.pattern, cfg.strict)

        async with get_session() as session:
            already_awarded = await vanity_repository.is_awarded(session, after.guild.id, after.id)

        if matched and not already_awarded:
            await self._award(after, cfg, status_text)
        elif not matched and already_awarded:
            await self._revoke(after)

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Reward members who put your vanity in their status.",
        syntax=",vanity",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["van"],
        require_args=False,
    )
    @commands.group(name="vanity", aliases=["van"], invoke_without_command=True, with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def vanity(self, ctx: commands.Context):
        await send_help(ctx, "vanity")

    @vanity.command(name="help")
    async def vanity_help(self, ctx: commands.Context):
        await send_help(ctx, "vanity")

    # ---------------------------------------------------------- channel / set / strict

    @command_meta(
        category="Server",
        description="Set where thank-you messages go.",
        syntax=",vanity channel <channel>",
        examples=[",vanity channel #shoutouts"],
        permissions=["Manage Guild"],
    )
    @vanity.command(name="channel")
    @has_permission_or_fake("manage_guild")
    async def vanity_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await vanity_repository.get_or_create_config(session, ctx.guild.id)
            await vanity_repository.update_config(session, cfg, channel_id=channel.id)

        await ctx.success(f"Thank-you messages will now be posted in {channel.mention}.")

    @command_meta(
        category="Server",
        description="Set the text to look for in custom statuses.",
        syntax=",vanity set [pattern]",
        examples=[",vanity set discord.gg/example"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.command(name="set")
    @has_permission_or_fake("manage_guild")
    async def vanity_set(self, ctx: commands.Context, *, pattern: str = None):
        async with get_session() as session:
            cfg = await vanity_repository.get_or_create_config(session, ctx.guild.id)
            await vanity_repository.update_config(session, cfg, pattern=pattern)

        if pattern:
            await ctx.success(f"Now watching for `{pattern}` in custom statuses.")
        else:
            await ctx.success("Cleared the vanity pattern.")

    @command_meta(
        category="Server",
        description="Require an exact match, including case and spacing.",
        syntax=",vanity strict [setting]",
        examples=[",vanity strict on", ",vanity strict off"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.command(name="strict")
    @has_permission_or_fake("manage_guild")
    async def vanity_strict(self, ctx: commands.Context, setting: str = None):
        value = setting is None or setting.lower() in ("on", "true", "enable", "enabled")

        async with get_session() as session:
            cfg = await vanity_repository.get_or_create_config(session, ctx.guild.id)
            await vanity_repository.update_config(session, cfg, strict=value)

        await ctx.success(f"Strict matching is now **{'on' if value else 'off'}**.")

    # ---------------------------------------------------------- message / config / reset

    @command_meta(
        category="Server",
        description="Set the thank-you message.",
        syntax=",vanity message [script]",
        examples=[",vanity message Thanks for repping {vanity}, {user.mention}!"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.command(name="message", aliases=["msg"])
    @has_permission_or_fake("manage_guild")
    async def vanity_message(self, ctx: commands.Context, *, script: str = None):
        async with get_session() as session:
            cfg = await vanity_repository.get_or_create_config(session, ctx.guild.id)
            await vanity_repository.update_config(session, cfg, message_template=script or DEFAULT_MESSAGE)

        await ctx.success("Updated the thank-you message." if script else "Reset the thank-you message to the default.")

    @command_meta(
        category="Server",
        description="Show the current configuration.",
        syntax=",vanity config",
        examples=[",vanity config"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.command(name="config")
    @has_permission_or_fake("manage_guild")
    async def vanity_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await vanity_repository.get_config(session, ctx.guild.id)
            role_ids = await vanity_repository.get_roles(session, ctx.guild.id)

        if cfg is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Vanity isn't configured yet.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        channel = ctx.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        roles_display = ", ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else "None"

        description = (
            f"**Pattern** {f'`{cfg.pattern}`' if cfg.pattern else 'Not set'}\n"
            f"**Strict** {'✅' if cfg.strict else '❌'}\n"
            f"**Channel** {channel.mention if channel else 'Not set'}\n"
            f"**Roles** {roles_display}\n\n"
            f"**Message**\n{cfg.message_template}"
        )
        embed = discord.Embed(title="Vanity Configuration", description=description[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Clear the configuration.",
        syntax=",vanity reset",
        examples=[",vanity reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def vanity_reset(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await vanity_repository.get_or_create_config(session, ctx.guild.id)
            await vanity_repository.update_config(
                session, cfg, pattern=None, strict=False, channel_id=None, message_template=DEFAULT_MESSAGE,
            )
            await vanity_repository.clear_config(session, ctx.guild.id)

        await ctx.success("Cleared the vanity configuration.")

    # ---------------------------------------------------------- role add/remove/list

    @command_meta(
        category="Server",
        description="Manage award roles.",
        syntax=",vanity role (add | remove | list)",
        examples=[",vanity role add @VanityFan", ",vanity role list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @vanity.group(name="role", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def vanity_role(self, ctx: commands.Context):
        await self.vanity_role_list(ctx)

    @vanity_role.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def vanity_role_add(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            added = await vanity_repository.add_role(session, ctx.guild.id, role.id)

        if added:
            await ctx.success(f"{role.mention} will now be given to repping members.")
        else:
            await ctx.error(f"{role.mention} is already an award role.")

    @vanity_role.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def vanity_role_remove(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            removed = await vanity_repository.remove_role(session, ctx.guild.id, role.id)

        if removed:
            await ctx.success(f"Removed {role.mention} from the award roles.")
        else:
            await ctx.error(f"{role.mention} wasn't an award role.")

    @vanity_role.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def vanity_role_list(self, ctx: commands.Context):
        async with get_session() as session:
            role_ids = await vanity_repository.get_roles(session, ctx.guild.id)

        if not role_ids:
            await ctx.info("No award roles configured.")
            return

        lines = [f"<@&{rid}>" for rid in role_ids]
        await ctx.send(embed=discord.Embed(title="Vanity Award Roles", description="\n".join(lines)[:4000]))

    # ---------------------------------------------------------- variables

    @command_meta(
        category="Server",
        description="Show the variables you can use in the thank-you message.",
        syntax=",vanity variables",
        examples=[",vanity variables"],
        require_args=False,
    )
    @vanity.command(name="variables", aliases=["vars"])
    async def vanity_variables(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Vanity message variables",
            description=VARIABLES_DESCRIPTION,
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Every other script variable works too — these are just the ones with a value here.")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Vanity(bot))