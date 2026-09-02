"""
Generates website/backend/data/commands.json from the bot's actual
command_meta registry - and exposes build_commands_payload() for
main.py to call directly at startup, so the live API never depends on
this file being run manually at all.

Optional manual run (still useful for local inspection or a static
fallback file):

    python website/backend/command_export.py

It imports every cog module directly (not through bot.load_extension,
so no Discord token or connection is needed - command_meta decorators
run at class-definition time, which is import time). This is the
mechanism that keeps the website's docs from ever drifting out of
sync with the real bot: the website reads the same registry the bot's
,help command reads, never a hand-maintained copy.

IMPORTANT: every new cog module must be added to COG_MODULES below,
or the website's Commands page will simply never see its commands -
this list is the one place that has to be kept in sync manually.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

COG_MODULES = [
    "cogs.aliases.aliases",
    "cogs.antiraid.antiraid",
    "cogs.automod.automod",
    "cogs.autopfp.autopfp",
    "cogs.autoreact.autoreact",
    "cogs.avatarfx.avatarfx",
    "cogs.backup.backup",
    "cogs.badge.badge",
    "cogs.boost.boost",
    "cogs.boosterrole.boosterrole",
    "cogs.commandtoggle.commandtoggle",
    "cogs.economy.economy",
    "cogs.embeds.embeds",
    "cogs.fun.fun",
    "cogs.giveaway.giveaway",
    "cogs.help.help_cog",
    "cogs.joindm.joindm",
    "cogs.lastfm.lastfm",
    "cogs.leave.leave",
    "cogs.levels.levels",
    "cogs.logging.logging_cog",
    "cogs.moderation.moderation",
    "cogs.music.music",
    "cogs.pingonjoin.pingonjoin",
    "cogs.premium.premium",
    "cogs.roles.roles",
    "cogs.schedule.schedule",
    "cogs.security.security",
    "cogs.setup.setup_cog",
    "cogs.socials.socials",
    "cogs.tickets.tickets",
    "cogs.twitch.twitch",
    "cogs.utility.utility",
    "cogs.vanity.vanity",
    "cogs.voicemaster.voicemaster",
    "cogs.welcome.welcome",
    "cogs.youtube.youtube",
]

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "commands.json")


def build_commands_payload() -> list[dict]:
    """Imports every cog module and returns the current command_meta
    registry as a plain list of dicts - shared by both this script's
    manual export and main.py's automatic startup load."""
    import importlib

    for module_name in COG_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # a cog with a broken import shouldn't kill the whole export
            print(f"WARNING: could not import {module_name}: {exc}", file=sys.stderr)

    from core.command_meta import registry

    commands_payload = [
        {
            "name": meta.name,
            "category": meta.category,
            "description": meta.description,
            "syntax": meta.syntax,
            "examples": meta.examples,
            "permissions": meta.permissions,
            "aliases": meta.aliases,
        }
        for meta in registry.all()
    ]
    commands_payload.sort(key=lambda c: (c["category"], c["name"]))
    return commands_payload


def main() -> None:
    commands_payload = build_commands_payload()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(commands_payload, f, indent=2)

    print(f"Exported {len(commands_payload)} commands to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
