import logging
from typing import List

import re
import random
import asyncio

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only

logger = logging.getLogger(__name__)


class PoissonConfig(SectionView):
    channels_exclude: List[discord.Channel]


class PoissonState(SectionView):
    factor: float


class Poisson(KazCog):
    """!kazhelp
    category: Commands
    brief: "Ceci n'est pas un poisson."
    description: "Ceci n'est pas un poisson."
    contents:
        - poisson
    """
    cog_config: PoissonConfig
    cog_state: PoissonState

    data = [
        (
            re.compile(r'\bfact\b', re.I), 0.25,
            ("Ninety per cent of most magic merely consists of knowing one extra fact.",)
        ),
        (
            re.compile(r'\bthump(er)?\b|\bcat\b|\bkitty\b', re.I), 0.30,
            ('Aull hail Thumper, Lourd aund Saviour of the Maple Leaf Mod Team!',)
        ),
        (
            re.compile(r'\bfuck', re.I), 0.15,
            ("https://tenor.com/view/gomen-naka-naori-kenka-ayamaru-gif-11957657",
             "https://tenor.com/view/kaede-girl-senpai-panda-gomen-gif-16026628")
        ),
        (
            re.compile(r'\bmagic', re.I), 0.15,
            ("... that’s why I don’t like magic, captain. ’Cos it’s magic. "
             "You can’t ask questions, it’s magic. It doesn’t explain anything, it’s magic. "
             "You don’t know where it comes from, it’s magic! "
             "That’s what I don’t like about magic, it does everything by magic!",)
        ),
        (
            re.compile(r'\bmov(e|ing)\b', re.I), 0.25,
            ("‘Magic is basically just movin’ stuff around,’ said Ridcully.",)
        ),
        (
            re.compile(r'\bdanger', re.I), 0.20,
            ("What was magic, after all, but something that happened at the snap of a finger? "
             "Where was the magic in that? It was mumbled words and weird drawings in old books "
             "and in the wrong hands it was dangerous as hell, but not one half as dangerous as "
             "it could be in the right hands.",)
        ),
        (
            re.compile(r'\b(stick|staff|rod|wand|mage|tree)\b', re.I), 0.10,
            ("The Archchancellor polished his staff as he walked along. It was a particularly "
             "good one, six feet long and quite magical. Not that he used magic very much."
             "In his experience, anything that couldn’t be disposed of with a couple of whacks "
             "from six feet of oak was probably immune to magic as well.",)
        ),
        (
            re.compile(r'anyone|intelligence|intelligent', re.I), 0.15,
            ("Anyone with a bit of intelligence and enough perseverance could do magic, "
             "which was why the wizards cloaked it with rituals and the whole pointy-hat business. "
             "The trick was to do magic and get away with it.",)
        ),
        (
            re.compile(r'\b(real|star|heart)\b', re.I), 0.10,
            ("Real magic is the hand around the bandsaw, the thrown spark in the powder keg, "
             "the dimension-warp linking you straight into the heart of a star, "
             "the flaming sword that burns all the way down to the pommel. Sooner juggle "
             "torches in a tar pit than mess with real magic. "
             "Sooner lie down in front of a thousand elephants.",)
        ),
        (
            re.compile(r'\b(Terry|Pratchett|TP)\b', re.I), 0.50,
            ("Magic never dies.  It merely fades away.",)
        )
    ]

    def __init__(self, bot):
        super().__init__(bot, 'poisson', PoissonConfig, PoissonState)
        self.cog_config.set_defaults(channels_exclude=[])
        self.cog_state.set_defaults(factor=1.0)
        self.channels_exclude = None

    async def on_ready(self):
        """
        Load information from the server.
        """
        await super().on_ready()

    @ready_only
    async def on_message(self, message: discord.Message):
        """
        Message handler. If keyword match, do a thing.
        """
        if message.channel.id in self.cog_config.channels_exclude:
            return

        if message.author.id == self.bot.user.id:
            return

        for entry in self.data:
            pattern = entry[0]
            p = entry[1] * self.cog_state.factor
            responses = entry[2]

            if pattern.search(message.content):
                logger.debug(f"Found match for pattern '{pattern.pattern}' ({p:.3f}) in message "
                            f"from {message.author.name} in #{message.channel.name}")
                if random.random() < p:
                    logger.info(f"Responding for pattern '{pattern.pattern}' in "
                                f"#{message.channel.name}")
                    response = random.choice(responses)
                    await self.bot.send_typing(message.channel)
                    await asyncio.sleep(min(10, random.random()*2.5 + 2.5))
                    await self.send_message(message.channel, response)
                    return  # don't look for more matches
                else:
                    logger.debug("Failed probability check. Not responding.")

    @commands.command(pass_context=True)
    @mod_only()
    async def poisson(self, ctx: commands.Context, factor: float):
        """!kazhelp
        description: |
            Set multiplication factor for this module's probabilities.
        """
        with self.cog_state as s:
            s.factor = factor
        await self.send_message(ctx.message.channel, ctx.message.author.mention +
            f' Set multiplier to {self.cog_state.factor}.')


def setup(bot):
    bot.add_cog(Poisson(bot))
