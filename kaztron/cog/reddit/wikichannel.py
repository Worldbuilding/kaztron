from datetime import datetime
import logging
from typing import List, Dict, Iterable, Optional, Union

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.driver import reddit
from kaztron.utils.checks import mod_only
from kaztron.utils.datetime import utctimestamp

from kaztron.utils.embeds import EmbedSplitter, Limits
from kaztron.utils.logging import exc_log_str, tb_log_str
from kaztron.utils.strings import split_chunks_on, natural_truncate

logger = logging.getLogger(__name__)
WikiPage = reddit.models.WikiPage


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
    :ivar messages: List of IDs to messages already posted
    """
    def __init__(self, *, subreddit: str, wikipage: str, last_revision: int,
                 channel: discord.Channel, messages: Iterable[str]):
        self.subreddit = subreddit
        self.wikipage = wikipage
        self.last_revision = last_revision
        self.channel = channel
        self.messages = list(messages)

    def to_dict(self):
        return {
            'subreddit': self.subreddit,
            'wikipage': self.wikipage,
            'last_revision': self.last_revision,
            'channel': self.channel.id,
            'messages': self.messages
        }

    @staticmethod
    def from_dict(bot: discord.Client, data: dict):
        ch = bot.get_channel(data['channel'])
        if ch is None:
            raise ValueError("Invalid channel {!r}".format(data['channel']))
        return WikiChannelData(
            subreddit=data['subreddit'],
            wikipage=data['wikipage'],
            last_revision=data.get('last_revision', 0),
            channel=ch,
            messages=data.get('messages', [])
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
        call to `.wikichannel refresh`.

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
        - wikichannel:
            - remove
            - refresh
            - preview
            - testfile
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
    # Reddit
    #####

    async def _update_wiki(self, channel: discord.Channel):
        """
        Checks wiki pages configured for the specified channel and update them if needed.
        """
        data = self.cog_state.channels[channel]
        with self.cog_state as state:
            data = state.channels[channel]
            logger.info("Updating wiki page {} in channel #{}".format(data.wikipage, channel.name))
            await self._delete_messages(data)
            # end of this context so that the deletion is written/persisted in case of later errors
        with self.cog_state as state:
            await self._post_wikichannel(state.channels[channel])

    async def _delete_messages(self, data: WikiChannelData):
        """ Delete Discord messages for a WikiChannel. Modifies the :param:`data` structure. """
        if data.messages:
            logger.info("Deleting wikichannel messages for #{}...".format(data.channel.name))
            del_msgs = []
            for msg_id in data.messages:
                try:
                    del_msgs.append(await self.bot.get_message(data.channel, msg_id))
                except discord.NotFound:
                    logger.warning("Skipping message, not found: {}".format(msg_id))
            if len(del_msgs) > 1:
                await self.bot.delete_messages(del_msgs)
            elif len(del_msgs) == 1:
                await self.bot.delete_message(del_msgs[0])
            else:
                logger.warning("No valid messages to delete.")
            data.messages.clear()

    async def _post_wikichannel(self, data: WikiChannelData, channel: discord.Channel=None):
        """
        Post wikichannel messages to a channel. If channel isn't specified, defaults to the
        channel configured by :param:`data`.

        If channel is specified, posts to that channel and does not update the `data` structure's
        message list (preview mode).
        """
        if channel is None:
            channel = data.channel
            is_preview = False
        else:
            is_preview = True

        sr = await self.reddit.subreddit(data.subreddit)  # type: reddit.models.Subreddit
        page = await sr.wiki.get_page(data.wikipage)  # type: reddit.models.WikiPage
        page_parsed = self._parse_wiki(page.content_md)
        page_embed = self._render_embed(page_parsed)
        messages = []  # type: List[discord.Message]
        for embed in page_embed:
            if isinstance(embed, EmbedSplitter):
                messages.extend(await self.send_message(channel, embed=embed))
            else:
                messages.extend(await self.send_message(channel, embed))
        if not is_preview:
            data.messages.extend(message.id for message in messages)

    #####
    # Parsing/rendering for Discord
    #####

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
                if msg_break or not items or not isinstance(items[-1], EmbedSplitter):
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

    @commands.group(invoke_without_command=True, pass_context=True)
    async def wikichannel(self, ctx: commands.Context,
                          channel: discord.Channel, subreddit: str, page_name: str):
        """!kazhelp
        brief: Set or modify a wiki channel.
        description: |
            Set or change the wiki page that a channel mirrors.
        parameters:
            - name: channel
              type: channel name
              description: Discord channel to update.
            - name: subreddit
              type: string
              description: Name of subreddit of wiki page.
            - name: page_name
              type: string
              description: Name of wiki page.
        examples:
            - command: ".wikichannel #rules mysubreddit rules"
              description: set #rules
        """
        logger.info("Configuring wikichannel for #{}...".format(channel.name))
        sr = await self.reddit.subreddit(subreddit)  # type: reddit.models.Subreddit
        page = await sr.wiki.get_page(page_name)  # type: reddit.models.WikiPage
        page_preview = natural_truncate(page.content_md, 128)
        try:
            with self.cog_state as state:
                state.channels[channel].subreddit = subreddit
                state.channels[channel].wikipage = page_name
                state.channels[channel].last_revision = 0
                state.channels[channel].channel = channel
                # don't overwrite messages - still want to delete discord messages on update
            logger.debug("Updated channel data.")
        except KeyError:
            with self.cog_state as state:
                state.channels[channel] = WikiChannelData(
                    subreddit=subreddit,
                    wikipage=page_name,
                    last_revision=0,
                    channel=channel,
                    messages=tuple())
            logger.debug("Channel not previously configured: added channel data.")
        await self.send_message(ctx.message.channel, ctx.message.author.mention + " " +
            ("Configured channel {} to mirror wiki page /r/{}/wiki/{}. Use `.wikichannel refresh` "
            "to update the channel with the new page text. Contents preview:\n\n```{}```")
            .format(channel.mention, subreddit, page_name, page_preview))

    @wikichannel.command(pass_context=True, aliases=['rem'])
    async def remove(self, ctx: commands.Context, channel: discord.Channel):
        """!kazhelp
        brief: Remove a wiki channel.
        description: |
            Disables wiki mirroring to a channel.
        parameters:
            - name: channel
              type: channel name
              description: Discord channel to update.
        examples:
            - command: ".wikichannel rem #rules"
              description: disable in #rules
        """
        logger.info("Deleting channel #{} from wikichannel config...".format(channel.name))
        with self.cog_state as state:
            await self._delete_messages(state.channels[channel])
            del state.channels[channel]
        logger.debug("Done.")
        await self.send_message(ctx.message.channel, ctx.message.author.mention + " " +
            "Removed wiki mirroring from channel {}".format(channel.mention))

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def refresh(self, ctx: commands.Context, channel: discord.Channel):
        """!kazhelp
        brief: Update the specified channel with the latest wiki page.
        description: |
            Update the specified channel with the latest wiki page configured for this channel.
        parameters:
            - name: channel
              type: channel name
              description: Channel to update.
        examples:
            - command: ".wikichannel preview #rules"
              description: Update the wiki page in #rules.
        """
        await self._update_wiki(channel)
        data = self.cog_state.channels[channel]
        await self.send_message(ctx.message.channel, ctx.message.author.mention + " " +
            "Updated wiki page r/{}/{} in channel {}: sent {} messages"
            .format(data.subreddit, data.wikipage, data.channel.mention, len(data.messages)))

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def preview(self, ctx: commands.Context, channel: discord.Channel=None):
        """!kazhelp
        brief: Preview the latest wiki page in-channel.
        description: |
            Preview the latest wiki page that is normally configured for the given channel. The
            preview is posted to the channel this command is issued in, not the specified channel.
            Careful, this could be spammy!
        parameters:
            - name: channel
              type: channel name
              description: Channel the wiki page would usually show up in.
        examples:
            - command: ".wikichannel preview #rules"
              description: "Shows a preview of the wiki page in #rules. This preview is shown in the
                           same channel the command is issued in."
        """
        data = self.cog_state.channels[channel]
        await self._post_wikichannel(data, ctx.message.channel)

    @wikichannel.error
    @remove.error
    @refresh.error
    @preview.error
    async def wikichannel_error(self, exc: Exception, ctx: commands.Context):
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc
            if isinstance(root_exc, KeyError):
                ch = root_exc.args[0]
                await self.send_message(ctx.message.channel,
                    "Channel {} is not configured for wikichannel.".format(ch.mention))
                logger.warning("Channel #{} not configured for wikichannel.".format(ch.name))
            elif isinstance(root_exc, reddit.NotFound):
                msg = "404 Not Found: {}".format(root_exc.response.url.path)
                await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + msg)
                logger.warning(msg)
            elif isinstance(root_exc, reddit.OAuthException):
                msg = "An OAuth error occurred: {}".format(exc_log_str(root_exc))
                await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + msg)
                logger.error(msg)
            elif isinstance(root_exc, reddit.RequestException):
                msg = "A reddit request error occurred: {}".format(exc_log_str(root_exc))
                await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + msg)
                logger.error(msg)
            elif isinstance(root_exc, reddit.ResponseException):
                msg = "A reddit error occurred: {}".format(exc_log_str(root_exc))
                await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + msg)
                logger.warning(msg)
            else:
                core_cog = self.bot.get_cog("CoreCog")
                await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @wikichannel.command(pass_context=True)
    @mod_only()
    async def testfile(self, ctx: commands.Context):
        """!kazhelp
        brief: Preview the output of this module based on a text file.
        description: |
            Preview the output of this module based on a text file stored on the bot's server. The
            bot administrator must be the one to install this file.

            Primarily used for testing/demoing.
        """
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
