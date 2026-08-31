"""Command alias resolution."""

from __future__ import annotations

from database.database import get_session
from repositories import alias_repository


def render_template(template: str, args: list[str]) -> str:
    """Substitute {0}, {1}, ... in the template with the given args."""
    rendered = template
    for i, arg in enumerate(args):
        rendered = rendered.replace("{" + str(i) + "}", arg)
    return rendered


async def resolve(guild_id: int, alias_name: str, remaining_args: list[str]) -> str | None:
    """Returns the resolved command string (without prefix) if
    `alias_name` is a registered alias for this guild, else None."""
    async with get_session() as session:
        alias = await alias_repository.get_alias(session, guild_id, alias_name)

    if alias is None:
        return None

    if "{" in alias.command_template:
        return render_template(alias.command_template, remaining_args)

    # No placeholders - just append whatever args the user typed.
    if remaining_args:
        return f"{alias.command_template} {' '.join(remaining_args)}"
    return alias.command_template
