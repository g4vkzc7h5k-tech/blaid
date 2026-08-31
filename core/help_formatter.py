"""
HelpFormatter - drives ,help, ,h, ,help <category>, ,help <command>,
and the small on-empty-args help embed. This is the single source
that renders CommandMeta objects from core.command_meta.registry.

Anyone can use ,help / ,h - no permission check here.

The bare ,help / ,h landing page (HelpHomeView) uses Components V2
(Container/Section/Separator/Select all in one seamless card, matching
the reference look) - genuinely newer discord.py API surface (2.6+)
that I haven't been able to test live. ,help <command> and
,help <category> are unaffected - those still use classic embeds via
Paginator, which is well-established and not part of this rebuild.
"""

from __future__ import annotations

import re

import discord
from discord.ext import commands

from core.command_meta import CommandMeta, registry
from core.paginator import Paginator

CATEGORY_EMOJI = {
    "Fun": "🎮",
    "General": "🌐",
    "Information": "ℹ️",
    "Moderation": "🔨",
    "Music": "🎵",
    "Security": "🔒",
    "Server": "🏢",
    "Utility": "🛠️",
    "Voice": "🔊",
}


def _extract_parameters(syntax: str) -> str:
    """',ban <member> [reason]' -> 'member, reason'; no args -> 'None'."""
    parts = syntax.split(maxsplit=1)
    if len(parts) < 2:
        return "None"
    words = re.findall(r"[\w.]+", parts[1])
    return ", ".join(words) if words else "None"


def command_help_embed(meta: CommandMeta, invoker: discord.abc.User) -> discord.Embed:
    """The BIG, rich embed - used by ,help / ,h for every page, including
    a group's own root page. Author is whoever invoked help, title is
    the command name, then Aliases/Parameters/Information, then a
    Usage(+Example, if any are set) block."""
    embed = discord.Embed(title=meta.name.title(), description=f"> {meta.description}")
    embed.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)
    embed.set_footer(text=meta.category)

    embed.add_field(name="Aliases", value=", ".join(meta.aliases) if meta.aliases else "None", inline=True)
    embed.add_field(name="Parameters", value=_extract_parameters(meta.syntax), inline=True)
    embed.add_field(
        name="Information",
        value=", ".join(meta.permissions) if meta.permissions else "None",
        inline=True,
    )

    if meta.examples:
        example_line = "\n" + "\n".join(f"Example: {ex}" for ex in meta.examples)
    else:
        example_line = ""
    usage_block = f"```Usage: {meta.syntax}{example_line}```"
    embed.add_field(name="Usage", value=usage_block, inline=False)

    if meta.flags:
        flags_lines = "\n".join(f"`{flag}` — {desc}" for flag, desc in meta.flags)
        embed.add_field(name="Flags", value=flags_lines, inline=False)

    return embed


def command_usage_embed(meta: CommandMeta, invoker: discord.abc.User) -> discord.Embed:
    """The SMALL embed shown when a command is invoked without its
    required arguments (e.g. typing just ',role' or ',ban'). Only the
    invoker as author, title, description, and a bare usage code block -
    no Aliases/Parameters/Information/Example. ,help always shows the
    big embed instead - this one is only for the on-empty-args case."""
    embed = discord.Embed(title=meta.name.title(), description=f"> {meta.description}")
    embed.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)
    embed.add_field(name="Usage", value=f"```{meta.syntax}```", inline=False)
    return embed


def _category_pages(category: str, invoker: discord.abc.User) -> list[discord.Embed]:
    """One command per page - each page is the same rich embed shown by
    ,help <command>, paginated through the whole category."""
    metas = registry.by_category().get(category, [])
    return [command_help_embed(meta, invoker) for meta in metas]


class HelpHomeView(discord.ui.LayoutView):
    """The bare ,help / ,h landing page - banner, title/tagline +
    thumbnail, an optional category chip list, and a category dropdown,
    all inside one seamless Components V2 container. Selecting a
    category rebuilds the whole view with that category's chips shown;
    picking "Home" rebuilds it with none. ,help <command> and
    ,help <category> are unaffected - they still use Paginator."""

    def __init__(self, ctx: commands.Context, author_id: int, category: str | None = None):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.author_id = author_id
        self.category = category
        self.message: discord.Message | None = None

        from config import config

        bot = ctx.bot
        prefix = bot.guild_prefixes.get(ctx.guild.id, config.default_prefix) if ctx.guild else config.default_prefix

        components: list[discord.ui.Item] = []

        if bot.user.banner:
            components.append(
                discord.ui.MediaGallery(discord.MediaGalleryItem(media=bot.user.banner.url))
            )

        components.append(
            discord.ui.Section(
                discord.ui.TextDisplay(f"## **{bot.user.name} help**"),
                discord.ui.TextDisplay(
                    "-# Experience the ultimate Discord bot designed for seamless server "
                    "management and community engagement."
                ),
                accessory=discord.ui.Thumbnail(media=bot.user.display_avatar.url),
            )
        )

        components.append(discord.ui.Separator(visible=True))
        components.append(
            discord.ui.TextDisplay(
                f"🖥️ **Prefix** `{prefix}`\n"
                f"🗃️ **Commands** `{registry.count():,}`\n"
                f"🧩 **Modules** `{len(registry.categories())}`"
            )
        )

        if category is not None:
            components.append(discord.ui.Separator(visible=True))
            metas = sorted(registry.by_category().get(category, []), key=lambda m: m.name)
            # Only top-level commands - "antinuke ban", "tickets claim",
            # etc. all have a space in their name (subcommand paths), so
            # this keeps the chip list to one entry per command family.
            metas = [m for m in metas if " " not in m.name]
            emoji = CATEGORY_EMOJI.get(category, "📁")
            chips = " ".join(f"`{meta.name}`" for meta in metas) or "\u200b"
            if len(chips) > 900:
                chips = chips[:900] + " …"
            components.append(discord.ui.TextDisplay(f"{emoji} **{category}**\n{chips}"))

        components.append(discord.ui.Separator(visible=True))

        select = discord.ui.Select(placeholder="Select a category")
        options = [discord.SelectOption(label="Home", emoji="🏠", value="__home__", default=category is None)]
        for cat in registry.categories():
            options.append(
                discord.SelectOption(label=cat, emoji=CATEGORY_EMOJI.get(cat, "📁"), value=cat, default=(cat == category))
            )
        select.options = options
        select.callback = self._on_select
        self.select = select
        components.append(discord.ui.ActionRow(select))

        components.append(discord.ui.Separator(visible=True))
        components.append(discord.ui.TextDisplay(f"-# Use {prefix}help (command) for details on a specific command"))

        container = discord.ui.Container(*components)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You can't control someone else's help menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _on_select(self, interaction: discord.Interaction) -> None:
        value = self.select.values[0]
        new_category = None if value == "__home__" else value
        new_view = HelpHomeView(self.ctx, self.author_id, category=new_category)
        new_view.message = self.message
        await interaction.response.edit_message(view=new_view)


def _resolve_alias(query: str) -> str:
    """If the first word of `query` is a registered alias for a
    top-level command (e.g. 'gw' for 'giveaway'), rewrite it to the
    command's canonical name - so ,help gw and ,help gw start behave
    exactly like ,help giveaway and ,help giveaway start."""
    parts = query.split(maxsplit=1)
    if not parts:
        return query

    first, rest = parts[0], parts[1:]
    for meta in registry.all():
        if " " in meta.name:
            continue  # only top-level commands carry group aliases
        if first.lower() in (alias.lower() for alias in meta.aliases):
            return f"{meta.name} {rest[0]}" if rest else meta.name

    return query


async def send_help(ctx: commands.Context, query: str | None = None) -> None:
    """Entry point called by the `,help` / `,h` commands. Anyone can use it."""

    if not query:
        view = HelpHomeView(ctx, ctx.author.id)
        message = await ctx.send(view=view)
        view.message = message
        return

    query = _resolve_alias(query.strip())

    # Exact command match (supports dotted subcommand paths, e.g. "levels roles")
    meta = registry.get(query)
    if meta is not None:
        # If this command has subcommands (e.g. "levels" -> "levels lock",
        # "levels config", ...), page through the whole family. A leaf
        # command with no subcommands just shows its own single page.
        family = registry.command_family(query)
        pages = [command_help_embed(m, ctx.author) for m in family]
        paginator = Paginator(pages, author_id=ctx.author.id)
        await paginator.start(ctx)
        return

    # Category match (case-insensitive)
    for category in registry.categories():
        if category.lower() == query.lower():
            pages = _category_pages(category, ctx.author)
            if not pages:
                await ctx.error(f"No commands found in category `{category}`.")
                return
            paginator = Paginator(pages, author_id=ctx.author.id)
            await paginator.start(ctx)
            return

    await ctx.error(f"No command or category found matching `{query}`.")