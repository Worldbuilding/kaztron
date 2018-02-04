from collections import deque

import discord
from discord.ext import commands


def format_list(list_) -> str:
    """
    Format a list as a string for display over Discord, with indices starting from 1.
    """
    fmt = "{0: >3d}. {1:s}"
    text_bits = ["```"]
    text_bits.extend(fmt.format(i+1, item) for i, item in enumerate(list_))
    text_bits.append("```")
    return '\n'.join(text_bits)


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
    return "{0.bot.command_prefix}{0.command!s}".format(ctx)


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

    return "{0.bot.command_prefix}help {0.command!s}".format(ctx)
