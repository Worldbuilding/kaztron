import logging
import random

from discord.ext import commands

from kaztron import errors, KazCog
from kaztron.config import SectionView
from kaztron.utils.discord import channel_mention
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class DiceConfig(SectionView):
    channel_dice: str


class Dice(KazCog):
    """!kazhelp
    category: Commands
    brief: Various dice rolls and other randomness-based commands.
    description:
    contents:
        - choose
        - roll
        - rollf
    """
    cog_config: DiceConfig
    MAX_CHOICES = 20

    def __init__(self, bot):
        super().__init__(bot, 'dice', DiceConfig)
        self.cog_config.set_converters('channel_dice',
            lambda cid: self.validate_channel(cid),
            lambda _: None)
        self.ch_dice = None

    async def on_ready(self):
        await super().on_ready()
        self.ch_dice = self.cog_config.channel_dice

    @commands.command(pass_context=True, ignore_extra=False, no_pm=False, aliases=['rolls'])
    async def roll(self, ctx, dice: str):
        """!kazhelp

        description: Rolls dice.
        details: "Rolls an `m`-sided die `n` times, and reports the rolls and total."
        parameters:
            - name: dice
              type: string
              description: "`ndm` format, where `n` is the number of dice to roll,
                and `m` is the number of sides on each die. Do not add spaces."
        examples:
            - command: .roll 2d6
              description: Roll three six-sided dice.
        """
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

    @commands.command(pass_context=True, ignore_extra=False, no_pm=False)
    async def rollf(self, ctx):
        """!kazhelp
        description: Rolls four dice for the FATE tabletop roleplaying game system.
        """
        dice = (-1, -1, 0, 0, 1, 1)
        str_map = {-1: '-', 0: '0', 1: '+'}
        roll_results = [random.choice(dice) for _ in range(4)]
        total = sum(roll_results)
        rolls_str = [str_map[roll] for roll in roll_results]
        await self.bot.say("[{}]\n**Sum:** {:d}".format(' '.join(rolls_str), total))
        logger.info("Rolled FATE dice: {!r} (sum={})".format(rolls_str, total))

    @commands.command(pass_context=True, ignore_extra=False, no_pm=False)
    async def choose(self, ctx, *, choices: str):
        """!kazhelp

        brief: Randomly choose from a list of items.
        description: |
            Need some help making a decision? Let the bot choose for you! This command
            randomly chooses from a list of items.
        parameters:
            - name: choices
              type: string
              description: Two or more choices, separated by commas `,`.
        examples:
            - command: .choose a, b, c
        """
        choices = list(map(str.strip, choices.split(",")))
        if "" in choices:
            logger.warning("choose(): argument empty")
            await self.bot.say("I cannot decide if there's an empty choice.")
        elif len(choices) < 2:
            logger.warning("choose(): arguments out of range")
            await self.bot.say("I need something to choose from.")
        elif len(choices) > self.MAX_CHOICES:
            logger.warning("choose(): arguments out of range")
            await self.bot.say("I don't know, that's too much to choose from! "
                "I can't handle more than {:d} choices!".format(self.MAX_CHOICES))
        else:
            r = random.randint(0, len(choices) - 1)
            await self.bot.say(choices[r])

    @roll.error
    @rollf.error
    async def roll_on_error(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc

            if isinstance(root_exc, errors.UnauthorizedChannelError):
                logger.error("Unauthorized use of command in #{1}: {0}"
                             .format(cmd_string, ctx.message.channel.name))
                await self.bot.send_message(
                    ctx.message.channel,
                    "Sorry, this command can only be used in {}"
                    .format(channel_mention(self.ch_allowed_list[0]))
                )

            else:
                core_cog = self.bot.get_cog("CoreCog")
                await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(Dice(bot))
