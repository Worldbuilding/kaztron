from discord.ext import commands

class DiscordErrorCodes:
    # https://discordapp.com/developers/docs/topics/opcodes-and-status-codes
    CANNOT_PM_USER = 50007


class BotNotReady(commands.CommandError):
    pass


class BotCogError(commands.CommandError):
    pass


class CogNotLoadedError(RuntimeError):
    pass


class UnauthorizedUserError(commands.CheckFailure):
    pass


class ModOnlyError(UnauthorizedUserError):
    pass


class AdminOnlyError(UnauthorizedUserError):
    pass


class UnauthorizedChannelError(commands.CheckFailure):
    pass


class DeleteMessage(commands.CommandError):
    """
    Wrapper error that signals a need to delete the original command attempt. Message object is
    retrieved from the :cls:`~discord.Context` object only when this error is handled by
    :meth:`~kaztron.cog.core.on_command_error`.

    :param cause: The exception that caused this one.
    """
    def __init__(self, cause: Exception):
        self.cause = cause
        super().__init__("Delete message due to exception: {}".format(self.cause))
