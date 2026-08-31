"""
Script parser: turns Blade's script syntax into a discord.Embed,
plain message content, and/or buttons.

Syntax (one component per line, or separated by the literal "$v" for
typing inline in a single chat command):

    {content: Hello there}          (alias: {message: ...})
    {embed}                         (marker - optional, embed fields alone are enough)
    {title: Some Title}
    {description: Some description}
    {color: #5865F2}
    {thumbnail: <url>}
    {image: <url>}
    {footer: text && icon_url}      (icon_url optional)
    {author: name:X && icon:Y && url:Z}   (icon/url optional)
    {field: Name && Value && inline}      (inline optional literal "inline")
    {button: label:X && url:Y && emoji:Z && style:primary && disabled}

This module does NOT resolve {user.mention}-style variables itself -
run text through core.variables.resolve_variables() first, then parse
the result here. Keeping these separate means the same parser can be
reused for welcome/boost/leave/ticket messages later without dragging
variable-resolution context into this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

_BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
    "link": discord.ButtonStyle.link,
}


@dataclass
class ButtonSpec:
    label: str = "Button"
    url: str | None = None
    emoji: str | None = None
    style: str = "link"
    disabled: bool = False


@dataclass
class ParsedScript:
    content: str | None = None
    embed: discord.Embed | None = None
    buttons: list[ButtonSpec] = field(default_factory=list)


def _parse_kv_parts(value: str | None) -> dict[str, str | bool]:
    """'name:X && icon:Y && disabled' -> {'name': 'X', 'icon': 'Y', 'disabled': True}"""
    result: dict[str, str | bool] = {}
    if not value:
        return result
    for part in value.split("&&"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, _, val = part.partition(":")
            result[key.strip().lower()] = val.strip()
        else:
            result[part.lower()] = True
    return result


def _parse_color(value: str) -> discord.Color:
    value = value.strip().lstrip("#")
    try:
        return discord.Color(int(value, 16))
    except ValueError:
        pass
    try:
        return discord.Color(int(value))
    except ValueError:
        return discord.Color.default()


def parse_script(raw: str) -> ParsedScript:
    """Parses already variable-resolved script text. Unknown component
    keywords are silently ignored so a typo doesn't break the whole
    message - only that one line is dropped."""
    normalized = raw.replace("$v", "\n")
    lines = [ln.strip() for ln in normalized.split("\n") if ln.strip()]

    content: str | None = None
    embed = discord.Embed()
    has_embed_content = False
    buttons: list[ButtonSpec] = []

    for line in lines:
        if not (line.startswith("{") and line.endswith("}")):
            continue

        inner = line[1:-1]
        if ":" in inner:
            keyword, _, value = inner.partition(":")
            value = value.strip()
        else:
            keyword, value = inner, None
        keyword = keyword.strip().lower()

        if keyword in ("content", "message"):
            content = value or ""

        elif keyword == "embed":
            has_embed_content = True

        elif keyword == "title":
            embed.title = value
            has_embed_content = True

        elif keyword == "description":
            embed.description = value
            has_embed_content = True

        elif keyword == "color":
            if value:
                embed.color = _parse_color(value)
            has_embed_content = True

        elif keyword == "thumbnail":
            if value:
                embed.set_thumbnail(url=value)
            has_embed_content = True

        elif keyword == "image":
            if value:
                embed.set_image(url=value)
            has_embed_content = True

        elif keyword == "footer":
            parts = [p.strip() for p in (value or "").split("&&")]
            text = parts[0] if parts else ""
            icon = parts[1] if len(parts) > 1 and parts[1] else None
            embed.set_footer(text=text, icon_url=icon)
            has_embed_content = True

        elif keyword == "author":
            kv = _parse_kv_parts(value)
            embed.set_author(
                name=str(kv.get("name", "")),
                icon_url=kv.get("icon") or None,
                url=kv.get("url") or None,
            )
            has_embed_content = True

        elif keyword == "field":
            parts = [p.strip() for p in (value or "").split("&&")]
            name = parts[0] if len(parts) > 0 and parts[0] else "\u200b"
            field_value = parts[1] if len(parts) > 1 and parts[1] else "\u200b"
            inline = len(parts) > 2 and parts[2].strip().lower() == "inline"
            embed.add_field(name=name, value=field_value, inline=inline)
            has_embed_content = True

        elif keyword == "button":
            kv = _parse_kv_parts(value)
            buttons.append(ButtonSpec(
                label=str(kv.get("label", "Button")),
                url=kv.get("url") if isinstance(kv.get("url"), str) else None,
                emoji=kv.get("emoji") if isinstance(kv.get("emoji"), str) else None,
                style=str(kv.get("style", "link")).lower(),
                disabled=bool(kv.get("disabled", False)),
            ))

        # Unknown keywords are ignored rather than raising, so one typo
        # doesn't take down the whole script.

    return ParsedScript(content=content, embed=embed if has_embed_content else None, buttons=buttons)


def build_button_view(buttons: list[ButtonSpec]) -> discord.ui.View | None:
    if not buttons:
        return None

    view = discord.ui.View(timeout=None)
    for i, spec in enumerate(buttons):
        if spec.url:
            button = discord.ui.Button(
                label=spec.label, url=spec.url, emoji=spec.emoji or None,
                disabled=spec.disabled, style=discord.ButtonStyle.link,
            )
        else:
            style = _BUTTON_STYLES.get(spec.style, discord.ButtonStyle.secondary)
            if style == discord.ButtonStyle.link:
                style = discord.ButtonStyle.secondary  # link style requires a URL
            button = discord.ui.Button(
                label=spec.label, style=style, emoji=spec.emoji or None,
                disabled=spec.disabled, custom_id=f"blade_script_btn:{i}",
            )

            async def _no_action(interaction: discord.Interaction):
                await interaction.response.send_message(
                    "This button isn't configured to do anything.", ephemeral=True
                )

            button.callback = _no_action

        view.add_item(button)

    return view