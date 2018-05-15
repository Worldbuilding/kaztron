from typing import List, Union, Iterable

from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.errors import UnauthorizedUserError, UnauthorizedChannelError, DeleteMessage, \
    ModOnlyError, AdminOnlyError
from kaztron.utils.discord import check_mod, check_admin, check_role

import logging

logger = logging.getLogger('kaztron.checks')


def has_role(role_names: Union[str, Iterable[str]]):
    """
    Command check decorator for a list of role names.
    """
    return _check_role(role_names, False)


def mod_or_has_role(role_names: Union[str, Iterable[str]]):
    """
    Command check decorator. Only allows mods or users with specific roles to execute this command.
    Mods are  defined by the roles in the "discord" -> "mod_roles" and "discord" -> "admin_roles"
    configs).
    """
    return _check_role(role_names, True)


def _check_role(role_names: Union[str, Iterable[str]], with_mods):
    if isinstance(role_names, str):
        role_names = [role_names]

    def check_role_wrapper(ctx: commands.Context):
        if check_role(role_names, ctx.message) or (with_mods and check_mod(ctx)):
            return True
        else:
            msgs = {  # (single_role, with_mods)
                (True, True): "You must be a moderator or have the {r} role.",
                (True, False): "You must have the {r} role to use that command.",
                (False, True): "You must be a moderator or have one of these roles to use that "
                               "command: {rl}",
                (False, False): "You must have one of these roles to use that command: {rl}"
            }
            msg_fmt = msgs[(len(role_names) == 1, with_mods)]
            raise UnauthorizedUserError(msg_fmt.format(
                r=role_names[0] if role_names else "", rl=", ".join(role_names)
            ))
    return commands.check(check_role_wrapper)


def mod_only():
    """
    Command check decorator. Only allow mods and admins to execute this command (as defined by the
    roles in the "discord" -> "mod_roles" and "discord" -> "admin_roles" configs).
    """
    def check_mod_wrapper(ctx):
        if check_mod(ctx):
            return True
        else:
            raise ModOnlyError("Only moderators may use that command.")
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
            raise AdminOnlyError("Only administrators may use that command.", ctx)
    return commands.check(check_admin_wrapper)


def in_channels(channel_id_list: List[str], allow_pm=False, delete_on_fail=False):
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
            if not delete_on_fail:
                raise UnauthorizedChannelError("Command not allowed in channel.", ctx)
            else:
                raise DeleteMessage(
                    UnauthorizedChannelError("Command not allowed in channel.", ctx))

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
    config_channels = config.get(config_section, config_name)

    if isinstance(config_channels, str):
        config_channels = [config_channels]

    return in_channels(config_channels, allow_pm, delete_on_fail)


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
