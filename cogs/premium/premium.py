"""
,premium and ,plans - category "General". ,premium approve/remove are
owner-only and deliberately excluded from command_meta (no @command_meta
decorator) so they never show up in ,help.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands, tasks

from core.command_meta import command_meta
from database.database import get_session
from repositories import premium_repository
from services import premium_service


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        premium_service.check_renewals.start(bot)

    def cog_unload(self) -> None:
        premium_service.check_renewals.cancel()

    # ---------------------------------------------------------- ,premium

    @command_meta(
        category="General",
        description="Want more free slots and premium-only features? Buy Blaid Premium.",
        syntax=",premium",
        examples=[],
        require_args=False,
    )
    @commands.group(name="premium", with_app_command=False, invoke_without_command=True)
    @commands.guild_only()
    async def premium(self, ctx: commands.Context):
        view = premium_service.GetPremiumView()
        await ctx.send(view=view)

    # ---------------------------------------------------------- ,plans

    @command_meta(
        category="General",
        description="Shows what each Blaid Premium plan includes.",
        syntax=",plans",
        examples=[],
        require_args=False,
    )
    @commands.command(name="plans", with_app_command=False)
    async def plans(self, ctx: commands.Context):
        description = (
            "**Server Premium**\n"
            "> Autoresponders: `10` â `200`\n"
            "> Reaction Roles: `15` â `250`\n"
            "> Autoroles: `2` â `50`\n"
            "> Log Channels: `4` â `15`\n"
            "> Ticket Panels: `3` â `10`\n"
            "> Level Role Rewards: `50` â `200`\n"
            "> Button Roles: `50` â `150`\n"
            "> Join to Create Hubs: `1` â `3`\n"
            "> AI Questions/day: `10` â `200`\n"
            "> Backups (,backup)\n"
            "> Unlocks `,funnel`, `,verification`, `,selfpurge`, `,twitch`, `,antinuke soundboard`, "
            "`,antinuke vanity`, `,antiraid avatar`, `,antiraid username`, `,firstmessage`\n"
            "> Customizable level-up stat cards\n\n"
            "**Customize**\n"
            "> Unlocks the entire `,customize` command family - a server-specific bot name, avatar, banner, and bio\n\n"
            "Run `,premium` to buy."
        )
        embed = discord.Embed(title="Premium Plans", description=description)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- owner-only subcommands, deliberately no
    # @command_meta on either - keeps them out of ,help entirely, per "der ist nur fÃ¼r mich"

    @premium.command(name="approve")
    @commands.is_owner()
    async def premium_approve(self, ctx: commands.Context, plan: str, guild_id: int):
        plan = plan.lower()
        if plan in ("serverpremium", "server"):
            plan = "server"
        elif plan == "customize":
            plan = "customize"
        else:
            await ctx.send("Plan must be `customize` or `serverpremium`.")
            return

        async with get_session() as session:
            purchase = await premium_repository.get_latest_pending_purchase(session, guild_id, plan)

        period = purchase.billing_period if purchase else "lifetime"
        expires_at = None
        if period == "monthly":
            expires_at = discord.utils.utcnow() + datetime.timedelta(days=30)
        elif period == "yearly":
            expires_at = discord.utils.utcnow() + datetime.timedelta(days=365)

        async with get_session() as session:
            cfg = await premium_repository.get_or_create_config(session, guild_id)
            if plan == "server":
                await premium_repository.update_config(
                    session, cfg, server_premium=True, server_premium_expires_at=expires_at
                )
            else:
                await premium_repository.update_config(
                    session, cfg, customize_premium=True, customize_premium_expires_at=expires_at
                )

        sent_to_channel = await premium_service.send_approval_confirmation(self.bot, guild_id, plan)

        confirmation = f"Approved **{plan}** premium for guild `{guild_id}`."
        if not sent_to_channel:
            confirmation += " (No pending billing channel found to notify - message the buyer directly.)"
        await ctx.send(confirmation)

    @premium.command(name="remove")
    @commands.is_owner()
    async def premium_remove(self, ctx: commands.Context, plan: str, guild_id: int):
        plan = plan.lower()
        if plan in ("serverpremium", "server"):
            plan = "server"
        elif plan == "customize":
            plan = "customize"
        else:
            await ctx.send("Plan must be `customize` or `serverpremium`.")
            return

        async with get_session() as session:
            cfg = await premium_repository.get_or_create_config(session, guild_id)
            if plan == "server":
                await premium_repository.update_config(
                    session, cfg, server_premium=False, server_premium_expires_at=None
                )
            else:
                await premium_repository.update_config(
                    session, cfg, customize_premium=False, customize_premium_expires_at=None
                )

        await ctx.send(f"Removed **{plan}** premium from guild `{guild_id}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
