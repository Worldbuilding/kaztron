import discord


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
        except:
            pass
    else:
        return False
