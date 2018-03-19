import csv
import datetime
import enum
import gzip
import hashlib
import logging
from os import path
import os
import time
from typing import Tuple, List, Union, Optional

import binascii
import dateparser
import discord
from discord.ext import commands

from kaztron import KazCog, utils
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only
from kaztron.utils.datetime import utctimestamp
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_date

logger = logging.getLogger(__name__)


class EventType(enum.Enum):
    msg = 0
    join = 1
    part = 2
    voice = 3
    total_users = 4


class StatsAccumulator:
    """
    Statistics accumulator.

    Counts the number of events for various event tuples: (EventType, channel_id, user_id).

    :meth:`~.to_dict()` and :meth:`~.from_dict()` can be used to store into persisted state, with no
    anonymisation. This should ONLY be used to prevent data loss while accumulating, and not for
    long term storage, due to the lack of anonymisation.

    At the end of each accumulation period, :meth:`~.write_anonymised_csv()` may be called to
    anonymise user information and output as a CSV for storage and later analysis. Note that
    anonymisation is performed by securely hashing user information with a salt - this salt is to
    later be discarded once the CSV has been written. This ensures that it is possible to collect
    statistics across different Accumulator outputs, while ensuring no link between the user and
    data can reasonably be made.

    :param period: The start time of the period covered.
    :param salt: The salt to use for user anonymisation.
    :param hash_name: The name of the hash to use for user anonymisation.
    :param iterations: The number of hash iterations to use.
    """
    def __init__(self, period: datetime, salt: bytes, hash_name='sha256', iterations=100000):
        self.data = {}
        self.start_times = {}
        self.period = period
        self.salt = salt

        self.hash_name = hash_name
        self.hash_iters = iterations

    def _make_tuple(self,
                    type_: EventType,
                    user: Union[discord.Member, str],
                    channel: Union[discord.Channel, str]) -> Tuple:
        if isinstance(user, discord.Member):
            user_hash = self._hash(user.id)
        elif user is None:
            user_hash = None
        else:
            user_hash = self._hash(str(user))
        return type_, user_hash, channel.id if isinstance(channel, discord.Channel) else channel

    def _hash(self, data):
        if not isinstance(data, bytes):
            data = str(data)

        if isinstance(data, str):
            data = data.encode('utf-8', 'replace')

        dk = hashlib.pbkdf2_hmac(self.hash_name, data, self.salt, self.hash_iters)
        return binascii.hexlify(dk).decode()

    def capture_event(self,
                      type_: EventType,
                      user: Optional[discord.Member],
                      channel: Optional[discord.Channel]):
        key = self._make_tuple(type_, user, channel)
        try:
            self.data[key] += 1
        except KeyError:
            self.data[key] = 1

    def capture_timed_event_start(self,
                                  timestamp: datetime.datetime,
                                  type_: EventType,
                                  user: discord.Member,
                                  channel: discord.Channel):
        key = self._make_tuple(type_, user, channel)
        self.start_times[key] = utctimestamp(timestamp)

    def capture_timed_event_end(self,
                                timestamp: datetime.datetime,
                                type_: EventType,
                                user: discord.Member,
                                channel: discord.Channel):
        key = self._make_tuple(type_, user, channel)
        try:
            start_time = self.start_times[key]
            del self.start_times[key]
        except KeyError:
            pass
        else:
            try:
                self.data[key] += int(utctimestamp(timestamp) - start_time + 0.5)
            except KeyError:
                self.data[key] = int(utctimestamp(timestamp) - start_time + 0.5)

    def set_event(self,
                  type_: EventType,
                  user: discord.Member,
                  channel: discord.Channel,
                  value: int):
        key = self._make_tuple(type_, user, channel)
        self.data[key] = value

    def get(self, type_: EventType, user: discord.Member, channel: discord.Channel) -> int:
        """ Retrieve an event count. If the tuple is not found, returns 0. """
        key = self._make_tuple(type_, user, channel)
        try:
            return self.data[key]
        except KeyError:
            return 0

    def find(self,
            type_: EventType=None,
            user: discord.Member=None,
            channel: discord.Channel=None) -> List[Tuple[EventType, str, str, int]]:
        """
        Search for data. This is an O(n) operation, searches for any combination of parameters.

        :return: A list of tuples containing (type, user_hash, channel_id, count)
        """

        def tuple_filt(t: tuple):
            return ((type_ is None or type_ == t[0]) and
                    (user is None or user.id == t[1]) and
                    (channel is None or channel.id == t[2]))

        # noinspection PyTypeChecker
        return [(*key, self.data[key]) for key in filter(tuple_filt, self.data.keys())]

    def write_anonymised_csv(self, filepath: str, bot: discord.Client, now: datetime.datetime):
        logger.info("Writing CSV file: {}".format(filepath))
        autoinc = 0
        with gzip.open(filepath, mode='at') as csvfile:
            writer = csv.writer(csvfile)
            # commit all unfinished time-based events to the main event data
            logger.debug("Time-based events: closing any unclosed events: {!r}"
                .format(self.start_times))
            for k in self.start_times.keys():
                self.capture_timed_event_end(now, k[0], k[1], k[2])
                self.capture_timed_event_start(now, k[0], k[1], k[2])

            # write all events
            logger.debug("Writing all events to CSV...")
            rows = []
            period_str = self.period.isoformat(' ')
            for k, v in self.data.items():
                channel = bot.get_channel(k[2])
                channel_name = ('#' + channel.name) if channel else k[2]
                rows.append([period_str, k[0].name, k[1], channel_name, v])
            writer.writerows(rows)

    def to_dict(self):
        return {
            'data': [(k[0].name, k[1], k[2], v) for k, v in self.data.items()],
            'start_time_data': [(k[0].name, k[1], k[2], v) for k, v in self.start_times.items()],
            'period': utctimestamp(self.period),
            'salt': binascii.b2a_base64(self.salt).decode(),

            'hash_name': self.hash_name,
            'hash_iters': self.hash_iters
        }

    @staticmethod
    def from_dict(data: dict):
        self = StatsAccumulator(
            datetime.datetime.utcfromtimestamp(data['period']),
            salt=binascii.a2b_base64(data['salt']),
            hash_name=data['hash_name'],
            iterations=data['hash_iters']
        )
        self.data = {(EventType[i[0]], i[1], i[2]): i[3] for i in data['data']}
        self.start_times = {(EventType[i[0]], i[1], i[2]): i[3] for i in data['start_time_data']}
        return self


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
        self.ignore_user_ids = self.config.get('userstats', 'ignore_users', [])
        self.ignore_channel_ids = self.config.get('userstats', 'ignore_channels', [])
        self.dest_output = discord.Object(id=self.config.get('discord', 'channel_output'))
        self.stats_dir = self.config.get('userstats', 'data_dir', 'userstats')
        self.file_date_format = '%Y-%m-%d'
        self.file_format = '{}.csv.gz'
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
                next_salt = self.get_next_salt(None, current_hour, None)
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

    def get_next_salt(self, prev_period: datetime, next_period: datetime, prev_salt: bytes):
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
        return utils.datetime.truncate(datetime.datetime.utcnow(), 'hour')

    def get_filepath_for(self, dt: datetime.datetime):
        filename = self.file_format.format(dt.strftime(self.file_date_format))
        filepath = path.join(self.stats_dir, filename)
        return filepath

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

        logger.info("Checking/making directory '{}'...".format(self.stats_dir))
        os.makedirs(self.stats_dir, mode=0o775, exist_ok=True)

        logger.info("Closing stats accumulator for {}".format(self.acc.period.isoformat(' ')))
        filepath = self.get_filepath_for(self.acc.period)
        self.acc.write_anonymised_csv(filepath, self.bot, datetime.datetime.utcnow())

        logger.info("Starting new stats accumulator for {}".format(current_hour))
        old_start_times = self.acc.start_times
        self.acc = StatsAccumulator(
            current_hour,
            salt=self.get_next_salt(self.acc.period, current_hour, self.acc.salt),
            **self.ACCUMULATOR_SETTINGS
        )
        self.acc.start_times.update(old_start_times)
        self.save_accumulator(force=True)

        # announce daily/weekly available reports and commands for it
        # announcement including some basic activity stats?

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
                datetime.datetime.utcnow(), EventType.voice, after, before.voice_channel
            )
            modified = True

        if after.voice_channel and after.voice_channel not in self.ignore_channel_ids:
            self.acc.capture_timed_event_start(
                datetime.datetime.utcnow(), EventType.voice, after, after.voice_channel
            )
            modified = True

        if modified:
            self.save_accumulator()

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
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
            dates = (dates[0], dates[0] + datetime.timedelta(days=1))

        # if the order is wrong, swap
        if dates[0] > dates[1]:
            dates[0], dates[1] = dates[1], dates[0]

        await self.bot.say("One moment, collecting stats for {} to {}..."
            .format(format_date(dates[0]), format_date(dates[1])))

        filenames = []
        cur_date = dates[0].replace(microsecond=0, second=0, minute=0)
        end_date = dates[1].replace(microsecond=0, second=0, minute=0)
        while cur_date < end_date:
            filepath = self.get_filepath_for(cur_date)
            if filepath not in filenames:
                filenames.append(filepath)
            cur_date += datetime.timedelta(hours=1)

        logger.debug("Files to collect: {}".format(', '.join(filenames)))

        logger.info("Writing temp file...")
        with gzip.open('temp.csv.gz', mode='wt') as outfile:
            outfile.write('Period,Event,Unique user,Channel,Count\n')
            for file in filenames:
                logger.info("Writing '{}' to temp file...".format(file))
                try:
                    with gzip.open(file, mode='rt') as infile:
                        for line in infile:
                                outfile.write(line)
                except FileNotFoundError:
                    logger.warning("No stats file '{}'".format(file))

        logger.info("Sending collected stats file.")
        filename = self.output_file_format.format(
            dates[0].strftime(self.file_date_format),
            dates[1].strftime(self.file_date_format)
        )
        with open('temp.csv.gz', mode='rb') as tempfile:
            await self.bot.send_file(ctx.message.channel, tempfile, filename=filename,
                content="User stats for {} to {}"
                        .format(format_date(dates[0]), format_date(dates[1])))


    # TODO: AND IDEAS, NOT NECESSARILY FINAL
    # some commands to retrieve basic activity stats for a given date or week (# active users, messages, - see the github issue w/viz's interests)
    # global and per channel hour-by-hour stats, regenerated and stored daily???


def setup(bot):
    bot.add_cog(UserStats(bot))
