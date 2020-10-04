import logging

import discord

from kaztron import KazCog
from kaztron.config import SectionView

logger = logging.getLogger(__name__)


class WelcomeConfig(SectionView):
    channel_welcome: str
    channel_rules: str
    public_join: bool
    public_quit: bool


class Welcome(KazCog):
    """!kazhelp
    category: Automation
    brief: Welcomes new users to the server and logs users joining/leaving.
    description: |
        The Welcome cog welcomes new users to the server in the {{welcome_channel}} channel. This
        serves as a replacement to Discord's terrible built-in welcome messages. It also announces
        users who leave the server.

        This cog also logs users joining and leaving the server to {{output_channel}}, for
        moderation purposes, such as detecting raids, impersonation and ban evasion.

        It has no usable commands.
    """
    cog_config: WelcomeConfig

    def __init__(self, bot):
        super().__init__(bot, "welcome", WelcomeConfig)
        self.cog_config.set_defaults(public_join=True, public_quit=False)
        self.channel_welcome: discord.Channel = \
            discord.Object(id=self.cog_config.channel_welcome)

    async def on_ready(self):
        await super().on_ready()
        self.channel_welcome = self.get_channel(self.cog_config.channel_welcome)

    def export_kazhelp_vars(self):
        return {'welcome_channel': '#' + self.channel_welcome.name}

    async def on_member_join(self, member: discord.Member):
        """
        On member join, welcome the member and log their join to the output channel.
        """
        rules_channel = self.bot.get_channel(id=self.cog_config.channel_rules)
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at {2}'
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has joined the server."

        await self.send_output(out_fmt.format(member))
        if self.cog_config.public_join:
            await self.bot.send_message(self.channel_welcome, fmt.format(member, server,
                rules_channel.mention if rules_channel else "#welcome-rules-etc"))
        logger.info("New user welcomed: %s \n" % str(member))

    async def on_member_remove(self, member: discord.Member):
        """
        On member part, log the departure in the output channel and public channel.
        """
        server = member.server
        fmt = "{0.mention} has quit {1.name}! Fare thee well!"
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has left the server."
        await self.send_output(out_fmt.format(member))
        if self.cog_config.public_quit:
            await self.bot.send_message(self.channel_welcome, fmt.format(member, server))
        logger.info("User quit: %s \n" % str(member))


def setup(bot):
    bot.add_cog(Welcome(bot))
