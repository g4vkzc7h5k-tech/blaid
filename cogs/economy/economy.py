"""
Economy - ,balance / ,daily / ,work / ,crime / ,rob / ,shop / ,transfer /
,deposit / ,withdraw / ,leaderboard / ,addbalance (owner) / ,removebalance
(owner) / ,resetbalance (owner), plus gambling games: blackjack, bombs,
coinflip, crash, dice, gamble, highlow, ladder, plinko, roulette,
scratch, slots.

Money lives in two places per member: wallet (spendable, at risk in
games and to ,rob) and bank (safe, only touched by ,deposit/,withdraw).

HONEST SCOPE NOTE: blackjack and crash are real interactive games
(buttons, live state). The other 10 games are single-shot: bet in,
one random roll, payout or loss shown immediately - not multi-step
interactive boards (e.g. bombs/mines isn't a real tile grid you click
through, it's one probability roll based on how many bombs you chose).
This keeps 12 games shippable in one pass rather than a handful done
deeply and the rest not at all - say if you want any specific one
turned into a fuller interactive version later.
"""

from __future__ import annotations

import random

import discord
from discord.ext import commands

from core import embeds as core_embeds
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.helpers import format_duration
from database.database import get_session
from repositories import economy_repository

COOLDOWNS = {
    "daily": 86400,
    "work": 3600,
    "crime": 1800,
    "rob": 3600,
}


def _money(amount: int) -> str:
    return f"${amount:,}"


def _seconds_until(last: "datetime | None", cooldown: int) -> int:
    import datetime

    if last is None:
        return 0
    last_aware = last if last.tzinfo is not None else last.replace(tzinfo=datetime.timezone.utc)
    elapsed = (discord.utils.utcnow() - last_aware).total_seconds()
    remaining = cooldown - elapsed
    return max(0, int(remaining))


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- root / help

    @command_meta(
        category="Economy",
        description="Earn, gamble, and manage your server balance.",
        syntax=",economy",
        examples=[],
        require_args=False,
    )
    @commands.command(name="economy", with_app_command=False)
    async def economy(self, ctx: commands.Context):
        await send_help(ctx, "economy")

    # ---------------------------------------------------------- balance

    @command_meta(
        category="Economy",
        description="Shows your (or another member's) wallet and bank balance.",
        syntax=",balance [member]",
        examples=[",balance", ",balance @User"],
        require_args=False,
    )
    @commands.command(name="balance", aliases=["bal"], with_app_command=False)
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, member.id)

        embed = discord.Embed(
            description=(
                f"**Wallet** {_money(row.wallet)}\n"
                f"**Bank** {_money(row.bank)}\n"
                f"**Total** {_money(row.wallet + row.bank)}"
            ),
            color=core_embeds.COLOR_INFO,
        )
        embed.set_author(name=f"{member.display_name}'s Balance", icon_url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- addbalance / removebalance / resetbalance (owner only)

    @command_meta(
        category="Economy",
        description="Adds to a member's wallet. Bot owner only.",
        syntax=",addbalance <member> <amount>",
        examples=[",addbalance @User 1000"],
        permissions=["Bot Owner"],
    )
    @commands.command(name="addbalance", with_app_command=False)
    @commands.is_owner()
    @commands.guild_only()
    async def addbalance(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            await ctx.error("Amount must be positive.")
            return
        async with get_session() as session:
            row = await economy_repository.add_wallet(session, ctx.guild.id, member.id, amount)
        await ctx.success(f"Added {_money(amount)} to {member.mention}'s wallet. New balance: {_money(row.wallet)}.")

    @command_meta(
        category="Economy",
        description="Removes from a member's wallet. Bot owner only.",
        syntax=",removebalance <member> <amount>",
        examples=[",removebalance @User 1000"],
        permissions=["Bot Owner"],
    )
    @commands.command(name="removebalance", with_app_command=False)
    @commands.is_owner()
    @commands.guild_only()
    async def removebalance(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            await ctx.error("Amount must be positive.")
            return
        async with get_session() as session:
            row = await economy_repository.add_wallet(session, ctx.guild.id, member.id, -amount)
        await ctx.success(f"Removed {_money(amount)} from {member.mention}'s wallet. New balance: {_money(row.wallet)}.")

    @command_meta(
        category="Economy",
        description="Resets a member's balance to zero. Bot owner only.",
        syntax=",resetbalance <member>",
        examples=[",resetbalance @User"],
        permissions=["Bot Owner"],
    )
    @commands.command(name="resetbalance", with_app_command=False)
    @commands.is_owner()
    @commands.guild_only()
    async def resetbalance(self, ctx: commands.Context, member: discord.Member):
        async with get_session() as session:
            await economy_repository.reset_balance(session, ctx.guild.id, member.id)
        await ctx.success(f"Reset {member.mention}'s balance to {_money(0)}.")

    # ---------------------------------------------------------- deposit / withdraw / transfer

    @command_meta(
        category="Economy",
        description="Moves money from your wallet into your bank.",
        syntax=",deposit <amount|all>",
        examples=[",deposit 500", ",deposit all"],
    )
    @commands.command(name="deposit", with_app_command=False)
    @commands.guild_only()
    async def deposit(self, ctx: commands.Context, amount: str):
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)

        value = row.wallet if amount.lower() == "all" else _parse_amount(amount)
        if value is None or value <= 0:
            await ctx.error("Provide a positive amount, or `all`.")
            return
        if value > row.wallet:
            await ctx.error(f"You only have {_money(row.wallet)} in your wallet.")
            return

        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=row.wallet - value, bank=row.bank + value)

        await ctx.success(f"Deposited {_money(value)} into your bank.")

    @command_meta(
        category="Economy",
        description="Moves money from your bank into your wallet.",
        syntax=",withdraw <amount|all>",
        examples=[",withdraw 500", ",withdraw all"],
    )
    @commands.command(name="withdraw", with_app_command=False)
    @commands.guild_only()
    async def withdraw(self, ctx: commands.Context, amount: str):
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)

        value = row.bank if amount.lower() == "all" else _parse_amount(amount)
        if value is None or value <= 0:
            await ctx.error("Provide a positive amount, or `all`.")
            return
        if value > row.bank:
            await ctx.error(f"You only have {_money(row.bank)} in your bank.")
            return

        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=row.wallet + value, bank=row.bank - value)

        await ctx.success(f"Withdrew {_money(value)} from your bank.")

    @command_meta(
        category="Economy",
        description="Sends money from your wallet to another member.",
        syntax=",transfer <member> <amount>",
        examples=[",transfer @User 500"],
    )
    @commands.command(name="transfer", aliases=["pay"], with_app_command=False)
    @commands.guild_only()
    async def transfer(self, ctx: commands.Context, member: discord.Member, amount: int):
        if member.id == ctx.author.id:
            await ctx.error("You can't transfer money to yourself.")
            return
        if amount <= 0:
            await ctx.error("Amount must be positive.")
            return

        async with get_session() as session:
            sender = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            if amount > sender.wallet:
                await ctx.error(f"You only have {_money(sender.wallet)} in your wallet.")
                return
            await economy_repository.add_wallet(session, ctx.guild.id, ctx.author.id, -amount)
            await economy_repository.add_wallet(session, ctx.guild.id, member.id, amount)

        await ctx.success(f"Sent {_money(amount)} to {member.mention}.")

    # ---------------------------------------------------------- daily / work / crime / rob

    @command_meta(
        category="Economy",
        description="Claim your daily reward.",
        syntax=",daily",
        examples=[",daily"],
        require_args=False,
    )
    @commands.command(name="daily", with_app_command=False)
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)

        remaining = _seconds_until(row.last_daily, COOLDOWNS["daily"])
        if remaining > 0:
            await ctx.error(f"You can claim your daily reward again in `{format_duration(remaining)}`.")
            return

        reward = random.randint(500, 1000)
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=row.wallet + reward, last_daily=discord.utils.utcnow())

        embed = discord.Embed(description=f"You claimed your daily reward of {_money(reward)}.", color=core_embeds.COLOR_SUCCESS)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Economy",
        description="Work for some money.",
        syntax=",work",
        examples=[",work"],
        require_args=False,
    )
    @commands.command(name="work", with_app_command=False)
    @commands.guild_only()
    async def work(self, ctx: commands.Context):
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)

        remaining = _seconds_until(row.last_work, COOLDOWNS["work"])
        if remaining > 0:
            await ctx.error(f"You can work again in `{format_duration(remaining)}`.")
            return

        reward = random.randint(100, 300)
        jobs = ["delivered packages", "walked dogs", "fixed a website", "washed cars", "waited tables", "mowed lawns"]
        job = random.choice(jobs)

        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=row.wallet + reward, last_work=discord.utils.utcnow())

        embed = discord.Embed(description=f"You {job} and earned {_money(reward)}.", color=core_embeds.COLOR_SUCCESS)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Economy",
        description="Attempt a crime for a bigger reward - risky, you can get caught.",
        syntax=",crime",
        examples=[",crime"],
        require_args=False,
    )
    @commands.command(name="crime", with_app_command=False)
    @commands.guild_only()
    async def crime(self, ctx: commands.Context):
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)

        remaining = _seconds_until(row.last_crime, COOLDOWNS["crime"])
        if remaining > 0:
            await ctx.error(f"You can attempt another crime in `{format_duration(remaining)}`.")
            return

        success = random.random() < 0.7
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            if success:
                reward = random.randint(200, 600)
                await economy_repository.update_balance(
                    session, row, wallet=row.wallet + reward, last_crime=discord.utils.utcnow()
                )
                embed = discord.Embed(description=f"Your crime paid off! You earned {_money(reward)}.", color=core_embeds.COLOR_SUCCESS)
            else:
                penalty = min(row.wallet, random.randint(100, 300))
                await economy_repository.update_balance(
                    session, row, wallet=row.wallet - penalty, last_crime=discord.utils.utcnow()
                )
                embed = discord.Embed(description=f"You got caught and paid a fine of {_money(penalty)}.", color=core_embeds.COLOR_ERROR)

        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Economy",
        description="Attempt to rob another member's wallet.",
        syntax=",rob <member>",
        examples=[",rob @User"],
    )
    @commands.command(name="rob", with_app_command=False)
    @commands.guild_only()
    async def rob(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.error("You can't rob yourself.")
            return

        async with get_session() as session:
            robber = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            target = await economy_repository.get_or_create_balance(session, ctx.guild.id, member.id)

        remaining = _seconds_until(robber.last_rob, COOLDOWNS["rob"])
        if remaining > 0:
            await ctx.error(f"You can attempt another robbery in `{format_duration(remaining)}`.")
            return

        if target.wallet < 100:
            await ctx.error(f"{member.mention} doesn't have enough in their wallet to be worth robbing.")
            return

        success = random.random() < 0.4
        async with get_session() as session:
            robber = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            target = await economy_repository.get_or_create_balance(session, ctx.guild.id, member.id)

            if success:
                stolen = int(target.wallet * random.uniform(0.10, 0.30))
                await economy_repository.update_balance(session, target, wallet=target.wallet - stolen)
                await economy_repository.update_balance(
                    session, robber, wallet=robber.wallet + stolen, last_rob=discord.utils.utcnow()
                )
                embed = discord.Embed(
                    description=f"You robbed {member.mention} and got away with {_money(stolen)}!",
                    color=core_embeds.COLOR_SUCCESS,
                )
            else:
                fine = min(robber.wallet, random.randint(50, 200))
                await economy_repository.update_balance(
                    session, robber, wallet=robber.wallet - fine, last_rob=discord.utils.utcnow()
                )
                embed = discord.Embed(
                    description=f"You got caught trying to rob {member.mention} and paid a fine of {_money(fine)}.",
                    color=core_embeds.COLOR_ERROR,
                )

        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- leaderboard

    @command_meta(
        category="Economy",
        description="Shows the richest members in this server.",
        syntax=",leaderboard",
        examples=[",leaderboard"],
        aliases=["lb"],
        require_args=False,
    )
    @commands.command(name="leaderboard", aliases=["lb"], with_app_command=False)
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        async with get_session() as session:
            rows = await economy_repository.get_leaderboard(session, ctx.guild.id, limit=10)

        if not rows:
            await ctx.info("No balances recorded yet.")
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row.user_id)
            name = member.display_name if member else f"User {row.user_id}"
            lines.append(f"`{i:02d}` **{name}** â {_money(row.wallet + row.bank)}")

        embed = discord.Embed(title=f"Richest in {ctx.guild.name}", description="\n".join(lines), color=core_embeds.COLOR_INFO)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- shop

    @command_meta(
        category="Economy",
        description="Shows the server shop, or manages it (Manage Guild: add/remove items).",
        syntax=",shop",
        examples=[",shop"],
        require_args=False,
    )
    @commands.group(name="shop", invoke_without_command=True, with_app_command=False)
    @commands.guild_only()
    async def shop(self, ctx: commands.Context):
        async with get_session() as session:
            items = await economy_repository.get_shop_items(session, ctx.guild.id)

        if not items:
            await ctx.info("This server's shop is empty.")
            return

        lines = [f"`#{item.id}` **{item.name}** â {_money(item.price)}" for item in items]
        embed = discord.Embed(title=f"{ctx.guild.name} Shop", description="\n".join(lines), color=core_embeds.COLOR_INFO)
        embed.set_footer(text="Buy with ,shop buy <#>")
        await ctx.send(embed=embed)

    @shop.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def shop_add(self, ctx: commands.Context, price: int, *, name: str):
        if price <= 0:
            await ctx.error("Price must be positive.")
            return
        async with get_session() as session:
            item = await economy_repository.add_shop_item(session, ctx.guild.id, name, price)
        await ctx.success(f"Added **{item.name}** to the shop for {_money(item.price)} (`#{item.id}`).")

    @shop.command(name="buy")
    async def shop_buy(self, ctx: commands.Context, item_id: int):
        async with get_session() as session:
            item = await economy_repository.get_shop_item(session, item_id)
            if item is None or item.guild_id != ctx.guild.id:
                await ctx.error("No item found with that ID.")
                return

            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            if row.wallet < item.price:
                await ctx.error(f"You need {_money(item.price)} to buy that - you have {_money(row.wallet)}.")
                return

            await economy_repository.update_balance(session, row, wallet=row.wallet - item.price)
            await economy_repository.add_inventory_item(session, ctx.guild.id, ctx.author.id, item.id)

        await ctx.success(f"Bought **{item.name}** for {_money(item.price)}.")

    # ---------------------------------------------------------- simple single-shot games

    async def _place_bet(self, ctx: commands.Context, amount: int):
        """Shared bet validation - returns the balance row if valid,
        or None (already sent an error) if not."""
        if amount <= 0:
            await ctx.error("Bet must be positive.")
            return None
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
        if amount > row.wallet:
            await ctx.error(f"You only have {_money(row.wallet)} in your wallet.")
            return None
        return row

    async def _resolve_bet(self, ctx: commands.Context, amount: int, payout: int, description: str, won: bool) -> None:
        """payout is the NET change to wallet (already includes/excludes
        the original bet, e.g. pass -amount for a total loss, or
        +amount*2 for a 2x win)."""
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=max(0, row.wallet + payout))

        embed = discord.Embed(description=description, color=core_embeds.COLOR_SUCCESS if won else core_embeds.COLOR_ERROR)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @command_meta(
        category="Economy",
        description="Flip a coin - call heads or tails.",
        syntax=",coinflip <amount> <heads|tails>",
        examples=[",coinflip 100 heads"],
    )
    @commands.command(name="coinflip", aliases=["cf"], with_app_command=False)
    @commands.guild_only()
    async def coinflip(self, ctx: commands.Context, amount: int, call: str):
        call = call.lower()
        if call not in ("heads", "tails"):
            await ctx.error("Call `heads` or `tails`.")
            return
        if await self._place_bet(ctx, amount) is None:
            return

        result = random.choice(["heads", "tails"])
        won = result == call
        payout = amount if won else -amount
        desc = f"The coin landed on **{result}**. " + (f"You won {_money(amount)}!" if won else f"You lost {_money(amount)}.")
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Roll a die - 4, 5, or 6 wins.",
        syntax=",dice <amount>",
        examples=[",dice 100"],
    )
    @commands.command(name="dice", with_app_command=False)
    @commands.guild_only()
    async def dice(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        roll = random.randint(1, 6)
        won = roll >= 4
        payout = amount if won else -amount
        desc = f"You rolled a **{roll}**. " + (f"You won {_money(amount)}!" if won else f"You lost {_money(amount)}.")
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Double or nothing, roughly 45% odds.",
        syntax=",gamble <amount>",
        examples=[",gamble 100"],
    )
    @commands.command(name="gamble", with_app_command=False)
    @commands.guild_only()
    async def gamble(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        won = random.random() < 0.45
        payout = amount if won else -amount
        desc = f"You won {_money(amount)}!" if won else f"You lost {_money(amount)}."
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Guess whether the next card is higher or lower.",
        syntax=",highlow <amount> <higher|lower>",
        examples=[",highlow 100 higher"],
    )
    @commands.command(name="highlow", aliases=["hl"], with_app_command=False)
    @commands.guild_only()
    async def highlow(self, ctx: commands.Context, amount: int, guess: str):
        guess = guess.lower()
        if guess not in ("higher", "lower"):
            await ctx.error("Guess `higher` or `lower`.")
            return
        if await self._place_bet(ctx, amount) is None:
            return

        card_a = random.randint(2, 13)  # leave room for a strictly higher/lower comparison
        card_b = random.randint(2, 14)
        while card_b == card_a:
            card_b = random.randint(2, 14)

        actual = "higher" if card_b > card_a else "lower"
        won = actual == guess
        payout = amount if won else -amount
        desc = (
            f"First card: **{card_a}**, second card: **{card_b}** ({actual}). "
            + (f"You won {_money(amount)}!" if won else f"You lost {_money(amount)}.")
        )
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Climb the ladder - each rung multiplies your winnings, but you can fall at any point.",
        syntax=",ladder <amount>",
        examples=[",ladder 100"],
    )
    @commands.command(name="ladder", with_app_command=False)
    @commands.guild_only()
    async def ladder(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        rungs_climbed = 0
        for _ in range(5):
            if random.random() < 0.55:
                rungs_climbed += 1
            else:
                break

        if rungs_climbed == 0:
            await self._resolve_bet(ctx, amount, -amount, "You fell off the first rung and lost everything.", False)
            return

        multiplier = 1.5 ** rungs_climbed
        winnings = int(amount * multiplier)
        payout = winnings - amount
        desc = f"You climbed **{rungs_climbed}** rung(s) (`x{multiplier:.2f}`) and won {_money(winnings)}!"
        await self._resolve_bet(ctx, amount, payout, desc, True)

    @command_meta(
        category="Economy",
        description="Drop a ball through the pegs for a random multiplier.",
        syntax=",plinko <amount>",
        examples=[",plinko 100"],
    )
    @commands.command(name="plinko", with_app_command=False)
    @commands.guild_only()
    async def plinko(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        multipliers = [0, 0.5, 0.5, 1, 1, 1, 2, 2, 5, 10]
        weights = [10, 15, 15, 20, 20, 20, 12, 12, 4, 1]
        multiplier = random.choices(multipliers, weights=weights, k=1)[0]

        winnings = int(amount * multiplier)
        payout = winnings - amount
        won = winnings > amount
        desc = f"The ball landed on **x{multiplier}** â " + (
            f"you won {_money(winnings)}!" if winnings > 0 else f"you lost {_money(amount)}."
        )
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Scratch a card for a random prize.",
        syntax=",scratch <amount>",
        examples=[",scratch 100"],
    )
    @commands.command(name="scratch", with_app_command=False)
    @commands.guild_only()
    async def scratch(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        outcomes = [0, 1, 2, 3, 5]
        weights = [40, 25, 20, 10, 5]
        multiplier = random.choices(outcomes, weights=weights, k=1)[0]

        winnings = int(amount * multiplier)
        payout = winnings - amount
        won = winnings > amount
        if multiplier == 0:
            desc = f"You scratched... nothing. You lost {_money(amount)}."
        elif multiplier == 1:
            desc = "You scratched your bet back - no gain, no loss."
        else:
            desc = f"You scratched a **x{multiplier}** prize and won {_money(winnings)}!"
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Spin the slots - match symbols to win.",
        syntax=",slots <amount>",
        examples=[",slots 100"],
    )
    @commands.command(name="slots", with_app_command=False)
    @commands.guild_only()
    async def slots(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        symbols = ["ð", "ð", "ð", "ð", "ð", "7ï¸â£"]
        reels = [random.choice(symbols) for _ in range(3)]

        if reels[0] == reels[1] == reels[2]:
            multiplier = 10 if reels[0] == "7ï¸â£" else 5
        elif len(set(reels)) == 2:
            multiplier = 1.5
        else:
            multiplier = 0

        winnings = int(amount * multiplier)
        payout = winnings - amount
        won = winnings > amount
        desc = f"{' '.join(reels)}\n\n" + (
            f"You won {_money(winnings)}!" if winnings > 0 else f"You lost {_money(amount)}."
        )
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Bet on a number (35x) or color (2x) - red, black, or green.",
        syntax=",roulette <amount> <number|red|black|green>",
        examples=[",roulette 100 red", ",roulette 100 17"],
    )
    @commands.command(name="roulette", with_app_command=False)
    @commands.guild_only()
    async def roulette(self, ctx: commands.Context, amount: int, bet: str):
        bet = bet.lower()
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

        if bet not in ("red", "black", "green") and not bet.isdigit():
            await ctx.error("Bet on a number (0-36), or `red`/`black`/`green`.")
            return
        if bet.isdigit() and not (0 <= int(bet) <= 36):
            await ctx.error("Number bets must be between 0 and 36.")
            return
        if await self._place_bet(ctx, amount) is None:
            return

        result = random.randint(0, 36)
        result_color = "green" if result == 0 else ("red" if result in red_numbers else "black")

        won = False
        multiplier = 0
        if bet.isdigit() and int(bet) == result:
            won = True
            multiplier = 35
        elif bet == result_color and bet != "green":
            won = True
            multiplier = 2
        elif bet == "green" and result == 0:
            won = True
            multiplier = 14

        winnings = amount * multiplier
        payout = winnings - amount if won else -amount
        desc = f"The ball landed on **{result} ({result_color})**. " + (
            f"You won {_money(winnings)}!" if won else f"You lost {_money(amount)}."
        )
        await self._resolve_bet(ctx, amount, payout, desc, won)

    @command_meta(
        category="Economy",
        description="Pick how many bombs to risk (1-24) - more bombs, higher risk and reward.",
        syntax=",bombs <amount> <bomb_count>",
        examples=[",bombs 100 5"],
    )
    @commands.command(name="bombs", with_app_command=False)
    @commands.guild_only()
    async def bombs(self, ctx: commands.Context, amount: int, bomb_count: int):
        bomb_count = max(1, min(bomb_count, 24))
        if await self._place_bet(ctx, amount) is None:
            return

        # Simplified single-roll odds: fewer bombs = safer, more bombs = riskier/higher payout.
        safe_tiles = 25 - bomb_count
        win_chance = safe_tiles / 25
        multiplier = round(1 / win_chance, 2) if win_chance > 0 else 0

        won = random.random() < win_chance
        winnings = int(amount * multiplier) if won else 0
        payout = winnings - amount if won else -amount
        desc = (
            f"You risked **{bomb_count}** bomb(s) (`x{multiplier}` potential). "
            + (f"You avoided them all and won {_money(winnings)}!" if won else f"You hit a bomb and lost {_money(amount)}.")
        )
        await self._resolve_bet(ctx, amount, payout, desc, won)

    # ---------------------------------------------------------- blackjack (interactive)

    @command_meta(
        category="Economy",
        description="Play a hand of blackjack against the dealer.",
        syntax=",blackjack <amount>",
        examples=[",blackjack 100"],
    )
    @commands.command(name="blackjack", aliases=["bj"], with_app_command=False)
    @commands.guild_only()
    async def blackjack(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        game = BlackjackGame(amount)
        embed = game.build_embed()
        view = BlackjackView(self, ctx.author.id, game)
        message = await ctx.send(embed=embed, view=view)
        view.message = message

        if game.is_over:
            await self._finish_blackjack(ctx, game)

    async def _finish_blackjack(self, ctx: commands.Context, game: "BlackjackGame") -> None:
        payout = game.payout()
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, ctx.guild.id, ctx.author.id)
            await economy_repository.update_balance(session, row, wallet=max(0, row.wallet + payout))

    # ---------------------------------------------------------- crash (interactive)

    @command_meta(
        category="Economy",
        description="Watch the multiplier rise and cash out before it crashes.",
        syntax=",crash <amount>",
        examples=[",crash 100"],
    )
    @commands.command(name="crash", with_app_command=False)
    @commands.guild_only()
    async def crash(self, ctx: commands.Context, amount: int):
        if await self._place_bet(ctx, amount) is None:
            return

        crash_point = round(random.uniform(1.0, 5.0), 2)
        view = CrashView(self, ctx.author.id, ctx.guild.id, amount, crash_point)
        embed = view.build_embed()
        message = await ctx.send(embed=embed, view=view)
        view.message = message


class BlackjackGame:
    """Standard blackjack rules, ace counted as 1 or 11."""

    SUITS = ["â ", "â¥", "â¦", "â£"]
    RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

    def __init__(self, bet: int):
        self.bet = bet
        self.deck = [f"{rank}{suit}" for suit in self.SUITS for rank in self.RANKS] * 2
        random.shuffle(self.deck)
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.is_over = False
        self.result_text = ""

        if self._value(self.player) == 21:
            self._resolve_dealer()

    @staticmethod
    def _value(hand: list[str]) -> int:
        total = 0
        aces = 0
        for card in hand:
            rank = card[:-1]
            if rank == "A":
                total += 11
                aces += 1
            elif rank in ("J", "Q", "K"):
                total += 10
            else:
                total += int(rank)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def hit(self) -> None:
        self.player.append(self.deck.pop())
        if self._value(self.player) >= 21:
            self._resolve_dealer()

    def stand(self) -> None:
        self._resolve_dealer()

    def _resolve_dealer(self) -> None:
        player_value = self._value(self.player)
        if player_value > 21:
            self.result_text = "Bust! You lose."
            self.is_over = True
            return

        while self._value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

        dealer_value = self._value(self.dealer)
        if player_value == 21 and len(self.player) == 2:
            self.result_text = "Blackjack! You win 2.5x."
        elif dealer_value > 21:
            self.result_text = "Dealer busts! You win."
        elif dealer_value > player_value:
            self.result_text = "Dealer wins."
        elif dealer_value < player_value:
            self.result_text = "You win!"
        else:
            self.result_text = "Push - bet returned."
        self.is_over = True

    def payout(self) -> int:
        """Net change to wallet."""
        if "Blackjack" in self.result_text:
            return int(self.bet * 1.5)
        if "You win" in self.result_text or "busts" in self.result_text:
            return self.bet
        if "Push" in self.result_text:
            return 0
        return -self.bet

    def build_embed(self) -> discord.Embed:
        dealer_display = " ".join(self.dealer) if self.is_over else f"{self.dealer[0]} ??"
        description = (
            f"**Your hand** ({self._value(self.player)}): {' '.join(self.player)}\n"
            f"**Dealer's hand**{' (' + str(self._value(self.dealer)) + ')' if self.is_over else ''}: {dealer_display}"
        )
        if self.is_over:
            description += f"\n\n**{self.result_text}**"

        color = core_embeds.COLOR_INFO
        if self.is_over:
            color = core_embeds.COLOR_SUCCESS if self.payout() > 0 else (
                core_embeds.COLOR_INFO if self.payout() == 0 else core_embeds.COLOR_ERROR
            )

        return discord.Embed(title="Blackjack", description=description, color=color)


class BlackjackView(discord.ui.View):
    def __init__(self, cog: Economy, author_id: int, game: BlackjackGame):
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id
        self.game = game
        self.message: discord.Message | None = None
        if game.is_over:
            for item in self.children:
                item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.game.hit()
        if self.game.is_over:
            for item in self.children:
                item.disabled = True
            async with get_session() as session:
                row = await economy_repository.get_or_create_balance(session, interaction.guild.id, self.author_id)
                await economy_repository.update_balance(session, row, wallet=max(0, row.wallet + self.game.payout()))
            self.stop()
        await interaction.response.edit_message(embed=self.game.build_embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.game.stand()
        for item in self.children:
            item.disabled = True
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, interaction.guild.id, self.author_id)
            await economy_repository.update_balance(session, row, wallet=max(0, row.wallet + self.game.payout()))
        await interaction.response.edit_message(embed=self.game.build_embed(), view=self)
        self.stop()


class CrashView(discord.ui.View):
    def __init__(self, cog: Economy, author_id: int, guild_id: int, amount: int, crash_point: float):
        super().__init__(timeout=30)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.amount = amount
        self.crash_point = crash_point
        self.current_multiplier = 1.0
        self.cashed_out = False
        self.crashed = False
        self.message: discord.Message | None = None

    def build_embed(self) -> discord.Embed:
        if self.cashed_out:
            winnings = int(self.amount * self.current_multiplier)
            desc = f"You cashed out at **x{self.current_multiplier:.2f}** and won {_money(winnings)}!"
            color = core_embeds.COLOR_SUCCESS
        elif self.crashed:
            desc = f"Crashed at **x{self.crash_point:.2f}**! You lost {_money(self.amount)}."
            color = core_embeds.COLOR_ERROR
        else:
            desc = f"Multiplier: **x{self.current_multiplier:.2f}**\nCash out before it crashes!"
            color = core_embeds.COLOR_INFO
        return discord.Embed(title="Crash", description=desc, color=color)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success)
    async def cash_out(self, interaction: discord.Interaction, _button: discord.ui.Button):
        # Simplified: one click resolves at a random point between 1.0x
        # and the pre-rolled crash point, simulating "you clicked at
        # some point before it crashed" rather than a live-ticking
        # multiplier (Discord rate-limits rapid message edits too
        # heavily for a smooth real-time animation here).
        self.current_multiplier = round(random.uniform(1.0, self.crash_point), 2)
        self.cashed_out = True
        for item in self.children:
            item.disabled = True

        winnings = int(self.amount * self.current_multiplier)
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, self.guild_id, self.author_id)
            await economy_repository.update_balance(session, row, wallet=max(0, row.wallet + (winnings - self.amount)))

        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        self.stop()

    async def on_timeout(self) -> None:
        if self.cashed_out:
            return
        self.crashed = True
        for item in self.children:
            item.disabled = True
        async with get_session() as session:
            row = await economy_repository.get_or_create_balance(session, self.guild_id, self.author_id)
            await economy_repository.update_balance(session, row, wallet=max(0, row.wallet - self.amount))
        if self.message is not None:
            try:
                await self.message.edit(embed=self.build_embed(), view=self)
            except discord.HTTPException:
                pass


def _parse_amount(raw: str) -> int | None:
    try:
        value = int(raw.replace(",", "").replace("$", ""))
        return value
    except ValueError:
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
