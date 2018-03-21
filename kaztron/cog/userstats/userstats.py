from datetime import datetime, timedelta
import logging
import os
import time
from typing import Tuple, Optional

import dateparser
import discord
from discord.ext import commands

from kaztron import KazCog, utils
from kaztron.cog.userstats import core
from kaztron.cog.userstats.core import EventType, StatsAccumulator
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.datetime import utctimestamp, format_date
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class UserStats(KazCog):
    """
    Collects user activity statistics.

    No messages or personally identifiable information is stored by this module, but only event
    counts such as number of messages in each channel on an hour-by-hour basis.
    """
    DATEPARSER_SETTINGS = {
        'TIMEZONE': 'UTC',
        'TO_TIMEZONE': 'UTC',
        'RETURN_AS_TIMEZONE_AWARE': False
    }

    ACCUMULATOR_SETTINGS = {
        'hash_name': 'sha256',
        'iterations': 100000
    }

    SALT_PERIOD = 'month'  # must be a valid `timespec` argument to utils.datetime.truncate()

    SAVE_TIMEOUT = 120

    def __init__(self, bot):
        super().__init__(bot)
        self.setup_custom_state('userstats')
        self.ignore_user_ids = self.config.get('userstats', 'ignore_users', [])
        self.ignore_channel_ids = self.config.get('userstats', 'ignore_channels', [])
        self.dest_output = discord.Object(id=self.config.get('discord', 'channel_output'))
        self.output_file_format = 'userstats-{}-{}.csv.gz'

        self.acc = None  # type: StatsAccumulator
        self.last_acc_save = 0

        self.load_accumulator()

    def load_accumulator(self):
        acc_dict = self.state.get('userstats', 'accumulator', {})

        if acc_dict:
            self.acc = StatsAccumulator.from_dict(acc_dict)
        else:
            current_hour = self.get_current_hour()
            if self.acc:
                next_salt = self.get_next_salt(self.acc.period, current_hour, self.acc.salt)
            else:
                next_salt = self.get_next_salt(None, current_hour)
            self.acc = StatsAccumulator(current_hour, salt=next_salt, **self.ACCUMULATOR_SETTINGS)

        self.last_acc_save = time.monotonic()

    def save_accumulator(self, force=False):
        if force or time.monotonic() - self.last_acc_save >= self.SAVE_TIMEOUT:
            logger.debug("Updating total user count in accumulator...")
            user_count = 0
            for server in self.bot.servers:
                user_count += len(server.members)
            self.acc.set_event(EventType.total_users, None, None, user_count)

            logger.debug("Saving accumulator...")
            self.state.set('userstats', 'accumulator', self.acc.to_dict())
            self.state.write()
            self.last_acc_save = time.monotonic()

    def get_next_salt(self,
                      prev_period: Optional[datetime],
                      next_period: datetime,
                      prev_salt: bytes=None):
        salt_period = self.SALT_PERIOD
        if prev_period is not None:
            prev_month = utils.datetime.truncate(prev_period, salt_period)
        else:
            prev_month = None
        next_month = utils.datetime.truncate(next_period, salt_period)

        if prev_salt and prev_month and prev_month == next_month:
            return prev_salt
        else:
            logger.info("Generating new salt...")
            return os.urandom(32)

    @staticmethod
    def get_current_hour():
        return utils.datetime.truncate(datetime.utcnow(), 'hour')

    async def on_ready(self):
        await self.update_accumulator()
        await super().on_ready()

    async def update_accumulator(self):
        """
        If the current accumulator period has elapsed, write the collected data from the current
        accumulator and prepare the next accumulator.
        """
        current_hour = self.get_current_hour()
        if current_hour == self.acc.period:
            return

        core.init_dir()

        logger.info("Closing stats accumulator for {}".format(self.acc.period.isoformat(' ')))
        filepath = core.get_filepath_for(self.acc.period)
        self.acc.write_anonymised_csv(filepath, self.bot, datetime.utcnow())

        logger.info("Starting new stats accumulator for {}".format(current_hour))
        old_start_times = self.acc.start_times
        self.acc = StatsAccumulator(
            current_hour,
            salt=self.get_next_salt(self.acc.period, current_hour, self.acc.salt),
            **self.ACCUMULATOR_SETTINGS
        )
        self.acc.start_times.update(old_start_times)
        self.save_accumulator(force=True)

        # TODO: announce daily/weekly available reports and commands for it
        # TODO: announcement including some basic activity stats?

    @ready_only
    async def on_message(self, message: discord.Message):
        """ On message received, record the event. """
        await self.update_accumulator()

        ignored_user = message.author.id in self.ignore_user_ids
        ignored_channel = message.channel.id in self.ignore_channel_ids

        if not ignored_user and not ignored_channel and not message.channel.is_private:
            self.acc.capture_event(EventType.msg, message.author, message.channel)
            self.save_accumulator()

    @ready_only
    async def on_member_join(self, member: discord.Member):
        """ On member join, record the event. """
        await self.update_accumulator()

        if member.id not in self.ignore_user_ids:
            self.acc.capture_event(EventType.join, None, None)
            self.save_accumulator()

    @ready_only
    async def on_member_remove(self, member: discord.Member):
        """ On member part, record the event. """
        await self.update_accumulator()

        if member.id not in self.ignore_user_ids:
            self.acc.capture_event(EventType.part, None, None)
            self.save_accumulator()

    @ready_only
    async def on_voice_state_update(self, before: discord.Member, after: discord.Member):
        """ Record voice chat usage events. """
        await self.update_accumulator()

        modified = False

        if before.voice_channel and before.voice_channel not in self.ignore_channel_ids:
            self.acc.capture_timed_event_end(
                datetime.utcnow(), EventType.voice, after, before.voice_channel
            )
            modified = True

        if after.voice_channel and after.voice_channel not in self.ignore_channel_ids:
            self.acc.capture_timed_event_start(
                datetime.utcnow(), EventType.voice, after, after.voice_channel
            )
            modified = True

        if modified:
            self.save_accumulator()

    def process_daterange(self, daterange: str) -> Tuple[datetime, datetime]:
        """
        Process and parse a date or daterange, in the form of "X to Y".
        """
        date_split = daterange.split(' to ', maxsplit=1)
        logger.debug("Identified date strings: {!r}".format(date_split))

        dates = tuple(dateparser.parse(date_str, settings=self.DATEPARSER_SETTINGS)
                      for date_str in date_split)
        if None in dates:
            logger.warning("Invalid datespec(s) passed: '{}' split as {!r}"
                .format(daterange, date_split))
            raise commands.BadArgument("Invalid date format(s)")

        # if only one
        if len(dates) == 1:
            dates = (dates[0], dates[0] + timedelta(days=1))

        # if the order is wrong, swap
        if dates[0] > dates[1]:
            dates[0], dates[1] = dates[1], dates[0]

        return dates

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def userstats(self, ctx: commands.Context, *, daterange: str):
        """
        Retrieve a CSV dump of stats for a date or range of dates.

        If a range of dates is specified, the data retrieved is up to and EXCLUDING the second date.
        A day starts at midnight UTC.

        This will generate and upload a CSV file, and could take some time. Please avoid calling
        this function multiple times for the same data or requesting giant ranges.

        Parameters:
        * daterange. This can be a single date, or a range of dates in the form
          `date1 to date2`. Each date can be specified as ISO format (2018-01-12), in English with
          or without abbreviations (12 Jan 2018), or as relative times (5 days ago).

        Examples:
        .userstats 2018-01-12
        .userstats yesterday
        .userstats 2018-01-12 to 2018-01-14
        .userstats 3 days ago to yesterday
        .userstats 2018-01-01 to 7 days ago
        """
        logger.debug("userstats: {}".format(message_log_str(ctx.message)))

        dates = self.process_daterange(daterange)

        await self.bot.say("One moment, collecting stats for {} to {}..."
            .format(format_date(dates[0]), format_date(dates[1])))

        with core.collect_stats(dates[0], dates[1]) as collect_file:
            logger.info("Sending collected stats file.")
            filename = self.output_file_format.format(
                core.format_filename_date(dates[0]),
                core.format_filename_date(dates[1])
            )
            await self.bot.send_file(ctx.message.channel, collect_file, filename=filename,
                content="User stats for {} to {}"
                        .format(format_date(dates[0]), format_date(dates[1])))

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def report(self, ctx: commands.Context, *, daterange: str):
        """
        Generate and show a statistics report for a date or range of dates.

        If a range of dates is specified, the data retrieved is up to and EXCLUDING the second date.
        A day starts at midnight UTC.

        This will read and process the raw data to generate stats, and could take some time. Please
        avoid calling this function multiple times for the same data or requesting giant ranges.

        Parameters:
        * daterange. This can be a single date, or a range of dates in the form
          `date1 to date2`. Each date can be specified as ISO format (2018-01-12), in English with
          or without abbreviations (12 Jan 2018), or as relative times (5 days ago).

        Examples:
        .report 2018-01-12
        .report yesterday
        .report 2018-01-12 to 2018-01-14
        .report 3 days ago to yesterday
        .report 2018-01-01 to 7 days ago
        """
        logger.debug("report: {}".format(message_log_str(ctx.message)))
        dates = self.process_daterange(daterange)
        # TODO


    # TODO: AND IDEAS, NOT NECESSARILY FINAL
    # some commands to retrieve basic activity stats for a given date or week (# active users, messages, - see the github issue w/viz's interests)
    # global and per channel hour-by-hour stats, regenerated and stored daily???
