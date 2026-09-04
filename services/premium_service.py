"""
Premium system - TEMPORARILY DISABLED. The bot is fully free for now
while premium purchasing gets rebuilt (Discord App Monetization SKUs
are set up but not yet purchasable - see the "Product unavailable"
issue reported to Discord Developer Support).

is_premium() always returns True and check_limit() never blocks
anything, so every feature limit and every premium-gated command
behaves as if every server already has Server Premium + Customize -
this is the single choke point every other file's premium check
funnels through, so nothing else needs to change to make the bot
fully free.

To bring premium back later: revert is_premium/check_limit to their
real logic (compare against PremiumConfig), and re-enable the
Premium cog (cogs.premium.premium) in core/bot.py's INITIAL_COGS.
"""

from __future__ import annotations

# feature -> (free_limit, premium_limit) - kept for reference/when
# premium comes back; unused while everything is free.
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


def get_limit(feature: str, is_premium: bool) -> int:
    _free_limit, premium_limit = LIMITS[feature]
    return premium_limit  # everyone gets the premium limit while this is disabled


async def check_limit(guild_id: int, feature: str, current_count: int) -> tuple[bool, int]:
    """Premium disabled - always allowed."""
    limit = get_limit(feature, True)
    return True, limit


def limit_reached_message(feature_label: str, limit: int, is_premium: bool) -> str:
    return f"You've reached the limit of **{limit}** {feature_label}."


async def is_premium(guild_id: int, plan: str) -> bool:
    """Premium disabled - everyone has every plan for now."""
    return True


def command_plan(qualified_name: str) -> str | None:
    """No commands are gated while premium is disabled."""
    return None
