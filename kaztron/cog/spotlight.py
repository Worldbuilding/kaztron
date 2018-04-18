import random
import re
import time
import logging
from typing import List, Union
from collections import deque

import discord
from discord.ext import commands

from datetime import datetime, date, timedelta

from kaztron import KazCog, theme
from kaztron.cog.role_man import RoleManager
from kaztron.driver import gsheets
from kaztron.utils.checks import mod_only
from kaztron.utils.converter import NaturalDateConverter
from kaztron.utils.datetime import utctimestamp, parse as dt_parse, parse_daterange, \
    get_month_offset, truncate
from kaztron.utils.decorators import error_handler
from kaztron.utils.discord import get_named_role, Limits, remove_role_from_all, \
    extract_user_id, user_mention, get_member, get_help_str
from kaztron.utils.logging import message_log_str, tb_log_str, exc_log_str
from kaztron.utils.strings import format_list, natural_truncate, split_chunks_on

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
        return dt_parse(self._data[0], future=False)

    @property
    @error_handler(IndexError, "")
    def user_name(self) -> str:
        return self._data[1].strip()

    @property
    @error_handler(IndexError, "")
    def user_name_only(self) -> str:
        """ User name without discriminator (if provided in the field). """
        return self._data[1].split('#', maxsplit=1)[0].strip()

    @property
    @error_handler(IndexError, "")
    def user_discriminator(self) -> str:
        """ Discriminator (the #xxxx part of an @mention in the client, if provided). """
        return self._data[1].split('#', maxsplit=1)[1].strip()

    @property
    @error_handler(IndexError, "")
    def user_disp(self) -> str:
        """ Displayed user: either a mention if possible, else their user_name_only. """
        try:
            s_user_id = extract_user_id(self.user_id)
        except discord.InvalidArgument:
            return self.user_name_only.strip()
        else:
            return user_mention(s_user_id)

    @property
    @error_handler(ValueError, "")
    @error_handler(IndexError, "")
    def user_id(self) -> str:
        return self._data[2].strip()

    @property
    @error_handler(IndexError, "")
    def user_reddit(self) -> str:
        return self._data[3].strip()

    @property
    @error_handler(IndexError, "")
    def project(self) -> str:
        return self._data[4].strip()

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

    @property
    def is_valid(self) -> bool:
        return self.user_name and self.project and not self.project.upper() == 'DELETED'

    def __str__(self):
        return "{} - {}".format(self.user_name, self.project)

    def discord_str(self):
        try:
            s_user_id = extract_user_id(self.user_id)
        except discord.InvalidArgument:
            author_value = "{} (invalid ID)".format(self.user_name_only)
        else:
            author_value = "{} ({})".format(self.user_name_only, user_mention(s_user_id))
        return "{} - *{}*".format(author_value, self.project.replace('*', '\\*'))


class Spotlight(KazCog):
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

    LIST_HEADING = "Spotlight Application List"
    QUEUE_HEADING = "**Upcoming Spotlight Queue**"
    QUEUE_ADD_HEADING = "**Added to Queue**"
    QUEUE_EDIT_HEADING = "**Edited in Queue**"
    QUEUE_REM_HEADING = "**Removed from Queue**"
    QUEUE_ENTRY_FMT = '(#{id:d}) [{start}–{end}] {app}'
    QUEUE_CHANGED_FMT = '{msg}: {i:d}. ' + QUEUE_ENTRY_FMT
    QUEUE_SHOWCASE_FMT = '{app_obj.user_disp} with **{app_obj.project}** ({start}–{end})'

    UNKNOWN_APP_STR = "Unknown - Index out of bounds"

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults('spotlight', current=-1, queue=[])

        self.channel_spotlight = None
        self.role_audience_name = self.config.get('spotlight', 'audience_role')
        self.role_host_name = self.config.get('spotlight', 'host_role')

        self.user_agent = self.config.get("core", "name")
        self.gsheet_id = self.config.get("spotlight", "spreadsheet_id")
        self.gsheet_range = self.config.get("spotlight", "spreadsheet_range")
        self.applications = []
        self.applications_last_refresh = 0

        self.current_app_index = int(self.state.get('spotlight', 'current', -1))
        self.queue_data = deque(self.state.get('spotlight', 'queue', []))

        self.time_formats = (self.config.get('spotlight', 'start_date_format'),
                             self.config.get('spotlight', 'end_date_format'))

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
        self.state.set('spotlight', 'current', self.current_app_index)
        self.state.set('spotlight', 'queue', list(self.queue_data))
        self.state.write()

    def _upgrade_queue_v21(self):
        new_queue = deque()
        cur_date = datetime.utcnow()
        next_date = cur_date + timedelta(days=1)
        if self.queue_data and not isinstance(self.queue_data[0], dict):
            logger.info("Upgrading queue to version 2.1")
            for queue_index in self.queue_data:
                new_queue.append({
                    'index': queue_index,
                    'start': cur_date.timestamp(),
                    'end': next_date.timestamp()
                })
                cur_date += timedelta(days=2)
                next_date += timedelta(days=2)
            self.queue_data = new_queue
            self._write_db()

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

        try:
            s_user_id = extract_user_id(app.user_id)
        except discord.InvalidArgument:
            author_value = "{} (invalid ID)".format(app.user_name_only)
        else:
            author_value = "{} ({})".format(user_mention(s_user_id), app.user_name_only)

        em = discord.Embed(color=0x80AAFF)
        em.add_field(name="Project Name", value=app.project, inline=True)
        em.add_field(name="Author", value=author_value, inline=True)

        # if app.is_filled(app.user_reddit):
        #     em.add_field(name="Reddit", value="/u/" + app.user_reddit[:128], inline=True)

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
        await self.bot.say("Spotlight ID #{:d}: {!s}".format(index, app))

    async def send_validation_warnings(self, ctx: commands.Context, app: SpotlightApp):
        """
        Handles validating the app (mostly existence of the user), and communicating any warnings
        via Discord message to msg_dest.
        """
        try:
            user_id = extract_user_id(app.user_id)
        except discord.InvalidArgument:
            logger.warning("User ID format for spotlight app is invalid: '{}'".format(app.user_id))
            await self.bot.say("**Warning**: User ID format is invalid: '{}'".format(app.user_id))
            return

        # user not on server
        if ctx.message.server.get_member(user_id) is None:
            logger.warning("Spotlight app user not on server: '{}' {}"
                .format(app.user_name_only, user_id))
            await self.bot.say("**Warning:** User not on server: {} {}"
                .format(app.user_name_only, user_mention(user_id)))

    async def send_embed_list(self, title: str, contents: str):
        contents_split = split_chunks_on(contents, Limits.EMBED_FIELD_VALUE)
        em = discord.Embed(color=0x80AAFF, title=title)
        sep = '-'
        num_fields = 0
        max_fields = (Limits.EMBED_TOTAL - len(title) - 2) \
            // (Limits.EMBED_FIELD_VALUE + len(sep))
        for say_str in contents_split:
            if num_fields >= max_fields:
                await self.bot.say(embed=em)
                em = discord.Embed(color=theme.solarized.cyan, title=title)
                num_fields = 0
            em.add_field(name=sep, value=say_str, inline=False)
            num_fields += 1
        await self.bot.say(embed=em)

    async def on_ready(self):
        """ Load information from the server. """
        id_spotlight = self.config.get('spotlight', 'channel')
        self.channel_spotlight = self.validate_channel(id_spotlight)

        roleman = self.bot.get_cog("RoleManager")  # type: RoleManager
        if roleman:
            try:
                roleman.add_managed_role(
                    role_name=self.role_audience_name,
                    join_name="join",
                    leave_name="leave",
                    join_msg=self.msg_join,
                    leave_msg=self.msg_leave,
                    join_err=self.msg_join_err,
                    leave_err=self.msg_leave_err,
                    join_doc="Join the Spotlight Audience. This allows you to be pinged by "
                             "moderators or the Spotlight Host for news about the spotlight (like "
                             "the start of a new spotlight, or a newly released schedule).\n\n"
                             "To leave the Spotlight Audience, use `.spotlight leave`.",
                    leave_doc="Leave the Spotlight Audience. See `.help spotlight join` for more "
                              "information.\n\n"
                              "To join the Spotlight Audience, use `.spotlight join`.",
                    group=self.spotlight,
                    cog_instance=self,
                    ignore_extra=False
                )
            except discord.ClientException:
                logger.warning("`sprint follow` command already defined - "
                               "this is OK if client reconnected")
        else:
            err_msg = "Cannot find RoleManager - is it enabled in config?"
            logger.error(err_msg)
            await self.send_output(err_msg)

        # convert queue from v2.0 queue
        self._upgrade_queue_v21()

        # get spotlight applications - mostly to verify the connection
        self._load_applications()

        await super().on_ready()

    @commands.group(invoke_without_command=True, pass_context=True)
    async def spotlight(self, ctx):
        """
        Manages the World Spotlight event. Users: see `.help spotlight join`.
        """
        command_list = list(self.spotlight.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

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

        # format each application as a string
        app_str_list = []
        for app in self.applications:
            if app.is_valid:
                app_str_list.append(app.discord_str())
            else:  # deleted entries: blank username/project name or blank user/'DELETED' project
                app_str_list.append(None)
                continue

        # format into a string list for display
        app_list_string = format_list(app_str_list) if app_str_list else 'Empty'
        # cleanup for deleted records
        # We don't have a dedicated column for this, so hacky regex post-numbering it is!
        app_list_string = re.sub(r'(^|\n)\s*\d+\. None(\n|$)', '\n', app_list_string)
        await self.send_embed_list(title=self.LIST_HEADING, contents=app_list_string)

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['c'])
    @mod_only()
    async def current(self, ctx):
        """ [MOD ONLY] Show the currently selected application. """
        logger.debug("current: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        try:
            app = await self._get_current()
        except IndexError:
            return  # get_current() already handles this
        await self.send_spotlight_info(ctx.message.channel, app)
        await self.send_validation_warnings(ctx, app)

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
        await self.send_validation_warnings(ctx, selected_app)

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
            await self.send_validation_warnings(ctx, selected_app)

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

        try:
            role = get_named_role(ctx.message.server, self.role_audience_name)
        except ValueError:
            logger.exception("Can't retrieve Spotlight Audience role")
            role = None

        await self.bot.send_message(self.channel_spotlight,
            "**WORLD SPOTLIGHT** {2}\n\n"
            "Our next host is {0}, presenting their project, *{1}*!\n\n"
            "Welcome, {0}!".format(
                current_app.user_disp,
                current_app.project,
                role.mention if role else ""
            )
        )
        await self.send_spotlight_info(self.channel_spotlight, current_app)
        await self.bot.say("Application showcased: {} ({}) - {}"
            .format(current_app.user_disp, current_app.user_name_only, current_app.project)
        )
        await self.send_validation_warnings(ctx, current_app)

        # Deassign the spotlight host role
        server = ctx.message.server  # type: discord.Server
        host_role = get_named_role(server, self.role_host_name)
        await remove_role_from_all(self.bot, server, host_role)

        # Assign the role to the selected app's owner
        try:
            user = get_member(ctx, current_app.user_id)
        except discord.InvalidArgument:
            logger.warning("Invalid discord ID in application: '{}'".format(current_app.user_id))
            await self.bot.say(("Can't set new Spotlight Host role: Application Discord ID "
                                "'{0.user_id}' is invalid or user not on server")
                .format(current_app))
        else:
            await self.bot.add_roles(user, host_role)
            await self.bot.say("'{}' role switched to {.mention}."
                .format(self.role_host_name, user))

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

    def _get_queue_list(self, showcase=False):
        app_strings = []
        for queue_item in self.queue_data:
            app_index = queue_item['index']
            try:
                # don't convert this to _get_app - don't want the error msgs from that
                app = self.applications[app_index]
            except IndexError:
                app_str = self.UNKNOWN_APP_STR
                app = SpotlightApp([], self.bot)
            else:
                app_str = app.discord_str()

            fmt = self.QUEUE_ENTRY_FMT if not showcase else self.QUEUE_SHOWCASE_FMT
            start, end = self.format_date_range(
                date.fromtimestamp(queue_item['start']),
                date.fromtimestamp(queue_item['end'])
            )
            app_strings.append(fmt.format(
                id=app_index+1, start=start, end=end, app=app_str, app_obj=app
            ))

        return app_strings

    def format_date_range(self, start: Union[date, datetime], end: Union[date, datetime]):
        return start.strftime(self.time_formats[0]), end.strftime(self.time_formats[1])

    def sort_queue(self):
        self.queue_data = deque(sorted(self.queue_data, key=lambda o: o['start']))

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
        await self.send_embed_list(title=self.QUEUE_HEADING, contents=app_list_string)

    @queue.command(name='showcase', ignore_extra=False, pass_context=True, aliases=['s'])
    @mod_only()
    async def queue_showcase(self, ctx, *, month: NaturalDateConverter=None):
        """
        [MOD ONLY] Lists a month's queue in the showcase format.

        Arguments:
        * month: Optional. Specify the month to list applications for. Default: next month.

        Examples:
            .spotlight q s 2018-03
            .spotlight q s March 2018
        """
        logger.debug("queue showcase: {}".format(message_log_str(ctx.message)))
        self._load_applications()
        logger.info("Listing showcase queue for {0.author!s} in {0.channel!s}".format(ctx.message))
        month = month  # type: datetime

        # figure out month start/end times
        if not month:
            month = get_month_offset(datetime.utcnow(), 1)
        else:
            month = truncate(month, 'month')
        month_end = get_month_offset(month, 1)
        month_ts, month_end_ts = utctimestamp(month), utctimestamp(month_end)

        app_strings = self._get_queue_list(showcase=True)

        # filter by month
        filt_app_strings = []
        for queue_item, app_string in zip(self.queue_data, app_strings):
            if month_ts <= queue_item['start'] < month_end_ts:
                filt_app_strings.append(app_string)

        if filt_app_strings:
            app_list_string = format_list(filt_app_strings)
        else:
            app_list_string = 'Empty'
        await self.bot.say('{}\n```{}```'.format(self.QUEUE_HEADING, app_list_string))

    @queue.command(name='add', ignore_extra=False, pass_context=True, aliases=['a'])
    @mod_only()
    async def queue_add(self, ctx, *, daterange: str):
        """
        [MOD ONLY] Add a spotlight application scheduled for a given date range.

        The currently selected spotlight will be added. Use `.spotlight select` or `.spotlight roll`
        to change the currently selected spotlight.

        NOTE: KazTron will not take any action on the scheduled date. It is purely informational,
        intended for the bot operator, as well as determining the order of the queue.

        TIP: You can add the same Spotlight application to the queue multiple times (e.g. on
        different dates). To edit the date instead, use `.spotlight queue edit`.

        Arguments:
        * `daterange`: Required, string. A string in the form "date1 to date2". Each date can be
          in one of these formats:
            * An exact date: "2017-12-25", "25 December 2017", "December 25, 2017"
            * A partial date: "April 23"
            * A time expression: "tomorrow", "next week", "in 5 days". Does **not** accept days of
              the week ("next Tuesday").

        Examples:
        * `.spotlight queue add 2018-01-25 to 2018-01-26`
        * `.spotlight queue add april 3 to april 5`
        """
        logger.debug("queue add: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        try:
            dates = parse_daterange(daterange)
        except ValueError as e:
            raise commands.BadArgument(e.args[0]) from e

        try:
            app = await self._get_current()
        except IndexError:
            return  # already handled by _get_current

        queue_item = {
            'index': self.current_app_index,
            'start': utctimestamp(dates[0]),
            'end': utctimestamp(dates[1])
        }
        self.queue_data.append(queue_item)
        logger.info("queue add: added #{:d} from current select at {} to {}"
            .format(self.current_app_index + 1, dates[0].isoformat(' '), dates[1].isoformat(' ')))

        self.sort_queue()
        queue_index = self.queue_data.index(queue_item)  # find the new position now
        self._write_db()
        start, end = self.format_date_range(dates[0], dates[1])
        await self.bot.say(self.QUEUE_CHANGED_FMT.format(
            msg=self.QUEUE_ADD_HEADING,
            i=queue_index+1,
            id=queue_item['index'] + 1,
            start=start,
            end=end,
            app=app.discord_str()
        ))

    @queue.command(name='insert', pass_context=True, hidden=True, aliases=['i'])
    @mod_only()
    async def queue_insert(self, ctx):
        logger.debug("queue insert: {}".format(message_log_str(ctx.message)))
        await self.bot.say("**Error**: This command is no longer supported (>= 2.1).")

    @queue.command(name='next', ignore_extra=False, pass_context=True, aliases=['n'])
    @mod_only()
    async def queue_next(self, ctx):
        """
        [MOD ONLY] Set the next spotlight in the queue as the currently selected spotlight, and
        remove it from the queue. This is useful when a new spotlight is ready to start, as you can
        then immediately use `.spotlight showcase` to announce it publicly.
        """
        logger.debug("queue next: {}".format(message_log_str(ctx.message)))
        try:
            queue_item = self.queue_data.popleft()
        except IndexError:
            logger.warning("queue next: Queue is empty")
            await self.bot.say("**Error:** The queue is empty!")
            return

        self._load_applications()
        old_index = self.current_app_index
        self.current_app_index = queue_item['index']
        start_str, end_str = self.format_date_range(
            date.fromtimestamp(queue_item['start']),
            date.fromtimestamp(queue_item['end'])
        )
        try:
            app = await self._get_current()
        except IndexError:
            self.queue_data.appendleft(queue_item)
            self.current_app_index = old_index
            return  # get_current() already handles this
        except Exception:
            self.queue_data.appendleft(queue_item)
            self.current_app_index = old_index
            raise
        else:
            await self.send_spotlight_info(ctx.message.channel, app)
            await self.bot.say("**Scheduled for:** {} to {}".format(start_str, end_str))
            await self.send_validation_warnings(ctx, app)
            self._write_db()

    @queue.command(name='edit', ignore_extra=False, pass_context=True, aliases=['e'])
    @mod_only()
    async def queue_edit(self, ctx, queue_index: int, *, daterange: str):
        """
        [MOD ONLY] Change the scheduled date of a spotlight application in the queue.

        This command takes a QUEUE INDEX, not by spotlight number. Check the index with
        `.spotlight queue list`.

        Note: KazTron will not take any action on the scheduled date. It is purely informational,
        intended for the bot operator, as well as determining the order of the queue.

        Arguments:
        * `<queue_index>`: Required, int. The numerical position in the queue, as shown with
          `.spotlight queue list`.
        * `<daterange>`: Required, string. A string in the form "date1 to date2". Each date can be
          in one of these formats:
            * An exact date: "2017-12-25", "25 December 2017", "December 25, 2017"
            * A partial date: "April 23"
            * A time expression: "tomorrow", "next week", "in 5 days". Does **not** accept days of
              the week ("next Tuesday").

        Examples:
            `.spotlight queue edit 3 april 3 to april 6`
        """
        logger.debug("queue edit: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        # Retrieve the queue item
        if queue_index is not None:
            queue_array_index = queue_index - 1

            if not (0 <= queue_array_index < len(self.queue_data)):
                raise commands.BadArgument(
                    ("{0:d} is not a valid queue index! "
                     "Currently valid values are 1 to {1:d} inclusive.")
                    .format(queue_index, len(self.queue_data)))
        else:
            queue_array_index = -1  # last item

        queue_item = self.queue_data[queue_array_index]
        array_index = queue_item['index']
        list_index = array_index + 1  # user-facing

        # parse the daterange
        try:
            dates = parse_daterange(daterange)
        except ValueError as e:
            raise commands.BadArgument(e.args[0]) from e

        # Make the changes
        queue_item['start'] = utctimestamp(dates[0])  # same mutable object as in queue_data
        queue_item['end'] = utctimestamp(dates[1])  # same mutable object as in queue_data
        self.sort_queue()
        new_queue_index = self.queue_data.index(queue_item) + 1

        # Prepare the output
        try:
            # don't use _get_app - don't want errmsgs
            app_str = self.applications[array_index].discord_str()
        except IndexError:
            app_str = self.UNKNOWN_APP_STR
        start, end = self.format_date_range(dates[0], dates[1])

        logger.info("queue edit: changed item {:d} to dates {} to {}"
            .format(queue_index, dates[0].isoformat(' '), dates[1].isoformat(' ')))
        self._write_db()
        await self.bot.say(self.QUEUE_CHANGED_FMT.format(
            msg=self.QUEUE_EDIT_HEADING,
            i=new_queue_index,
            id=list_index,
            start=start,
            end=end,
            app=app_str
        ))

    @queue.command(name='rem', ignore_extra=False, pass_context=True, aliases=['r', 'remove'])
    @mod_only()
    async def queue_rem(self, ctx, queue_index: int=None):
        """
        [MOD ONLY] Remove a spotlight application from the queue.

        Removes by QUEUE INDEX, not by spotlight number. If no queue index is passed, removes the
        last item in the queue.

        Arguments:
        * queue_index: Optional, int. The numerical position in the queue, as shown with `.spotlight
          queue list`. If this is not provided, the last queue item will be removed.

        Examples:
            `.spotlight queue rem` - Remove the last spotlight in the queue.
            `.spotlight queue rem 3` - Remove the third spotlight in the queue.
        """
        logger.debug("queue rem: {}".format(message_log_str(ctx.message)))
        self._load_applications()

        if queue_index is not None:
            queue_array_index = queue_index - 1

            if not (0 <= queue_array_index < len(self.queue_data)):
                raise commands.BadArgument(
                    ("{0:d} is not a valid queue index! "
                     "Currently valid values are 1 to {1:d} inclusive.")
                    .format(queue_index, len(self.queue_data)))
        else:
            queue_array_index = -1  # last item

        queue_item = self.queue_data[queue_array_index]
        array_index = queue_item['index']
        list_index = array_index + 1  # user-facing

        try:
            # don't use _get_app - don't want errmsgs
            app_str = self.applications[array_index].discord_str()
        except IndexError:
            app_str = self.UNKNOWN_APP_STR
        start, end = self.format_date_range(
            date.fromtimestamp(queue_item['start']),
            date.fromtimestamp(queue_item['end'])
        )

        del self.queue_data[queue_array_index]

        logger.info("queue rem: removed index {0:d}".format(queue_index))
        self._write_db()
        await self.bot.say(self.QUEUE_CHANGED_FMT.format(
            msg=self.QUEUE_REM_HEADING,
            i=queue_index, id=list_index, start=start, end=end, app=app_str
        ))

    @list.error
    @current.error
    @roll.error
    @select.error
    @showcase.error
    @queue_list.error
    @queue_add.error
    @queue_edit.error
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
                await self.send_output(
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
                await self.send_output(
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
                await self.send_output(
                    ("[ERROR] Error sending spotlight info.\n"
                     "Original command: {}\nDiscord API error: {!s}\n\n"
                     "See logs for details").format(cmd_string, root_exc))

            else:
                await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(Spotlight(bot))
