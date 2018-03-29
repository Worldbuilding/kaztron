import contextlib
import csv
import gzip
import os
from datetime import datetime, timedelta
from os import path
from typing import Sequence, Tuple, List, Callable
import logging

import discord

from kaztron.utils import datetime as utils_dt
from kaztron.cog.userstats.core import EventType, list_stats_files, \
    init_stats_dir, init_out_dir, out_dir, CsvRow
from kaztron.driver.stats import MeanVarianceAccumulator

logger = logging.getLogger(__name__)


class Report:
    """
    Data structure containing summarised user statistics during a period of time.

    :ivar name: The title of the report, containing information about scope and otherwise (e.g. full
        report, or weekday/hourly reports, or specific channels, etc.)
    :ivar period: Covered period for the report, including the start point but excluding the end.
    :ivar total_users: Total users at the end of the period.
    :ivar messages: Total messages.
    :ivar active_users: Unique active users in text channels during the period.
    :ivar messages_per_user: The mean and standard deviation of messages posted per active user.
    :ivar voice_time: Total voice time by all users (man-seconds).
    :ivar voice_users: Total unique users who used voice during the period.
    :ivar voice_time_per_user: The mean and standard deviation of voice time per unique voice user.
    :ivar joins: Total joins during the period.
    :ivar parts: Total parts during the period.
    """
    def __init__(self):
        self.name = None  # type: str
        self.period = (None, None)  # type: Tuple[datetime, datetime]
        self.total_users = None  # type: int
        self.messages = None  # type: int
        self.active_users = None  # type: int
        self.messages_per_user = (None, None)  # type: Tuple[float, float]
        self.voice_time = None  # type: int
        self.voice_users = None  # type: int
        self.voice_time_per_user = (None, None)  # type: Tuple[float, float]
        self.joins = None  # type: int
        self.parts = None  # type: int


class ReportGenerator:
    def __init__(self, name: str, start: datetime, end: datetime):
        start_month = utils_dt.truncate(start, 'month')
        # end is excluded from the range - if it's the 1st, subtraction forces into prev month
        end_month = utils_dt.truncate(end - timedelta(seconds=1), 'month')
        if start_month != end_month:
            raise ValueError("Reports can't span across different months!")
        self._name = name
        self._period = (start, end)
        self._data = {}
        self._total_users = 0
        self._total_users_date = None

    def add_data(self, row: CsvRow):
        """
        Add a new event row to the report. This method aggregates all data by 1) event and 2) user,
        effectively reducing it over time (period) and channels.
        """
        key = self._make_tuple(row)
        if key[0] != EventType.total_users:
            # normal count events
            self._data[key] = self._data.get(key, 0) + row.count
        else:
            period = row.period
            # total users event: only keep the most recent total user count
            if self._total_users_date is None or period > self._total_users_date:
                self._total_users = row.count
                self._total_users_date = period

    @staticmethod
    def _make_tuple(row: CsvRow):
        return row.event, row.user

    def generate(self) -> Report:
        """ Generate the report with the data collected so far. """
        logger.debug("Generating report: {}".format(self._name))

        msg_stats = MeanVarianceAccumulator()
        voice_stats = MeanVarianceAccumulator()
        total_joins = 0
        total_parts = 0

        for key, count in self._data.items():
            event, user = key
            if event is EventType.msg:
                msg_stats.update(count)
            elif event is EventType.voice:
                voice_stats.update(count)
            elif event is EventType.join:
                total_joins += count
            elif event is EventType.part:
                total_parts += count

        report = Report()
        report.name = self._name
        report.period = self._period
        report.total_users = self._total_users
        report.messages = msg_stats.sum
        report.active_users = msg_stats.count
        report.messages_per_user = (msg_stats.mean, msg_stats.std_dev)
        report.voice_time = voice_stats.sum
        report.voice_users = voice_stats.count
        report.voice_time_per_user = (voice_stats.mean, voice_stats.std_dev)
        report.joins = total_joins
        report.parts = total_parts
        return report


def prepare_report(from_date: datetime, to_date: datetime, channel: discord.Channel=None) \
        -> Report:
    """
    Generate a report between two dates (including from_date but excluding to_date).
    """
    logger.info("Preparing full report for {} to {}..."
        .format(from_date.isoformat(' '), to_date.isoformat(' ')))
    generator = ReportGenerator("Full report", from_date, to_date)

    def row_callback(row: CsvRow):
        generator.add_data(row)

    _prepare_report_inner(from_date, to_date, channel, row_callback)

    return generator.generate()


def prepare_weekday_report(from_date: datetime, to_date: datetime, channel: discord.Channel=None)\
        -> Tuple[Report, ...]:
    """
    Generate a report between two dates (including from_date but excluding to_date), aggregated
    by day of the week.

    :return: A tuple of 7 reports, Monday (index=0) to Sunday (index=6).
    """
    logger.info("Preparing weekday reports for {} to {}..."
        .format(from_date.isoformat(' '), to_date.isoformat(' ')))
    generators = []  # type: List[ReportGenerator]
    # indices here correspond to datetime.weekday values
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        generators.append(ReportGenerator("Weekday report: {}".format(day), from_date, to_date))

    def row_callback(row: CsvRow):
        period = row.period
        generators[period.weekday()].add_data(row)

    _prepare_report_inner(from_date, to_date, channel, row_callback)

    return tuple(g.generate() for g in generators)


def prepare_hourly_report(from_date: datetime, to_date: datetime, channel: discord.Channel=None)\
        -> Tuple[Report, ...]:
    """
    Generate a report between two dates (including from_date but excluding to_date), aggregated
    by hour of the day.

    :return: A tuple of 24 reports, from hour 0 to 23 (UTC).
    """
    logger.info("Preparing hourly reports for {} to {}..."
        .format(from_date.isoformat(' '), to_date.isoformat(' ')))

    generators = []  # type: List[ReportGenerator]
    for hour in range(24):
        generators.append(ReportGenerator("Hourly report: {}h".format(hour), from_date, to_date))

    def row_callback(row: CsvRow):
        period = row.period
        generators[period.hour].add_data(row)

    _prepare_report_inner(from_date, to_date, channel, row_callback)

    return tuple(g.generate() for g in generators)


def _prepare_report_inner(from_date, to_date, channel: discord.Channel,
                          row_callback: Callable[[CsvRow], None]):
    filenames = list_stats_files(from_date, to_date)
    logger.debug("Report: Files to collect: {}".format(', '.join(filenames)))
    for file in filenames:
        logger.debug("Opening '{}' for report...".format(file))
        try:
            with gzip.open(file, mode='rt') as infile:
                for row_raw in csv.reader(infile):
                    row = CsvRow(row_raw)
                    if channel is None or not row.channel or '#' + channel.name == row.channel:
                        row_callback(row)
        except FileNotFoundError:
            logger.warning("No stats file '{}'".format(file))


@contextlib.contextmanager
def collect_report_matrix(filename: str, reports: Sequence[Report], heads: Sequence[str]):
    """
    Generate a CSV file corresponding to the given reports.
    """
    init_stats_dir()
    init_out_dir()

    filename = path.join(out_dir, filename)
    logger.info("Collecting report into output file '{}'...".format(filename))
    try:
        with open(filename, mode='w+b') as outfile:
            with gzip.open(outfile, mode='wt') as zipfile:
                zipfile.write(','.join(["Case", "Total users", "Active users", "Voice users",
                                        "Joins", "Parts",
                                        "Messages", "Messages/user", "(stdev)",
                                        "Voice man-hours", "Voice hours/user", "(stdev)"]))
                zipfile.write('\n')
                for heading, report in zip(heads, reports):
                    zipfile.write(','.join(
                        [str(v) for v in
                         (heading, report.total_users, report.active_users, report.voice_users,
                          report.joins, report.parts,
                          report.messages, *report.messages_per_user,
                          report.voice_time/3600, *[v/3600 for v in report.voice_time_per_user]
                          )]))
                    zipfile.write('\n')
            outfile.seek(0)
            yield outfile
    finally:
        os.unlink(filename)
