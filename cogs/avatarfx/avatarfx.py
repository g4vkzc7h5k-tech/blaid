"""
Avatar manipulation effects - ,invert, ,blur, ,glitch, etc. Category
"Manipulation". Anyone can use these; the bot itself needs Embed
Links + Attach Files in the channel to post the result image.

HONEST SCOPE: this covers every effect from the original list EXCEPT
the ones that are genuinely meme TEMPLATES needing a real image asset
supplied separately - drake, pooh, oogway, sadcat, wanted, patpat,
bonks, gun, calling, captcha, console, ipcam, phone, laundry, gallery,
print, billboard, cinema, tv, supreme, alert. Everything else (74
effects) is pure code, no external images needed.
"""

from __future__ import annotations

import io

import discord
from discord.ext import commands

from core.command_meta import command_meta
from services import avatar_fx_service


class AvatarFx(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _run_effect(self, ctx: commands.Context, member: discord.Member | None, effect_fn, name: str) -> None:
        target = member or ctx.author

        async with ctx.typing():
            avatar_bytes = await target.display_avatar.with_size(512).with_format("png").read()
            source = io.BytesIO(avatar_bytes)

            try:
                from PIL import Image

                img = Image.open(source)
                result = await self.bot.loop.run_in_executor(None, effect_fn, img)

                buffer = io.BytesIO()
                result.save(buffer, format="PNG")
                buffer.seek(0)
            except Exception:
                await ctx.error(f"Couldn't apply the `{name}` effect to that avatar.")
                return

        file = discord.File(buffer, filename=f"{name}.png")
        embed = discord.Embed()
        embed.set_image(url=f"attachment://{name}.png")
        await ctx.send(embed=embed, file=file)


    @command_meta(
        category="Manipulation",
        description="Applies the invert effect to an avatar.",
        syntax=",invert [member]",
        examples=[",invert", ",invert @User"],
        require_args=False,
    )
    @commands.command(name="invert", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_invert(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_invert, "invert")

    @command_meta(
        category="Manipulation",
        description="Applies the halfinvert effect to an avatar.",
        syntax=",halfinvert [member]",
        examples=[",halfinvert", ",halfinvert @User"],
        require_args=False,
    )
    @commands.command(name="halfinvert", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_halfinvert(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_halfinvert, "halfinvert")

    @command_meta(
        category="Manipulation",
        description="Applies the blur effect to an avatar.",
        syntax=",blur [member]",
        examples=[",blur", ",blur @User"],
        require_args=False,
    )
    @commands.command(name="blur", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_blur(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_blur, "blur")

    @command_meta(
        category="Manipulation",
        description="Applies the neon effect to an avatar.",
        syntax=",neon [member]",
        examples=[",neon", ",neon @User"],
        require_args=False,
    )
    @commands.command(name="neon", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_neon(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_neon, "neon")

    @command_meta(
        category="Manipulation",
        description="Applies the cartoon effect to an avatar.",
        syntax=",cartoon [member]",
        examples=[",cartoon", ",cartoon @User"],
        require_args=False,
    )
    @commands.command(name="cartoon", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_cartoon(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_cartoon, "cartoon")

    @command_meta(
        category="Manipulation",
        description="Applies the painting effect to an avatar.",
        syntax=",painting [member]",
        examples=[",painting", ",painting @User"],
        require_args=False,
    )
    @commands.command(name="painting", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_painting(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_painting, "painting")

    @command_meta(
        category="Manipulation",
        description="Applies the lines effect to an avatar.",
        syntax=",lines [member]",
        examples=[",lines", ",lines @User"],
        require_args=False,
    )
    @commands.command(name="lines", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_lines(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_lines, "lines")

    @command_meta(
        category="Manipulation",
        description="Applies the matrix effect to an avatar.",
        syntax=",matrix [member]",
        examples=[",matrix", ",matrix @User"],
        require_args=False,
    )
    @commands.command(name="matrix", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_matrix(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_matrix, "matrix")

    @command_meta(
        category="Manipulation",
        description="Applies the lsd effect to an avatar.",
        syntax=",lsd [member]",
        examples=[",lsd", ",lsd @User"],
        require_args=False,
    )
    @commands.command(name="lsd", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_lsd(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_lsd, "lsd")

    @command_meta(
        category="Manipulation",
        description="Applies the gameboy effect to an avatar.",
        syntax=",gameboy [member]",
        examples=[",gameboy", ",gameboy @User"],
        require_args=False,
    )
    @commands.command(name="gameboy", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_gameboy(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_gameboy, "gameboy")

    @command_meta(
        category="Manipulation",
        description="Applies the dither effect to an avatar.",
        syntax=",dither [member]",
        examples=[",dither", ",dither @User"],
        require_args=False,
    )
    @commands.command(name="dither", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_dither(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_dither, "dither")

    @command_meta(
        category="Manipulation",
        description="Applies the bayer effect to an avatar.",
        syntax=",bayer [member]",
        examples=[",bayer", ",bayer @User"],
        require_args=False,
    )
    @commands.command(name="bayer", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_bayer(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_bayer, "bayer")

    @command_meta(
        category="Manipulation",
        description="Applies the blocks effect to an avatar.",
        syntax=",blocks [member]",
        examples=[",blocks", ",blocks @User"],
        require_args=False,
    )
    @commands.command(name="blocks", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_blocks(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_blocks, "blocks")

    @command_meta(
        category="Manipulation",
        description="Applies the tiles effect to an avatar.",
        syntax=",tiles [member]",
        examples=[",tiles", ",tiles @User"],
        require_args=False,
    )
    @commands.command(name="tiles", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_tiles(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_tiles, "tiles")

    @command_meta(
        category="Manipulation",
        description="Applies the pattern effect to an avatar.",
        syntax=",pattern [member]",
        examples=[",pattern", ",pattern @User"],
        require_args=False,
    )
    @commands.command(name="pattern", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_pattern(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_pattern, "pattern")

    @command_meta(
        category="Manipulation",
        description="Applies the wiggle effect to an avatar.",
        syntax=",wiggle [member]",
        examples=[",wiggle", ",wiggle @User"],
        require_args=False,
    )
    @commands.command(name="wiggle", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_wiggle(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_wiggle, "wiggle")

    @command_meta(
        category="Manipulation",
        description="Applies the earthquake effect to an avatar.",
        syntax=",earthquake [member]",
        examples=[",earthquake", ",earthquake @User"],
        require_args=False,
    )
    @commands.command(name="earthquake", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_earthquake(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_earthquake, "earthquake")

    @command_meta(
        category="Manipulation",
        description="Applies the glitch effect to an avatar.",
        syntax=",glitch [member]",
        examples=[",glitch", ",glitch @User"],
        require_args=False,
    )
    @commands.command(name="glitch", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_glitch(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_glitch, "glitch")

    @command_meta(
        category="Manipulation",
        description="Applies the shred effect to an avatar.",
        syntax=",shred [member]",
        examples=[",shred", ",shred @User"],
        require_args=False,
    )
    @commands.command(name="shred", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_shred(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_shred, "shred")

    @command_meta(
        category="Manipulation",
        description="Applies the slice effect to an avatar.",
        syntax=",slice [member]",
        examples=[",slice", ",slice @User"],
        require_args=False,
    )
    @commands.command(name="slice", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_slice(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_slice, "slice")

    @command_meta(
        category="Manipulation",
        description="Applies the shear effect to an avatar.",
        syntax=",shear [member]",
        examples=[",shear", ",shear @User"],
        require_args=False,
    )
    @commands.command(name="shear", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_shear(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_shear, "shear")

    @command_meta(
        category="Manipulation",
        description="Applies the stretch effect to an avatar.",
        syntax=",stretch [member]",
        examples=[",stretch", ",stretch @User"],
        require_args=False,
    )
    @commands.command(name="stretch", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_stretch(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_stretch, "stretch")

    @command_meta(
        category="Manipulation",
        description="Applies the spin effect to an avatar.",
        syntax=",spin [member]",
        examples=[",spin", ",spin @User"],
        require_args=False,
    )
    @commands.command(name="spin", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_spin(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_spin, "spin")

    @command_meta(
        category="Manipulation",
        description="Applies the dizzy effect to an avatar.",
        syntax=",dizzy [member]",
        examples=[",dizzy", ",dizzy @User"],
        require_args=False,
    )
    @commands.command(name="dizzy", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_dizzy(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_dizzy, "dizzy")

    @command_meta(
        category="Manipulation",
        description="Applies the globe effect to an avatar.",
        syntax=",globe [member]",
        examples=[",globe", ",globe @User"],
        require_args=False,
    )
    @commands.command(name="globe", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_globe(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_globe, "globe")

    @command_meta(
        category="Manipulation",
        description="Applies the warp effect to an avatar.",
        syntax=",warp [member]",
        examples=[",warp", ",warp @User"],
        require_args=False,
    )
    @commands.command(name="warp", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_warp(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_warp, "warp")

    @command_meta(
        category="Manipulation",
        description="Applies the magnify effect to an avatar.",
        syntax=",magnify [member]",
        examples=[",magnify", ",magnify @User"],
        require_args=False,
    )
    @commands.command(name="magnify", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_magnify(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_magnify, "magnify")

    @command_meta(
        category="Manipulation",
        description="Applies the boil effect to an avatar.",
        syntax=",boil [member]",
        examples=[",boil", ",boil @User"],
        require_args=False,
    )
    @commands.command(name="boil", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_boil(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_boil, "boil")

    @command_meta(
        category="Manipulation",
        description="Applies the liquefy effect to an avatar.",
        syntax=",liquefy [member]",
        examples=[",liquefy", ",liquefy @User"],
        require_args=False,
    )
    @commands.command(name="liquefy", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_liquefy(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_liquefy, "liquefy")

    @command_meta(
        category="Manipulation",
        description="Applies the flush effect to an avatar.",
        syntax=",flush [member]",
        examples=[",flush", ",flush @User"],
        require_args=False,
    )
    @commands.command(name="flush", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_flush(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_flush, "flush")

    @command_meta(
        category="Manipulation",
        description="Applies the drip effect to an avatar.",
        syntax=",drip [member]",
        examples=[",drip", ",drip @User"],
        require_args=False,
    )
    @commands.command(name="drip", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_drip(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_drip, "drip")

    @command_meta(
        category="Manipulation",
        description="Applies the fall effect to an avatar.",
        syntax=",fall [member]",
        examples=[",fall", ",fall @User"],
        require_args=False,
    )
    @commands.command(name="fall", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_fall(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_fall, "fall")

    @command_meta(
        category="Manipulation",
        description="Applies the melt effect to an avatar.",
        syntax=",melt [member]",
        examples=[",melt", ",melt @User"],
        require_args=False,
    )
    @commands.command(name="melt", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_melt(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_melt, "melt")

    @command_meta(
        category="Manipulation",
        description="Applies the tunnel effect to an avatar.",
        syntax=",tunnel [member]",
        examples=[",tunnel", ",tunnel @User"],
        require_args=False,
    )
    @commands.command(name="tunnel", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_tunnel(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_tunnel, "tunnel")

    @command_meta(
        category="Manipulation",
        description="Applies the endless effect to an avatar.",
        syntax=",endless [member]",
        examples=[",endless", ",endless @User"],
        require_args=False,
    )
    @commands.command(name="endless", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_endless(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_endless, "endless")

    @command_meta(
        category="Manipulation",
        description="Applies the infinity effect to an avatar.",
        syntax=",infinity [member]",
        examples=[",infinity", ",infinity @User"],
        require_args=False,
    )
    @commands.command(name="infinity", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_infinity(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_infinity, "infinity")

    @command_meta(
        category="Manipulation",
        description="Applies the radiate effect to an avatar.",
        syntax=",radiate [member]",
        examples=[",radiate", ",radiate @User"],
        require_args=False,
    )
    @commands.command(name="radiate", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_radiate(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_radiate, "radiate")

    @command_meta(
        category="Manipulation",
        description="Applies the shine effect to an avatar.",
        syntax=",shine [member]",
        examples=[",shine", ",shine @User"],
        require_args=False,
    )
    @commands.command(name="shine", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_shine(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_shine, "shine")

    @command_meta(
        category="Manipulation",
        description="Applies the rain effect to an avatar.",
        syntax=",rain [member]",
        examples=[",rain", ",rain @User"],
        require_args=False,
    )
    @commands.command(name="rain", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_rain(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_rain, "rain")

    @command_meta(
        category="Manipulation",
        description="Applies the fire effect to an avatar.",
        syntax=",fire [member]",
        examples=[",fire", ",fire @User"],
        require_args=False,
    )
    @commands.command(name="fire", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_fire(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_fire, "fire")

    @command_meta(
        category="Manipulation",
        description="Applies the lamp effect to an avatar.",
        syntax=",lamp [member]",
        examples=[",lamp", ",lamp @User"],
        require_args=False,
    )
    @commands.command(name="lamp", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_lamp(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_lamp, "lamp")

    @command_meta(
        category="Manipulation",
        description="Applies the reflection effect to an avatar.",
        syntax=",reflection [member]",
        examples=[",reflection", ",reflection @User"],
        require_args=False,
    )
    @commands.command(name="reflection", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_reflection(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_reflection, "reflection")

    @command_meta(
        category="Manipulation",
        description="Applies the stereo effect to an avatar.",
        syntax=",stereo [member]",
        examples=[",stereo", ",stereo @User"],
        require_args=False,
    )
    @commands.command(name="stereo", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_stereo(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_stereo, "stereo")

    @command_meta(
        category="Manipulation",
        description="Applies the phase effect to an avatar.",
        syntax=",phase [member]",
        examples=[",phase", ",phase @User"],
        require_args=False,
    )
    @commands.command(name="phase", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_phase(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_phase, "phase")

    @command_meta(
        category="Manipulation",
        description="Applies the layers effect to an avatar.",
        syntax=",layers [member]",
        examples=[",layers", ",layers @User"],
        require_args=False,
    )
    @commands.command(name="layers", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_layers(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_layers, "layers")

    @command_meta(
        category="Manipulation",
        description="Applies the optics effect to an avatar.",
        syntax=",optics [member]",
        examples=[",optics", ",optics @User"],
        require_args=False,
    )
    @commands.command(name="optics", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_optics(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_optics, "optics")

    @command_meta(
        category="Manipulation",
        description="Applies the bevel effect to an avatar.",
        syntax=",bevel [member]",
        examples=[",bevel", ",bevel @User"],
        require_args=False,
    )
    @commands.command(name="bevel", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_bevel(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_bevel, "bevel")

    @command_meta(
        category="Manipulation",
        description="Applies the 3d effect to an avatar.",
        syntax=",3d [member]",
        examples=[",3d", ",3d @User"],
        require_args=False,
    )
    @commands.command(name="3d", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_n3d(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_3d, "3d")

    @command_meta(
        category="Manipulation",
        description="Applies the letters effect to an avatar.",
        syntax=",letters [member]",
        examples=[",letters", ",letters @User"],
        require_args=False,
    )
    @commands.command(name="letters", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_letters(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_letters, "letters")

    @command_meta(
        category="Manipulation",
        description="Applies the knit effect to an avatar.",
        syntax=",knit [member]",
        examples=[",knit", ",knit @User"],
        require_args=False,
    )
    @commands.command(name="knit", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_knit(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_knit, "knit")

    @command_meta(
        category="Manipulation",
        description="Applies the cow effect to an avatar.",
        syntax=",cow [member]",
        examples=[",cow", ",cow @User"],
        require_args=False,
    )
    @commands.command(name="cow", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_cow(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_cow, "cow")

    @command_meta(
        category="Manipulation",
        description="Applies the cracks effect to an avatar.",
        syntax=",cracks [member]",
        examples=[",cracks", ",cracks @User"],
        require_args=False,
    )
    @commands.command(name="cracks", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_cracks(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_cracks, "cracks")

    @command_meta(
        category="Manipulation",
        description="Applies the shock effect to an avatar.",
        syntax=",shock [member]",
        examples=[",shock", ",shock @User"],
        require_args=False,
    )
    @commands.command(name="shock", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_shock(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_shock, "shock")

    @command_meta(
        category="Manipulation",
        description="Applies the soap effect to an avatar.",
        syntax=",soap [member]",
        examples=[",soap", ",soap @User"],
        require_args=False,
    )
    @commands.command(name="soap", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_soap(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_soap, "soap")

    @command_meta(
        category="Manipulation",
        description="Applies the ads effect to an avatar.",
        syntax=",ads [member]",
        examples=[",ads", ",ads @User"],
        require_args=False,
    )
    @commands.command(name="ads", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_ads(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_ads, "ads")

    @command_meta(
        category="Manipulation",
        description="Applies the sensitive effect to an avatar.",
        syntax=",sensitive [member]",
        examples=[",sensitive", ",sensitive @User"],
        require_args=False,
    )
    @commands.command(name="sensitive", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_sensitive(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_sensitive, "sensitive")

    @command_meta(
        category="Manipulation",
        description="Applies the explicit effect to an avatar.",
        syntax=",explicit [member]",
        examples=[",explicit", ",explicit @User"],
        require_args=False,
    )
    @commands.command(name="explicit", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_explicit(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_explicit, "explicit")

    @command_meta(
        category="Manipulation",
        description="Applies the canny effect to an avatar.",
        syntax=",canny [member]",
        examples=[",canny", ",canny @User"],
        require_args=False,
    )
    @commands.command(name="canny", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_canny(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_canny, "canny")

    @command_meta(
        category="Manipulation",
        description="Applies the cube effect to an avatar.",
        syntax=",cube [member]",
        examples=[",cube", ",cube @User"],
        require_args=False,
    )
    @commands.command(name="cube", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_cube(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_cube, "cube")

    @command_meta(
        category="Manipulation",
        description="Applies the didyoumean effect to an avatar.",
        syntax=",didyoumean [member]",
        examples=[",didyoumean", ",didyoumean @User"],
        require_args=False,
    )
    @commands.command(name="didyoumean", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_didyoumean(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_didyoumean, "didyoumean")

    @command_meta(
        category="Manipulation",
        description="Applies the emojify effect to an avatar.",
        syntax=",emojify [member]",
        examples=[",emojify", ",emojify @User"],
        require_args=False,
    )
    @commands.command(name="emojify", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_emojify(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_emojify, "emojify")

    @command_meta(
        category="Manipulation",
        description="Applies the fan effect to an avatar.",
        syntax=",fan [member]",
        examples=[",fan", ",fan @User"],
        require_args=False,
    )
    @commands.command(name="fan", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_fan(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_fan, "fan")

    @command_meta(
        category="Manipulation",
        description="Applies the hearts effect to an avatar.",
        syntax=",hearts [member]",
        examples=[",hearts", ",hearts @User"],
        require_args=False,
    )
    @commands.command(name="hearts", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_hearts(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_hearts, "hearts")

    @command_meta(
        category="Manipulation",
        description="Applies the logoff effect to an avatar.",
        syntax=",logoff [member]",
        examples=[",logoff", ",logoff @User"],
        require_args=False,
    )
    @commands.command(name="logoff", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_logoff(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_logoff, "logoff")

    @command_meta(
        category="Manipulation",
        description="Applies the paparazzi effect to an avatar.",
        syntax=",paparazzi [member]",
        examples=[",paparazzi", ",paparazzi @User"],
        require_args=False,
    )
    @commands.command(name="paparazzi", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_paparazzi(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_paparazzi, "paparazzi")

    @command_meta(
        category="Manipulation",
        description="Applies the plank effect to an avatar.",
        syntax=",plank [member]",
        examples=[",plank", ",plank @User"],
        require_args=False,
    )
    @commands.command(name="plank", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_plank(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_plank, "plank")

    @command_meta(
        category="Manipulation",
        description="Applies the plates effect to an avatar.",
        syntax=",plates [member]",
        examples=[",plates", ",plates @User"],
        require_args=False,
    )
    @commands.command(name="plates", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_plates(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_plates, "plates")

    @command_meta(
        category="Manipulation",
        description="Applies the poly effect to an avatar.",
        syntax=",poly [member]",
        examples=[",poly", ",poly @User"],
        require_args=False,
    )
    @commands.command(name="poly", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_poly(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_poly, "poly")

    @command_meta(
        category="Manipulation",
        description="Applies the pyramid effect to an avatar.",
        syntax=",pyramid [member]",
        examples=[",pyramid", ",pyramid @User"],
        require_args=False,
    )
    @commands.command(name="pyramid", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_pyramid(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_pyramid, "pyramid")

    @command_meta(
        category="Manipulation",
        description="Applies the ripped effect to an avatar.",
        syntax=",ripped [member]",
        examples=[",ripped", ",ripped @User"],
        require_args=False,
    )
    @commands.command(name="ripped", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_ripped(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_ripped, "ripped")

    @command_meta(
        category="Manipulation",
        description="Applies the wall effect to an avatar.",
        syntax=",wall [member]",
        examples=[",wall", ",wall @User"],
        require_args=False,
    )
    @commands.command(name="wall", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_wall(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_wall, "wall")

    @command_meta(
        category="Manipulation",
        description="Applies the zonk effect to an avatar.",
        syntax=",zonk [member]",
        examples=[",zonk", ",zonk @User"],
        require_args=False,
    )
    @commands.command(name="zonk", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_zonk(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_zonk, "zonk")

    @command_meta(
        category="Manipulation",
        description="Applies the equations effect to an avatar.",
        syntax=",equations [member]",
        examples=[",equations", ",equations @User"],
        require_args=False,
    )
    @commands.command(name="equations", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_equations(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_equations, "equations")

    @command_meta(
        category="Manipulation",
        description="Applies the facts effect to an avatar.",
        syntax=",facts [member]",
        examples=[",facts", ",facts @User"],
        require_args=False,
    )
    @commands.command(name="facts", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def cmd_facts(self, ctx: commands.Context, member: discord.Member = None):
        await self._run_effect(ctx, member, avatar_fx_service.fx_facts, "facts")

async def setup(bot: commands.Bot):
    await bot.add_cog(AvatarFx(bot))
