from datetime import timedelta, datetime
import logging
from typing import List, Dict, Sequence, Set, Iterable, Tuple, AsyncGenerator

import discord
from discord.ext import commands

from kaztron import KazCog, task
from kaztron.config import SectionView
from kaztron.driver import reddit
from kaztron.utils.checks import mod_only
from kaztron.utils.containers import FifoCache
from kaztron.utils.datetime import format_timedelta, utctimestamp

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
    no_results_count: int
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


class RedditStreamManager:
    """
    Helps manage and cache the submissions stream. Also manages stream failures (e.g. when the
    last retrieved post is deleted, the stream may return no results instead of the latest results
    since the last query).

    :param reddit: Reddit instance to use
    :param subreddits: List of subreddit names to check
    :param renewal_threshold: Number of times the stream is checked with no results before
        automatically refreshing (i.e. assumed stream failure).
    """
    def __init__(self,
                 reddit_: reddit.Reddit,
                 subreddits: Iterable[str],
                 renewal_threshold=5,
                 cache_expiry=180):
        self.reddit = reddit_

        self._subreddits = tuple(subreddits)
        self._stream = None
        self._is_fresh = True
        self.no_result_count = 0
        self.renewal_threshold = renewal_threshold

        self.submission_cache = FifoCache()  # type: Dict[str, Tuple[reddit.models.Submission, int]]
        self.cache_expiry_delta = cache_expiry

    @property
    def subreddits(self):
        """
        List of subreddit names for this stream. If this list is modified, the stream is refreshed.
        """
        return self._subreddits

    @subreddits.setter
    def subreddits(self, subreddits: Iterable[str]):
        self._subreddits = tuple(subreddits)
        self.refresh()

    @property
    def is_fresh(self):
        """
        True if the stream is fresh, i.e., will return a backlog. This property remains true until
        the stream has iterated through the first set of responses from the API, i.e.,
        :meth:`~.stream` has iterated through to its end.
        """
        return self._is_fresh

    async def stream(self) -> AsyncGenerator[reddit.models.Submission, None]:
        """
        Generator of new reddit posts. Should be async iterated.

        After a :meth:`~.refresh()`, setting :attr:`~.subreddits`, or hitting the
        :attr:`~.renewal_threshold`, this will load a number of recent posts instead of restarting
        from the latest post.
        """
        has_results = False
        if self.is_fresh:
            sr = await self.reddit.subreddit(display_name='+'.join(self.subreddits))
            self._stream = sr.stream.submissions(pause_after=0)

        async for submission in self._stream:
            if submission is None:
                if has_results:
                    self.no_result_count = 0
                else:
                    self.no_result_count += 1
                break
            has_results = True
            self.submission_cache[submission.id] = (submission, utctimestamp(datetime.utcnow()))
            yield submission

        self._is_fresh = False
        if self.no_result_count >= self.renewal_threshold:
            self.refresh()

    def refresh(self):
        self._stream = None
        self._is_fresh = True

    async def get_submission(self, reddit_id: str) -> reddit.models.Submission:
        """
        Get the submission from cache or from the reddit API (if not in cache or expired).
        :param reddit_id:
        :return:
        :raise reddit.DeletedError: submission is removed/deleted
        """
        try:
            s, load_time = self.submission_cache[reddit_id]
            if utctimestamp(datetime.utcnow()) - load_time > self.cache_expiry_delta:
                await s.load()
                self.submission_cache[reddit_id] = (s, utctimestamp(datetime.utcnow()))
        except KeyError:
            s = await self.reddit.submission(reddit_id)
            self.submission_cache[reddit_id] = (s, utctimestamp(datetime.utcnow()))

        if getattr(s, 'removed_by_category', None) is not None:
            raise reddit.DeletedError(s, s.removed_by_category)
        elif not getattr(s, 'is_robot_indexable', True):
            raise reddit.DeletedError(s, 'unknown')
        return s


class QueueManager:
    """
    Manage a queue of subreddit posts found and not yet posted.

    Note: this class's methods will not mark dirty or write the state file. All mutating methods
    should be called under `with self.cog_state:` contexts to ensure the file is properly updated.
    """

    def __init__(self, state: SubwatchState):
        self.state = state

    def add(self, submission: reddit.models.Submission):
        """ Add a submission to the queue. """
        for ch, ch_info in self.state.channels.items():
            if submission.subreddit.display_name.lower() in ch_info.subreddits:
                ch_info.queue.append(submission.id)

    def pop(self, channel: discord.Channel) -> str:
        """
        Pop a reddit ID off the channel's queue.
        :raise IndexError: Nothing in queue
        :raise KeyError: Channel is not configured for SubWatch
        """
        return self.state.channels[channel].queue.pop(0)


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
        self.cog_state.set_defaults(
            channels=dict(),
            last_checked=utctimestamp(datetime.utcnow()),
            no_results_count=0
        )
        self.reddit = None  # type: reddit.Reddit
        self.stream_manager = None  # type: RedditStreamManager
        self.queue_manager = None  # type: QueueManager

    async def on_ready(self):
        await super().on_ready()
        self.cog_state.set_cog(self)
        _ = self.cog_state.channels  # convert and validate
        self.reddit = reddit.RedditLoginManager().get_reddit(self.cog_config.reddit_username)
        self.stream_manager = RedditStreamManager(self.reddit, self._get_all_subreddits())
        self.queue_manager = QueueManager(self.cog_state)

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

    async def _post_all_channels(self):
        for channel in self.cog_state.channels.keys():
            await self._post_from_queue(channel)

    def schedule_post_from_queue(self, channel: discord.Channel):
        """

        :param channel:
        :return: True if scheduled later, False if not (channel can post now)
        """
        # check if already scheduled
        for task_instance in self.scheduler.get_instances(self.task_process_queue):
            if task_instance.args[0] == channel:
                return True

        ch_info = self.cog_state.channels[channel]
        next_post_time = ch_info.last_posted + self.cog_config.min_post_interval
        if ch_info.queue and datetime.utcnow() < next_post_time:
            logger.warning("Too early to post in #{}: scheduling for later.".format(channel.name))
            self.scheduler.schedule_task_at(
                task=self.task_process_queue,
                dt=next_post_time,
                args=(channel,)
            )
            return True
        return False

    async def _post_from_queue(self, channel: discord.Channel):
        """
        Post any queued messages in the channel. This respects the minimum interval between discord
        posts and maximum number of posts per interval configuration settings, and will schedule
        the :meth:`~.task_process_queue` for later if there are too many queued posts.

        :param channel: Channel to post in.
        """
        if self.schedule_post_from_queue(channel):
            return

        logger.debug("Posting from queue for #{}".format(channel.name))
        ch_info = self.cog_state.channels[channel]
        count = 0
        try:
            while count < self.cog_config.max_posts_per_interval:
                try:
                    submission_id = self.queue_manager.pop(channel)
                    submission = await self.stream_manager.get_submission(submission_id)
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
                    await self.send_output("[ERROR] Subwatch: Error posting post in #{}: {}"
                        .format(channel.name, submission.id))
                    continue
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
            desc_parts.append(f'({submission.domain})')
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

        with self.cog_state as state:
            count = 0
            last_checked = utctimestamp(state.last_checked)
            last_timestamp = last_checked  # last processed submission timestamp
            async for submission in self.stream_manager.stream():
                # if an old submission / already checked, skip it
                if self.stream_manager.is_fresh and submission.created_utc <= last_checked:
                    continue
                self.queue_manager.add(submission)
                last_timestamp = submission.created_utc
                logger.debug("Found post: {}".format(self.log_submission(submission)))
                count += 1
            logger.info("Found {} new posts in subreddits: {}".format(count, ', '.join(sub_set)))
            state.last_checked = datetime.utcfromtimestamp(last_timestamp)
            await self._post_all_channels()

    @task(is_unique=False)
    async def task_process_queue(self, channel: discord.Channel):
        """ Checks queue of reddit posts to send to Discord channel and posts when possible. """
        with self.cog_state:
            await self._post_from_queue(channel)

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=False)
    @mod_only()
    async def subwatch(self, ctx: commands.Context):
        """!kazhelp

        brief: Show Subwatch configuration.
        description: Show the current subwatch configuration.
        """
        channel_strings = []
        for channel, ch_info in self.cog_state.channels.items():
            channel_strings.append("{}: {}".format(
                channel.mention, ', '.join('/r/' + name for name in ch_info.subreddits)
            ))
        await self.send_message(ctx.message.channel, ctx.message.author.mention + '\n' +
            (format_list(channel_strings) if channel_strings else 'No subwatch configured'))

    @subwatch.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def add(self, ctx: commands.Context, channel: discord.Channel=None, *,
                       subreddits: str=None):
        """!kazhelp

        brief: Add or edit a channel's sub watches.
        description: Add or change subreddits to watch and post into a channel.
        parameters:
            - name: channel
              type: string
              description: "Discord channel to output the watched subreddits into."
            - name: subreddits
              type: string
              optional: True
              description: "Subreddits to watch and post in the channel. Can be separated by commas,
                spaces or `+`."
        examples:
            - command: ".subwatch #general askreddit askscience"
              description: "Watch the subreddits AskReddit and AskScience and post new posts to
                #general."
        """
        # preprocess the list
        subs_list_raw = subreddits.replace(',', ' ').replace('+', ' ').split(' ')
        # strip elements, and filter empty elements due to extra whitespace
        subreddits_list = tuple(filter(lambda s: s, (s.strip().lower() for s in subs_list_raw)))
        self.cog_state.channels[channel] = SubwatchChannel(
            subreddits=subreddits_list,
            last_posted=datetime.utcfromtimestamp(0)
        )
        self.stream_manager.subreddits = self._get_all_subreddits()
        logger.info("Set channel #{} to subwatch: {}"
            .format(channel.name, ', '.join('/r/' + s for s in subreddits_list)))
        await self.send_message(ctx.message.channel, ctx.message.author.mention + ' ' +
            "Set channel {} to subwatch: {}"
            .format(channel.mention, ', '.join('/r/' + s for s in subreddits_list)))

    @subwatch.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def rem(self, ctx: commands.Context, channel: discord.Channel=None):
        """!kazhelp

        brief: Remove subwatches from a channel.
        description: Stop watching subreddits in a channel.
        parameters:
            - name: channel
              type: string
              description: "Discord channel."
        examples:
            - command: ".subwatch rem #general"
              description: "Stop watching subreddits in #general."
        """
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
            self.stream_manager.subreddits = self._get_all_subreddits()
            logger.info(f'Removed subwatches in #{channel.name}.')
            await self.send_message(ctx.message.channel,
                ctx.message.author.mention + ' ' + f'Removed subwatches in {channel.mention}.')


def setup(bot):
    bot.add_cog(Subwatch(bot))
