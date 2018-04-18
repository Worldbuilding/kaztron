import discord
from discord.ext import commands

import kaztron.utils.datetime as utils_dt
from kaztron.utils.discord import extract_user_id


class NaturalDateConverter(commands.Converter):
    """
    Convert natural language date strings to datetime using the dateparser library.

    Note: If the string contains spaces, the user must include it in quotation marks for it to be
    considered a single argument.
    """
    def convert(self):
        date = utils_dt.parse(self.argument)
        if date is None:
            raise commands.BadArgument("Argument {!r} could not be parsed as a date string"
                .format(self.argument))
        return date


class MemberConverter2(commands.MemberConverter):
    """
    Member converter with slightly more tolerant ID inputs permitted.
    """
    def convert(self):
        try:
            s_user_id = extract_user_id(self.argument)
        except discord.InvalidArgument:
            s_user_id = self.argument
        self.argument = s_user_id
        return super().convert()


class NaturalInteger(commands.Converter):
    """
    Integer converter that is tolerant of various natural number input conventions (e.g. commas as
    digit grouping separators).

    This converter is tolerant of three common locale conventions, along with normal Python integer
    literals, and attempts a best guess at conversion:

    * 1,000,000 (commas as thousands separator)
    * 1.000.000 (periods as thousands separator)
    * 1 000 000 (spaces as thousands separators)
    * 1000000 (Python integer literal)

    NOTE: The spaces convention may not be very useful, as with most command arguments, the space is
    used to separate arguments. These numbers would need to be enclosed in quotes by the user, or
    input as the final keyword argument to the command, or manually parsed.

    There is naturally an ambiguity when it comes to decimal numbers, as the first 2 locales use
    each other's thousands separators. In the case that only one thousand separator is present, this
    converter checks if it's separating a grouping of 3 digits to validate that the input isn't
    an erroneous decimal value:

    * "1.234" interpreted as 1234
    * "1,234" interpreted as 1234
    * "1,22" interpret as a float 1.22 (error)
    * "1.22" interpreted as a float 1.22 (error)

    :raise commands.BadArgument: Cannot interpret as integer. This includes inputs that are detected
        as floating-point.
    """
    def convert(self):
        n_str = self.argument
        try:
            return int(n_str)
        except ValueError:
            pass

        # Simple conversion didn't work, try to eliminate if it's a float first
        commas_split = n_str.split(',')
        periods_split = n_str.split('.')
        if (len(commas_split) > 1 and len(periods_split) > 1)\
                or (len(commas_split) == 2 and len(commas_split[1]) != 3)\
                or (len(periods_split) == 2 and len(periods_split[1]) != 3):
            raise commands.BadArgument("Argument {!r} must be an integer, not a decimal number."
                .format(n_str))
        if any(len(c) != 3 for c in commas_split[1:])\
                or any(len(c) != 3 for c in periods_split[1:])\
                or any(len(c) != 3 for c in n_str.split(' ')[1:]):
            raise commands.BadArgument("Cannot convert {!r} to an integer.")

        try:
            return int(n_str.replace(',', '').replace('.', '').replace(' ', ''))
        except ValueError:
            raise commands.BadArgument("Cannot convert {!r} to an integer.")
