"""
,premium - category "General". Buying now goes through Discord's own
App Monetization (real purchase buttons, native checkout) instead of
the old manual billing-channel flow - see services/premium_service.py
for the entitlement-handling side of this.

,plans is gone - the plan details now live on the premium buttons/
website instead of a separate command.

,premium approve/remove are owner-only manual overrides (e.g. gifting
premium, or fixing a sync issue) and deliberately excluded from
command_meta so they never show up in ,help.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from core.command_meta import command_meta
from database.database import get_session
from repositories import premium_repository
from services import premium_service


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        synced = await premium_service.sync_entitlements(self.bot)
        if synced:
            import logging
            logging.getLogger("blade.premium").info("Synced %d active entitlement(s) on startup.", synced)

    # ---------------------------------------------------------- entitlement events

    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement):
        await premium_service.apply_entitlement(self.bot, entitlement, active=True)

    @commands.Cog.listener()
    async def on_entitlement_update(self, entitlement: discord.Entitlement):
        await premium_service.apply_entitlement(self.bot, entitlement, active=not entitlement.deleted)

    @commands.Cog.listener()
    async def on_entitlement_delete(self, entitlement: discord.Entitlement):
        await premium_service.apply_entitlement(self.bot, entitlement, active=False)

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
        view = premium_service.ChoosePlanView()
        await ctx.send(view=view)

    # ---------------------------------------------------------- owner-only manual overrides, deliberately
    # no @command_meta on either - keeps them out of ,help entirely

    @premium.command(name="approve")
    @commands.is_owner()
    async def premium_approve(self, ctx: commands.Context, plan: str, guild_id: int, period: str = "lifetime"):
        plan = plan.lower()
        if plan in ("serverpremium", "server"):
            plan = "server"
        elif plan == "customize":
            plan = "customize"
        else:
            await ctx.send("Plan must be `customize` or `serverpremium`.")
            return

        expires_at = None
        if period == "monthly":
            expires_at = discord.utils.utcnow() + datetime.timedelta(days=30)

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

        await ctx.send(f"Manually granted **{plan}** premium ({period}) for guild `{guild_id}`.")

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
