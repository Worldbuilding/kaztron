import asyncio
import logging

import sys
from typing import List, Dict

import discord

import kaztron
from kaztron.config import SectionView
from kaztron.errors import *
from kaztron.help_formatter import DiscordHelpFormatter, JekyllHelpFormatter
from kaztron.rolemanager import RoleManager
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.decorators import task_handled_errors
from kaztron.utils.logging import message_log_str, exc_log_str, tb_log_str, exc_msg_str
from kaztron.utils.discord import get_command_prefix, get_command_str, get_help_str, get_usage_str
from kaztron.utils.datetime import format_timestamp

logger = logging.getLogger(__name__)


class CoreConfig(SectionView):
    name: str
    extensions: List[str]
    channel_request: discord.Channel
    info_links: Dict[str, str]
    date_format: str
    datetime_format: str
    datetime_seconds_format: str
    daemon: bool
    daemon_pidfile: str
    daemon_user: str
    daemon_group: str
    daemon_log: str


class CoreCog(kaztron.KazCog):
    """!kazhelp

    brief: Essential internal {{name}} functionality, plus bot information and control commands.
    description: |
        Essential {{name}} functionality: core setup and configuration tasks, general-purpose error
        handling for other cogs and commands, etc. It also includes commands for general bot
        information and control. The Core cog cannot be disabled.
    contents:
        - info
        - request
        - jekyllate
    """

    def __init__(self, bot):
        super().__init__(bot, 'core')
        self.cog_config = self.cog_config  # type: CoreConfig
        self.cog_config.set_converters('channel_request', self.validate_channel, lambda c: c.id)
        self.name = self.cog_config.name

        self.bot.event(self.on_error)  # register this as a global event handler, not just local
        self.bot.add_check(self.check_bot_ready)
        self.ready_cogs = set()
        self.error_cogs = set()

    def check_bot_ready(self, ctx: commands.Context):
        """ Check if bot is ready. Used as a global check. """
        if ctx.cog is not None:
            if ctx.cog in self.ready_cogs:
                return True
            elif ctx.cog in self.error_cogs:
                raise BotCogError(type(ctx.cog).__name__)
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
        registered_cogs = {c for c in self.bot.cogs.values() if isinstance(c, kaztron.KazCog)}
        if self.ready_cogs == registered_cogs:
            logger.info("=== ALL COGS READY ===")
            self.bot.loop.create_task(self.prepare_command_help())

    def set_cog_error(self, cog):
        """
        Called by the kaztron.KazCog base to signal that an error occurred during on_ready.
        """
        logger.error("Cog error: {}".format(type(cog).__name__))
        self.error_cogs.add(cog)

    def set_cog_shutdown(self, cog):
        logger.info("Cog has been shutdown: {}".format(type(cog).__name__))
        self.ready_cogs.remove(cog)
        if cog.state != self.state:  # not using global state (saving handled in runner)
            cog.state.write()

    async def on_ready(self):
        logger.debug("on_ready")
        await super().on_ready()

        # set global variables (don't use export_kazhelp_vars - these are cog-local)
        try:
            self.bot.kaz_help_parser.variables['output_channel'] = '#' + self.channel_out.name
            self.bot.kaz_help_parser.variables['test_channel'] = '#' + self.channel_test.name
            self.bot.kaz_help_parser.variables['public_channel'] = '#' + self.channel_public.name
        except AttributeError:
            logger.warning("Help parser not found in bot")

        await self.set_status_message()
        await self.send_startup_message()

    async def set_status_message(self):
        playing = self.config.discord.playing
        if playing:
            await self.bot.change_presence(game=discord.Game(name=playing))

    async def send_startup_message(self):
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

    @task_handled_errors
    async def prepare_command_help(self):
        obj_list = set()
        formatter = self.bot.formatter  # type: DiscordHelpFormatter

        for cog_name, cog in self.bot.cogs.items():
            if cog not in obj_list:
                try:
                    formatter.kaz_preprocess(cog, self.bot)
                    obj_list.add(cog)
                except Exception as e:
                    raise discord.ClientException(
                        "Error while parsing !kazhelp for cog {}".format(cog_name))\
                        from e

        for command in self.bot.walk_commands():
            if command not in obj_list:
                try:
                    formatter.kaz_preprocess(command, self.bot)
                    obj_list.add(command)
                except Exception as e:
                    raise discord.ClientException("Error while parsing !kazhelp for command {}"
                        .format(command.qualified_name)) from e

        logger.info("=== KAZHELP PROCESSED ===")

    async def on_command_completion(self, command: commands.Command, ctx: commands.Context):
        """ On command completion, save state files. """
        for cog in self.bot.cogs.values():
            if isinstance(cog, kaztron.KazCog):
                # ok if same state object in multiple cogs - dirty flag prevents multiple writes
                cog.state.write()

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

    bad_argument_map = {
        'Converting to "int" failed.': 'Argument(s) must be a whole number (0, 1, 2, -1, etc.).',
        'Converting to "float" failed.': 'Argument(s) must be a whole or decimal number '
                                         '(0, 1, 2, 3.14, -2.71, etc.)'
    }

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
                await self.bot.delete_message(ctx.message)
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
            elif isinstance(root_exc, discord.Forbidden) \
                    and root_exc.code == DiscordErrorCodes.CANNOT_PM_USER:
                author: discord.Member = ctx.message.author
                err_msg = "Can't PM user (FORBIDDEN): {0} {1}".format(
                    author.nick or author.name, author.id)
                logger.warning(err_msg)
                logger.debug(tb_log_str(root_exc))
                await self.bot.send_message(ctx.message.channel,
                    ("{} You seem to have PMs from this server disabled or you've blocked me. "
                     "I need to be able to PM you for this command.").format(author.mention))
                await self.send_output("[WARNING] " + err_msg, auto_split=False)
                return  # we don't want the generic "an error occurred!"
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

        elif isinstance(exc, (ModOnlyError, AdminOnlyError)):
            err_msg = "Unauthorised user for this command ({}): {!r}".format(
                type(exc).__name__, cmd_string
            )
            logger.warning(err_msg)
            await self.send_output('[WARNING] ' + err_msg)

            err_str = exc_msg_str(exc,
                "Only moderators may use that command." if isinstance(exc, ModOnlyError)
                else "Only administrators may use that command.")
            await self.bot.send_message(ctx.message.channel, author_mention + err_str)

        elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
            logger.warning(
                "Check failed on command: {!r}\n\n{}".format(cmd_string, tb_log_str(exc)))
            await self.send_output('[WARNING] ' +
                "Check failed on command: {!r}\n\n{}".format(cmd_string, exc_log_str(exc)))
            err_str = exc_msg_str(exc,
                "*(Dev note: Implement error handler with more precise reason)*")
            await self.bot.send_message(ctx.message.channel, author_mention +
                "You're not allowed to use that command: " + err_str)

        elif isinstance(exc, UnauthorizedChannelError):
            err_msg = "Unauthorised channel for this command: {!r}".format(cmd_string)
            logger.warning(err_msg)
            await self.send_output('[WARNING] ' + err_msg)
            err_str = exc_msg_str(exc, "Command not allowed in this channel.")
            await self.bot.send_message(ctx.message.channel,
                author_mention + "You can't use that command here: " + err_str)

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

            # do some user-friendliness message remapping
            exc_msg = self.bad_argument_map[exc_msg]\
                            if exc_msg in self.bad_argument_map else exc_msg

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

        elif isinstance(exc, BotCogError):
            try:
                cog_name = exc.args[0]
            except IndexError:
                cog_name = 'unknown'
            logger.warning("Attempted to use command on cog in error state: {}".format(cmd_string))
            await self.bot.send_message(
                ctx.message.channel, author_mention +
                "Sorry, an error occurred loading the {} module! Please let a mod/admin know."
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

        elif isinstance(exc, commands.UserInputError):
            logger.warning("UserInputError: {}\n{}"
                .format(cmd_string, tb_log_str(exc)))
            await self.bot.send_message(ctx.message.channel,
                '{} {}'.format(author_mention, exc.args[0]))

        else:
            logger.error("Unknown command exception occurred: {}\n\n{}"
                .format(cmd_string, tb_log_str(exc)))
            await self.bot.send_message(ctx.message.channel, author_mention +
                "An unexpected error occurred! Details have been logged. Let a mod know so we can "
                "investigate.")
            await self.send_output(
                ("[ERROR] Unknown error while trying to process command {}\n"
                 "Error: {!s}\n\nSee logs for details").format(cmd_string, exc))

    @commands.command(pass_context=True)
    @mod_only()
    async def info(self, ctx):
        """!kazhelp

        description: |
            Provides bot info and useful links.

            This command provides the version of the {{name}} instance currently running, the latest
            changelog summary, and links to documentation, the GitHub repository, and other
            resources for operators and moderators.

            TIP: *For mods.* If {{name}} ever seems unresponsive, try this command first.
        """
        em = discord.Embed(color=0x80AAFF, title=self.name)
        em.add_field(name="KazTron version",
                     value="v{}".format(kaztron.bot_info["version"]), inline=True)
        em.add_field(name="discord.py version",
            value="v{}".format(discord.__version__), inline=True)
        em.add_field(name="Loaded Cogs", value='\n'.join(self.bot.cogs.keys()))

        links = kaztron.bot_info["links"].copy()
        links.update(self.cog_config.info_links)
        for title, url in links.items():
            em.add_field(name=title, value="[{0}]({1})".format(title, url), inline=True)
        await self.bot.say(embed=em)

    @commands.command(pass_context=True, aliases=['bug', 'issue'])
    @commands.cooldown(rate=3, per=120)
    async def request(self, ctx, *, content: str):
        """!kazhelp

        description: Submit a bug report or feature request to the {{name}} bot team.
        details: |
            Everyone can use this command, but please make sure that:

            * Your issue is clear and sufficiently detailed.
            * You submit **one issue per command**. Do not include multiple issues in one command,
              or split up one issue into multiple commands. Otherwise the bot team will get mad at
              you =P

            If you're reporting a bug, include the answers to the questions:

            * What were you trying to do? Include the *exact* command you tried to use, if any.
            * What error messages were given by the bot? *Exact* message.
            * Where and when did this happen? Ideally, link the message itself (message menu >
              Copy Link).

            IMPORTANT: Any submissions made via this system may be tracked publicly. By submitting
            a request via this system, you give us permission to post your username and message,
            verbatim or altered, to a public database for the purpose of project management.

            IMPORTANT: Abuse of this command may be treated as channel spam, and enforced
            accordingly.

            NOTE: The three command names do not differ from each other. They are defined purely
            for convenience.
        examples:
            - command: |
                .request When trying to use the `.roll 3d20` command, I get the message:
                "An error occurred! Details have been logged. Let a mod know so we can investigate."

                This only happens with d20, I've tried d12 and d6 with no problems.
                The last time this happened in #tabletop on 2018-01-31 at 5:24PM PST.
        """
        em = discord.Embed(color=0x80AAFF)
        em.set_author(name="User Issue Submission")
        em.add_field(name="User", value=ctx.message.author.mention, inline=True)
        try:
            em.add_field(name="Channel", value=ctx.message.channel.mention, inline=True)
        except AttributeError:  # probably a private channel
            em.add_field(name="Channel", value=ctx.message.channel, inline=True)
        em.add_field(name="Timestamp", value=format_timestamp(ctx.message), inline=True)
        em.add_field(name="Content", value=content, inline=False)
        await self.bot.send_message(self.cog_config.channel_request, embed=em)
        await self.bot.say("Your issue was submitted to the bot DevOps team. "
                           "If you have any questions or if there's an urgent problem, "
                           "please feel free to contact the moderators.")

    @commands.command(pass_context=True)
    @mod_only()
    @mod_channels()
    async def jekyllate(self, ctx: commands.Context):
        """!kazhelp

        description: Generate Jekyll-compatible markdown documentation for all loaded cogs.
        """
        import os
        import io
        import zipfile

        jekyll = JekyllHelpFormatter(self.bot.kaz_help_parser, self.bot)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
            for cog_name, cog in self.bot.cogs.items():
                logger.info("jekyllate: Generating docs for {}".format(cog_name))
                with z.open(cog_name.lower() + '.md', mode='w') as f:
                    docs = jekyll.format(cog, ctx)
                    docs_b = docs.encode('utf8')
                    f.write(docs_b)

        logger.info("jekyllate: Sending file...")
        buf.seek(0)
        await self.bot.send_file(ctx.message.channel, buf,
                                 filename=self.config.core.name + "-jekyll.zip")


def setup(bot):
    bot.add_cog(CoreCog(bot))
    bot.add_cog(RoleManager(bot))
