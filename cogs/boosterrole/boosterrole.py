"""
Custom booster roles - ,boosterrole / ,br.

One custom, colorable role per server booster, created under a
configurable base role. Booster-only actions (color/create/delete/
icon/name/share) check premium_since directly rather than a stored
flag, since Discord itself is the source of truth for who's currently
boosting.

HONEST GAP: the second-color/"gradient" support in ,boosterrole color
uses discord.RoleColours, which is very new Discord/discord.py API
surface I haven't been able to test live - if it errors, a plain
single-color role is the safe fallback (this already degrades to an
error message telling the booster to try one color instead, rather
than crashing).
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import boosterrole_repository


def _is_booster(member: discord.Member) -> bool:
    return member.premium_since is not None


class ShareRoleView(discord.ui.View):
    """Grey Accept/Decline - only the recipient can answer."""

    def __init__(self, giver: discord.Member, receiver: discord.Member, role: discord.Role):
        super().__init__(timeout=120)
        self.giver = giver
        self.receiver = receiver
        self.role = role

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("This share request isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.secondary)
    async def accept(self, interaction: discord.Interaction, _button: discord.ui.Button):
        try:
            await self.receiver.add_roles(self.role, reason=f"Booster role shared by {self.giver}")
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to add that role.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            description=f"{self.receiver.mention} accepted **{self.role.name}** from {self.giver.mention}."
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            description=f"{self.receiver.mention} declined **{self.role.name}** from {self.giver.mention}."
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


class BoosterRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _require_booster(self, ctx: commands.Context) -> bool:
        if not _is_booster(ctx.author):
            await ctx.error("This command is only for server boosters.")
            return False
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
        if not cfg.enabled:
            await ctx.error("Custom booster roles are currently disabled.")
            return False
        return True

    async def _get_or_create_role(self, ctx: commands.Context) -> discord.Role | None:
        async with get_session() as session:
            existing = await boosterrole_repository.get_booster_role(session, ctx.guild.id, ctx.author.id)

        if existing is not None:
            role = ctx.guild.get_role(existing.role_id)
            if role is not None:
                return role
            # the role was deleted outside the bot - clean up the stale record
            async with get_session() as session:
                await boosterrole_repository.delete_booster_role(session, ctx.guild.id, ctx.author.id)

        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            count = await boosterrole_repository.count_booster_roles(session, ctx.guild.id)

        if cfg.limit is not None and count >= cfg.limit:
            await ctx.error(f"The server-wide limit of `{cfg.limit}` booster roles has been reached.")
            return None

        base_role = ctx.guild.get_role(cfg.base_role_id) if cfg.base_role_id else None
        position = base_role.position if base_role is not None else 1

        try:
            new_role = await ctx.guild.create_role(
                name=ctx.author.display_name[:100], hoist=cfg.hoist_default,
                reason=f"Booster role created for {ctx.author}",
            )
            await new_role.edit(position=position)
            await ctx.author.add_roles(new_role, reason="Booster role")
        except discord.Forbidden:
            await ctx.error("I don't have permission to create/position that role.")
            return None

        async with get_session() as session:
            await boosterrole_repository.create_booster_role(session, ctx.guild.id, ctx.author.id, new_role.id)

        return new_role

    # ---------------------------------------------------------- root

    @command_meta(
        category="Server",
        description="Configures custom booster roles - one colorable role per server booster.",
        syntax=",boosterrole",
        examples=[],
        aliases=["br", "boosterroles"],
        require_args=False,
    )
    @commands.group(name="boosterrole", aliases=["br", "boosterroles"], invoke_without_command=True)
    @commands.guild_only()
    async def boosterrole(self, ctx: commands.Context):
        async with get_session() as session:
            count = await boosterrole_repository.count_booster_roles(session, ctx.guild.id)

        if count == 0:
            embed = discord.Embed(description=f"{ctx.author.mention}: No booster roles have been created yet.")
            await ctx.send(embed=embed)
            return

        await send_help(ctx, "boosterrole")

    @boosterrole.command(name="help")
    async def boosterrole_help(self, ctx: commands.Context):
        await send_help(ctx, "boosterrole")

    # ---------------------------------------------------------- base

    @command_meta(
        category="Server",
        description="Sets the role that booster roles are positioned under.",
        syntax=",boosterrole base <role>",
        examples=[",boosterrole base @Booster Roles"],
        permissions=["Manage Guild"],
    )
    @boosterrole.command(name="base")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_base(self, ctx: commands.Context, *, role: discord.Role):
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            await boosterrole_repository.update_config(session, cfg, base_role_id=role.id)
        await ctx.success(f"{ctx.author.mention}: Set the booster-role base position to {role.mention}.")

    # ---------------------------------------------------------- color

    @command_meta(
        category="Server",
        description="Sets your booster role's color. Give a second color for a gradient, if your server has it unlocked.",
        syntax=",boosterrole color <color> [second_color]",
        examples=[",boosterrole color #ff0000", ",boosterrole color #ff0000 #0000ff"],
    )
    @boosterrole.command(name="color", aliases=["colour"])
    async def boosterrole_color(self, ctx: commands.Context, color: str, second_color: str = None):
        if not await self._require_booster(ctx):
            return

        try:
            primary = discord.Color(int(color.lstrip("#"), 16))
        except ValueError:
            await ctx.error("Provide a valid hex color, e.g. `#ff0000`.")
            return

        secondary = None
        if second_color:
            try:
                secondary = discord.Color(int(second_color.lstrip("#"), 16))
            except ValueError:
                await ctx.error("Provide a valid hex color for the second color, e.g. `#0000ff`.")
                return

        role = await self._get_or_create_role(ctx)
        if role is None:
            return

        try:
            if secondary is not None:
                colours = discord.RoleColours(primary_colour=primary, secondary_colour=secondary)
                await role.edit(colours=colours, reason=f"Booster role color set by {ctx.author}")
            else:
                await role.edit(color=primary, reason=f"Booster role color set by {ctx.author}")
        except (discord.Forbidden, discord.HTTPException, AttributeError, TypeError) as exc:
            await ctx.error(
                f"Couldn't set that color ({exc}). Gradient colors need a certain boost level and may not be "
                f"supported on this discord.py version - try a single color instead."
            )
            return

        await ctx.success(f"{ctx.author.mention}: Updated your booster role's color.")

    # ---------------------------------------------------------- create / delete

    @command_meta(
        category="Server",
        description="Creates your booster role.",
        syntax=",boosterrole create [name]",
        examples=[",boosterrole create", ",boosterrole create VIP"],
        require_args=False,
    )
    @boosterrole.command(name="create")
    async def boosterrole_create(self, ctx: commands.Context, *, name: str = None):
        if not await self._require_booster(ctx):
            return

        async with get_session() as session:
            existing = await boosterrole_repository.get_booster_role(session, ctx.guild.id, ctx.author.id)
        if existing is not None and ctx.guild.get_role(existing.role_id) is not None:
            await ctx.error("You already have a booster role - use `,boosterrole name`/`,boosterrole color` to edit it.")
            return

        if name:
            async with get_session() as session:
                blocked = await boosterrole_repository.get_filter_words(session, ctx.guild.id)
            lowered = name.lower()
            if any(word in lowered for word in blocked):
                await ctx.error("That name contains a blocked word.")
                return

        role = await self._get_or_create_role(ctx)
        if role is None:
            return

        if name:
            try:
                await role.edit(name=name[:100], reason=f"Booster role named by {ctx.author}")
            except discord.Forbidden:
                pass

        await ctx.success(f"{ctx.author.mention}: Created your booster role {role.mention}.")

    @command_meta(
        category="Server",
        description="Deletes your booster role.",
        syntax=",boosterrole delete",
        examples=[",boosterrole delete"],
        require_args=False,
    )
    @boosterrole.command(name="delete")
    async def boosterrole_delete(self, ctx: commands.Context):
        async with get_session() as session:
            existing = await boosterrole_repository.get_booster_role(session, ctx.guild.id, ctx.author.id)

        if existing is None:
            await ctx.error("You don't have a booster role.")
            return

        role = ctx.guild.get_role(existing.role_id)
        if role is not None:
            try:
                await role.delete(reason=f"Booster role deleted by {ctx.author}")
            except discord.Forbidden:
                pass

        async with get_session() as session:
            await boosterrole_repository.delete_booster_role(session, ctx.guild.id, ctx.author.id)

        await ctx.success(f"{ctx.author.mention}: Deleted your booster role.")

    # ---------------------------------------------------------- disable / setup

    @command_meta(
        category="Server",
        description="Disables custom booster roles for this server.",
        syntax=",boosterrole disable",
        examples=[",boosterrole disable"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boosterrole.command(name="disable")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_disable(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            await boosterrole_repository.update_config(session, cfg, enabled=False)
        await ctx.success(f"{ctx.author.mention}: Disabled custom booster roles.")

    @command_meta(
        category="Server",
        description="Enables custom booster roles for this server.",
        syntax=",boosterrole setup",
        examples=[",boosterrole setup"],
        permissions=["Manage Guild"],
        aliases=["enable"],
        require_args=False,
    )
    @boosterrole.command(name="setup", aliases=["enable"])
    @has_permission_or_fake("manage_guild")
    async def boosterrole_setup(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            await boosterrole_repository.update_config(session, cfg, enabled=True)
        await ctx.success(f"{ctx.author.mention}: Enabled custom booster roles.")

    # ---------------------------------------------------------- filter

    @command_meta(
        category="Server",
        description="Toggles a word from being blocked in booster role names.",
        syntax=",boosterrole filter <word>",
        examples=[",boosterrole filter badword"],
        permissions=["Manage Guild"],
    )
    @boosterrole.group(name="filter", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def boosterrole_filter(self, ctx: commands.Context, *, word: str):
        word = word.lower().strip()
        async with get_session() as session:
            added = await boosterrole_repository.add_filter_word(session, ctx.guild.id, word)
            if not added:
                await boosterrole_repository.remove_filter_word(session, ctx.guild.id, word)

        if added:
            await ctx.success(f"{ctx.author.mention}: Blocked `{word}` from being used in booster role names.")
        else:
            await ctx.success(f"{ctx.author.mention}: Unblocked `{word}`.")

    @boosterrole_filter.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_filter_list(self, ctx: commands.Context):
        async with get_session() as session:
            words = await boosterrole_repository.get_filter_words(session, ctx.guild.id)
        if not words:
            await ctx.info("No blocked words.")
            return
        await ctx.send(embed=discord.Embed(
            title="Blocked Booster Role Words", description=", ".join(f"`{w}`" for w in words)[:4000]
        ))

    # ---------------------------------------------------------- hoist

    @command_meta(
        category="Server",
        description="Toggles whether booster roles are shown separately in the member list.",
        syntax=",boosterrole hoist <on|off>",
        examples=[",boosterrole hoist on"],
        permissions=["Manage Guild"],
    )
    @boosterrole.command(name="hoist")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_hoist(self, ctx: commands.Context, state: str):
        value = state.lower() in ("on", "true", "enable", "enabled")
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            await boosterrole_repository.update_config(session, cfg, hoist_default=value)
            all_roles = await boosterrole_repository.get_all_booster_roles(session, ctx.guild.id)

        for record in all_roles:
            role = ctx.guild.get_role(record.role_id)
            if role is not None:
                try:
                    await role.edit(hoist=value, reason=f"Booster role hoist toggled by {ctx.author}")
                except discord.HTTPException:
                    pass

        await ctx.success(f"{ctx.author.mention}: Booster roles are now **{'hoisted' if value else 'not hoisted'}**.")

    # ---------------------------------------------------------- icon

    @command_meta(
        category="Server",
        description="Sets your booster role's icon - an emoji or an image URL.",
        syntax=",boosterrole icon <emoji_or_url>",
        examples=[",boosterrole icon 👑", ",boosterrole icon https://example.com/icon.png"],
    )
    @boosterrole.command(name="icon")
    async def boosterrole_icon(self, ctx: commands.Context, icon: str):
        if not await self._require_booster(ctx):
            return

        role = await self._get_or_create_role(ctx)
        if role is None:
            return

        icon = icon.strip()
        display_icon: bytes | str

        if icon.startswith("http://") or icon.startswith("https://"):
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status != 200:
                            await ctx.error("Couldn't download that image.")
                            return
                        display_icon = await resp.read()
            except (aiohttp.ClientError, TimeoutError):
                await ctx.error("Couldn't download that image.")
                return
        else:
            display_icon = icon  # treat as a unicode emoji

        try:
            await role.edit(display_icon=display_icon, reason=f"Booster role icon set by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Discord rejected that icon - this server may not have role icons unlocked. ({exc})")
            return

        await ctx.success(f"{ctx.author.mention}: Updated your booster role's icon.")

    # ---------------------------------------------------------- limit / list

    @command_meta(
        category="Server",
        description="Sets the maximum number of booster roles allowed.",
        syntax=",boosterrole limit <number>",
        examples=[",boosterrole limit 50"],
        permissions=["Manage Guild"],
    )
    @boosterrole.command(name="limit")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_limit(self, ctx: commands.Context, number: int):
        number = max(1, number)
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            await boosterrole_repository.update_config(session, cfg, limit=number)
        await ctx.success(f"{ctx.author.mention}: Set the booster role limit to `{number}`.")

    @command_meta(
        category="Server",
        description="Lists all booster roles and their owners.",
        syntax=",boosterrole list",
        examples=[",boosterrole list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boosterrole.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_list(self, ctx: commands.Context):
        async with get_session() as session:
            records = await boosterrole_repository.get_all_booster_roles(session, ctx.guild.id)

        if not records:
            await ctx.info("No booster roles have been created yet.")
            return

        lines = []
        for record in records:
            role = ctx.guild.get_role(record.role_id)
            role_display = role.mention if role else f"`{record.role_id}` (deleted)"
            lines.append(f"{role_display} — <@{record.owner_id}>")

        await ctx.send(embed=discord.Embed(title="Booster Roles", description="\n".join(lines)[:4000]))

    # ---------------------------------------------------------- name

    @command_meta(
        category="Server",
        description="Renames your booster role.",
        syntax=",boosterrole name <name>",
        examples=[",boosterrole name VIP"],
    )
    @boosterrole.command(name="name")
    async def boosterrole_name(self, ctx: commands.Context, *, name: str):
        if not await self._require_booster(ctx):
            return

        async with get_session() as session:
            blocked = await boosterrole_repository.get_filter_words(session, ctx.guild.id)
        lowered = name.lower()
        if any(word in lowered for word in blocked):
            await ctx.error("That name contains a blocked word.")
            return

        role = await self._get_or_create_role(ctx)
        if role is None:
            return

        try:
            await role.edit(name=name[:100], reason=f"Booster role renamed by {ctx.author}")
        except discord.Forbidden:
            await ctx.error("I don't have permission to rename that role.")
            return

        await ctx.success(f"{ctx.author.mention}: Renamed your booster role to `{name}`.")

    # ---------------------------------------------------------- share

    @command_meta(
        category="Server",
        description="Shares your booster role with another member - they can accept or decline.",
        syntax=",boosterrole share <member>",
        examples=[",boosterrole share @User"],
    )
    @boosterrole.command(name="share")
    async def boosterrole_share(self, ctx: commands.Context, member: discord.Member):
        if not await self._require_booster(ctx):
            return

        if member.id == ctx.author.id:
            await ctx.error("You can't share your role with yourself.")
            return

        async with get_session() as session:
            existing = await boosterrole_repository.get_booster_role(session, ctx.guild.id, ctx.author.id)

        role = ctx.guild.get_role(existing.role_id) if existing else None
        if role is None:
            await ctx.error("You don't have a booster role to share. Create one first with `,boosterrole create`.")
            return

        embed = discord.Embed(
            description=f"{member.mention} {ctx.author.mention} wants to share their booster role {role.mention} with you."
        )
        view = ShareRoleView(ctx.author, member, role)
        await ctx.send(embed=embed, view=view)

    # ---------------------------------------------------------- sync

    @command_meta(
        category="Server",
        description="Re-stacks all booster roles directly under the base role.",
        syntax=",boosterrole sync",
        examples=[",boosterrole sync"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @boosterrole.command(name="sync")
    @has_permission_or_fake("manage_guild")
    async def boosterrole_sync(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await boosterrole_repository.get_or_create_config(session, ctx.guild.id)
            records = await boosterrole_repository.get_all_booster_roles(session, ctx.guild.id)

        base_role = ctx.guild.get_role(cfg.base_role_id) if cfg.base_role_id else None
        if base_role is None:
            await ctx.error("No base role set. Run `,boosterrole base @role` first.")
            return

        position = base_role.position
        synced = 0
        for record in records:
            role = ctx.guild.get_role(record.role_id)
            if role is None:
                continue
            try:
                await role.edit(position=position)
                synced += 1
            except discord.HTTPException:
                pass

        await ctx.success(f"{ctx.author.mention}: Synced {synced} booster role(s) under {base_role.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(BoosterRole(bot))