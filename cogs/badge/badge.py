"""Reward members who equip your server tag - ,badge (aliases
,servertag, ,badges). Category "Server". All subcommands need Manage
Guild.

Uses discord.py's Member.primary_guild (added for Discord's "server
tag"/clan tag feature) - this is a very new part of the API, so
attribute access is defensive throughout in case a user's client
hasn't populated it, or the library version doesn't have it yet."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.badge_models import DEFAULT_MESSAGE
from database.database import get_session
from repositories import badge_repository

VARIABLES_DESCRIPTION = (
    "**What they're repping** `{badge}`\n\n"
    "**The member** `{user.mention}` `{user.name}` `{user.display_name}` `{user.id}` `{user.avatar}` "
    "`{user.joined_at}` `{user.top_role}` `{user.join_position}` `{user.boost}`\n\n"
    "**The server** `{guild.name}` `{guild.id}` `{guild.icon}` `{guild.member_count}` `{guild.boost_count}` "
    "`{guild.boost_tier}`"
)


class Badge(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _is_repping(member: discord.Member, guild_id: int) -> tuple[bool, str]:
        """Returns (is_wearing_our_tag, tag_text)."""
        primary_guild = getattr(member, "primary_guild", None)
        if primary_guild is None:
            return False, ""
        if not getattr(primary_guild, "identity_enabled", False):
            return False, ""
        if getattr(primary_guild, "identity_guild_id", None) != guild_id:
            return False, ""
        return True, getattr(primary_guild, "tag", "") or ""

    async def _award(self, member: discord.Member, cfg, tag_text: str) -> None:
        async with get_session() as session:
            role_ids = await badge_repository.get_roles(session, member.guild.id)

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role is not None:
                try:
                    await member.add_roles(role, reason="Server tag reward")
                except discord.HTTPException:
                    pass

        async with get_session() as session:
            await badge_repository.mark_awarded(session, member.guild.id, member.id)

        channel = member.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        if channel is not None:
            resolved = resolve_variables(cfg.message_template, guild=member.guild, member=member, badge=tag_text)
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
            role_ids = await badge_repository.get_roles(session, member.guild.id)

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role is not None and role in member.roles:
                try:
                    await member.remove_roles(role, reason="No longer repping server tag")
                except discord.HTTPException:
                    pass

        async with get_session() as session:
            await badge_repository.unmark_awarded(session, member.guild.id, member.id)

    async def _check(self, member: discord.Member) -> None:
        if member.guild is None or member.bot:
            return

        async with get_session() as session:
            cfg = await badge_repository.get_config(session, member.guild.id)
        if cfg is None or not cfg.enabled:
            return

        matched, tag_text = self._is_repping(member, member.guild.id)

        async with get_session() as session:
            already_awarded = await badge_repository.is_awarded(session, member.guild.id, member.id)

        if matched and not already_awarded:
            await self._award(member, cfg, tag_text)
        elif not matched and already_awarded:
            await self._revoke(member)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        await self._check(after)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # primary_guild lives on the User, not just presence - user-level
        # changes (like unequipping a tag) may only fire here.
        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is not None:
                await self._check(member)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._check(member)

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Reward members who equip your server tag.",
        syntax=",badge",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["servertag", "badges"],
        require_args=False,
    )
    @commands.group(name="badge", aliases=["servertag", "badges"], invoke_without_command=True, with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def badge(self, ctx: commands.Context):
        await send_help(ctx, "badge")

    @badge.command(name="help")
    async def badge_help(self, ctx: commands.Context):
        await send_help(ctx, "badge")

    # ---------------------------------------------------------- toggle / channel / message

    @command_meta(
        category="Server",
        description="Turn the server tag reward on or off.",
        syntax=",badge toggle",
        examples=[",badge toggle"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @badge.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def badge_toggle(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await badge_repository.get_or_create_config(session, ctx.guild.id)
            new_state = not cfg.enabled
            await badge_repository.update_config(session, cfg, enabled=new_state)

        await ctx.success(f"Server tag rewards are now **{'enabled' if new_state else 'disabled'}**.")

    @command_meta(
        category="Server",
        description="Set where thank-you messages go.",
        syntax=",badge channel <channel>",
        examples=[",badge channel #shoutouts"],
        permissions=["Manage Guild"],
    )
    @badge.command(name="channel")
    @has_permission_or_fake("manage_guild")
    async def badge_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            cfg = await badge_repository.get_or_create_config(session, ctx.guild.id)
            await badge_repository.update_config(session, cfg, channel_id=channel.id)

        await ctx.success(f"Thank-you messages will now be posted in {channel.mention}.")

    @command_meta(
        category="Server",
        description="Set the thank-you message.",
        syntax=",badge message [script]",
        examples=[",badge message Thanks for repping our tag, {user.mention}!"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @badge.command(name="message", aliases=["msg"])
    @has_permission_or_fake("manage_guild")
    async def badge_message(self, ctx: commands.Context, *, script: str = None):
        async with get_session() as session:
            cfg = await badge_repository.get_or_create_config(session, ctx.guild.id)
            await badge_repository.update_config(session, cfg, message_template=script or DEFAULT_MESSAGE)

        await ctx.success("Updated the thank-you message." if script else "Reset the thank-you message to the default.")

    # ---------------------------------------------------------- config / reset

    @command_meta(
        category="Server",
        description="Show the current configuration.",
        syntax=",badge config",
        examples=[",badge config"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @badge.command(name="config")
    @has_permission_or_fake("manage_guild")
    async def badge_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await badge_repository.get_config(session, ctx.guild.id)
            role_ids = await badge_repository.get_roles(session, ctx.guild.id)

        if cfg is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Server tag rewards aren't configured yet.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        channel = ctx.guild.get_channel(cfg.channel_id) if cfg.channel_id else None
        roles_display = ", ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else "None"

        description = (
            f"**Enabled** {'✅' if cfg.enabled else '❌'}\n"
            f"**Channel** {channel.mention if channel else 'Not set'}\n"
            f"**Roles** {roles_display}\n\n"
            f"**Message**\n{cfg.message_template}"
        )
        embed = discord.Embed(title="Server Tag Configuration", description=description[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Clear the configuration.",
        syntax=",badge reset",
        examples=[",badge reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @badge.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def badge_reset(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await badge_repository.get_or_create_config(session, ctx.guild.id)
            await badge_repository.update_config(session, cfg, enabled=False, channel_id=None, message_template=DEFAULT_MESSAGE)
            await badge_repository.clear_config(session, ctx.guild.id)

        await ctx.success("Cleared the server tag configuration.")

    # ---------------------------------------------------------- role add/remove/list

    @command_meta(
        category="Server",
        description="Manage award roles.",
        syntax=",badge role (add | remove | list)",
        examples=[",badge role add @TagFan", ",badge role list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @badge.group(name="role", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def badge_role(self, ctx: commands.Context):
        await self.badge_role_list(ctx)

    @badge_role.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def badge_role_add(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            added = await badge_repository.add_role(session, ctx.guild.id, role.id)

        if added:
            await ctx.success(f"{role.mention} will now be given to members repping our tag.")
        else:
            await ctx.error(f"{role.mention} is already an award role.")

    @badge_role.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def badge_role_remove(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            removed = await badge_repository.remove_role(session, ctx.guild.id, role.id)

        if removed:
            await ctx.success(f"Removed {role.mention} from the award roles.")
        else:
            await ctx.error(f"{role.mention} wasn't an award role.")

    @badge_role.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def badge_role_list(self, ctx: commands.Context):
        async with get_session() as session:
            role_ids = await badge_repository.get_roles(session, ctx.guild.id)

        if not role_ids:
            await ctx.info("No award roles configured.")
            return

        lines = [f"<@&{rid}>" for rid in role_ids]
        await ctx.send(embed=discord.Embed(title="Server Tag Award Roles", description="\n".join(lines)[:4000]))

    # ---------------------------------------------------------- variables

    @command_meta(
        category="Server",
        description="Show the variables you can use in the thank-you message.",
        syntax=",badge variables",
        examples=[",badge variables"],
        require_args=False,
    )
    @badge.command(name="variables", aliases=["vars"])
    async def badge_variables(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Badge message variables",
            description=VARIABLES_DESCRIPTION,
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Every other script variable works too — these are just the ones with a value here.")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Badge(bot))