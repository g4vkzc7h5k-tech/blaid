"""
One reusable paginator used everywhere (help, leaderboard, level roles,
logs, lists, configuration views). Do not build a bespoke paginator
per command.
"""

from __future__ import annotations

from typing import Sequence

import discord


class Paginator(discord.ui.View):
    def __init__(
        self,
        pages: Sequence[discord.Embed],
        author_id: int,
        timeout: float = 90.0,
    ):
        super().__init__(timeout=timeout)
        self.pages = list(pages)
        self.author_id = author_id
        self.index = 0
        self.message: discord.Message | None = None

        self._apply_page_numbers()

        if len(self.pages) <= 1:
            # No point showing prev/next for a single page, but the
            # close button always stays.
            self.remove_item(self.previous_button)
            self.remove_item(self.next_button)
        else:
            self._update_button_state()

    def _apply_page_numbers(self) -> None:
        total = len(self.pages) or 1
        for i, embed in enumerate(self.pages, start=1):
            footer_text = f"Page {i}/{total}"
            if embed.footer and embed.footer.text:
                embed.set_footer(text=f"{embed.footer.text} - {footer_text}")
            else:
                embed.set_footer(text=footer_text)

    def _update_button_state(self) -> None:
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You can't control someone else's paginator.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass  # message was likely deleted

    async def start(self, ctx_or_interaction) -> None:
        if not self.pages:
            return
        embed = self.pages[self.index]
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed, view=self)
            self.message = await ctx_or_interaction.original_response()
        else:
            self.message = await ctx_or_interaction.send(embed=embed, view=self)

    @discord.ui.button(emoji="<:emoji_4:1543849564455309322>", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="<:emoji_3:1543849536651264151>", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="<:emoji_12:1543851555407659088>", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        if self.message is not None:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass
        self.stop()