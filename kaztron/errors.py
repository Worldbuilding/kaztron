from discord.ext import commands


class UnauthorizedUserError(commands.CommandError):
    pass


class ModOnlyError(UnauthorizedUserError):
    pass


