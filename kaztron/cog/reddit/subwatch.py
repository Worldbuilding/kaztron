from collections import OrderedDict
from datetime import timedelta, datetime
import logging
from typing import List, Dict, Sequence, Set, AsyncGenerator

import discord
from discord.ext import commands

from kaztron import KazCog, task, scheduler
from kaztron.config import SectionView
from kaztron.driver import reddit
from kaztron.utils.checks import mod_only
from kaztron.utils.datetime import format_timedelta, utctimestamp
from asyncpraw.models.reddit.subreddit import SubredditStream

from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.strings import format_list, natural_truncate

logger = logging.getLogger(__name__)


def get_reddit_scopes():
    return 'identity', 'read'


class SubwatchConfig(SectionView):
    """
    :ivar reddit_username: Username to use. If not specified, will use the first logged-in user.
    :ivar check_interval: How often to check a subreddit for new posts.
    :ivar min_post_interval: Minimum time between posts to Discord.
        If more than max_posts_per_interval new Reddit posts are detected, they will be queued up
        and posted at this interval.
    :ivar max_posts_per_interval: Maximum number of Reddit posts to post to Discord at a time. If
        more Reddit posts are detected, they will be queued up and posted every min_post_interval.
    """
    reddit_username: str
    check_interval: timedelta
    min_post_interval: timedelta
    max_posts_per_interval: int

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_converters('check_interval', self._get_timedelta, self._set_timedelta)
        self.set_converters('min_post_interval', self._get_timedelta, self._set_timedelta)

    @staticmethod
    def _get_timedelta(seconds: int):
        return timedelta(seconds=seconds)

    @staticmethod
    def _set_timedelta(d: timedelta):
        return d.total_seconds()


class SubwatchChannel:
    def __init__(self, *,
                 subreddits: Sequence[str],
                 queue: List[str]=tuple(),
                 last_posted: datetime):
        self.subreddits = tuple(subreddits)
        self.queue = list(queue)
        self.last_posted = last_posted

    def to_dict(self):
        return {
            'subreddits': self.subreddits,
            'queue': self.queue,
            'last_posted': utctimestamp(self.last_posted)
        }

    @staticmethod
    def from_dict(data: dict):
        return SubwatchChannel(subreddits=data['subreddits'], queue=data.get('queue', []),
                               last_posted=datetime.utcfromtimestamp(data['last_posted']))


class SubwatchState(SectionView):
    """
    :ivar queue: Queue of reddit submission IDs for each Discord channel.
    :ivar watch: Discord channels and the subreddit(s) they subwatch.
    """
    channels: Dict[discord.Channel, SubwatchChannel]
    last_checked: datetime
    cog: KazCog

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__['cog'] = None
        self.set_converters('channels', self._get_channels, self._set_channels)
        self.set_converters('last_checked', datetime.utcfromtimestamp, utctimestamp)

    def set_cog(self, cog: KazCog):
        self.__dict__['cog'] = cog

    def _get_channels(self, data: Dict[str, dict]):
        return {self.cog.get_channel(key): SubwatchChannel.from_dict(channels_dict)
                for key, channels_dict in data.items()}

    @staticmethod
    def _set_channels(data: Dict[discord.Channel, SubwatchChannel]):
        return {ch.id: sub.to_dict() for ch, sub in data.items()}


class FifoCache(OrderedDict):
    """ Fixed-size cache, evicting the oldest inserted item when full. """

    def __init__(self, maxsize=128, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            self.popitem(last=False)


class Subwatch(KazCog):
    """!kazhelp
    category: Automation
    brief: Announce new reddit posts in a channel.
    description: |
        This module monitors one or more subreddits and announces new posts to Discord channels.

        It is configured to check every {{check_interval}}. It will post a maximum of
        {{max_posts_per_interval}} posts at a time every {{min_post_interval}}, to avoid flooding
        a Discord channel; otherwise, it will queue posts.
    contents:
        - subwatch
    """
    cog_config: SubwatchConfig
    cog_state: SubwatchState

    CACHE_SIZE = 32

    #####
    # Lifecycle
    #####

    def __init__(self, bot):
        super().__init__(bot, 'subwatch', SubwatchConfig, SubwatchState)
        self.cog_config.set_defaults(
            reddit_username=None,
            check_interval=60,
            min_post_interval=300,
            max_posts_per_interval=2,
        )
        self.cog_state.set_defaults(channels=dict(), last_checked=utctimestamp(datetime.utcnow()))
        self.reddit = None  # type: reddit.Reddit
        self.submission_stream = None  # type: AsyncGenerator
        self.submission_cache = FifoCache(self.CACHE_SIZE)  # type: OrderedDict[str, reddit.models.Submission]

    async def on_ready(self):
        await super().on_ready()
        self.cog_state.set_cog(self)
        _ = self.cog_state.channels  # convert and validate
        self.reddit = reddit.RedditLoginManager().get_reddit(self.cog_config.reddit_username)

        logger.info("Using reddit account: {}".format((await self.reddit.user.me()).name))

        if not self.scheduler.get_instances(self.task_check_reddit):
            delay = timedelta(seconds=15)
            interval = self.cog_config.check_interval
            self.scheduler.schedule_task_in(self.task_check_reddit, delay, every=interval)

    def export_kazhelp_vars(self):
        return {
            'check_interval': format_timedelta(self.cog_config.check_interval),
            'min_post_interval': format_timedelta(self.cog_config.min_post_interval),
            'max_posts_per_interval': str(self.cog_config.max_posts_per_interval)
        }

    def unload_kazcog(self):
        self.scheduler.cancel_all(self.task_check_reddit)
        self.scheduler.cancel_all(self.task_process_queue)

    #####
    # Core
    #####

    @staticmethod
    def log_submission(submission: reddit.models.Submission) -> str:
        """ Format submission info in short form for logs. """
        return "{0.id} on {0.subreddit.display_name} (\"{1}\")".format(
            submission, natural_truncate(submission.title, 50)
        )

    def _get_all_subreddits(self) -> Set[str]:
        """ Get the set of all subreddits being watched across all channels. """
        subreddits = set()
        for channel, data in self.cog_state.channels.items():
            subreddits.update(data.subreddits)
        return subreddits

    def _add_to_queues(self, submission: reddit.models.Submission):
        """
        Add a submission to queue in the cog state structure.

        WARNING: This method does NOT write the state file. Do that when you're done (or use
        `with` constructs).
        """
        for ch, ch_info in self.cog_state.channels.items():
            if submission.subreddit.display_name.lower() in ch_info.subreddits:
                ch_info.queue.append(submission.id)
            self.submission_cache[submission.id] = submission

    async def _pop_queued_submission(self, channel: discord.Channel):
        """
        Pop a submission from the queue, and refresh it from Reddit if stale.

        Note: This method directly modifies the cog_state structures and might not mark it as
        dirty, nor will it write the file.
        :return:
        :raise DeletedError: post was removed or deleted
        """
        submission_id = self.cog_state.channels[channel].queue.pop(0)
        try:
            submission = self.submission_cache[submission_id]
            # if the submission object isn't new enough, reload it
            if utctimestamp(datetime.utcnow()) > submission.created_utc + 60:
                await submission.load()
        except KeyError:  # cache miss
            submission = await self.reddit.submission(submission_id)

        if submission.author is None or (hasattr(submission, 'selftext') and
                                         submission.selftext in ('[deleted]', '[removed]')):
            raise reddit.DeletedError(submission)

        return submission

    async def _post_from_queue(self, channel: discord.Channel=None):
        """
        Post any queued messages in the channel. This respects the minimum interval between discord
        posts and maximum number of posts per interval configuration settings, and will schedule
        the task_post_to_discord for later if there are too many queued posts.

        :param channel: Optional, channel to post in. If not specified, check all channels.
        """
        if channel is None:
            for cur_channel in self.cog_state.channels.keys():
                await self._post_from_queue(cur_channel)
            return

        ch_info = self.cog_state.channels[channel]

        # has a queue, but not time to post yet: let's schedule the next time
        next_post_time = ch_info.last_posted + self.cog_config.min_post_interval
        if ch_info.queue and datetime.utcnow() < next_post_time:
            logger.warning("Too early to post in #{}: scheduling for later.".format(channel.name))
            self.scheduler.schedule_task_at(
                task=self.task_process_queue,
                dt=next_post_time,
                args=(channel,)
            )
            return

        logger.debug("Posting from queue for #{}".format(channel.name))
        count = 0
        try:
            while count < self.cog_config.max_posts_per_interval:
                try:
                    submission = await self._pop_queued_submission(channel)
                except reddit.DeletedError as e:
                    logger.warning("Skipping deleted or removed post: {}"
                        .format(self.log_submission(e.args[0])))
                    continue

                try:
                    await self._send_submission(channel, submission)
                except (AttributeError, TypeError, ValueError) as e:
                    logger.exception("Error posting submission: {}"
                        .format(self.log_submission(submission)))
                    await self.send_message(channel, "Subwatch: Error posting post: {}"
                        .format(submission.id))
                    await self.send_message(channel, "Subwatch: Error posting post in #{}: {}"
                        .format(channel.name, submission.id))
                count += 1
        except IndexError:  # we don't have enough in queue to post; that's fine
            pass
        else:  # we did post something
            ch_info.last_posted = datetime.utcnow()

    async def _send_submission(self,
                               channel: discord.Channel,
                               submission: reddit.models.Submission):
        """ Post a submission to a channel. """
        logger.info("Posting to #{}: {}".format(channel.name, self.log_submission(submission)))
        tags = []
        if submission.link_flair_text:
            tags.append(f'[{submission.link_flair_text}]')
        if submission.is_original_content:
            tags.append('[OC]')
        subreddit = '/r/{0}'.format(submission.subreddit.display_name)

        desc_parts = [''.join(tags)]
        if submission.is_self:
            desc_parts.append(f'(self.{submission.subreddit.display_name})')
        else:
            desc_parts.append(f'({submission.domain}')
        desc_parts.append('on')
        desc_parts.append(subreddit)

        es = EmbedSplitter(
            auto_truncate=True,
            title=submission.title,
            url='https://reddit.com' + submission.permalink,
            timestamp=datetime.utcfromtimestamp(submission.created_utc)
        )
        es.set_footer(text=' '.join(desc_parts))
        es.set_author(name='/u/' + submission.author.name,
                      url='https://reddit.com/u/{}'.format(submission.author.name))
        if submission.thumbnail.startswith('http://') or submission.thumbnail.startswith('https://'):
            es.set_thumbnail(url=submission.thumbnail)
        await self.send_message(channel, embed=es)

    #####
    # Discord
    #####

    @task(is_unique=True)
    async def task_check_reddit(self):
        """ Checks all subreddits configured. """
        sub_set = self._get_all_subreddits()

        if not sub_set:
            return  # none configured

        logger.debug("Checking for new posts in subreddits: {}".format(', '.join(sub_set)))

        subs = await self.reddit.subreddit(display_name='+'.join(sub_set))

        if not self.submission_stream:
            self.submission_stream = subs.stream.submissions(pause_after=0)

        with self.cog_state as state:
            count = 0
            async for submission in self.submission_stream:  # type: reddit.models.Submission
                if submission is None:
                    break  # no more items
                # if an old submission / already checked, skip it
                if submission.created_utc <= utctimestamp(state.last_checked):
                    continue
                self._add_to_queues(submission)
                logger.debug("Found post: {0.subreddit.display_name} {0.id} {1}"
                    .format(submission, submission.title[:50]))
                count += 1
            logger.info(f"Found {count} new posts in all subreddits watched.")
            state.last_checked = datetime.utcnow()
            await self._post_from_queue(None)  # update all channels

    @task(is_unique=False)
    async def task_process_queue(self, channel: discord.Channel):
        """ Checks queue of reddit posts to send to Discord channel and posts when possible. """
        with self.cog_state:
            await self._post_from_queue(channel)

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def subwatch(self, ctx: commands.Context, channel: discord.Channel=None, *,
                       subreddits: str=None):
        """!kazhelp

        brief: Configure Subwatch or show configuration.
        description: Add or remove subreddits to watch and post into channels, or show the current
            configuration.
        parameters:
            - name: channel
              type: string
              description: "Discord channel to output the watched subreddits into."
            - name: subreddits
              type: string
              optional: True
              description: "Subreddits to watch and post in the channel. Can be separated by commas,
                spaces or `+`.If `off` or `none`, turns off Subwatch for that channel. If not
                specified, lists current subreddits watched."
        examples:
            - command: ".subwatch #general askreddit askscience"
              description: "Watch the subreddits AskReddit and AskScience and post new posts to
                #general."
            - command: ".subwatch #general off"
              description: "Stop watching subreddits in #general."
            - command: ".subwatch"
              description: "Show what subreddits are being watched and what channels they're being
                output to."
        """
        if channel is None:
            await self._subwatch_show(ctx)
            return

        with self.cog_state:
            if subreddits == 'off' or subreddits == 'none':
                await self._subwatch_rem(ctx, channel)
            else:
                await self._subwatch_add(ctx, channel, subreddits)

    async def _subwatch_show(self, ctx: commands.Context):
        channel_strings = []
        for channel, ch_info in self.cog_state.channels.items():
            channel_strings.append("{}: {}".format(
                channel.mention, ', '.join('/r/' + name for name in ch_info.subreddits)
            ))
        await self.send_message(ctx.message.channel, ctx.message.author.mention + '\n' +
            (format_list(channel_strings) if channel_strings else 'No subwatch configured'))

    async def _subwatch_add(self, ctx: commands.Context, channel: discord.Channel, subreddits: str):
        # preprocess the list
        subs_list_raw = subreddits.replace(',', ' ').replace('+', ' ').split(' ')
        # strip elements, and filter empty elements due to extra whitespace
        subreddits_list = tuple(filter(lambda s: s, (s.strip().lower() for s in subs_list_raw)))
        self.cog_state.channels[channel] = SubwatchChannel(
            subreddits=subreddits_list,
            last_posted=datetime.utcfromtimestamp(0)
        )
        self.submission_stream = None  # change in subreddits
        logger.info("Set channel #{} to subwatch: {}"
                .format(channel.name, ', '.join('/r/' + s for s in subreddits_list)))
        await self.send_message(ctx.message.channel, ctx.message.author.mention + ' ' +
            "Set channel {} to subwatch: {}"
            .format(channel.mention, ', '.join('/r/' + s for s in subreddits_list)))

    async def _subwatch_rem(self, ctx: commands.Context, channel: discord.Channel):
        try:
            del self.cog_state.channels[channel]
        except IndexError:
            logger.warning(f'Cannot remove channel #{channel.name}: no subwatch for channel')
            await self.send_message(ctx.message.channel, ctx.message.author.mention + ' ' +
                f'Cannot remove channel {channel.mention}: no subwatch for channel')
        else:
            # clean up scheduled tasks
            for task_instance in self.scheduler.get_instances(self.task_process_queue):
                if task_instance.args[0] == channel:
                    task_instance.cancel()
            self.submission_stream = None  # change in subreddits - renew the stream
            logger.info(f'Removed subwatches in #{channel.name}.')
            await self.send_message(ctx.message.channel,
                ctx.message.author.mention + ' ' + f'Removed subwatches in {channel.mention}.')





def setup(bot):
    bot.add_cog(Subwatch(bot))
