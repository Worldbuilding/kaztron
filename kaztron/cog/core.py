import logging

import discord
from discord.ext import commands

from kaztron.KazTron import bot_info
from kaztron.config import get_kaztron_config
from kaztron.utils.checks import mod_only
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import get_timestamp_str

logger = logging.getLogger('kaztron.' + __name__)


class CoreCog:
    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        self.ch_request = discord.Object(self.config.get('core', 'channel_request'))

    @commands.command(pass_context=True,
        description="[MOD ONLY] Provide bot info. Useful for testing but responsivity too.")
    @mod_only()
    async def info(self, ctx):
        """
        [MOD ONLY] Provides bot info and useful links.

        Also useful for testing basic bot responsivity.

        Arguments: None.
        """
        logger.debug("info(): {!s}".format(message_log_str(ctx.message)))
        em = discord.Embed(color=0x80AAFF)
        em.set_author(name="KazTron %s" % bot_info["version"])
        em.add_field(name="Changelog", value=bot_info["changelog"], inline=False)
        for title, url in bot_info["links"].items():
            em.add_field(name=title, value="[Link]({})".format(url), inline=True)
        await self.bot.say(embed=em)

    @commands.command(pass_context=True, aliases=['bug', 'issue'])
    @commands.cooldown(rate=5, per=60)
    async def request(self, ctx, *args):
        """
        Submit a bug report or feature request to the bot DevOps Team.

        Everyone can use this, but please make sure that your request is clear and has enough
        enough details. This is especially true for us to be able to track down and fix bugs:
        we need information like what were you trying to do, what did you expect to happen, what
        actually happened? Quote exact error messages and give dates/times).

        Please note that any submissions made via this system may be publicly tracked via the
        GitHub repo. By submitting a request via this system, you give us permission to post
        your username and message, verbatim or altered, to a public issue tracker for the purposes
        of bot development and project management.

        Abuse may be treated in the same way as other forms of spam on the Discord server.
        """
        logger.debug("request(): {}".format(message_log_str(ctx.message)))

        content = ctx.message.content.split(
                "{0.bot.command_prefix}{0.invoked_with} ".format(ctx))[1]

        em = discord.Embed(color=0x80AAFF)
        em.set_author(name="User Issue Submission")
        em.add_field(name="User", value=ctx.message.author.mention, inline=True)
        try:
            em.add_field(name="Channel", value=ctx.message.channel.mention, inline=True)
        except AttributeError:  # probably a private channel
            em.add_field(name="Channel", value=ctx.message.channel, inline=True)
        em.add_field(name="Timestamp", value=get_timestamp_str(ctx.message), inline=True)
        em.add_field(name="Content", value=content, inline=False)
        await self.bot.send_message(self.ch_request, embed=em)
        await self.bot.say("Your issue was submitted to the bot DevOps team. "
                           "If you have any questions or if there's an urgent problem, "
                           "please feel free to contact the moderators.")


def setup(bot):
    bot.add_cog(CoreCog(bot))
