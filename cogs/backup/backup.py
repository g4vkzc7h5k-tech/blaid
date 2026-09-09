"""Server backups - ,backup. Category "Server". Administrator only,
premium (server plan).

,recover lives in this same file/category - it's a separate,
standalone command (not a ,backup subcommand) that reuses
backup_service.restore_guild in destructive mode, but with its own
pick-what-to-restore UI. Server owner only (stricter than ,backup
itself, since this is the "something already went badly wrong"
command - deliberately not delegable to regular admins)."""

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


# ---------------------------------------------------------- ,recover

class RecoverSelectView(discord.ui.LayoutView):
    """Step 1 - Components V2 card: toggle which parts of the backup to
    restore (roles/categories/channels), then Continue. Only the
    server owner who ran ,recover can use these buttons."""

    def __init__(self, cog: "Backup", owner_id: int, backup_id: int, snapshot: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.owner_id = owner_id
        self.backup_id = backup_id
        self.snapshot = snapshot
        self.selected: set[str] = {"roles", "categories", "channels"}

        self.roles_button = discord.ui.Button(label="Roles ✅", style=discord.ButtonStyle.secondary)
        self.categories_button = discord.ui.Button(label="Categories ✅", style=discord.ButtonStyle.secondary)
        self.channels_button = discord.ui.Button(label="Channels ✅", style=discord.ButtonStyle.secondary)
        self.continue_button = discord.ui.Button(label="Continue", style=discord.ButtonStyle.success)

        self.roles_button.callback = self._make_toggle("roles", self.roles_button)
        self.categories_button.callback = self._make_toggle("categories", self.categories_button)
        self.channels_button.callback = self._make_toggle("channels", self.channels_button)
        self.continue_button.callback = self._on_continue

        self._build()

    def _build(self) -> None:
        self.clear_items()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# Recover from backup #{self.backup_id}"),
            discord.ui.TextDisplay(
                f"{backup_service.summarize(self.snapshot)}\n\n"
                f"Choose what to restore, then continue. Anything currently in the "
                f"server with a matching name is left alone - only what's missing gets rebuilt."
            ),
            discord.ui.Separator(visible=True),
            discord.ui.ActionRow(self.roles_button, self.categories_button, self.channels_button),
            discord.ui.ActionRow(self.continue_button),
        )
        self.add_item(container)

    def _make_toggle(self, key: str, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Only the server owner can use this.", ephemeral=True)
                return
            if key in self.selected:
                self.selected.discard(key)
                button.label = f"{key.capitalize()} ❌"
            else:
                self.selected.add(key)
                button.label = f"{key.capitalize()} ✅"
            self._build()
            await interaction.response.edit_message(view=self)
        return callback

    async def _on_continue(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the server owner can use this.", ephemeral=True)
            return
        if not self.selected:
            await interaction.response.send_message("Select at least one thing to restore.", ephemeral=True)
            return

        included = ", ".join(sorted(self.selected))
        embed = discord.Embed(
            title="⚠️ This will wipe the server first",
            description=(
                f"Every current role and channel not managed by Discord itself will be **deleted**, "
                f"then rebuilt from backup #{self.backup_id} - restoring: **{included}**.\n\n"
                f"This cannot be undone (unless you have another backup)."
            ),
            color=discord.Color.red(),
        )
        confirm_view = ConfirmDestructiveView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=confirm_view)

        await confirm_view.wait()
        if not confirm_view.confirmed:
            return

        result = await backup_service.restore_guild(
            interaction.guild, self.snapshot, mode="destructive", include=self.selected,
        )
        summary = (
            f"**Roles created** {result['roles_created']}\n"
            f"**Categories created** {result['categories_created']}\n"
            f"**Channels created** {result['channels_created']}"
        )
        if result["errors"]:
            summary += f"\n**Errors** {result['errors']} (check my role position and permissions)"

        try:
            await interaction.followup.send(
                embed=discord.Embed(title=f"Recovered from backup #{self.backup_id}", description=summary)
            )
        except discord.HTTPException:
            pass


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
            await ctx.send(
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

    # ---------------------------------------------------------- recover (standalone, owner-only)

    @command_meta(
        category="Server",
        description="Wipe and rebuild the server from a backup - for when something's already gone badly wrong. Server owner only.",
        syntax=",recover <id>",
        examples=[",recover 3"],
        permissions=["Server Owner"],
        require_args=False,
    )
    @commands.command(name="recover", with_app_command=False)
    @requires_premium("server")
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def recover(self, ctx: commands.Context, backup_id: int = None):
        if backup_id is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: You need to provide `id`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        if ctx.author.id != ctx.guild.owner_id:
            await ctx.error("Only the server owner can use `,recover`.")
            return

        async with get_session() as session:
            row = await backup_repository.get_backup(session, backup_id)
        if row is None or row.guild_id != ctx.guild.id:
            await ctx.error(f"No backup `#{backup_id}` found in this server - check `,backup list` for valid IDs.")
            return

        snapshot = backup_service.loads(row.data)
        view = RecoverSelectView(self, ctx.author.id, backup_id, snapshot)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
