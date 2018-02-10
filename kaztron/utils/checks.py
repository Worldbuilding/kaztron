from typing import List

from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.errors import ModOnlyError, UnauthorizedChannelError
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
        if check_role(config.get("discord", "mod_roles", []), ctx.message):
            logger.info("Validated {!s} as moderator".format(ctx.message.author))
            return True
        else:
            raise ModOnlyError("Only moderators may use this command.", ctx)

    return commands.check(predicate)


def in_channels(channel_id_list: List[str]):
    """
    Command check decorator. Only allow this command to be run in specific channels (passed as a
    list of channel ID strings).
    """
    def predicate(ctx: commands.Context):
        if ctx.message.channel.id in channel_id_list:
            logger.info(
                "Validated command in allowed channel #{!s}".format(ctx.message.channel.name)
            )
            return True
        else:
            raise UnauthorizedChannelError("Command not allowed in channel.", ctx)

    return commands.check(predicate)


def in_channels_cfg(config_section: str, config_name: str):
    """
    Command check decorator. Only allow this command to be run in specific channels (as specified
    from the config).
    """
    config = get_kaztron_config()

    def predicate(ctx: commands.Context):
        if ctx.message.channel.id in config.get(config_section, config_name):
            logger.info(
                "Validated command in allowed channel #{!s}".format(ctx.message.channel.name)
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
    return in_channels_cfg('discord', 'mod_channels')
