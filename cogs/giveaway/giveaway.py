"""Giveaway commands."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake

from core.command_meta import command_meta
from core.help_formatter import send_help
from core.converters import Duration
from database.database import get_session
from repositories import giveaway_repository
from services.giveaway_service import edit_giveaway, end_giveaway, reroll_giveaway, start_giveaway


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        from services.giveaway_service import GiveawayEntryView

        async with get_session() as session:
            active = await giveaway_repository.get_active_giveaways(session)
        for giveaway in active:
            self.bot.add_view(GiveawayEntryView(giveaway.id))

    @command_meta(
        category="Server",
        description="Starts a giveaway in the current channel.",
        syntax=",giveaway start <duration> <winners> <prize>",
        examples=[",giveaway start 1h 1 Nitro"],
        permissions=["Manage Guild"],
        aliases=["gw"],
    )
    @commands.group(name="giveaway", aliases=["gw"], invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @giveaway.command(name="start")
    @has_permission_or_fake("manage_guild")
    async def giveaway_start(self, ctx: commands.Context, duration: Duration, winners: int, *, prize: str):
        winners = max(1, min(winners, 20))
        await start_giveaway(ctx.channel, ctx.author, prize, winners, duration, self.bot)
        await ctx.success(f"Giveaway started for **{prize}**.")

    @command_meta(
        category="Server",
        description="Ends a giveaway early and picks winners now.",
        syntax=",giveaway end <giveaway_id>",
        examples=[",giveaway end 4"],
        permissions=["Manage Guild"],
    )
    @giveaway.command(name="end")
    @has_permission_or_fake("manage_guild")
    async def giveaway_end(self, ctx: commands.Context, giveaway_id: int):
        winners = await end_giveaway(self.bot, giveaway_id)
        if winners:
            await ctx.success(f"Giveaway ended. {len(winners)} winner(s) selected.")
        else:
            await ctx.info("Giveaway ended - no valid entries.")

    @command_meta(
        category="Server",
        description="Rerolls the winner(s) of a previously ended giveaway.",
        syntax=",giveaway reroll <giveaway_id>",
        examples=[",giveaway reroll 4"],
        permissions=["Manage Guild"],
    )
    @giveaway.command(name="reroll")
    @has_permission_or_fake("manage_guild")
    async def giveaway_reroll(self, ctx: commands.Context, giveaway_id: int):
        winners = await reroll_giveaway(self.bot, giveaway_id)
        if winners:
            await ctx.success(f"Rerolled - {len(winners)} new winner(s) selected.")
        else:
            await ctx.info("No valid entries to reroll from.")

    @command_meta(
        category="Server",
        description="Lists all currently active giveaways in this server.",
        syntax=",giveaway list",
        examples=[",giveaway list"],
        require_args=False,
    )
    @giveaway.command(name="list")
    async def giveaway_list(self, ctx: commands.Context):
        async with get_session() as session:
            active = await giveaway_repository.get_active_giveaways(session)
        active = [g for g in active if g.guild_id == ctx.guild.id]

        if not active:
            await ctx.info("No active giveaways.")
            return

        lines = [f"`#{g.id}` **{g.prize}** in <#{g.channel_id}> — ends <t:{int(g.ends_at.timestamp())}:R>" for g in active]
        await ctx.send(embed=discord.Embed(title="Active Giveaways", description="\n".join(lines)))

    @command_meta(
        category="Server",
        description="Toggles whether you get DMed when a giveaway you hosted ends. A personal setting - follows you across every server.",
        syntax=",giveaway dmcreator",
        examples=[",giveaway dmcreator"],
        require_args=False,
    )
    @giveaway.command(name="dmcreator")
    async def giveaway_dmcreator(self, ctx: commands.Context):
        async with get_session() as session:
            settings = await giveaway_repository.get_or_create_user_settings(session, ctx.author.id)
            settings.dm_on_creator_end = not settings.dm_on_creator_end
            await session.commit()
        await ctx.success(f"You will {'now' if settings.dm_on_creator_end else 'no longer'} be DMed when your giveaways end.")

    @command_meta(
        category="Server",
        description="Toggles whether you get DMed when you win a giveaway. A personal setting - follows you across every server.",
        syntax=",giveaway dmwinners",
        examples=[",giveaway dmwinners"],
        require_args=False,
    )
    @giveaway.command(name="dmwinners")
    async def giveaway_dmwinners(self, ctx: commands.Context):
        async with get_session() as session:
            settings = await giveaway_repository.get_or_create_user_settings(session, ctx.author.id)
            settings.dm_on_winner = not settings.dm_on_winner
            await session.commit()
        await ctx.success(f"You will {'now' if settings.dm_on_winner else 'no longer'} be DMed when you win a giveaway.")

    @command_meta(
        category="Server",
        description="Sets a custom embed template for this server's giveaways. Use {prize} as a placeholder.",
        syntax=",giveaway template <title|description|color> <value>",
        examples=[",giveaway template title {prize} Giveaway!", ",giveaway template color #ff5500"],
        permissions=["Manage Guild"],
    )
    @giveaway.group(name="template", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def giveaway_template(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @giveaway_template.command(name="title")
    @has_permission_or_fake("manage_guild")
    async def giveaway_template_title(self, ctx: commands.Context, *, title: str):
        async with get_session() as session:
            template = await giveaway_repository.get_or_create_template(session, ctx.guild.id)
            template.title = title[:256]
            await session.commit()
        await ctx.success("Giveaway embed title template updated.")

    @giveaway_template.command(name="description")
    @has_permission_or_fake("manage_guild")
    async def giveaway_template_description(self, ctx: commands.Context, *, description: str):
        async with get_session() as session:
            template = await giveaway_repository.get_or_create_template(session, ctx.guild.id)
            template.description = description
            await session.commit()
        await ctx.success("Giveaway embed description template updated.")

    @giveaway_template.command(name="color")
    @has_permission_or_fake("manage_guild")
    async def giveaway_template_color(self, ctx: commands.Context, hex_color: str):
        hex_color = hex_color.strip()
        if not hex_color.startswith("#"):
            hex_color = f"#{hex_color}"
        try:
            int(hex_color.lstrip("#"), 16)
        except ValueError:
            await ctx.error("Invalid hex color. Example: `#ff5500`.")
            return

        async with get_session() as session:
            template = await giveaway_repository.get_or_create_template(session, ctx.guild.id)
            template.color = hex_color
            await session.commit()
        await ctx.success(f"Giveaway embed color set to `{hex_color}`.")

    @command_meta(
        category="Server",
        description="Toggles a role from being able to enter giveaways.",
        syntax=",giveaway blacklist <role>",
        examples=[",giveaway blacklist @Muted"],
        permissions=["Manage Guild"],
    )
    @giveaway.command(name="blacklist")
    @has_permission_or_fake("manage_guild")
    async def giveaway_blacklist(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            now_blacklisted = await giveaway_repository.toggle_blacklist(session, ctx.guild.id, role.id)
        if now_blacklisted:
            await ctx.success(f"{role.mention} can no longer enter giveaways.")
        else:
            await ctx.success(f"{role.mention} can enter giveaways again.")

    @command_meta(
        category="Server",
        description="Sets the number of entries members with a role receive in giveaway draws.",
        syntax=",giveaway setmax <role> <entries>",
        examples=[",giveaway setmax @Booster 3"],
        permissions=["Manage Guild"],
    )
    @giveaway.command(name="setmax")
    @has_permission_or_fake("manage_guild")
    async def giveaway_setmax(self, ctx: commands.Context, role: discord.Role, entries: int):
        entries = max(1, min(entries, 20))
        async with get_session() as session:
            await giveaway_repository.set_role_max_entries(session, ctx.guild.id, role.id, entries)
        await ctx.success(f"Members with {role.mention} now get `{entries}` entries per giveaway.")

    @command_meta(
        category="Server",
        description="Edits an active giveaway's duration, description, prize, or winner count.",
        syntax=",giveaway edit <duration|description|prize|winners> <giveaway_id> <value>",
        examples=[",giveaway edit prize 4 Discord Nitro"],
        permissions=["Manage Guild"],
    )
    @giveaway.group(name="edit", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def giveaway_edit(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @giveaway_edit.command(name="duration")
    @has_permission_or_fake("manage_guild")
    async def giveaway_edit_duration(self, ctx: commands.Context, giveaway_id: int, duration: Duration):
        result = await edit_giveaway(self.bot, giveaway_id, duration_seconds=duration)
        if result is None:
            await ctx.error(f"No active giveaway with ID `{giveaway_id}`.")
            return
        await ctx.success(f"Giveaway `#{giveaway_id}` now ends <t:{int(result.ends_at.timestamp())}:R>.")

    @giveaway_edit.command(name="description")
    @has_permission_or_fake("manage_guild")
    async def giveaway_edit_description(self, ctx: commands.Context, giveaway_id: int, *, description: str):
        result = await edit_giveaway(self.bot, giveaway_id, description=description)
        if result is None:
            await ctx.error(f"No active giveaway with ID `{giveaway_id}`.")
            return
        await ctx.success(f"Giveaway `#{giveaway_id}` description updated.")

    @giveaway_edit.command(name="prize")
    @has_permission_or_fake("manage_guild")
    async def giveaway_edit_prize(self, ctx: commands.Context, giveaway_id: int, *, prize: str):
        result = await edit_giveaway(self.bot, giveaway_id, prize=prize)
        if result is None:
            await ctx.error(f"No active giveaway with ID `{giveaway_id}`.")
            return
        await ctx.success(f"Giveaway `#{giveaway_id}` prize updated to **{prize}**.")

    @giveaway_edit.command(name="winners")
    @has_permission_or_fake("manage_guild")
    async def giveaway_edit_winners(self, ctx: commands.Context, giveaway_id: int, winner_count: int):
        result = await edit_giveaway(self.bot, giveaway_id, winner_count=winner_count)
        if result is None:
            await ctx.error(f"No active giveaway with ID `{giveaway_id}`.")
            return
        await ctx.success(f"Giveaway `#{giveaway_id}` now has `{result.winner_count}` winner(s).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))