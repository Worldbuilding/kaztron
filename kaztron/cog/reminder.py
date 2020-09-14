import asyncio
import logging
import re
from datetime import datetime, timedelta
from functools import reduce
from typing import List, Tuple, Dict

import discord
from discord.ext import commands

from kaztron import KazCog, TaskInstance, task
from kaztron.config import SectionView
from kaztron.errors import DiscordErrorCodes
from kaztron.utils.checks import mod_channels, mod_only
from kaztron.utils.datetime import utctimestamp, format_datetime, format_timedelta, \
    parse as dt_parse
from kaztron.utils.discord import Limits, user_mention, channel_mention
from kaztron.utils.logging import exc_log_str
from kaztron.utils.strings import format_list

logger = logging.getLogger(__name__)


class RenewData:
    def __init__(self, *, interval: timedelta, limit: int, limit_time: datetime):
        self.interval = interval
        self.limit = limit
        self.limit_time = limit_time

    def to_dict(self):
        return {
            'interval': self.interval.total_seconds(),
            'limit': self.limit,
            'limit_time': utctimestamp(self.limit_time) if self.limit_time else None
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            interval=timedelta(seconds=data['interval']),
            limit=data.get('limit', 0),
            limit_time=data.get('limit_time', None)
        )

    def __repr__(self):
        return "<RenewData(interval={}, limit={}, limit_time={})>" \
            .format(self.interval, self.limit, self.limit_time)

    def str_dict(self) -> Dict[str, str]:
        return {
            'interval': format_timedelta(self.interval) if self.interval else '',
            'limit': '{:d}'.format(self.limit) if self.limit else '',
            'limit_time': format_datetime(self.limit_time) if self.limit_time else ''
        }


class ReminderData:
    MSG_LIMIT = Limits.MESSAGE - 75

    def __init__(self,
                 *,
                 user_id: str,
                 channel_id: str = None,
                 timestamp: datetime,
                 remind_time: datetime,
                 renew_data: RenewData,
                 msg: str
                 ):
        self.user_id = user_id
        self.channel_id = channel_id
        self.timestamp = timestamp
        self.remind_time = remind_time
        self.renew_data = renew_data
        self.message = msg[:self.MSG_LIMIT]
        self.retries = 0

    def to_dict(self):
        data = {
            'user_id': self.user_id,
            'channel_id': self.channel_id,
            'timestamp': utctimestamp(self.timestamp),
            'remind_time': utctimestamp(self.remind_time),
            'renew': self.renew_data.to_dict() if self.renew_data else None,
            'message': self.message
        }
        return data

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            user_id=data.get('user_id', ''),
            channel_id=data.get('channel_id', ''),
            timestamp=datetime.utcfromtimestamp(data['timestamp']),
            remind_time=datetime.utcfromtimestamp(data['remind_time']),
            renew_data=RenewData.from_dict(data['renew']) if data.get('renew', None) else None,
            msg=data['message']
        )

    def __repr__(self):
        return "<ReminderData(user_id={}, channel_id={}, " \
               "timestamp={}, remind_time={}, renew={!r}, message={!r})>" \
            .format(self.user_id, self.channel_id,
                    self.timestamp.isoformat(' '),
                    self.remind_time.isoformat(' '),
                    self.renew_data,
                    self.message)

    def str_dict(self) -> Dict[str, str]:
        return {
            'user': user_mention(self.user_id) if self.user_id else '',
            'channel': channel_mention(self.channel_id) if self.channel_id else 'PM',
            'timestamp': format_datetime(self.timestamp),
            'remind_time': format_datetime(self.remind_time),
            'message': self.message
        }

    def is_match(self, user_id: str=None, channel_id: str=None):
        """
        Check if reminder matches criteria.

        If only a user_id is provided, returns True if the reminder is a private reminder for that
        user.

        If a channel_id is provided, returns True if the reminder is a channel message for that
        channel. This check can further be filtered by the user who set the reminder, if user_id is
        also provided.
        """
        return self.channel_id == channel_id and (user_id is None or self.user_id == user_id)


class ReminderParser:
    MAX_TIMESPEC = timedelta(weeks=521)  # 10 years
    RE_ARGS = re.compile(r'(?P<timespec>.*?)'
                         r'(\s+'
                            r'every\s+(?P<renew_interval>.*?)'
                            r'(\s+limit\s+(?P<limit>\d+)|\s+until\s+(?P<limit_time>.*?))?'
                         r')?\s*:\s+(?P<msg>.*)$')

    @classmethod
    def parse(cls, args: str, now: datetime) -> Tuple[datetime, Tuple[timedelta, int, datetime], str]:
        """
        Parse reminder args.
        :return: (timespec, (renew_interval, renew_limit, renew_limit_time), msg)
        """
        args = cls.RE_ARGS.match(args)  # type: re.Match
        if args is None:
            raise commands.BadArgument("message")

        timespec = cls._parse_timespec(args.group('timespec'), now)

        if args.group('renew_interval'):
            renew = cls._parse_renew(args.group('renew_interval'),
                                     args.group('limit'),
                                     args.group('limit_time'),
                                     now)
        else:
            renew = None
        return timespec, renew, args.group('msg')

    @classmethod
    def _parse_timespec(cls, timespec_s: str, now: datetime):
        max_timestamp = now + cls.MAX_TIMESPEC
        # first one allows "10 minutes" as a future input, second is a fallback
        try:
            timespec = dt_parse('in '+timespec_s, future=True) or dt_parse(timespec_s, future=True)
        except ValueError:
            # usually raised by datetime, for range issues
            # the parser will usually return None if parsing fails
            raise commands.BadArgument("range", timespec_s[:64])

        if timespec is None:
            raise commands.BadArgument("timespec", timespec_s[:64])
        elif timespec <= now:
            raise commands.BadArgument("past", timespec_s[:64])
        elif timespec >= max_timestamp:
            raise commands.BadArgument("range", timespec_s[:64])

        return timespec

    @classmethod
    def _parse_renew(cls, interval_s: str, limit_s: str, limit_time_s: str, now: datetime):
        # process the renewal time: use dateparser and then figure out the delta
        try:
            timespec = dt_parse('in' + interval_s, future=True,
                                PARSERS=['relative-time'], RELATIVE_BASE=now)
            interval = timespec - now  # type: timedelta
        except ValueError:
            raise commands.BadArgument("range", interval_s[:64])

        if interval is None:
            raise commands.BadArgument("timespec", interval_s[:64])
        elif interval.total_seconds() < 0:
            raise commands.BadArgument("renew_interval_neg", interval_s[:64])
        elif interval >= cls.MAX_TIMESPEC:
            raise commands.BadArgument("range", interval_s[:64])

        try:
            limit = int(limit_s) if limit_s is not None else None
        except ValueError:
            raise commands.BadArgument("renew_limit")

        limit_time = cls._parse_timespec(limit_time_s, now) if limit_time_s is not None else None

        return interval, limit, limit_time


class ReminderState(SectionView):
    reminders: List[ReminderData]


class ReminderConfig(SectionView):
    max_per_user: int        # maximum personal reminders per user
    renew_limit: int         # maximum times a reminder or saylater can repeat
    renew_interval_min: int  # minimum interval for recurring reminders/saylater (seconds)


class Reminders(KazCog):
    """!kazhelp
    category: Commands
    brief: Get reminders for later.
    description: |
        The Reminder cog allows you to ask the bot to send you a reminder message in a certain
        amount of time. Reminders are personal and PMed to you.

        IMPORTANT: While we want this module to be useful and reliable, we can't guarantee that
        you'll get the reminder on time. Don't rely on this module for anything critical!

        This cog also allows moderators to schedule messages in-channel at a later time.
    contents:
        - reminder:
            - list
            - rem
            - clear
        - saylater:
            - list
            - rem
    """
    cog_state: ReminderState
    cog_config: ReminderConfig

    MAX_RETRIES = 10
    RETRY_INTERVAL = 90

    ###
    # LIFECYCLE
    ###
    def __init__(self, bot):
        super().__init__(bot, 'reminders', ReminderConfig, ReminderState)
        self.cog_config.set_defaults(
            max_per_user=10,
            renew_limit=25,
            renew_interval_min=600
        )
        self.cog_state.set_defaults(reminders=[])
        self.cog_state.set_converters('reminders',
            lambda l: [ReminderData.from_dict(r) for r in l],
            lambda l: [r.to_dict() for r in l]
        )
        self.reminders = []  # type: List[ReminderData]

    async def on_ready(self):
        await super().on_ready()
        if not self.reminders:
            self._load_reminders()

    def export_kazhelp_vars(self):
        interval_s = format_timedelta(timedelta(seconds=self.cog_config.renew_interval_min))
        return {
            "max_per_user": f'{self.cog_config.max_per_user:d}',
            "renew_limit": f'{self.cog_config.renew_limit:d}',
            "renew_interval_min": interval_s
        }

    def _load_reminders(self):
        logger.info("Loading reminders from persisted state...")
        try:
            self.scheduler.cancel_all(self.task_reminder_expired)
        except asyncio.InvalidStateError:
            pass
        self.reminders.clear()
        for reminder in self.cog_state.reminders:
            self.add_reminder(reminder)

    def _save_reminders(self):
        if not self.is_ready:
            logger.debug("_save_reminders: not ready, skipping")
            return
        logger.debug("_save_reminders")
        self.cog_state.reminders = self.reminders
        self.state.write()

    ###
    # GENERAL UTILITY FUNCTIONS
    ###

    def get_count(self, user_id: str = None, channel_id: str = None):
        """ Get number of reminders matching criteria. """
        return reduce(lambda c, r: c+1 if r.is_match(user_id, channel_id) else c, self.reminders, 0)

    def get_matching(self, user_id: str = None, channel_id: str = None):
        """ Get list of reminders matching criteria, in ascending order of remind time. """
        return sorted(filter(lambda r: r.is_match(user_id, channel_id), self.reminders),
                      key=lambda r: r.remind_time)

    @property
    def saylaters(self):
        return sorted(filter(lambda r: r.channel_id, self.reminders), key=lambda r: r.remind_time)

    @property
    def personal_reminders(self):
        return sorted(filter(lambda r: not r.channel_id, self.reminders),
                      key=lambda r: r.remind_time)

    def make_reminder(self, ctx: commands.Context, args: str, channel: discord.Channel = None):
        """
        Prepare ReminderData for any kind of reminder (channel or private/PM).
        :param ctx: Command context.
        :param args: Full reminder argument string, of the form "<timespec>: <message>" (or
                    extended for recurring reminders).
        :param channel: Optional. If specified, creates a channel reminder. Otherwise, creates a
                    personal reminder.
        :return:
        """
        ctx.message: discord.Message
        timestamp = ctx.message.timestamp
        renew_data = None

        # parse arguments
        timespec, renew, msg = ReminderParser.parse(args, timestamp)
        if renew:
            renew_data = RenewData(interval=renew[0], limit=renew[1], limit_time=renew[2])
            # enforce limits
            if renew_data.interval.total_seconds() < self.cog_config.renew_interval_min:
                raise commands.BadArgument("renew_interval_min", renew_data.interval)
            if not renew_data.limit or not (0 < renew_data.limit <= self.cog_config.renew_limit):
                logger.warning(f"Reminder limit ({renew_data.limit}) invalid: setting to "
                f"configured maximum {self.cog_config.renew_limit}")
                renew_data.limit = self.cog_config.renew_limit

        reminder = ReminderData(
            user_id=ctx.message.author.id, channel_id=channel.id if channel else None,
            renew_data=renew_data, timestamp=timestamp, remind_time=timespec, msg=msg
        )
        return reminder

    def add_reminder(self, r: ReminderData):
        self.reminders.append(r)
        self.scheduler.schedule_task_at(self.task_reminder_expired, r.remind_time, args=(r,),
            every=self.RETRY_INTERVAL)
        self._save_reminders()
        logger.info("Set reminder: {!r}".format(r))

    def remove_reminder(self, r: ReminderData):
        """ Remove reminder. Parameter must be exact object. """
        for inst in self.scheduler.get_instances(self.task_reminder_expired):  # type: TaskInstance
            if inst.args[0] is r:
                try:
                    inst.cancel()
                except asyncio.InvalidStateError:
                    pass
                self.reminders.remove(r)
                break
        self._save_reminders()

    @staticmethod
    def format_list(reminders: List[ReminderData]) -> str:
        """ Format the input list for sending to a user. """
        items = []
        for reminder in reminders:
            build_str = []

            if reminder.channel_id:
                build_str.append("In {channel} at {timestamp} UTC (in {delta})")
            else:
                build_str.append("At {timestamp} UTC (in {delta})")

            if reminder.renew_data:
                renew_data = reminder.renew_data
                build_str.append(" and every {interval}")
                if renew_data.limit_time:
                    build_str.append(" until {limit_time} up to")
                build_str.append(" {limit} times")

            build_str.append(": {message}")

            items.append(''.join(build_str).format(
                delta=format_timedelta(reminder.remind_time - datetime.utcnow()),
                **reminder.str_dict(),
                **(reminder.renew_data.str_dict() if reminder.renew_data else {})
            ))
        return format_list(items) if items else 'None'

    ###
    # COMMANDS
    ###

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['remind'])
    async def reminder(self, ctx: commands.Context, *, args: str):
        """!kazhelp

        description: |
            Sends you a personal reminder by PM at some point in the future. This function can also
            set up recurring reminders.

            Each user can have a maximum of {{max_per_user}} reminders. Recurring reminders can
            repeat up to {{renew_limit}} times, and cannot repeat more often than every
            {{renew_interval_min}}.

            TIP: Make sure you've enabled "Allow direct messages from server members" for the server
            the bot is on.

            TIP: You should double-check the reminder time in the confirmation PM, to make sure your
            timespec was interpreted correctly.
        parameters:
            - name: args
              description: "Multi-part argument consists of `<timespec> [\\"every\\" <intervalspec>
                    [\\"limit\\" <limit>|\\"until\\" <limit_timespec>]: <message>`."
            - name: timespec
              type: timespec
              description: |
                  A time in the future to send you a reminder, followed by
                  a colon and a space. This can be an absolute date and time `2018-03-07 12:00:00`,
                  a relative time `in 2h 30m` (the "in" **and** the spaces are important), or
                  combinations of the two (`tomorrow at 1pm`). If giving an absolute time, you can
                  specify a time zone (e.g. `1pm UTC-5` or `13:05 EST`); if none specified, default
                  is UTC.
            - name: intervalspec
              type: timespec
              optional: true
              description: |
                How often the reminder should repeat after the `timespec`. Can take any relative
                time specification accepted by `timespec`, e.g., `every 1 hour`, `every 4h 30m`,
                etc.
            - name: limit
              type: int
              optional: true
              description: How many times the reminder will repeat. Only one of `limit` or
                `limitspec` may be used.
            - name: limitspec
              type: timespec
              optional: true
              description: The latest time at which the reminder will repeat. Accepts the same
                values  as `timespec`. Only one of `limit` or `limitspec` may be used.
            - name: message
              type: string
              description: The message you want to be reminded with.
        examples:
            - command: ".remind on 24 december at 4:50pm: Grandma's Christmas call"
              description: Date and time. Assumes nearest future date. Time is interpreted as UTC.
            - command: ".remind in 2 hours: Feed the dog"
              description: Relative time.
            - command: ".remind tomorrow at 8am PST: start spotlight"
              description: Relative date, absolute time, time zone specified.
            - command: ".remind in 2 hours every 1 hour limit 8: drink water, you dehydrated prune"
              description: Reminder starting in 2 hours, repeating every 1 hour, 8 times total.
            - command: ".remind 22:00 EDT every 1 hour until 08:00 EDT: Remember to sleep"
              description: Reminder every hour between 10PM tonight and 8AM tomorrow.
        """
        if self.get_count(user_id=ctx.message.author.id) >= self.cog_config.max_per_user:
            raise commands.UserInputError('max_per_user')

        reminder = self.make_reminder(ctx, args)
        self.add_reminder(reminder)

        # set message
        if not reminder.renew_data:
            reply = "Got it! I'll remind you by PM at {timestamp} UTC (in {delta}).".format(
                delta=format_timedelta(reminder.remind_time - reminder.timestamp),
                **reminder.str_dict()
            )
        else:
            if not reminder.renew_data.limit_time:
                replyf = "Got it! I'll remind you by PM at {timestamp} UTC (in {delta}), " \
                         "then every {interval} up to {limit} times."
            else:
                replyf = "Got it! I'll remind you by PM at {timestamp} UTC (in {delta}), " \
                         "then every {interval} until {limit_time} or up to {limit} times."
            reply = replyf.format(
                delta=format_timedelta(reminder.remind_time - reminder.timestamp),
                **reminder.str_dict(),
                **reminder.renew_data.str_dict()
            )

        await self.send_message(ctx.message.channel, reply)

    @commands.group(pass_context=True, invoke_without_command=True)
    @mod_only()
    @mod_channels()
    async def saylater(self, ctx: commands.Context, channel: discord.Channel, *, args: str):
        """!kazhelp

        description: |
            Schedule a message for the bot to send in-channel later. Can also set up recurring
            messages (static messages only).

            Recurring messages can repeat up to {{renew_limit}} times, and cannot repeat more often
            than every {{renew_interval_min}}s.

            TIP: You should double-check the time in the response message to make sure your timespec
            was interpreted correctly.
        parameters:
            - name: channel
              description: The channel to post the message in.
            - name: args
              description: Same as {{!reminder}}.
        examples:
            - command: ".saylater #community-programs at 12:00:
                Welcome to our AMA with philosopher Aristotle!"
              description: Single message at noon UTC.
            - command: ".saylater #announcements at 12:00 every 1 hour limit 24: Attention,
                citizens. For the duration of gremlin season, all citizens must be on the lookout
                for crown-stealing gremlins. Any sightings or incidents must be reported to your
                nearest moderator immediately."
              description: Recurring message every hour starting at noon UTC.
        """

        reminder = self.make_reminder(ctx, args, channel)
        self.add_reminder(reminder)

        # set message
        if not reminder.renew_data:
            reply = "Got it! I'll post that in {channel} at {timestamp} UTC (in {delta}).".format(
                delta=format_timedelta(reminder.remind_time - reminder.timestamp),
                **reminder.str_dict()
            )
        else:
            if not reminder.renew_data.limit_time:
                replyf = "Got it! I'll post that in {channel} at {timestamp} UTC (in {delta}), " \
                         "then every {interval} up to {limit} times."
            else:
                replyf = "Got it! I'll post that in {channel} at {timestamp} UTC (in {delta}), " \
                         "then every {interval} until {limit_time} or up to {limit} times."
            reply = replyf.format(
                delta=format_timedelta(reminder.remind_time - reminder.timestamp),
                **reminder.str_dict(),
                **reminder.renew_data.str_dict()
            )

        await self.send_message(ctx.message.channel, reply)

    @saylater.error
    @reminder.error
    async def reminder_error(self, exc, ctx):
        if isinstance(exc, commands.BadArgument):
            if exc.args[0] == 'timespec':
                logger.warning("Passed unknown timespec: {}".format(exc.args[1]))
                await self.send_message(ctx.message.channel, ctx.message.author.mention +
                    " Sorry, I don't understand the timespec '{}'".format(exc.args[1])
                )
            elif exc.args[0] == 'range':
                logger.warning("Passed timespec outside range: {}".format(exc.args[1]))
                await self.send_message(ctx.message.channel, ctx.message.author.mention +
                    " Sorry, that's too far in the future! I'll forget by then."
                )
            elif exc.args[0] == 'past':
                logger.warning("Passed timespec in the past: {}".format(exc.args[1]))
                await self.send_message(ctx.message.channel, ctx.message.author.mention +
                    " Oops! You can't set a reminder in the past."
                )
            elif exc.args[0] == 'message':
                logger.warning("Invalid syntax: {}".format(exc.args[1]))
                await self.send_message(ctx.message.channel, ctx.message.author.mention +
                    " You need to specify a message for your reminder! "
                    "Separate it from the timespec with a colon *and* space: "
                    "`.reminder in 10 minutes: message`"
                )
            elif exc.args[0] == 'renew_interval_neg' or exc.args[0] == 'renew_interval_min':
                logger.warning("Passed invalid renew interval: {}".format(exc.args[1]))
                await self.send_message(ctx.message.channel, ctx.message.author.mention +
                     " Sorry, I can't repeat reminders more often than {}. Don't want to spam you!"
                     .format(format_timedelta(timedelta(seconds=self.cog_config.renew_interval_min)))
                 )
        elif isinstance(exc, commands.UserInputError) and exc.args[0] == 'max_per_user':
            logger.warning("Cannot add reminder: user {} at limit".format(ctx.message.author))
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                "Sorry, you already have too many future reminders! "
                "The limit is {:d} per person.".format(self.cog_config.max_per_user))
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @task(is_unique=False)
    async def task_reminder_expired(self, reminder: ReminderData):
        logger.info("Reminder has expired: {!r}".format(reminder))

        # determine the destination (user or channel)
        if reminder.channel_id:
            dest = discord.Object(id=reminder.channel_id)
            message = f"{reminder.message}\n\n*({user_mention(reminder.user_id)})*"
        else:  # user reminder
            # can't use discord.Object - send_message would interpret it as a channel, not a user
            dest = discord.utils.get(self.bot.get_all_members(), id=reminder.user_id)
            message = "**Reminder** At {} UTC, you asked me to send you a reminder: {}".format(
                format_datetime(reminder.timestamp),
                reminder.message)

        await self.send_message(dest, message)

        # stop scheduled retries and remove the reminder
        try:
            for instance in self.scheduler.get_instances(self.task_reminder_expired):
                if instance.args[0] is reminder:
                    instance.cancel()
                    break
        except asyncio.InvalidStateError:
            pass

        try:
            self.reminders.remove(reminder)
        except ValueError:
            logger.warning("task_reminder_expired: Reminder not in list of reminders - "
                           "already removed? {!r}".format(reminder))

        # set up recurring reminder
        if reminder.renew_data and reminder.renew_data.interval:
            reminder.remind_time += reminder.renew_data.interval
            reminder.renew_data.limit -= 1
            if reminder.renew_data.limit <= 0:
                logger.debug("Recurring reminder has reached recurrence limit")
            elif reminder.renew_data.limit_time and \
                    reminder.remind_time > reminder.renew_data.limit_time:
                logger.debug("Recurring reminder has reached time limit")
            else:
                logger.debug("Setting up recurrence")
                self.add_reminder(reminder)

        self._save_reminders()

    @task_reminder_expired.error
    async def on_reminder_expired_error(self, e: Exception, t: TaskInstance):
        r = t.args[0]
        r.retries += 1
        retry = True
        logger.error("Error sending reminder: {}".format(exc_log_str(e)))
        if not isinstance(e, discord.HTTPException):
            logger.error("Reminders: non-HTTP error; giving up: {!r}".format(r))
            await self.send_output("Giving up on reminder: {!r}. Non-HTTP error occurred".format(r))
            retry = False
        elif isinstance(e, discord.Forbidden) and e.code == DiscordErrorCodes.CANNOT_PM_USER:
            logger.error("Reminders: can't send PM to user; giving up: {!r}".format(r))
            await self.send_public(
                ("{} You seem to have PMs from this server disabled or you've blocked me. "
                 "I need to be able to PM you to send you reminders. (reminder missed)")
                .format(user_mention(r.user_id))
            )
            await self.send_output("Giving up on reminder: {!r}. User has PMs disabled.".format(r))
            retry = False
        elif r.retries > self.MAX_RETRIES:
            logger.error("Reminders: max retries reached; giving up: {!r}".format(r))
            await self.send_output("Giving up on reminder: {!r}. Too many retries".format(r))
            retry = False
        else:
            logger.debug("Will retry reminder: {!r}".format(r))

        if not retry:
            t.cancel()
            self.reminders.remove(r)
            self._save_reminders()

    @reminder.command(ignore_extra=False, pass_context=True, name='list')
    async def reminder_list(self, ctx: commands.Context):
        """!kazhelp

         description: |
            List all your future reminders. The list is sent by PM.
         """

        reminder_list = self.format_list(self.get_matching(user_id=ctx.message.author.id))
        await self.send_message(ctx.message.author, "**Your reminders**\n" + reminder_list,
                                split='line')
        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            pass  # no permission or in a PM; oh well, this is not critical

    @saylater.command(ignore_extra=False, pass_context=True, name='list')
    @mod_only()
    @mod_channels()
    async def saylater_list(self, ctx: commands.Context):
        """!kazhelp

         description: |
            List all future scheduled messages.
         """
        reminder_list = self.format_list(self.saylaters)
        await self.send_message(ctx.message.channel, "**Scheduled messages**\n" + reminder_list,
                                split='line')
        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            pass  # no permission or in a PM; oh well, this is not critical

    @reminder.command(pass_context=True, ignore_extra=False, name='clear')
    async def reminder_clear(self, ctx: commands.Context):
        """!kazhelp

        description: |
            Remove all your future reminders.

            WARNING: This command cannot be undone.
        """
        for inst in self.scheduler.get_instances(self.task_reminder_expired):  # type: TaskInstance
            if inst.args[0].is_match(user_id=ctx.message.author.id):
                try:
                    inst.cancel()
                except asyncio.InvalidStateError:
                    pass
                self.reminders.remove(inst.args[0])
        self._save_reminders()
        await self.bot.say("All your reminders have been cleared.")

    @saylater.command(pass_context=True, ignore_extra=False, name='clear')
    @mod_only()
    @mod_channels()
    async def saylater_clear(self, ctx: commands.Context):
        """!kazhelp

        description: |
            Remove all scheduled messages.

            WARNING: This removes scheduled messages created by other users, too.

            WARNING: This command cannot be undone.
        """
        for inst in self.scheduler.get_instances(self.task_reminder_expired):  # type: TaskInstance
            if inst.args[0].channel_id:
                try:
                    inst.cancel()
                except asyncio.InvalidStateError:
                    pass
                self.reminders.remove(inst.args[0])
        self._save_reminders()
        await self.bot.say("All scheduled messages have been cleared.")

    @reminder.command(pass_context=True, ignore_extra=False, name='remove', aliases=['rem'])
    async def reminder_remove(self, ctx: commands.Context, index: int):
        """!kazhelp

        description: |
            Remove a reminder.

            WARNING: This command cannot be undone.
        parameters:
            - name: index
              type: int
              description: The number of the reminder to remove. See the {{!reminder list}} command
                  for the numbered list.
        examples:
            - command: .reminder rem 4
              description: Removes reminder number 4.
        """
        if index <= 0:
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                " Oops, that reminder doesn't exist!")
            return

        try:
            reminder = self.get_matching(user_id=ctx.message.author.id)[index-1]
        except IndexError:
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                " Oops, that reminder doesn't exist! You only have {:d} reminders."
                .format(self.get_count(user_id=ctx.message.author.id)))
            return

        desc = "Removed reminder for {remind_time} UTC (in {delta}): {message}".format(
                delta=format_timedelta(reminder.remind_time - datetime.utcnow()),
                **reminder.str_dict()
            )

        self.remove_reminder(reminder)
        await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + desc)

    @saylater.command(pass_context=True, ignore_extra=False, name='remove', aliases=['rem'])
    @mod_only()
    @mod_channels()
    async def saylater_remove(self, ctx: commands.Context, index: int):
        """!kazhelp

        description: |
            Remove a scheduled message.

            WARNING: This command cannot be undone.
        parameters:
            - name: index
              type: int
              description: The number of the reminder to remove. See the {{!saylater list}} command
                  for the numbered list.
        examples:
            - command: .saylater rem 4
              description: Removes message number 4.
        """
        if index <= 0:
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                " Oops, that scheduled message doesn't exist!")
            return
        try:
            reminder = self.saylaters[index-1]
        except IndexError:
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                 " Oops, that message doesn't exist! You only have {:d} messages scheduled."
                 .format(len(self.saylaters)))
            return

        desc = "Removed scheduled message "\
               "in {channel} for {remind_time} UTC (in {delta}): {message}".format(
                    delta=format_timedelta(reminder.remind_time - datetime.utcnow()),
                    **reminder.str_dict()
                )

        self.remove_reminder(reminder)
        await self.send_message(ctx.message.channel, ctx.message.author.mention + " " + desc)


def setup(bot):
    bot.add_cog(Reminders(bot))
