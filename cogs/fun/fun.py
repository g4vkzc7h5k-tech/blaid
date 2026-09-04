"""Fun commands - reaction gifs (via the free otakugifs.xyz API), plus
,ship, ,smoke, ,spark, and ,vape.

HONEST GAP: otakugifs.xyz's confirmed reaction list includes kiss/hug/
bite/stare/pout and others, but I don't have full certainty every
reaction name below (nom, nope, thumbsup, yeet, etc.) exists in their
library. fetch_reaction_gif() fails gracefully either way - if a given
reaction isn't supported, the embed just has no image instead of the
command crashing. If any of these come back gif-less in practice, say
which ones and I'll look at an alternate source for just those.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.command_meta import command_meta
from database.database import get_session
from repositories import fun_repository
from services import fun_service


# ---------------------------------------------------------- tic-tac-toe

# channel_id -> game state - only one game per channel at a time
_ttt_active_games: dict[int, "TicTacToeGame"] = {}

_TTT_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


class TicTacToeGame:
    def __init__(self, challenger: discord.Member, opponent: discord.Member):
        self.challenger = challenger  # X
        self.opponent = opponent  # O
        self.board: list[str | None] = [None] * 9
        self.current = challenger

    @property
    def other(self) -> discord.Member:
        return self.opponent if self.current.id == self.challenger.id else self.challenger

    def symbol_for(self, player: discord.Member) -> str:
        return "X" if player.id == self.challenger.id else "O"

    def mark(self, index: int) -> None:
        self.board[index] = self.symbol_for(self.current)

    def check_result(self) -> str | None:
        """Returns 'X', 'O', 'draw', or None (still going)."""
        for a, b, c in _TTT_LINES:
            if self.board[a] is not None and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if all(cell is not None for cell in self.board):
            return "draw"
        return None


class TicTacToeView(discord.ui.View):
    def __init__(self, game: TicTacToeGame, channel_id: int):
        super().__init__(timeout=300)
        self.game = game
        self.channel_id = channel_id

        for index in range(9):
            button = discord.ui.Button(label="\u200b", style=discord.ButtonStyle.secondary, row=index // 3)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            game = self.game

            if interaction.user.id not in (game.challenger.id, game.opponent.id):
                await interaction.response.send_message("This isn't your game.", ephemeral=True)
                return
            if interaction.user.id != game.current.id:
                await interaction.response.send_message("It's not your turn.", ephemeral=True)
                return
            if game.board[index] is not None:
                await interaction.response.send_message("That spot's already taken.", ephemeral=True)
                return

            game.mark(index)
            button = self.children[index]
            symbol = game.board[index]
            button.label = symbol
            button.style = discord.ButtonStyle.danger if symbol == "X" else discord.ButtonStyle.primary
            button.disabled = True

            result = game.check_result()
            if result is not None:
                for child in self.children:
                    child.disabled = True
                _ttt_active_games.pop(self.channel_id, None)

                if result == "draw":
                    description = "It's a draw!"
                else:
                    winner = game.challenger if result == "X" else game.opponent
                    description = f"{winner.mention} wins!"

                embed = discord.Embed(title="Tic-Tac-Toe", description=description)
                await interaction.response.edit_message(embed=embed, view=self)
                return

            game.current = game.other
            embed = discord.Embed(
                title="Tic-Tac-Toe",
                description=f"{game.challenger.mention} (X) vs {game.opponent.mention} (O)\n\n"
                            f"{game.current.mention}'s turn ({game.symbol_for(game.current)})",
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def on_timeout(self) -> None:
        _ttt_active_games.pop(self.channel_id, None)
        for child in self.children:
            child.disabled = True


# ---------------------------------------------------------- blacktea

import asyncio
import random

_blacktea_active_games: dict[int, "BlackTeaGame"] = {}

_BLACKTEA_TRIGRAMS = [
    "ing", "the", "and", "ion", "tio", "ent", "for", "ter", "est", "ers",
    "ati", "hat", "ate", "all", "eth", "ver", "his", "ith", "res", "ear",
    "sto", "ans", "hin", "her", "ere", "ric", "con", "tra", "ade", "man",
    "car", "sta", "gra", "und", "ous", "ive", "ome", "one", "art", "ort",
]


class BlackTeaGame:
    def __init__(self, host: discord.Member, channel: discord.TextChannel):
        self.host = host
        self.channel = channel
        self.lives: dict[int, int] = {}
        self.members: dict[int, discord.Member] = {}
        self.used_words: set[str] = set()
        self.turn_order: list[int] = []
        self.ended = False


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------- shared helpers

    async def _send_reaction(
        self, ctx: commands.Context, reaction: str, member: discord.Member | None,
        verb_with_target: str | None, verb_alone: str | None,
    ) -> None:
        gif_url = await fun_service.fetch_reaction_gif(reaction)
        embed = discord.Embed()
        if gif_url:
            embed.set_image(url=gif_url)

        if member is not None and verb_with_target:
            async with get_session() as session:
                count = await fun_repository.increment_count(
                    session, ctx.guild.id, ctx.author.id, member.id, reaction
                )
            embed.description = (
                f"**{ctx.author.display_name}** {verb_with_target} **{member.display_name}** "
                f"for the **{fun_service.ordinal(count)}** time."
            )
        elif member is None and verb_alone:
            embed.description = f"**{ctx.author.display_name}** {verb_alone}."

        await ctx.send(embed=embed)

    async def _check_nsfw(self, ctx: commands.Context) -> bool:
        if isinstance(ctx.channel, discord.TextChannel) and ctx.channel.is_nsfw():
            return True
        await ctx.send(embed=discord.Embed(
            description=f"{ctx.author.mention}: This command can only be used in an **NSFW** channel."
        ))
        return False

    # ---------------------------------------------------------- kiss (with counter)

    @command_meta(
        category="Fun",
        description="Kiss someone.",
        syntax=",kiss [member]",
        examples=[",kiss @User", ",kiss"],
        require_args=False,
    )
    @commands.command(name="kiss")
    @commands.guild_only()
    async def kiss(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "kiss", member, "kissed", "kisses the air")

    @command_meta(
        category="Fun",
        description="Hug someone.",
        syntax=",hug [member]",
        examples=[",hug @User", ",hug"],
        require_args=False,
    )
    @commands.command(name="hug")
    @commands.guild_only()
    async def hug(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "hug", member, 'hugs', 'hugs themselves')

    @command_meta(
        category="Fun",
        description="Bite someone.",
        syntax=",bite [member]",
        examples=[",bite @User", ",bite"],
        require_args=False,
    )
    @commands.command(name="bite")
    @commands.guild_only()
    async def bite(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "bite", member, 'bites', 'bites the air')

    @command_meta(
        category="Fun",
        description="Cuddle someone.",
        syntax=",cuddle [member]",
        examples=[",cuddle @User", ",cuddle"],
        require_args=False,
    )
    @commands.command(name="cuddle")
    @commands.guild_only()
    async def cuddle(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "cuddle", member, 'cuddles', 'wants to cuddle')

    @command_meta(
        category="Fun",
        description="Feed someone.",
        syntax=",feed [member]",
        examples=[",feed @User", ",feed"],
        require_args=False,
    )
    @commands.command(name="feed")
    @commands.guild_only()
    async def feed(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "nom", member, 'feeds', 'eats a snack')

    @command_meta(
        category="Fun",
        description="Handhold someone.",
        syntax=",handhold [member]",
        examples=[",handhold @User", ",handhold"],
        require_args=False,
    )
    @commands.command(name="handhold")
    @commands.guild_only()
    async def handhold(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "handhold", member, 'holds hands with', 'holds their own hand')

    @command_meta(
        category="Fun",
        description="Handshake someone.",
        syntax=",handshake [member]",
        examples=[",handshake @User", ",handshake"],
        require_args=False,
    )
    @commands.command(name="handshake")
    @commands.guild_only()
    async def handshake(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "handhold", member, 'shakes hands with', 'offers a handshake')

    @command_meta(
        category="Fun",
        description="Highfive someone.",
        syntax=",highfive [member]",
        examples=[",highfive @User", ",highfive"],
        require_args=False,
    )
    @commands.command(name="highfive")
    @commands.guild_only()
    async def highfive(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "brofist", member, 'high-fives', 'raises a hand for a high-five')

    @command_meta(
        category="Fun",
        description="Laugh someone.",
        syntax=",laugh [member]",
        examples=[",laugh @User", ",laugh"],
        require_args=False,
    )
    @commands.command(name="laugh")
    @commands.guild_only()
    async def laugh(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "laugh", member, 'laughs at', 'laughs')

    @command_meta(
        category="Fun",
        description="Nod someone.",
        syntax=",nod [member]",
        examples=[",nod @User", ",nod"],
        require_args=False,
    )
    @commands.command(name="nod")
    @commands.guild_only()
    async def nod(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "yes", member, 'nods at', 'nods')

    @command_meta(
        category="Fun",
        description="Nom someone.",
        syntax=",nom [member]",
        examples=[",nom @User", ",nom"],
        require_args=False,
    )
    @commands.command(name="nom")
    @commands.guild_only()
    async def nom(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "nom", member, 'noms on', 'noms')

    @command_meta(
        category="Fun",
        description="Nope someone.",
        syntax=",nope [member]",
        examples=[",nope @User", ",nope"],
        require_args=False,
    )
    @commands.command(name="nope")
    @commands.guild_only()
    async def nope(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "no", member, 'nopes at', 'nopes out')

    @command_meta(
        category="Fun",
        description="Pat someone.",
        syntax=",pat [member]",
        examples=[",pat @User", ",pat"],
        require_args=False,
    )
    @commands.command(name="pat")
    @commands.guild_only()
    async def pat(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "pat", member, 'pats', 'pats themselves')

    @command_meta(
        category="Fun",
        description="Peck someone.",
        syntax=",peck [member]",
        examples=[",peck @User", ",peck"],
        require_args=False,
    )
    @commands.command(name="peck")
    @commands.guild_only()
    async def peck(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "airkiss", member, 'pecks', 'blows a kiss')

    @command_meta(
        category="Fun",
        description="Poke someone.",
        syntax=",poke [member]",
        examples=[",poke @User", ",poke"],
        require_args=False,
    )
    @commands.command(name="poke")
    @commands.guild_only()
    async def poke(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "poke", member, 'pokes', 'pokes the air')

    @command_meta(
        category="Fun",
        description="Punch someone.",
        syntax=",punch [member]",
        examples=[",punch @User", ",punch"],
        require_args=False,
    )
    @commands.command(name="punch")
    @commands.guild_only()
    async def punch(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "punch", member, 'punches', 'throws a punch')

    @command_meta(
        category="Fun",
        description="Run someone.",
        syntax=",run [member]",
        examples=[",run @User", ",run"],
        require_args=False,
    )
    @commands.command(name="run")
    @commands.guild_only()
    async def run(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "run", member, 'runs away from', 'runs away')

    @command_meta(
        category="Fun",
        description="Shoot someone.",
        syntax=",shoot [member]",
        examples=[",shoot @User", ",shoot"],
        require_args=False,
    )
    @commands.command(name="shoot")
    @commands.guild_only()
    async def shoot(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "punch", member, 'shoots', 'fires a shot')

    @command_meta(
        category="Fun",
        description="Slap someone.",
        syntax=",slap [member]",
        examples=[",slap @User", ",slap"],
        require_args=False,
    )
    @commands.command(name="slap")
    @commands.guild_only()
    async def slap(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "slap", member, 'slaps', 'slaps themselves')

    @command_meta(
        category="Fun",
        description="Stare someone.",
        syntax=",stare [member]",
        examples=[",stare @User", ",stare"],
        require_args=False,
    )
    @commands.command(name="stare")
    @commands.guild_only()
    async def stare(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "stare", member, 'stares at', 'stares into the distance')

    @command_meta(
        category="Fun",
        description="Think someone.",
        syntax=",think [member]",
        examples=[",think @User", ",think"],
        require_args=False,
    )
    @commands.command(name="think")
    @commands.guild_only()
    async def think(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "confused", member, 'thinks about', 'is deep in thought')

    @command_meta(
        category="Fun",
        description="Thumbsup someone.",
        syntax=",thumbsup [member]",
        examples=[",thumbsup @User", ",thumbsup"],
        require_args=False,
    )
    @commands.command(name="thumbsup")
    @commands.guild_only()
    async def thumbsup(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "thumbsup", member, 'gives a thumbs up to', 'gives a thumbs up')

    @command_meta(
        category="Fun",
        description="Tickle someone.",
        syntax=",tickle [member]",
        examples=[",tickle @User", ",tickle"],
        require_args=False,
    )
    @commands.command(name="tickle")
    @commands.guild_only()
    async def tickle(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "tickle", member, 'tickles', 'wiggles their fingers')

    @command_meta(
        category="Fun",
        description="Wave someone.",
        syntax=",wave [member]",
        examples=[",wave @User", ",wave"],
        require_args=False,
    )
    @commands.command(name="wave")
    @commands.guild_only()
    async def wave(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "wave", member, 'waves at', 'waves')

    @command_meta(
        category="Fun",
        description="Wink someone.",
        syntax=",wink [member]",
        examples=[",wink @User", ",wink"],
        require_args=False,
    )
    @commands.command(name="wink")
    @commands.guild_only()
    async def wink(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "wink", member, 'winks at', 'winks')

    @command_meta(
        category="Fun",
        description="Yeet someone.",
        syntax=",yeet [member]",
        examples=[",yeet @User", ",yeet"],
        require_args=False,
    )
    @commands.command(name="yeet")
    @commands.guild_only()
    async def yeet(self, ctx: commands.Context, member: discord.Member = None):
        await self._send_reaction(ctx, "roll", member, 'yeets', 'yeets themselves')

    @command_meta(
        category="Fun",
        description="Blush someone.",
        syntax=",blush",
        examples=[",blush"],
        require_args=False,
    )
    @commands.command(name="blush")
    @commands.guild_only()
    async def blush(self, ctx: commands.Context):
        await self._send_reaction(ctx, "blush", None, None, 'blushes')

    @command_meta(
        category="Fun",
        description="Bore someone.",
        syntax=",bored",
        examples=[",bored"],
        require_args=False,
    )
    @commands.command(name="bored")
    @commands.guild_only()
    async def bored(self, ctx: commands.Context):
        await self._send_reaction(ctx, "tired", None, None, 'is bored')

    @command_meta(
        category="Fun",
        description="Cry someone.",
        syntax=",cry",
        examples=[",cry"],
        require_args=False,
    )
    @commands.command(name="cry")
    @commands.guild_only()
    async def cry(self, ctx: commands.Context):
        await self._send_reaction(ctx, "cry", None, None, 'cries')

    @command_meta(
        category="Fun",
        description="Facepalm someone.",
        syntax=",facepalm",
        examples=[",facepalm"],
        require_args=False,
    )
    @commands.command(name="facepalm")
    @commands.guild_only()
    async def facepalm(self, ctx: commands.Context):
        await self._send_reaction(ctx, "facepalm", None, None, 'facepalms')

    @command_meta(
        category="Fun",
        description="Happy someone.",
        syntax=",happy",
        examples=[",happy"],
        require_args=False,
    )
    @commands.command(name="happy")
    @commands.guild_only()
    async def happy(self, ctx: commands.Context):
        await self._send_reaction(ctx, "happy", None, None, 'is happy')

    @command_meta(
        category="Fun",
        description="Lurk someone.",
        syntax=",lurk",
        examples=[",lurk"],
        require_args=False,
    )
    @commands.command(name="lurk")
    @commands.guild_only()
    async def lurk(self, ctx: commands.Context):
        await self._send_reaction(ctx, "peek", None, None, 'lurks in the shadows')

    @command_meta(
        category="Fun",
        description="Pout someone.",
        syntax=",pout",
        examples=[",pout"],
        require_args=False,
    )
    @commands.command(name="pout")
    @commands.guild_only()
    async def pout(self, ctx: commands.Context):
        await self._send_reaction(ctx, "pout", None, None, 'pouts')

    @command_meta(
        category="Fun",
        description="Shrug someone.",
        syntax=",shrug",
        examples=[",shrug"],
        require_args=False,
    )
    @commands.command(name="shrug")
    @commands.guild_only()
    async def shrug(self, ctx: commands.Context):
        await self._send_reaction(ctx, "shrug", None, None, 'shrugs')

    @command_meta(
        category="Fun",
        description="Sleep someone.",
        syntax=",sleep",
        examples=[",sleep"],
        require_args=False,
    )
    @commands.command(name="sleep")
    @commands.guild_only()
    async def sleep(self, ctx: commands.Context):
        await self._send_reaction(ctx, "sleep", None, None, 'goes to sleep')

    @command_meta(
        category="Fun",
        description="Smile someone.",
        syntax=",smile",
        examples=[",smile"],
        require_args=False,
    )
    @commands.command(name="smile")
    @commands.guild_only()
    async def smile(self, ctx: commands.Context):
        await self._send_reaction(ctx, "smile", None, None, 'smiles')

    @command_meta(
        category="Fun",
        description="Smug someone.",
        syntax=",smug",
        examples=[",smug"],
        require_args=False,
    )
    @commands.command(name="smug")
    @commands.guild_only()
    async def smug(self, ctx: commands.Context):
        await self._send_reaction(ctx, "smug", None, None, 'looks smug')

    @command_meta(
        category="Fun",
        description="Yawn someone.",
        syntax=",yawn",
        examples=[",yawn"],
        require_args=False,
    )
    @commands.command(name="yawn")
    @commands.guild_only()
    async def yawn(self, ctx: commands.Context):
        await self._send_reaction(ctx, "yawn", None, None, 'yawns')

    @command_meta(
        category="Fun",
        description="Fuck someone. (NSFW)",
        syntax=",fuck [member]",
        examples=[",fuck @User", ",fuck"],
        require_args=False,
    )
    @commands.command(name="fuck")
    @commands.guild_only()
    async def fuck(self, ctx: commands.Context, member: discord.Member = None):
        if not await self._check_nsfw(ctx):
            return
        await self._send_reaction(ctx, "fuck", member, 'fucks', 'is horny')

    @command_meta(
        category="Fun",
        description="Nutkick someone. (NSFW)",
        syntax=",nutkick [member]",
        examples=[",nutkick @User", ",nutkick"],
        require_args=False,
    )
    @commands.command(name="nutkick")
    @commands.guild_only()
    async def nutkick(self, ctx: commands.Context, member: discord.Member = None):
        if not await self._check_nsfw(ctx):
            return
        await self._send_reaction(ctx, "nutkick", member, 'nutkicks', 'kicks at nothing')

    @command_meta(
        category="Fun",
        description="Spank someone. (NSFW)",
        syntax=",spank [member]",
        examples=[",spank @User", ",spank"],
        require_args=False,
    )
    @commands.command(name="spank")
    @commands.guild_only()
    async def spank(self, ctx: commands.Context, member: discord.Member = None):
        if not await self._check_nsfw(ctx):
            return
        await self._send_reaction(ctx, "spank", member, 'spanks', 'spanks themselves')
    # ---------------------------------------------------------- ship

    @command_meta(
        category="Fun",
        description="Check two people´s compatibility.",
        syntax=",ship <member> [member2]",
        examples=[",ship @User", ",ship @User1 @User2"],
    )
    @commands.command(name="ship")
    @commands.guild_only()
    async def ship(self, ctx: commands.Context, member: discord.Member, member2: discord.Member = None):
        user1, user2 = (ctx.author, member) if member2 is None else (member, member2)

        percentage = fun_service.ship_percentage(user1.id, user2.id)
        name = fun_service.ship_name(user1.display_name, user2.display_name)
        bar = fun_service.ship_bar(percentage)
        comment = fun_service.ship_comment(percentage)

        gif_url = await fun_service.fetch_reaction_gif("kiss")

        embed = discord.Embed(
            title=f"{user1.display_name} 💞 {user2.display_name}",
            description=(
                f"Ship name: **{name}**\n"
                f"`{bar}` **{percentage}%**\n"
                f"{comment}"
            ),
        )
        if gif_url:
            embed.set_image(url=gif_url)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- smoke / spark (self-only)

    @command_meta(
        category="Fun",
        description="Sends a random smoking anime gif. Self-only.",
        syntax=",smoke",
        examples=[",smoke"],
        require_args=False,
    )
    @commands.command(name="smoke")
    @commands.guild_only()
    async def smoke(self, ctx: commands.Context):
        await self._send_reaction(ctx, "smoke", None, None, "lights up a cigarette")

    @command_meta(
        category="Fun",
        description="Sparks the blunt with a random anime gif. Self-only.",
        syntax=",spark",
        examples=[",spark"],
        require_args=False,
    )
    @commands.command(name="spark")
    @commands.guild_only()
    async def spark(self, ctx: commands.Context):
        await self._send_reaction(ctx, "smoke", None, None, "sparks the blunt")

    # ---------------------------------------------------------- vape / vape flavor (self-only)

    @command_meta(
        category="Fun",
        description="Takes a hit of your vape (mentions your chosen flavor if you've set one). Self-only.",
        syntax=",vape",
        examples=[",vape"],
        require_args=False,
    )
    @commands.group(name="vape", invoke_without_command=True)
    @commands.guild_only()
    async def vape(self, ctx: commands.Context):
        async with get_session() as session:
            flavor = await fun_repository.get_vape_flavor(session, ctx.guild.id, ctx.author.id)

        verb = f"takes a hit of their **{flavor}** vape" if flavor else "takes a hit of their vape"
        await self._send_reaction(ctx, "smoke", None, None, verb)

    @command_meta(
        category="Fun",
        description="Sets your vape flavor, used by ,vape.",
        syntax=",vape flavor <flavor>",
        examples=[",vape flavor blue raspberry"],
    )
    @vape.command(name="flavor")
    async def vape_flavor(self, ctx: commands.Context, *, flavor: str):
        flavor = flavor.strip()[:64]
        async with get_session() as session:
            await fun_repository.set_vape_flavor(session, ctx.guild.id, ctx.author.id, flavor)
        await ctx.success(f"Your vape flavor is now set to **{flavor}**.")


    # ---------------------------------------------------------- tic-tac-toe

    @command_meta(
        category="Fun",
        description="Play tic-tac-toe against another member.",
        syntax=",tictactoe <opponent>",
        examples=[",tictactoe @User"],
        aliases=["ttt"],
    )
    @commands.hybrid_group(name="tictactoe", aliases=["ttt"], invoke_without_command=True)
    @commands.guild_only()
    async def tictactoe(self, ctx: commands.Context, opponent: discord.Member = None):
        if opponent is None:
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: You need to provide `opponent`.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        if opponent.id == ctx.author.id:
            await ctx.error("You can't play against yourself.")
            return
        if opponent.bot:
            await ctx.error("You can't play against a bot.")
            return
        if ctx.channel.id in _ttt_active_games:
            await ctx.error("There's already a tic-tac-toe game running in this channel.")
            return

        game = TicTacToeGame(ctx.author, opponent)
        _ttt_active_games[ctx.channel.id] = game
        view = TicTacToeView(game, ctx.channel.id)

        embed = discord.Embed(
            title="Tic-Tac-Toe",
            description=f"{ctx.author.mention} (X) vs {opponent.mention} (O)\n\n{ctx.author.mention}'s turn (X)",
        )
        await ctx.send(embed=embed, view=view)

    @tictactoe.command(name="help")
    async def tictactoe_help_cmd(self, ctx: commands.Context):
        from core.help_formatter import send_help
        await send_help(ctx, "tictactoe")

    @command_meta(
        category="Fun",
        description="Cancel the running tic-tac-toe game in this channel.",
        syntax=",ttt cancel",
        examples=[",ttt cancel"],
        require_args=False,
    )
    @tictactoe.command(name="cancel")
    async def tictactoe_cancel(self, ctx: commands.Context):
        game = _ttt_active_games.pop(ctx.channel.id, None)
        if game is None:
            await ctx.error("There's no tic-tac-toe game running in this channel.")
            return
        await ctx.success("Cancelled the tic-tac-toe game.")


    # ---------------------------------------------------------- pp

    @command_meta(
        category="Fun",
        description="Measure someone's... size.",
        syntax=",pp [member]",
        examples=[",pp", ",pp @User"],
        aliases=["dih"],
        require_args=False,
    )
    @commands.command(name="pp", aliases=["dih"])
    @commands.guild_only()
    async def pp(self, ctx: commands.Context, member: discord.Member = None):
        import random

        target = member or ctx.author
        size = random.Random(target.id).randint(0, 12)

        if target.id == ctx.author.id:
            text = f"{ctx.author.mention} Your dih is `{size} inches`"
        else:
            text = f"{ctx.author.mention} {target.mention}'s dih is `{size} inches`"

        embed = discord.Embed(description=text)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------- iq / how-x stat commands

    @command_meta(
        category="Fun",
        description="Measure someone's IQ.",
        syntax=",iq [member]",
        examples=[",iq", ",iq @User"],
        require_args=False,
    )
    @commands.command(name="iq")
    @commands.guild_only()
    async def iq(self, ctx: commands.Context, member: discord.Member = None):
        import random

        target = member or ctx.author
        score = random.Random(target.id).randint(50, 160)

        if target.id == ctx.author.id:
            text = f"{ctx.author.mention} Your IQ is `{score}`"
        else:
            text = f"{ctx.author.mention} {target.mention}'s IQ is `{score}`"

        await ctx.send(embed=discord.Embed(description=text))

    async def _how_stat(self, ctx: commands.Context, member: discord.Member | None, label: str, seed_salt: str) -> None:
        import random

        target = member or ctx.author
        percent = random.Random(f"{target.id}{seed_salt}").randint(0, 100)

        if target.id == ctx.author.id:
            text = f"{ctx.author.mention} You are `{percent}%` {label}"
        else:
            text = f"{ctx.author.mention} {target.mention} is `{percent}%` {label}"

        await ctx.send(embed=discord.Embed(description=text))

    @command_meta(
        category="Fun",
        description="Measure how gay someone is.",
        syntax=",howgay [member]",
        examples=[",howgay", ",howgay @User"],
        require_args=False,
    )
    @commands.command(name="howgay")
    @commands.guild_only()
    async def howgay(self, ctx: commands.Context, member: discord.Member = None):
        await self._how_stat(ctx, member, "gay", "gay")

    @command_meta(
        category="Fun",
        description="Measure how lesbian someone is.",
        syntax=",howlesbian [member]",
        examples=[",howlesbian", ",howlesbian @User"],
        require_args=False,
    )
    @commands.command(name="howlesbian")
    @commands.guild_only()
    async def howlesbian(self, ctx: commands.Context, member: discord.Member = None):
        await self._how_stat(ctx, member, "lesbian", "lesbian")

    @command_meta(
        category="Fun",
        description="Measure how autistic someone is.",
        syntax=",howautism [member]",
        examples=[",howautism", ",howautism @User"],
        require_args=False,
    )
    @commands.command(name="howautism")
    @commands.guild_only()
    async def howautism(self, ctx: commands.Context, member: discord.Member = None):
        await self._how_stat(ctx, member, "autistic", "autism")

    @command_meta(
        category="Fun",
        description="Measure how much of a simp someone is.",
        syntax=",howsimp [member]",
        examples=[",howsimp", ",howsimp @User"],
        require_args=False,
    )
    @commands.command(name="howsimp")
    @commands.guild_only()
    async def howsimp(self, ctx: commands.Context, member: discord.Member = None):
        await self._how_stat(ctx, member, "a simp", "simp")


    # ---------------------------------------------------------- blacktea

    @command_meta(
        category="Fun",
        description="Play a game of BlackTea - say a word containing the given letters.",
        syntax=",blacktea",
        examples=[",blacktea"],
        require_args=False,
    )
    @commands.group(name="blacktea", invoke_without_command=True)
    @commands.guild_only()
    async def blacktea(self, ctx: commands.Context):
        if ctx.channel.id in _blacktea_active_games:
            await ctx.error("There's already a BlackTea game running in this channel.")
            return

        game = BlackTeaGame(ctx.author, ctx.channel)
        _blacktea_active_games[ctx.channel.id] = game

        embed = discord.Embed(
            description=(
                "Waiting for players, react with `✅` to join. The game will begin in 30 seconds.\n\n"
                "`GOAL:` You have 10 seconds to say a word containing the given group of 3 letters. "
                "Failure to do so within the 10 seconds will lose a life. Each player has 2 lives to begin with.\n\n"
                "`NOTES:` A word can only be used once through the course of the game."
            )
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        join_message = await ctx.send(embed=embed)
        await join_message.add_reaction("✅")

        await asyncio.sleep(30)

        join_message = await ctx.channel.fetch_message(join_message.id)
        reaction = discord.utils.get(join_message.reactions, emoji="✅")
        players = []
        if reaction is not None:
            async for user in reaction.users():
                if not user.bot:
                    players.append(user)

        if len(players) < 2:
            _blacktea_active_games.pop(ctx.channel.id, None)
            embed = discord.Embed(
                description=f"⚠️ {ctx.author.mention}: Not enough players to start!",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        for player in players:
            game.lives[player.id] = 2
            game.members[player.id] = player
        game.turn_order = [p.id for p in players]
        random.shuffle(game.turn_order)

        await self._run_blacktea_game(ctx, game)

    async def _run_blacktea_game(self, ctx: commands.Context, game: "BlackTeaGame") -> None:
        turn_index = 0

        while sum(1 for pid in game.turn_order if game.lives.get(pid, 0) > 0) > 1:
            if game.ended:
                break

            current_id = game.turn_order[turn_index % len(game.turn_order)]
            turn_index += 1
            if game.lives.get(current_id, 0) <= 0:
                continue

            current_member = game.members[current_id]
            letters = random.choice(_BLACKTEA_TRIGRAMS)

            embed = discord.Embed(
                description=(
                    f"Say a word containing: `{letters.upper()}`\n\n"
                    f"You have **10 seconds**. Each player has **2 lives**."
                )
            )
            embed.set_footer(text=f"Lives remaining: {game.lives[current_id]}")
            await ctx.send(content=current_member.mention, embed=embed)

            def check(message: discord.Message) -> bool:
                if message.channel.id != ctx.channel.id or message.author.id != current_id:
                    return False
                word = message.content.strip().lower()
                if not word.isalpha():
                    return False
                if letters not in word:
                    return False
                if word in game.used_words:
                    return False
                return True

            try:
                message = await self.bot.wait_for("message", check=check, timeout=10)
            except asyncio.TimeoutError:
                if game.ended:
                    break
                game.lives[current_id] -= 1
                embed = discord.Embed(description=f"⏱️ {current_member.mention} ran out of time and lost a life!")
                if game.lives[current_id] <= 0:
                    embed.description += f"\n{current_member.mention} is **eliminated**."
                await ctx.send(embed=embed)
                continue

            game.used_words.add(message.content.strip().lower())
            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass

        _blacktea_active_games.pop(ctx.channel.id, None)
        if game.ended:
            return

        remaining = [pid for pid in game.turn_order if game.lives.get(pid, 0) > 0]
        if remaining:
            winner = game.members[remaining[0]]
            await ctx.send(embed=discord.Embed(description=f"🏆 {winner.mention} wins the game!"))
        else:
            await ctx.send(embed=discord.Embed(description="The game ended with no winner."))

    @blacktea.command(name="help")
    async def blacktea_help_cmd(self, ctx: commands.Context):
        from core.help_formatter import send_help
        await send_help(ctx, "blacktea")

    @command_meta(
        category="Fun",
        description="End the current BlackTea game.",
        syntax=",blacktea end",
        examples=[",blacktea end"],
        require_args=False,
    )
    @blacktea.command(name="end")
    async def blacktea_end(self, ctx: commands.Context):
        game = _blacktea_active_games.get(ctx.channel.id)
        if game is None:
            await ctx.error("There's no BlackTea game running in this channel.")
            return
        game.ended = True
        _blacktea_active_games.pop(ctx.channel.id, None)
        await ctx.success("Ended the BlackTea game.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
