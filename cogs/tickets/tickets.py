"""
Ticket system commands - the group rename/alias, help routing, all
action commands, forms, and the options builder. Claim/unclaim/close/
reopen/delete/move all route through the central do_* functions in
services/ticket_service.py, which enforce creator_can_close, trainee/
support-role permissions, and send the option's configured messages -
the command layer here is just argument parsing + calling those.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake

from core.command_meta import command_meta
from core.help_formatter import send_help
from database.database import get_session
from repositories import ticket_repository
from services import ticket_forms_service, ticket_options_service
from services.ticket_service import (
    build_panel_view,
    do_claim,
    do_close,
    do_delete,
    do_move,
    do_reopen,
    do_unclaim,
    get_option_for_ticket,
    get_transcript,
    handle_member_leave,
    handle_ticket_activity,
    resume_ticket_control_views,
    resume_ticket_timers,
)


async def _get_ticket_and_option(channel_id: int):
    async with get_session() as session:
        ticket = await ticket_repository.get_ticket_by_channel(session, channel_id)
    if ticket is None:
        return None, None
    option = await get_option_for_ticket(ticket)
    return ticket, option


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        async with get_session() as session:
            from sqlalchemy import select
            from database.tickets_models import TicketPanel
            result = await session.execute(select(TicketPanel))
            panels = list(result.scalars().all())

        for panel in panels:
            view = await build_panel_view(panel.id)
            if panel.message_id:
                self.bot.add_view(view, message_id=panel.message_id)
            else:
                self.bot.add_view(view)

        resumed_controls = await resume_ticket_control_views(self.bot)
        resumed_close, resumed_delete = await resume_ticket_timers(self.bot)
        if resumed_controls or resumed_close or resumed_delete:
            import logging
            logging.getLogger("blade.tickets").info(
                "Resumed %d ticket control view(s), %d auto-close timer(s), %d auto-delete timer(s).",
                resumed_controls, resumed_close, resumed_delete,
            )

    # ---------------------------------------------------------- listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await handle_ticket_activity(self.bot, message)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await handle_member_leave(member.guild, member)

    # ---------------------------------------------------------- group root

    @command_meta(
        category="Server",
        description="Opens the panel management menu - pick an existing panel or create a new one.",
        syntax=",tickets panel",
        examples=[",tickets panel"],
        permissions=["Manage Guild"],
        aliases=["tix"],
        require_args=False,
    )
    @commands.group(name="tickets", aliases=["tix"], invoke_without_command=True)
    @commands.guild_only()
    async def tickets(self, ctx: commands.Context):
        await send_help(ctx, "tickets")

    @tickets.command(name="help")
    async def tickets_help(self, ctx: commands.Context):
        await send_help(ctx, "tickets")

    @tickets.command(name="panel")
    @has_permission_or_fake("manage_guild")
    async def tickets_panel(self, ctx: commands.Context):
        from services import ticket_panel_manager_service
        await ticket_panel_manager_service.start(ctx)

    @command_meta(
        category="Server",
        description="Resends a panel's message and button, e.g. if the original was deleted.",
        syntax=",tickets resend <panel_id>",
        examples=[",tickets resend 1"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="resend")
    @has_permission_or_fake("manage_guild")
    async def tickets_resend(self, ctx: commands.Context, panel_id: int):
        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, panel_id)
        if panel is None or panel.guild_id != ctx.guild.id:
            await ctx.error(f"No panel found with ID `{panel_id}`.")
            return

        embed = discord.Embed(title=panel.title, description=panel.description)
        view = await build_panel_view(panel.id)
        message = await ctx.send(embed=embed, view=view)

        async with get_session() as session:
            panel = await ticket_repository.get_panel(session, panel_id)
            panel.channel_id = ctx.channel.id
            panel.message_id = message.id
            session.add(panel)
            await session.commit()

    @command_meta(
        category="Server",
        description="Creates or manages ticket forms - questions asked when a ticket is opened.",
        syntax=",tickets forms",
        examples=[",tickets forms"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="forms", aliases=["form"])
    @has_permission_or_fake("manage_guild")
    async def tickets_forms(self, ctx: commands.Context):
        await ticket_forms_service.start(ctx)

    @command_meta(
        category="Server",
        description="Toggle whether ticket-closed logs are sent, for every panel in this server.",
        syntax=",tickets logs <on|off>",
        examples=[",tickets logs on"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="logs")
    @has_permission_or_fake("manage_guild")
    async def tickets_logs(self, ctx: commands.Context, state: str):
        value = state.lower() in ("on", "true", "enable", "enabled")
        async with get_session() as session:
            panels = await ticket_repository.get_panels_for_guild(session, ctx.guild.id)
            for panel in panels:
                await ticket_repository.update_panel(session, panel, logs_enabled=value)

        await ctx.success(f"{ctx.author.mention}: Ticket-closed logs are now **{'enabled' if value else 'disabled'}**.")

    @command_meta(
        category="Server",
        description="Set the ticket-closed log message, for every panel in this server.",
        syntax=",tickets logs message [script]",
        examples=[",tickets logs message {ticket.creator} closed ticket #{ticket.case}"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="logsmessage", aliases=["logmessage"])
    @has_permission_or_fake("manage_guild")
    async def tickets_logs_message(self, ctx: commands.Context, *, script: str = None):
        from database.tickets_models import DEFAULT_LOG_MESSAGE

        async with get_session() as session:
            panels = await ticket_repository.get_panels_for_guild(session, ctx.guild.id)
            for panel in panels:
                await ticket_repository.update_panel(session, panel, log_message_template=script or DEFAULT_LOG_MESSAGE)

        await ctx.success(f"{ctx.author.mention}: Updated the ticket-closed log message.")

    @command_meta(
        category="Server",
        description="Configures a panel's options - behavior, form, messages, automation, and style per option.",
        syntax=",tickets options",
        examples=[",tickets options"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="options")
    @has_permission_or_fake("manage_guild")
    async def tickets_options(self, ctx: commands.Context):
        await ticket_options_service.start(ctx)

    # ---------------------------------------------------------- claim / unclaim

    @command_meta(
        category="Server",
        description="Claims the current ticket. Anyone with Manage Guild, a configured support role, or (if allowed) a trainee role can do this.",
        syntax=",tickets claim",
        examples=[",tickets claim"],
        require_args=False,
    )
    @tickets.command(name="claim")
    async def tickets_claim(self, ctx: commands.Context):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return
        success, message = await do_claim(ctx.channel, ctx.author, ticket, option)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Server",
        description="Unclaims the current ticket.",
        syntax=",tickets unclaim",
        examples=[",tickets unclaim"],
        require_args=False,
    )
    @tickets.command(name="unclaim")
    async def tickets_unclaim(self, ctx: commands.Context):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return
        success, message = await do_unclaim(ctx.channel, ctx.author, ticket, option)
        await (ctx.success(message) if success else ctx.error(message))

    # ---------------------------------------------------------- close / reopen / delete

    @command_meta(
        category="Server",
        description="Closes the current ticket. Creators can close their own ticket if Creator Can Close is enabled for its option.",
        syntax=",tickets close",
        examples=[",tickets close"],
        require_args=False,
    )
    @tickets.command(name="close")
    async def tickets_close(self, ctx: commands.Context):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return

        success, message = await do_close(self.bot, ctx.channel, ctx.author, ticket, option)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Server",
        description="Permanently deletes the current ticket channel after saving a transcript.",
        syntax=",tickets delete",
        examples=[",tickets delete"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="delete")
    @has_permission_or_fake("manage_guild")
    async def tickets_delete(self, ctx: commands.Context):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return
        success, message = await do_delete(ctx.channel, ctx.author, ticket, option)
        if not success:
            await ctx.error(message)

    @command_meta(
        category="Server",
        description="Reopens a closed ticket.",
        syntax=",tickets reopen",
        examples=[",tickets reopen"],
        require_args=False,
    )
    @tickets.command(name="reopen")
    async def tickets_reopen(self, ctx: commands.Context):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return
        success, message = await do_reopen(ctx.channel, ctx.author, ticket, option)
        await (ctx.success(message) if success else ctx.error(message))

    # ---------------------------------------------------------- allow / deny

    @command_meta(
        category="Server",
        description="Allows a user into the current ticket even if they're not staff.",
        syntax=",tickets allow <user>",
        examples=[",tickets allow @User"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="allow")
    @has_permission_or_fake("manage_guild")
    async def tickets_allow(self, ctx: commands.Context, user: discord.Member):
        async with get_session() as session:
            ticket = await ticket_repository.get_ticket_by_channel(session, ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return

        try:
            await ctx.channel.set_permissions(user, view_channel=True, send_messages=True)
        except discord.Forbidden:
            await ctx.error("I don't have permission to edit this channel.")
            return
        await ctx.success(f"{user.mention} can now view and reply in this ticket.")

    @command_meta(
        category="Server",
        description="Removes a user's access from the current ticket.",
        syntax=",tickets deny <user>",
        examples=[",tickets deny @User"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="deny")
    @has_permission_or_fake("manage_guild")
    async def tickets_deny(self, ctx: commands.Context, user: discord.Member):
        async with get_session() as session:
            ticket = await ticket_repository.get_ticket_by_channel(session, ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return

        try:
            await ctx.channel.set_permissions(user, view_channel=False, send_messages=False)
        except discord.Forbidden:
            await ctx.error("I don't have permission to edit this channel.")
            return
        await ctx.success(f"{user.mention} no longer has access to this ticket.")

    # ---------------------------------------------------------- move / rename

    @command_meta(
        category="Server",
        description="Moves the current ticket to a different category.",
        syntax=",tickets move <category>",
        examples=[",tickets move Escalated"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="move")
    @has_permission_or_fake("manage_guild")
    async def tickets_move(self, ctx: commands.Context, *, category: discord.CategoryChannel):
        ticket, option = await _get_ticket_and_option(ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return
        success, message = await do_move(ctx.channel, ctx.author, ticket, option, category)
        await (ctx.success(message) if success else ctx.error(message))

    @command_meta(
        category="Server",
        description="Renames the current ticket channel.",
        syntax=",tickets rename <name>",
        examples=[",tickets rename billing-question"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="rename")
    @has_permission_or_fake("manage_guild")
    async def tickets_rename(self, ctx: commands.Context, *, name: str):
        async with get_session() as session:
            ticket = await ticket_repository.get_ticket_by_channel(session, ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return

        try:
            await ctx.channel.edit(name=name.strip()[:100])
        except discord.Forbidden:
            await ctx.error("I don't have permission to rename this channel.")
            return
        await ctx.success(f"Ticket renamed to `{name}`.")

    # ---------------------------------------------------------- blacklist

    @command_meta(
        category="Server",
        description="Toggles a user from being able to open new tickets.",
        syntax=",tickets blacklist <user>",
        examples=[",tickets blacklist @User"],
        permissions=["Manage Guild"],
    )
    @tickets.command(name="blacklist")
    @has_permission_or_fake("manage_guild")
    async def tickets_blacklist(self, ctx: commands.Context, user: discord.Member):
        async with get_session() as session:
            already = await ticket_repository.is_blacklisted(session, ctx.guild.id, user.id)
            if already:
                await ticket_repository.remove_blacklist(session, ctx.guild.id, user.id)
            else:
                await ticket_repository.add_blacklist(session, ctx.guild.id, user.id)

        if already:
            await ctx.success(f"{user.mention} can open tickets again.")
        else:
            await ctx.success(f"{user.mention} is now blacklisted from opening tickets.")

    # ---------------------------------------------------------- all / stats / status

    @command_meta(
        category="Server",
        description="Shows all currently open tickets in this server.",
        syntax=",tickets all",
        examples=[",tickets all"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="all")
    @has_permission_or_fake("manage_guild")
    async def tickets_all(self, ctx: commands.Context):
        async with get_session() as session:
            open_tickets = await ticket_repository.get_open_tickets(session, ctx.guild.id)

        if not open_tickets:
            embed = discord.Embed(description=f"{ctx.author.mention} There are no tickets in this server.")
            await ctx.send(embed=embed)
            return

        lines = [f"`#{t.case_number}` <#{t.channel_id}> — opened by <@{t.creator_id}> ({t.status})" for t in open_tickets]
        await ctx.send(embed=discord.Embed(title="Open Tickets", description="\n".join(lines)[:4000]))

    @command_meta(
        category="Server",
        description="Shows ticket statistics for this server.",
        syntax=",tickets stats",
        examples=[",tickets stats"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="stats")
    @has_permission_or_fake("manage_guild")
    async def tickets_stats(self, ctx: commands.Context):
        async with get_session() as session:
            counts = await ticket_repository.count_tickets(session, ctx.guild.id)

        embed = discord.Embed(title="Ticket Statistics")
        embed.add_field(name="Total", value=str(counts["total"]), inline=True)
        embed.add_field(name="Open", value=str(counts["open"]), inline=True)
        embed.add_field(name="Claimed", value=str(counts["claimed"]), inline=True)
        embed.add_field(name="Closed", value=str(counts["closed"]), inline=True)
        await ctx.send(embed=embed)

    @command_meta(
        category="Server",
        description="Shows the status of the current ticket.",
        syntax=",tickets status",
        examples=[",tickets status"],
        require_args=False,
    )
    @tickets.command(name="status")
    async def tickets_status(self, ctx: commands.Context):
        async with get_session() as session:
            ticket = await ticket_repository.get_ticket_by_channel(session, ctx.channel.id)
        if ticket is None:
            await ctx.error("This is not a ticket channel.")
            return

        embed = discord.Embed(title=f"Ticket #{ticket.case_number}")
        embed.add_field(name="Creator", value=f"<@{ticket.creator_id}>", inline=True)
        embed.add_field(name="Claimed By", value=f"<@{ticket.claimed_by}>" if ticket.claimed_by else "Unclaimed", inline=True)
        embed.add_field(name="Status", value=ticket.status.title(), inline=True)
        embed.add_field(name="Opened", value=f"<t:{int(ticket.created_at.timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- transcript

    @command_meta(
        category="Server",
        description="Generates a transcript of the current (or a given) ticket channel without closing it.",
        syntax=",tickets transcript [channel]",
        examples=[",tickets transcript", ",tickets transcript #ticket-user"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @tickets.command(name="transcript")
    @has_permission_or_fake("manage_guild")
    async def tickets_transcript(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        path = await get_transcript(channel)
        if path is None:
            await ctx.error(f"{channel.mention} is not a ticket channel.")
            return

        await ctx.send(file=discord.File(path))

    @command_meta(
        category="Server",
        description="Show the variables available in ticket messages.",
        syntax=",tickets variables",
        examples=[",tickets variables"],
        require_args=False,
    )
    @tickets.command(name="variables", aliases=["vars"])
    async def tickets_variables(self, ctx: commands.Context):
        variables = [
            "{ticket.case}", "{ticket.id}",
            "{ticket.creator}", "{ticket.creator.id}", "{ticket.creator.name}", "{ticket.creator.mention}",
            "{ticket.author}", "{ticket.author.id}", "{ticket.author.name}", "{ticket.author.mention}",
            "{ticket.claimed_by}", "{ticket.claimed_by.mention}",
            "{ticket.closed_by}", "{ticket.closed_by.mention}",
            "{ticket.deleted_by}", "{ticket.deleted_by.mention}",
            "{ticket.opened_at}", "{ticket.open_time}",
            "{ticket.users}",
            "{ticket.status}",
        ]
        description = (
            " ".join(f"`{v}`" for v in variables)
            + "\n\nThe usual `{user.*}`, `{guild.*}`, and `{channel.*}` variables also work in ticket messages - "
            "everything else renders as normal script."
        )
        embed = discord.Embed(title="Ticket Variables", description=description)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))