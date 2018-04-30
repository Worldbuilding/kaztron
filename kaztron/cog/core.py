import asyncio
import logging

import sys
import discord

import kaztron
from kaztron.errors import *
from kaztron.utils.checks import mod_only
from kaztron.utils.logging import message_log_str, exc_log_str, tb_log_str
from kaztron.utils.discord import get_command_prefix, get_command_str, get_help_str, get_usage_str
from kaztron.utils.datetime import format_timestamp

logger = logging.getLogger(__name__)


class CoreCog(kaztron.KazCog):

    def __init__(self, bot):
        super().__init__(bot)
        self.ch_request = discord.Object(self.config.get('core', 'channel_request'))
        self.name = self.config.get("core", "name", "KazTron")

        self.bot.event(self.on_error)  # register this as a global event handler, not just local
        self.bot.add_check(self.check_bot_ready)
        self.ready_cogs = set()

    def check_bot_ready(self, ctx: commands.Context):
        """ Check if bot is ready. Used as a global check. """
        if ctx.cog is not None:
            if ctx.cog in self.ready_cogs:
                return True
            else:
                raise BotNotReady(type(ctx.cog).__name__)
        elif self in self.ready_cogs or not isinstance(ctx.cog, kaztron.KazCog):
            return True
        else:
            raise BotNotReady(type(self).__name__)

    def set_cog_ready(self, cog):
        """
        Called by the kaztron.KazCog base to signal it has executed its on_ready handler and is
        ready to receive commands.
        """
        logger.info("Cog ready: {}".format(type(cog).__name__))
        self.ready_cogs.add(cog)

    def set_cog_shutdown(self, cog):
        logger.info("Cog has been shutdown: {}".format(type(cog).__name__))
        self.ready_cogs.remove(cog)
        if cog.state != self.state:  # not using global state (saving handled in runner)
            cog.state.write()

    async def on_ready(self):
        logger.debug("on_ready")

        playing = self.config.get('discord', 'playing', default="")
        if playing:
            await self.bot.change_presence(game=discord.Game(name=playing))

        startup_info = (
            "Bot name {}".format(self.name),
            "KazTron version {}".format(kaztron.__version__),
            "discord.py version {}".format(discord.__version__),
            "Logged in as {} (id:{})".format(self.bot.user.name, self.bot.user.id),
        )

        for msg in startup_info:
            logger.info(msg)  # for file logging

        for msg in startup_info:  # Iterate again to keep these together in logs
            print(msg)  # in case console logger is below INFO level - display startup info

        try:
            await self.send_output(
                "**{} is running**\n".format(self.name) + '\n'.join(startup_info)
            )
        except discord.HTTPException:
            logger.exception("Error sending startup information to output channel")

        await super().on_ready()

    async def on_error(self, event, *args, **kwargs):
        exc_info = sys.exc_info()
        if exc_info[0] is KeyboardInterrupt:
            logger.warning("Interrupted by user (SIGINT)")
            raise exc_info[1]
        elif exc_info[0] is asyncio.CancelledError:
            raise exc_info[1]
        elif exc_info[0] is BotNotReady:
            logger.warning("Event {} called before on_ready: ignoring".format(event))
            return

        log_msg = "Error occurred in {}({}, {})".format(
            event,
            ', '.join(repr(arg) for arg in args),
            ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
        logger.exception(log_msg)
        await self.send_output("[ERROR] {} - see logs for details".format(exc_log_str(exc_info[1])))

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
        author_mention = ctx.message.author.mention + ' '

        if not force and hasattr(ctx.command, "on_error"):
            return

        if ctx is not None and ctx.command is not None:
            usage_str = get_usage_str(ctx)
        else:
            usage_str = '(Unable to retrieve usage information)'

        if isinstance(exc, DeleteMessage):
            try:
                await self.bot.delete_message(exc.message)
                logger.info("on_command_error: Deleted invoking message")
            except discord.errors.DiscordException:
                logger.exception("Can't delete invoking message!")
            exc = exc.cause
        # and continue on to handle the cause of the DeleteMessage...

        if isinstance(exc, commands.CommandOnCooldown):
            await self.bot.send_message(ctx.message.channel, author_mention +
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
                await self.send_output(
                    "[ERROR] " + err_msg + "\n\nSee log for details")
            else:
                logger.error("An error occurred while processing the command: {}\n\n{}"
                    .format(cmd_string, tb_log_str(root_exc)))
                await self.send_output(
                    "[ERROR] While executing {}\n\n{}\n\nSee logs for details"
                    .format(cmd_string, exc_log_str(root_exc)))

            # In all cases (except if return early/re-raise)
            await self.bot.send_message(ctx.message.channel, author_mention +
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
            await self.send_output('[WARNING] ' + err_msg)
            await self.bot.send_message(ctx.message.channel,
                author_mention + "Only mods can use that command.")

        elif isinstance(exc, AdminOnlyError):
            err_msg = "Unauthorised user for this command (not an admin): {!r}".format(
                cmd_string)
            logger.warning(err_msg)
            await self.send_output('[WARNING] ' + err_msg)
            await self.bot.send_message(ctx.message.channel,
                author_mention + "Only admins can use that command.")

        elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
            logger.warning(
                "Check failed on command: {!r}\n\n{}".format(cmd_string, tb_log_str(exc)))
            await self.bot.send_message(ctx.message.channel, author_mention +
                "You're not allowed to use that command. "
                " *(Dev note: Implement error handler with more precise reason)*")

        elif isinstance(exc, UnauthorizedChannelError):
            err_msg = "Unauthorised channel for this command: {!r}".format(
                cmd_string)
            logger.warning(err_msg)
            await self.send_output('[WARNING] ' + err_msg)
            await self.bot.send_message(ctx.message.channel,
                author_mention + "You can't use that command here.")

        elif isinstance(exc, commands.NoPrivateMessage):
            msg = "Attempt to use non-PM command in PM: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                "Sorry, you can't use that command in PM.")
            # No need to log this on Discord, spammy and isn't something mods need to be aware of

        elif isinstance(exc, commands.BadArgument):
            exc_msg = exc.args[0] if len(exc.args) > 0 else '(No error message).'
            msg = "Bad argument passed in command: {}\n{}".format(cmd_string, exc_msg)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel, author_mention +
                ("Invalid argument(s): {}\n\n**Usage:** `{}`\n\n"
                 "Use `{}` for help.")
                    .format(exc_msg, usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.TooManyArguments):
            msg = "Too many arguments passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel, author_mention +
                "Too many arguments.\n\n**Usage:** `{}`\n\nUse `{}` for help."
                    .format(usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.MissingRequiredArgument):
            msg = "Missing required arguments in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel, author_mention +
                "Missing argument(s).\n\n**Usage:** `{}`\n\nUse `{}` for help."
                    .format(usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, BotNotReady):
            try:
                cog_name = exc.args[0]
            except IndexError:
                cog_name = 'unknown'
            logger.warning("Attempted to use command while cog is not ready: {}".format(cmd_string))
            await self.bot.send_message(
                ctx.message.channel, author_mention +
                "Sorry, I'm still loading the {} module! Try again in a few seconds."
                .format(cog_name)
            )

        elif isinstance(exc, commands.CommandNotFound):
            msg = "Unknown command: {}".format(cmd_string)
            # safe to assume commands usually words - symbolic commands are rare
            # and we want to avoid emoticons ('._.', etc.), punctuation ('...') and decimal numbers
            # without leading 0 (.12) being detected
            if ctx.invoked_with and all(c.isalnum() for c in ctx.invoked_with) \
                    and not ctx.invoked_with[0].isdigit():
                logger.warning(msg)
                await self.bot.send_message(ctx.message.channel, author_mention +
                    "Sorry, I don't know the command `{}{.invoked_with}`"
                        .format(get_command_prefix(ctx), ctx))

        else:
            logger.exception("Unknown exception occurred")
            await self.bot.send_message(ctx.message.channel, author_mention +
                "An unexpected error occurred! Details have been logged. Let a mod know so we can "
                "investigate.")
            await self.send_output(
                ("[ERROR] Unknown error while trying to process command {}\n"
                 "Error: {!s}\n\nSee logs for details").format(cmd_string, exc))

    @commands.command(pass_context=True)
    @mod_only()
    async def info(self, ctx):
        """
        [MOD ONLY] Provides bot info and useful links.

        Also useful for testing basic bot responsivity.

        Arguments: None.
        """
        logger.debug("info(): {!s}".format(message_log_str(ctx.message)))
        em = discord.Embed(color=0x80AAFF, title=self.name)
        em.add_field(name="Logged in as",
                     value="{!s}".format(self.bot.user.mention))
        em.add_field(name="KazTron version",
                     value="v{}".format(kaztron.bot_info["version"]), inline=True)
        em.add_field(name="discord.py version",
            value="v{}".format(discord.__version__), inline=True)

        links = kaztron.bot_info["links"].copy()
        links.update(self.config.get('core', 'info_links', {}))
        for title, url in links.items():
            em.add_field(name=title, value="[{0}]({1})".format(title, url), inline=True)
        await self.bot.say(embed=em)

    @commands.command(pass_context=True, aliases=['bug', 'issue'])
    @commands.cooldown(rate=5, per=60)
    async def request(self, ctx, *, content: str):
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

        em = discord.Embed(color=0x80AAFF)
        em.set_author(name="User Issue Submission")
        em.add_field(name="User", value=ctx.message.author.mention, inline=True)
        try:
            em.add_field(name="Channel", value=ctx.message.channel.mention, inline=True)
        except AttributeError:  # probably a private channel
            em.add_field(name="Channel", value=ctx.message.channel, inline=True)
        em.add_field(name="Timestamp", value=format_timestamp(ctx.message), inline=True)
        em.add_field(name="Content", value=content, inline=False)
        await self.bot.send_message(self.ch_request, embed=em)
        await self.bot.say("Your issue was submitted to the bot DevOps team. "
                           "If you have any questions or if there's an urgent problem, "
                           "please feel free to contact the moderators.")


def setup(bot):
    bot.add_cog(CoreCog(bot))
