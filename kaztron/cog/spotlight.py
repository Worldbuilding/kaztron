import random
import time
import logging
from typing import List, Optional, Union
from collections import deque

import discord
from discord.ext import commands

import dateparser
from datetime import datetime

from kaztron.config import get_kaztron_config, get_runtime_config
from kaztron.driver import gsheets
from kaztron.utils.checks import mod_only
from kaztron.utils.decorators import error_handler
from kaztron.utils.discord import get_named_role, MSG_MAX_LEN, Limits, remove_role_from_all
from kaztron.utils.logging import message_log_str, tb_log_str, exc_log_str
from kaztron.utils.strings import format_list, get_help_str, split_code_chunks_on, natural_truncate

logger = logging.getLogger(__name__)


class SpotlightApp:
    """
    Should only be instantiated once the bot is ready (as it attempts to retrieve user data from
    the server).
    """
    def __init__(self, data: List[str], bot: commands.Bot):
        self._data = data
        self.bot = bot
        self._cached_user = None
        self._is_user_cached = False

    @staticmethod
    def is_filled(str_property: str) -> bool:
        return str_property and str_property.lower() != 'n/a'

    @property
    @error_handler(ValueError, datetime.utcfromtimestamp(0))
    @error_handler(IndexError, datetime.utcfromtimestamp(0))
    def timestamp(self) -> datetime:
        return dateparser.parse(self._data[0])

    @property
    @error_handler(IndexError, "")
    def user_name(self) -> str:
        return self._data[1]

    @property
    @error_handler(ValueError, "")
    @error_handler(IndexError, "")
    def user_id(self) -> str:
        return self._data[2]

    async def get_user(self, ctx: commands.Context=None)\
            -> Union[discord.User, discord.Member, None]:
        """
        Return a :cls:`discord.User` or :cls:`discord.Member` class for the current user.
        Returns None if the application's discord ID is invalid.

        If possible, this method will return a cached copy of a :cls:`discord.User` if it has been
        called previously (this won't work if the spotlight applications cache has been refreshed -
        see the main cog class), avoiding API calls.

        If ``ctx`` is provided, always fetches a :cls:`discord.Member` from the current server's
        user cache.

        :param ctx: Context. If provided, return the Member on the current server.
        :return:
        """
        if ctx is None:
            if self._is_user_cached:
                return self._cached_user

            try:
                self._cached_user = await self.bot.get_user_info(self._data[2])
            except (discord.NotFound, discord.HTTPException):
                self._cached_user = None
            self._is_user_cached = True
            return self._cached_user
        else:
            return ctx.message.server.get_member(self._data[2])

    @property
    @error_handler(IndexError, "")
    def user_reddit(self) -> str:
        return self._data[3]

    @property
    @error_handler(IndexError, "")
    def project(self) -> str:
        return self._data[4]

    @property
    @error_handler(IndexError, "")
    def keywords(self) -> str:
        return self._data[5]

    @property
    @error_handler(IndexError, "")
    def favorite(self) -> str:
        return self._data[6]

    @property
    @error_handler(IndexError, "")
    def talking_point(self) -> str:
        return self._data[7]

    @property
    @error_handler(IndexError, "")
    def mature(self) -> str:
        return self._data[8]

    @property
    @error_handler(IndexError, "")
    def inspirations(self) -> str:
        return self._data[9]

    @property
    @error_handler(IndexError, "")
    def prompt(self) -> str:
        return self._data[10]

    @property
    @error_handler(IndexError, "")
    def pitch(self) -> str:
        return self._data[11]

    @property
    @error_handler(IndexError, False)
    def is_nsfw(self) -> bool:
        return self._data[12].lower() == 'yes'

    @property
    @error_handler(IndexError, "")
    def nsfw_info(self) -> str:
        return self._data[13]

    @property
    @error_handler(IndexError, "")
    def art_url(self) -> str:
        return self._data[14]

    @property
    @error_handler(IndexError, "")
    def additional_info_url(self) -> str:
        return self._data[15]

    @property
    @error_handler(IndexError, False)
    def is_ready(self) -> bool:
        return self._data[16].lower() == 'yes'

    @property
    @error_handler(IndexError, "")
    def unnamed(self) -> str:
        return self._data[17]

    def __str__(self):
        return "{} - {}".format(self.user_name, self.project)

    async def str_discord(self):
        user = await self.get_user()
        if user:
            return "{} - {}".format(user.mention, self.project)
        else:
            return str(self)


class Spotlight:
    msg_join = \
        "You are now a part of the World Spotlight audience. You can be pinged by the "\
        "moderators or the host for spotlight-related news (like the start of a "\
        "spotlight). You can use `.spotlight leave` to leave the audience."

    msg_join_err = \
        "Oops! You're already part of the World Spotlight audience. If you want to leave, " \
        "please use `.spotlight leave`. (Note that this change happened for KazBot 1.3)."

    msg_leave = \
        "You are no longer part of the World Spotlight audience. You will no longer be pinged "\
        "for spotlight-related news. You can use `.spotlight join` to join the audience " \
        "again."

    msg_leave_err = \
        "Oops! You're not currently part of the World Spotlight audience. If you want to join, " \
        "please use `.spotlight join`."

    APPLICATIONS_CACHE_EXPIRES_S = 60.0

    LIST_HEADING = "**Spotlight Applications**"
    QUEUE_HEADING = "**Upcoming Spotlight Queue**"
    QUEUE_ADD_HEADING = "**Added to Queue**"
    QUEUE_INSERT_HEADING = "**Inserted into Queue**"
    QUEUE_REM_HEADING = "**Removed from Queue**"

    UNKNOWN_APP_STR = "Unknown - Index out of bounds"

    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        try:
            self.db = get_runtime_config()
        except OSError as e:
            logger.error(str(e))
            raise RuntimeError("Failed to load runtime config") from e

        self._make_default_config()

        self.dest_output = None
        self.dest_spotlight = None
        self.role_audience_name = self.config.get('spotlight', 'audience_role')
        self.role_host_name = self.config.get('spotlight', 'host_role')

        self.user_agent = self.config.get("core", "name")
        self.gsheet_id = self.config.get("spotlight", "spreadsheet_id")
        self.gsheet_range = self.config.get("spotlight", "spreadsheet_range")
        self.applications = []
        self.applications_last_refresh = 0

        self.current_app_index = int(self.db.get('spotlight', 'current', -1))
        self.queue = deque(self.db.get('spotlight', 'queue', []))

    def _make_default_config(self):
        changed = False
        c = self.db
        try:
            int(c.get('spotlight', 'current'))
        except (KeyError, ValueError):
            c.set('spotlight', 'current', -1)
            changed = True

        try:
            c.get('spotlight', 'queue')
        except KeyError:
            c.set('spotlight', 'queue', [])
            changed = True

        if changed:
            c.write()

    def _load_applications(self):
        """ Load Spotlight applications from the Google spreadsheet. """
        if time.monotonic() - self.applications_last_refresh > self.APPLICATIONS_CACHE_EXPIRES_S:
            logger.debug("Cache miss: Loading Spotlight applications from Google Sheets")
            apps_data = gsheets.get_sheet_rows(self.gsheet_id, self.gsheet_range, self.user_agent)
            self.applications = [SpotlightApp(app, self.bot) for app in apps_data]
            self.applications_last_refresh = time.monotonic()
        else:
            logger.debug("Cache hit: Using Spotlight applications cache")

    def _write_db(self):
        """ Write all data to the dynamic configuration file. """
        self.db.set('spotlight', 'current', self.current_app_index)
        self.db.set('spotlight', 'queue', list(self.queue))
        self.db.write()

    async def _get_current(self) -> SpotlightApp:
        """
        Get the current application.

        :raises IndexError: Current index invalid or not set. In this case, note that logging and
        messaging the command caller is already handled.
        """
        logger.info("Retrieving current spotlight application "
                    "index={:d}...".format(self.current_app_index))

        if self.current_app_index < 0:
            err_msg = "No spotlight application selected"
            logger.warning("_get_current: " + err_msg)
            await self.bot.say("**No spotlight application selected**")
            raise IndexError(err_msg)

        try:
            return self.applications[self.current_app_index]
        except IndexError as e:
            err_msg = "Invalid current spotlight index: {:d}".format(self.current_app_index)
            logger.warning("_get_current: " + err_msg)
            await self.bot.say("**Selected spotlight application no longer exists.**")
            self.current_app_index = -1
            self._write_db()
            raise IndexError(err_msg) from e

    async def _get_app(self, index) -> SpotlightApp:
        """
        Get an application from index (internal zero-index, not user one-based index).

        :param index: Index to retrieve (zero-indexed).

        :raises IndexError: Passed index is not valid. In this case, not that logging and messaging
        the command caller is already handled.
        """

        try:
            if index < 0:
                raise IndexError()  # to make use of the same handling code for neg indices...
            app = self.applications[index]
        except IndexError as e:
            err_msg = "list index {:d} out of bounds (1-{:d})"\
                        .format(index + 1, len(self.applications))
            logger.warning("_get_app: " + err_msg)
            await self.bot.say(
                ("That isn't a valid spotlight application! "
                 "Valid indices are currently 1 to {:d}")
                .format(len(self.applications)))
            raise IndexError(err_msg) from e
        else:
            return app

    async def send_spotlight_info(self, destination: discord.Object, app: SpotlightApp) -> None:
        """
        Sends a discord.Embed object containing human-readable formatted
        spotlight_data to the given destination.

        :param destination: The destination as a Discord object (often a :cls:`discord.Channel`)
        :param app: the array of spotlight data to send
        :return: None, or a :cls:`discord.HTTPException` class if sending fails (this is already
            logged and communicated over Discord, provided for informational purposes/further
            handling)
        """
        index = self.applications.index(app) + 1
        logger.info("Displaying spotlight data for: {!s}".format(app))

        user = await app.get_user()

        em = discord.Embed(color=0x80AAFF, title=app.user_name[:128])
        em.set_author(name="Spotlight Application #{:d}".format(index))
        em.add_field(name="Project Name", value=app.project, inline=True)
        em.add_field(name="Author",
                     value=user.mention if user else (app.user_name[:128] + " (invalid ID)"),
                     inline=True)

        if app.is_filled(app.user_reddit):
            em.add_field(name="Reddit", value="/u/" + app.user_reddit[:128], inline=True)

        em.add_field(name="Elevator Pitch",
                     value=natural_truncate(app.pitch, Limits.EMBED_FIELD_VALUE) or "None",
                     inline=False)

        if app.is_filled(app.mature):
            em.add_field(name="Mature & Controversial Issues",
                         value=natural_truncate(app.mature, Limits.EMBED_FIELD_VALUE),
                         inline=False)

        em.add_field(name="Keywords",
                     value=natural_truncate(app.keywords, Limits.EMBED_FIELD_VALUE) or "None",
                     inline=False)

        if app.is_filled(app.art_url):
            em.add_field(name="Project Art",
                         value=natural_truncate(app.art_url, Limits.EMBED_FIELD_VALUE),
                         inline=True)

        if app.is_filled(app.additional_info_url):
            em.add_field(name="Additional Content",
                         value=natural_truncate(app.additional_info_url, Limits.EMBED_FIELD_VALUE),
                         inline=True)

        await self.bot.send_message(destination, embed=em)

    async def on_ready(self):
        """ Load information from the server. """
        id_output = self.config.get('discord', 'channel_output')
        self.dest_output = self.bot.get_channel(id_output)

        id_spotlight = self.config.get('spotlight', 'channel')
        self.dest_spotlight = self.bot.get_channel(id_spotlight)

        # validation
        if self.dest_output is None:
            raise ValueError("Output channel '{}' not found".format(id_output))

        if self.dest_spotlight is None:
            raise ValueError("Spotlight channel '{}' not found".format(id_spotlight))

        # get spotlight applications - mostly to verify the connection
        self._load_applications()

    @commands.group(invoke_without_command=True, pass_context=True)
    async def spotlight(self, ctx):
        """
        Manages the World Spotlight event. Users: see `.help spotlight join`.
        """
        command_list = list(self.spotlight.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

    @spotlight.command(pass_context=True)
    async def join(self, ctx):
        """
        Join the Spotlight Audience. This allows you to be pinged by moderators or the Spotlight
        Host for news about the spotlight (like the start of a new spotlight, or a newly released
        schedule).

        To leave the Spotlight Audience, use `.spotlight leave`.
        """
        logger.debug("join: " + message_log_str(ctx.message)[:64])
        role = get_named_role(ctx.message.server, self.role_audience_name)

        if role not in ctx.message.author.roles:
            await self.bot.add_roles(ctx.message.author, role)
            logger.info("join: Gave role {} to user {}"
                .format(self.role_audience_name, ctx.message.author))
            await self.bot.send_message(ctx.message.author, self.msg_join)
        else:
            await self.bot.send_message(ctx.message.author, self.msg_join_err)
        await self.bot.delete_message(ctx.message)

    @spotlight.command(pass_context=True)
    async def leave(self, ctx):
        """
        Leave the Spotlight Audience. See `.help spotlight join` for more information.

        To join the Spotlight Audience, use `.spotlight join`.
        """
        logger.debug("leave: " + message_log_str(ctx.message)[:64])
        role = get_named_role(ctx.message.server, self.role_audience_name)

        if role in ctx.message.author.roles:
            await self.bot.remove_roles(ctx.message.author, role)
            logger.info("leave: Removed role {} from user {}"
                .format(self.role_audience_name, ctx.message.author))
            await self.bot.send_message(ctx.message.author, self.msg_leave)
        else:
            await self.bot.send_message(ctx.message.author, self.msg_leave_err)
        await self.bot.delete_message(ctx.message)

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['l'])
    @mod_only()
    async def list(self, ctx):
        """
        [MOD ONLY] List all the spotlight applications in summary form.
        """
        logger.debug("list: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        logger.info("Listing all spotlight applications for {0.author!s} in {0.channel!s}"
            .format(ctx.message))

        if self.applications:
            app_list_string = format_list([str(app) for app in self.applications])
        else:
            app_list_string = 'Empty'

        say_strings = split_code_chunks_on(
            app_list_string,
            MSG_MAX_LEN - len(self.LIST_HEADING) - 2
        )
        logger.info([len(s) for s in say_strings])
        await self.bot.say("{}\n{}".format(self.LIST_HEADING, say_strings[0]))
        for say_str in say_strings[1:]:
            await self.bot.say(say_str)

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['c'])
    @mod_only()
    async def current(self, ctx):
        """ [MOD ONLY] Show the currently selected application. """
        logger.debug("current: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        try:
            await self.send_spotlight_info(ctx.message.channel, await self._get_current())
        except IndexError:
            return  # get_current() already handles this

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['r'])
    @mod_only()
    async def roll(self, ctx):
        """
        [MOD ONLY] Select a spotlight application at random, and set it as the currently selected
        application. Only applications that are marked 'ready for Spotlight' will be selected.
        """
        logger.debug("roll: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        if not self.applications:
            logger.warning("roll: No spotlight applications found")
            await self.bot.say("There are no spotlight applications!")
            return

        selected_app = random.choice(list(filter(lambda app: app.is_ready, self.applications)))
        self.current_app_index = self.applications.index(selected_app)
        self._write_db()

        logger.info("roll: Currently selected app {:d} {!s}"
            .format(self.current_app_index, selected_app))
        await self.send_spotlight_info(ctx.message.channel, selected_app)

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['s'])
    @mod_only()
    async def select(self, ctx, list_index: int):
        """
        [MOD ONLY] Set a specific spotlight application as the currently selected application.

        Arguments:
        * list_index: Required. The numerical index of a spotlight application, as shown with
         .spotlight list.
        """
        logger.debug("set: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        if not self.applications:
            logger.warning("set: No spotlight applications found")
            await self.bot.say("There are no spotlight applications!")
            return

        array_index = list_index - 1
        try:
            selected_app = await self._get_app(array_index)
        except IndexError:
            return  # already handled by _get_app
        else:
            self.current_app_index = array_index
            self._write_db()

            logger.info("set: Currently selected app: (#{:d}) {!s}"
                .format(list_index, selected_app))
            await self.send_spotlight_info(ctx.message.channel, selected_app)

    @spotlight.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def showcase(self, ctx):
        """
        [MOD ONLY] Publicly announce the currently selected application in the Spotlight channel,
        and switch the Spotlight Host role to the application's owner (if valid).
        """

        # Retrieve and showcase the app
        logger.debug("showcase: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        try:
            current_app = await self._get_current()
        except IndexError:
            return  # get_current() already handles this

        user = await current_app.get_user(ctx)  # None if invalid

        await self.bot.send_message(self.dest_spotlight,
            "**WORLD SPOTLIGHT**\n\n"
            "Our next host is {0}, presenting their project, *{1}*!\n\nWelcome, {0}!"
                .format(user.mention if user else current_app.user_name, current_app.project))
        await self.send_spotlight_info(self.dest_spotlight, current_app)
        await self.bot.say("Application showcased: {}".format(await current_app.str_discord()))

        server = ctx.message.server  # type: discord.Server
        host_role = get_named_role(server, self.role_host_name)

        # Deassign the spotlight host role
        await remove_role_from_all(self.bot, server, host_role)

        # Assign the role to the selected app's owner
        if user is not None:
            await self.bot.add_roles(user, host_role)
            await self.bot.say("'{}' role switched to {.mention}.".format(self.role_host_name, user))
        else:
            logger.warning("Invalid discord ID in application: '{}'".format(current_app.user_id))
            await self.bot.say("Can't set new Spotlight Host role: "
                               "Application Discord ID '{0.user_id}' is invalid (app: {0!s})"
                               .format(current_app))

    @spotlight.group(pass_context=True, invoke_without_command=True, aliases=['q'])
    @mod_only()
    async def queue(self, ctx):
        """
        [MOD ONLY] The `.spotlight queue` sub-command contains sub-sub-commands that let moderators
        manage a queue of upcoming spotlights.
        """
        command_list = list(self.spotlight.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

    def _get_queue_list(self):
        app_strings = []
        for app_index in self.queue:
            try:
                # don't convert this to _get_app - don't want the error msgs from that
                app_strings.append("(#{0:d}) {1!s}"
                    .format(app_index + 1, self.applications[app_index]))
            except IndexError:
                app_strings.append("#{0:d}) {}".format(app_index, self.UNKNOWN_APP_STR))
        return app_strings

    @queue.command(name='list', ignore_extra=False, pass_context=True, aliases=['l'])
    @mod_only()
    async def queue_list(self, ctx):
        """
        [MOD ONLY] Lists the current queue of upcoming spotlights.
        """
        logger.debug("queue list: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        logger.info("Listing queue for {0.author!s} in {0.channel!s}".format(ctx.message))

        app_strings = self._get_queue_list()
        if app_strings:
            app_list_string = format_list(app_strings)
        else:
            app_list_string = 'Empty'

        say_strings = split_code_chunks_on(
            app_list_string,
            MSG_MAX_LEN - len(self.LIST_HEADING) - 2
        )
        await self.bot.say("{}\n{}".format(self.QUEUE_HEADING, say_strings[0]))
        for say_str in say_strings[1:]:
            await self.bot.say(say_str)

    @queue.command(name='add', ignore_extra=False, pass_context=True, aliases=['a'])
    @mod_only()
    async def queue_add(self, ctx, list_index: int=None):
        """
        [MOD ONLY] Add a spotlight application to the end of the queue of upcoming spotlights. You
        can either use the currently selected spotlight, or specify an index number for the
        spotlight application to add.

        Arguments:
        * list_index: Optional, int. The numerical index of a spotlight application, as shown with
        .spotlight list. If this is not provided, the currently selected application will be used
        (so you don't have to specify this argument if you're using `.spotlight roll` or
        `.spotlight set`, for example).

        Examples:
        * `.spotlight queue add` - Adds the currently selected application to the end of the queue.
        * `.spotlight queue add 13` - Adds application #13 to the end of the queue.
        """
        logger.debug("queue add: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        if list_index is not None:
            array_index = list_index - 1
            try:
                app = await self._get_app(array_index)
            except IndexError:
                return  # already handled by _get_app
            else:
                self.queue.append(array_index)
                logger.info("queue add: added #{:d} from passed arg".format(list_index))
        else:  # no list_index passed
            try:
                app = await self._get_current()
            except IndexError:
                return  # already handled by _get_current
            else:
                self.queue.append(self.current_app_index)
                logger.info("queue add: added #{:d} from current select"
                    .format(self.current_app_index + 1))

        self._write_db()
        await self.bot.say("{}\n```{:d}. {!s}```".format(
            self.QUEUE_ADD_HEADING, len(self.queue) - 1, app
        ))

    @queue.command(name='insert', ignore_extra=False, pass_context=True, aliases=['i'])
    @mod_only()
    async def queue_insert(self, ctx, queue_index: int, list_index: int=None):
        """
        [MOD ONLY] Insert a spotlight application into the queue of upcoming spotlights. You can
        either use the currently selected spotlight, or specify an index number for the spotlight
        application to add.

        Arguments:
        * queue_index: Required, int. The numerical position at which to insert this entry in the
          queue.
        * list_index: Optional, int. The numerical index of a spotlight application, as shown with
        .spotlight list. If this is not provided, the currently selected application will be used
        (so you don't have to specify this argument if you're using `.spotlight roll` or
        `.spotlight set`, for example).

        Examples:
        * `.spotlight queue insert 4` - Insert the currently selected application to the 4th
          position in the queue.
        * `.spotlight queue add 1 13` - Adds application #13 to the front of the queue.
        """
        logger.debug("queue insert: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        queue_array_index = queue_index - 1

        if list_index is not None:
            array_index = list_index - 1
            try:
                app = await self._get_app(array_index)
            except IndexError:
                return  # already handled by _get_app
            else:
                self.queue.insert(queue_array_index, array_index)
                logger.info("queue insert: inserted #{1:d} at {0:d} from passed arg"
                    .format(queue_index, list_index))
        else:  # no list_index passed
            try:
                app = await self._get_current()
            except IndexError:
                return  # already handled by _get_current
            else:
                self.queue.insert(queue_array_index, self.current_app_index)
                logger.info("queue insert: inserted #{1:d} at {0:d} from current select"
                    .format(queue_index, self.current_app_index + 1))

        self._write_db()
        await self.bot.say("{}\n```{:d}. {!s}```".format(
            self.QUEUE_INSERT_HEADING, queue_index, app
        ))

    @queue.command(name='next', ignore_extra=False, pass_context=True, aliases=['n'])
    @mod_only()
    async def queue_next(self, ctx):
        """
        [MOD ONLY] Set the next spotlight in the queue as the currently selected spotlight, and
        remove it from the queue. This is useful when a new spotlight is ready to start, as you can
        then immediately use `.spotlight showcase` to announce it publicly.
        """
        logger.debug("queue next: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        old_index = self.current_app_index
        self.current_app_index = self.queue.popleft()
        try:
            await self.send_spotlight_info(ctx.message.channel, await self._get_current())
        except IndexError:
            self.bot.say("Sorry, the queued index seems to have become invalid!")
            self.queue.appendleft(self.current_app_index)
            self.current_app_index = old_index
            return  # get_current() already handles this
        except:
            self.queue.appendleft(self.current_app_index)
            self.current_app_index = old_index
            raise
        else:
            self._write_db()

    @queue.command(name='rem', ignore_extra=False, pass_context=True, aliases=['r'])
    @mod_only()
    async def queue_rem(self, ctx, queue_index: int):
        logger.debug("queue rem: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        queue_array_index = queue_index - 1
        try:
            array_index = self.queue[queue_array_index]
            list_index = array_index + 1  # user-facing
        except IndexError:
            err_msg = "queue index {:d} out of bounds (1-{:d})" \
                .format(queue_index, len(self.queue))
            logger.warning("queue rem: " + err_msg)
            await self.bot.say(
                "That isn't a valid queue position! Valid indices are currently 1 to {:d}"
                .format(len(self.queue))
            )
            return

        try:
            # don't use _get_app - don't want errmsgs
            app_str = "(#{:d}) {!s}".format(list_index, self.applications[array_index])
        except IndexError:
            app_str = "(#{0:d}) {}".format(list_index, self.UNKNOWN_APP_STR)

        del self.queue[queue_array_index]

        logger.info("queue rem: removed index {0:d}".format(queue_index))
        self._write_db()
        await self.bot.say("{}\n```{:d}. {}```".format(
            self.QUEUE_REM_HEADING, queue_index, app_str
        ))

    @list.error
    @current.error
    @roll.error
    @select.error
    @showcase.error
    @queue_list.error
    @queue_add.error
    @queue_insert.error
    @queue_next.error
    @queue_rem.error
    async def spotlight_on_error(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc

            # noinspection PyUnresolvedReferences
            if isinstance(root_exc, gsheets.Error):  # any Google API errors
                logger.error("Google API error while processing command: {}\n\n{}"
                    .format(cmd_string, tb_log_str(root_exc)))
                await self.bot.send_message(ctx.message.channel,
                    "An error occurred while communicating with the Google API. "
                    "See bot output for details.")
                await self.bot.send_message(self.dest_output,
                    ("[ERROR] An error occurred while communicating with the Google API.\n"
                     "Original command: {}\n{}\n\nSee logs for details")
                        .format(cmd_string, exc_log_str(root_exc)))

            elif isinstance(root_exc,
                    (gsheets.UnknownClientSecretsFlowError, gsheets.InvalidClientSecretsError)
            ):  # Auth credentials file errors
                logger.error("Problem with Google API credentials file: {}\n\n{}"
                    .format(cmd_string, tb_log_str(root_exc)))
                await self.bot.send_message(ctx.message.channel,
                    "Problem with the stored Google API credentials. "
                    "See bot output for details.")
                await self.bot.send_message(self.dest_output,
                    ("[ERROR] Problem with Google API credentials file.\n"
                     "Original command: {}\n{}\n\nSee logs for details")
                        .format(cmd_string, exc_log_str(root_exc)))

            elif isinstance(root_exc, discord.HTTPException):
                cmd_string = str(ctx.message.content)[11:]
                logger.error("Error sending spotlight info ({}): {!s}"
                    .format(cmd_string, root_exc))
                await self.bot.send_message(ctx.message.channel,
                    ("Error sending spotlight info, "
                     "maybe the message is too long but Discord is stupid and might not "
                     "give a useful error message here: {!s}").format(root_exc))
                await self.bot.send_message(self.dest_output,
                    ("[ERROR] Error sending spotlight info.\n"
                     "Original command: {}\nDiscord API error: {!s}\n\n"
                     "See logs for details").format(cmd_string, root_exc))

            else:
                core_cog = self.bot.get_cog("CoreCog")
                await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(Spotlight(bot))
