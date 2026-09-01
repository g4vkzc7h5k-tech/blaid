"""
Polls the website backend's /api/tickets/pending queue every 30s and
builds the requested panel/options/forms using the exact same
repositories ,tickets panel/,tickets options/,tickets forms use - so a
panel built on the website behaves identically to one built with
commands.

Why polling instead of the website calling the bot directly: the
website backend (Render) and the bot (PebbleHost) are on separate
hosts that can't reach each other's database or filesystem, and the
bot can't accept inbound connections the way it's hosted - but it can
always make outbound HTTP requests, which is what this does.

Needs config.website_api_url and config.bot_api_token (same
BOT_API_TOKEN env var set on the backend's host).
"""

from __future__ import annotations

import logging

import aiohttp
import discord

from config import config
from database.database import get_session
from repositories import ticket_forms_repository, ticket_options_repository, ticket_repository

log = logging.getLogger("blade.website_tickets")

TIMEOUT = aiohttp.ClientTimeout(total=20)


async def poll_and_build(bot: discord.Client) -> None:
    if not config.website_api_url or not config.bot_api_token:
        return

    headers = {"x-bot-token": config.bot_api_token}
    base = config.website_api_url.rstrip("/")

    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(f"{base}/api/tickets/pending", headers=headers, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
    except (aiohttp.ClientError, TimeoutError):
        return

    for item in data.get("items", []):
        guild_id = int(item["request"]["guild_id"])
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue  # not our guild (or bot isn't in it) - leave pending for now

        try:
            await _build_panel(guild, item["request"])
        except Exception:
            log.exception("Failed to build ticket panel for guild %s from website queue", guild_id)
            continue  # leave it pending rather than silently losing the request

        try:
            async with aiohttp.ClientSession() as http:
                await http.post(
                    f"{base}/api/tickets/pending/{item['id']}/complete", headers=headers, timeout=TIMEOUT
                )
        except (aiohttp.ClientError, TimeoutError):
            pass


async def _build_panel(guild: discord.Guild, request: dict) -> None:
    from services.ticket_service import build_panel_view

    panel_data = request["panel"]
    channel = guild.get_channel(int(panel_data["channel_id"]))
    if channel is None:
        return

    # --- 1. Create the panel with its channel, then apply every other setting
    async with get_session() as session:
        panel = await ticket_repository.create_panel(
            session, guild_id=guild.id, channel_id=channel.id, title=panel_data["title"],
        )
        await ticket_repository.update_panel(
            session, panel,
            description=panel_data.get("description") or None,
            button_label=panel_data.get("button_label") or "Open Ticket",
            log_channel_id=_as_int(panel_data.get("log_channel_id")),
            category_id=_as_int(panel_data.get("category_id")),
            closed_category_id=_as_int(panel_data.get("closed_category_id")),
            delete_delay_seconds=panel_data.get("delete_delay_seconds", 0),
            max_open_tickets=panel_data.get("max_open_tickets", 1),
            auto_pin_controls=panel_data.get("auto_pin_controls", False),
            claims_enabled=panel_data.get("claims_enabled", True),
            logs_enabled=panel_data.get("logs_enabled", False),
            log_message_template=panel_data.get("log_message_template") or None,
            channel_name_format=panel_data.get("channel_name_format") or "{ticket.case}-{ticket.author.name}",
            case_padding=panel_data.get("case_padding", 0),
            dropdown_placeholder=panel_data.get("dropdown_placeholder") or None,
            mode=panel_data.get("mode", "dropdown"),
        )
        panel_id = panel.id

    # --- 2. Create every form, tracking temp key -> real form_id
    form_key_to_id: dict[str, int] = {}
    for form_data in request.get("forms", []):
        async with get_session() as session:
            form = await ticket_forms_repository.create_form(
                session, guild.id, form_data["name"], form_data["modal_title"], form_data.get("enable_filtering", False),
            )
            for field in form_data.get("fields", []):
                await ticket_forms_repository.add_field(
                    session, form.id,
                    field_type=field["field_type"],
                    label=field["label"],
                    description=field.get("description"),
                    key=field.get("key"),
                    required=field.get("required", True),
                )
        form_key_to_id[form_data["key"]] = form.id

    # --- 3. Create every option with its full settings
    for option_data in request.get("options", []):
        async with get_session() as session:
            option = await ticket_options_repository.create_option(
                session, guild.id, panel_id,
                option_data["name"], option_data["label"], option_data.get("emoji"),
            )
            await ticket_options_repository.update_option(
                session, option,
                button_style=option_data.get("button_style", "blue"),
                button_description=option_data.get("button_description"),
                default_category_id=_as_int(option_data.get("default_category_id")),
                claim_category_id=_as_int(option_data.get("claim_category_id")),
                close_category_id=_as_int(option_data.get("close_category_id")),
                transcript_channel_id=_as_int(option_data.get("transcript_channel_id")),
                channel_name_format=option_data.get("channel_name_format") or "{ticket.case}-{ticket.author.name}",
                claim_rename_template=option_data.get("claim_rename_template"),
                close_rename_template=option_data.get("close_rename_template"),
                creator_can_close=option_data.get("creator_can_close", True),
                close_on_leave=option_data.get("close_on_leave", False),
                require_all_roles=option_data.get("require_all_roles", False),
                keep_staff_visible_on_claim=option_data.get("keep_staff_visible_on_claim", True),
                staff_can_speak_on_claim=option_data.get("staff_can_speak_on_claim", True),
                trainees_can_claim=option_data.get("trainees_can_claim", False),
                trainees_can_close=option_data.get("trainees_can_close", False),
                trainees_can_speak=option_data.get("trainees_can_speak", False),
                auto_close_timer=option_data.get("auto_close_timer"),
                auto_delete_timer=option_data.get("auto_delete_timer"),
                inactivity_timer=option_data.get("inactivity_timer"),
                form_id=form_key_to_id.get(option_data.get("form_key")),
            )

            for role_id in option_data.get("required_role_ids", []):
                await ticket_options_repository.add_required_role(session, option.id, int(role_id))
            for role_id in option_data.get("support_role_ids", []):
                await ticket_options_repository.add_support_role(session, option.id, int(role_id))
            for role_id in option_data.get("trainee_role_ids", []):
                await ticket_options_repository.add_trainee_role(session, option.id, int(role_id))

            for action, cfg in option_data.get("button_configs", {}).items():
                await ticket_options_repository.set_button_config(
                    session, option.id, action,
                    label=cfg.get("label", action.title()),
                    emoji=cfg.get("emoji"),
                    color=cfg.get("color", "gray"),
                    requires_reason=cfg.get("requires_reason", False),
                )

            for message_type, content in option_data.get("messages", {}).items():
                await ticket_options_repository.set_message(session, option.id, message_type, content)

    # --- 4. Send the actual panel message, using the correct view for however
    # many options ended up configured (0 = plain button, 1 = single styled
    # button, 2+ = dropdown/buttons per panel.mode)
    embed = discord.Embed(title=panel_data["title"], description=panel_data.get("description") or None)
    view = await build_panel_view(panel_id)
    message = await channel.send(embed=embed, view=view)

    async with get_session() as session:
        fresh = await ticket_repository.get_panel(session, panel_id)
        await ticket_repository.update_panel(session, fresh, message_id=message.id, channel_id=channel.id)


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
