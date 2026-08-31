"""Custom argument converters."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import InvalidDuration, parse_duration


class Duration(commands.Converter, app_commands.Transformer):
    """Converts a duration string ('10m', '2h', '1w2d') into total
    seconds. Implements both commands.Converter (prefix invocation) and
    app_commands.Transformer (slash invocation) so hybrid commands using
    this as a parameter type work identically either way."""

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        try:
            return parse_duration(argument)
        except InvalidDuration as exc:
            raise commands.BadArgument(str(exc)) from exc

    async def transform(self, interaction: discord.Interaction, value: str) -> int:
        try:
            return parse_duration(value)
        except InvalidDuration as exc:
            raise app_commands.AppCommandError(str(exc)) from exc

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string