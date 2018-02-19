from typing import List

from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.errors import ModOnlyError, UnauthorizedChannelError, AdminOnlyError
from kaztron.utils.discord import check_role

import logging

logger = logging.getLogger('kaztron.checks')


def mod_only():
    """
    Command check decorator. Only allow mods and admins to execute this command (as defined by the
    roles in the "discord" -> "mod_roles" config).
    """
    config = get_kaztron_config()

    def predicate(ctx: commands.Context):
        if check_role(config.get("discord", "mod_roles", []), ctx.message) or\
                check_role(config.get("discord", "admin_roles", []), ctx.message):
            logger.info("Validated {!s} as moderator".format(ctx.message.author))
            return True
        else:
            raise ModOnlyError("Only moderators may use this command.", ctx)

    return commands.check(predicate)


def admin_only():
    """
    Command check decorator. Only allow admins to execute this command (as defined by the
    roles in the "discord" -> "admin_roles" config).
    """
    config = get_kaztron_config()

    def predicate(ctx: commands.Context):
        if check_role(config.get("discord", "admin_roles", []), ctx.message):
            logger.info("Validated {!s} as bot administrator".format(ctx.message.author))
            return True
        else:
            raise AdminOnlyError("Only administrators may use this command.", ctx)

    return commands.check(predicate)


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


def in_channels_cfg(config_section: str, config_name: str, allow_pm=False):
    """
    Command check decorator. Only allow this command to be run in specific channels (as specified
    from the config).
    """
    config = get_kaztron_config()

    def predicate(ctx: commands.Context):
        pm_exemption = allow_pm and ctx.message.channel.is_private
        if ctx.message.channel.id in config.get(config_section, config_name) or pm_exemption:
            logger.info(
                "Validated command in allowed channel {!s}".format(ctx.message.channel)
            )
            return True
        else:
            raise UnauthorizedChannelError("Command not allowed in channel.", ctx)

    return commands.check(predicate)


def mod_channels():
    """
    Command check decorator. Only allow this command to be run in mod channels (as configured
    in "discord" -> "mod_channels" config).
    """
    return in_channels_cfg('discord', 'mod_channels', allow_pm=True)


def admin_channels():
    """
    Command check decorator. Only allow this command to be run in admin channels (as configured
    in "discord" -> "admin_channels" config).
    """
    return in_channels_cfg('discord', 'admin_channels', allow_pm=True)
