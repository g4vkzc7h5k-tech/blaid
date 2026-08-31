"""
Centralized embed theme.

Never hardcode a discord.Color(...) value in a cog. Import the
factory functions below instead, so Blade's visual identity lives
in exactly one place.
"""

from __future__ import annotations

import discord

COLOR_SUCCESS = discord.Color.from_rgb(67, 181, 129)
COLOR_ERROR = discord.Color.from_rgb(237, 66, 69)
COLOR_WARNING = discord.Color.from_rgb(250, 166, 26)
COLOR_INFO = discord.Color.from_rgb(88, 101, 242)
COLOR_HELP = discord.Color.from_rgb(47, 49, 54)
COLOR_CONFIG = discord.Color.from_rgb(114, 137, 218)
COLOR_MODERATION = discord.Color.from_rgb(153, 45, 34)


def success(description: str, **kwargs) -> discord.Embed:
    return discord.Embed(description=f"<:emoji_2:1543849487250886717> {description}", color=COLOR_SUCCESS, **kwargs)


def error(description: str, **kwargs) -> discord.Embed:
    return discord.Embed(description=f"<:emoji_1:1543849473820860456> {description}", color=COLOR_ERROR, **kwargs)
  

def warning(description: str, **kwargs) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {description}", color=COLOR_WARNING, **kwargs)


def info(description: str, **kwargs) -> discord.Embed:
    return discord.Embed(description=description, color=COLOR_INFO, **kwargs)


def help_embed(**kwargs) -> discord.Embed:
    return discord.Embed(color=COLOR_HELP, **kwargs)


def config_embed(**kwargs) -> discord.Embed:
    return discord.Embed(color=COLOR_CONFIG, **kwargs)


def moderation_embed(**kwargs) -> discord.Embed:
    return discord.Embed(color=COLOR_MODERATION, **kwargs)
