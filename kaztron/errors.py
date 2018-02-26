from discord.ext import commands


class UnauthorizedUserError(commands.CommandError):
    pass


class ModOnlyError(UnauthorizedUserError):
    pass


class AdminOnlyError(UnauthorizedUserError):
    pass


class UnauthorizedChannelError(commands.CommandError):
    pass
