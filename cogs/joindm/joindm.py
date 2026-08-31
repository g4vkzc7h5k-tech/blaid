"""DM members a message when they join - ,joindm (alias ,welcomedm).
Category "Server". All subcommands need Manage Guild."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.script_parser import parse_script
from core.variables import resolve_variables
from database.database import get_session
from database.joindm_models import DEFAULT_MESSAGE
from repositories import joindm_repository


class JoinDm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with get_session() as session:
            cfg = await joindm_repository.get_config(session, member.guild.id)

        if cfg is None or not cfg.enabled:
            return

        resolved = resolve_variables(cfg.message_template, guild=member.guild, member=member)
        parsed = parse_script(resolved)

        try:
            if parsed.embed is not None:
                await member.send(content=parsed.content, embed=parsed.embed)
            else:
                await member.send(resolved)
        except discord.HTTPException:
            pass

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="DM members a message when they join.",
        syntax=",joindm",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["welcomedm"],
        require_args=False,
    )
    @commands.group(name="joindm", aliases=["welcomedm"], invoke_without_command=True, with_app_command=False)
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def joindm(self, ctx: commands.Context):
        await send_help(ctx, "joindm")

    @joindm.command(name="help")
    async def joindm_help(self, ctx: commands.Context):
        await send_help(ctx, "joindm")

    # ---------------------------------------------------------- config

    @command_meta(
        category="Server",
        description="Show the current join DM settings.",
        syntax=",joindm config",
        examples=[",joindm config"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @joindm.command(name="config")
    @has_permission_or_fake("manage_guild")
    async def joindm_config(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await joindm_repository.get_config(session, ctx.guild.id)

        if cfg is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Join DM isn't configured yet.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        description = (
            f"**Enabled** {'✅' if cfg.enabled else '❌'}\n\n"
            f"**Message**\n{cfg.message_template}"
        )
        embed = discord.Embed(title="Join DM Configuration", description=description[:4000])
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- message

    @command_meta(
        category="Server",
        description="Set the join DM message.",
        syntax=",joindm message [script]",
        examples=[",joindm message Welcome to {guild.name}, {user.mention}!"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @joindm.command(name="message", aliases=["msg"])
    @has_permission_or_fake("manage_guild")
    async def joindm_message(self, ctx: commands.Context, *, script: str = None):
        async with get_session() as session:
            cfg = await joindm_repository.get_or_create_config(session, ctx.guild.id)
            await joindm_repository.update_config(session, cfg, message_template=script or DEFAULT_MESSAGE)

        await ctx.success("Updated the join DM message." if script else "Reset the join DM message to the default.")

    # ---------------------------------------------------------- reset / toggle / test

    @command_meta(
        category="Server",
        description="Clear the join DM configuration.",
        syntax=",joindm reset",
        examples=[",joindm reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @joindm.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def joindm_reset(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await joindm_repository.get_or_create_config(session, ctx.guild.id)
            await joindm_repository.update_config(session, cfg, enabled=False, message_template=DEFAULT_MESSAGE)

        await ctx.success("Cleared the join DM configuration.")

    @command_meta(
        category="Server",
        description="Turn the join DM on or off.",
        syntax=",joindm toggle",
        examples=[",joindm toggle"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @joindm.command(name="toggle")
    @has_permission_or_fake("manage_guild")
    async def joindm_toggle(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await joindm_repository.get_or_create_config(session, ctx.guild.id)
            new_state = not cfg.enabled
            await joindm_repository.update_config(session, cfg, enabled=new_state)

        await ctx.success(f"Join DM is now **{'enabled' if new_state else 'disabled'}**.")

    @command_meta(
        category="Server",
        description="DM yourself the join message.",
        syntax=",joindm test",
        examples=[",joindm test"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @joindm.command(name="test")
    @has_permission_or_fake("manage_guild")
    async def joindm_test(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await joindm_repository.get_or_create_config(session, ctx.guild.id)

        resolved = resolve_variables(cfg.message_template, guild=ctx.guild, member=ctx.author)
        parsed = parse_script(resolved)

        try:
            if parsed.embed is not None:
                await ctx.author.send(content=parsed.content, embed=parsed.embed)
            else:
                await ctx.author.send(resolved)
        except discord.HTTPException:
            await ctx.error("I couldn't DM you - check your privacy settings.")
            return

        await ctx.success("Sent you a test join DM.")


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinDm(bot))