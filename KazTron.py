#!/usr/bin/env python
# coding=utf8

import sys
import os.path
import asyncio
import random
import logging
import traceback
import time

import discord
from discord.ext import commands

import config
import wordfilter
import showcaser

# In the loving memory of my time as a moderator of r/worldbuilding network
# To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience.
# (Assuming this is from Kazandaki -- Laogeodritt)

#
# Application data
#

__version__ = "1.2.5"

changelog = "- Improved logging facilities, internal refactors for reliability and code cleanliness.\n"
url_manual = "https://github.com/Kazandaki/KazTron/wiki"
url_github = "https://github.com/Kazandaki/KazTron"
url_roadmap = "https://docs.google.com/spreadsheets/d/1ScVRoondp50HoonVBTZz8WUmfkLnDlGaomJrG0pgGs0/edit?usp=sharing"
url_spotlight= "https://docs.google.com/spreadsheets/d/1YSwx6AJFfOEzIwTAeb71YXEeM0l34mUt6OvyhxTwQis/edit?usp=sharing"

#
# init
#

def setup_logging(logger, config):
    logger.setLevel(config.loglevel)

    # File handler
    fh = logging.FileHandler(config.logfile)
    fh_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s [in %(pathname)s:%(lineno)d]')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    # Console handler - fixed log level
    ch = logging.StreamHandler()
    ch_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s')
    ch.setLevel(max(config.loglevel, logging.INFO)) # never below INFO - avoid cluttering console
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

client = commands.Bot(command_prefix='.',
                      description='This an automated bot for r/worldbuilding discord server',
                      pm_help=True)
Client = discord.Client()

# load configuration
try:
    config.data_import()
except OSError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)

warnCHID = config.warnchannel
showcaseChannel = discord.Object(id=config.showcase)
outputChannel = discord.Object(id=config.outputchannel)

# setup logging
setup_logging(logging.getLogger(), config) # setup the root logger
logger = logging.getLogger('kaztron')
clogger = logging.getLogger('kaztron.cmd')

# load filter dictionary data
try:
    config.dict_import()
except OSError as e:
    logger.error(str(e))
    sys.exit(1)


#
# Errors
#

class UnauthorizedUserError(commands.CommandError):
    pass

class ModOnlyError(UnauthorizedUserError):
    pass


#
# General utility methods
#

def check_role(rolelist, message):
    """
    Check if the author of a ``message`` has one of the roles in ``rolelist``.

    :param rolelist: A list of role names.
    :param message: A :cls:``discord.Message`` object representing the message
        to check.
    """
    for role in rolelist:
        try:
            if discord.utils.get(message.server.roles, name=role) in message.author.roles:
                return True
        except:
            pass
    else:
        return False


def mod_only():
    """
    From a given context, check if a command was sent by a mod/admin.
    """
    def predicate(ctx):
        if check_role(config.modteam, ctx.message):
            return True
        else:
            raise ModOnlyError("Only moderators may use this command.")
    return commands.check(predicate)


def message_log_str(message : discord.Message) -> str:
    """
    Convert a :cls:`discord.Message` object to a string suitable for logging or tracing the message.
    Format looks like:

    [2012-01-01 12:34:56] <#channel:username#1234> "Message here"
    """
    return "[{}] <#{!s}:{!s}> {!r}".format(message.timestamp.isoformat(sep=' '), message.channel, message.author, message.content)


def exc_log_str(exception) -> str:
    """
    Format an exception as a "nice" one-liner string (does not include stack trace).
    """
    return "{}: {!s}".format(type(exception).__name__, exception)

def tb_log_str(exception) -> str:
    """
    Format an exception as a full traceback.
    """
    return "\n".join(traceback.format_exception(None, exception, exception.__traceback__))


#
# Main
#

@client.event
async def on_ready():
    logger.debug("on_ready")

    startup_info = (
        "Logged in as {} (id:{})".format(client.user.name, client.user.id),
        "KazTron version {}".format(__version__),
        "Discord API version {}".format(discord.__version__)
    )

    for msg in startup_info:
        logger.info(msg) # for file logging
        print(msg) # because current console logger always logs at WARN level

    # TODO: validate configs against server? e.g. channels


@client.event
async def on_error(event, *args, **kwargs):
    exc_info = sys.exc_info()
    if exc_info[0] is KeyboardInterrupt:
        logger.warn("Interrupted by user (SIGINT)")
        raise

    log_msg = "Error occurred in {}({}, {})".format(
        event,
        ', '.join(repr(arg) for arg in args),
        ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
    logger.exception(log_msg)
    await client.send_message(outputChannel,
        "[ERROR] {} - see logs for details".format(exc_log_str(exc_info[1])))

    try:
        message = args[0]
        await client.send_message(message.channel, "An error occurred! Details have been logged. Please let the mods know so we can investigate.")
    except IndexError:
        pass
    except AttributeError:
        logger.warn("Couldn't extract channel context from previous error - is args[0] not a message?")


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
            "{} is on cooldown! Try again in {:.2f} seconds."
            .format(ctx.command.name, exc.retry_after))

    elif isinstance(exc, commands.CommandInvokeError):
        if isinstance(exc.__cause__, KeyboardInterrupt):
            logger.warn("Interrupted by user (SIGINT)")
            raise

        root_exc = exc.__cause__ if exc.__cause__ is not None else exc
        clogger.error("An error occurred while processing the command: {}\n\n{}"
            .format(cmd_string, tb_log_str(root_exc)))
        await client.send_message(outputChannel,
            "[ERROR] While executing {}\n\n{}\n\nSee logs for details"
            .format(cmd_string, exc_log_str(root_exc)))
        await client.send_message(ctx.message.channel,
            "An error occurred! Details have been logged. Let a mod know so we can investigate.")

    elif isinstance(exc, commands.DisabledCommand):
        msg = "Attempt to use disabled command: {}".format(cmd_string)
        clogger.warn(msg)
        # No need to log this on Discord - not something mods need to be aware of
        # No need to inform user of this - prevents spam, "disabled" commands could just not exist

    elif isinstance(exc, ModOnlyError):
        err_msg = "Unauthorised user for this command (not a moderator): {!r}".format(cmd_string)
        clogger.warn(err_msg)
        await client.send_message(outputChannel, '[WARNING] ' + err_msg)
        await client.send_message(ctx.message.channel,
            "Only mods can use that command.")

    elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
        clogger.warn("Check failed on command: {!r}\n\n{}".format(cmd_string, tb_log_str(exc)))
        await client.send_message(ctx.message.channel,
            "You're not allowed to use that command. "
            " (Dev note: Implement error handler + specify more precise reason)")

    elif isinstance(exc, commands.NoPrivateMessage):
        msg = "Attempt to use non-PM command in PM: {}".format(cmd_string)
        clogger.warn(msg)
        await client.send_message(ctx.message.channel, "Sorry, you can't use that command in PMs.")
        # No need to log this on Discord, spammy and isn't something mods need to be aware of

    elif isinstance(exc, commands.BadArgument):
        msg = "Bad argument passed in command: {}".format(cmd_string)
        clogger.warn(msg)
        await client.send_message(ctx.message.channel,
            "Bad argument for the command '{}'. ".format(ctx.invoked_with) +
            "Check that the arguments after the command name are correct."
            " (Dev note: Implement error handler + specify more precise check)")
        # No need to log user errors to mods

    elif isinstance(exc, commands.TooManyArguments):
        msg = "Too many arguments passed in command: {}".format(cmd_string)
        clogger.warn(msg)
        await client.send_message(ctx.message.channel,
            "Too many arguments for the command '{}'. ".format(ctx.invoked_with) +
            "Check that the arguments after the command name are correct.")
        # No need to log user errors to mods

    elif isinstance(exc, commands.MissingRequiredArgument):
        msg = "Missing required arguments in command: {}".format(cmd_string)
        clogger.warn(msg)
        await client.send_message(ctx.message.channel,
            "Missing arguments for the command '{}'. ".format(ctx.invoked_with) +
            "Check that you've passed all the needed arguments after the command name."
            " (Dev note: Implement error handler + specify more precise check)")
        # No need to log user errors to mods

    elif isinstance(exc, commands.CommandNotFound):
        msg = "Unknown command: {}".format(cmd_string)
        # avoid some natural language things that start with period (ellipsis, etc.)
        if ctx.invoked_with not in ['.', '..'] and not ctx.invoked_with.startswith('.'):
            clogger.warn(msg)
            await client.send_message(ctx.message.author, "Sorry, I don't know the command '{}'".format(ctx.invoked_with))

    else:
        clogger.exception("Unknown exception occurred")
        await client.send_message(ctx.message.channel,
            "An error occurred! Details have been logged. Let a mod know so we can investigate.")
        await client.send_message(outputChannel,
            "[ERROR] Unknown error while trying to process command {}\nError: {!s}\n\nSee logs for details".format(cmd_string, exc))


@client.command(pass_context=True,
    description="Sends a request for the bot (e.g. features, bug reports) "
                "to the bot maintainers. Avoid spam or repeated messages.")
async def request(ctx):
    clogger.debug("request(): {}".format(message_log_str(ctx.message)))
    author = ctx.message.author
    bot_author = discord.User(id=config.authorID)
    message = "Feature request from {!s}: {!s}".format(
        ctx.message.author,
        str(ctx.message.content).split(' ', 1)[1])
    await client.send_message(bot_author, message)
    await client.say("I forwarded your request.")


@client.command(pass_context=True, description="[MOD ONLY] Changes bot output channel.")
@mod_only()
async def switch(ctx):
    """
    Switch the bot's message filter warning channel between warnchannel
    and the general outputchannel (from config).
    """
    clogger.debug("switch()")
    global warnCHID
    if warnCHID == config.warnchannel:
        new_channel_id = config.outputchannel
    else:
        new_channel_id = config.warnchannel

    new_channel = client.get_channel(new_channel_id)
    if new_channel is not None:
        warnCHID = new_channel_id
        clogger.info("switch(): Changed filter warning channel to #{}".format(new_channel.name))
        await client.say("Changed the filter warning channel to {}".format(new_channel.mention))
    else:
        msg = 'Cannot change filter warning channel. Target channel {:d} does not exist.".format(new_channel_id)'
        clogger.error("switch(): " + msg)
        await client.say("Error: " + msg)

@client.event
async def on_message(message):
    """
    Message handler. Check all non-mod messages for filtered words.
    """
    if not check_role(config.modteam, message): # don't check mod messages
        # way too verbose
        # clogger.debug("on_message(): checking for filtered words")

        message_string = str(message.content)

        if wordfilter.filter_func(config.filterdelete,message_string) == True:
            clogger.info("Found filter match (auto-delete) in {}".format(message_log_str(message)))
            clogger.debug("Deleting message")
            await client.delete_message(message)

            clogger.debug("Preparing and sending warning")
            usercolor = 0xff8080
            em = discord.Embed(color=usercolor)
            em.set_author(name="Auto-Delete Filter Trigger")
            em.add_field(name="User", value=message.author.mention, inline=True)
            em.add_field(name="Channel", value=message.channel.mention, inline=True)
            em.add_field(name="Timestamp", value=message.timestamp, inline=True)
            # TODO: show rule matched
            em.add_field(name="Content", value=message_string, inline=True)

            await client.send_message(discord.Object(id=warnCHID), embed=em)

        elif wordfilter.filter_func(config.filterwarn,message_string) == True:

            clogger.info("Found filter match (auto-warn) in {}".format(message_log_str(message)))
            clogger.debug("Preparing and sending warning")

            usercolor = 0xffbf80
            em = discord.Embed(color=usercolor)
            em.set_author(name="Auto-Warn Filter Trigger")
            em.add_field(name="User", value=message.author.mention, inline=True)
            em.add_field(name="Channel", value=message.channel.mention, inline=True)
            em.add_field(name="Timestamp", value=message.timestamp, inline=True)
            # TODO: show rule matched
            em.add_field(name="Content", value=message_string, inline=True)

            await client.send_message(discord.Object(id=warnCHID), embed=em)

    await client.process_commands(message)


# TODO: extract this into its own module, fix the poorly designed 'lucky' global/non-persisted state
@client.command(pass_context = True, description = "World spotlight control.")
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
        server = ctx.message.server
        if discord.utils.get(ctx.message.server.roles, name='Spotlight Audience') in ctx.message.author.roles:
            await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Spotlight Audience'))
            await client.delete_message(ctx.message)
            await client.send_message(ctx.message.author,
                "You are no longer part of the world spotlight audience. You will not be pinged "
                "for spotlight-related news. You can use the same command to join the audience "
                "again.")
            clogger.info("spotlight(): removed audience role from {!s}".format(ctx.message.author))
        else:
            await client.add_roles(ctx.message.author, discord.utils.get(server.roles, name='Spotlight Audience'))
            await client.delete_message(ctx.message)
            await client.send_message(ctx.message.author,
                "You are now a part of the world spotlight audience. You can be mass pinged by the "
                "moderators or the host for spotlight-related news (like the start of a "
                "spotlight). You can use the same command to leave the audience.")
            clogger.info("spotlight(): gave audience role to {!s}".format(ctx.message.author))

    elif check_role(config.modteam, ctx.message):
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
                clogger.warn("spotlight(): current: No spotlight currently selected.")
                await client.say("No spotlight currently selected.")

        elif command == "showcase":
            clogger.debug("spotlight(): showcase")
            if lucky:
                await client.send_message(showcaseChannel, "**Next spotlight host!**")
                await send_spotlight_info(showcaseChannel, lucky)
            else:
                clogger.warn("spotlight(): showcase: No spotlight currently selected.")
                await client.say("No spotlight currently selected.")
        else:
            err_msg = "{!r} is not a valid spotlight sub-command.".format(command)
            clogger.warn("spotlight(): " + err_msg)
            await client.say("{!r} is not a valid spotlight sub-command.".format(command))
    else:
        err_msg = "Non-mod tried to use mod-only spotlight command: {}".format(message_log_str(ctx.message))
        clogger.warn(err_msg)
        await client.send_message(ctx.message.channel, "You're not allowed to use that command.")
        await client.send_message(outputChannel, "[WARNING] " + err_msg)


@spotlight.error
async def spotlight_on_error(exc, ctx):
    cmd_string = message_log_str(ctx.message)
    if isinstance(exc, commands.CommandInvokeError):
        root_exc = exc.__cause__ if exc.__cause__ is not None else exc

        if isinstance(root_exc, showcaser.Error): # any Google API errors
            clogger.exception("Google API error while processing command: {}".format(cmd_string))
            await client.send_message(ctx.message.channel,
                "An error occurred while communicating with the Google API. "
                "See bot output for details.")
            await client.send_message(outputChannel,
                ("[ERROR] An error occurred while communicating with the Google API.\n"
                "Original command: {}\n{}\n\nSee logs for details")
                .format(cmd_string, exc_log_str(root_exc)))


        elif isinstance(root_exc,
                (showcaser.UnknownClientSecretsFlowError, showcaser.InvalidClientSecretsError)
                ): # Auth credentials file errors
            clogger.exception("Problem with Google API credentials file: {}".format(cmd_string))
            await client.send_message(ctx.message.channel,
                "Problem with the stored Google API credentials. "
                "See bot output for details.")
            await client.send_message(outputChannel,
                ("[ERROR] Problem with Google API credentials file.\n"
                 "Original command: {}\n{}\n\nSee logs for details")
                .format(cmd_string, exc_log_str(root_exc)))

        else:
            on_command_error(exc, ctx, force=True) # Other errors can bubble up
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

    try:
        await client.send_message(destination, embed=em)

    except discord.HTTPException as e:
        clogger.error("Error sending spotlight info ({}): {}".format(cmd_string, e.text))
        await client.send_message(ctx.message.channel,
            "Error sending spotlight info: {}".format(e.text))
        await client.send_message(outputChannel,
            ("[ERROR] Error sending spotlight info.\n"
             "Original command: {}\nDiscord API error: {}\n\n"
             "See logs for details").format(cmd_string, e.text))


def format_list(list_) -> str:
    """
    Format a list as a string for display over Discord, with indices starting from 1.
    """
    fmt = "{0: >3d}. {1:s}"
    text_bits = ["```"]
    text_bits.extend(fmt.format(i+1, item) for i, item in enumerate(list_))
    text_bits.append("```")
    return '\n'.join(text_bits)


@client.command(pass_context = True,
    description="[MOD ONLY] Adds/removes strings to/from filter list. Commands are ad, rd, aw, rw "
    "and l, you can contact me anytime to make sense of the commands.")
@mod_only()
async def filter(ctx):
    clogger.debug("filter(): {}".format(message_log_str(ctx.message)))
    commandraw = str(ctx.message.content)
    command = commandraw[8:]

    if command.startswith("ad "):
        config.filterdelete.append(command[3:])
        config.dict_write()

        reply_msg = "Added `{}` to the auto-delete list.".format(command[3:])
        clogger.info('filter(): ad: ' + reply_msg)
        await client.say(reply_msg)

    elif command.startswith("rd "):
        try:
            del_index = int(command[3:]) - 1
            del_value = config.filterdelete[del_index]
            del config.filterdelete[del_index]

        except IndexError:
            err_msg = "Index out of range: {:d}".format(del_index+1)
            clogger.error("filter(): rd: " + err_msg)
            await client.say(err_msg)
            return

        else: # no exceptions
            config.dict_write()

            reply_msg = "Removed `{}` from the auto-delete list.".format(del_value)
            clogger.info('filter(): rd: ' + reply_msg)
            await client.say(reply_msg)

    elif command.startswith("aw "):
        config.filterwarn.append(command[3:])
        config.dict_write()

        reply_msg = "Added `{}` to the auto-warn list.".format(command[3:])
        clogger.info('filter(): aw: ' + reply_msg)
        await client.say(reply_msg)

    elif command.startswith("rw "):
        try:
            del_index = int(command[3:]) - 1
            del_value = config.filterwarn[del_index]
            del config.filterwarn[del_index]

        except IndexError:
            err_msg = "Index out of range: {:d}".format(del_index+1)
            clogger.error("filter(): rw: " + err_msg)
            await client.say(err_msg)
            return

        else: # no exceptions
            config.dict_write()

            reply_msg = "Removed `{}` from the auto-warn list.".format(del_value)
            clogger.info('filter(): rw: ' + reply_msg)
            await client.say(reply_msg)

    elif command == "list warn":
        clogger.debug("filter(): listing auto-warn")
        if config.filterwarn:
            list_str = format_list(config.filterwarn)
        else:
            list_str = '```Empty```'
        await client.say("**Auto-warn filter**\n\n" + list_str)

    elif command == "list delete":
        clogger.debug("filter(): listing auto-delete")
        if config.filterdelete:
            list_str = format_list(config.filterdelete)
        else:
            list_str = '```Empty```'
        await client.say("**Auto-delete filter**\n\n" + list_str)

    else:
        clogger.debug("filter(): invalid subcommand: {}".format(message_log_str(ctx.message)))
        await client.say(
            "filter: invalid subcommand. Recognised subcommands are "
            "`ad`, `rd`, `aw`, `rw`, `list delete`, `list warn`.")


@client.command(pass_context = True,
    description= "[MOD ONLY] Provide bot info. Useful for testing but responsivity too.")
@mod_only()
async def info(ctx):
    clogger.debug("info(): {!s}".format(message_log_str(ctx.message)))
    usercolor = 0x80AAFF
    em = discord.Embed(color=usercolor)
    em.set_author(name="KazTron %s" % __version__)
    em.add_field(name="Changelog", value=changelog, inline=False)
    em.add_field(name="Instruction Manual",
        value="[Click Here]({})".format(url_manual), inline=True)
    em.add_field(name="GitHub Page",
        value="[Click Here]({})".format(url_github), inline=True)
    em.add_field(name="Development Roadmap",
        value="[Click Here]({})".format(url_roadmap), inline=True)
    em.add_field(name="Spotlight Applications",
        value="[Click Here]({})".format(url_spotlight), inline=True)
    await client.say(embed=em)


## rolls a XdY dice in allowed channels ##
@client.command(pass_context=True, description="Rolls dice. Only allowed on some channels.")
async def rolls(ctx, dice : str):
    """
        Usage: `.rolls xdy`

        Rolls a y-sided die x times.

        Example: `.rolls 3d6` rolls three six-sided dice.
    """
    clogger.info("rolls(): {}".format(message_log_str(ctx.message)))
    dice_channel = client.get_channel(id=config.dicechannel)

    if ctx.message.channel in [
            dice_channel,
            client.get_channel(id=config.testchannel),
            client.get_channel(id=config.warnchannel)
    ]:
        try:
            rolls, limit = map(int, dice.split('d'))
        except ValueError as e:
            err_msg = "Invalid format: {}".format(message_log_str(ctx.message))
            clogger.warn("rolls(): " + err_msg)
            await client.say('Invalid format. Please enter `.rolls XdY`, where X and Y are positive whole numbers.')
            return

        if rolls <= 0:
            clogger.warn("rolls(): arguments out of range")
            await client.say("You have to roll at least 1 die.")
        elif limit <= 1:
            clogger.warn("rolls(): arguments out of range")
            await client.say("Dice must have at least 2 sides.")
        elif limit > 100 or rolls > 100:
            clogger.warn("rolls(): arguments out of range")
            await client.say("The limit for dice number and sides is 100 each.")
        else:
            result = [random.randint(1, limit) for _ in range(rolls)]
            total = sum(result)
            await client.say(str(result))
            await client.say("Sum of your roll is: {:d}".format(total))
            clogger.info("Rolled dice: {:d}d{:d} = {!r} (sum={})"
                .format(rolls, limit, result, total))

    else:
        clogger.warn("rolls(): Used in disallowed channel: {}".format(message_log_str(ctx.message)))
        await client.say("This command is only available in {}".format(dice_channel.mention))


@client.command(pass_context=True, description = "Rolls FATE dice.")
async def rollf(ctx):
    clogger.info("rollf(): {}".format(message_log_str(ctx.message)))
    dice_channel = client.get_channel(id=config.dicechannel)

    if ctx.message.channel in [
            dice_channel,
            client.get_channel(id=config.testchannel),
            client.get_channel(id=config.warnchannel)
    ]:
        dice = [-1,-1,0,0,1,1]
        str_map = {-1: '-', 0: '0', 1: '+'}
        rolls = [random.choice(dice) for _ in range(4)]
        total = sum(rolls)
        rolls_str = [str_map[roll] for roll in rolls]
        await client.say(str(rolls_str))
        await client.say("Sum of your roll is: {:d}".format(total))
        clogger.info("Rolled FATE dice: {!r} (sum={})"
            .format(rolls_str, total))
    else:
        clogger.warn("rollf(): Used in disallowed channel: {}".format(message_log_str(ctx.message)))
        await client.say("This command is only available in {}".format(dice_channel.mention))


@client.command(pass_context=True,
    description = "Gives a mod/admin their 'Distinguish' role (usually for colored name).")
@mod_only()
async def up(ctx):
    clogger.info("up(): {}".format(message_log_str(ctx.message)))
    server = ctx.message.server
    if discord.utils.get(ctx.message.server.roles, name='Senior Moderators') in ctx.message.author.roles:
        await client.add_roles(ctx.message.author,discord.utils.get(server.roles, name='Distinguish-SrM'))
        await client.delete_message(ctx.message)
        clogger.info("up(): Gave {} distinguish (SrM) role".format(ctx.message.author))
    elif discord.utils.get(ctx.message.server.roles, name='Moderators') in ctx.message.author.roles:
        await client.add_roles(ctx.message.author,discord.utils.get(server.roles, name='Distinguish-Mod'))
        await client.delete_message(ctx.message)
        clogger.info("up(): Gave {} distinguish (Mod) role".format(ctx.message.author))
    else:
        err_msg = "up(): user roles not recognised: {}".format(message_log_str(ctx.message))
        clogger.warn(err_msg)
        await client.say("That command is only available to mods and admins.")
        await client.send_message(outputChannel, "[WARNING] " + err_msg)


@client.command(pass_context=True,
    description="Remove a mod/admin's 'Distinguish' role (usually remove their colored name).")
@mod_only()
async def down(ctx):
    clogger.info("down(): {}".format(message_log_str(ctx.message)))
    server = ctx.message.server
    if discord.utils.get(ctx.message.server.roles, name='Senior Moderators') in ctx.message.author.roles:
        await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Distinguish-SrM'))
        await client.delete_message(ctx.message)
        clogger.info("up(): Removed {} distinguish (SrM) role".format(ctx.message.author))
    elif discord.utils.get(ctx.message.server.roles, name='Moderators') in ctx.message.author.roles:
        await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='Distinguish-Mod'))
        await client.delete_message(ctx.message)
        clogger.info("up(): Removed {} distinguish (Mod) role".format(ctx.message.author))
    else:
        err_msg = "down(): user roles not recognised: {}".format(message_log_str(ctx.message))
        clogger.warn(err_msg)
        await client.say("That command is only available to mods and admins.")
        await client.send_message(outputChannel, "[WARNING] " + err_msg)


@client.command(pass_context=True, description="Gives a user the 'tabletop' role on demand. If the user already has the role, takes it away.")
async def rp(ctx):
    clogger.info("rp(): {}".format(message_log_str(ctx.message)))
    server = ctx.message.server
    if discord.utils.get(ctx.message.server.roles, name='tabletop') in ctx.message.author.roles:
        await client.remove_roles(ctx.message.author, discord.utils.get(server.roles, name='tabletop'))
        await client.say("Thou hast been revok'd the 'tabletop' role.")
        clogger.info("up(): Removed tabletop role from user {}".format(ctx.message.author))
    else:
        await client.add_roles(ctx.message.author, discord.utils.get(server.roles, name='tabletop'))
        await client.say("I bestow upon thee the 'tabletop' role.")
        clogger.info("up(): Gave tabletop role to user {}".format(ctx.message.author))


@client.command(pass_context=True,
    description="[MOD ONLY] Finds user with given ID")
@mod_only()
async def find(ctx):
    clogger.info("find(): {}".format(message_log_str(ctx.message)))
    commandraw = str(ctx.message.content)
    command = commandraw[6:]
    user = discord.User(id=command)
    clogger.info("find(): user lookup: {}={!s}".format(command, user))
    await client.say("ID {} is user {}".format(command, user.mention))

## Welcomes a newly joined member on #Worldbuilding and outputs on the output channel##
@client.event
async def on_member_join(member):
    channel = discord.Object(id=config.welcomechannel)
    output_channel = discord.Object(id=outputChannel)
    server = member.server
    fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at #welcome-rules-etc'
    out_fmt = "{0.mention} has joined the server."
    clogger.info("New user welcomed: %s \n" % str(member))
    await client.send_message(channel, fmt.format(member, server))
    await client.send_message(output_channel, out_fmt.format(member))

## Assigns "in voice" role to members who join #voice voice channel ##
@client.event
async def on_voice_state_update(before, after):
    server = after.server
    voice_channel_list = ["voice", "Patricians", "Wild West"]
    if (str(after.voice_channel) in voice_channel_list):
        await client.add_roles(after,discord.utils.get(server.roles, name='in_voice'))
        clogger.info("Given 'in_voice' role to %s" % str(after))
    elif after.voice_channel == None:
        await client.remove_roles(after,discord.utils.get(server.roles, name='in_voice'))
        clogger.info("Taken 'in_voice' role from %s" % str(after))


@client.command(pass_context=True, description="[MOD ONLY] Posts a 'Please talk about worldbuilding' image")
@mod_only()
async def wb(ctx, index:int=None):
    """
    Usage: `.wb [n]`

    Shows a "Please talk about worldbuilding" image. For mods when discussions get off-topic.
    *n* is the index of the image to show; if none, random.
    """
    # TODO: Convert this to configurable instead of hardcoded data
    images = [
        ("https://cdn.discordapp.com/attachments/221333052629057536/376535932003811328/image.jpg", "Teeteegone"),
        ("https://imgur.com/Dajz8Re", "Urmille"),
        ("https://cdn.discordapp.com/attachments/221333052629057536/380517117759324161/worldbuilding_2.jpg", "Yazuki"),
        ("https://cdn.discordapp.com/attachments/221333052629057536/380520533529198594/unknown.png", "Shagomir"),
        ("https://i.gyazo.com/99ec60315371d5f4b62fc31175bb08fa.png", "ProkhorVLG"),
        ("https://cdn.discordapp.com/attachments/193833682203705345/380536568365973504/please_talk_about_worldbuilding.jpg", "Caba111"),
        ("https://cdn.discordapp.com/attachments/221333052629057536/386627117271613442/Talk_About_Worldbuilding.jpg", "Yazuki")
    ]

    if index is None:
        index = random.randint(0, len(images))
        clogger.debug("wb(): random image = {:d}".format(index))

    try:
        image_url, author = images[index]
    except IndexError:
        clogger.warn("wb(): Invalid index: {}".format(message_log_str(ctx.message)))
        await client.say("{} (wb) That image doesn't exist! Valid index range: 0-{:d}"
            .format(ctx.message.author.mention, len(images)-1))
    else:
        clogger.debug("wb(): displaying image {:d}".format(index))
        await client.say(images[index][0])
        await client.say("_Artist: {}_ (Image #{})"
            .format(images[index][1].replace('_', '\_'), index))
    finally:
        await client.delete_message(ctx.message)
    

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(client.login(config.token))
        loop.run_until_complete(client.connect())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        logger.info("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.info("Client closed.")
    except:
        logger.exception("Uncaught exception during bot execution")
        logger.error("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.error("Client closed.")
    finally:
        logger.info("Closing event loop...")
        loop.close()
        logger.info("Loop closed.")
