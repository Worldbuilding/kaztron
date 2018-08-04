import logging

import discord

from kaztron import KazCog

logger = logging.getLogger(__name__)


class Welcome(KazCog):
    """!kazhelp
    brief: Welcomes new users to the server and logs users joining/leaving.
    description: |
        The Welcome cog welcomes new users to the server in the {{welcome_channel}} channel. This
        serves as a replacement to Discord's terrible built-in welcome messages.

        This cog also logs users joining and leaving the server to {{output_channel}}, for
        moderation purposes, such as detecting raids, impersonation and ban evasion.

        It has no usable commands.
    """
    def __init__(self, bot):
        super().__init__(bot)
        self.channel_welcome: discord.Channel = \
            discord.Object(id=self.config.welcome.channel_welcome)

    async def on_ready(self):
        await super().on_ready()
        self.channel_welcome = self.validate_channel(self.config.welcome.channel_welcome)

    def export_kazhelp_vars(self):
        return {'welcome_channel': '#' + self.channel_welcome.name}

    async def on_member_join(self, member: discord.Member):
        """
        On member join, welcome the member and log their join to the output channel.
        """
        rules_channel = self.bot.get_channel(id=self.config.get("welcome", "channel_rules"))
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at {2}'
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has joined the server."
        logger.info("New user welcomed: %s \n" % str(member))
        await self.bot.send_message(self.channel_welcome, fmt.format(member, server,
            rules_channel.mention if rules_channel else "#welcome-rules-etc"))
        await self.send_output(out_fmt.format(member))

    async def on_member_remove(self, member: discord.Member):
        """
        On member part, log the departure in the output channel.
        """
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has left the server."
        logger.info("User parted: %s \n" % str(member))
        await self.send_output(out_fmt.format(member))


def setup(bot):
    bot.add_cog(Welcome(bot))
