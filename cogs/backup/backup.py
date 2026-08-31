"""Server backups - ,backup. Category "Server". Administrator only,
premium (server plan)."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import requires_premium
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import backup_repository
from services import backup_service


class ConfirmDestructiveView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Yes, wipe and restore", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="Restoring...", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", view=None)


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Snapshot and restore this server's roles, channels, and settings.",
        syntax=",backup",
        examples=[],
        permissions=["Administrator"],
        require_args=False,
    )
    @commands.group(name="backup", invoke_without_command=True, with_app_command=False)
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    @commands.guild_only()
    async def backup(self, ctx: commands.Context):
        await send_help(ctx, "backup")

    @backup.command(name="help")
    async def backup_help(self, ctx: commands.Context):
        await send_help(ctx, "backup")

    # ---------------------------------------------------------- create

    @command_meta(
        category="Server",
        description="Create a backup of this server.",
        syntax=",backup create <name> [description]",
        examples=[",backup create pre-rebrand", ",backup create pre-rebrand before the redesign"],
        permissions=["Administrator"],
    )
    @backup.command(name="create")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    async def backup_create(self, ctx: commands.Context, name: str, *, description: str = None):
        async with ctx.typing():
            snapshot = backup_service.snapshot_guild(ctx.guild)
            data = backup_service.dumps(snapshot)

            async with get_session() as session:
                row = await backup_repository.create_backup(
                    session, ctx.guild.id, name, description, data, ctx.author.id,
                )

        await ctx.success(f"Created backup `#{row.id}` (**{name}**) - {backup_service.summarize(snapshot)}")

    # ---------------------------------------------------------- list / view / rename / delete

    @command_meta(
        category="Server",
        description="List your backups.",
        syntax=",backup list",
        examples=[",backup list"],
        permissions=["Administrator"],
        require_args=False,
    )
    @backup.command(name="list")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    async def backup_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await backup_repository.get_backups_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No backups yet. Use `,backup create` to make one.")
            return

        lines = [
            f"`#{row.id}` **{row.name}** - {discord.utils.format_dt(row.created_at, style='R')}"
            for row in rows
        ]
        embed = discord.Embed(title="Server Backups", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="View a backup's details.",
        syntax=",backup view <id>",
        examples=[",backup view 3"],
        permissions=["Administrator"],
    )
    @backup.command(name="view")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    async def backup_view(self, ctx: commands.Context, backup_id: int):
        async with get_session() as session:
            row = await backup_repository.get_backup(session, backup_id)

        if row is None or row.guild_id != ctx.guild.id:
            await ctx.error(f"No backup `#{backup_id}` found in this server.")
            return

        snapshot = backup_service.loads(row.data)
        description = (
            f"{backup_service.summarize(snapshot)}\n\n"
            f"**Created** {discord.utils.format_dt(row.created_at, style='F')}\n"
            f"**Created By** <@{row.created_by}>\n"
        )
        if row.description:
            description += f"\n{row.description}"

        embed = discord.Embed(title=f"Backup #{row.id} - {row.name}", description=description)
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Rename a backup.",
        syntax=",backup rename <id> <name> [description]",
        examples=[",backup rename 3 pre-rebrand", ",backup rename 3 pre-rebrand before the redesign"],
        permissions=["Administrator"],
    )
    @backup.command(name="rename")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    async def backup_rename(self, ctx: commands.Context, backup_id: int, name: str, *, description: str = None):
        async with get_session() as session:
            row = await backup_repository.get_backup(session, backup_id)
            if row is None or row.guild_id != ctx.guild.id:
                await ctx.error(f"No backup `#{backup_id}` found in this server.")
                return
            await backup_repository.update_backup(session, row, name=name, description=description)

        await ctx.success(f"Renamed backup `#{backup_id}` to **{name}**.")

    @command_meta(
        category="Server",
        description="Delete a backup.",
        syntax=",backup delete <id>",
        examples=[",backup delete 3"],
        permissions=["Administrator"],
    )
    @backup.command(name="delete")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    async def backup_delete(self, ctx: commands.Context, backup_id: int):
        async with get_session() as session:
            removed = await backup_repository.delete_backup(session, backup_id, ctx.guild.id)

        if removed:
            await ctx.success(f"Deleted backup `#{backup_id}`.")
        else:
            await ctx.error(f"No backup `#{backup_id}` found in this server.")

    # ---------------------------------------------------------- restore

    @command_meta(
        category="Server",
        description="Restore a backup (merge or destructive).",
        syntax=",backup restore <id> [mode]",
        examples=[",backup restore 3", ",backup restore 3 destructive"],
        permissions=["Administrator"],
    )
    @backup.command(name="restore")
    @commands.has_permissions(administrator=True)
    @requires_premium("server")
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def backup_restore(self, ctx: commands.Context, backup_id: int, mode: str = "merge"):
        mode = mode.lower()
        if mode not in ("merge", "destructive"):
            await ctx.error("Mode must be `merge` or `destructive`.")
            return

        async with get_session() as session:
            row = await backup_repository.get_backup(session, backup_id)
        if row is None or row.guild_id != ctx.guild.id:
            await ctx.error(f"No backup `#{backup_id}` found in this server.")
            return

        snapshot = backup_service.loads(row.data)

        if mode == "destructive":
            view = ConfirmDestructiveView(ctx.author.id)
            warning = await ctx.send(
                content=(
                    f"⚠️ **Destructive restore** will delete every current channel and role in this server "
                    f"before rebuilding from backup `#{backup_id}` (**{row.name}**). This cannot be undone "
                    f"(unless you have another backup). Are you sure?"
                ),
                view=view,
            )
            await view.wait()
            if not view.confirmed:
                return

        async with ctx.typing():
            result = await backup_service.restore_guild(ctx.guild, snapshot, mode)

        summary = (
            f"**Roles created** {result['roles_created']}\n"
            f"**Categories created** {result['categories_created']}\n"
            f"**Channels created** {result['channels_created']}"
        )
        if result["errors"]:
            summary += f"\n**Errors** {result['errors']} (check my role position and permissions)"

        await ctx.send(embed=discord.Embed(title=f"Restored backup #{backup_id}", description=summary))


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))