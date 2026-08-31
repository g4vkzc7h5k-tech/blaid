"""
Central command metadata registry.

One CommandMeta per command powers: ,help / ,h (paginated categories),
,help <command> (single-command help), the small on-empty-args help
embed, and - later - the website's command documentation. Never
maintain a second, separate description of a command anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommandMeta:
    name: str
    category: str
    description: str
    syntax: str
    examples: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    flags: list[tuple[str, str]] = field(default_factory=list)  # [(flag_display, description), ...]
    require_args: bool = True  # show small help embed if invoked with no/missing args
    no_help_on_empty: bool = False  # opt out of the above entirely (NSFW/optional-arg commands)


class CommandRegistry:
    """Simple in-memory registry, keyed by the full dotted command path
    (e.g. 'levels', 'levels roles', 'levels leaderboard rename')."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandMeta] = {}

    def register(self, meta: CommandMeta) -> CommandMeta:
        self._commands[meta.name] = meta
        return meta

    def get(self, name: str) -> CommandMeta | None:
        return self._commands.get(name)

    def by_category(self) -> dict[str, list[CommandMeta]]:
        grouped: dict[str, list[CommandMeta]] = {}
        for meta in self._commands.values():
            grouped.setdefault(meta.category, []).append(meta)
        for entries in grouped.values():
            entries.sort(key=lambda m: m.name)
        return grouped

    def command_family(self, name: str) -> list[CommandMeta]:
        """Returns the command's own meta (if registered) plus every
        direct or nested subcommand registered under it, e.g.
        command_family('setup') -> [setup, setup reset]. Used by
        ,help <command> to page through a command and its subcommands
        together instead of showing only the parent."""
        family = []
        exact = self._commands.get(name)
        if exact is not None:
            family.append(exact)

        prefix = name + " "
        for cmd_name, meta in self._commands.items():
            if cmd_name.startswith(prefix):
                family.append(meta)

        family.sort(key=lambda m: m.name)
        return family

    def categories(self) -> list[str]:
        return sorted(self.by_category().keys())

    def count(self) -> int:
        return len(self._commands)

    def all(self) -> list[CommandMeta]:
        return list(self._commands.values())


registry = CommandRegistry()


def command_meta(
    category: str,
    description: str,
    syntax: str,
    examples: list[str] | None = None,
    permissions: list[str] | None = None,
    aliases: list[str] | None = None,
    flags: list[tuple[str, str]] | None = None,
    require_args: bool = True,
    no_help_on_empty: bool = False,
):
    """
    Decorator applied *above* @commands.command() that both registers
    the metadata and stashes it on the command's __blade_meta__ so the
    help formatter and the on-empty-args logic can look it up at
    runtime without a second lookup table.

    Usage:
        @command_meta(
            category="Moderation",
            description="Permanently ban a member.",
            syntax=",ban <member> [reason]",
            examples=[",ban @User Spamming"],
            permissions=["Ban Members"],
        )
        @commands.command(name="ban")
        async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
            ...
    """

    def decorator(func):
        # func here is already a commands.Command instance if this decorator
        # is stacked below @commands.command(); handle both cases.
        target_name = getattr(func, "qualified_name", None) or getattr(func, "__name__", "")

        meta = CommandMeta(
            name=target_name,
            category=category,
            description=description,
            syntax=syntax,
            examples=examples or [],
            permissions=permissions or [],
            aliases=aliases or [],
            flags=flags or [],
            require_args=require_args,
            no_help_on_empty=no_help_on_empty,
        )
        registry.register(meta)
        setattr(func, "__blade_meta__", meta)
        return func

    return decorator