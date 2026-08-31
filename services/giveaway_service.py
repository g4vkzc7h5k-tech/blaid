"""
Giveaway business logic: the entry/participants buttons, embed
building, weighted winner selection (via per-role max-entries),
blacklist enforcement, DM preferences, and restart-resume /
edit-reschedule timers so nothing gets lost or left stale.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

import discord

from config import config
from database.database import get_session
from database.giveaway_models import Giveaway
from repositories import giveaway_repository

# giveaway_id -> asyncio.Task, so editing the duration can cancel and
# reschedule the exact task that would otherwise fire at the old time.
_scheduled_tasks: dict[int, asyncio.Task] = {}


def _schedule(bot: discord.Client, giveaway_id: int, delay_seconds: float) -> None:
    existing = _scheduled_tasks.get(giveaway_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _scheduled_tasks[giveaway_id] = bot.loop.create_task(_schedule_end(bot, giveaway_id, delay_seconds))


async def _schedule_end(bot: discord.Client, giveaway_id: int, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
    except asyncio.CancelledError:
        return  # rescheduled - a new task now owns this giveaway
    await end_giveaway(bot, giveaway_id)


# ---------------------------------------------------------- embed building

async def build_giveaway_view(guild: discord.Guild, giveaway: Giveaway) -> "GiveawayEntryView":
    async with get_session() as session:
        template = await giveaway_repository.get_template(session, guild.id)
        entry_count = await giveaway_repository.count_entries(session, giveaway.id)

    title = "{prize} Giveaway"
    intro = "Click the \U0001f389 button to enter the giveaway"
    color = discord.Color.blurple()

    if template is not None:
        if template.title:
            title = template.title
        if template.description:
            intro = template.description
        if template.color:
            try:
                color = discord.Color(int(template.color.lstrip("#"), 16))
            except ValueError:
                pass

    title = title.replace("{prize}", giveaway.prize)
    intro = (giveaway.description or intro).replace("{prize}", giveaway.prize)

    lines = [intro, "___"]
    lines.append(
        f"**Ends:** <t:{int(giveaway.ends_at.timestamp())}:R> "
        f"(<t:{int(giveaway.ends_at.timestamp())}:F>)"
    )
    lines.append(f"**Entries**: {entry_count}")
    lines.append(f"**Hosted By** <@{giveaway.host_id}>")

    if config.topgg_vote_url:
        lines.append("")
        lines.append(f"Vote for 1.5x entries: {config.topgg_vote_url}")

    body = "\n".join(lines)
    return GiveawayEntryView(giveaway.id, title=title, body=body, color=color)


async def refresh_giveaway_message(bot: discord.Client, giveaway: Giveaway) -> None:
    """Re-fetches and edits the live giveaway message - used after an
    entry, an edit, or an end/reroll so the panel always reflects the
    current state."""
    if giveaway.message_id is None:
        return
    channel = bot.get_channel(giveaway.channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(giveaway.message_id)
    except discord.HTTPException:
        return

    view = await build_giveaway_view(channel.guild, giveaway)
    try:
        await message.edit(view=view)
    except discord.HTTPException:
        pass


# ---------------------------------------------------------- views

class GiveawayEntryView(discord.ui.LayoutView):
    """Components V2 layout - title/body text and both buttons live
    inside one seamless container, matching ,invite's look. This is
    genuinely newer discord.py API surface (2.6+) I haven't been able
    to test live - if the container errors or renders oddly, that's
    the first thing to check. `title`/`body` default to empty because
    cog_load re-registers this on restart with only the giveaway_id
    (for button-routing on the already-sent message) - it never
    actually needs to re-render text in that case."""

    def __init__(self, giveaway_id: int, title: str = "", body: str = "", color: discord.Color | None = None):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        enter_button = discord.ui.Button(
            label="Enter Giveaway", emoji="\U0001f389",
            style=discord.ButtonStyle.primary,
            custom_id=f"blade_giveaway_entry:{giveaway_id}",
        )
        enter_button.callback = self._enter
        self.enter_button = enter_button

        participants_button = discord.ui.Button(
            label="View Participants", style=discord.ButtonStyle.secondary,
            custom_id=f"blade_giveaway_participants:{giveaway_id}",
        )
        participants_button.callback = self._view_participants
        self.participants_button = participants_button

        components = []
        if title:
            components.append(discord.ui.TextDisplay(f"# {title}"))
        if body:
            components.append(discord.ui.TextDisplay(body))
        components.append(discord.ui.ActionRow(enter_button, participants_button))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def _enter(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            giveaway = await giveaway_repository.get_giveaway(session, self.giveaway_id)
            if giveaway is None or giveaway.ended:
                await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
                return

            blacklisted_roles = await giveaway_repository.get_blacklisted_roles(session, interaction.guild.id)

        member_role_ids = {r.id for r in interaction.user.roles} if isinstance(interaction.user, discord.Member) else set()
        if member_role_ids & set(blacklisted_roles):
            await interaction.response.send_message(
                "You have a role that's blocked from entering giveaways.", ephemeral=True
            )
            return

        async with get_session() as session:
            added = await giveaway_repository.add_entry(session, self.giveaway_id, interaction.user.id)

        message = "You're entered! Good luck." if added else "You're already entered."
        await interaction.response.send_message(message, ephemeral=True)

        if added:
            await refresh_giveaway_message(interaction.client, giveaway)

    async def _view_participants(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            entries = await giveaway_repository.get_entries(session, self.giveaway_id)

        if not entries:
            await interaction.response.send_message("No one has entered yet.", ephemeral=True)
            return

        shown = entries[:50]
        lines = "\n".join(f"<@{uid}>" for uid in shown)
        suffix = f"\n...and {len(entries) - 50} more." if len(entries) > 50 else ""
        await interaction.response.send_message(
            f"**Participants ({len(entries)}):**\n{lines}{suffix}", ephemeral=True
        )


# ---------------------------------------------------------- weighted winner selection

async def _weighted_winners(guild: discord.Guild, entrant_ids: list[int], winner_count: int) -> list[int]:
    """Members with a role configured via ,giveaway setmax get that
    many entries (weight) in the draw instead of just one."""
    async with get_session() as session:
        role_max = await giveaway_repository.get_role_max_entries(session, guild.id)

    weighted_pool: list[int] = []
    for user_id in entrant_ids:
        member = guild.get_member(user_id)
        weight = 1
        if member is not None and role_max:
            applicable = [role_max[r.id] for r in member.roles if r.id in role_max]
            if applicable:
                weight = max(applicable)
        weighted_pool.extend([user_id] * max(1, weight))

    winners: list[int] = []
    pool = weighted_pool[:]
    remaining_unique = set(entrant_ids)

    while pool and len(winners) < winner_count and remaining_unique:
        pick = random.choice(pool)
        if pick not in winners:
            winners.append(pick)
            remaining_unique.discard(pick)
        pool = [uid for uid in pool if uid != pick]

    return winners


# ---------------------------------------------------------- DM helpers

async def _dm_creator(bot: discord.Client, giveaway: Giveaway, winners: list[int]) -> None:
    async with get_session() as session:
        settings = await giveaway_repository.get_or_create_user_settings(session, giveaway.host_id)
    if not settings.dm_on_creator_end:
        return

    user = bot.get_user(giveaway.host_id) or await bot.fetch_user(giveaway.host_id)
    if user is None:
        return

    if winners:
        text = f"Your giveaway for **{giveaway.prize}** has ended. Winner(s): " + ", ".join(f"<@{w}>" for w in winners)
    else:
        text = f"Your giveaway for **{giveaway.prize}** has ended with no valid entries."

    try:
        await user.send(text)
    except discord.HTTPException:
        pass


async def _dm_winners(bot: discord.Client, giveaway: Giveaway, winners: list[int]) -> None:
    for winner_id in winners:
        async with get_session() as session:
            settings = await giveaway_repository.get_or_create_user_settings(session, winner_id)
        if not settings.dm_on_winner:
            continue

        user = bot.get_user(winner_id) or await bot.fetch_user(winner_id)
        if user is None:
            continue
        try:
            await user.send(f"\U0001f389 You won **{giveaway.prize}**!")
        except discord.HTTPException:
            pass


# ---------------------------------------------------------- lifecycle

async def start_giveaway(
    channel: discord.TextChannel, host: discord.Member, prize: str, winner_count: int, duration_seconds: int, bot: discord.Client
) -> Giveaway:
    ends_at_dt = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + duration_seconds, tz=timezone.utc)

    async with get_session() as session:
        giveaway = await giveaway_repository.create_giveaway(
            session,
            guild_id=channel.guild.id,
            channel_id=channel.id,
            host_id=host.id,
            prize=prize,
            winner_count=winner_count,
            ends_at=ends_at_dt,
        )

    view = await build_giveaway_view(channel.guild, giveaway)
    message = await channel.send(view=view)

    async with get_session() as session:
        await giveaway_repository.set_message_id(session, giveaway, message.id)

    _schedule(bot, giveaway.id, duration_seconds)
    return giveaway


async def end_giveaway(bot: discord.Client, giveaway_id: int) -> list[int]:
    async with get_session() as session:
        giveaway = await giveaway_repository.get_giveaway(session, giveaway_id)
        if giveaway is None or giveaway.ended:
            return []
        entries = await giveaway_repository.get_entries(session, giveaway_id)
        await giveaway_repository.mark_ended(session, giveaway)

    guild = bot.get_guild(giveaway.guild_id)
    channel = bot.get_channel(giveaway.channel_id)

    winners = await _weighted_winners(guild, entries, giveaway.winner_count) if guild and entries else []

    if channel is not None:
        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            await channel.send(f"\U0001f389 Congratulations {mentions}! You won **{giveaway.prize}**.")
        else:
            await channel.send(f"No valid entries for **{giveaway.prize}** - no winner could be selected.")

    if guild is not None:
        await refresh_giveaway_message(bot, giveaway)
        await _dm_creator(bot, giveaway, winners)
        await _dm_winners(bot, giveaway, winners)

    return winners


async def reroll_giveaway(bot: discord.Client, giveaway_id: int) -> list[int]:
    async with get_session() as session:
        giveaway = await giveaway_repository.get_giveaway(session, giveaway_id)
        if giveaway is None:
            return []
        entries = await giveaway_repository.get_entries(session, giveaway_id)

    guild = bot.get_guild(giveaway.guild_id)
    channel = bot.get_channel(giveaway.channel_id)
    winners = await _weighted_winners(guild, entries, giveaway.winner_count) if guild and entries else []

    if channel is not None and winners:
        mentions = ", ".join(f"<@{w}>" for w in winners)
        await channel.send(f"\U0001f389 New winner(s) for **{giveaway.prize}**: {mentions}!")

    if guild is not None and winners:
        await _dm_winners(bot, giveaway, winners)

    return winners


async def resume_active_giveaways(bot: discord.Client) -> int:
    async with get_session() as session:
        active = await giveaway_repository.get_active_giveaways(session)

    now = datetime.now(timezone.utc)
    resumed = 0
    for giveaway in active:
        ends_at = giveaway.ends_at
        if ends_at.tzinfo is None:
            # SQLite doesn't actually preserve tz-awareness even with
            # DateTime(timezone=True) - values always come back naive
            # from the driver, so treat a naive read as UTC (the zone
            # every datetime in this app is written in).
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        remaining = (ends_at - now).total_seconds()
        _schedule(bot, giveaway.id, max(0, remaining))
        resumed += 1

    return resumed


# ---------------------------------------------------------- editing an active giveaway

async def edit_giveaway(
    bot: discord.Client,
    giveaway_id: int,
    *,
    duration_seconds: int | None = None,
    description: str | None = None,
    prize: str | None = None,
    winner_count: int | None = None,
) -> Giveaway | None:
    async with get_session() as session:
        giveaway = await giveaway_repository.get_giveaway(session, giveaway_id)
        if giveaway is None or giveaway.ended:
            return None

        fields = {}
        if description is not None:
            fields["description"] = description
        if prize is not None:
            fields["prize"] = prize
        if winner_count is not None:
            fields["winner_count"] = max(1, min(winner_count, 20))
        if duration_seconds is not None:
            fields["ends_at"] = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + duration_seconds, tz=timezone.utc
            )

        giveaway = await giveaway_repository.update_giveaway(session, giveaway, **fields)

    if duration_seconds is not None:
        _schedule(bot, giveaway.id, duration_seconds)

    await refresh_giveaway_message(bot, giveaway)
    return giveaway