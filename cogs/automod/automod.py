"""
Automod: autorole, autoresponders, and the chat filter.

Autorole used to live under the Roles category alongside reaction/
button roles - it's split out here into its own Automod category.
Reaction roles and button roles stay in cogs/roles/roles.py.

The chat filter (,filter / ,chatfilter) lives here too since it's
conceptually an automod feature, even though its command_meta category
is "Security" per the requested footer.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.checks import has_permission_or_fake
from core.command_meta import command_meta
from core.help_formatter import send_help
from core.paginator import Paginator
from database.database import get_session
from database.filter_models import FILTER_MODULES, FILTER_PUNISHMENTS
from repositories import automod_repository, filter_repository, roles_repository
from services import filter_service, premium_service
from services.roles_service import apply_autoroles

FILTER_FLAGS = [
    ("--do (punishment)", "Set punishment type: delete, warn, timeout, kick, ban"),
    ("--threshold (number)", "Sensitivity threshold (meaning varies per module)"),
]

# A short, deliberately mild starter list for ,filter wordmigrate -
# not a comprehensive profanity filter, just a customizable example set.
# Use ,filter add/blacklist/regex to add anything more specific.
_PRESET_WORDS = ["damn", "hell", "crap", "stupid", "idiot", "shut up", "dumb", "moron"]


def _parse_filter_flags(rest: str) -> dict:
    tokens = rest.split()
    result = {"status": None, "do": None, "threshold": None}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--do" and i + 1 < len(tokens):
            result["do"] = tokens[i + 1].lower()
            i += 2
        elif tok == "--threshold" and i + 1 < len(tokens):
            result["threshold"] = tokens[i + 1]
            i += 2
        elif not tok.startswith("--") and result["status"] is None:
            result["status"] = tok.lower()
            i += 1
        else:
            i += 1
    return result


async def _sync_and_report(ctx: commands.Context) -> None:
    """Runs the native AutoMod sync and, only on failure, sends a
    follow-up warning explaining why - so a missing bot permission or
    an API mismatch doesn't fail silently and leave someone wondering
    why no rule showed up in Server Settings > AutoMod."""
    success, message = await filter_service.sync_custom_automod_rule(ctx.guild)
    if not success:
        await ctx.warn(f"Filter list updated, but the native AutoMod rule didn't sync: {message}")


async def _run_filter_module_command(ctx: commands.Context, module_name: str, rest: str) -> None:
    flags = _parse_filter_flags(rest)
    detail_parts = []

    async with get_session() as session:
        module = await filter_repository.get_or_create_module(session, ctx.guild.id, module_name)
        any_change = False

        if flags["status"] is not None:
            if flags["status"] in ("on", "enable", "enabled", "true"):
                module = await filter_repository.update_module(session, module, enabled=True)
                any_change = True
            elif flags["status"] in ("off", "disable", "disabled", "false"):
                module = await filter_repository.update_module(session, module, enabled=False)
                any_change = True
            else:
                await ctx.error(f"Status must be `on` or `off`, not `{flags['status']}`.")
                return

        if flags["do"] is not None:
            if flags["do"] not in FILTER_PUNISHMENTS:
                await ctx.error(f"Punishment must be one of: {', '.join(FILTER_PUNISHMENTS)}.")
                return
            module = await filter_repository.update_module(session, module, punishment=flags["do"])
            detail_parts.append(f"Punishment is set to **{flags['do']}**")
            any_change = True

        if flags["threshold"] is not None:
            try:
                threshold_value = max(1, int(flags["threshold"]))
            except ValueError:
                await ctx.error("Threshold must be a number.")
                return
            module = await filter_repository.update_module(session, module, threshold=threshold_value)
            detail_parts.append(f"threshold is set to **{threshold_value}**")
            any_change = True

    if not any_change:
        embed = discord.Embed(
            title=f"Filter â {module_name}",
            description=(
                f"Status: **{'Enabled' if module.enabled else 'Disabled'}**\n"
                f"Punishment: `{module.punishment}`\n"
                f"Threshold: `{module.threshold}`"
            ),
        )
        await ctx.send(embed=embed)
        return

    message = f"{ctx.author.mention}: Updated **{module_name}** filter module."
    if detail_parts:
        if len(detail_parts) == 1:
            message += f" {detail_parts[0]}."
        else:
            message += f" {' and '.join(detail_parts)}."

    await ctx.success(message)


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await apply_autoroles(member)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content:
            return

        async with get_session() as session:
            responder = await automod_repository.get_responder(session, message.guild.id, message.content.strip())
            if responder is None:
                return
            allowed_role_ids = await automod_repository.get_role_restrictions(session, responder.id)

        if allowed_role_ids:
            member_role_ids = {r.id for r in message.author.roles} if isinstance(message.author, discord.Member) else set()
            if not member_role_ids & set(allowed_role_ids):
                return

        try:
            await message.channel.send(responder.response)
        except discord.HTTPException:
            pass

    @commands.Cog.listener(name="on_message")
    async def on_message_filter_check(self, message: discord.Message):
        await filter_service.check_message(message)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            await filter_service.check_nickname(after)

    @command_meta(
        category="Server",
        description="Adds a role that every new member automatically receives on join.",
        syntax=",autorole add <role>",
        examples=[",autorole add @Member"],
        permissions=["Manage Roles"],
    )
    @commands.group(name="autorole", invoke_without_command=True)
    @commands.guild_only()
    @has_permission_or_fake("manage_roles")
    async def autorole(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @autorole.command(name="add")
    @has_permission_or_fake("manage_roles")
    async def autorole_add(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            existing = await roles_repository.get_autoroles(session, ctx.guild.id)
            allowed, limit = await premium_service.check_limit(ctx.guild.id, "autorole", len(existing))
            if not allowed:
                is_prem = await premium_service.is_premium(ctx.guild.id, "server")
                await ctx.error(premium_service.limit_reached_message("autoroles", limit, is_prem))
                return
            await roles_repository.add_autorole(session, ctx.guild.id, role.id)
        await ctx.success(f"{role.mention} will now be given to new members automatically.")

    @command_meta(
        category="Security",
        description="Removes a role from autorole.",
        syntax=",autorole remove <role>",
        examples=[",autorole remove @Member"],
        permissions=["Manage Roles"],
    )
    @autorole.command(name="remove")
    @has_permission_or_fake("manage_roles")
    async def autorole_remove(self, ctx: commands.Context, role: discord.Role):
        async with get_session() as session:
            removed = await roles_repository.remove_autorole(session, ctx.guild.id, role.id)
        if removed:
            await ctx.success(f"{role.mention} removed from autorole.")
        else:
            await ctx.error(f"{role.mention} was not an autorole.")

    @command_meta(
        category="Security",
        description="Lists all configured autoroles.",
        syntax=",autorole list",
        examples=[",autorole list"],
        require_args=False,
    )
    @autorole.command(name="list")
    async def autorole_list(self, ctx: commands.Context):
        async with get_session() as session:
            autoroles = await roles_repository.get_autoroles(session, ctx.guild.id)
        if not autoroles:
            await ctx.info("No autoroles configured.")
            return
        await ctx.send("\n".join(f"<@&{a.role_id}>" for a in autoroles))

    @command_meta(
        category="Security",
        description="Removes every configured autorole.",
        syntax=",autorole clear",
        examples=[",autorole clear"],
        permissions=["Manage Roles"],
        require_args=False,
    )
    @autorole.command(name="clear")
    @has_permission_or_fake("manage_roles")
    async def autorole_clear(self, ctx: commands.Context):
        async with get_session() as session:
            autoroles = await roles_repository.get_autoroles(session, ctx.guild.id)
            for a in autoroles:
                await roles_repository.remove_autorole(session, ctx.guild.id, a.role_id)
        await ctx.success(f"Cleared {len(autoroles)} autorole(s).")

    @command_meta(
        category="Server",
        description="Creates or manages autoresponders - triggers Blaid replies to automatically.",
        syntax=",autoresponder add <trigger> | <response>",
        examples=[",autoresponder add !rules | Check out #rules"],
        permissions=["Manage Guild"],
        aliases=["ar"],
    )
    @commands.group(name="autoresponder", aliases=["ar"], invoke_without_command=True)
    @commands.guild_only()
    @has_permission_or_fake("manage_guild")
    async def autoresponder(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @autoresponder.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_add(self, ctx: commands.Context, *, config: str):
        trigger, _, response = config.partition("|")
        trigger, response = trigger.strip(), response.strip()
        if not trigger or not response:
            await ctx.error("Format: `,autoresponder add <trigger> | <response>`")
            return

        async with get_session() as session:
            existing = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if existing is not None:
                await ctx.error(f"An autoresponder for `{trigger}` already exists. Use `,autoresponder update` instead.")
                return

            current = await automod_repository.get_all_responders(session, ctx.guild.id)
            allowed, limit = await premium_service.check_limit(ctx.guild.id, "autoresponder", len(current))
            if not allowed:
                is_prem = await premium_service.is_premium(ctx.guild.id, "server")
                await ctx.error(premium_service.limit_reached_message("autoresponders", limit, is_prem))
                return

            await automod_repository.create_responder(session, ctx.guild.id, trigger, response)

        await ctx.success(f"Autoresponder added: `{trigger}` â {response}")

    @command_meta(
        category="Security",
        description="Updates the response for an existing autoresponder trigger.",
        syntax=",autoresponder update <trigger> | <new response>",
        examples=[",autoresponder update !rules | See #server-rules"],
        permissions=["Manage Guild"],
    )
    @autoresponder.command(name="update")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_update(self, ctx: commands.Context, *, config: str):
        trigger, _, response = config.partition("|")
        trigger, response = trigger.strip(), response.strip()
        if not trigger or not response:
            await ctx.error("Format: `,autoresponder update <trigger> | <new response>`")
            return

        async with get_session() as session:
            existing = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if existing is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            await automod_repository.update_response(session, existing, response)

        await ctx.success(f"Autoresponder `{trigger}` updated.")

    @command_meta(
        category="Security",
        description="Removes an autoresponder trigger.",
        syntax=",autoresponder remove <trigger>",
        examples=[",autoresponder remove !rules"],
        permissions=["Manage Guild"],
    )
    @autoresponder.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_remove(self, ctx: commands.Context, *, trigger: str):
        trigger = trigger.strip()
        async with get_session() as session:
            existing = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if existing is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            await automod_repository.delete_responder(session, existing)
        await ctx.success(f"Autoresponder `{trigger}` removed.")

    @command_meta(
        category="Security",
        description="Lists every autoresponder configured in this server.",
        syntax=",autoresponder list",
        examples=[",autoresponder list"],
        require_args=False,
    )
    @autoresponder.command(name="list")
    async def autoresponder_list(self, ctx: commands.Context):
        async with get_session() as session:
            responders = await automod_repository.get_all_responders(session, ctx.guild.id)
        if not responders:
            await ctx.info("No autoresponders configured.")
            return
        lines = [f"`{r.trigger}` â {r.response}" for r in responders]
        await ctx.send(embed=discord.Embed(title="Autoresponders", description="\n".join(lines)[:4000]))

    @command_meta(
        category="Security",
        description="Deletes every autoresponder configured in this server.",
        syntax=",autoresponder reset",
        examples=[",autoresponder reset"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @autoresponder.command(name="reset")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_reset(self, ctx: commands.Context):
        async with get_session() as session:
            await automod_repository.delete_all_responders(session, ctx.guild.id)
        await ctx.success("All autoresponders have been reset.")

    @command_meta(
        category="Security",
        description="Restricts an autoresponder trigger to specific roles, or removes an existing restriction.",
        syntax=",autoresponder role add <trigger> <role>",
        examples=[",autoresponder role add !rules @Member"],
        permissions=["Manage Guild"],
    )
    @autoresponder.group(name="role", invoke_without_command=True)
    @has_permission_or_fake("manage_guild")
    async def autoresponder_role(self, ctx: commands.Context):
        await send_help(ctx, ctx.command.qualified_name)

    @autoresponder_role.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_role_add(self, ctx: commands.Context, trigger: str, role: discord.Role):
        async with get_session() as session:
            responder = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if responder is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            await automod_repository.add_role_restriction(session, responder.id, role.id)
        await ctx.success(f"`{trigger}` is now restricted to include {role.mention}.")

    @command_meta(
        category="Security",
        description="Removes a role restriction from an autoresponder trigger.",
        syntax=",autoresponder role remove <trigger> <role>",
        examples=[",autoresponder role remove !rules @Member"],
        permissions=["Manage Guild"],
    )
    @autoresponder_role.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_role_remove(self, ctx: commands.Context, trigger: str, role: discord.Role):
        async with get_session() as session:
            responder = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if responder is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            removed = await automod_repository.remove_role_restriction(session, responder.id, role.id)
        if removed:
            await ctx.success(f"{role.mention} removed from `{trigger}`'s role restrictions.")
        else:
            await ctx.error(f"{role.mention} was not restricting `{trigger}`.")

    @command_meta(
        category="Security",
        description="Lists the roles currently restricting an autoresponder trigger.",
        syntax=",autoresponder role list <trigger>",
        examples=[",autoresponder role list !rules"],
    )
    @autoresponder_role.command(name="list")
    async def autoresponder_role_list(self, ctx: commands.Context, *, trigger: str):
        async with get_session() as session:
            responder = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if responder is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            role_ids = await automod_repository.get_role_restrictions(session, responder.id)

        if not role_ids:
            await ctx.info(f"`{trigger}` has no role restrictions - everyone can trigger it.")
            return
        await ctx.send("\n".join(f"<@&{rid}>" for rid in role_ids))

    @command_meta(
        category="Security",
        description="Clears all role restrictions from an autoresponder trigger, so everyone can trigger it again.",
        syntax=",autoresponder clear <trigger>",
        examples=[",autoresponder clear !rules"],
        permissions=["Manage Guild"],
    )
    @autoresponder.command(name="clear")
    @has_permission_or_fake("manage_guild")
    async def autoresponder_clear(self, ctx: commands.Context, *, trigger: str):
        async with get_session() as session:
            responder = await automod_repository.get_responder(session, ctx.guild.id, trigger)
            if responder is None:
                await ctx.error(f"No autoresponder found for `{trigger}`.")
                return
            await automod_repository.clear_role_restrictions(session, responder.id)
        await ctx.success(f"Cleared role restrictions for `{trigger}`.")

    # ---------------------------------------------------------- ,filter root

    @command_meta(
        category="Security",
        description="Configures the chat filter - custom words/phrases/patterns, whitelist, and 14 built-in detection modules.",
        syntax=",filter",
        examples=[],
        permissions=["Manage Guild"],
        aliases=["chatfilter"],
        require_args=False,
    )
    @commands.group(name="filter", aliases=["chatfilter"], invoke_without_command=True)
    @commands.guild_only()
    async def filter_group(self, ctx: commands.Context):
        await send_help(ctx, "filter")

    @filter_group.command(name="help")
    async def filter_help(self, ctx: commands.Context):
        await send_help(ctx, "filter")

    # ---------------------------------------------------------- words / phrases / regex

    @command_meta(
        category="Security",
        description="Adds a word to the filter - any message containing it is deleted.",
        syntax=",filter add <word>",
        examples=[",filter add badword"],
        permissions=["Manage Guild"],
        aliases=["chatfilter add"],
    )
    @filter_group.command(name="add")
    @has_permission_or_fake("manage_guild")
    async def filter_add(self, ctx: commands.Context, *, word: str):
        word = word.strip().lower()
        async with get_session() as session:
            added = await filter_repository.add_word(session, ctx.guild.id, word, "word")
        if added:
            await ctx.success(f"{ctx.author.mention}: Added `{word}` to the filter list.")
            await _sync_and_report(ctx)
        else:
            await ctx.error(f"`{word}` is already filtered.")

    @command_meta(
        category="Security",
        description="Removes a word from the filter.",
        syntax=",filter remove <word>",
        examples=[",filter remove badword"],
        permissions=["Manage Guild"],
        aliases=["chatfilter remove"],
    )
    @filter_group.command(name="remove")
    @has_permission_or_fake("manage_guild")
    async def filter_remove(self, ctx: commands.Context, *, word: str):
        word = word.strip().lower()
        async with get_session() as session:
            removed = await filter_repository.remove_word(session, ctx.guild.id, word, "word")
        if removed:
            await ctx.success(f"{ctx.author.mention}: Removed `{word}` from the filter list.")
            await _sync_and_report(ctx)
        else:
            await ctx.error(f"`{word}` was not filtered.")

    @command_meta(
        category="Security",
        description="Lists every filtered word, phrase, and regex pattern.",
        syntax=",filter list",
        examples=[",filter list"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @filter_group.command(name="list")
    @has_permission_or_fake("manage_guild")
    async def filter_list(self, ctx: commands.Context):
        async with get_session() as session:
            words = await filter_repository.get_words(session, ctx.guild.id)

        if not words:
            await ctx.info("No filtered words, phrases, or patterns configured.")
            return

        lines = [f"**{w.value}**" for w in words]
        chunks = [lines[i:i + 15] for i in range(0, len(lines), 15)]
        pages = []
        for chunk in chunks:
            embed = discord.Embed(title="Filtered Keywords", description="\n".join(chunk))
            embed.set_footer(text=f"{len(words)} entries")
            pages.append(embed)

        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)

    @command_meta(
        category="Security",
        description="Removes every filtered word, phrase, and regex pattern.",
        syntax=",filter clear",
        examples=[",filter clear"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @filter_group.command(name="clear")
    @has_permission_or_fake("manage_guild")
    async def filter_clear(self, ctx: commands.Context):
        async with get_session() as session:
            count = await filter_repository.clear_words(session, ctx.guild.id)
        await ctx.success(f"{ctx.author.mention}: Cleared {count} entr{'y' if count == 1 else 'ies'} from the filter list.")
        await _sync_and_report(ctx)

    @command_meta(
        category="Security",
        description="Adds a multi-word phrase to the filter (matched as a substring, unlike single-word add).",
        syntax=",filter blacklist <phrase>",
        examples=[",filter blacklist some bad phrase"],
        permissions=["Manage Guild"],
    )
    @filter_group.command(name="blacklist")
    @has_permission_or_fake("manage_guild")
    async def filter_blacklist(self, ctx: commands.Context, *, phrase: str):
        phrase = phrase.strip().lower()
        async with get_session() as session:
            added = await filter_repository.add_word(session, ctx.guild.id, phrase, "phrase")
        if added:
            await ctx.success(f"{ctx.author.mention}: Added `{phrase}` to the filter list.")
            await _sync_and_report(ctx)
        else:
            await ctx.error(f"`{phrase}` is already filtered.")

    @command_meta(
        category="Security",
        description="Adds a custom regex pattern to the filter.",
        syntax=",filter regex <pattern>",
        examples=[",filter regex \\\\bfree.?nitro\\\\b"],
        permissions=["Manage Guild"],
    )
    @filter_group.command(name="regex")
    @has_permission_or_fake("manage_guild")
    async def filter_regex(self, ctx: commands.Context, *, pattern: str):
        pattern = pattern.strip()
        import re as _re
        try:
            _re.compile(pattern)
        except _re.error as exc:
            await ctx.error(f"Invalid regex pattern: {exc}")
            return
        async with get_session() as session:
            added = await filter_repository.add_word(session, ctx.guild.id, pattern, "regex")
        if added:
            await ctx.success(f"{ctx.author.mention}: Added `{pattern}` to the filter list.")
            await _sync_and_report(ctx)
        else:
            await ctx.error("That pattern is already filtered.")

    # ---------------------------------------------------------- whitelist / exempt / punishment / settings

    @command_meta(
        category="Security",
        description="Toggles a user or role's exemption from the filter.",
        syntax=",filter whitelist <user|role>",
        examples=[",filter whitelist @Staff"],
        permissions=["Manage Guild"],
    )
    @filter_group.command(name="whitelist", with_app_command=False)
    @has_permission_or_fake("manage_guild")
    async def filter_whitelist(self, ctx: commands.Context, target: discord.Member | discord.Role):
        target_type = "user" if isinstance(target, discord.Member) else "role"
        async with get_session() as session:
            already = await filter_repository.is_whitelisted(session, ctx.guild.id, [target.id])
            if already:
                await filter_repository.remove_whitelist(session, ctx.guild.id, target.id)
            else:
                await filter_repository.add_whitelist(session, ctx.guild.id, target.id, target_type)

        if already:
            await ctx.success(f"{target.mention} removed from the filter whitelist.")
        else:
            await ctx.success(f"{target.mention} is now exempt from the filter.")

    @command_meta(
        category="Security",
        description="Toggles a channel's exemption from the filter.",
        syntax=",filter exempt <channel>",
        examples=[",filter exempt #general"],
        permissions=["Manage Guild"],
    )
    @filter_group.command(name="exempt")
    @has_permission_or_fake("manage_guild")
    async def filter_exempt(self, ctx: commands.Context, channel: discord.TextChannel):
        async with get_session() as session:
            already = await filter_repository.is_exempt_channel(session, ctx.guild.id, channel.id)
            if already:
                await filter_repository.remove_exempt_channel(session, ctx.guild.id, channel.id)
            else:
                await filter_repository.add_exempt_channel(session, ctx.guild.id, channel.id)

        if already:
            await ctx.success(f"{channel.mention} removed from filter exemptions.")
        else:
            await ctx.success(f"{channel.mention} is now exempt from the filter.")

    @command_meta(
        category="Security",
        description="Sets the punishment applied when a custom word/phrase/regex match triggers.",
        syntax=",filter punishment <type>",
        examples=[",filter punishment timeout"],
        permissions=["Manage Guild"],
        flags=[("delete, warn, timeout, kick, ban", "Valid punishment types")],
    )
    @filter_group.command(name="punishment")
    @has_permission_or_fake("manage_guild")
    async def filter_punishment(self, ctx: commands.Context, punishment: str):
        punishment = punishment.lower()
        if punishment not in FILTER_PUNISHMENTS:
            await ctx.error(f"Punishment must be one of: {', '.join(FILTER_PUNISHMENTS)}.")
            return
        async with get_session() as session:
            cfg = await filter_repository.get_or_create_config(session, ctx.guild.id)
            cfg.default_punishment = punishment
            await session.commit()
        await ctx.success(f"Default filter punishment set to **{punishment}**.")
        await _sync_and_report(ctx)

    @command_meta(
        category="Security",
        description="Shows the full chat filter configuration.",
        syntax=",filter settings",
        examples=[",filter settings"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @filter_group.command(name="settings")
    @has_permission_or_fake("manage_guild")
    async def filter_settings(self, ctx: commands.Context):
        async with get_session() as session:
            cfg = await filter_repository.get_or_create_config(session, ctx.guild.id)
            modules = await filter_repository.get_all_modules(session, ctx.guild.id)
            words = await filter_repository.get_words(session, ctx.guild.id)

        lines = [f"Default Punishment: **{cfg.default_punishment}**", f"Filtered Entries: **{len(words)}**", ""]
        for name in FILTER_MODULES:
            module = modules.get(name)
            if module is None or not module.enabled:
                lines.append(f"ð´ **{name}** â disabled")
            else:
                lines.append(f"ð¢ **{name}** â `{module.punishment}` at `{module.threshold}`")

        embed = discord.Embed(title="Chat Filter Settings", description="\n".join(lines)[:4000])
        await ctx.send(embed=embed)

    @command_meta(
        category="Security",
        description="Bulk-adds a short starter set of filtered words. Use ,filter add/blacklist/regex for anything more specific.",
        syntax=",filter wordmigrate",
        examples=[",filter wordmigrate"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @filter_group.command(name="wordmigrate")
    @has_permission_or_fake("manage_guild")
    async def filter_wordmigrate(self, ctx: commands.Context):
        added = 0
        async with get_session() as session:
            for word in _PRESET_WORDS:
                if await filter_repository.add_word(session, ctx.guild.id, word, "word", is_preset=True):
                    added += 1
        await ctx.success(f"Added {added} preset word(s) to the filter.")
        await _sync_and_report(ctx)

    @command_meta(
        category="Security",
        description="Removes only the preset words added by ,filter wordmigrate, leaving manually-added entries untouched.",
        syntax=",filter unmigrate",
        examples=[",filter unmigrate"],
        permissions=["Manage Guild"],
        require_args=False,
    )
    @filter_group.command(name="unmigrate")
    @has_permission_or_fake("manage_guild")
    async def filter_unmigrate(self, ctx: commands.Context):
        async with get_session() as session:
            count = await filter_repository.remove_preset_words(session, ctx.guild.id)
        await ctx.success(f"Removed {count} preset word(s) from the filter.")
        await _sync_and_report(ctx)

    @command_meta(
        category="Security",
        description="Shows (or resets) a member's filter strike count.",
        syntax=",filter strikes <user> [reset]",
        examples=[",filter strikes @User", ",filter strikes @User reset"],
        permissions=["Manage Guild"],
    )
    @filter_group.command(name="strikes")
    @has_permission_or_fake("manage_guild")
    async def filter_strikes(self, ctx: commands.Context, user: discord.Member, action: str = None):
        async with get_session() as session:
            if action and action.lower() == "reset":
                await filter_repository.reset_strikes(session, ctx.guild.id, user.id)
                await ctx.success(f"Reset filter strikes for {user.mention}.")
                return
            count = await filter_repository.get_strikes(session, ctx.guild.id, user.id)
        await ctx.send(embed=discord.Embed(description=f"{user.mention} has **{count}** filter strike(s)."))

    # ---------------------------------------------------------- built-in modules

    @command_meta(
        category="Security",
        description="Deletes messages containing links.",
        syntax=",filter links (status) [flags]",
        examples=[",filter links on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter links"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="links")
    @has_permission_or_fake("manage_guild")
    async def filter_links(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "links", rest)

    @command_meta(
        category="Security",
        description="Punishes members sending messages too quickly.",
        syntax=",filter spam (status) [flags]",
        examples=[",filter spam on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter spam"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="spam")
    @has_permission_or_fake("manage_guild")
    async def filter_spam(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "spam", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with too high a percentage of capital letters.",
        syntax=",filter caps (status) [flags]",
        examples=[",filter caps on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter caps"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="caps")
    @has_permission_or_fake("manage_guild")
    async def filter_caps(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "caps", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with too many emojis.",
        syntax=",filter emoji (status) [flags]",
        examples=[",filter emoji on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter emoji"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="emoji")
    @has_permission_or_fake("manage_guild")
    async def filter_emoji(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "emoji", rest)

    @command_meta(
        category="Security",
        description="Deletes messages containing Discord invite links.",
        syntax=",filter invites (status) [flags]",
        examples=[",filter invites on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter invites"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="invites")
    @has_permission_or_fake("manage_guild")
    async def filter_invites(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "invites", rest)

    @command_meta(
        category="Security",
        description="Deletes messages mentioning too many users/roles at once.",
        syntax=",filter massmention (status) [flags]",
        examples=[",filter massmention on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter massmention"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="massmention")
    @has_permission_or_fake("manage_guild")
    async def filter_massmention(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "massmention", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with too many spoiler tags.",
        syntax=",filter spoilers (status) [flags]",
        examples=[",filter spoilers on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter spoilers"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="spoilers")
    @has_permission_or_fake("manage_guild")
    async def filter_spoilers(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "spoilers", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with audio file attachments.",
        syntax=",filter musicfiles (status) [flags]",
        examples=[",filter musicfiles on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter musicfiles"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="musicfiles")
    @has_permission_or_fake("manage_guild")
    async def filter_musicfiles(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "musicfiles", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with image attachments.",
        syntax=",filter images (status) [flags]",
        examples=[",filter images on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter images"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="images")
    @has_permission_or_fake("manage_guild")
    async def filter_images(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "images", rest)

    @command_meta(
        category="Security",
        description="Deletes messages with excessive repeated characters.",
        syntax=",filter repetition (status) [flags]",
        examples=[",filter repetition on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter repetition"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="repetition")
    @has_permission_or_fake("manage_guild")
    async def filter_repetition(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "repetition", rest)

    @command_meta(
        category="Security",
        description="Deletes messages longer than the configured length.",
        syntax=",filter walloftext (status) [flags]",
        examples=[",filter walloftext on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter walloftext"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="walloftext")
    @has_permission_or_fake("manage_guild")
    async def filter_walloftext(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "walloftext", rest)

    @command_meta(
        category="Security",
        description="Deletes messages containing known malicious/IP-logging links.",
        syntax=",filter malicious (status) [flags]",
        examples=[",filter malicious on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter malicious"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="malicious")
    @has_permission_or_fake("manage_guild")
    async def filter_malicious(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "malicious", rest)

    @command_meta(
        category="Security",
        description="Deletes messages matching basic NSFW keyword heuristics.",
        syntax=",filter nsfw (status) [flags]",
        examples=[",filter nsfw on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter nsfw"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="nsfw")
    @has_permission_or_fake("manage_guild")
    async def filter_nsfw(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "nsfw", rest)

    @command_meta(
        category="Security",
        description="Resets nicknames that match a filtered word/phrase/regex.",
        syntax=",filter nicknames (status) [flags]",
        examples=[",filter nicknames on --do delete --threshold 3"],
        permissions=["Manage Guild"],
        aliases=["chatfilter nicknames"],
        flags=FILTER_FLAGS,
        require_args=False,
    )
    @filter_group.command(name="nicknames")
    @has_permission_or_fake("manage_guild")
    async def filter_nicknames(self, ctx: commands.Context, *, rest: str = ""):
        await _run_filter_module_command(ctx, "nicknames", rest)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))