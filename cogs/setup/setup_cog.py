"""The ,setup / ,setup reset commands, plus ,prefix. Both are
server-wide configuration entry points, so they live together."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from sqlalchemy import select

from config import config
from core import embeds
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from database.models import Guild as GuildModel
from repositories import guild_config_repository, prefix_repository
from services.prefix_service import send_prefix_info
from services.setup_service import SetupHierarchyError, reset_setup, run_setup


async def _get_or_create_guild(session, guild_id: int) -> GuildModel:
    result = await session.execute(select(GuildModel).where(GuildModel.guild_id == guild_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = GuildModel(guild_id=guild_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


class ResetConfirmView(discord.ui.View):
    """Green Confirm / red Cancel. Only the command author can answer."""

    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.confirmed: bool | None = None
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This isn't your confirmation to answer.", ephemeral=True
            )
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


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Keep the jail isolation intact for channels created after
        ,setup already ran - otherwise the jailed role would see any
        brand-new channel by default."""
        async with get_session() as session:
            cfg = await guild_config_repository.get(session, channel.guild.id)

        if cfg is None or not cfg.jail_role_id or channel.id == cfg.jail_channel_id:
            return

        role = channel.guild.get_role(cfg.jail_role_id)
        if role is None:
            return

        try:
            await channel.set_permissions(role, view_channel=False, reason="Blaid: jail isolation")
        except discord.Forbidden:
            pass

    # ---------------------------------------------------------- ,setup

    @command_meta(
        category="Server",
        description="Sets up Blaid's moderation system: a blaid-mod category, a jail role/channel, and a logs channel.",
        syntax=",setup",
        examples=[",setup"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @commands.hybrid_group(name="setup", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    @commands.guild_only()
    async def setup_group(self, ctx: commands.Context):
        embed = discord.Embed(description=f"{ctx.author.mention}: Working on **moderation setup**.")
        message = await ctx.send(embed=embed)

        try:
            await run_setup(ctx.guild, ctx.author)
        except SetupHierarchyError:
            warn_embed = discord.Embed(
                description=(
                    f"{ctx.author.mention}: **blaid** must be higher than the **jailed**, **imute**, and **rmute** roles. "
                    f"In Server Settings > Roles, drag **blaid** above these roles, then run `setup` again."
                ),
                color=discord.Color.orange(),
            )
            await message.edit(embed=warn_embed)
            return

        final_embed = embeds.help_embed(
            description=(
                f"{ctx.author.mention} **Moderation system set up** has been completed. "
                f"Please make sure that all your channels and roles have been configured properly."
            )
        )
        await message.edit(embed=final_embed)

    # ---------------------------------------------------------- ,setup reset

    @command_meta(
        category="Server",
        description="Deletes Blaid's moderation setup: unjails everyone, removes the jail role, and deletes the jail and logs channels.",
        syntax=",setup reset",
        examples=[",setup reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @setup_group.command(name="reset")
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def setup_reset(self, ctx: commands.Context):
        confirm_embed = embeds.help_embed(
            description=(
                f"{ctx.author.mention} Are you sure you want to reset moderation setup? "
                f"This will unjail everyone, remove jail roles, and delete the jail and logs channel."
            )
        )
        view = ResetConfirmView(ctx.author.id)
        message = await ctx.send(embed=confirm_embed, view=view)
        view.message = message

        await view.wait()

        if view.confirmed is None:
            return  # timed out - on_timeout already disabled the buttons

        if not view.confirmed:
            cancelled_embed = embeds.help_embed(description=f"{ctx.author.mention} Reset cancelled.")
            await message.edit(embed=cancelled_embed, view=None)
            return

        working_embed = embeds.help_embed(description="Working **moderation reset**")
        await message.edit(embed=working_embed, view=None)

        await reset_setup(ctx.guild)

        done_embed = embeds.help_embed(description=f"{ctx.author.mention} **Moderation setup** has been reset.")
        await message.edit(embed=done_embed)

    # ---------------------------------------------------------- ,prefix

    @command_meta(
        category="Server",
        description="Shows this server's command prefix.",
        syntax=",prefix",
        examples=[",prefix"],
        require_args=False,
    )
    @commands.hybrid_group(name="prefix", invoke_without_command=True)
    @commands.guild_only()
    async def prefix(self, ctx: commands.Context):
        await send_prefix_info(ctx)

    @prefix.command(name="help")
    async def prefix_help(self, ctx: commands.Context):
        await send_help(ctx, "prefix")

    @command_meta(
        category="Server",
        description="Sets this server's command prefix.",
        syntax=",prefix set <new_prefix>",
        examples=[",prefix set !"],
        permissions=["Manage Guild"],
    )
    @prefix.command(name="set")
    @has_permission_or_fake("manage_guild")
    async def prefix_set(self, ctx: commands.Context, new_prefix: str):
        new_prefix = new_prefix.strip()[:8]
        if not new_prefix:
            await ctx.error("Prefix cannot be empty.")
            return

        async with get_session() as session:
            row = await _get_or_create_guild(session, ctx.guild.id)
            row.prefix = new_prefix
            await session.commit()

        self.bot.guild_prefixes[ctx.guild.id] = new_prefix
        await ctx.success(f"Prefix set to `{new_prefix}`.")

    @command_meta(
        category="Server",
        description="Removes this server's custom prefix, reverting to the default.",
        syntax=",prefix remove",
        examples=[",prefix remove"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @prefix.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def prefix_remove(self, ctx: commands.Context):
        async with get_session() as session:
            row = await _get_or_create_guild(session, ctx.guild.id)
            row.prefix = config.default_prefix
            await session.commit()

        self.bot.guild_prefixes.pop(ctx.guild.id, None)
        await ctx.success(f"Prefix reset to the default `{config.default_prefix}`.")

    @command_meta(
        category="Server",
        description="Sets your own personal prefix - works in every server Blaid is in, for you specifically.",
        syntax=",prefix self set <new_prefix>",
        examples=[",prefix self set !!"],
        require_args=False,
    )
    @prefix.group(name="self", invoke_without_command=True)
    async def prefix_self(self, ctx: commands.Context):
        await send_help(ctx, "prefix self")

    @command_meta(
        category="Server",
        description="Sets your personal prefix, usable by anyone regardless of server permissions.",
        syntax=",prefix self set <new_prefix>",
        examples=[",prefix self set !!"],
    )
    @prefix_self.command(name="set")
    async def prefix_self_set(self, ctx: commands.Context, new_prefix: str):
        new_prefix = new_prefix.strip()[:8]
        if not new_prefix:
            await ctx.error("Prefix cannot be empty.")
            return

        async with get_session() as session:
            await prefix_repository.set_user_prefix(session, ctx.author.id, new_prefix)

        self.bot.user_prefixes[ctx.author.id] = new_prefix
        await ctx.success(f"Your personal prefix is now `{new_prefix}` in every server with Blaid.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
