import logging
from typing import Sequence, Dict

import discord
from discord.ext import commands
from discord.ext.commands import UserInputError
from sqlalchemy import orm
from datetime import datetime, timedelta

from kaztron import KazCog, task
from kaztron.driver.pagination import Pagination
from kaztron.theme import solarized
from kaztron.utils.checks import mod_only, mod_channels, in_channels
from kaztron.utils.converter import MemberConverter2, NaturalDateConverter, BooleanConverter, \
    NaturalInteger
from kaztron.utils.discord import Limits, get_group_help, user_mention, get_named_role, check_mod
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.datetime import format_datetime, format_date

from kaztron.cog.blots import model
from kaztron.cog.blots.controller import CheckInController, MilestoneInfo, BlotsConfig
from kaztron.utils.strings import split_chunks_on

logger = logging.getLogger(__name__)


class CheckInManager(KazCog):
    """!kazhelp
    brief: Manage check-ins for Inkblood's BLOTS programme.
    description: |
        This module allows {{name}} to manage user check-ins for Inkblood's BLOTS programme, and
        provides tools to help moderators oversee this programme.

        Check-ins are **only** allowed from {{checkin_window_start}} to {{checkin_window_end}},
        unless you are a mod or a member of the following roles: {{checkin_anytime_roles}}. The
        start and end of the checkin window are announced in the channel.
    contents:
        - checkin:
            - type
            - list
            - report
            - query
            - exempt
        - milestone:
            - report
            - update
    """
    cog_config: BlotsConfig

    ITEMS_PER_PAGE = 12
    EMBED_COLOR = solarized.yellow
    PROJECT_UNIT_MAP = {
        model.ProjectType.script: "pages (script)",
        model.ProjectType.visual: "pages (visual)",
        model.ProjectType.words: "words"
    }

    check_in_channel_id = KazCog.config.blots.check_in_channel
    test_channel_id = KazCog.config.discord.channel_test

    def __init__(self, bot):
        super().__init__(bot, 'blots', BlotsConfig)
        self.cog_config.set_defaults(milestone_map={})
        self.c = None  # type: CheckInController
        self.checkin_anytime_roles = []
        self.check_in_channel = None
        self.announce_tasks = []

    def export_kazhelp_vars(self):
        import calendar
        window = self.c.get_check_in_window(datetime.utcnow())
        return {
            'checkin_window_start': "{} {}".format(
                calendar.day_name[window[0].weekday()],
                self.c.checkin_time.strftime('%H:%M') + ' UTC'
            ),
            'checkin_window_end': "{} {}".format(
                calendar.day_name[window[1].weekday()],
                self.c.checkin_time.strftime('%H:%M') + ' UTC'
            ),
            'checkin_anytime_roles': ', '.join(r.name for r in self.checkin_anytime_roles)
        }

    async def on_ready(self):
        await super().on_ready()
        self.check_in_channel = self.validate_channel(self.check_in_channel_id)
        self.checkin_anytime_roles = tuple(get_named_role(self.server, n)
                                           for n in self.cog_config.check_in_window_exempt_roles)
        milestone_map = {}
        for pt, ms_map in self.cog_config.milestone_map.items():
            milestone_map[model.ProjectType[pt]] = {get_named_role(self.server, r): v
                                                    for r, v in ms_map.items()}
        self.c = CheckInController(self.server, self.cog_config, milestone_map)
        await self.schedule_checkin_announcements()

    async def schedule_checkin_announcements(self):
        if not self.announce_tasks:
            window = self.c.get_check_in_window(datetime.utcnow())
            self.announce_tasks.append(self.scheduler.schedule_task_at(
                self.announce_start, window[0], every=timedelta(days=7)
            ))
            self.announce_tasks.append(self.scheduler.schedule_task_at(
                self.announce_end, window[1], every=timedelta(days=7)
            ))

    @task(is_unique=True)
    async def announce_start(self):
        logger.info("Announcing start of check-in window")
        await self.bot.send_message(self.check_in_channel,
            "~\n" + ("^" * 32) + "\n**Check-ins for this week are now OPEN!**")

    @task(is_unique=True)
    async def announce_end(self):
        logger.info("Announcing end of check-in window")
        await self.bot.send_message(self.check_in_channel,
            "~\n**Check-ins for this week are now CLOSED!**\n" + ("=" * 32))

    async def send_check_in_list(self,
                               dest: discord.Channel,
                               check_ins: Pagination,
                               member: discord.Member):

        es = EmbedSplitter(
            auto_truncate=True,
            title="Check-in list",
            description=member.mention,
            colour=self.EMBED_COLOR
        )
        es.set_footer(text="Page {:d}/{:d}".format(check_ins.page + 1, check_ins.total_pages))

        for check_in in check_ins:  # type: model.CheckIn
            f_name = format_datetime(check_in.timestamp)
            f_message = '{}\n*{:d} {}* – {}\n\\_\\_\\_'.format(
                member.mention,
                check_in.word_count,
                self.PROJECT_UNIT_MAP[check_in.project_type],
                check_in.message
            )
            es.add_field(name=f_name, value=f_message, inline=False)

        for em in es.finalize():
            await self.bot.send_message(dest, embed=em)

    @commands.group(name="checkin", pass_context=True, invoke_without_command=True)
    @in_channels([check_in_channel_id])
    async def check_in(self, ctx: commands.Context, word_count: NaturalInteger, *, message: str):
        """!kazhelp
        brief: BLOTS weekly check-in.
        description: |
            BLOTS weekly check-in.

            Enter your **total** word (or page) count and a brief update message.

            If your project type is "words", enter your word_count in words (total). If your project
            type is "visual" or "script", enter your total number of pages instead. See also
            {{!checkin type}}.

            Check-ins are **only** allowed from {{checkin_window_start}} to {{checkin_window_end}},
            unless you are a mod or a member of the following roles: {{checkin_anytime_roles}}. The
            start and end of the checkin window are announced in the channel.
        parameters:
            - name: word_count
              type: number
              description: Your total word count (or total pages, depending on set project type).
                Do **not** include the word 'words' or 'pages'.
            - name: message
              type: string
              description: Your progress update. Maximum length 1000 characters.
        examples:
            - command: ".checkin 304882 Finished chapter 82 and developed some of the social and
                economic fallout of the Potato Battle of 1912."
        """

        # check if allowed to checkin at the current time
        msg_time = ctx.message.timestamp
        window = self.c.get_check_in_window(msg_time)
        is_in_window = window[0] <= msg_time <= window[1]
        is_anytime = set(ctx.message.author.roles) & set(self.checkin_anytime_roles)

        if not check_mod(ctx) and not is_in_window and not is_anytime:
            import calendar
            window_name = "from {0} {2} to {1} {2}".format(
                calendar.day_name[window[0].weekday()],
                calendar.day_name[window[1].weekday()],
                self.c.checkin_time.strftime('%H:%M') + ' UTC'
            )
            raise UserInputError(
                "**You cannot check-in right now!** Check-ins are {}. Need help? Ask us in #meta!"
                .format(window_name)
            )

        # validate argument
        word_count = word_count  # type: int  # for IDE type checking
        if word_count < 0:
            raise commands.BadArgument("word_count must be greater than 0.")
        if not message:
            raise commands.BadArgument("Check-in message is required.")

        # store the checkin
        check_in = self.c.save_check_in(
            member=ctx.message.author,
            word_count=word_count,
            message=message,
            timestamp=ctx.message.timestamp
        )
        start, end = self.c.get_check_in_week(ctx.message.timestamp)
        await self.bot.say(
            "{} Check-in for {:d} {} recorded for the week of {} to {}. Thanks!".format(
                ctx.message.author.mention,
                check_in.word_count, self.PROJECT_UNIT_MAP[check_in.project_type],
                format_date(start), format_date(end))
        )

    @check_in.command(name="type", pass_context=True, ignore_extra=False)
    @in_channels([check_in_channel_id, test_channel_id])
    async def check_in_type(self, ctx: commands.Context, project_type: str=None):
        """!kazhelp
        description: |
            Check or set project type for check-ins.

            If no argument is provided, checks your project type. If an argument is provided, sets
            the project type to the specified value.

            This command determines the unit for the word_count you enter when you check in. If your
            project type is "words" (the default), enter it in words. If your project type is
            "visual" or "script", enter it in pages. See also {{!checkin}}.
        parameters:
            - name: project_type
              optional: true
              type: "`words`, `visual` or `script`"
              description: The project type to change to.
        examples:
            - command: .checkin type
              description: Check your current project type.
            - command: .checkin type script
              description: Set your project type to script.
        """
        if project_type:  # set
            try:
                project_type_e = model.ProjectType[project_type]
            except KeyError:
                raise commands.BadArgument("Invalid project_type {!r} (must be one of {})"
                    .format(project_type, ', '.join([e for e in model.ProjectType.__members__])))
            self.c.set_user_type(ctx.message.author, project_type_e)
            await self.bot.say("{} Your project type has been changed to {}"
                .format(ctx.message.author.mention, project_type_e.name))
        else:  # get
            user = self.c.get_user(ctx.message.author)
            await self.bot.say("{} Your current project type is {}"
                         .format(ctx.message.author.mention, user.project_type.name))

    @check_in.command(name='list', pass_context=True, ignore_extra=False)
    @in_channels([check_in_channel_id, test_channel_id])
    async def check_in_list(self, ctx: commands.Context, page: int=None):
        """!kazhelp
        description: |
            Check your list of check-ins.

            The result is always PMed to you.

            Moderators can query any user's checkins with {{!checkin query}} instead.
        parameters:
            - name: page
              type: number
              optional: true
              description: The page number to access, if a user has more than 1 page of badges.
              default: last page (most recent)
        examples:
            - command: .checkin list
              description: List all your check-ins (last page if multiple pages).
            - command: .checkin list 4
              description: List the 4th page of check-ins.
        """
        try:
            db_records = self.c.query_check_ins(member=ctx.message.author)
            paginator = Pagination(db_records, self.ITEMS_PER_PAGE, align_end=True)
            if page is not None:
                paginator.page = max(0, min(paginator.total_pages - 1, page-1))
            await self.send_check_in_list(ctx.message.author, paginator, ctx.message.author)
        except orm.exc.NoResultFound:
            await self.bot.say("{} You haven't checked in yet!".format(ctx.message.author.mention))

    @check_in.command(name='query', pass_context=True, ignore_extra=False)
    @mod_only()
    async def check_in_query(self, ctx: commands.Context, user: MemberConverter2, page: int=None):
        """!kazhelp
        description: |
            Query a user's list of check-ins.

            This is the moderator's version of {{!checkin list}}.
        parameters:
            - name: user
              type: "@mention"
              description: The user to check (as an @mention or a Discord ID).
            - name: page
              type: number
              optional: true
              description: The page number to access, if a user has more than 1 page of badges.
              default: last page (most recent)
        examples:
            - command: .checkin query @JaneDoe
              description: List all check-ins by JaneDoe (last page if multiple pages).
            - command: .checkin query @JaneDoe 4
              description: List the 4th page of check-ins by JaneDoe.
        """
        member = user  # type: discord.Member  # just for type checking
        try:
            db_records = self.c.query_check_ins(member=member)
            paginator = Pagination(db_records, self.ITEMS_PER_PAGE, align_end=True)
            if page is not None:
                paginator.page = max(0, min(paginator.total_pages - 1, page-1))
            await self.send_check_in_list(ctx.message.channel, paginator, member)
        except orm.exc.NoResultFound:
            await self.bot.say("{} has not checked in yet.".format(member.mention))

    @check_in.command(name='report', pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def check_in_report(self, ctx: commands.Context, *, datespec: NaturalDateConverter=None):
        """!kazhelp
        description: "Get a report of who has or has not checked in in a given week."
        parameters:
            - name: datespec
              type: datespec
              optional: true
              default: 'last week ("7 days ago")'
              description: A date in any unambiguous format (2018-03-14, March 14 2018,
                  14 March 2018, today, 1 month ago, etc.). The report will be for the check-in week
                  that includes this date.
        examples:
            - command: .checkin report
              description: Get a report for last week.
            - command: .checkin report 2018-04-18
              description: Get a report for the week that includes 18 April 2018.
        """
        if not datespec:
            datespec = datetime.utcnow() - timedelta(days=7)

        start, end = self.c.get_check_in_week(datespec)
        week_str = "the week from {} to {}".format(format_datetime(start), format_datetime(end))
        try:
            ci, nci = self.c.generate_check_in_report(datespec)  # checked in, not checked in
        except orm.exc.NoResultFound:
            await self.bot.say("No check-ins for {}.".format(week_str))
            return

        #
        # determine sorting order of each list
        #

        # checked in: by name
        ci_users = list(ci.keys())
        ci_users.sort(key=lambda u: u.nick.lower() if u.nick else u.name.lower())

        # not checked in: by last checkin date pre-reporting week
        nci_users = list(nci.keys())
        epoch = datetime(1970, 1, 1)
        nci_users.sort(key=lambda u: nci[u].timestamp if nci.get(u, None) else epoch, reverse=True)

        #
        # Prepare display
        #

        # format strings for display
        ci_list_str = '\n'.join(
            "{0} ({1} - *{2:d} {3}*)".format(
                u.mention,
                format_datetime(ci[u].timestamp),
                ci[u].word_count,
                self.PROJECT_UNIT_MAP[ci[u].project_type]
            ) for u in ci_users
        )
        nci_list_str = '\n'.join(
            "{0} (last: {1})".format(
                u.mention, format_date(nci[u].timestamp) if nci.get(u, None) else 'Never'
            ) for u in nci_users
        )

        # Prepare the overall embed
        es = EmbedSplitter(
            title="Check-In Report",
            colour=solarized.green,
            description="Report for " + week_str,
            timestamp=datetime.utcnow(),
            repeat_header=True,
            auto_truncate=True
        )
        es.set_footer(text="Generated: ")
        if len(ci_list_str) < Limits.EMBED_FIELD_VALUE:
            es.add_field(name="Checked in", value=ci_list_str or 'Nobody', inline=False)
        else:
            es.add_field(
                name="Checked in",
                value="{:d} users (list too long)".format(len(ci_users)),
                inline=False
            )

        es.add_field(name="Did NOT check in", value=nci_list_str, inline=False)
        await self.send_message(ctx.message.channel, embed=es)

    @check_in.command(name='delta', pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def check_in_delta(self, ctx: commands.Context, *, datespec: NaturalDateConverter=None):
        """!kazhelp
        description: "Get a report of wordcount changes in a given check-in week, compared to
            previous check-in."
        parameters:
            - name: datespec
              type: datespec
              optional: true
              default: 'last week ("7 days ago")'
              description: A date in any unambiguous format (2018-03-14, March 14 2018,
                  14 March 2018, today, 1 month ago, etc.). The report will be for the check-in week
                  that includes this date.
        examples:
            - command: .checkin delta
              description: Get a report for last week.
            - command: .checkin delta 2018-04-18
              description: Get a report for the week that includes 18 April 2018.
        """
        if not datespec:
            datespec = datetime.utcnow() - timedelta(days=7)

        start, end = self.c.get_check_in_week(datespec)
        week_str = "the week from {} to {}".format(format_datetime(start), format_datetime(end))
        try:
            report, ci_map = self.c.generate_check_in_deltas(datespec)
        except orm.exc.NoResultFound:
            await self.bot.say("No check-ins for {}.".format(week_str))
            return

        # sort descending by diff value
        s_users = list(report.keys())
        s_users.sort(key=lambda u: report[u] if report.get(u, None)
                     else float('-inf'), reverse=True)

        # Prepare display
        delta_strings = []
        for u in s_users:
            if report[u] is not None:
                unit = self.PROJECT_UNIT_MAP[ci_map[u].project_type] if ci_map.get(u, None) \
                    else 'words'
                delta_strings.append(
                    "{0} ({1:+d} {3} - *total {2:d} {3}*)".format(
                        u.mention,
                        report[u],
                        ci_map[u].word_count if ci_map.get(u, None) else 0,
                        unit
                    )
                )
            else:
                delta_strings.append("{0} (no check-in)".format(u.mention))
        delta_list_str = '\n'.join(delta_strings)

        # Prepare the overall embed
        es = EmbedSplitter(
            title="User Progress Report",
            colour=solarized.cyan,
            description="Report for " + week_str + '\n\n',
            timestamp=datetime.utcnow(),
            repeat_header=True,
            auto_truncate=True
        )
        es.set_footer(text="Generated: ")
        es.add_field(name="_", value=delta_list_str, inline=False)
        await self.send_message(ctx.message.channel, embed=es)

    @check_in.command(name='exempt', pass_context=True, ignore_extra=True)
    @mod_only()
    @mod_channels()
    async def checkin_exempt(self,
                             ctx: commands.Context,
                             user: MemberConverter2=None,
                             val: BooleanConverter=None):
        """!kazhelp
        description: |
            Check or set exemptions from check-ins.

            Users who are exempt from check-ins will not appear in a {{!checkin report}}.
        parameters:
            - name: user
              type: "@mention"
              optional: true
              description: The user to check (as an @mention or a Discord ID).
            - name: val
              type: '"yes" or "no"'
              optional: true
              description: "If not specified, check a user's exemption status. If specified, change
                that user's exemption status."
        examples:
            - command: .checkin exempt
              description: Get a list of exempt users.
            - command: .checkin exempt @JaneDoe
              description: Check if JaneDoe is exempt from check-ins.
            - command: .checkin exempt @JaneDoe yes
              description: Set JaneDoe as exempt from check-ins.
        """
        self.c.cleanup_exempt(self.server)
        if user is None:
            exempt_users = self.c.get_exempt_users()
            if exempt_users:
                full_msg = "**Exempt from check-ins**\n{}"\
                    .format('\n'.join(user_mention(u.discord_id) for u in exempt_users))
            else:
                full_msg = "**No users are exempt from check-ins.**"
            for msg in split_chunks_on(full_msg, Limits.MESSAGE):
                await self.bot.say(msg[:Limits.MESSAGE])
        elif val is None:
            member_ = user  # type: discord.Member  # IDE type detection
            if self.c.get_user(member_).is_exempt:
                await self.bot.say("{} is **exempt** from check-ins.".format(member_.mention))
            else:
                await self.bot.say("{} is **not** exempt from check-ins.".format(member_.mention))
        else:
            member_ = user  # type: discord.Member  # IDE type detection
            self.c.set_user_exempt(member_, val)
            await self.bot.say("{} has been set {} from check-ins."
                .format(member_.mention, "**exempt**" if val else "**not** exempt"))

    @commands.group(pass_context=True, ignore_extra=True, invoke_without_command=True)
    @mod_only()
    @mod_channels()
    async def milestone(self, ctx: commands.Context):
        """!kazhelp
        description: Command group for milestone management tools.
        """
        await self.bot.say(get_group_help(ctx))

    @milestone.command(name='report', pass_context=True, ignore_extra=True)
    @mod_only()
    @mod_channels()
    async def milestone_report(self, ctx: commands.Context):
        """!kazhelp
        description: Give a report of each user's current milestone roles compared to their last
            check-in.
        """
        report = self.c.generate_milestone_report()
        es = EmbedSplitter(
            title="Milestone Updates Required",
            colour=solarized.yellow,
            timestamp=datetime.utcnow(),
            repeat_header=True,
            auto_truncate=True
        )
        es.set_footer(text="Generated: ")

        for role, ms_info_list in report.items():
            if role is not None:
                changed_milestone_list = [m for m in ms_info_list if m.milestone_changed]
                es.add_field(
                    name=role.name,
                    value=self._ms_report_list_users(changed_milestone_list) or 'None',
                    inline=False
                )
            else:
                es.add_field(
                    name="No Check-Ins",
                    value=self._ms_report_list_users(ms_info_list) or 'None'
                )
        await self.send_message(ctx.message.channel, embed=es)

    def _ms_report_list_users(self, ms_info_list: Sequence[MilestoneInfo]) -> str:
        list_str = []
        for ms_info in ms_info_list:
            u = ms_info.user.mention
            if ms_info.check_in is not None:
                wc = ms_info.check_in.word_count
                wu = self.PROJECT_UNIT_MAP[ms_info.check_in.project_type]
            else:
                wc = 0
                wu = self.PROJECT_UNIT_MAP[self.c.get_user(ms_info.user).project_type]
            rl = ', '.join(r.name for r in ms_info.current_roles) or 'No milestone roles'
            list_str.append('{} {:d} {} (currently: {})'.format(u, wc, wu, rl))
        return '\n'.join(list_str)

    @milestone.group(name='update', pass_context=True, ignore_extra=False)
    @mod_only()
    async def milestone_update(self, ctx: commands.Context, user: MemberConverter2):
        """!kazhelp
        description: Update a user's milestone role.
        parameters:
            - name: user
              type: "@mention"
              description: The user to update (as an @mention or a Discord ID).
        """
        user = user  # type: discord.Member  # IDE type checking
        try:
            last_check_in = self.c.query_check_ins(member=user)[-1]
            target_role = self.c.find_target_milestone(last_check_in)
        except orm.exc.NoResultFound:
            logger.warning("milestone_update: No check-ins for member {!s}".format(user))
            target_role = None

        milestone_roles = self.c.get_milestone_roles()
        logger.debug("Found milestone roles: {}".format(", ".join(r.name for r in milestone_roles)))

        updated_roles = (set(user.roles) - set(milestone_roles))

        if target_role:
            updated_roles |= {target_role}
            logger.info("Setting member {!s} milestone role to {.name}".format(user, target_role))
            await self.bot.replace_roles(user, *updated_roles)
            await self.bot.reply("Set {.mention} milestone role to {.name}."
                .format(user, target_role))
        else:
            logger.info("Removing member {!s} milestone roles.".format(user))
            await self.bot.replace_roles(user, *updated_roles)
            await self.bot.reply(("Member {.mention} has no check-ins; "
                                  "removing milestone roles (if any).").format(user))
