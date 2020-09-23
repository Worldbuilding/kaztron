import logging
import re
from typing import Union, List, Pattern

import discord

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.kazcog import ready_only

logger = logging.getLogger(__name__)


class ResourceChannelConfig(SectionView):
    channel: discord.Channel                    # ID of the resources channel
    reactions: List[Union[discord.Emoji, str]]  # list of reactions to add to identified resources
    allow_strings: List[str]         # messages containing any of these strings are resources
    allow_re_strings: List[Pattern]  # messages matching any of these regexes are resources
    deny_strings: List[str]          # messages containing any of these strings are NOT resources
    deny_re_strings: List[Pattern]   # messages matching any of these regexes are NOT resources

    # Deny takes precedence over Allow.
    # The "reactions" list should be either the :name:ID of the custom emoji, or the Unicode emoji
    # for standard ones. To ensure the correct emoji strings are used, you can
    # backslash-escape the emoji in Discord and copy the resulting string. (If it comes out as
    # <:Name:123456789012345678>, then omit the <angle brackets>.)


class ResourceChannelManager(KazCog):
    """!kazhelp
    category: Moderator
    brief: "{{%resource_channel_name}} automation module"
    description: "Management and automation of the {{resource_channel_name}} channel."
    jekyll_description: |
        A collection of functionality to help manage the {{resource_channel_name}} channel.

        Current features:

        * Auto-upvote valid resources

        NOTE: Maintaining an automatic message in the channel can be achieved using the
        {{%InfoMessage}} cog.
    contents: []
    """
    cog_config: ResourceChannelConfig

    def __init__(self, bot):
        super().__init__(bot, 'resource_channel', ResourceChannelConfig)
        self.cog_config.set_defaults(
            reactions=["\uD83D\uDC4D", "\uD83D\uDC4E"],
            allow_strings=('http://', 'https://'),
            allow_re_strings=tuple(),
            deny_strings=tuple(),
            deny_re_strings=tuple()
        )
        self.cog_config.set_converters('channel', lambda id_: self.validate_channel(id_), None)
        self.cog_config.set_converters('allow_re_strings',
                                       lambda l: list(re.compile(s) for s in l), None)
        self.cog_config.set_converters('deny_re_strings',
                                       lambda l: list(re.compile(s) for s in l), None)

    async def on_ready(self):
        await super().on_ready()

    @ready_only
    async def on_message(self, message: discord.Message):
        """ Message handler. Auto-upvotes valid resource messages. """
        if message.channel.id != self.cog_config.channel.id:
            return

        if not self.is_resource_post(message):
            return

        message.author = message.author  # type: discord.Member
        logger.info("New #resources message from {} ({})".format(
            message.author.nick or message.author.name, message.author.id
        ))

        for reaction in self.cog_config.reactions:
            logger.info("Adding reaction '{}'".format(reaction))
            await self.bot.add_reaction(message, reaction)

    def is_resource_post(self, message: discord.Message):
        if any(s in message.content for s in self.cog_config.deny_strings):
            return False
        if any(p.search(message.content) is not None for p in self.cog_config.deny_re_strings):
            return False
        if any(s in message.content for s in self.cog_config.allow_strings):
            return True
        if any(p.search(message.content) is not None for p in self.cog_config.allow_re_strings):
            return True


def setup(bot):
    bot.add_cog(ResourceChannelManager(bot))
