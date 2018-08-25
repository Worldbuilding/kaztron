import discord
from discord.ext import commands

import kaztron.utils.datetime as utils_dt
from kaztron.utils.discord import get_member


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


class FutureDateRange(commands.Converter):
    """
    Convert a natural language date range, in the form "date1 to date2". If there is ambiguity to
    the range (e.g. implied year), then it will start in the future.
    """
    def convert(self):
        try:
            return utils_dt.parse_daterange(self.argument, future=True)
        except ValueError as e:
            raise commands.BadArgument(e.args[0])


class DateRange(commands.Converter):
    """
    Convert a natural language date range, in the form "date1 to date2".
    """
    def convert(self):
        try:
            return utils_dt.parse_daterange(self.argument, future=False)
        except ValueError as e:
            raise commands.BadArgument(e.args[0])


class MemberConverter2(commands.Converter):
    """
    Member converter with slightly more tolerant ID inputs permitted.
    """
    def convert(self):
        return get_member(self.ctx, self.argument)


class BooleanConverter(commands.Converter):
    """ Convert true/false words to boolean. """
    true_words = ['true', 'yes', '1', 'enabled', 'enable', 'on', 'y', 'ok', 'confirm']
    false_words = ['false', 'no', '0', 'disabled', 'disable', 'off', 'n', 'null', 'none', 'cancel']

    def convert(self):
        arg = self.argument.lower()
        if arg in self.true_words:
            return True
        elif arg in self.false_words:
            return False
        else:
            raise commands.BadArgument("{!r} is not a true/false word.".format(self.argument))


class NaturalInteger(commands.Converter):
    """
    Integer converter that is tolerant of various natural number input conventions:

    * Commas or periods as digit grouping separators
    * Period or comma as decimal point (identified as an error -> not an integer)
    * '#' prepended to an integer, for ordinals, IDs and list items.

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
        n_str = self.argument.rstrip(',.').strip('#')
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
            raise commands.BadArgument("Cannot convert {!r} to an integer.".format(n_str))

        try:
            return int(n_str.replace(',', '').replace('.', '').replace(' ', ''))
        except ValueError:
            raise commands.BadArgument("Cannot convert {!r} to an integer.".format(n_str))
