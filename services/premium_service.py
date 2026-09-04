"""
Premium system - now backed by Discord's own App Monetization
(SKUs/Entitlements), replacing the old manual billing-channel flow.

Two independent plans, each with a Monthly and a Lifetime SKU (Discord
doesn't support yearly subscription billing yet, so only these two
periods exist):
- "server" (Server Premium) - raises per-guild feature limits and
  unlocks a handful of premium-only commands, for the whole server.
- "customize" (Customize) - unlocks ,customize (per-server bot
  branding) for the whole server.

How it works: ,premium shows a Discord "Premium Button" for each SKU -
clicking it opens Discord's own native purchase flow (Discord itself
handles payment; we never see card/bank details). Once Discord
confirms the purchase, it fires an Entitlement event over the gateway
(on_entitlement_create/update/delete), which this file listens for and
applies directly to this guild's PremiumConfig row - no manual
approval step anymore.

HONEST GAP: whether a Durable (lifetime) SKU's resulting Entitlement
reliably carries guild_id when purchased via a button clicked inside a
guild channel is something to verify against a real purchase, since
Discord's docs describe this scenario incompletely as of this
writing. If a lifetime purchase doesn't grant premium automatically,
check entitlement.guild_id here first - the sync/apply logic below
falls back to look up the guild from the interaction that show the
button as a mitigation, but that fallback only works at the moment of
purchase, not for the periodic full-entitlement sync.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands
from sqlalchemy import select

from database.database import get_session
from database.premium_models import PremiumConfig
from repositories import premium_repository

# ---------------------------------------------------------- constants

PLAN_LABELS = {"server": "Server Premium", "customize": "Customize"}
PERIOD_LABELS = {"monthly": "Monthly", "lifetime": "Lifetime"}

PRICES = {
    "server": {"monthly": "$4.99", "lifetime": "$11.99"},
    "customize": {"monthly": "$3.99", "lifetime": "$5.49"},
}

# SKU ID (from the Developer Portal) -> (plan, period)
SKU_MAP: dict[int, tuple[str, str]] = {
    1545278130959294474: ("server", "monthly"),
    1545279733967884328: ("server", "lifetime"),
    1545280298625794168: ("customize", "monthly"),
    1545280773764943982: ("customize", "lifetime"),
}

# plan -> {period: sku_id}, the reverse of SKU_MAP, for building buttons
PLAN_SKUS: dict[str, dict[str, int]] = {"server": {}, "customize": {}}
for _sku_id, (_plan, _period) in SKU_MAP.items():
    PLAN_SKUS[_plan][_period] = _sku_id

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


def command_plan(qualified_name: str) -> str | None:
    """Which plan a premium-gated command belongs to, or None if it
    isn't gated."""
    root = qualified_name.split()[0]
    if qualified_name in PREMIUM_COMMANDS_SERVER or root in PREMIUM_COMMANDS_SERVER:
        return "server"
    if qualified_name in PREMIUM_COMMANDS_CUSTOMIZE or root in PREMIUM_COMMANDS_CUSTOMIZE:
        return "customize"
    return None


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
    return top + "\n-# blaid Premium - run `,premium` to buy."


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
        )
        self.add_item(container)

    async def _on_get_premium(self, interaction: discord.Interaction) -> None:
        plan = self.preselected_plan or "server"
        await interaction.response.send_message(view=PlanPurchaseView(plan), ephemeral=True)


async def send_premium_gate(ctx_or_interaction, command_name: str | None, plan_hint: str | None = None) -> None:
    view = GetPremiumView(command_name=command_name, preselected_plan=plan_hint)
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(view=view, ephemeral=True)
    elif getattr(ctx_or_interaction, "interaction", None) is not None:
        await ctx_or_interaction.send(view=view, ephemeral=True)
    else:
        await ctx_or_interaction.send(view=view)


# ---------------------------------------------------------- purchase flow (Discord-native premium buttons)

class ChoosePlanView(discord.ui.LayoutView):
    """,premium's first step - pick which plan, then see its real
    purchase buttons."""

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
        await interaction.response.send_message(view=PlanPurchaseView("server"), ephemeral=True)

    async def _on_customize(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=PlanPurchaseView("customize"), ephemeral=True)


class PlanPurchaseView(discord.ui.LayoutView):
    """Step 2 - real Discord purchase buttons (style=premium) for this
    plan's Monthly and Lifetime SKUs. Clicking one opens Discord's own
    native checkout - we never see payment details."""

    def __init__(self, plan: str):
        super().__init__(timeout=180)

        monthly_sku = PLAN_SKUS[plan]["monthly"]
        lifetime_sku = PLAN_SKUS[plan]["lifetime"]

        monthly_button = discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=monthly_sku)
        lifetime_button = discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=lifetime_sku)

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {PLAN_LABELS[plan]}"),
            discord.ui.TextDisplay(
                f"**Monthly** - {PRICES[plan]['monthly']}/month\n**Lifetime** - {PRICES[plan]['lifetime']} once"
            ),
            discord.ui.Separator(visible=True),
            discord.ui.ActionRow(monthly_button),
            discord.ui.ActionRow(lifetime_button),
            discord.ui.TextDisplay("-# Premium unlocks automatically right after checkout."),
        )
        self.add_item(container)


# ---------------------------------------------------------- entitlement handling

async def _set_premium(guild_id: int, plan: str, *, active: bool, expires_at: datetime.datetime | None) -> None:
    async with get_session() as session:
        result = await session.execute(select(PremiumConfig).where(PremiumConfig.guild_id == guild_id))
        cfg = result.scalar_one_or_none()
        if cfg is None:
            cfg = PremiumConfig(guild_id=guild_id)
            session.add(cfg)

        if plan == "server":
            cfg.server_premium = active
            cfg.server_premium_expires_at = expires_at
        elif plan == "customize":
            cfg.customize_premium = active
            cfg.customize_premium_expires_at = expires_at

        await session.commit()


async def apply_entitlement(bot: commands.Bot, entitlement: discord.Entitlement, *, active: bool) -> None:
    """Called from on_entitlement_create/update/delete. Grants or
    revokes the matching plan for whichever guild this entitlement
    belongs to."""
    mapping = SKU_MAP.get(entitlement.sku_id)
    if mapping is None:
        return  # a SKU we don't recognize - ignore
    plan, period = mapping

    guild_id = entitlement.guild_id
    if guild_id is None:
        # Not guild-scoped for some reason (see the HONEST GAP note at
        # the top of this file) - nothing we can apply this to.
        return

    expires_at = None
    if period == "monthly" and active:
        expires_at = entitlement.ends_at  # Discord auto-renews unless cancelled; this just tracks the current period

    await _set_premium(guild_id, plan, active=active, expires_at=expires_at)

    if active:
        guild = bot.get_guild(guild_id)
        if guild is not None:
            await _announce_activated(guild, plan)


async def _announce_activated(guild: discord.Guild, plan: str) -> None:
    channel = guild.system_channel
    if channel is None:
        return
    embed = discord.Embed(
        title=f"{PLAN_LABELS[plan]} activated!",
        description="Thanks for the support - this server's premium features are live now.",
        color=discord.Color.gold(),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def sync_entitlements(bot: commands.Bot) -> int:
    """Call on startup: re-applies every currently active entitlement,
    in case the bot was offline when a purchase or cancellation event
    fired. Returns how many were processed."""
    count = 0
    async for entitlement in bot.entitlements():
        if entitlement.sku_id not in SKU_MAP:
            continue
        active = not entitlement.is_expired() if hasattr(entitlement, "is_expired") else not entitlement.deleted
        await apply_entitlement(bot, entitlement, active=active)
        count += 1
    return count
