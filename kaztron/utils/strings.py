import datetime
import re
from typing import List, Union, Dict, Iterable

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config


def format_list(list_) -> str:
    """
    Format a list as a string for display over Discord, with indices starting from 1.
    """
    digits = len(str(len(list_)))
    fmt = "{0: >" + str(digits) + "d}. {1!s:s}"
    text_bits = []
    text_bits.extend(fmt.format(i+1, item) for i, item in enumerate(list_))
    return '\n'.join(text_bits)


def split_chunks_on(str_: str, maxlen: int, split_char='\n') -> List[str]:
    """
    Split a long string along `split_char` such that all strings are smaller than but as close as
    possible to `maxlen` size.

    Lines that exceed `maxlen` size will not be split.
    """
    len_split = len(split_char)
    lines = str_.split(split_char)
    parts = []
    this_part = []
    running_len = 0
    for line in lines:
        len_line = len(line) + len_split  # can't forget the newline/split_char!
        if len_line + running_len <= maxlen:
            this_part.append(line)
            running_len += len_line
        else:
            parts.append(this_part)
            this_part = [line]
            running_len = len_line
    parts.append(this_part)  # last one, not committed in loop
    return [split_char.join(part) for part in parts]


def split_code_chunks_on(str_: str, maxlen: int, split_char='\n', lang: str=None) -> List[str]:
    """
    Same as :func:`split_chunks_on`, but returns string parts that are all formatted as Markdown
    code blocks, optionally with a language string (the original string must not already be a code
    block!).

    Lines that exceed `maxlen` size will not be split.
    """
    head = '```{}\n'.format(lang if lang else '')
    tail = '\n```'
    len_pad = len(head) + len(tail)
    raw_parts = split_chunks_on(str_, maxlen - len_pad, split_char=split_char)
    return ["{}{}{}".format(head, part, tail) for part in raw_parts]


def natural_truncate(str_: str, maxlen: int, ellipsis='[…]') -> str:
    """
    If the string is too long, truncate to up to maxlen along word boundaries, with ellipsis
    appended to the end.
    """
    maxlen_net = maxlen - len(ellipsis)
    if len(str_) > maxlen:
            trunc_str = str_[:maxlen_net]
            match = re.search(r'\W.*?$', trunc_str)
            if match:
                return str_[:match.start() + 1] + ellipsis
            else:
                return trunc_str
    else:
        return str_


def get_command_prefix(ctx: commands.Context) -> str:
    prefix = ctx.bot.command_prefix
    if callable(prefix):
        prefix = prefix(ctx.bot, ctx.message)
    return prefix


def get_command_str(ctx: commands.Context) -> str:
    """
    Get the command string, with subcommand if passed. Arguments are not included.
    :param ctx:
    :return:
    """
    # apparently in a subcommand, invoked_with == the SUBcommand, invoked_subcommand == None???
    # ... what???

    # cmd_str = "{0.bot.command_prefix}{0.invoked_with}".format(ctx)
    # if ctx.subcommand_passed:
    #    cmd_str += " {0.subcommand_passed}".format(ctx)
    # return cmd_str
    return "{0}{1.command!s}".format(get_command_prefix(ctx), ctx)


def get_help_str(ctx: commands.Context) -> str:
    """
    Gets the help string for the invoked command, with subcommand if passed.
    :param ctx:
    :return:
    """
    # Same remark as above ... what???

    # cmd_str = "{0.bot.command_prefix}help {0.invoked_with}".format(ctx)
    # if ctx.subcommand_passed:
    #     cmd_str += " {0.subcommand_passed}".format(ctx)
    # return cmd_str

    return "{0}help {1.command!s}".format(get_command_prefix(ctx), ctx)


def get_usage_str(ctx: commands.Context) -> str:
    """
    Retrieves the signature portion of the help page.

    Based on discord.ext.commands.formatter.HelpFormatter.get_command_signature()
    https://github.com/Rapptz/discord.py/blob/async/discord/ext/commands/formatter.py

    Copyright (c) 2015-2016 Rapptz. Distributed under the MIT Licence.
    """
    result = []
    prefix = get_command_prefix(ctx)
    cmd = ctx.command
    parent = cmd.full_parent_name
    if len(cmd.aliases) > 0:
        aliases = '|'.join(cmd.aliases)
        fmt = '{0}[{1.name}|{2}]'
        if parent:
            fmt = '{0}{3} [{1.name}|{2}]'
        result.append(fmt.format(prefix, cmd, aliases, parent))
    else:
        name = prefix + cmd.name if not parent else prefix + parent + ' ' + cmd.name
        result.append(name)

    params = cmd.clean_params
    if len(params) > 0:
        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str)\
                               else param.default is not None
                if should_print:
                    result.append('[{}={}]'.format(name, param.default))
                else:
                    result.append('[{}]'.format(name))
            elif param.kind == param.VAR_POSITIONAL:
                result.append('[{}...]'.format(name))
            else:
                result.append('<{}>'.format(name))

    return ' '.join(result)


def get_timestamp_str(dt: Union[discord.Message, datetime.datetime]) -> str:
    """
    Get the timestamp string of a message in ISO format, to second precision.
    """
    if isinstance(dt, discord.Message):
        dt = dt.timestamp
    return format_datetime(dt, seconds=True) + ' UTC'


def none_wrapper(value, default=""):
    """
    Pure laziness! Sometimes this ends up being nice syntactic sugar for code readability.
    """
    return value if value is not None else default


_KWARG_RE = re.compile('\s*([A-Za-z0-9_-]+)=("[^"]+"|[^ ]+)\s+(.*)')


def parse_keyword_args(keywords: Iterable[str], args: str) -> (Dict[str, str], str):
    """
    :param keywords: Valid keywords
    :param args: String argument to parse
    :return: (Dict of kwargs, remaining part of args)
    """
    kwargs = {}
    matches = _KWARG_RE.match(args)
    while matches is not None:
        key, value, args = matches.group(1, 2, 3)
        if key in kwargs:
            raise ValueError("Argument '{}' passed multiple times".format(key))
        elif key in keywords:
            kwargs[key] = value
        else:
            raise ValueError('Unknown keyword `{}`'.format(key))
        matches = _KWARG_RE.match(args)
    return kwargs, args.strip()


def format_datetime(dt: datetime.datetime, seconds=False) -> str:
    """
    Format a datetime object as a datetime (as specified in config).
    :param dt: The datetime object to format.
    :param seconds: Whether or not to display seconds (this determines which config format to use).
    :return:
    """
    format_key = 'datetime_format' if not seconds else 'datetime_seconds_format'
    return dt.strftime(get_kaztron_config().get('core', format_key))


def format_date(d: Union[datetime.datetime, datetime.date]) -> str:
    """
    Format a datetime object as a date (as specified in config).

    :param d: The date or datetime object to format.
    :return:
    """
    return d.strftime(get_kaztron_config().get('core', 'date_format'))


def format_timedelta(delta: datetime.timedelta, timespec="seconds") -> str:
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
    hours, rem = divmod(rem, datetime.timedelta(hours=1))
    minutes, rem = divmod(rem, datetime.timedelta(minutes=1))
    seconds, rem = divmod(rem, datetime.timedelta(seconds=1))

    if delta.days:
        str_parts.append("{:d} days".format(delta.days))
    if hours and timespec_prio >= timespec_list.index('hours'):
        str_parts.append("{:d} hours".format(hours))
    if minutes and timespec_prio >= timespec_list.index('minutes'):
        str_parts.append("{:d} minutes".format(minutes))
    if (seconds or delta.microseconds) and timespec_prio >= timespec_list.index('microseconds'):
        str_parts.append("{:.6f} seconds".format(seconds + delta.microseconds/1e6))
    elif seconds and timespec_prio >= timespec_list.index('seconds'):
        str_parts.append("{:d} seconds".format(seconds))

    return ' '.join(str_parts)
