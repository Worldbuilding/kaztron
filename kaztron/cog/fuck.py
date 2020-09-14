import logging
import random

import discord
from discord.ext import commands

from kaztron import KazCog

logger = logging.getLogger(__name__)


class FuckCog(KazCog):
    FUCK_LIST = [
        "https://tenor.com/view/gomen-naka-naori-kenka-ayamaru-gif-11957657",
        "https://tenor.com/view/kaede-girl-senpai-panda-gomen-gif-16026628"
    ]

    @commands.command(pass_context=True)
    async def fuck(self, ctx: commands.Context):
        await self.send_message(ctx.message.channel, random.choice(self.FUCK_LIST))


def setup(bot):
    bot.add_cog(FuckCog(bot))
