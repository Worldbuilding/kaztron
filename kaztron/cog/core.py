import logging

import sys
import discord

import kaztron
from kaztron.errors import *
from kaztron.config import get_kaztron_config
from kaztron.utils.checks import mod_only
from kaztron.utils.logging import message_log_str, exc_log_str, tb_log_str
from kaztron.utils.strings import get_timestamp_str, get_command_str, get_help_str

logger = logging.getLogger(__name__)


class CoreCog:
    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        self.ch_request = discord.Object(self.config.get('core', 'channel_request'))
        self.dest_output = discord.Object(id=self.config.get('discord', 'channel_output'))

    async def on_ready(self):
        logger.debug("on_ready")

        playing = self.config.get('discord', 'playing', default="")
        if playing:
            await self.bot.change_presence(game=discord.Game(name=playing))

        startup_info = (
            "Logged in as {} (id:{})".format(self.bot.user.name, self.bot.user.id),
            "KazTron version {}".format(kaztron.__version__),
            "discord.py version {}".format(discord.__version__)
        )

        for msg in startup_info:
            logger.info(msg)  # for file logging
            print(msg)  # because current console logger always logs at WARN level

    async def on_error(self, event, *args, **kwargs):
        exc_info = sys.exc_info()
        if exc_info[0] is KeyboardInterrupt:
            logger.warning("Interrupted by user (SIGINT)")
            raise exc_info[1]

        log_msg = "Error occurred in {}({}, {})".format(
            event,
            ', '.join(repr(arg) for arg in args),
            ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
        logger.exception(log_msg)
        await self.bot.send_message(self.dest_output,
            "[ERROR] {} - see logs for details".format(exc_log_str(exc_info[1])))

        try:
            message = args[0]
            await self.bot.send_message(message.channel,
                "An error occurred! Details have been logged. "
                "Please let the mods know so we can investigate.")
        except IndexError:
            pass
        except AttributeError:
            logger.warning("Couldn't extract channel context from previous error - "
                           "is args[0] not a message?")

    async def on_command_error(self, exc, ctx, force=False):
        """
        Handles all command errors (see the ``discord.ext.commands.errors`` module).
        This method will do nothing if a command is detected to have an error
        handler ("on_error"); if you want on_command_error's default behaviour to
        take over, within a command error handler, you can call this method and
        pass ``force=True``.

        If you define custom command error handlers, note that CommandInvokeError
        is the one you want to handle for arbitrary errors (i.e. any exception
        raised that isn't derived from CommandError will cause discord.py to raise
        a CommandInvokeError from it).
        """
        cmd_string = message_log_str(ctx.message)

        if not force and hasattr(ctx.command, "on_error"):
            return

        if isinstance(exc, commands.CommandOnCooldown):
            await self.bot.send_message(ctx.message.channel,
                "`{}` is on cooldown! Try again in {:.0f} seconds."
                    .format(get_command_str(ctx), max(exc.retry_after, 1.0)))

        elif isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc
            if isinstance(root_exc, KeyboardInterrupt):
                logger.warning("Interrupted by user (SIGINT)")
                raise root_exc
            elif isinstance(root_exc, discord.HTTPException):  # API errors
                err_msg = 'While executing {c}\n\nDiscord API error {e!s}' \
                    .format(c=cmd_string, e=root_exc)
                logger.error(err_msg + "\n\n{}".format(tb_log_str(root_exc)))
                await self.bot.send_message(self.dest_output,
                    "[ERROR] " + err_msg + "\n\nSee log for details")
            else:
                logger.error("An error occurred while processing the command: {}\n\n{}"
                    .format(cmd_string, tb_log_str(root_exc)))
                await self.bot.send_message(self.dest_output,
                    "[ERROR] While executing {}\n\n{}\n\nSee logs for details"
                        .format(cmd_string, exc_log_str(root_exc)))

            # In all cases (except if return early/re-raise)
            await self.bot.send_message(ctx.message.channel,
                "An error occurred! Details have been logged. Let a mod know so we can "
                "investigate.")

        elif isinstance(exc, commands.DisabledCommand):
            msg = "Attempt to use disabled command: {}".format(cmd_string)
            logger.warning(msg)
            # No need to log this on Discord - not something mods need to be aware of
            # No need to inform user of this - prevents spam, "disabled" commands could just not
            # exist

        elif isinstance(exc, ModOnlyError):
            err_msg = "Unauthorised user for this command (not a moderator): {!r}".format(
                cmd_string)
            logger.warning(err_msg)
            await self.bot.send_message(self.dest_output, '[WARNING] ' + err_msg)
            await self.bot.send_message(ctx.message.channel,
                "Only mods can use that command.")

        elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
            logger.warning(
                "Check failed on command: {!r}\n\n{}".format(cmd_string, tb_log_str(exc)))
            await self.bot.send_message(ctx.message.channel,
                "You're not allowed to use that command. "
                " (Dev note: Implement error handler + specify more precise reason)")

        elif isinstance(exc, commands.NoPrivateMessage):
            msg = "Attempt to use non-PM command in PM: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                "Sorry, you can't use that command in PM.")
            # No need to log this on Discord, spammy and isn't something mods need to be aware of

        elif isinstance(exc, commands.BadArgument):
            msg = "Bad argument passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                ("Invalid argument(s) for the command `{}`. "
                 "Check that the arguments after the command name are correct."
                 "Use `{}` for instructions. "
                 "(Dev note: Implement error handler + specify more precise check)")
                    .format(get_command_str(ctx), get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.TooManyArguments):
            msg = "Too many arguments passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                ("Too many arguments for the command `{}`. "
                 "Check that the arguments after the command name are correct. "
                 "Use `{}` for instructions.")
                    .format(get_command_str(ctx), get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.MissingRequiredArgument):
            msg = "Missing required arguments in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                ("Missing argument(s) for the command `{}`. "
                 "Check that you've passed all the needed arguments after the command name. "
                 "Use `{}` for instructions. "
                 "(Dev note: Implement error handler + specify more precise check)")
                    .format(get_command_str(ctx), get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.CommandNotFound):
            msg = "Unknown command: {}".format(cmd_string)
            # avoid some natural language things that start with period (ellipsis, etc.)
            if ctx.invoked_with not in ['.', '..'] and not ctx.invoked_with.startswith('.'):
                logger.warning(msg)
                await self.bot.send_message(ctx.message.channel,
                    "Sorry, I don't know the command `{}{}`"
                        .format(self.bot.command_prefix, ctx.invoked_with))

        else:
            logger.exception("Unknown exception occurred")
            await self.bot.send_message(ctx.message.channel,
                "An error occurred! Details have been logged. Let a mod know so we can "
                "investigate.")
            await self.bot.send_message(self.dest_output,
                ("[ERROR] Unknown error while trying to process command {}\n"
                 "Error: {!s}\n\nSee logs for details").format(cmd_string, exc))

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
        em.set_author(name="KazTron %s" % kaztron.bot_info["version"])
        em.add_field(name="Changelog", value=kaztron.bot_info["changelog"], inline=False)
        for title, url in kaztron.bot_info["links"].items():
            em.add_field(name=title, value="[Link]({})".format(url), inline=True)
        await self.bot.say(embed=em)

    @commands.command(pass_context=True, aliases=['bug', 'issue'])
    @commands.cooldown(rate=5, per=60)
    async def request(self, ctx):
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
