from datetime import datetime
import logging
import os
import time
from typing import Tuple, Optional

import discord
from discord.ext import commands
from discord.ext.commands import ChannelConverter

from kaztron import KazCog, utils, theme
from kaztron.cog.userstats import core, reports
from kaztron.cog.userstats.core import EventType, StatsAccumulator
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.datetime import utctimestamp, format_date, parse_daterange
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class UserStats(KazCog):
    """
    Collects user activity statistics.

    No messages or personally identifiable information are stored by this module, only event counts
    such as number of messages in each channel on an hour-by-hour basis.

    """
    ACCUMULATOR_SETTINGS = {
        'hash_name': 'sha256',
        'iterations': 100000
    }

    SALT_PERIOD = 'month'  # must be a valid `timespec` argument to utils.datetime.truncate()

    SAVE_TIMEOUT = 15

    def __init__(self, bot):
        super().__init__(bot)
        self.setup_custom_state('userstats')
        self.ignore_user_ids = self.config.get('userstats', 'ignore_users', [])
        self.ignore_channel_ids = self.config.get('userstats', 'ignore_channels', [])

        try:
            self.last_report_dt = datetime.utcfromtimestamp(
                self.state.get('userstats', 'last_report'))
        except KeyError:
            self.last_report_dt = utils.datetime.get_month_offset(datetime.utcnow(), -1)

        self.output_file_format = 'userstats-{}-{}.csv.gz'
        self.report_file_format = 'report-{}-{}-{}-{}.csv.gz'

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
            # logger.debug("Updating total user count in accumulator...")
            user_count = 0
            for server in self.bot.servers:
                user_count += len(server.members)
            self.acc.set_event(EventType.total_users, None, None, user_count)

            # logger.debug("Saving accumulator...")
            self.state.set('userstats', 'accumulator', self.acc.to_dict())
            self.state.write(log=False)
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
        await self.init_voice_channels()
        await super().on_ready()

    async def init_voice_channels(self):
        logger.debug("Collecting all members currently in voice channels")
        now = datetime.utcnow()
        for server in self.bot.servers:
            for channel in server.channels:
                for member in channel.voice_members:
                    self.acc.capture_timed_event_start(now, EventType.voice, member, channel)

    def unload_kazcog(self):
        logger.info("Unloading: stopping all ongoing timed events")
        old_start_times = self.acc.start_times.copy()
        now = datetime.utcnow()
        for k in old_start_times.keys():
            self.acc.capture_timed_event_end(now, *k)
        self.state.set('userstats', 'accumulator', self.acc.to_dict())

    async def update_accumulator(self):
        """
        If the current accumulator period has elapsed, write the collected data from the current
        accumulator and prepare the next accumulator.
        """
        current_hour = self.get_current_hour()
        if current_hour == self.acc.period:
            return

        core.init_stats_dir()

        logger.info("Closing stats accumulator for {}".format(self.acc.period.isoformat(' ')))
        filepath = core.get_filepath_for(self.acc.period)
        now = datetime.utcnow()
        self.acc.write_csv(filepath, self.bot, now)

        logger.info("Starting new stats accumulator for {}".format(current_hour))
        old_start_times = self.acc.start_times
        self.acc = StatsAccumulator(
            current_hour,
            salt=self.get_next_salt(self.acc.period, current_hour, self.acc.salt),
            **self.ACCUMULATOR_SETTINGS
        )
        now = datetime.utcnow()
        for k in old_start_times.keys():
            self.acc.capture_timed_event_start(now, *k)
        self.acc.start_times.update(old_start_times)
        self.save_accumulator(force=True)

        await self.do_monthly_tasks()

    async def show_report(self, dest, report: reports.Report):
        em = discord.Embed(
            title=report.name,
            color=theme.solarized.magenta
        )
        em.add_field(name="Total users", value=str(report.total_users), inline=True)
        em.add_field(name="Active users", value=str(report.active_users), inline=True)
        em.add_field(name="Voice users", value=str(report.voice_users), inline=True)
        em.add_field(
            name="Delta users",
            value="{} (+{}|-{})".format(report.joins-report.parts, report.joins, report.parts),
            inline=True
        )
        em.add_field(name="Messages", value=str(report.messages), inline=True)
        em.add_field(
            name="Messages/user",
            value="{0[0]:.1f} (σ={0[1]:.1f})".format(report.messages_per_user),
            inline=True
        )
        em.add_field(
            name="Voice time",
            value="{:.1f} man-hours".format(report.voice_time/3600),
            inline=True
        )
        em.add_field(
            name="Voice time/user",
            value="{0[0]:.1f}h (σ={0[1]:.1f}h)"
                  .format(tuple(v/3600 for v in report.voice_time_per_user)),
            inline=True
        )

        await self.bot.send_message(dest, embed=em)

    async def do_monthly_tasks(self):
        last_month = utils.datetime.get_month_offset(self.acc.period, -1)
        if last_month > self.last_report_dt:
            logger.debug("monthly tasks: last month {}, last report {}".format(
                last_month.isoformat(' '), self.last_report_dt.isoformat(' ')
            ))
            # Do all months since the last month processed
            month = utils.datetime.get_month_offset(self.last_report_dt, 1)
            while month <= last_month:
                logger.info("Doing monthly tasks for {}".format(month.strftime('%B %Y')))
                await self.anonymize_monthly_data(month)
                await self.generate_monthly_report(month)
                month = utils.datetime.get_month_offset(month, 1)

            self.last_report_dt = last_month
            self.state.set('userstats', 'last_report', utctimestamp(self.last_report_dt))
            self.state.write()

    async def generate_monthly_report(self, month: datetime):
        """
        Generate this month's report, if it has not yet been generated.
        :param month: The 1st of the month to generate a report for.
        """
        report = reports.prepare_report(month, utils.datetime.get_month_offset(month, 1))
        report.name = "Report for {}".format(month.strftime('%B %Y'))
        await self.show_report(self.channel_out, report)
        await self.send_output(
            "**Monthly reports now available!** Check `.help report` for help on generating "
            "and viewing detailed reports.")

    async def anonymize_monthly_data(self, month: datetime):
        core.anonymize_csv_data(month, utils.datetime.get_month_offset(month, 1))
        await self.send_output(
            "**Userstats** Anonymisation completed for {}".format(month.strftime('%B %Y')))

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

    @staticmethod
    def default_daterange() -> Tuple[datetime, datetime]:
        """ Return the default daterange (last month). """
        end = utils.datetime.truncate(datetime.utcnow(), 'month')
        start = utils.datetime.get_month_offset(end, -1)
        return start, end

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def userstats(self, ctx: commands.Context, *, daterange: str=None):
        """
        [MOD ONLY] Retrieve a CSV dump of stats for a date or range of dates.

        If a range of dates is specified, the data retrieved is up to and EXCLUDING the second date.
        A day starts at midnight UTC.

        Note that if the range crosses month boundaries (e.g. March to April), then the unique user
        hashes can be correlated between each other only within a given month. The same user will
        have different hashes in different months. This is used as a anonymisation method, to avoid
        long-term tracking of a unique user.

        This will generate and upload a CSV file, and could take some time. Please avoid calling
        this function multiple times for the same data or requesting giant ranges.

        The file is compressed using gzip. Windows users should use a modern archiving programme
        like 7zip <https://www.7-zip.org/download.html>; macOS users can open these files
        natively. Linux users know the drill.

        Arguments:
        * daterange. Optional. This can be a single date (period of 24 hours), or a range of
          dates in the form `date1 to date2`. Each date can be specified as ISO format
          (2018-01-12), in English with or without abbreviations (12 Jan 2018), or as relative dates
          (5 days ago). Default is last month.

        Examples:
        .userstats 2018-01-12
        .userstats yesterday
        .userstats 2018-01-12 to 2018-01-14
        .userstats 3 days ago to yesterday
        .userstats 2018-01-01 to 7 days ago
        """
        logger.debug("userstats: {}".format(message_log_str(ctx.message)))

        if daterange:
            dates = parse_daterange(daterange)
        else:
            dates = self.default_daterange()

        await self.bot.say("One moment, collecting stats for {} to {}..."
            .format(format_date(dates[0]), format_date(dates[1])))

        filename = self.output_file_format.format(
            core.format_filename_date(dates[0]),
            core.format_filename_date(dates[1])
        )
        with core.collect_stats(filename, dates[0], dates[1]) as collect_file:
            logger.info("Sending collected stats file.")
            await self.bot.send_file(ctx.message.channel, collect_file, filename=filename,
                content="User stats for {} to {}"
                        .format(format_date(dates[0]), format_date(dates[1])))

        if dates[1] >= utils.datetime.get_month_offset(self.last_report_dt, 1):
            self.bot.say("**WARNING:** Data not yet anonymised - "
                         "hashes on an unexpired salt are in use. Do not distribute.")

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def report(self, ctx: commands.Context, type_: str, channel: str=None,
                     *, daterange: str=None):
        """
        [MOD ONLY] Generate and show a statistics report for a date or range of dates.

        If a range of dates is specified, the data retrieved is up to and EXCLUDING the second date.
        A day starts at midnight UTC.

        The date range cannot cross the boundary of one month (because unique users are not tracked
        from month to month for anonymisation reasons; it's only possible to identify unique users
        within the same month).

        This will read and process the raw data to generate stats, and could take some time. Please
        avoid calling this function multiple times for the same data or requesting giant ranges.

        The file is compressed using gzip. Windows users should use a modern archiving programme
        like 7zip <https://www.7-zip.org/download.html>; macOS users can open these files
        natively. Linux users know the drill.

        Arguments:
        * type: One of "full", "weekday" or "hourly". "weekday" and "hourly" take the raw data and
            provide a breakdown by day of the week or hour of the day, respectively.
        * channel: The name of a channel on the server, or "all".
        * daterange. Optional. This can be a single date (period of 24 hours), or a range of
          dates in the form `date1 to date2`. Each date can be specified as ISO format
          (2018-01-12), in English with or without abbreviations (12 Jan 2018), or as relative dates
          (5 days ago). Default is last month.

        Examples:
        .report full all 2018-01-12
        .report full all yesterday
        .report full #general 2018-01-12 to 2018-01-14
        .report weekday all 3 days ago to yesterday
        .report hourly #worldbuilding 2018-01-01 to 7 days ago
        """
        logger.debug("report: {}".format(message_log_str(ctx.message)))

        type_ = type_.lower()
        types = ["full", "weekday", "hourly"]
        if type_ not in types:
            raise commands.BadArgument("Invalid type; types in {}".format(types))

        if daterange:
            dates = parse_daterange(daterange)
        else:
            dates = self.default_daterange()

        if channel.lower() != 'all':
            conv = ChannelConverter(ctx, channel)
            channel = conv.convert()
        else:
            channel = None

        await self.bot.say("Preparing report, please wait...")

        if type_ == "full":
            report = reports.prepare_report(*dates, channel=channel)
            if not channel:
                report.name = "Report for {} to {}"\
                    .format(format_date(dates[0]), format_date(dates[1]))
            else:  # channel
                report.name = "Report for #{} from {} to {}"\
                    .format(channel.name, format_date(dates[0]), format_date(dates[1]))
            await self.show_report(ctx.message.channel, report)
        elif type_ == "weekday":
            filename = self.report_file_format.format(
                type_,
                channel.name if channel is not None else 'all',
                core.format_filename_date(dates[0]),
                core.format_filename_date(dates[1])
            )
            week_reports = reports.prepare_weekday_report(*dates, channel=channel)
            heads = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
            with reports.collect_report_matrix(filename, week_reports, heads) as collect_file:
                logger.info("Sending collected reports file.")
                if channel:
                    msg = "Weekly report for {} from {} to {}"\
                        .format(channel.name, format_date(dates[0]), format_date(dates[1]))
                else:
                    msg = "Weekly report for {} to {}"\
                        .format(format_date(dates[0]), format_date(dates[1]))
                await self.bot.send_file(
                    ctx.message.channel, collect_file, filename=filename, content=msg)
        elif type_ == "hourly":
            filename = self.report_file_format.format(
                type_,
                channel.name if channel is not None else 'all',
                core.format_filename_date(dates[0]),
                core.format_filename_date(dates[1])
            )
            hourly_reports = reports.prepare_hourly_report(*dates, channel=channel)
            heads = tuple(str(i) for i in range(24))
            with reports.collect_report_matrix(filename, hourly_reports, heads) as collect_file:
                logger.info("Sending collected reports file.")
                if channel:
                    msg = "Hourly report for {} from {} to {}" \
                        .format(channel.name, format_date(dates[0]), format_date(dates[1]))
                else:
                    msg = "Hourly report for {} to {}" \
                        .format(format_date(dates[0]), format_date(dates[1]))
                await self.bot.send_file(
                    ctx.message.channel, collect_file, filename=filename, content=msg)
