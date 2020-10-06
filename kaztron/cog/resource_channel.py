import logging
import re
from typing import Union, List, Pattern

import discord

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.kazcog import ready_only

logger = logging.getLogger(__name__)


class ResourceChannelConfig(SectionView):
    """
    :ivar channel: Resources channel ID
    :ivar reactions: list of reactions to add to identified resources. Can be Unicode emoji or
        custom server emoticon given in the form :name:123456789012345678. (You can backslash-escape
        the emoticon in Discord to get this form.)
    :ivar allow_strings: List of strings to search for. Any message containing one or more of these
        strings is considered a resource message.
    :ivar allow_re_strings: List of regular expressions to match against. Any message matching one
        or more of these patterns is considered a resource message.
    :ivar deny_strings: List of strings to search for to EXCLUDE a message as a resource. This takes
        priority over the "allow" configurations.
    :ivar deny_re_strings: List of regular expressions to match against to EXCLUDE a message as a
        resource. This takes priority over the "allow" configurations.
    """
    channel: discord.Channel
    reactions: List[Union[discord.Emoji, str]]
    allow_strings: List[str]
    allow_re_strings: List[Pattern]
    deny_strings: List[str]
    deny_re_strings: List[Pattern]
    allow_uploads: bool


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
            deny_re_strings=tuple(),
            allow_uploads=True
        )
        self.cog_config.set_converters('channel', lambda id_: self.get_channel(id_), None)
        self.cog_config.set_converters('allow_re_strings',
                                       lambda l: list(re.compile(s) for s in l), None)
        self.cog_config.set_converters('deny_re_strings',
                                       lambda l: list(re.compile(s) for s in l), None)

    async def on_ready(self):
        await super().on_ready()

    @ready_only
    async def on_message(self, message: discord.Message):
        """ Message handler. Auto-upvotes valid resource messages. """

        # resource channel only
        if message.channel != self.cog_config.channel:
            return

        # don't react to self
        if message.author == self.bot.user:
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
        if self.cog_config.allow_uploads and message.attachments:
            return True
        if any(s in message.content for s in self.cog_config.allow_strings):
            return True
        if any(p.search(message.content) is not None for p in self.cog_config.allow_re_strings):
            return True


def setup(bot):
    bot.add_cog(ResourceChannelManager(bot))
