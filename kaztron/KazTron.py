# coding=utf8

from collections import OrderedDict
import logging
import random
import sys

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.driver import showcaser
from kaztron.errors import UnauthorizedUserError, ModOnlyError
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import check_role, get_named_role
from kaztron.utils.logging import setup_logging, message_log_str, exc_log_str, tb_log_str
from kaztron.utils.strings import get_command_str, get_help_str

# In the loving memory of my time as a moderator of r/worldbuilding network
# To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience.
# (Assuming this is from Kazandaki -- Laogeodritt)

#
# Application data
#

__version__ = "1.2.6"

bot_info = {
    "version": __version__,
    "changelog": "- Improved logging facilities\n"
                 "- Internal refactor for maintainability and reliability\n"
                 "- Internal architectural improvements: configuration handling\n"
                 "- Refactor of command UI of several modules\n",
    "links": OrderedDict()
}
bot_info["links"]["Manual"] = "https://github.com/Kazandaki/KazTron/wiki"
bot_info["links"]["GitHub"] = "https://github.com/cxcfme/KazTron"
bot_info["links"]["Roadmap"] = "https://docs.google.com/spreadsheets/d/" \
        "1ScVRoondp50HoonVBTZz8WUmfkLnDlGaomJrG0pgGs0/edit?usp=sharing"
bot_info["links"]["Spotlight Apps"] = "https://docs.google.com/spreadsheets/d/" \
        "1YSwx6AJFfOEzIwTAeb71YXEeM0l34mUt6OvyhxTwQis/edit?usp=sharing"

cfg_defaults = {
    "discord": {
        "mod_roles": ["Admin", "Moderator", "Bot"]
    },
    "core": {
        "name": "UnnamedBot",
        "log_level": "INFO",
        "log_file": "kaztron.log"
    }
}

#
# init
#

client = commands.Bot(command_prefix='.',
                      description='This an automated bot for the /r/worldbuilding discord server',
                      pm_help=True)
Client = discord.Client()

# load configuration
try:
    config = get_kaztron_config(cfg_defaults)
except OSError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)

dest_output = discord.Object(id=config.get('discord', 'channel_output'))
dest_showcase = discord.Object(id=config.get('showcase', 'channel'))
lucky = None  # Ugh, fix this.


# setup logging
setup_logging(logging.getLogger(), config)  # setup the root logger
logger = logging.getLogger('kaztron')
clogger = logging.getLogger('kaztron.cmd')


#
# Main
#

@client.event
async def on_ready():
    logger.debug("on_ready")

    playing = config.get('discord', 'playing', default="")
    if playing:
        await client.change_presence(game=discord.Game(name=playing))

    startup_info = (
        "Logged in as {} (id:{})".format(client.user.name, client.user.id),
        "KazTron version {}".format(__version__),
        "Discord API version {}".format(discord.__version__)
    )

    for msg in startup_info:
        logger.info(msg)  # for file logging
        print(msg)  # because current console logger always logs at WARN level


@client.event
async def on_error(event, *args, **kwargs):
    exc_info = sys.exc_info()
    if exc_info[0] is KeyboardInterrupt:
        logger.warning("Interrupted by user (SIGINT)")
        raise exc_info[1]

    log_msg = "Error occurred in {}({}, {})".format(
        event,
        ', '.join(repr(arg) for arg in args),
        ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
    logger.exception(log_msg)
    await client.send_message(dest_output,
        "[ERROR] {} - see logs for details".format(exc_log_str(exc_info[1])))

    try:
        message = args[0]
        await client.send_message(message.channel,
            "An error occurred! Details have been logged. Please let the mods know so we can investigate.")
    except IndexError:
        pass
    except AttributeError:
        logger.warning("Couldn't extract channel context from previous error - is args[0] not a message?")


@client.event
async def on_command_error(exc, ctx, force=False):
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
        await client.send_message(ctx.message.channel,
            "`{}` is on cooldown! Try again in {:.0f} seconds."
            .format(get_command_str(ctx), max(exc.retry_after, 1.0)))

    elif isinstance(exc, commands.CommandInvokeError):
        root_exc = exc.__cause__ if exc.__cause__ is not None else exc
        if isinstance(root_exc, KeyboardInterrupt):
            logger.warning("Interrupted by user (SIGINT)")
            raise root_exc
        elif isinstance(root_exc, discord.HTTPException):  # API errors
            err_msg = 'While executing {c}\n\nDiscord API error {e!s}'\
                .format(c=cmd_string, e=root_exc)
            clogger.error(err_msg + "\n\n{}".format(tb_log_str(root_exc)))
            await client.send_message(dest_output,
                "[ERROR] " + err_msg + "\n\nSee log for details")
        else:
            clogger.error("An error occurred while processing the command: {}\n\n{}"
                          .format(cmd_string, tb_log_str(root_exc)))
            await client.send_message(dest_output,
                "[ERROR] While executing {}\n\n{}\n\nSee logs for details"
                                      .format(cmd_string, exc_log_str(root_exc)))

        # In all cases (except if return early/re-raise)
        await client.send_message(ctx.message.channel,
            "An error occurred! Details have been logged. Let a mod know so we can investigate.")

    elif isinstance(exc, commands.DisabledCommand):
        msg = "Attempt to use disabled command: {}".format(cmd_string)
        clogger.warning(msg)
        # No need to log this on Discord - not something mods need to be aware of
        # No need to inform user of this - prevents spam, "disabled" commands could just not exist

    elif isinstance(exc, ModOnlyError):
        err_msg = "Unauthorised user for this command (not a moderator): {!r}".format(cmd_string)
        clogger.warning(err_msg)
        await client.send_message(dest_output, '[WARNING] ' + err_msg)
        await client.send_message(ctx.message.channel,
            "Only mods can use that command.")

    elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
        clogger.warning("Check failed on command: {!r}\n\n{}".format(cmd_string, tb_log_str(exc)))
        await client.send_message(ctx.message.channel,
            "You're not allowed to use that command. "
            " (Dev note: Implement error handler + specify more precise reason)")

    elif isinstance(exc, commands.NoPrivateMessage):
        msg = "Attempt to use non-PM command in PM: {}".format(cmd_string)
        clogger.warning(msg)
        await client.send_message(ctx.message.channel, "Sorry, you can't use that command in PM.")
        # No need to log this on Discord, spammy and isn't something mods need to be aware of

    elif isinstance(exc, commands.BadArgument):
        msg = "Bad argument passed in command: {}".format(cmd_string)
        clogger.warning(msg)
        await client.send_message(ctx.message.channel,
            ("Invalid argument(s) for the command `{}`. "
            "Check that the arguments after the command name are correct."
            "Use `{}` for instructions. "
            "(Dev note: Implement error handler + specify more precise check)")
                .format(get_command_str(ctx), get_help_str(ctx)))
        # No need to log user errors to mods

    elif isinstance(exc, commands.TooManyArguments):
        msg = "Too many arguments passed in command: {}".format(cmd_string)
        clogger.warning(msg)
        await client.send_message(ctx.message.channel,
            ("Too many arguments for the command `{}`. "
            "Check that the arguments after the command name are correct. "
             "Use `{}` for instructions.")
                .format(get_command_str(ctx), get_help_str(ctx)))
        # No need to log user errors to mods

    elif isinstance(exc, commands.MissingRequiredArgument):
        msg = "Missing required arguments in command: {}".format(cmd_string)
        clogger.warning(msg)
        await client.send_message(ctx.message.channel,
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
            clogger.warning(msg)
            await client.send_message(ctx.message.author,
                "Sorry, I don't know the command `{}`".format(get_help_str(ctx)))

    else:
        clogger.exception("Unknown exception occurred")
        await client.send_message(ctx.message.channel,
            "An error occurred! Details have been logged. Let a mod know so we can investigate.")
        await client.send_message(dest_output,
                                  ("[ERROR] Unknown error while trying to process command {}\n"
                                   "Error: {!s}\n\nSee logs for details").format(cmd_string, exc))


# TODO: extract this into its own module, fix the poorly designed 'lucky' global/non-persisted state
@client.command(pass_context=True, description="World spotlight control.")
async def spotlight(ctx):
    """
    Public subcommands:

    * `join` Join or leave the world spotlight audience. If you join, you will be pinged for
      spotlight-related news (e.g. start of a spotlight). Example usage: `.spotlight join`
    
    Mod-only subcommands:

    * `choose [index]` Choose row #<index> as current spotlight from the spreadsheet.
    * `roll` Roll a random spotlight application from the spreadsheet.
    * `current` Display the currently selected spotlight.
    * `showcase` Show the currently selected spotlight in the Showcase channel (publicly).
    """
    global lucky
    clogger.debug("spotlight(): " + message_log_str(ctx.message)[:64])

    commandraw = str(ctx.message.content)
    command = commandraw[11:]

    # TODO: convert to subcommands. See here: https://github.com/Rapptz/discord.py/blob/d50acf79f8003052090f79770ad251daa3a7ff70/docs/faq.rst#how-do-i-make-a-subcommand
    # TODO: properly tokenize the arguments... I think discord.py is supposed to already tokenize though? Look into this, look into Context.args
    if command == "join":
        clogger.debug("spotlight(): audience role request from {!s}".format(ctx.message.author))
        audience_role = get_named_role(ctx.server, config.get("showcase", "audience_role"))
        if audience_role in ctx.message.author.roles:
            await client.remove_roles(ctx.message.author, audience_role)
            await client.delete_message(ctx.message)
            await client.send_message(ctx.message.author,
                "You are no longer part of the world spotlight audience. You will not be pinged "
                "for spotlight-related news. You can use the same command to join the audience "
                "again.")
            clogger.info("spotlight(): removed audience role from {!s}".format(ctx.message.author))
        else:
            await client.add_roles(ctx.message.author, audience_role)
            await client.delete_message(ctx.message)
            await client.send_message(ctx.message.author,
                "You are now a part of the world spotlight audience. You can be mass pinged by the "
                "moderators or the host for spotlight-related news (like the start of a "
                "spotlight). You can use the same command to leave the audience.")
            clogger.info("spotlight(): gave audience role to {!s}".format(ctx.message.author))

    elif check_role(config.get("discord", "mod_roles", []), ctx.message):
        if command[:6] == "choose":
            clogger.debug("spotlight(): choose")
            row_index = int(command[7:])-2
            try:
                lucky = showcaser.choose(row_index)
            except IndexError:
                err_msg = "Index out of range: {:d}".format(row_index + 2)
                clogger.error("spotlight(): choose: " + err_msg)
                await client.say(err_msg)
                return
            await send_spotlight_info(ctx.message.channel, lucky)

        elif command == "roll":
            clogger.debug("spotlight(): roll")
            lucky = showcaser.roll()
            await send_spotlight_info(ctx.message.channel, lucky)

        elif command == "current":
            clogger.debug("spotlight(): current")
            if lucky:
                await send_spotlight_info(ctx.message.channel, lucky)
            else:
                clogger.warning("spotlight(): current: No spotlight currently selected.")
                await client.say("No spotlight currently selected.")

        elif command == "showcase":
            clogger.debug("spotlight(): showcase")
            if lucky:
                await client.send_message(dest_showcase, "**Next spotlight host!**")
                await send_spotlight_info(dest_showcase, lucky)
            else:
                clogger.warning("spotlight(): showcase: No spotlight currently selected.")
                await client.say("No spotlight currently selected.")
        else:
            err_msg = "{!r} is not a valid spotlight sub-command.".format(command)
            clogger.warning("spotlight(): " + err_msg)
            await client.say("{!r} is not a valid spotlight sub-command.".format(command))
    else:
        err_msg = "Non-mod tried to use mod-only spotlight command: {}".format(message_log_str(ctx.message))
        clogger.warning(err_msg)
        await client.send_message(ctx.message.channel, "You're not allowed to use that command.")
        await client.send_message(dest_output, "[WARNING] " + err_msg)


@spotlight.error
async def spotlight_on_error(exc, ctx):
    cmd_string = message_log_str(ctx.message)
    if isinstance(exc, commands.CommandInvokeError):
        root_exc = exc.__cause__ if exc.__cause__ is not None else exc

        # noinspection PyUnresolvedReferences
        if isinstance(root_exc, showcaser.Error):  # any Google API errors
            clogger.exception("Google API error while processing command: {}\n\n{}"
                              .format(cmd_string, tb_log_str(root_exc)))
            await client.send_message(ctx.message.channel,
                "An error occurred while communicating with the Google API. "
                "See bot output for details.")
            await client.send_message(dest_output,
                                      ("[ERROR] An error occurred while communicating with the Google API.\n"
                "Original command: {}\n{}\n\nSee logs for details")
                                      .format(cmd_string, exc_log_str(root_exc)))

        elif isinstance(root_exc,
                (showcaser.UnknownClientSecretsFlowError, showcaser.InvalidClientSecretsError)
                ):  # Auth credentials file errors
            clogger.error("Problem with Google API credentials file: {}\n\n{}"
                          .format(cmd_string, tb_log_str(root_exc)))
            await client.send_message(ctx.message.channel,
                "Problem with the stored Google API credentials. "
                "See bot output for details.")
            await client.send_message(dest_output,
                                      ("[ERROR] Problem with Google API credentials file.\n"
                 "Original command: {}\n{}\n\nSee logs for details")
                                      .format(cmd_string, exc_log_str(root_exc)))

        elif isinstance(root_exc, discord.HTTPException):
            cmd_string = str(ctx.message.content)[11:]
            clogger.error("Error sending spotlight info ({}): {}".format(cmd_string, root_exc.text))
            await client.send_message(ctx.message.channel,
                "Error sending spotlight info: {}".format(root_exc.text))
            await client.send_message(dest_output,
                ("[ERROR] Error sending spotlight info.\n"
                 "Original command: {}\nDiscord API error: {}\n\n"
                 "See logs for details").format(cmd_string, root_exc.text))

        else:
            await on_command_error(exc, ctx, force=True)  # Other errors can bubble up
    else:
        on_command_error(exc, ctx, force=True)


async def send_spotlight_info(destination: discord.Object, spotlight_data: [str]) -> None:
    """
    Returns a discord.Embed object containing human-readable formatted
    spotlight_data. This object can then be sent to any normal text channel
    over Discord.

    :param destination: The destination as a Discord object (often a :cls:`discord.Channel`)
    :param spotlight_data: the array of spotlight data to send
    :return: None, or a :cls:`discord.HTTPException` class if sending fails (this is already
        logged and communicated over Discord, provided for informational purposes/further handling)
    """
    user = discord.User(id=spotlight_data[2])
    clogger.info("Displaying spotlight data for: {!s} - {!s}"
        .format(user, spotlight_data[4]))

    usercolor = 0x80AAFF
    em = discord.Embed(color=usercolor)
    em.add_field(name="Author", value=user.mention, inline=False)
    em.add_field(name="Project Name", value=spotlight_data[4], inline=False)
    em.add_field(name="Project Description", value=spotlight_data[11], inline=False)

    if spotlight_data[8] != "n/a":
        em.add_field(
            name="Are there any mature or controversial issues that you explore or discuss in your world?",
            value=spotlight_data[8], inline=False)

    em.add_field(name="Keywords", value=spotlight_data[5], inline=False)

    if spotlight_data[14] and spotlight_data[14].lower() != "n/a":
        em.add_field(name="Project Art", value="[Click Here](%s)" % spotlight_data[14], inline=True)

    if spotlight_data[15] and spotlight_data[15].lower() != "n/a":
        em.add_field(name="Additional Content", value="[Click Here](%s)" % spotlight_data[15], inline=True)

    await client.send_message(destination, embed=em)
