"""Level system commands."""

from __future__ import annotations

import discord
from discord.ext import commands

from core import embeds
from core.checks import has_permission_or_fake, is_server_owner, requires_premium
from core.command_meta import command_meta
from core.paginator import Paginator
from database.database import get_session
from repositories import level_repository
from services import level_service, premium_service


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        user, leveled_up = await level_service.award_message_xp(message.author, message.channel.id)
        if not leveled_up:
            return

        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, message.guild.id)

        from core.variables import resolve_variables
        text = resolve_variables(cfg.levelup_message, member=message.author, level=user.level, xp=user.total_xp)

        target_channel = message.channel
        if cfg.levelup_channel_id:
            fetched = message.guild.get_channel(cfg.levelup_channel_id)
            if fetched is not None:
                target_channel = fetched

        try:
            await target_channel.send(text)
        except discord.HTTPException:
            pass

    # ---------------------------------------------------------- ,levels [member]

    @command_meta(
        category="Server",
        description="Shows your (or another member's) level stats.",
        syntax=",levels [member]",
        examples=[",levels", ",levels @User"],
        require_args=False,
    )
    @commands.group(name="levels", invoke_without_command=True)
    @commands.guild_only()
    async def levels(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        async with get_session() as session:
            user = await level_repository.get_or_create_user(session, ctx.guild.id, member.id)

        embed = discord.Embed(
            title=f"{member.display_name}'s Level Stats",
            description=f"Total XP: {user.total_xp}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(user.level), inline=False)
        embed.add_field(name="Text Stats", value=f"XP: `{user.text_xp}`\nMessages: `{user.message_count}`", inline=True)
        embed.add_field(name="Voice Stats", value=f"XP: `{user.voice_xp}`\nTime spent: `{user.voice_minutes}` min", inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- ,levels reset

    @command_meta(
        category="Server",
        description="Resets ALL level data for this server. Server owner only.",
        syntax=",levels reset",
        examples=[",levels reset"],
        permissions=["Server Owner"],
        require_args=False,
    )
    @levels.command(name="reset")
    @is_server_owner()
    async def levels_reset(self, ctx: commands.Context):
        await ctx.send(embed=embeds.warning(
            "This will permanently delete ALL level data for this server. Type `confirm` within 30s to proceed."
        ))

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower() == "confirm"

        try:
            await self.bot.wait_for("message", check=check, timeout=30)
        except TimeoutError:
            await ctx.info("Reset cancelled.")
            return

        async with get_session() as session:
            await level_repository.reset_guild(session, ctx.guild.id)
        await ctx.success("All level data for this server has been reset.")

    # ---------------------------------------------------------- ,levels lock / unlock

    @command_meta(
        category="Server",
        description="Disables XP gain for this server.",
        syntax=",levels lock",
        examples=[",levels lock"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @levels.command(name="lock")
    @has_permission_or_fake("manage_guild")
    async def levels_lock(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.enabled = False
            await session.commit()
        await ctx.success("Leveling locked. No further XP will be awarded.")

    @command_meta(
        category="Server",
        description="Enables XP gain for this server.",
        syntax=",levels unlock",
        examples=[",levels unlock"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @levels.command(name="unlock")
    @has_permission_or_fake("manage_guild")
    async def levels_unlock(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.enabled = True
            await session.commit()
        await ctx.success("Leveling unlocked. Members will now earn XP.")

    # ---------------------------------------------------------- ,levels stackroles

    @command_meta(
        category="Server",
        description="Toggles whether members keep every earned level role or only the highest.",
        syntax=",levels stackroles <on|off>",
        examples=[",levels stackroles on"],
        permissions=["Manage Guild"],
    )
    @levels.command(name="stackroles")
    @has_permission_or_fake("manage_guild")
    async def levels_stackroles(self, ctx: commands.Context, state: str):
        value = state.lower() in ("on", "true", "enable", "enabled")
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.stack_roles = value
            await session.commit()
        await ctx.success(f"Stack roles is now **{'on' if value else 'off'}**.")

    # ---------------------------------------------------------- ,levels config

    @command_meta(
        category="Server",
        description="Shows the current level system configuration.",
        syntax=",levels config",
        examples=[",levels config"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @levels.command(name="config")
    @has_permission_or_fake("manage_guild")
    async def levels_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            roles = await level_repository.get_roles(session, ctx.guild.id)
            ignored = await level_repository.get_ignored(session, ctx.guild.id)

        embed = embeds.config_embed(title="Level Configuration")
        if not cfg.enabled:
            embed.description = "🔒 **Leveling is locked.** Run `,levels unlock` to start awarding XP."

        embed.add_field(name="Status", value="🔒 Locked" if not cfg.enabled else "🔓 Unlocked", inline=True)
        embed.add_field(name="Stack Roles", value=str(cfg.stack_roles), inline=True)
        embed.add_field(name="Multiplier", value=f"{cfg.multiplier}x", inline=True)
        embed.add_field(name="Level-up Channel", value=f"<#{cfg.levelup_channel_id}>" if cfg.levelup_channel_id else "Current channel", inline=True)
        embed.add_field(name="Leaderboard Title", value=cfg.leaderboard_title, inline=True)
        embed.add_field(name="XP Cooldown", value=f"{cfg.xp_cooldown_seconds}s", inline=True)
        embed.add_field(name="Level Roles Configured", value=str(len(roles)), inline=True)
        embed.add_field(name="Ignored Roles/Channels", value=str(len(ignored)), inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- ,levels setrate

    @command_meta(
        category="Server",
        description="Sets the server-wide XP multiplier.",
        syntax=",levels setrate <multiplier>",
        examples=[",levels setrate 2"],
        permissions=["Manage Guild"],
    )
    @levels.command(name="setrate")
    @has_permission_or_fake("manage_guild")
    async def levels_setrate(self, ctx: commands.Context, multiplier: float):
        multiplier = max(0.1, min(multiplier, 10.0))
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.multiplier = multiplier
            await session.commit()
        await ctx.success(f"XP multiplier set to `{multiplier}x`.")

    # ---------------------------------------------------------- ,levels ignore

    @command_meta(
        category="Server",
        description="Ignores a role or channel so it no longer earns/grants XP.",
        syntax=",levels ignore <role|channel>",
        examples=[",levels ignore @Bots", ",levels ignore #spam"],
        permissions=["Manage Guild"],
    )
    @levels.command(name="ignore", with_app_command=False)
    @has_permission_or_fake("manage_guild")
    async def levels_ignore(self, ctx: commands.Context, target: discord.Role | discord.TextChannel):
        target_type = "role" if isinstance(target, discord.Role) else "channel"
        async with get_session() as session:
            await level_repository.add_ignored(session, ctx.guild.id, target.id, target_type)
        await ctx.success(f"{target.mention} is now ignored for leveling.")

    # ---------------------------------------------------------- ,levels roles / add role / remove

    @command_meta(
        category="Server",
        description="Lists all configured level roles.",
        syntax=",levels roles",
        examples=[",levels roles"],
        require_args=False,
    )
    @levels.command(name="roles")
    async def levels_roles(self, ctx: commands.Context):
        async with get_session() as session:
            roles = await level_repository.get_roles(session, ctx.guild.id)

        if not roles:
            await ctx.info("No level roles configured yet.")
            return

        lines = [f"`{i:02d}` <@&{r.role_id}> — Level {r.level_required}" for i, r in enumerate(roles, start=1)]
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        pages = [
            embeds.help_embed(title="Level Roles", description="\n".join(chunk))
            for chunk in chunks
        ]
        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    @command_meta(
        category="Server",
        description="Creates or updates a level role.",
        syntax=",levels add role <role> <level>",
        examples=[",levels add role @Level5 5"],
        permissions=["Manage Guild"],
    )
    @levels.group(name="add", invoke_without_command=False)
    @has_permission_or_fake("manage_guild")
    async def levels_add(self, ctx: commands.Context):
        pass

    @levels_add.command(name="role")
    @has_permission_or_fake("manage_guild")
    async def levels_add_role(self, ctx: commands.Context, role: discord.Role, level: int):
        async with get_session() as session:
            existing_roles = await level_repository.get_roles(session, ctx.guild.id)
            is_new = not any(r.rank == level for r in existing_roles)
            if is_new:
                allowed, limit = await premium_service.check_limit(ctx.guild.id, "level_role_rewards", len(existing_roles))
                if not allowed:
                    is_prem = await premium_service.is_premium(ctx.guild.id, "server")
                    await ctx.error(premium_service.limit_reached_message("level role rewards", limit, is_prem))
                    return
            await level_repository.add_role(session, ctx.guild.id, level, role.id, level)
        await ctx.success(f"{role.mention} will now be given at level {level}.")

    @command_meta(
        category="Server",
        description="Removes a configured level role by its level number.",
        syntax=",levels remove <level>",
        examples=[",levels remove 5"],
        permissions=["Manage Guild"],
    )
    @levels.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def levels_remove(self, ctx: commands.Context, level: int):
        async with get_session() as session:
            removed = await level_repository.remove_role(session, ctx.guild.id, level)
        if removed:
            await ctx.success(f"Removed the level role at level `{level}`.")
        else:
            await ctx.error(f"No level role found for level `{level}`.")

    # ---------------------------------------------------------- ,levels leaderboard

    @command_meta(
        category="Server",
        description="Shows the server's XP leaderboard.",
        syntax=",levels leaderboard",
        examples=[",levels leaderboard"],
        require_args=False,
        aliases=["lb"],
    )
    @levels.group(name="leaderboard", aliases=["lb"], invoke_without_command=True)
    async def levels_leaderboard(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            top = await level_repository.get_leaderboard(session, ctx.guild.id, limit=10)

        if not top:
            await ctx.info("No leveling data yet.")
            return

        lines = [
            f"`#{i}` <@{u.user_id}> (`{u.user_id}`) — Level {u.level} • {u.total_xp} XP"
            for i, u in enumerate(top, start=1)
        ]
        embed = embeds.help_embed(title=cfg.leaderboard_title, description="\n".join(lines))
        await ctx.send(embed=embed)

    @levels_leaderboard.command(name="rename")
    @has_permission_or_fake("manage_guild")
    async def levels_leaderboard_rename(self, ctx: commands.Context, *, title: str):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.leaderboard_title = title[:128]
            await session.commit()
        await ctx.success(f"Leaderboard title set to `{title}`.")

    # ---------------------------------------------------------- ,levels message

    @command_meta(
        category="Server",
        description="Sets the message sent when a member levels up.",
        syntax=",levels message <text>",
        examples=[",levels message {user.mention} hit Level {level}!"],
        permissions=["Manage Guild"],
    )
    @levels.group(name="message", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @requires_premium("server")
    async def levels_message(self, ctx: commands.Context, *, text: str):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
            cfg.levelup_message = text[:512]
            await session.commit()
        await ctx.success("Level-up message updated.")

    @levels_message.command(name="view")
    @has_permission_or_fake("manage_guild")
    async def levels_message_view(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await level_repository.get_or_create_config(session, ctx.guild.id)
        from core.variables import resolve_variables
        rendered = resolve_variables(cfg.levelup_message, member=ctx.author, level=99)
        await ctx.send(rendered)

    # ---------------------------------------------------------- ,levels list

    @command_meta(
        category="Server",
        description="Lists ignored roles and channels for leveling.",
        syntax=",levels list",
        examples=[",levels list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @levels.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def levels_list(self, ctx: commands.Context):
        async with get_session() as session:
            ignored = await level_repository.get_ignored(session, ctx.guild.id)

        roles = [f"<@&{i.target_id}>" for i in ignored if i.target_type == "role"]
        channels = [f"<#{i.target_id}>" for i in ignored if i.target_type == "channel"]

        embed = embeds.config_embed(title="Ignored Roles/Channels")
        embed.add_field(name="Roles", value="\n".join(roles) or "None", inline=True)
        embed.add_field(name="Channels", value="\n".join(channels) or "None", inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- XP admin commands

    @command_meta(
        category="Server",
        description="Sets a member's total XP.",
        syntax=",setxp <member> <amount>",
        examples=[",setxp @User 500"],
        permissions=["Manage Guild"],
    )
    @commands.command(name="setxp")
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def setxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        async with get_session() as session:
            user = await level_repository.set_xp(session, ctx.guild.id, member.id, amount)
            user.level = level_service.level_from_xp(user.total_xp)
            await session.commit()
        await level_service.sync_roles(member, user.level)
        await ctx.success(f"Set **{member}**'s XP to `{amount}` (Level {user.level}).")

    @command_meta(
        category="Server",
        description="Removes XP from a member.",
        syntax=",removexp <member> <amount>",
        examples=[",removexp @User 100"],
        permissions=["Manage Guild"],
    )
    @commands.command(name="removexp")
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def removexp(self, ctx: commands.Context, member: discord.Member, amount: int):
        async with get_session() as session:
            user = await level_repository.remove_xp(session, ctx.guild.id, member.id, amount)
            user.level = level_service.level_from_xp(user.total_xp)
            await session.commit()
        await level_service.sync_roles(member, user.level)
        await ctx.success(f"Removed `{amount}` XP from **{member}** (Level {user.level}).")

    @command_meta(
        category="Server",
        description="Sets a member's level directly.",
        syntax=",setlevel <member> <level>",
        examples=[",setlevel @User 10"],
        permissions=["Manage Guild"],
    )
    @commands.command(name="setlevel")
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def setlevel(self, ctx: commands.Context, member: discord.Member, level: int):
        async with get_session() as session:
            user = await level_repository.set_level(session, ctx.guild.id, member.id, level)
            user.total_xp = level_service.xp_for_level(level)
            await session.commit()
        await level_service.sync_roles(member, level)
        await ctx.success(f"Set **{member}**'s level to `{level}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
