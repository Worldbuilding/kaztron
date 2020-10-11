import logging
from datetime import datetime

from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.datetime import format_datetime
from kaztron.utils.discord import channel_mention

logger = logging.getLogger(__name__)


class DiscordTools(KazCog):
    """!kazhelp
    category: Commands
    brief: Various tools to help with Discord.
    description:
    contents:
        - id
        - rchid
    """

    def __init__(self, bot):
        super().__init__(bot)

    @commands.command(pass_context=True, ignore_extra=True, no_pm=False)
    async def id(self, ctx: commands.Context):
        """!kazhelp

        description: Gets your own user ID.
        parameters: []
        examples:
            - command: .id
              description: Gets your own user ID.
        """
        await self.send_message(ctx.message.channel, ctx.message.author.mention +
            " Your ID is: " + ctx.message.author.id)

    @commands.command(pass_context=True, ignore_extra=True, no_pm=False, aliases=['now', 'time'])
    async def kaztime(self, ctx: commands.Context):
        """!kazhelp

        description: "Gets the current KazTron Time (UTC, GMT). Can be used to help convert
            community programme schedules to your timezone."
        parameters: []
        examples:
            - command: .kaztime
              description: Shows the current time.
        """
        await self.send_message(ctx.message.channel, ctx.message.author.mention +
            "Current KazTime: {} UTC".format(format_datetime(datetime.utcnow(), seconds=True)))

    @commands.command(pass_context=True, ignore_extra=True, no_pm=False)
    @mod_only()
    @mod_channels()
    async def rchid(self, ctx: commands.Context, *, ids: str):
        """!kazhelp

        description: Convert channel IDs to channel links.
        details: "This command is primarily intended for bot operators to help in validating
            the configuration file."
        parameters:
            - name: ids
              type: str
              description: "A list of channel IDs. They may be comma- or line-separated and may or
                may not be quoted, using either double or single quotes."
        examples:
            - command: |
                    .rchid "123456789012345678", "876543210987654321"
              description: Translates these two IDs into channel names, e.g., #general, #potato.
        """
        ids_list = [s.strip().strip(r"'\"[]{}") for s in ids.replace(',', '\n').splitlines()]
        await self.send_message(ctx.message.channel, ctx.message.author.mention + "\n" +
            '\n'.join(channel_mention(cid) for cid in ids_list))


def setup(bot):
    bot.add_cog(DiscordTools(bot))
