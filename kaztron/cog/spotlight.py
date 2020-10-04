import asyncio
import random
import re
import time
import logging
from typing import List, Union, Optional
from collections import deque

import discord
from discord.ext import commands

from datetime import datetime, date, timedelta

from kaztron import KazCog, theme, task
from kaztron.driver import gsheets
from kaztron.utils.checks import mod_only, mod_or_has_role, in_channels_cfg
from kaztron.utils.converter import NaturalDateConverter
from kaztron.utils.datetime import utctimestamp, parse as dt_parse, parse_daterange, \
    get_month_offset, truncate, format_timedelta
from kaztron.utils.decorators import error_handler, natural_truncate
from kaztron.utils.discord import get_named_role, Limits, remove_role_from_all, \
    extract_user_id, user_mention, get_member, get_group_help, get_members_with_role
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str, tb_log_str, exc_log_str
from kaztron.utils.strings import format_list, split_chunks_on

logger = logging.getLogger(__name__)


class SpotlightApp:
    """
    Should only be instantiated once the bot is ready (as it attempts to retrieve user data from
    the server).
    """
    TRUNC_LEN = 3*Limits.EMBED_FIELD_VALUE
    SHORT_TRUNC_LEN = 0.5 * Limits.EMBED_FIELD_VALUE

    def __init__(self, data: List[str], bot: commands.Bot):
        self._data = data
        self.bot = bot
        self._cached_user = None
        self._is_user_cached = False

    @staticmethod
    def is_filled(str_property: str) -> bool:
        return str_property and str_property.strip().lower() != 'n/a'

    @property
    @error_handler(IndexError, datetime.utcfromtimestamp(0))
    def timestamp(self) -> datetime:
        return dt_parse(self._data[0], future=False)

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def user_name(self) -> str:
        return self._data[1].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def user_name_only(self) -> str:
        """ User name without discriminator (if provided in the field). """
        return self._data[1].split('#', maxsplit=1)[0].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def user_discriminator(self) -> str:
        """ Discriminator (the #xxxx part of an @mention in the client, if provided). """
        return self._data[1].split('#', maxsplit=1)[1].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
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
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(ValueError, "")
    @error_handler(IndexError, "")
    def user_id(self) -> str:
        return self._data[2].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def user_reddit(self) -> str:
        return self._data[3].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def project(self) -> str:
        return self._data[4].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def keywords(self) -> str:
        return self._data[5].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def favorite(self) -> str:
        return self._data[6].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def talking_point(self) -> str:
        return self._data[7].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def mature(self) -> str:
        return self._data[8].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def inspirations(self) -> str:
        return self._data[9].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def prompt(self) -> str:
        return self._data[10].strip()

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def pitch(self) -> str:
        return self._data[11].strip()

    @property
    @error_handler(IndexError, False)
    def is_nsfw(self) -> bool:
        return self._data[12].strip().lower() == 'yes'

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def nsfw_info(self) -> str:
        return self._data[13].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def art_url(self) -> str:
        return self._data[14].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def additional_info_url(self) -> str:
        return self._data[15].strip()

    @property
    @error_handler(IndexError, False)
    def is_ready(self) -> bool:
        return self._data[16].strip().lower() == 'yes'

    @property
    @natural_truncate(TRUNC_LEN)
    @error_handler(IndexError, "")
    def unnamed(self) -> str:
        return self._data[17].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def genre(self) -> str:
        return self._data[27].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def project_type(self) -> str:
        return self._data[28].strip()

    @property
    @natural_truncate(SHORT_TRUNC_LEN)
    @error_handler(IndexError, "")
    def language(self) -> str:
        return self._data[29].strip()

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
    """!kazhelp
    category: Commands
    brief: |
        Management of the {{spotlight_name}} community feature: applications, upcoming, reminders
        and timing.
    description: |
        The Spotlight cog provides functionality which manages the {{spotlight_name}} community
        feature. A number of functions are bundled in this cog:

        * Applications review and management (mod only)
        * Announcing a project in the {{spotlight_name}} channel (mod only)
        * Management of a queue of upcoming {{spotlight_name}} events (mod only)
        * Following or unfollowing {{spotlight_name}} notifications (everyone)
        * Starting a {{spotlight_name}}, timing and reminders ({{spotlight_host_name}} only)
    contents:
        - spotlight:
            - join
            - leave
            - start
            - stop
            - time
            - list
            - current
            - select
            - roll
            - showcase
            - queue:
                - list
                - showcase
                - add
                - edit
                - next
                - rem
                - insert
    """
    msg_join = \
        "You are now a part of the {0} audience. You can be pinged by the "\
        "moderators or the {1} for {0}-related news. " \
        "You can use `.spotlight leave` to leave the audience."\

    msg_join_err = \
        "Oops! You're already part of the {} audience. If you want to leave, " \
        "please use `.spotlight leave`."

    msg_leave = \
        "You are no longer part of the {0} audience. You will no longer be pinged "\
        "for {0}-related news. You can use `.spotlight join` to join the audience " \
        "again."

    msg_leave_err = \
        "Oops! You're not currently part of the {} audience. If you want to join, " \
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
    QUEUE_REMINDER = '{mention} **Upcoming {feature} Reminder** ' + QUEUE_ENTRY_FMT

    UNKNOWN_APP_STR = "Unknown - Index out of bounds"

    #
    # Config
    #

    # discord stuff
    feature_name = KazCog.config.get('spotlight', 'name')
    role_audience_name = KazCog.config.get('spotlight', 'audience_role')
    role_host_name = KazCog.config.get('spotlight', 'host_role')
    role_mods_name = KazCog.config.get('spotlight', 'mod_role')
    ch_id_spotlight = KazCog.config.get('spotlight', 'channel')

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults('spotlight', current=-1, queue=[], start_time=None, reminders=[])

        # discord stuff
        self.channel_spotlight = None

        # settings
        self.duration = self.config.get('spotlight', 'duration')
        self.reminder_offsets = self.config.get('spotlight', 'reminders')
        self.time_formats = (self.config.get('spotlight', 'start_date_format'),
                             self.config.get('spotlight', 'end_date_format'))

        # google sheet stuff
        self.user_agent = self.config.get("core", "name")
        self.gsheet_id = self.config.get("spotlight", "spreadsheet_id")
        self.gsheet_range = self.config.get("spotlight", "spreadsheet_range")
        self.applications = []
        self.applications_last_refresh = 0

        # queues
        self.current_app_index = int(self.state.get('spotlight', 'current', -1))
        # deque contains dicts with keys ('index', 'start', 'end')
        self.queue_data = deque(self.state.get('spotlight', 'queue', []))
        self.queue_reminder_offset = timedelta(
            seconds=self.config.get('spotlight', 'queue_reminder_offset')
        )

        # reminders
        st_unix = self.state.get('spotlight', 'start_time')
        self.start_time = datetime.utcfromtimestamp(st_unix) if st_unix is not None else None

        self.reminders = deque(datetime.utcfromtimestamp(t)
                               for t in self.state.get('spotlight', 'reminders', []))

    def export_kazhelp_vars(self):
        return {
            'spotlight_name': self.feature_name,
            'spotlight_host_name': self.role_host_name
        }

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
        self.state.set('spotlight', 'start_time',
            utctimestamp(self.start_time) if self.start_time is not None else None)
        self.state.set('spotlight', 'reminders',
            [utctimestamp(t) for t in self.reminders])
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

    def _upgrade_queue_v22(self):
        if self.queue_data and 'reminder_sent' not in self.queue_data[0]:
            logger.info("Upgrading queue to version 2.2")
            for queue_item in self.queue_data:
                queue_item['reminder_sent'] = False
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

        es = EmbedSplitter(color=0x80AAFF, auto_truncate=True)
        es.add_field_no_break(name="Project Name", value=app.project, inline=True)
        es.add_field(name="Author", value=author_value, inline=True)

        es.add_field(name="Elevator Pitch", value=app.pitch or "None", inline=False)

        if app.is_filled(app.mature):
            es.add_field(name="Mature & Controversial Issues", value=app.mature, inline=True)

        if app.is_filled(app.keywords):
            es.add_field(name="Keywords", value=app.keywords, inline=False)

        if app.is_filled(app.art_url):
            es.add_field_no_break(name="Project Art", value=app.art_url, inline=True)

        if app.is_filled(app.additional_info_url):
            es.add_field(name="Additional Content", value=app.additional_info_url, inline=True)

        if app.is_filled(app.genre):
            es.add_field_no_break(name="Genre", value=app.genre, inline=True)

        if app.is_filled(app.project_type):
            es.add_field_no_break(name="Type", value=app.project_type, inline=True)

        if app.is_filled(app.language):
            es.add_field(name="Language", value=app.language, inline=True)

        await self.send_message(destination, embed=es)
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
        await super().on_ready()

        self.channel_spotlight = self.get_channel(self.ch_id_spotlight)

        try:
            self.rolemanager.add_managed_role(
                role_name=self.role_audience_name,
                join_name="join",
                leave_name="leave",
                join_msg=self.msg_join.format(self.feature_name, self.role_host_name),
                leave_msg=self.msg_leave.format(self.feature_name, self.role_host_name),
                join_err=self.msg_join_err.format(self.feature_name, self.role_host_name),
                leave_err=self.msg_leave_err.format(self.feature_name, self.role_host_name),
                join_doc=("Join the {0} Audience. This allows you to be pinged by "
                          "moderators or the Host for news like "
                          "the start of a new {0} or a newly released schedule.\n\n"
                          "To leave the Audience, use `.spotlight leave`.")
                .format(self.feature_name, self.role_host_name),
                leave_doc=("Leave the {0} Audience. See `.help spotlight join` for more "
                           "information.\n\n"
                           "To join the {0} Audience, use `.spotlight join`.")
                .format(self.feature_name, self.role_host_name),
                group=self.spotlight,
                cog_instance=self,
                ignore_extra=False
            )
        except discord.ClientException:
            logger.warning("`sprint follow` command already defined - "
                           "this is OK if client reconnected")

        for role_name in (self.role_host_name, self.role_audience_name):
            get_named_role(self.server, role_name)  # raise error early if any don't exist

        # role_mods_name is optional
        try:
            get_named_role(self.server, self.role_mods_name)
        except ValueError:
            msg = "Configuration spotlight.mod_role is not valid: role '{}' not found"\
                .format(self.role_mods_name)
            logger.warning(msg)
            await self.send_output("[Warning] " + msg)

        # convert queue from previous versions
        self._upgrade_queue_v21()
        self._upgrade_queue_v22()

        # get spotlight applications - mostly to verify the connection
        self._load_applications()

        # start reminders tasks
        self._schedule_reminders()
        self._schedule_upcoming_reminder()

    @commands.group(invoke_without_command=True, pass_context=True)
    async def spotlight(self, ctx):
        """!kazhelp
        brief: "{{spotlight_name}} commands group. See sub-commands."
        description: |
            {{spotlight_name}} commands group. See sub-commands.

            TIP: For convenience, most sub-commands support a single-letter shorthand. Check each
            command's Usage section.
        """
        await self.bot.say(get_group_help(ctx))

    @spotlight.command(pass_context=True, ignore_extra=False, aliases=['l'])
    @mod_only()
    async def list(self, ctx):
        """!kazhelp
        description: List all the {{spotlight_name}} applications in summary form.
        """
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
        """!kazhelp
        description: |
            Show the currently selected application.

            The "current application" is selected by {{!spotlight roll}} or {{!spotlight select}},
            and is the application used by {{!spotlight showcase}} and {{!spotlight queue add}}.
        """
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
        """!kazhelp
        description: |
            Select a {{spotlight_name}} application at random, and set it as the currently selected
            application. Only applications that are marked 'ready for Spotlight' will be selected.
        """
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
        """!kazhelp
        description: Set the currently selected application.
        parameters:
            - name: list_index
              optional: false
              type: number
              description: The numerical index of an application, as shown by {{!spotlight list}}.
        examples:
            - command: .spotlight set 5
              description: Set the current application to entry #5.
        """
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
        """!kazhelp

        brief: Announce the next {{spotlight_name}} from the currently selected application.
        description: Announce the next {{spotlight_name}} from the currently selected application
            in the configured public {{spotlight_name}} channel. Also switches the
            {{spotlight_host_name}}  role to the applicant (if a valid user).
        """

        # Retrieve and showcase the app
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
            "**{0}** {2}\n\n"
            "Our next host is {1.user_disp}, presenting their project, *{1.project}*!\n\n"
            "Welcome, {1.user_disp}!".format(
                self.feature_name.upper(),
                current_app,
                role.mention if role else ""
            )
        )
        await self.send_spotlight_info(self.channel_spotlight, current_app)
        await self.bot.say("Application showcased: {} ({}) - {}"
            .format(current_app.user_disp, current_app.user_name_only, current_app.project)
        )
        await self.send_validation_warnings(ctx, current_app)

        # remove host role
        host_role = get_named_role(self.server, self.role_host_name)
        await remove_role_from_all(self.bot, self.server, host_role)

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
        """!kazhelp
        description: Command group containing subcommands that allow managing the queue of upcoming
            {{spotlight_name}} events. See sub-commands for more information.
        """
        await self.bot.say(get_group_help(ctx))

    def _get_queue_list(self, showcase=False):
        app_strings = []
        for queue_item in self.queue_data:
            app_index = queue_item['index']
            try:
                # don't convert this to _get_app - don't want the error msgs from that
                app = self.applications[app_index]
            except IndexError:
                # app_str for non-showcase, app's data for showcase format
                app_str = self.UNKNOWN_APP_STR
                app = SpotlightApp(["", "Unknown", "", "", app_str], self.bot)
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
        """!kazhelp
        description: |
            Lists the current queue of upcoming {{spotlight_name}} events.

            The queue is always ordered chronologically. If two queue items have the exact same
            date, the order between them is undefined.
        """
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
        """!kazhelp
        brief: Lists the queued {{spotlight_name}} events for a given month.
        description: |
            Lists the queued {{spotlight_name}} events for a given month. This is sent as markdown
            in a code block, suitable for copy-pasting so that a mod can use it to prepare an
            announcement.
        parameters:
            - name: month
              optional: true
              type: date
              default: next month
              description: The month for which to list queued applications.
        examples:
            - command: .spotlight q s 2018-03
            - command: .spotlight q s March 2018
        """
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
        """!kazhelp
        description: |
            Add a {{spotlight_name}} application scheduled for a given date range.

            The currently selected application will be added. Use {{!spotlight select}} or
            {{!spotlight roll}} to change the currently selected application.
        details: |
            NOTE: {{name}} will not take any action on the scheduled date. The date is used to order
            the queue and as an informational tool to the moderators responsible for the
            {{spotlight_name}}.

            TIP: You can add the same {{spotlight_name}} application to the queue multiple times
            (e.g. on different dates). To edit the date instead, use {{!spotlight queue edit}}.
        parameters:
            - name: daterange
              optional: false
              type: string
              description: |
                    A string in the form of `date1 to date2`. Each of the two dates can be in any
                    of these formats:

                    * An exact date: `2017-12-25`, `25 December 2017`, `December 25, 2017`.
                    * A partial date: `April 23` (nearest future date)
                    * A time expression: `tomorrow`, `next week`, `in 5 days`. You **cannot** use
                      days of the week (e.g. "next Tuesday").
        examples:
            - command: .spotlight queue add 2018-01-25 to 2018-01-26
            - command: .spotlight queue add april 3 to april 5
        """
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
            'end': utctimestamp(dates[1]),
            'reminder_sent': False
        }
        self.queue_data.append(queue_item)
        logger.info("queue add: added #{:d} from current select at {} to {}"
            .format(self.current_app_index + 1, dates[0].isoformat(' '), dates[1].isoformat(' ')))

        self.sort_queue()
        queue_index = self.queue_data.index(queue_item)  # find the new position now
        self._write_db()
        self._schedule_upcoming_reminder()
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
        """!kazhelp
        description: "**Unsupported** as of v2.1."
        """
        await self.bot.say("**Error**: This command is no longer supported (>= 2.1).")

    @queue.command(name='next', ignore_extra=False, pass_context=True, aliases=['n'])
    @mod_only()
    async def queue_next(self, ctx):
        """!kazhelp
        brief: "Pop the next {{spotlight_name}} in the queue."
        description: |
            Pop the next {{spotlight_name}} in the queue and set it as the currently selected
            application. This is a useful shortcut to announce the next {{spotlight_name}} in queue,
            and is usually followed by a call to {{!spotlight showcase}}.
        """
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
            self._schedule_upcoming_reminder()

    @queue.command(name='edit', ignore_extra=False, pass_context=True, aliases=['e'])
    @mod_only()
    async def queue_edit(self, ctx, queue_index: int, *, daterange: str):
        """!kazhelp
        description: |
            Change the scheduled date of a {{spotlight_name}} in the queue.

            IMPORTANT: This command takes a **queue index**, as shown by {{!spotlight queue list}}.
        details: |
            NOTE: {{name}} will not take any action on the scheduled date. The date is used to order
            the queue and as an informational tool to the moderators responsible for the
            {{spotlight_name}}.
        parameters:
            - name: queue_index
              type: number
              optional: false
              description: The queue position to edit, as shown with {{!spotlight queue list}}.
            - name: daterange
              type: string
              optional: false
              description: A daterange in the form `date1 to date2`. The same kind of dates are
                accepted as for {{!spotlight queue add}}.
        examples:
            - command: .spotlight queue edit 3 april 3 to april 6
        """
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
        self._schedule_upcoming_reminder()
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
        """!kazhelp
        description: |
            Remove a {{spotlight_name}} application from the queue.

            IMPORTANT: This command takes a **queue index**, as shown by {{!spotlight queue list}}.
        parameters:
            - name: queue_index
              optional: true
              type: number
              description: The queue position to remove, as shown with {{!spotlight queue list}}.
                If not specified, then the last item in the queue is removed.
        examples:
            - command: .spotlight queue rem
              description: Remove the last spotlight in the queue.
            - command: .spotlight queue rem 3
              description: Remove the third spotlight in the queue.
        """
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
        self._schedule_upcoming_reminder()
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

    def _get_next_reminder(self):
        for queue_item in self.queue_data:
            if not queue_item['reminder_sent']:
                return queue_item
        else:  # no future item found
            return None

    def _schedule_upcoming_reminder(self):
        async def inner():
            logger.debug("Waiting on task_upcoming_reminder to finish cancelling...")
            await self.scheduler.wait_all(self.task_upcoming_reminder)
            logger.debug("Done, scheduling next reminder...")
            queue_item = self._get_next_reminder()
            if queue_item is not None:
                start_time = datetime.utcfromtimestamp(queue_item['start'])
                reminder_time = start_time - self.queue_reminder_offset
                self.scheduler.schedule_task_at(self.task_upcoming_reminder, reminder_time)

        self.scheduler.cancel_all(self.task_upcoming_reminder)
        asyncio.get_event_loop().create_task(inner())

    @task(is_unique=True)
    async def task_upcoming_reminder(self):
        queue_item = self._get_next_reminder()
        if not queue_item:
            logger.warning("task_upcoming_reminder: no future queue items to remind")
            await self.send_output("**Spotlight queue reminder failed**: no future queue items!")
            return

        array_index = queue_item['index']
        list_index = array_index + 1  # user-facing

        # Prepare the output
        self._load_applications()
        try:
            # don't use _get_app - don't want errmsgs
            app_str = self.applications[array_index].discord_str()
        except IndexError:
            app_str = self.UNKNOWN_APP_STR
        start_str, end_str = self.format_date_range(
            date.fromtimestamp(queue_item['start']),
            date.fromtimestamp(queue_item['end'])
        )
        mod_mention = get_named_role(self.server, self.role_mods_name).mention \
            if self.role_mods_name else ""

        await self.send_output(self.QUEUE_REMINDER.format(
            feature=self.feature_name, mention=mod_mention, id=list_index,
            start=start_str, end=end_str, app=app_str
        ))

        queue_item['reminder_sent'] = True
        self._write_db()
        self._schedule_upcoming_reminder()

    def get_host(self) -> Optional[discord.Member]:
        host_role = get_named_role(self.server, self.role_host_name)
        try:
            return get_members_with_role(self.server, host_role)[0]
        except IndexError:
            logger.warning("Cannot find user with host role!")
            return None

    @spotlight.command(ignore_extra=False, pass_context=True)
    @in_channels_cfg('spotlight', 'channel')
    @mod_or_has_role(role_host_name)
    async def start(self, ctx: commands.Context):
        """!kazhelp
        description: |
            Start the {{spotlight_name}}. For use by the {{spotlight_host_name}}.

            {{name}} will announce the start of your {{spotlight_name}} and start counting down
            your remaining time. You will get periodic reminders about the time remaining, as well
            as an announcement about the end of your {{spotlight_name}}.

            You can stop the {{spotlight_name}} early by calling {{!spotlight stop}}.
        """
        if self.start_time is not None:
            raise commands.UserInputError("The spotlight has already started! "
                                          "Use `.spotlight stop` to end it early.")

        host = self.get_host()
        host_mention = host.mention if host is not None else "<Error: Cannot find host>"
        audience_mention = get_named_role(self.server, self.role_audience_name).mention
        mod_mention = get_named_role(self.server, self.role_mods_name).mention \
            if self.role_mods_name else ""
        duration_s = format_timedelta(timedelta(seconds=self.duration), timespec="minutes")

        if host:
            msg = ("**{1}'s {0} is now starting!** It will last {3}. " 
                   "The host can use `.spotlight stop` to end it early. {2}").format(
                self.feature_name, host_mention, audience_mention, duration_s
            )
            await self.bot.send_message(self.channel_spotlight, msg)
            await self.send_output("{3} **{1}'s {0} has started.**"
                .format(self.feature_name, host_mention, audience_mention, mod_mention))

            self._start_spotlight()
        else:
            await self.send_output("{0} **Error** Cannot start spotlight: cannot find host!"
                .format(mod_mention))

        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            logger.warning("Cannot delete invoking message: Forbidden")

    @spotlight.command(ignore_extra=False, pass_context=True)
    @in_channels_cfg('spotlight', 'channel')
    @mod_or_has_role(role_host_name)
    async def stop(self, ctx: commands.Context):
        """!kazhelp
        description: Stop an ongoing {{spotlight_name}} previously started with
            {{!spotlight start}}.
        """
        if self.start_time is None:
            raise commands.UserInputError("The spotlight has not yet started! "
                                          "Use `.spotlight start` to start it.")

        await self._send_end(stop=True)
        self._stop_spotlight()

        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            logger.warning("Cannot delete invoking message: Forbidden")

    @spotlight.command(ignore_extra=False, pass_context=True)
    @in_channels_cfg('spotlight', 'channel')
    async def time(self, ctx: commands.Context):
        """!kazhelp
        description: Check the remaining time for the current {{spotlight_name}}.
        """
        host = self.get_host()
        host_name = host.nick if host.nick else host.name

        if self.start_time is None:
            msg = "{1}'s {0} hasn't started yet!".format(self.feature_name, host_name)
        else:
            elapsed = datetime.utcnow() - self.start_time
            remaining = timedelta(seconds=self.duration) - elapsed
            elapsed_s = format_timedelta(elapsed, timespec="minutes")
            rem_s = format_timedelta(remaining, timespec="minutes")

            msg = "{2} have passed for {1}'s {0}! {3} remain." \
                .format(self.feature_name, host_name, elapsed_s, rem_s)

        await self.bot.send_message(ctx.message.channel, msg)

    @task(is_unique=False)
    async def task_send_reminder(self):
        host = self.get_host()
        host_mention = host.mention if host else "<Error: Cannot find host>"
        elapsed = self.reminders.popleft() - self.start_time
        remaining = timedelta(seconds=self.duration) - elapsed
        elapsed_s = format_timedelta(elapsed, timespec="minutes")
        rem_s = format_timedelta(remaining, timespec="minutes")

        logger.info("Sending reminder: {:.3f} elapsed".format(elapsed.total_seconds()))
        msg = "**{0} Reminder**: {2} have passed for {1}'s {0}! {3} remain." \
            .format(self.feature_name, host_mention, elapsed_s, rem_s)
        await self.bot.send_message(self.channel_spotlight, msg)

        self._write_db()

    @task(is_unique=True)
    async def task_end_spotlight(self):
        logger.info("Spotlight has ended. Sending notification and cleaning up.")
        await self._send_end()
        self._stop_spotlight()

    def _start_spotlight(self):
        self.start_time = datetime.utcnow()
        self.reminders = deque(self.start_time + timedelta(seconds=offset)
                               for offset in self.reminder_offsets)
        self._schedule_reminders()

    def _schedule_reminders(self):
        """
        Schedule reminders in ``self.reminders`` as well as the end of the sprint. If the current
        sprint has not been started, does nothing.
        """
        scheduled_tasks = self.scheduler.get_instances(self.task_send_reminder) +\
                          self.scheduler.get_instances(self.task_end_spotlight)
        if self.start_time is not None and not scheduled_tasks:
            for r_dt in self.reminders:
                self.scheduler.schedule_task_at(self.task_send_reminder, r_dt)
            end_time = self.start_time + timedelta(seconds=self.duration)
            self.scheduler.schedule_task_at(self.task_end_spotlight, end_time)

    def _stop_spotlight(self):
        self.start_time = None
        self.reminders = deque()
        self.scheduler.cancel_all(self.task_send_reminder)
        self.scheduler.cancel_all(self.task_end_spotlight)
        self._write_db()

    async def _send_end(self, stop=False):
        host = self.get_host()
        host_mention = host.mention if host else "<Error: Cannot find host>"
        audience_mention = get_named_role(self.server, self.role_audience_name).mention
        mod_mention = get_named_role(self.server, self.role_mods_name).mention \
            if self.role_mods_name else ""

        if not stop:
            msg = ("**{1}'s {0} is now ending!** "
                   "Please finish any last questions and wrap up the {0}. {2}") \
                .format(self.feature_name, host_mention, audience_mention)
            log_msg = "{3} **{1}'s {0} has ended.**" \
                .format(self.feature_name, host_mention, audience_mention, mod_mention)
        else:
            msg = "**{1}'s {0} has been stopped!** {2}" \
                .format(self.feature_name, host_mention, audience_mention)
            log_msg = "{3} **{1}'s {0} has ended (stop command).**" \
                .format(self.feature_name, host_mention, audience_mention, mod_mention)

        await self.bot.send_message(self.channel_spotlight, msg)
        await self.send_output(log_msg)

        logger.info("Removing host role")
        host_role = get_named_role(self.server, self.role_host_name)
        try:
            for m in get_members_with_role(self.server, host_role):
                await self.bot.remove_roles(m, host_role)
        except discord.HTTPException as e:
            logger.exception("While trying to remove host role, an exception occurred")
            await self.send_output("While trying to remove spotlight host role, "
                                   "an exception occurred: " + exc_log_str(e))


def setup(bot):
    bot.add_cog(Spotlight(bot))
