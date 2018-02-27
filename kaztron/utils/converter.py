import dateparser

from discord.ext import commands


class NaturalDateConverter(commands.Converter):
    """
    Convert natural language date strings to datetime using the dateparser library.

    Note: If the string contains spaces, the user must include it in quotation marks for it to be
    considered a single argument.
    """
    def convert(self):
        date = dateparser.parse(self.argument)
        if date is None:
            raise commands.BadArgument("Argument {!r} could not be parsed as a date string"
                .format(self.argument))
        return date
