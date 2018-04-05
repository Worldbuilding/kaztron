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
        super().convert()
