import datetime
import re
from typing import List, Union, Dict, Iterable

import discord
from discord.ext import commands


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
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
    :
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
