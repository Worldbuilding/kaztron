from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.errors import ModOnlyError
from kaztron.utils.discord import check_role

import logging

logger = logging.getLogger('kaztron.checks')


def mod_only():
    """
    From a given context, check if a command was sent by a mod/admin.
    """
    config = get_kaztron_config()

    def predicate(ctx):
        if check_role(config.get("discord", "mod_roles", []), ctx.message):
            logger.info("Validated {!s} as moderator".format(ctx.message.author))
            return True
        else:
            raise ModOnlyError("Only moderators may use this command.")

    return commands.check(predicate)
