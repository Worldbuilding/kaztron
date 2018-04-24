from typing import List

from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.errors import UnauthorizedChannelError, ModOnlyError, AdminOnlyError, DeleteMessage
from kaztron.utils.discord import check_mod, check_admin

import logging

logger = logging.getLogger('kaztron.checks')


def mod_only():
    """
    Command check decorator. Only allow mods and admins to execute this command (as defined by the
    roles in the "discord" -> "mod_roles" and "discord" -> "admin_roles" configs).
    """
    def check_mod_wrapper(ctx):
        if check_mod(ctx):
            return True
        else:
            raise ModOnlyError("Only moderators may use this command.")
    return commands.check(check_mod_wrapper)


def admin_only():
    """
    Command check decorator. Only allow admins to execute this command (as defined by the
    roles in the "discord" -> "admin_roles" config).
    """
    def check_admin_wrapper(ctx):
        if check_admin(ctx):
            return True
        else:
            raise AdminOnlyError("Only administrators may use this command.", ctx)
    return commands.check(check_admin_wrapper)


def in_channels(channel_id_list: List[str], allow_pm=False):
    """
    Command check decorator. Only allow this command to be run in specific channels (passed as a
    list of channel ID strings).
    """
    def predicate(ctx: commands.Context):
        pm_exemption = allow_pm and ctx.message.channel.is_private
        if ctx.message.channel.id in channel_id_list or pm_exemption:
            logger.info(
                "Validated command in allowed channel {!s}".format(ctx.message.channel)
            )
            return True
        else:
            raise UnauthorizedChannelError("Command not allowed in channel.", ctx)

    return commands.check(predicate)


def in_channels_cfg(config_section: str, config_name: str, allow_pm=False, delete_on_fail=False):
    """
    Command check decorator. Only allow this command to be run in specific channels (as specified
    from the config).

    The configuration can point to either a single channel ID string or a list of channel ID
    strings.

    :param config_section: The KaztronConfig section to access
    :param config_name: The KaztronConfig key containing the list of channel IDs
    :param allow_pm: Allow this command in PMs, as well as the configured channels
    :param delete_on_fail: If this check fails, delete the original message. This option does not
        delete the message itself, but throws an UnauthorizedChannelDelete error to allow an
        ``on_command_error`` handler to take appropriate action.

    :raise UnauthorizedChannelError:
    :raise UnauthorizedChannelDelete:
    """
    config = get_kaztron_config()

    def predicate(ctx: commands.Context):
        pm_exemption = allow_pm and ctx.message.channel.is_private
        config_channels = config.get(config_section, config_name)
        ctx_channel = ctx.message.channel.id
        if ctx_channel == config_channels or ctx_channel in config_channels or pm_exemption:
            logger.info(
                "Validated command in allowed channel {!s}".format(ctx.message.channel)
            )
            return True
        else:
            if not delete_on_fail:
                raise UnauthorizedChannelError("Command not allowed in channel.", ctx)
            else:
                raise DeleteMessage(ctx.message,
                    UnauthorizedChannelError("Command not allowed in channel.", ctx))

    return commands.check(predicate)


def mod_channels(delete_on_fail=False):
    """
    Command check decorator. Only allow this command to be run in mod channels (as configured
    in "discord" -> "mod_channels" config).
    """
    return in_channels_cfg('discord', 'mod_channels', allow_pm=True, delete_on_fail=delete_on_fail)


def admin_channels(delete_on_fail=False):
    """
    Command check decorator. Only allow this command to be run in admin channels (as configured
    in "discord" -> "admin_channels" config).
    """
    return in_channels_cfg('discord', 'admin_channels', allow_pm=True,
        delete_on_fail=delete_on_fail)
