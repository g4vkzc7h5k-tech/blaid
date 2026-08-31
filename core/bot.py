"""Blade bot subclass."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from config import config
from core.context import BladeContext
from core.errors import handle_command_error

log = logging.getLogger("blade.bot")

INITIAL_COGS = [
    "cogs.moderation.moderation",
    "cogs.fun.fun",
    "cogs.levels.levels",
    "cogs.tickets.tickets",
    "cogs.voicemaster.voicemaster",
    "cogs.welcome.welcome",
    "cogs.boost.boost",
    "cogs.leave.leave",
    "cogs.logging.logging_cog",
    "cogs.utility.utility",
    "cogs.setup.setup_cog",
    "cogs.help.help_cog",
    "cogs.security.security",
    "cogs.roles.roles",
    "cogs.automod.automod",
    "cogs.giveaway.giveaway",
    "cogs.aliases.aliases",
    "cogs.music.music",
    "cogs.embeds.embeds",
    "cogs.boosterrole.boosterrole",
    "cogs.antiraid.antiraid",
    "cogs.economy.economy",
    "cogs.socials.socials",
    "cogs.twitch.twitch",
    "cogs.youtube.youtube",
    "cogs.pingonjoin.pingonjoin",
    "cogs.premium.premium",
    "cogs.schedule.schedule",
    "cogs.lastfm.lastfm",
    "cogs.autopfp.autopfp",
    "cogs.autoreact.autoreact",
    "cogs.backup.backup",
    "cogs.joindm.joindm",
    "cogs.vanity.vanity",
    "cogs.badge.badge",
    "cogs.commandtoggle.commandtoggle",
]


async def _get_prefix(bot: "Blade", message: discord.Message):
    if message.guild is None:
        base_prefix = config.default_prefix
    else:
        base_prefix = bot.guild_prefixes.get(message.guild.id, config.default_prefix)

    prefixes = [base_prefix]
    personal = bot.user_prefixes.get(message.author.id)
    if personal and personal not in prefixes:
        prefixes.append(personal)

    return commands.when_mentioned_or(*prefixes)(bot, message)


class Blade(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        intents.presences = True

        super().__init__(
            command_prefix=_get_prefix,
            intents=intents,
            help_command=None,  # replaced by cogs.help.help_cog
            owner_ids=set(config.owner_ids),
        )

        # guild_id -> prefix, populated from the database on_ready / on_guild_join
        self.guild_prefixes: dict[int, str] = {}
        # user_id -> personal prefix (,prefix self set), works across every server
        self.user_prefixes: dict[int, str] = {}
        self.started_at = discord.utils.utcnow()

    async def get_context(self, message, *, cls=BladeContext):
        return await super().get_context(message, cls=cls)

    async def setup_hook(self) -> None:
        for extension in INITIAL_COGS:
            try:
                await self.load_extension(extension)
                log.info("Loaded cog: %s", extension)
            except Exception:
                log.exception("Failed to load cog: %s", extension)

        log.info("Loaded %d commands total.", len(self.commands))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        from services.onboarding_service import handle_guild_join
        await handle_guild_join(self, guild)

    async def on_ready(self) -> None:
        log.info("Blade is online as %s (%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(activity=discord.Game(name=f"{config.default_prefix}help"))

        await self._load_guild_prefixes()
        await self._load_user_prefixes()

        from services.giveaway_service import resume_active_giveaways
        resumed = await resume_active_giveaways(self)
        if resumed:
            log.info("Resumed %d active giveaway(s).", resumed)

        from services.moderation_service import resume_jails
        resumed_jails = await resume_jails(self)
        if resumed_jails:
            log.info("Resumed %d timed jail(s).", resumed_jails)

        if not self._status_writer.is_running():
            self._status_writer.start()

    @tasks.loop(seconds=60)
    async def _status_writer(self) -> None:
        from services.status_service import write_status
        write_status(self)

    async def _load_guild_prefixes(self) -> None:
        from sqlalchemy import select

        from database.database import get_session
        from database.models import Guild as GuildModel

        async with get_session() as session:
            result = await session.execute(select(GuildModel))
            for row in result.scalars().all():
                self.guild_prefixes[row.guild_id] = row.prefix

    async def _load_user_prefixes(self) -> None:
        from sqlalchemy import select

        from database.database import get_session
        from database.models import UserPrefix

        async with get_session() as session:
            result = await session.execute(select(UserPrefix))
            for row in result.scalars().all():
                self.user_prefixes[row.user_id] = row.prefix

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild is not None and self.user is not None and message.content.strip() in (f"<@{self.user.id}>", f"<@!{self.user.id}>"):
            ctx = await self.get_context(message)
            from services.prefix_service import send_prefix_info
            await send_prefix_info(ctx)
            return

        if message.guild is not None:
            content = await self._resolve_alias(message)
            if content is not None:
                message.content = content

        await self.process_commands(message)

    async def _resolve_alias(self, message: discord.Message) -> str | None:
        """Returns rewritten message content if the first word after the
        prefix matches a registered alias, else None (leave unchanged)."""
        prefix = self.guild_prefixes.get(message.guild.id, config.default_prefix)
        if not message.content.startswith(prefix):
            return None

        rest = message.content[len(prefix):]
        if not rest:
            return None

        parts = rest.split()
        alias_name, remaining = parts[0], parts[1:]

        from services import alias_service
        resolved = await alias_service.resolve(message.guild.id, alias_name, remaining)
        if resolved is None:
            return None

        return f"{prefix}{resolved}"

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        await handle_command_error(ctx, error)
