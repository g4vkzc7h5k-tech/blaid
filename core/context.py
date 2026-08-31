"""Custom Context subclass with convenience response helpers."""

from __future__ import annotations

from discord.ext import commands

from core import embeds


class BladeContext(commands.Context):
    async def success(self, description: str, **kwargs):
        return await self.send(embed=embeds.success(description), **kwargs)

    async def error(self, description: str, **kwargs):
        return await self.send(embed=embeds.error(description), **kwargs)

    async def warn(self, description: str, **kwargs):
        return await self.send(embed=embeds.warning(description), **kwargs)

    async def info(self, description: str, **kwargs):
        return await self.send(embed=embeds.info(description), **kwargs)
