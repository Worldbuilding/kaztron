from discord import Message
from discord.ext import commands


class BotNotReady(commands.CommandError):
    pass


class UnauthorizedUserError(commands.CommandError):
    pass


class ModOnlyError(UnauthorizedUserError):
    pass


class AdminOnlyError(UnauthorizedUserError):
    pass


class UnauthorizedChannelError(commands.CommandError):
    pass


class DeleteMessage(commands.CommandError):
    def __init__(self, message: Message, cause: Exception):
        self.message = message
        self.cause = cause
        super().__init__("Delete message due to exception: {}".format(self.cause))
