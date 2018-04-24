import re

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config

import logging

logger = logging.getLogger('kaztron.discord')

MSG_MAX_LEN = 2000


class Limits:
    MESSAGE = MSG_MAX_LEN
    EMBED_TOTAL = 6000
    EMBED_TITLE = 256
    EMBED_DESC = 2048
    EMBED_FIELD_NAME = 256
    EMBED_FIELD_VALUE = 1024
    EMBED_FIELD_NUM = 25
    NAME = 32


def check_role(rolelist, message):
    """
    Check if the author of a ``message`` has one of the roles in ``rolelist``.

    :param rolelist: A list of role names.
    :param message: A :cls:``discord.Message`` object representing the message
        to check.
    """
    for role in rolelist:
        # noinspection PyBroadException
        try:
            if discord.utils.get(message.server.roles, name=role) in message.author.roles:
                return True
        except Exception:
            pass
    else:
        return False


def get_named_role(server: discord.Server, role_name: str) -> discord.Role:
    """
    Get a role by name. This is a convenience function, providing a ValueError if the role does not
    exist instead of returning None and causing a less clear exception downstream.

    :param server: Server on which to find the role
    :param role_name: Role name to find
    :return: Discord Role corresponding to the given name
    :raises ValueError: role does not exist
    """
    role = discord.utils.get(server.roles, name=role_name)
    if role is None:
        raise ValueError("Role '{!s}' not found.".format(role_name))
    return role


def check_mod(ctx: commands.Context):
    """
    Check if the sender of a command is a mod or admin (as defined by the
    roles in the "discord" -> "mod_roles" and "discord" -> "admin_roles" configs).
    """
    config = get_kaztron_config()
    return check_role(config.get("discord", "mod_roles", []), ctx.message) or \
        check_role(config.get("discord", "admin_roles", []), ctx.message)


def check_admin(ctx: commands.Context):
    """
    Check if the sender of a command is an admin (as defined by the
    roles in the "discord" -> "admin_roles" config).
    """
    config = get_kaztron_config()
    return check_role(config.get("discord", "admin_roles", []), ctx.message)


async def remove_role_from_all(client: discord.Client, server: discord.Server, role: discord.Role):
    """
    Removes a role from all users on the server who have that role.
    :param client: Discord client or bot instance.
    :param server:
    :param role:
    """
    for u in server.members:
        if role in u.roles:
            await client.remove_roles(u, role)


def user_mention(user_id: str) -> str:
    """
    Return a mention of a user that can be sent over a Discord message. This is a convenience
    method for cases where the user_id is known but you don't have or need the full discord.User
    or discord.Member object.
    """
    if not user_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<@{}>'.format(user_id)


def role_mention(role_id: str) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    if not role_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<@&{}>'.format(role_id)


def channel_mention(channel_id: str) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    if not channel_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<#{}>'.format(channel_id)


_re_user_id = re.compile('(?:<@|@)?!?([0-9]{15,23})>?')


def extract_user_id(input_id: str) -> str:
    """
    Validate and extract a user ID from an input (@mention, raw user ID, etc.).

    This method is intended to validate and sanitise an input provided by a user, e.g., over a
    command. It can accept:

    * Raw ID: '123456789012345678'
    * Mentions:
        * No nickname: '<@123456789012345678>'
        * User has nickname: '<@!123456789012345678>'
    * Attempts to provide a raw ID:
        * '@123456789012345678'
        * '@!123456789012345678'
        * '!123456789012345678'
    * Various errors:
        * <@123456789012345678
        * 123456789012345678>
        * etc.

    User ID parameters from:
    https://github.com/Rapptz/discord.py/blob/1863a1c6636f53592519320a173ec9573c090c0b/discord/ext/commands/converter.py#L83

    :param input_id: The raw input ID.
    :return: The extracted user ID (numerical string).
    :raise discord.InvalidArgument: id is not a recognised user ID format
    """
    try:
        return _re_user_id.fullmatch(input_id).group(1)
    except AttributeError:  # no match - fullmatch() returned None
        raise discord.InvalidArgument('Invalid user ID format {!r}'.format(input_id))


def get_member(ctx: commands.Context, user: str) -> discord.Member:
    """
    Return the :cls:`discord.Member` for a given input identifying a user (ID, mention, name, etc.).
    
    The user must be a member of a visible server. The current server (as determined by context)
    is prioritised in searching.
    
    This function is intended to be robust for various types of inputs that may be input by
    a user to a bot command:
    
    * Simple ID: '123456789012345678'
    * Mentions:
        * No nickname: '<@123456789012345678>'
        * User has nickname: '<@!123456789012345678>'
    * Variations on mentions altered by user:
        * '@123456789012345678'
        * '@!123456789012345678'
        * '!123456789012345678'
    * Search by user name and discriminator:
        * JaneDoe#0921
        * JaneDoe
    
    :return:
    :raises discord.InvalidArgument: user not found
    """

    # try our own extractor as it handles more weird input cases
    # if fail assume it's a name lookup
    try:
        s_user_id = extract_user_id(user)
    except discord.InvalidArgument:
        s_user_id = user

    member_converter = commands.MemberConverter(ctx, s_user_id)
    try:
        return member_converter.convert()
    except commands.BadArgument:
        raise discord.InvalidArgument(
            "User ID format {!r} is invalid or user not found".format(user)
        )


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


def get_group_help(ctx: commands.Context):
    command_list = list(ctx.command.commands.keys())
    return ('Invalid sub-command. Valid sub-commands are {0!s}. '
            'Use `{1}` or `{1} <subcommand>` for instructions.') \
        .format(command_list, get_help_str(ctx))
