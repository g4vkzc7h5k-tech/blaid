"""Reaction roles, button roles, and role management. Autorole now
lives in cogs/automod/automod.py under the Automod category."""

from __future__ import annotations

import asyncio

import aiohttp
import discord
from discord.ext import commands

from core.checks import has_permission_or_fake

from core.command_meta import command_meta
from core.help_formatter import send_help
from core.paginator import Paginator
from database.database import get_session
from repositories import roles_repository
from services import roles_service, premium_service
from services.roles_service import ButtonRolePanelView


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> running mass role asyncio.Task, so ,role cancel
        # can find and cancel it.
        self._mass_operations: dict[int, asyncio.Task] = {}

    async def cog_load(self) -> None:
        # Re-register persistent button-role panel views after a restart.
        async with get_session() as session:
            message_ids = await roles_repository.get_all_button_role_messages(session)
            for message_id in message_ids:
                buttons = await roles_repository.get_button_roles_for_message(session, message_id)
                view = ButtonRolePanelView(
                    message_id, [(b.custom_id, b.label, b.role_id, b.style, b.emoji) for b in buttons]
                )
                self.bot.add_view(view)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        emoji = str(payload.emoji)
        async with get_session() as session:
            rr = await roles_repository.get_reaction_role(session, payload.message_id, emoji)
        if rr is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(rr.role_id)
        if role is not None:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        emoji = str(payload.emoji)
        async with get_session() as session:
            rr = await roles_repository.get_reaction_role(session, payload.message_id, emoji)
        if rr is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(rr.role_id)
        if member is not None and role is not None:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Powers ,role restore - snapshot their roles (minus @everyone)
        # at the moment they leave.
        role_ids = [r.id for r in member.roles if r.name != "@everyone"]
        async with get_session() as session:
            await roles_repository.save_sticky_roles(session, member.guild.id, member.id, role_ids)

    # ---------------------------------------------------------- ,role

    @command_meta(
        category="Moderation",
        description="Gives or removes a role from a member - if they already have it, it's removed; otherwise it's added. Separate multiple roles with commas.",
        syntax=",role <member> <role>",
        examples=[",role @User @Member", ",role @User @Member, @VIP"],
        permissions=["Manage Roles"],
        aliases=["r"],
    )
    @commands.group(name="role", aliases=["r"], invoke_without_command=True)
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role(self, ctx: commands.Context, member: discord.Member, *, roles_input: str):
        role_names = [r.strip() for r in roles_input.split(",") if r.strip()]
        if not role_names:
            await ctx.error("Provide at least one role.")
            return

        converter = commands.RoleConverter()
        lines = []

        for name in role_names:
            try:
                role = await converter.convert(ctx, name)
            except commands.BadArgument:
                lines.append(f"{ctx.author.mention} Could not find role `{name}`.")
                continue

            if role >= ctx.guild.me.top_role:
                lines.append(f"{ctx.author.mention} I can't manage **{role.name}** - it's above my highest role.")
                continue

            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Role toggled by {ctx.author}")
                except discord.Forbidden:
                    lines.append(f"{ctx.author.mention} Missing permissions to remove **{role.name}**.")
                    continue
                lines.append(f"<:emoji_13:1541280729890164817> {ctx.author.mention} Removed {role.mention} from {member.mention}")
            else:
                try:
                    await member.add_roles(role, reason=f"Role toggled by {ctx.author}")
                except discord.Forbidden:
                    lines.append(f"{ctx.author.mention} Missing permissions to add **{role.name}**.")
                    continue
                lines.append(f"<:emoji_12:1541280716132716607> {ctx.author.mention} Added {role.mention} to {member.mention}")

        description = "\n".join(lines)
        await ctx.send(embed=discord.Embed(description=description, color=discord.Color(0xFFFFFF)))

    @role.command(name="help")
    async def role_help(self, ctx: commands.Context):
        await send_help(ctx, "role")

    # ---------------------------------------------------------- mass role: all / bots / cancel

    async def _start_mass_role(self, ctx: commands.Context, role: discord.Role, target_type: str, remove: bool) -> None:
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        if ctx.guild.id in self._mass_operations and not self._mass_operations[ctx.guild.id].done():
            await ctx.error("A mass role operation is already running in this server. Run `,role cancel` first.")
            return

        task = asyncio.create_task(self._run_mass_role(ctx, role, target_type, remove))
        self._mass_operations[ctx.guild.id] = task

    async def _run_mass_role(self, ctx: commands.Context, role: discord.Role, target_type: str, remove: bool) -> None:
        members = [m for m in ctx.guild.members if (m.bot if target_type == "bots" else not m.bot)]
        total = len(members)
        verb = "Removing" if remove else "Adding"
        progress = await ctx.send(embed=discord.Embed(description=f"{verb} {role.mention} {'from' if remove else 'to'} {total} {target_type}... `0/{total}`"))

        changed = 0
        processed = 0
        try:
            for member in members:
                processed += 1
                try:
                    if remove:
                        if role in member.roles:
                            await member.remove_roles(role, reason=f"Mass role by {ctx.author}")
                            changed += 1
                    else:
                        if role not in member.roles:
                            await member.add_roles(role, reason=f"Mass role by {ctx.author}")
                            changed += 1
                except discord.HTTPException:
                    pass

                if processed % 10 == 0 or processed == total:
                    try:
                        await progress.edit(embed=discord.Embed(
                            description=f"{verb} {role.mention} {'from' if remove else 'to'} {total} {target_type}... `{processed}/{total}`"
                        ))
                    except discord.HTTPException:
                        pass

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            done_verb = "Removed" if remove else "Added"
            await progress.edit(embed=discord.Embed(
                description=f"⚠️ Cancelled. {done_verb} {role.mention} {'from' if remove else 'to'} {changed}/{processed} {target_type} checked so far."
            ))
            return
        finally:
            self._mass_operations.pop(ctx.guild.id, None)

        done_verb = "Removed" if remove else "Added"
        await progress.edit(embed=discord.Embed(
            description=f"✅ {done_verb} {role.mention} {'from' if remove else 'to'} {changed} {target_type}."
        ))

    @command_meta(
        category="Server",
        description="Adds a role to every human member. Use ,role all remove to remove it from everyone instead.",
        syntax=",role all <role>",
        examples=[",role all @Member", ",role all remove @Member"],
        permissions=["Manage Roles"],
    )
    @role.group(name="all", invoke_without_command=True)
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_all(self, ctx: commands.Context, *, role: discord.Role):
        await self._start_mass_role(ctx, role, "humans", remove=False)

    @command_meta(
        category="Server",
        description="Removes a role from every human member.",
        syntax=",role all remove <role>",
        examples=[",role all remove @Member"],
        permissions=["Manage Roles"],
    )
    @role_all.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def role_all_remove(self, ctx: commands.Context, *, role: discord.Role):
        await self._start_mass_role(ctx, role, "humans", remove=True)

    @command_meta(
        category="Server",
        description="Adds a role to every bot in the server. Use ,role bots remove to remove it from every bot instead.",
        syntax=",role bots <role>",
        examples=[",role bots @Bot", ",role bots remove @Bot"],
        permissions=["Manage Roles"],
    )
    @role.group(name="bots", invoke_without_command=True)
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_bots(self, ctx: commands.Context, *, role: discord.Role):
        await self._start_mass_role(ctx, role, "bots", remove=False)

    @command_meta(
        category="Server",
        description="Removes a role from every bot in the server.",
        syntax=",role bots remove <role>",
        examples=[",role bots remove @Bot"],
        permissions=["Manage Roles"],
    )
    @role_bots.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def role_bots_remove(self, ctx: commands.Context, *, role: discord.Role):
        await self._start_mass_role(ctx, role, "bots", remove=True)

    @command_meta(
        category="Server",
        description="Cancels the currently running ,role all/bots mass operation in this server.",
        syntax=",role cancel",
        examples=[",role cancel"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @role.command(name="cancel")
    @has_permission_or_fake("manage_roles")
    async def role_cancel(self, ctx: commands.Context):
        task = self._mass_operations.get(ctx.guild.id)
        if task is None or task.done():
            await ctx.error("No mass role operation is currently running.")
            return
        task.cancel()
        await ctx.success("Cancelling the running mass role operation...")

    # ---------------------------------------------------------- role management

    @command_meta(
        category="Server",
        description="Sets a role's color.",
        syntax=",role color <role> <hex>",
        examples=[",role color @VIP #FFD700"],
        permissions=["Manage Roles"],
    )
    @role.command(name="color", aliases=["colour"])
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_color(self, ctx: commands.Context, role: discord.Role, hex_color: str):
        hex_color = hex_color.strip().lstrip("#")
        try:
            value = int(hex_color, 16)
        except ValueError:
            await ctx.error("Provide a valid hex color, e.g. `#FFD700`.")
            return
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        await role.edit(colour=discord.Colour(value), reason=f"Color changed by {ctx.author}")
        await ctx.success(f"{role.mention}'s color is now `#{hex_color.upper()}`.")

    @command_meta(
        category="Server",
        description="Creates a new role.",
        syntax=",role create <name>",
        examples=[",role create VIP"],
        permissions=["Manage Roles"],
    )
    @role.command(name="create")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_create(self, ctx: commands.Context, *, name: str):
        new_role = await ctx.guild.create_role(name=name[:100], reason=f"Created by {ctx.author}")
        await ctx.success(f"Created {new_role.mention}.")

    @command_meta(
        category="Server",
        description="Deletes a role.",
        syntax=",role delete <role>",
        examples=[",role delete @OldRole"],
        permissions=["Manage Roles"],
    )
    @role.command(name="delete")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_delete(self, ctx: commands.Context, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        name = role.name
        await role.delete(reason=f"Deleted by {ctx.author}")
        await ctx.success(f"Deleted **{name}**.")

    @command_meta(
        category="Server",
        description="Toggles whether a role is displayed separately in the member list.",
        syntax=",role hoist <role>",
        examples=[",role hoist @VIP"],
        permissions=["Manage Roles"],
    )
    @role.command(name="hoist")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_hoist(self, ctx: commands.Context, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        await role.edit(hoist=not role.hoist, reason=f"Hoist toggled by {ctx.author}")
        await ctx.success(f"{role.mention} is now **{'hoisted' if role.hoist else 'not hoisted'}**.")

    @command_meta(
        category="Server",
        description="Sets a role's icon - pass an image URL, or a single emoji. Requires the server to have enough boost level for role icons.",
        syntax=",role icon <role> <image_url_or_emoji>",
        examples=[",role icon @VIP 👑", ",role icon @VIP https://example.com/icon.png"],
        permissions=["Manage Roles"],
    )
    @role.command(name="icon")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_icon(self, ctx: commands.Context, role: discord.Role, icon: str):
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return

        icon = icon.strip()
        display_icon: bytes | str

        if icon.startswith("http://") or icon.startswith("https://"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status != 200:
                            await ctx.error("Couldn't download that image.")
                            return
                        display_icon = await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
                await ctx.error("Couldn't download that image.")
                return
        else:
            display_icon = icon  # treat as a unicode emoji

        try:
            await role.edit(display_icon=display_icon, reason=f"Icon changed by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.error(f"Discord rejected that icon - this server may not have role icons unlocked. ({exc})")
            return

        await ctx.success(f"Updated {role.mention}'s icon.")

    @command_meta(
        category="Server",
        description="Toggles whether a role can be mentioned by everyone.",
        syntax=",role mentionable <role>",
        examples=[",role mentionable @Announcements"],
        permissions=["Manage Roles"],
    )
    @role.command(name="mentionable")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx: commands.Context, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        await role.edit(mentionable=not role.mentionable, reason=f"Mentionable toggled by {ctx.author}")
        await ctx.success(f"{role.mention} is now **{'mentionable' if role.mentionable else 'not mentionable'}**.")

    @command_meta(
        category="Server",
        description="Renames a role.",
        syntax=",role rename <role> <new_name>",
        examples=[",role rename @oldname NewName"],
        permissions=["Manage Roles"],
    )
    @role.command(name="rename")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_rename(self, ctx: commands.Context, role: discord.Role, *, new_name: str):
        if role >= ctx.guild.me.top_role:
            await ctx.error(f"I can't manage **{role.name}** - it's above my highest role.")
            return
        old_name = role.name
        await role.edit(name=new_name[:100], reason=f"Renamed by {ctx.author}")
        await ctx.success(f"Renamed **{old_name}** to **{role.name}**.")

    @command_meta(
        category="Server",
        description="Re-applies the roles a member had the last time they left the server.",
        syntax=",role restore <member>",
        examples=[",role restore @User"],
        permissions=["Manage Roles"],
    )
    @role.command(name="restore")
    @has_permission_or_fake("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def role_restore(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            role_ids = await roles_repository.get_sticky_roles(session, ctx.guild.id, member.id)

        if not role_ids:
            await ctx.info(f"No stored roles found for **{member}**.")
            return

        roles_to_add = []
        for role_id in role_ids:
            role = ctx.guild.get_role(role_id)
            if role is not None and role < ctx.guild.me.top_role:
                roles_to_add.append(role)

        if not roles_to_add:
            await ctx.error("None of their previous roles still exist or are manageable by me.")
            return

        await member.add_roles(*roles_to_add, reason=f"Roles restored by {ctx.author}")
        await ctx.success(f"Restored {len(roles_to_add)} role(s) to **{member}**.")

    # ---------------------------------------------------------- ,roles

    @command_meta(
        category="Information",
        description="Lists every role in the server, or a member's roles if one is mentioned.",
        syntax=",roles [member]",
        examples=[",roles", ",roles @User"],
        require_args=False,
    )
    @commands.command(name="roles")
    @commands.guild_only()
    async def roles_list(self, ctx: commands.Context, member: discord.Member = None):
        if member is not None:
            title = f"{member.display_name}'s Roles"
            role_list = [r for r in reversed(member.roles) if r.name != "@everyone"]
        else:
            title = f"Roles in {ctx.guild.name}"
            role_list = [r for r in reversed(ctx.guild.roles) if r.name != "@everyone"]

        if not role_list:
            await ctx.info("No roles found.")
            return

        lines = [f"`{i:02d}` {role.mention}" for i, role in enumerate(role_list, start=1)]
        chunks = [lines[i : i + 10] for i in range(0, len(lines), 10)]

        pages = []
        for chunk in chunks:
            embed = discord.Embed(title=title, description="\n".join(chunk))
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            pages.append(embed)

        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    # ---------------------------------------------------------- reaction roles

    @command_meta(
        category="Server",
        description="Manage reaction roles for messages.",
        syntax=",reactionrole",
        examples=[],
        permissions=["Manage Roles"],
        aliases=["rr", "reactionroles", "reactrole"],
        require_args=False,
    )
    @commands.group(name="reactionrole", aliases=["rr", "reactionroles", "reactrole"], invoke_without_command=True)
    @commands.guild_only()
    @has_permission_or_fake("manage_roles")
    async def reactionrole(self, ctx: commands.Context):
        await send_help(ctx, "reactionrole")

    @reactionrole.command(name="help")
    async def reactionrole_help(self, ctx: commands.Context):
        await send_help(ctx, "reactionrole")

    @command_meta(
        category="Server",
        description="Add a reaction role to a message.",
        syntax=",reactionrole add <message_link> <emoji> <role>",
        examples=[",reactionrole add https://discord.com/channels/1/2/3 🎮 @Gamer"],
        permissions=["Manage Roles"],
    )
    @reactionrole.command(name="add")
    @has_permission_or_fake("manage_roles")
    async def reactionrole_add(self, ctx: commands.Context, message: discord.Message, emoji: str, role: discord.Role):
        async with get_session() as session:
            existing = await roles_repository.get_reaction_roles_for_guild(session, ctx.guild.id)
        allowed, limit = await premium_service.check_limit(ctx.guild.id, "reactionrole", len(existing))
        if not allowed:
            is_prem = await premium_service.is_premium(ctx.guild.id, "server")
            await ctx.error(premium_service.limit_reached_message("reaction roles", limit, is_prem))
            return

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.error("I couldn't react with that emoji - make sure it's valid and I can use it.")
            return

        async with get_session() as session:
            await roles_repository.add_reaction_role(session, ctx.guild.id, message.id, emoji, role.id)
        await ctx.success(f"Reacting with {emoji} on that message now toggles {role.mention}.")

    @command_meta(
        category="Server",
        description="Remove a reaction role from a message.",
        syntax=",reactionrole remove <message_link> <emoji>",
        examples=[",reactionrole remove https://discord.com/channels/1/2/3 🎮"],
        permissions=["Manage Roles"],
    )
    @reactionrole.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def reactionrole_remove(self, ctx: commands.Context, message: discord.Message, emoji: str):
        async with get_session() as session:
            removed = await roles_repository.remove_reaction_role(session, ctx.guild.id, message.id, emoji)

        if not removed:
            await ctx.error("No reaction role found for that message/emoji combination.")
            return

        try:
            await message.clear_reaction(emoji)
        except discord.HTTPException:
            pass

        await ctx.success(f"Removed the reaction role for {emoji} on that message.")

    @command_meta(
        category="Server",
        description="List all reaction roles in the server.",
        syntax=",reactionrole list",
        examples=[",reactionrole list"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @reactionrole.command(name="list")
    @has_permission_or_fake("manage_roles")
    async def reactionrole_list(self, ctx: commands.Context):
        async with get_session() as session:
            entries = await roles_repository.get_reaction_roles_for_guild(session, ctx.guild.id)

        if not entries:
            await ctx.info("No reaction roles configured.")
            return

        lines = [
            f"{entry.emoji} → <@&{entry.role_id}> — [message](https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{entry.message_id})"
            for entry in entries
        ]
        embed = discord.Embed(title="Reaction Roles", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Clear all reaction roles from the server.",
        syntax=",reactionrole clear",
        examples=[",reactionrole clear"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @reactionrole.command(name="clear")
    @has_permission_or_fake("manage_roles")
    async def reactionrole_clear(self, ctx: commands.Context):
        async with get_session() as session:
            count = await roles_repository.clear_reaction_roles(session, ctx.guild.id)
        await ctx.success(f"Cleared {count} reaction role(s).")

    # ---------------------------------------------------------- button roles

    @command_meta(
        category="Server",
        description="Manage button roles for messages.",
        syntax=",buttonrole",
        examples=[],
        permissions=["Manage Roles"],
        aliases=["buttonroles"],
        require_args=False,
    )
    @commands.group(name="buttonrole", aliases=["buttonroles"], invoke_without_command=True)
    @commands.guild_only()
    @has_permission_or_fake("manage_roles")
    async def buttonrole(self, ctx: commands.Context):
        await send_help(ctx, "buttonrole")

    @buttonrole.command(name="help")
    async def buttonrole_help(self, ctx: commands.Context):
        await send_help(ctx, "buttonrole")

    @command_meta(
        category="Server",
        description="Add a button role to one of my messages.",
        syntax=",buttonrole add <message_id> <role> [style] [emoji] [label]",
        examples=[",buttonrole add 123456789012345678 @Gamer primary 🎮 Gamer Role"],
        permissions=["Manage Roles"],
    )
    @buttonrole.command(name="add")
    @has_permission_or_fake("manage_roles")
    async def buttonrole_add(self, ctx: commands.Context, message_id: int, role: discord.Role, *, rest: str = ""):
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.error("Message not found in this channel.")
            return

        if message.author.id != self.bot.user.id:
            await ctx.error("I can only add buttons to my own messages.")
            return

        tokens = rest.split() if rest else []
        style = "secondary"
        emoji = None

        if tokens and tokens[0].lower() in roles_service.STYLE_MAP:
            style = tokens.pop(0).lower()

        if tokens and (tokens[0].startswith("<:") or tokens[0].startswith("<a:") or len(tokens[0]) <= 4):
            emoji = tokens.pop(0)

        label = " ".join(tokens) if tokens else role.name

        custom_id = f"blade_buttonrole:{message.id}:{role.id}"

        async with get_session() as session:
            existing = await roles_repository.get_button_role(session, message.id, custom_id)
            if existing is not None:
                await ctx.error(f"{role.mention} already has a button on that message.")
                return

            all_button_roles = await roles_repository.get_all_button_roles_for_guild(session, ctx.guild.id)
            allowed, limit = await premium_service.check_limit(ctx.guild.id, "buttonrole", len(all_button_roles))
            if not allowed:
                is_prem = await premium_service.is_premium(ctx.guild.id, "server")
                await ctx.error(premium_service.limit_reached_message("button roles", limit, is_prem))
                return

            await roles_repository.add_button_role(
                session, ctx.guild.id, message.id, custom_id, role.id, label, style, emoji,
            )
            rows = await roles_repository.get_button_roles_for_message(session, message.id)

        view = ButtonRolePanelView(message.id, [(r.custom_id, r.label, r.role_id, r.style, r.emoji) for r in rows])
        try:
            await message.edit(view=view)
        except discord.HTTPException:
            await ctx.error("Couldn't update that message - it may have too many buttons already (max 25).")
            return
        self.bot.add_view(view)

        await ctx.success(f"Added a button for {role.mention} to that message.")

    @command_meta(
        category="Server",
        description="List all button roles in the server.",
        syntax=",buttonrole list",
        examples=[",buttonrole list"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @buttonrole.command(name="list")
    @has_permission_or_fake("manage_roles")
    async def buttonrole_list(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await roles_repository.get_all_button_roles_for_guild(session, ctx.guild.id)

        if not rows:
            await ctx.info("No button roles configured.")
            return

        by_message: dict[int, list] = {}
        for row in rows:
            by_message.setdefault(row.message_id, []).append(row)

        lines = []
        for message_id, message_rows in by_message.items():
            link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message_id}"
            lines.append(f"**Message** [{message_id}]({link})")
            for i, row in enumerate(message_rows):
                lines.append(f"`{i}` {row.emoji or ''} {row.label} → <@&{row.role_id}>")

        embed = discord.Embed(title="Button Roles", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Remove a button role from a message by index.",
        syntax=",buttonrole remove <message_id> <index>",
        examples=[",buttonrole remove 123456789012345678 0"],
        permissions=["Manage Roles"],
    )
    @buttonrole.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def buttonrole_remove(self, ctx: commands.Context, message_id: int, index: int):
        async with get_session() as session:
            rows = await roles_repository.get_button_roles_for_message(session, message_id)
            if not (0 <= index < len(rows)):
                await ctx.error(f"No button at index `{index}` on that message.")
                return

            target = rows[index]
            await roles_repository.remove_button_role_row(session, target)
            remaining = await roles_repository.get_button_roles_for_message(session, message_id)

        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            message = None

        if message is not None:
            view = ButtonRolePanelView(
                message_id, [(r.custom_id, r.label, r.role_id, r.style, r.emoji) for r in remaining]
            ) if remaining else None
            try:
                await message.edit(view=view)
                if view is not None:
                    self.bot.add_view(view)
            except discord.HTTPException:
                pass

        await ctx.success(f"Removed the button role at index `{index}` from that message.")

    @command_meta(
        category="Server",
        description="Remove all button roles from a message.",
        syntax=",buttonrole removeall <message_id>",
        examples=[",buttonrole removeall 123456789012345678"],
        permissions=["Manage Roles"],
    )
    @buttonrole.command(name="removeall")
    @has_permission_or_fake("manage_roles")
    async def buttonrole_removeall(self, ctx: commands.Context, message_id: int):
        async with get_session() as session:
            count = await roles_repository.remove_button_roles_for_message(session, message_id)

        if count == 0:
            await ctx.error("That message has no button roles.")
            return

        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.edit(view=None)
        except discord.HTTPException:
            pass

        await ctx.success(f"Removed {count} button role(s) from that message.")

    @command_meta(
        category="Server",
        description="Remove all button roles from the server.",
        syntax=",buttonrole reset",
        examples=[",buttonrole reset"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @buttonrole.command(name="reset")
    @has_permission_or_fake("manage_roles")
    async def buttonrole_reset(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await roles_repository.get_all_button_roles_for_guild(session, ctx.guild.id)
            message_ids = {row.message_id for row in rows}
            count = await roles_repository.clear_button_roles_for_guild(session, ctx.guild.id)

        for message_id in message_ids:
            try:
                message = await ctx.channel.fetch_message(message_id)
                await message.edit(view=None)
            except discord.HTTPException:
                pass

        await ctx.success(f"Cleared {count} button role(s) from the server.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
