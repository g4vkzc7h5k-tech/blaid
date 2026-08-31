"""
Premium system.

Two independent plans, each billed monthly/yearly/lifetime:
- "server" (Server Premium) - raises per-guild feature limits and
  unlocks a handful of premium-only commands, for the whole server.
- "customize" (Customize) - unlocks ,customize (per-server bot
  branding) for the whole server.

Purchases are entirely manual: a private billing channel is created,
the buyer is shown a fixed price and payment details, and clicking
"Finished Payment" pings the bot owner in a fixed channel to review
and run ,premium approve by hand. There is no automated payment
verification - see the disclosure already given to the user for this
project about the risks of that approach.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands, tasks

from database.database import get_session
from repositories import premium_repository

# ---------------------------------------------------------- constants

OWNER_NOTIFY_CHANNEL_ID = 1543424088322871316

PAYMENT_IBAN = "DE64 8005 3722 0405 6541 70"
PAYMENT_PAYPAL = "elixx6.zsd@gmail.com"

PLAN_LABELS = {"server": "Server Premium", "customize": "Customize"}
PERIOD_LABELS = {"monthly": "Monthly", "yearly": "Yearly", "lifetime": "Lifetime"}

PRICES = {
    "customize": {"monthly": "2.99â¬", "yearly": "4.99â¬", "lifetime": "6.99â¬"},
    "server": {"monthly": "4.99â¬", "yearly": "7.99â¬", "lifetime": "10.99â¬"},
}

PERIOD_DAYS = {"monthly": 30, "yearly": 365, "lifetime": None}

# feature -> (free_limit, premium_limit) - server premium raises these
LIMITS = {
    "autoresponder": (10, 200),
    "reactionrole": (15, 250),
    "autorole": (2, 50),
    "log_channels": (4, 15),
    "ticket_panels": (3, 10),
    "level_role_rewards": (50, 200),
    "buttonrole": (50, 150),
    "jointocreate_hubs": (1, 3),
    "ai_questions_per_day": (10, 200),
}

# Commands that are entirely premium-only (not a limit increase - a
# hard gate). Keyed by the command's qualified name.
PREMIUM_COMMANDS_SERVER = {
    "funnel", "verification", "selfpurge", "twitch",
    "antinuke soundboard", "antinuke vanity",
    "antiraid avatar", "antiraid username", "firstmessage",
}
PREMIUM_COMMANDS_CUSTOMIZE = {"customize"}


def get_limit(feature: str, is_premium: bool) -> int:
    free_limit, premium_limit = LIMITS[feature]
    return premium_limit if is_premium else free_limit


async def check_limit(guild_id: int, feature: str, current_count: int) -> tuple[bool, int]:
    """Returns (allowed, limit) - allowed is False if current_count is
    already at or above the limit for this guild's premium status."""
    premium = await is_premium(guild_id, "server")
    limit = get_limit(feature, premium)
    return current_count < limit, limit


def limit_reached_message(feature_label: str, limit: int, is_premium: bool) -> str:
    if is_premium:
        return f"You've reached the Server Premium limit of **{limit}** {feature_label}."
    return f"You've reached the free limit of **{limit}** {feature_label}. Upgrade with `,premium` for more."


# ---------------------------------------------------------- status checks

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _make_aware(dt: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite doesn't preserve tzinfo even on a DateTime(timezone=True)
    column - values read back naive. Treat naive values as UTC so
    comparisons against _now() (aware) never crash."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


async def is_premium(guild_id: int, plan: str) -> bool:
    async with get_session() as session:
        cfg = await premium_repository.get_config(session, guild_id)
    if cfg is None:
        return False

    if plan == "server":
        if not cfg.server_premium:
            return False
        expires_at = _make_aware(cfg.server_premium_expires_at)
        return expires_at is None or expires_at > _now()
    if plan == "customize":
        if not cfg.customize_premium:
            return False
        expires_at = _make_aware(cfg.customize_premium_expires_at)
        return expires_at is None or expires_at > _now()
    return False


# ---------------------------------------------------------- gate view (Components V2)

def _gate_text(command_name: str | None) -> str:
    if command_name:
        top = f"**{command_name}** is a **premium-only** feature."
    else:
        top = "Want **more free slots** and **premium-only** features?"
    return top + "\n-# blaid Premium - more slots and premium-only features. Run `,premium` to buy."


class GetPremiumView(discord.ui.LayoutView):
    def __init__(self, command_name: str | None = None, preselected_plan: str | None = None):
        super().__init__(timeout=180)
        self.preselected_plan = preselected_plan

        get_premium_button = discord.ui.Button(label="Get Premium", style=discord.ButtonStyle.secondary)
        get_premium_button.callback = self._on_get_premium

        container = discord.ui.Container(
            discord.ui.TextDisplay(_gate_text(command_name)),
            discord.ui.Separator(visible=True),
            discord.ui.ActionRow(get_premium_button),
            discord.ui.TextDisplay("-# Pay with card or PayPal"),
        )
        self.add_item(container)

    async def _on_get_premium(self, interaction: discord.Interaction) -> None:
        if self.preselected_plan:
            view = ChoosePlanView(self.preselected_plan)
        else:
            view = ChooseProductView()
        await interaction.response.send_message(view=view, ephemeral=True)


async def send_premium_gate(ctx_or_interaction, command_name: str | None, plan_hint: str | None = None) -> None:
    view = GetPremiumView(command_name=command_name, preselected_plan=plan_hint)
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(view=view, ephemeral=True)
    elif getattr(ctx_or_interaction, "interaction", None) is not None:
        await ctx_or_interaction.send(view=view, ephemeral=True)
    else:
        await ctx_or_interaction.send(view=view)


def command_plan(qualified_name: str) -> str | None:
    """Which plan a premium-gated command belongs to, or None if it
    isn't gated."""
    root = qualified_name.split()[0]
    if qualified_name in PREMIUM_COMMANDS_SERVER or root in PREMIUM_COMMANDS_SERVER:
        return "server"
    if qualified_name in PREMIUM_COMMANDS_CUSTOMIZE or root in PREMIUM_COMMANDS_CUSTOMIZE:
        return "customize"
    return None


# ---------------------------------------------------------- purchase flow (Components V2, each step a fresh ephemeral message)

class ChooseProductView(discord.ui.LayoutView):
    """Step 1 (only reached via bare ,premium / the gate button with no
    plan hint) - pick Server Premium or Customize."""

    def __init__(self):
        super().__init__(timeout=180)

        server_button = discord.ui.Button(label="Server Premium", style=discord.ButtonStyle.secondary)
        server_button.callback = self._on_server
        customize_button = discord.ui.Button(label="Customize", style=discord.ButtonStyle.secondary)
        customize_button.callback = self._on_customize

        container = discord.ui.Container(
            discord.ui.TextDisplay("# Choose what to buy"),
            discord.ui.TextDisplay(
                "**Server Premium** covers everyone here.\n**Customize** unlocks branding for this server."
            ),
            discord.ui.Separator(visible=True),
            discord.ui.ActionRow(server_button, customize_button),
        )
        self.add_item(container)

    async def _on_server(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=ChoosePlanView("server"), ephemeral=True)

    async def _on_customize(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=ChoosePlanView("customize"), ephemeral=True)


class ChoosePlanView(discord.ui.LayoutView):
    """Step 2 - pick monthly/yearly/lifetime for the chosen plan."""

    def __init__(self, plan: str):
        super().__init__(timeout=180)
        self.plan = plan

        select = discord.ui.Select(
            placeholder="Pick a plan",
            options=[
                discord.SelectOption(label=f"{PERIOD_LABELS[period]} - {PRICES[plan][period]}", value=period)
                for period in ("monthly", "yearly", "lifetime")
            ],
        )
        select.callback = self._on_select

        back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        back_button.callback = self._on_back

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# Choose a plan\n-# {PLAN_LABELS[plan]}"),
            discord.ui.TextDisplay("Which plan would you like?"),
            discord.ui.ActionRow(select),
            discord.ui.ActionRow(back_button),
        )
        self.add_item(container)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        period = self._select.values[0]
        await interaction.response.send_message(view=ChoosePaymentView(self.plan, period), ephemeral=True)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=ChooseProductView(), ephemeral=True)


class ChoosePaymentView(discord.ui.LayoutView):
    """Step 3 - pick Card or PayPal."""

    def __init__(self, plan: str, period: str):
        super().__init__(timeout=180)
        self.plan = plan
        self.period = period

        card_button = discord.ui.Button(label="Card", style=discord.ButtonStyle.secondary)
        card_button.callback = self._on_card
        paypal_button = discord.ui.Button(label="PayPal", style=discord.ButtonStyle.secondary)
        paypal_button.callback = self._on_paypal
        back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        back_button.callback = self._on_back

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {PLAN_LABELS[plan]} - {PERIOD_LABELS[period]}"),
            discord.ui.TextDisplay("Pick how you'd like to pay."),
            discord.ui.ActionRow(card_button, paypal_button),
            discord.ui.ActionRow(back_button),
        )
        self.add_item(container)

    async def _on_card(self, interaction: discord.Interaction) -> None:
        await _open_billing_channel(interaction, self.plan, self.period, "card")

    async def _on_paypal(self, interaction: discord.Interaction) -> None:
        await _open_billing_channel(interaction, self.plan, self.period, "paypal")

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=ChoosePlanView(self.plan), ephemeral=True)


# ---------------------------------------------------------- billing channel

async def _open_billing_channel(interaction: discord.Interaction, plan: str, period: str, method: str) -> None:
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message("This has to be done inside a server.", ephemeral=True)
        return

    async with get_session() as session:
        purchase = await premium_repository.create_purchase(session, guild.id, user.id, plan, period)
        purchase = await premium_repository.update_purchase(session, purchase, payment_method=method)

    app_info = await interaction.client.application_info()
    owner_id = app_info.owner.id if app_info.owner else None

    channel_name = f"billing-{user.name}"[:100]
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    owner_member = guild.get_member(owner_id) if owner_id else None
    if owner_member is not None:
        overwrites[owner_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    try:
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites, reason="Premium purchase")
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to create a billing channel here - ask a server admin to grant me Manage Channels.",
            ephemeral=True,
        )
        return

    async with get_session() as session:
        fresh = await premium_repository.get_purchase(session, purchase.id)
        await premium_repository.update_purchase(session, fresh, channel_id=channel.id)

    view = SendPaymentView(purchase.id, plan, period, method)

    owner_ping = f"<@{owner_id}> " if owner_id else ""
    await channel.send(content=f"{user.mention} {owner_ping}".strip())
    await channel.send(view=view)

    await interaction.response.send_message(f"Opened {channel.mention} for you.", ephemeral=True)

    price = PRICES[plan][period]
    await _notify_owner(interaction.client, purchase.id, guild, user, plan, period, price, method)


class SendPaymentView(discord.ui.LayoutView):
    """The billing-channel payment instructions - also Components V2."""

    def __init__(self, purchase_id: int, plan: str, period: str, method: str):
        super().__init__(timeout=None)
        self.purchase_id = purchase_id
        self.method = method

        price = PRICES[plan][period]
        text = (
            f"# Send your payment\n"
            f"**{PLAN_LABELS[plan]} {PERIOD_LABELS[period]}** - {price}\n\n"
            f"Send exactly **{price}**\n\n"
        )
        if method == "paypal":
            text += f"To this address:\n`{PAYMENT_PAYPAL}`"
        else:
            text += f"IBAN:\n`{PAYMENT_IBAN}`"
        text += "\n-# Premium unlocks automatically once the network confirms."

        finished_button = discord.ui.Button(label="Finished Payment", style=discord.ButtonStyle.secondary)
        finished_button.callback = self._on_finished

        container = discord.ui.Container(
            discord.ui.TextDisplay(text),
            discord.ui.Separator(visible=True),
            discord.ui.ActionRow(finished_button),
        )
        self.add_item(container)

    async def _on_finished(self, interaction: discord.Interaction) -> None:
        question = (
            "What's your PayPal address or name?" if self.method == "paypal"
            else "What's your IBAN or name on the account?"
        )
        await interaction.response.send_modal(_PaymentDetailModal(self.purchase_id, question))


class _PaymentDetailModal(discord.ui.Modal):
    def __init__(self, purchase_id: int, question: str):
        super().__init__(title="Payment Details")
        self.purchase_id = purchase_id
        self.answer = discord.ui.TextInput(label=question, required=True, max_length=200)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        purchase = None
        async with get_session() as session:
            purchase = await premium_repository.get_purchase(session, self.purchase_id)
            if purchase is not None:
                purchase = await premium_repository.update_purchase(session, purchase, payment_detail=str(self.answer))

        await interaction.response.send_message(
            "Thanks - the owner has been notified and will review shortly.", ephemeral=True
        )

        if purchase is not None:
            await _notify_owner_form_answer(interaction.client, purchase, str(self.answer))


# ---------------------------------------------------------- approval confirmation

async def send_approval_confirmation(bot, guild_id: int, plan: str) -> bool:
    """Called by ,premium approve - finds the latest pending purchase
    for this guild+plan, marks it approved, and posts a confirmation
    back in its billing channel. Returns False if no pending purchase
    or channel could be found (the caller should fall back to a plain
    success message in that case)."""
    async with get_session() as session:
        purchase = await premium_repository.get_latest_pending_purchase(session, guild_id, plan)
        if purchase is None:
            return False
        purchase = await premium_repository.update_purchase(session, purchase, status="approved")

    if not purchase.channel_id:
        return False

    channel = bot.get_channel(purchase.channel_id)
    if channel is None:
        return False

    guild = channel.guild
    user = guild.get_member(purchase.user_id) if guild else None
    user_mention = user.mention if user else f"<@{purchase.user_id}>"

    price = PRICES[purchase.plan][purchase.billing_period]
    renews_note = (
        "This channel will reopen automatically when it's time to renew."
        if purchase.billing_period != "lifetime"
        else "This is a lifetime purchase - no renewal needed."
    )

    text = (
        f"# Payment confirmed\n"
        f"{PLAN_LABELS[purchase.plan]} - {PERIOD_LABELS[purchase.billing_period]} ({price}) via "
        f"{purchase.payment_method.title() if purchase.payment_method else 'Unknown'}\n\n"
        f"**{guild.name}** now has **{PLAN_LABELS[purchase.plan]}**!\n\n"
        f"You can delete this channel now.\n-# {renews_note}"
    )

    view = _ConfirmationView(text)

    try:
        await channel.send(content=user_mention)
        await channel.send(view=view)
    except discord.HTTPException:
        pass

    return True


class _ConfirmationView(discord.ui.LayoutView):
    def __init__(self, text: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Container(discord.ui.TextDisplay(text)))


async def _notify_owner(bot, purchase_id: int, guild: discord.Guild, user, plan: str, period: str, price: str, method: str) -> None:
    channel = bot.get_channel(OWNER_NOTIFY_CHANNEL_ID)
    if channel is None:
        return

    app_info = await bot.application_info()
    owner_id = app_info.owner.id if app_info.owner else None
    ping = f"<@{owner_id}>" if owner_id else ""

    description = (
        f"**{user}** wants to buy **{PLAN_LABELS[plan]} - {PERIOD_LABELS[period]}** ({price}) via **{method.title()}**.\n\n"
        f"**User** {user} (`{user.id}`)\n"
        f"**Server** {guild.name} (`{guild.id}`)\n"
        f"**Purchase ID** `{purchase_id}`"
    )
    embed = discord.Embed(title="New Premium Purchase", description=description, color=discord.Color.gold())
    try:
        await channel.send(content=ping, embed=embed)
    except discord.HTTPException:
        pass


async def _notify_owner_form_answer(bot, purchase, answer: str) -> None:
    channel = bot.get_channel(OWNER_NOTIFY_CHANNEL_ID)
    if channel is None:
        return

    app_info = await bot.application_info()
    owner_id = app_info.owner.id if app_info.owner else None
    ping = f"<@{owner_id}>" if owner_id else ""

    question = "PayPal address/name" if purchase.payment_method == "paypal" else "IBAN/account name"
    embed = discord.Embed(
        title="Payment Detail Submitted",
        description=f"**Purchase ID** `{purchase.id}`\n**{question}:** {answer}",
        color=discord.Color.gold(),
    )
    try:
        await channel.send(content=ping, embed=embed)
    except discord.HTTPException:
        pass


# ---------------------------------------------------------- renewal reminders

@tasks.loop(hours=12)
async def check_renewals(bot: commands.Bot) -> None:
    async with get_session() as session:
        configs = await premium_repository.get_all_configs(session)

    now = _now()
    soon = now + datetime.timedelta(days=3)

    for cfg in configs:
        guild = bot.get_guild(cfg.guild_id)
        if guild is None:
            continue

        server_expires = _make_aware(cfg.server_premium_expires_at)
        customize_expires = _make_aware(cfg.customize_premium_expires_at)

        if cfg.server_premium and server_expires and now <= server_expires <= soon:
            await _send_renewal_notice(bot, guild, "server")
        if cfg.customize_premium and customize_expires and now <= customize_expires <= soon:
            await _send_renewal_notice(bot, guild, "customize")


async def _send_renewal_notice(bot: commands.Bot, guild: discord.Guild | None, plan: str) -> None:
    """Best-effort: reopens the same billing-channel flow, but there's
    no single 'right' member to notify automatically for a renewal (the
    original purchaser may have left) - this posts in the server's
    system channel as a starting point rather than guessing a DM
    target."""
    if guild is None:
        return
    channel = guild.system_channel
    if channel is None:
        return

    embed = discord.Embed(
        title=f"{PLAN_LABELS[plan]} renewal due soon",
        description=(
            f"This server's **{PLAN_LABELS[plan]}** is about to expire. Run `,premium` to renew and keep your "
            f"current features and limits."
        ),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass
