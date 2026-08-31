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
        description="Kisses a member with a random anime gif, or just posts a kiss gif if no one is given.",
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
        description="Sends a random hug anime gif, optionally at a member.",
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
        description="Sends a random bite anime gif, optionally at a member.",
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
        description="Sends a random cuddle anime gif, optionally at a member.",
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
        description="Sends a random feed anime gif, optionally at a member.",
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
        description="Sends a random handhold anime gif, optionally at a member.",
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
        description="Sends a random handshake anime gif, optionally at a member.",
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
        description="Sends a random highfive anime gif, optionally at a member.",
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
        description="Sends a random laugh anime gif, optionally at a member.",
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
        description="Sends a random nod anime gif, optionally at a member.",
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
        description="Sends a random nom anime gif, optionally at a member.",
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
        description="Sends a random nope anime gif, optionally at a member.",
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
        description="Sends a random pat anime gif, optionally at a member.",
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
        description="Sends a random peck anime gif, optionally at a member.",
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
        description="Sends a random poke anime gif, optionally at a member.",
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
        description="Sends a random punch anime gif, optionally at a member.",
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
        description="Sends a random run anime gif, optionally at a member.",
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
        description="Sends a random shoot anime gif, optionally at a member.",
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
        description="Sends a random slap anime gif, optionally at a member.",
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
        description="Sends a random stare anime gif, optionally at a member.",
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
        description="Sends a random think anime gif, optionally at a member.",
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
        description="Sends a random thumbsup anime gif, optionally at a member.",
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
        description="Sends a random tickle anime gif, optionally at a member.",
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
        description="Sends a random wave anime gif, optionally at a member.",
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
        description="Sends a random wink anime gif, optionally at a member.",
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
        description="Sends a random yeet anime gif, optionally at a member.",
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
        description="Sends a random blush anime gif.",
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
        description="Sends a random bored anime gif.",
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
        description="Sends a random cry anime gif.",
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
        description="Sends a random facepalm anime gif.",
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
        description="Sends a random happy anime gif.",
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
        description="Sends a random lurk anime gif.",
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
        description="Sends a random pout anime gif.",
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
        description="Sends a random shrug anime gif.",
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
        description="Sends a random sleep anime gif.",
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
        description="Sends a random smile anime gif.",
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
        description="Sends a random smug anime gif.",
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
        description="Sends a random yawn anime gif.",
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
        description="Sends a random fuck gif (NSFW) - only usable in an NSFW channel, optionally at a member.",
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
        description="Sends a random nutkick gif (NSFW) - only usable in an NSFW channel, optionally at a member.",
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
        description="Sends a random spank gif (NSFW) - only usable in an NSFW channel, optionally at a member.",
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
        description="Ships two members and shows a compatibility percentage - or you and one member if only one is given.",
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

        embed = discord.Embed(
            title=f"{user1.display_name} 💞 {user2.display_name}",
            description=(
                f"Ship name: **{name}**\n"
                f"`{bar}` **{percentage}%**\n"
                f"{comment}"
            ),
        )
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))