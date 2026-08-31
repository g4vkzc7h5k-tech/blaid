"""
Chat filter detection.

check_message() is the single entry point, called from an on_message
listener. It checks (in order): whitelist/exempt bypass, custom
words/phrases/regex, then each enabled built-in module. The first
violation found triggers punishment and stops checking further ones
for that message.

HONEST LIMITATIONS: `malicious` and `nsfw` are basic heuristics (a
small built-in domain list / keyword list), not real threat-intel or
image classification - flagged here so it's clear what they actually
are rather than implying more than they do.
"""

from __future__ import annotations

import datetime
import re
import time
from collections import defaultdict

import discord

from database.database import get_session
from repositories import filter_repository

WINDOW_SECONDS = 10

# (guild_id, user_id) -> list[timestamp], for the spam module only.
_spam_log: dict[tuple[int, int], list[float]] = defaultdict(list)

_INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
_LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_SPOILER_RE = re.compile(r"\|\|.*?\|\|")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_UNICODE_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_REPEAT_CHAR_RE = re.compile(r"(.)\1{4,}")  # same char 5+ times in a row

# Basic, non-exhaustive heuristic lists - see module docstring.
_MALICIOUS_DOMAINS = {"grabify.link", "iplogger.org", "bit.ly", "tinyurl.com", "is.gd"}
_NSFW_KEYWORDS = {"porn", "nsfw", "onlyfans", "xvideos", "pornhub"}

_AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma")


async def _get_bypass(message: discord.Message) -> bool:
    member = message.author
    target_ids = [member.id] + [r.id for r in member.roles]
    async with get_session() as session:
        if await filter_repository.is_whitelisted(session, message.guild.id, target_ids):
            return True
        if await filter_repository.is_exempt_channel(session, message.guild.id, message.channel.id):
            return True
    return False


async def _match_custom(guild_id: int, content: str) -> str | None:
    """Returns a human-readable reason string if a custom word/phrase/
    regex matches, else None."""
    lowered = content.lower()
    async with get_session() as session:
        words = await filter_repository.get_words(session, guild_id)

    for word in words:
        if word.kind in ("word", "phrase"):
            if word.value.lower() in lowered:
                return f"filtered {word.kind} `{word.value}`"
        elif word.kind == "regex":
            try:
                if re.search(word.value, content, re.IGNORECASE):
                    return f"filtered pattern `{word.value}`"
            except re.error:
                continue
    return None


async def _check_module(guild_id: int, module_name: str):
    async with get_session() as session:
        module = await filter_repository.get_or_create_module(session, guild_id, module_name)
        if not module.enabled:
            return None
    return module


async def check_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
        return

    if await _get_bypass(message):
        return

    content = message.content or ""

    # Custom words/phrases/regex - checked regardless of the "regex"
    # module toggle, since word/phrase filtering is the core feature.
    # Punishment for these comes from FilterConfig.default_punishment,
    # set via ,filter punishment - custom entries don't have their own
    # per-entry punishment the way the 14 toggle modules do.
    reason = await _match_custom(message.guild.id, content)
    if reason:
        async with get_session() as session:
            cfg = await filter_repository.get_or_create_config(session, message.guild.id)
        await _trigger(message, reason, cfg.default_punishment)
        return

    checks = [
        ("links", _check_links),
        ("invites", _check_invites),
        ("massmention", _check_massmention),
        ("caps", _check_caps),
        ("spam", _check_spam),
        ("emoji", _check_emoji),
        ("spoilers", _check_spoilers),
        ("walloftext", _check_walloftext),
        ("repetition", _check_repetition),
        ("musicfiles", _check_musicfiles),
        ("images", _check_images),
        ("malicious", _check_malicious),
        ("nsfw", _check_nsfw),
    ]

    for module_name, check_fn in checks:
        module = await _check_module(message.guild.id, module_name)
        if module is None:
            continue
        if await check_fn(message, module.threshold):
            await _trigger(message, f"triggered `{module_name}` filter", module.punishment)
            return


async def _trigger(message: discord.Message, reason: str, punishment: str = "delete") -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        pass

    async with get_session() as session:
        strikes = await filter_repository.add_strike(session, message.guild.id, message.author.id)

    if punishment == "delete":
        return

    try:
        if punishment == "warn":
            await message.channel.send(
                f"{message.author.mention} your message was removed ({reason}). Strikes: `{strikes}`.",
                delete_after=8,
            )
        elif punishment == "timeout":
            until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
            await message.author.timeout(until, reason=f"Chat filter: {reason}")
        elif punishment == "kick":
            await message.author.kick(reason=f"Chat filter: {reason}")
        elif punishment == "ban":
            await message.author.ban(reason=f"Chat filter: {reason}")
    except discord.Forbidden:
        pass


# ---------------------------------------------------------- module checks

async def _check_links(message: discord.Message, _threshold: int) -> bool:
    return bool(_LINK_RE.search(message.content or ""))


async def _check_invites(message: discord.Message, _threshold: int) -> bool:
    return bool(_INVITE_RE.search(message.content or ""))


async def _check_massmention(message: discord.Message, threshold: int) -> bool:
    total_mentions = len(message.mentions) + len(message.role_mentions)
    return total_mentions >= max(1, threshold)


async def _check_caps(message: discord.Message, threshold: int) -> bool:
    content = message.content or ""
    letters = [c for c in content if c.isalpha()]
    if len(letters) < 8:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
    return upper_ratio >= max(10, threshold)


async def _check_spam(message: discord.Message, threshold: int) -> bool:
    key = (message.guild.id, message.author.id)
    now = time.time()
    _spam_log[key] = [t for t in _spam_log[key] if now - t < WINDOW_SECONDS]
    _spam_log[key].append(now)
    return len(_spam_log[key]) >= max(2, threshold)


async def _check_emoji(message: discord.Message, threshold: int) -> bool:
    content = message.content or ""
    count = len(_CUSTOM_EMOJI_RE.findall(content)) + len(_UNICODE_EMOJI_RE.findall(content))
    return count >= max(1, threshold)


async def _check_spoilers(message: discord.Message, threshold: int) -> bool:
    count = len(_SPOILER_RE.findall(message.content or ""))
    return count >= max(1, threshold)


async def _check_walloftext(message: discord.Message, threshold: int) -> bool:
    return len(message.content or "") >= max(200, threshold)


async def _check_repetition(message: discord.Message, _threshold: int) -> bool:
    return bool(_REPEAT_CHAR_RE.search(message.content or ""))


async def _check_musicfiles(message: discord.Message, _threshold: int) -> bool:
    return any(a.filename.lower().endswith(_AUDIO_EXTENSIONS) for a in message.attachments)


async def _check_images(message: discord.Message, _threshold: int) -> bool:
    return any((a.content_type or "").startswith("image/") for a in message.attachments)


async def _check_malicious(message: discord.Message, _threshold: int) -> bool:
    content = (message.content or "").lower()
    return any(domain in content for domain in _MALICIOUS_DOMAINS)


async def _check_nsfw(message: discord.Message, _threshold: int) -> bool:
    content = (message.content or "").lower()
    return any(keyword in content for keyword in _NSFW_KEYWORDS)


# ---------------------------------------------------------- native Discord AutoMod sync

async def sync_custom_automod_rule(guild: discord.Guild) -> tuple[bool, str]:
    """Creates or updates the ONE native Discord AutoMod rule that holds
    every custom word/phrase/regex entry, so matches get the real
    "Uses AutoMod" badge and show up in Server Settings > AutoMod.

    This is the newest, least battle-tested part of discord.py's API
    surface - if a method/attribute name below doesn't match the
    installed discord.py version, this fails gracefully (caught below)
    and the bot-side check_message() deletion keeps working as a
    fallback either way, so filtering never actually breaks.
    """
    if guild.me is None or not guild.me.guild_permissions.manage_guild:
        return False, "I need the Manage Server permission to create AutoMod rules."

    async with get_session() as session:
        cfg = await filter_repository.get_or_create_config(session, guild.id)
        words = await filter_repository.get_words(session, guild.id)

    # Discord's keyword_filter does whole-word matching unless wrapped
    # in wildcards - *word* gives the same "anywhere in the message"
    # behavior the old bot-side substring check had.
    keyword_entries = [f"*{w.value}*" for w in words if w.kind in ("word", "phrase")][:1000]
    regex_entries = [w.value for w in words if w.kind == "regex"][:10]
    enabled = bool(keyword_entries or regex_entries)

    try:
        actions = [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)]
        if cfg.default_punishment == "timeout":
            actions.append(
                discord.AutoModRuleAction(
                    type=discord.AutoModRuleActionType.timeout,
                    duration=datetime.timedelta(minutes=10),
                )
            )

        trigger = discord.AutoModTrigger(keyword_filter=keyword_entries, regex_patterns=regex_entries)

        rule = None
        if cfg.automod_rule_id is not None:
            try:
                existing_rules = await guild.fetch_automod_rules()
            except AttributeError:
                existing_rules = await guild.automod_rules()  # older/alternate discord.py naming
            rule = discord.utils.get(existing_rules, id=cfg.automod_rule_id)

        if rule is not None:
            await rule.edit(trigger=trigger, actions=actions, enabled=enabled, reason="Blaid chat filter sync")
        elif enabled:
            new_rule = await guild.create_automod_rule(
                name="Blaid - Chat Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions,
                enabled=True,
                reason="Blaid chat filter sync",
            )
            async with get_session() as session:
                fresh_cfg = await filter_repository.get_or_create_config(session, guild.id)
                fresh_cfg.automod_rule_id = new_rule.id
                await session.commit()
    except discord.HTTPException as exc:
        return False, f"Discord rejected the AutoMod rule update: {exc}"
    except (AttributeError, TypeError) as exc:
        return False, f"AutoMod API mismatch on this discord.py version ({exc}) - filtering still works bot-side."

    return True, "Synced to a native Discord AutoMod rule."


# ---------------------------------------------------------- nicknames (separate listener)

async def check_nickname(member: discord.Member) -> None:
    """Call from on_member_update - resets a nickname that matches a
    filtered word/phrase/regex, if the nicknames module is enabled."""
    if member.nick is None:
        return

    module = await _check_module(member.guild.id, "nicknames")
    if module is None:
        return

    reason = await _match_custom(member.guild.id, member.nick)
    if reason is None:
        return

    try:
        await member.edit(nick=None, reason=f"Chat filter: nickname {reason}")
    except discord.Forbidden:
        pass
