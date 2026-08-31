"""
,createembed / ,ce - builds and sends a custom message from Blade's
script syntax. The same core.variables + core.script_parser pipeline
used here is meant to be reused for welcome/goodbye/boost/leave and
ticket messages later - this cog is just the direct "build it now"
entry point.
"""

from __future__ import annotations

from discord.ext import commands

from core.checks import has_permission_or_fake

from core.command_meta import command_meta
from core.script_parser import build_button_view, parse_script
from core.variables import resolve_variables


class Embeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @command_meta(
        category="Utility",
        description="Create an embed or message using a template script.",
        syntax=",createembed <script>",
        examples=[",createembed {embed}"],
        permissions=["Manage Guild"],
        aliases=["ce"],
    )
    @commands.hybrid_command(name="createembed", aliases=["ce"])
    @has_permission_or_fake("manage_guild")
    @commands.guild_only()
    async def createembed(self, ctx: commands.Context, *, script: str):
        resolved = resolve_variables(script, guild=ctx.guild, member=ctx.author, channel=ctx.channel)
        parsed = parse_script(resolved)

        if parsed.embed is None and not parsed.content:
            await ctx.error(
                "Nothing to send - include at least `{content: ...}`/`{message: ...}` "
                "or an embed field like `{title: ...}`/`{description: ...}`."
            )
            return

        view = build_button_view(parsed.buttons)
        await ctx.send(content=parsed.content, embed=parsed.embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Embeds(bot))