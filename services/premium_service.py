"""
Premium system - backed by Discord's own App Monetization
(SKUs/Entitlements).

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

CONFIRMED (via live test purchase): a Durable (Lifetime) SKU's
resulting Entitlement always has guild_id=None - Discord scopes
one-time purchases to the purchasing USER, never to a guild, even
when bought from a button inside a server. Guild Subscription
(Monthly) entitlements DO carry guild_id directly, no issue there.
The fix: record_purchase_intent() is called from ,premium right
before showing the purchase buttons, remembering which guild the user
was in; apply_entitlement() falls back to that when guild_id is
missing. This is an in-memory, best-effort mapping (see its docstring
for the exact tradeoff) - it does NOT help sync_entitlements() on
startup, since a restart loses the in-memory intent. If a lifetime
purchase's entitlement is picked up by the startup sync rather than
the live gateway event (e.g. the bot was offline at purchase time)
and its guild_id is still None with no intent on file, it won't
auto-apply - the owner-only ,premium approve command exists for
exactly this kind of manual fix-up.
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
        if interaction.guild_id is not None:
            record_purchase_intent(interaction.user.id, interaction.guild_id)
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
                "**Server Premium** covers everyone here.\n**Customize** unlocks branding for this server.\n\n"
                "-# Purchasing only works on Discord web or desktop right now, not the mobile app."
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
            discord.ui.TextDisplay("-# Premium unlocks automatically right after checkout. Purchasing only works on Discord web or desktop, not mobile."),
        )
        self.add_item(container)


# ---------------------------------------------------------- entitlement handling

# user_id -> (guild_id, recorded_at) - remembers which server someone
# ran ,premium in most recently. Needed because a Durable (Lifetime)
# purchase's resulting Entitlement is scoped to the USER, never the
# guild (confirmed via live testing - Discord's own behavior, not a
# bug here), unlike a Guild Subscription (Monthly) entitlement which
# does carry guild_id directly. This is an in-memory best-effort
# fallback - if the bot restarts between someone running ,premium and
# completing checkout, the intent is lost and they'd need to run
# ,premium again before buying.
_pending_purchase_intent: dict[int, tuple[int, datetime.datetime]] = {}

# How long a recorded intent stays valid - generous, since someone
# might sit on the purchase screen for a while before paying.
_INTENT_TTL = datetime.timedelta(hours=1)


def record_purchase_intent(user_id: int, guild_id: int) -> None:
    """Call this right when ,premium is run in a guild, before showing
    the purchase buttons."""
    _pending_purchase_intent[user_id] = (guild_id, _now())


def _consume_purchase_intent(user_id: int) -> int | None:
    entry = _pending_purchase_intent.get(user_id)
    if entry is None:
        return None
    guild_id, recorded_at = entry
    if _now() - recorded_at > _INTENT_TTL:
        _pending_purchase_intent.pop(user_id, None)
        return None
    return guild_id

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
    import logging
    log = logging.getLogger("blade.premium")
    log.info(
        "Entitlement event: sku_id=%s guild_id=%s user_id=%s active=%s ends_at=%s",
        entitlement.sku_id, entitlement.guild_id, entitlement.user_id, active,
        getattr(entitlement, "ends_at", None),
    )

    mapping = SKU_MAP.get(entitlement.sku_id)
    if mapping is None:
        log.warning("Entitlement sku_id %s not in SKU_MAP - ignoring.", entitlement.sku_id)
        return  # a SKU we don't recognize - ignore
    plan, period = mapping

    guild_id = entitlement.guild_id
    if guild_id is None:
        # Durable (Lifetime) purchases are user-scoped, not
        # guild-scoped - fall back to whichever guild this user most
        # recently ran ,premium in.
        guild_id = _consume_purchase_intent(entitlement.user_id)

    if guild_id is None:
        log.warning(
            "Entitlement for sku_id %s (plan=%s) has no guild_id and no recent ,premium "
            "intent on file for user_id=%s - cannot grant premium. They may need to run "
            "`,premium` again in the target server before purchasing.",
            entitlement.sku_id, plan, entitlement.user_id,
        )
        return


    expires_at = None
    if period == "monthly" and active:
        expires_at = entitlement.ends_at  # Discord auto-renews unless cancelled; this just tracks the current period

    await _set_premium(guild_id, plan, active=active, expires_at=expires_at)
    log.info("Applied %s premium (active=%s) to guild %s", plan, active, guild_id)

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
