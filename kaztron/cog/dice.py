import logging
import random

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.utils.logging import message_log_str

logger = logging.getLogger('kaztron.' + __name__)


class DiceCog:
    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        self.ch_dice = None
        self.ch_allowed_list = []

    async def on_ready(self):
        self.ch_dice = self.bot.get_channel(self.config.get('dice', 'channel_dice'))
        if self.ch_dice is None:
            raise ValueError("Channel {} not found".format(self.config.get('dice', 'channel_dice')))
        self.ch_allowed_list.append(self.ch_dice)
        self.ch_allowed_list.append(
                self.bot.get_channel(self.config.get("discord", "channel_test")))
        self.ch_allowed_list.append(
                self.bot.get_channel(self.config.get("discord", "channel_output")))

    @commands.command(pass_context=True, aliases=['rolls'])
    async def roll(self, ctx, dice: str):
        """
        Rolls dice.

        Rolls a <sides>-sided die <num> times, and reports the rolls and total.

        Example: `.rolls 3d6` rolls three six-sided dice.
        """
        logger.info("roll: {}".format(message_log_str(ctx.message)))

        if ctx.message.channel in self.ch_allowed_list:
            try:
                num_rolls, num_sides = map(int, dice.split('d'))
            except ValueError:
                err_msg = "Invalid format: {}".format(message_log_str(ctx.message))
                logger.warning("rolls(): " + err_msg)
                await self.bot.say('Invalid format. Please enter `.rolls XdY`, '
                                   'where X and Y are positive whole numbers.')
                return

            if num_rolls <= 0:
                logger.warning("rolls(): arguments out of range")
                await self.bot.say("You have to roll at least 1 die.")
            elif num_sides <= 1:
                logger.warning("rolls(): arguments out of range")
                await self.bot.say("Dice must have at least 2 sides.")
            elif num_sides > 100 or num_rolls > 100:
                logger.warning("rolls(): arguments out of range")
                await self.bot.say("The limit for dice number and sides is 100 each.")
            else:
                result = [random.randint(1, num_sides) for _ in range(num_rolls)]
                total = sum(result)
                await self.bot.say("{!s}\n**Sum:** {:d}".format(result, total))
                logger.info("Rolled dice: {:d}d{:d} = {!r} (sum={})"
                    .format(num_rolls, num_sides, result, total))

        else:
            logger.warning("roll: Used in disallowed channel: {}"
                    .format(message_log_str(ctx.message)))
            await self.bot.say("This command is only available in {}".format(self.ch_dice.mention))

    @commands.command(pass_context=True)
    async def rollf(self, ctx):
        """
        Rolls four dice for the FATE tabletop roleplaying game system.

        Arguments: None
        """
        logger.info("roll: {}".format(message_log_str(ctx.message)))
        if ctx.message.channel in self.ch_allowed_list:
            dice = (-1, -1, 0, 0, 1, 1)
            str_map = {-1: '-', 0: '0', 1: '+'}
            roll_results = [random.choice(dice) for _ in range(4)]
            total = sum(roll_results)
            rolls_str = [str_map[roll] for roll in roll_results]
            await self.bot.say("{!s}\n**Sum:** {:d}".format(rolls_str, total))
            logger.info("Rolled FATE dice: {!r} (sum={})".format(rolls_str, total))
        else:
            logger.warning("rollf: Used in disallowed channel: {}"
                .format(message_log_str(ctx.message)))
            await self.bot.say("This command is only available in {}".format(self.ch_dice.mention))


def setup(bot):
    bot.add_cog(DiceCog(bot))
