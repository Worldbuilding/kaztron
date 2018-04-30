import logging

import discord

from kaztron import KazCog

logger = logging.getLogger(__name__)


class Welcome(KazCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.channel_welcome = discord.Object(id=self.config.get("welcome", "channel_welcome"))

    async def on_member_join(self, member: discord.Member):
        """
        On member join, welcome the member and log their join to the output channel.
        """
        rules_channel = self.bot.get_channel(id=self.config.get("welcome", "channel_rules"))
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at {2}'
        out_fmt = "{0.mention} has joined the server."
        logger.info("New user welcomed: %s \n" % str(member))
        await self.bot.send_message(self.channel_welcome, fmt.format(member, server,
            rules_channel.mention if rules_channel else "#welcome-rules-etc"))
        await self.send_output(out_fmt.format(member))

    async def on_member_remove(self, member: discord.Member):
        """
        On member part, log the departure in the output channel.
        """
        out_fmt = "{0.mention} has left the server."
        logger.info("User parted: %s \n" % str(member))
        await self.send_output(out_fmt.format(member))


def setup(bot):
    bot.add_cog(Welcome(bot))
