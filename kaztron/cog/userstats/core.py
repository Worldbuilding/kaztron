import binascii
import contextlib
import csv
import enum
import gzip
import hashlib
import logging
import os
from datetime import datetime, timedelta
from os import path
from typing import Union, Tuple, Optional, List

import discord

from kaztron import utils
import kaztron.utils.datetime
from kaztron.utils.datetime import utctimestamp

try:
    from secrets import token_urlsafe
except ImportError:
    def token_urlsafe(n: int):
        import base64
        return base64.b64encode(os.urandom(n)).decode('ascii')

logger = logging.getLogger(__name__)

stats_file_date_format = '%Y-%m-%d'
stats_file_format = '{}.csv.gz'
stats_dir = 'userstats'
out_dir = 'tmp'


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

    At the end of each accumulation period, :meth:`~.write_csv()` may be called to
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
        elif str(user).startswith('h$'):
            user_hash = user
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
        return 'h$' + binascii.hexlify(dk).decode()

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
                                  timestamp: datetime,
                                  type_: EventType,
                                  user: discord.Member,
                                  channel: discord.Channel):
        key = self._make_tuple(type_, user, channel)
        self.start_times[key] = utctimestamp(timestamp)

    def capture_timed_event_end(self,
                                timestamp: datetime,
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
                  user: Optional[discord.Member],
                  channel: Optional[discord.Channel],
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

    def write_csv(self, filepath: str, bot: discord.Client, now: datetime):
        logger.info("Writing CSV file: {}".format(filepath))
        with gzip.open(filepath, mode='at') as csvfile:
            writer = csv.writer(csvfile)
            # commit all unfinished time-based events to the main event data
            logger.debug("Time-based events: closing any unclosed events: {!r}"
                .format(self.start_times))
            for k in self.start_times.copy().keys():
                self.capture_timed_event_end(now, *k)
                self.capture_timed_event_start(now, *k)

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
            datetime.utcfromtimestamp(data['period']),
            salt=binascii.a2b_base64(data['salt']),
            hash_name=data['hash_name'],
            iterations=data['hash_iters']
        )
        self.data = {(EventType[i[0]], i[1], i[2]): i[3] for i in data['data']}
        self.start_times = {(EventType[i[0]], i[1], i[2]): i[3] for i in data['start_time_data']}
        return self


class CsvRow:
    headings = ('Period', 'Event', 'User hash (monthly)', 'Channel', 'Count')

    def __init__(self, row: List):
        self.data = row

    @property
    def period(self) -> datetime:
        return utils.datetime.parse(self.data[0])

    @property
    def event(self) -> EventType:
        return EventType[self.data[1]]

    @property
    def user(self) -> str:
        return self.data[2]

    @user.setter
    def user(self, v: str):
        self.data[2] = v

    @property
    def channel(self) -> str:
        return self.data[3]

    @property
    def count(self) -> int:
        return int(self.data[4])


def init_stats_dir():
    logger.info("Checking/making stats directory '{}'...".format(stats_dir))
    os.makedirs(stats_dir, mode=0o775, exist_ok=True)


def init_out_dir():
    logger.info("Checking/making output directory '{}'...".format(out_dir))
    os.makedirs(out_dir, mode=0o775, exist_ok=True)


def get_filepath_for(dt: datetime):
    filename = stats_file_format.format(dt.strftime(stats_file_date_format))
    filepath = path.join(stats_dir, filename)
    return filepath


def list_stats_files(from_date: datetime, to_date: datetime) -> List[str]:
    """
    Enumerate all statistics filenames between the two datetimes passed (excluding the to_date).
    The files are not guaranteed to exist, if no data was collected during that file's period.

    :param from_date: Start datetime (inclusive). Truncated to the nearest collection period (hour).
    :param to_date: End datetime (exclusive). Rounded to the nearest collection period (hour).
    :return: List of filenames.
    """
    filenames = []
    cur_date = utils.datetime.truncate(from_date, 'hour')
    end_date = utils.datetime.truncate(to_date + timedelta(minutes=30), 'hour')
    while cur_date < end_date:
        filepath = get_filepath_for(cur_date)
        if filepath not in filenames:
            filenames.append(filepath)
        cur_date += timedelta(hours=1)
    return filenames


def format_filename_date(dt: datetime) -> str:
    """ Format a filename-friendly date. The time part is ignored. """
    return dt.strftime(stats_file_date_format)


def anonymize_csv_data(from_date: datetime, to_date: datetime):
    """
    Fully anonymise the user hashes for data in a given date range.
    """
    logger.info("Anonymizing all data from {} to {}..."
        .format(from_date.isoformat(' '), to_date.isoformat(' ')))

    init_stats_dir()
    filenames = list_stats_files(from_date, to_date)
    logger.debug("Files to anonymize: {}".format(', '.join(filenames)))

    anonymizer = Anonymizer(from_date.strftime('%Y%m'))

    for in_filename in filenames:
        out_filename = in_filename + '.tmp'
        # noinspection PyPep8
        try:
            with gzip.open(in_filename, mode='rt') as infile:
                with gzip.open(out_filename, mode='wt') as outfile:
                    writer = csv.writer(outfile)
                    for row_raw in csv.reader(infile):
                        row = CsvRow(row_raw)
                        if row.user and row.user[0:2] == 'h$':
                            writer.writerow(anonymizer.anonymize(row).data)
                        else:
                            writer.writerow(row_raw)
            os.replace(out_filename, in_filename)
        except FileNotFoundError:
            logger.warning("No stats file '{}'".format(in_filename))
        except:
            os.unlink(out_filename)
            raise


class Anonymizer:
    def __init__(self, prefix):
        self._prefix = prefix
        self._hash_anon_map = {}
        self._anons = set()

    def _get_random_id(self):
        uid = token_urlsafe(6)
        while uid in self._anons:
            uid = token_urlsafe(6)
        return uid

    def anonymize(self, row: CsvRow) -> CsvRow:
        """
        Anonymize the user in a given row. Modifies the row in-place, and returns the same object
        for convenience.
        """
        try:
            anon_id = self._hash_anon_map[row.user]
        except KeyError:
            anon_id = self._get_random_id()
            self._anons.add(anon_id)
            self._hash_anon_map[row.user] = anon_id

        row.user = 'u{}${}'.format(self._prefix, anon_id)
        return row


@contextlib.contextmanager
def collect_stats(filename: str, from_date: datetime, to_date: datetime):
    """
    Collect all stats between two datetimes (including from_date but excluding to_date) as a
    compressed CSV file, stored in a temporary file, and yields the file object.

    Use in a `with` block. The temporary file is deleted upon exiting this block. This function
    is intended to immediately upload or transmit the file after generation, hence returning an
    open file object.
    """
    init_stats_dir()
    init_out_dir()

    logger.info("Collecting data into output file '{}'...".format(filename))

    filenames = list_stats_files(from_date, to_date)
    logger.debug("Files to collect: {}".format(', '.join(filenames)))

    filename = path.join(out_dir, filename)
    try:
        with open(filename, mode='w+b') as outfile:
            with gzip.open(outfile, mode='wt') as zipfile:
                zipfile.write(','.join(CsvRow.headings))
                zipfile.write('\n')
                for file in filenames:
                    logger.info("Writing '{}' to temp file...".format(file))
                    try:
                        with gzip.open(file, mode='rt') as infile:
                            for line in infile:
                                zipfile.write(line)
                    except FileNotFoundError:
                        logger.warning("No stats file '{}'".format(file))
            outfile.seek(0)
            yield outfile
    finally:
        os.unlink(filename)
