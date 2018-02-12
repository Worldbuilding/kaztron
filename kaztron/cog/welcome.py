import logging

import discord

from kaztron.config import get_kaztron_config

logger = logging.getLogger(__name__)


class Welcome:
    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        self.dest_output = discord.Object(id=self.config.get('discord', 'channel_output'))
        self.dest_welcome = discord.Object(id=self.config.get("welcome", "channel_welcome"))

    async def on_member_join(self, member):
        """
        On member join, welcome the member and log their join to the output channel.
        """
        rules_channel = self.bot.get_channel(id=self.config.get("welcome", "channel_rules"))
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at {2}'
        out_fmt = "{0.mention} has joined the server."
        logger.info("New user welcomed: %s \n" % str(member))
        await self.bot.send_message(self.dest_welcome, fmt.format(member, server,
            rules_channel.mention if rules_channel else "#welcome-rules-etc"))
        await self.bot.send_message(self.dest_output, out_fmt.format(member))


def setup(bot):
    bot.add_cog(Welcome(bot))
