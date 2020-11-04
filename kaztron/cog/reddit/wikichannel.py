from datetime import timedelta, datetime
import logging
from typing import List, Dict, Sequence, Set, Iterable, Tuple, Optional, Union

import discord
from discord.ext import commands

from kaztron import KazCog, task
from kaztron.config import SectionView
from kaztron.driver import reddit
from kaztron.utils.checks import mod_only
from kaztron.utils.datetime import format_timedelta, utctimestamp
from kaztron.utils.discord import get_group_help

from kaztron.utils.embeds import EmbedSplitter, Limits
from kaztron.utils.logging import exc_log_str, tb_log_str
from kaztron.utils.strings import split_chunks_on

logger = logging.getLogger(__name__)


def get_reddit_scopes():
    return 'identity', 'wikiread'


######
# DATA STORAGE/CONFIG STRUCTURES
######

class WikiChannelConfig(SectionView):
    """
    :ivar reddit_username: Username to use. If not specified, will use the first logged-in user.
    """
    reddit_username: str


class WikiChannelData:
    """
    :ivar wikipage: URL to the Reddit wiki page to mirror in channel
    :ivar last_revision: The revision last posted to channel
    :ivar channel: The Discord channel to post to
    :ivar messages: List of messages already posted
    """
    def __init__(self, *, wikipage: str, last_revision: str, channel: discord.Channel,
                 messages: Iterable[discord.Message]):
        self.wikipage = wikipage
        self.last_revision = last_revision
        self.channel = channel
        self.messages = list(messages)

    def to_dict(self):
        return {
            'wikipage': self.wikipage,
            'last_revision': self.last_revision,
            'channel': self.channel.id,
            'messages': [m.id for m in self.messages]
        }

    @staticmethod
    async def from_dict(bot: discord.Client, data: dict):
        ch = bot.get_channel(data['channel'])
        if ch is None:
            raise ValueError("Invalid channel {!r}".format(data['channel']))
        return WikiChannelData(
            wikipage=data['wikipage'],
            last_revision=data.get('last_revision', None),
            channel=ch,
            messages=[await bot.get_message(ch, m_id) for m_id in data.get('messages', [])]
        )


class WikiChannelState(SectionView):
    """
    :ivar queue: Queue of reddit submission IDs for each Discord channel.
    :ivar watch: Discord channels and the subreddit(s) they subwatch.
    """
    channels: Dict[discord.Channel, WikiChannelData]
    last_checked: datetime
    cog: KazCog

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__['cog'] = None
        self.set_converters('channels', self._get_channels, self._set_channels)
        self.set_converters('last_checked', datetime.utcfromtimestamp, utctimestamp)

    def set_cog(self, cog: KazCog):
        self.__dict__['cog'] = cog

    def _get_channels(self, data: List[dict]):
        return {
            self.cog.get_channel(channels_dict['channel']):
            WikiChannelData.from_dict(self.cog.bot, channels_dict)
            for channels_dict in data
        }

    @staticmethod
    def _set_channels(data: Dict[discord.Channel, WikiChannelData]) -> List[dict]:
        return [ch_data.to_dict() for ch_data in data.values()]


######
# PARSING INTERMEDIATE REPRESENTATION
######


class WikiStructure:
    pass


class WikiMessageBreak(WikiStructure):
    pass


class WikiSection(WikiStructure):
    def __init__(self, heading: Optional[str], text: str):
        self.heading = heading
        self.text = text


class WikiImage(WikiStructure):
    def __init__(self, url: str):
        self.url = url


class WikiParseError(Exception):
    pass


######
# BOT
######


class WikiChannel(KazCog):
    """!kazhelp
    category: Automation
    brief: Maintain a wiki page in a Discord channel.
    description: |
        This module mirrors one or more wiki pages in a Discord channel. Pages are updated upon a
        call to `.wikichannel update`.

        The raw wiki contents are interpreted as Discord message input, including Markdown.
        Any Markdown supported by Discord is supported by this module.

        The wiki page is automatically split in order to fit Discord message and embed limits.
        However, for more control over appearance, it is possible to manually define a message break
        within the wiki page.

        In addition, the following features are supported:

        * Headers. However, only one level of header is supported.
        * `---` defines a message break.
        * `IMG: <URL>`, as the only content in a message, where `<URL>` is the URL to an image file,
          will display that image in Discord. (This relies on the Discord client's image preview
          functionality.)

    contents:
        - wikichannel
            - update
            - preview
    """
    cog_config: WikiChannelConfig
    cog_state: WikiChannelState

    #####
    # Lifecycle
    #####

    def __init__(self, bot):
        super().__init__(bot, 'wikichannel', WikiChannelConfig, WikiChannelState)
        self.cog_config.set_defaults(
            reddit_username=None,
            check_interval=60
        )
        self.cog_state.set_defaults(
            channels=dict(),
            last_checked=0
        )
        self.reddit = None  # type: reddit.Reddit

    async def on_ready(self):
        await super().on_ready()
        self.cog_state.set_cog(self)
        _ = self.cog_state.channels  # convert and validate
        self.reddit = reddit.RedditLoginManager().get_reddit(self.cog_config.reddit_username)
        logger.info("Using reddit account: {}".format((await self.reddit.user.me()).name))

    #####
    # Core
    #####

    async def _update_wiki(self, channel: discord.Channel):
        """ Checks wiki pages configured for the specified channel and update them if needed. """
        # TODO:
        # - Check revision #S
        # - Check all messages still exist

    @staticmethod
    def _parse_wiki(text: str) -> List[WikiStructure]:
        lines = text.splitlines()
        items = []
        for line in lines:
            stripped_line = line.strip()
            if stripped_line == '---':
                items.append(WikiMessageBreak())
            elif stripped_line.startswith('#'):
                heading = stripped_line.strip("#").strip()
                items.append(WikiSection(heading=heading, text=''))
            elif stripped_line.startswith('IMG:'):
                url = stripped_line[4:].strip()
                if not url.startswith('http://') and not url.startswith('https://'):
                    raise WikiParseError('Invalid image URL: URL must use HTTP or HTTPS schema')
                items.append(WikiImage(url=url))
            else:
                if stripped_line:  # not an empty line
                    if isinstance(items[-1], WikiSection):
                        items[-1].text += '\n' + line
                    else:
                        items.append(WikiSection(heading=None, text=line))
                else:  # an empty line - only retain it within a section's text
                    if isinstance(items[-1], WikiSection):
                        items[-1].text += '\n' + line
        return items

    _MESSAGE_SPACER = '_ _\n'

    def _render(self, parsed: List[WikiStructure]) -> List[str]:
        items = []
        msg_break = False
        for i in parsed:
            if isinstance(i, WikiMessageBreak):
                pass
            elif isinstance(i, WikiImage):
                items.append(i.url)
            elif isinstance(i, WikiSection):
                if i.heading:
                    text = '**{}**\n\n{}'.format(i.heading, i.text.strip())
                else:
                    text = self._MESSAGE_SPACER + i.text.strip()

                split_text = split_chunks_on(text, Limits.MESSAGE)
                items.extend(split_text)
            else:
                items.append("**[WARNING] UNKNOWN WIKI STRUCTURE DURING RENDERING")
        return items

    def _render_embed(self, parsed: List[WikiStructure]) -> List[Union[str, EmbedSplitter]]:
        items = []
        msg_break = False
        for i in parsed:
            if isinstance(i, WikiMessageBreak):
                msg_break = True
            elif isinstance(i, WikiImage):
                msg_break = False
                items.append(i.url)
            elif isinstance(i, WikiSection):
                heading = i.heading or EmbedSplitter.Empty
                desc = i.text.strip()
                if msg_break or not isinstance(items[-1], EmbedSplitter):
                    if len(desc) <= Limits.EMBED_DESC:
                        items.append(EmbedSplitter(title=heading, description=desc))
                    else:
                        desc_split = split_chunks_on(desc, Limits.EMBED_FIELD_VALUE)
                        items.append(EmbedSplitter(title=heading, description=desc_split.pop(0)))
                        for s in desc_split:
                            items[-1].add_field(name=self._MESSAGE_SPACER, value=s, inline=False)
                else:
                    items[-1].add_field(name=heading, value=desc, inline=False)
                msg_break = False
            else:
                items.append("**[WARNING] UNKNOWN WIKI STRUCTURE DURING RENDERING")
        return items

    #####
    # Discord
    #####

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=True)
    async def wikichannel(self, ctx: commands.Context):
        """!kazhelp
        brief: Commands for maintaining a wiki page in a Discord channel.
        description: Commands for maintaining a wiki page in a Discord channel.
        """
        await self.bot.say(get_group_help(ctx))

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def update(self, ctx: commands.Context, channel: discord.Channel=None):
        """!kazhelp
        description: "TODO: KazHelp"
        """
        pass

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def preview(self, ctx: commands.Context, channel: discord.Channel=None):
        """!kazhelp
        brief: Preview the latest wiki page in-channel.
        description: |
            Preview the latest wiki page in the current channel. Careful, this could be spammy!
        parameters:
            - name: channel
              type: channel name
              description: Channel the wiki page would usually show up in.
        examples:
            - command: ".wikichannel preview #rules"
              description: Shows a preview of the wiki page in #rules.
        """
        pass

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def testfile(self, ctx: commands.Context):
        with open('test/wikichannel.txt') as f:
            s = f.read()
        p = self._parse_wiki(s)

        await self.send_message(ctx.message.channel, "**EMBED PREVIEW**")
        e = self._render_embed(p)
        for ee in e:
            if isinstance(ee, EmbedSplitter):
                await self.send_message(ctx.message.channel, embed=ee)
            else:
                await self.send_message(ctx.message.channel, ee)
        await self.send_message(ctx.message.channel, "**MESSAGE PREVIEW**")
        m = self._render(p)
        for mm in m:
            await self.send_message(ctx.message.channel, mm)

    @testfile.error
    async def testfile_error(self, exc: Exception, ctx: commands.Context):
        exc = exc.__cause__ if exc.__cause__ is not None else exc
        if isinstance(exc, IOError):
            await self.send_message(ctx.message.channel,
                "Error opening test file test/wikichannel.txt: {}".format(exc_log_str(exc)))
            logger.error("Error opening test file test/wikichannel.txt: {}".format(tb_log_str(exc)))
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(WikiChannel(bot))
