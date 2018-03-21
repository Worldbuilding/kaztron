import datetime
from datetime import datetime, date, timedelta, timezone
from typing import Union

import discord

from kaztron.config import get_kaztron_config


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
        res = datetime.timedelta(days=1)
    elif timespec == 'hours':
        res = datetime.timedelta(hours=1)
    elif timespec == 'minutes':
        res = datetime.timedelta(minutes=1)
    elif timespec == 'seconds':
        res = datetime.timedelta(seconds=1)
    elif timespec == 'microseconds':
        res = None
    else:
        raise ValueError("Invalid timespec")

    # round
    if res:
        delta = (delta + res/2) // res * res

    # split up seconds into hours, minutes, seconds
    # (because timedelta only stores days and seconds???)
    rem = datetime.timedelta(seconds=delta.seconds, microseconds=delta.microseconds)
    hours, rem = divmod(rem, timedelta(hours=1))
    minutes, rem = divmod(rem, timedelta(minutes=1))
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
