from datetime import datetime, date, timedelta, timezone
import dateparser
from typing import Union, Tuple

import discord

from kaztron.config import get_kaztron_config


DATEPARSER_SETTINGS = {
    'TIMEZONE': 'UTC',
    'TO_TIMEZONE': 'UTC',
    'RETURN_AS_TIMEZONE_AWARE': False
}


def parse(timespec: str, future=False, **kwargs):
    """
    Datetime parser, using the `dateparse` package. By default, assumes the UTC timezone unless the
    datetime string specifies timezone.

    :param timespec: String to parse
    :param future: If True, ambiguous dates should favour future times. Otherwise, past.
    :param kwargs: Any other kwargs to pass to dateparser.parse
    :return: A timezone-agnostic datetime object in UTC.
    """
    settings = DATEPARSER_SETTINGS.copy()
    settings.update(kwargs)
    if not future:
        return dateparser.parse(timespec, settings=settings)
    else:
        # workaround for https://github.com/scrapinghub/dateparser/issues/403
        # we'll try it out without this setting and return if it's in the future
        dt = dateparser.parse(timespec, settings=settings)
        if dt is None:  # not parsable
            return dt
        elif dt > datetime.utcnow():
            return dt
        else:
            settings['PREFER_DATES_FROM'] = 'future'
            return dateparser.parse(timespec, settings=settings)


def utctimestamp(utcdt: datetime):
    return utcdt.replace(tzinfo=timezone.utc).timestamp()
    

def truncate(dt: datetime, timespec='minute'):
    """
    Truncate a datetime to the resolution given by 'timespec'.

    :param dt: The datetime to round.
    :param timespec: One of "month", "day", "hour", "minute", "second" - the level of resolution
        to round to.
    :raise ValueError: invalid timespec parameter
    """
    if timespec == 'month':
        dt_replace_params = {'day': 1, 'hour': 0, 'minute': 0, 'second': 0, 'microsecond': 0}
    elif timespec == 'day':
        dt_replace_params = {'hour': 0, 'minute': 0, 'second': 0, 'microsecond': 0}
    elif timespec == 'hour':
        dt_replace_params = {'minute': 0, 'second': 0, 'microsecond': 0}
    elif timespec == 'minute':
        dt_replace_params = {'second': 0, 'microsecond': 0}
    elif timespec == 'second':
        dt_replace_params = {'microsecond': 0}
    else:
        raise ValueError("invalid timespec {!r}".format(timespec))

    try:
        return dt.replace(**dt_replace_params)
    except AttributeError as e:
        raise ValueError("invalid dt parameter {!r}".format(dt)) from e


def format_datetime(dt: datetime, seconds=False) -> str:
    """
    Format a datetime object as a datetime (as specified in config).
    :param dt: The datetime object to format.
    :param seconds: Whether or not to display seconds (this determines which config format to use).
    :return:
    """
    format_key = 'datetime_format' if not seconds else 'datetime_seconds_format'
    return dt.strftime(get_kaztron_config().get('core', format_key))


def format_date(d: Union[datetime, date]) -> str:
    """
    Format a datetime object as a date (as specified in config).

    :param d: The date or datetime object to format.
    :return:
    """
    return d.strftime(get_kaztron_config().get('core', 'date_format'))


def format_timedelta(delta: timedelta, timespec="seconds") -> str:
    """
    Format a timedelta object into "x days y hours" etc. format.

    This is ugly. Sorry.

    :param delta: The delta to format.
    :param timespec: One of "days", "hours", "minutes", "seconds", "microseconds" - the level of
        resolution to show.
    :return:
    """
    str_parts = []

    timespec_list = ['days', 'hours', 'minutes', 'seconds', 'microseconds']
    timespec_prio = timespec_list.index(timespec)

    # get a resolution object to round against
    if timespec == 'days':
        res = timedelta(days=1)
    elif timespec == 'hours':
        res = timedelta(hours=1)
    elif timespec == 'minutes':
        res = timedelta(minutes=1)
    elif timespec == 'seconds':
        res = timedelta(seconds=1)
    elif timespec == 'microseconds':
        res = None
    else:
        raise ValueError("Invalid timespec")

    # round
    if res:
        delta = (delta + res/2) // res * res

    # split up seconds into hours, minutes, seconds
    # (because timedelta only stores days and seconds???)
    rem = timedelta(seconds=delta.seconds, microseconds=delta.microseconds)
    # noinspection PyTypeChecker
    hours, rem = divmod(rem, timedelta(hours=1))
    # noinspection PyTypeChecker
    minutes, rem = divmod(rem, timedelta(minutes=1))
    # noinspection PyTypeChecker
    seconds, rem = divmod(rem, timedelta(seconds=1))

    if delta.days:
        str_parts.append("{:d} day{}".format(delta.days, 's' if abs(delta.days) != 1 else ''))
    if hours and timespec_prio >= timespec_list.index('hours'):
        str_parts.append("{:d} hour{}".format(hours, 's' if abs(hours) != 1 else ''))
    if minutes and timespec_prio >= timespec_list.index('minutes'):
        str_parts.append("{:d} minute{}".format(minutes, 's' if abs(minutes) != 1 else ''))
    if (seconds or delta.microseconds) and timespec_prio >= timespec_list.index('microseconds'):
        f_seconds = seconds + delta.microseconds/1e6
        str_parts.append("{:.6f} second{}".format(f_seconds, 's' if f_seconds != 1.0 else ''))
    elif seconds and timespec_prio >= timespec_list.index('seconds'):
        str_parts.append("{:d} second{}".format(seconds, 's' if seconds != 1 else ''))

    if not str_parts:
        if timespec == 'microseconds':
            timespec = 'seconds'
        str_parts.append("0 {}".format(timespec))

    return ' '.join(str_parts)


def format_timestamp(dt: Union[discord.Message, datetime]) -> str:
    """ Get the timestamp string of a message to second precision, with 'UTC' timezone string. """
    if isinstance(dt, discord.Message):
        dt = dt.timestamp
    return format_datetime(dt, seconds=True) + ' UTC'


def get_month_offset(dt_month: datetime, months: int) -> datetime:
    """
    Add or subtract months from a month datetime. Always returns the 1st of the month at midnight.
    :param dt_month:
    :param months: Number of months to add (>0) or subtract (<0).
    :return:
    """
    offset = abs(months)
    if months > 0:
        delta = timedelta(days=32)
    else:
        delta = timedelta(days=-1)

    new_dt = truncate(dt_month, 'month')
    for _ in range(offset):
        new_dt = truncate(new_dt + delta, 'month')
    return new_dt


def parse_daterange(daterange: str, future=False) -> Tuple[datetime, datetime]:
    """
    Process and parse a date or daterange, in the form of "X to Y".
    """
    date_split = daterange.split(' to ', maxsplit=1)

    dates = tuple(parse(date_str, future=future) for date_str in date_split)
    if None in dates:
        raise ValueError("Invalid date format(s): {!r} processed as {!r}".format(daterange, dates))

    # if only one
    if len(dates) == 1:
        dates = (dates[0], dates[0] + timedelta(days=1))

    # if the order is wrong, swap
    if dates[0] > dates[1]:
        dates = (dates[1], dates[0])

    return dates
