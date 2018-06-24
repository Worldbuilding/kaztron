import logging
from typing import Sequence

import discord
from discord.ext import commands
from sqlalchemy import orm
from datetime import datetime, timedelta

from kaztron import KazCog
from kaztron.driver.pagination import Pagination
from kaztron.theme import solarized
from kaztron.utils.checks import mod_only, mod_channels, in_channels
from kaztron.utils.converter import MemberConverter2, NaturalDateConverter, BooleanConverter, \
    NaturalInteger
from kaztron.utils.discord import Limits, get_group_help, user_mention, get_named_role
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.datetime import format_datetime, format_date

from kaztron.cog.blots import model
from kaztron.cog.blots.controller import CheckInController, MilestoneInfo
from kaztron.utils.strings import split_chunks_on

logger = logging.getLogger(__name__)


class CheckInManager(KazCog):
    """ Check-in manager for Inkblood BLOTS. """
    ITEMS_PER_PAGE = 12
    EMBED_COLOR = solarized.yellow
    PROJECT_UNIT_MAP = {
        model.ProjectType.script: "pages (script)",
        model.ProjectType.visual: "pages (visual)",
        model.ProjectType.words: "words"
    }

    check_in_channel_id = KazCog.config.get('blots', 'check_in_channel')
    test_channel_id = KazCog.config.get('discord', 'channel_test')

    def __init__(self, bot):
        super().__init__(bot)
        self.c = None  # type: CheckInController

    async def on_ready(self):
        await super().on_ready()
        milestone_map = {}
        for pt, ms_map in self.config.get('blots', 'milestone_map').items():
            milestone_map[model.ProjectType[pt]] = {get_named_role(self.server, r): v
                                                    for r, v in ms_map.items()}
        self.c = CheckInController(self.server, self.config, milestone_map)

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
        """
        BLOTS weekly check-in. Enter your TOTAL word (or page) count and a brief update message.

        If your project type is "words", enter your word_count in words (total). If your project
        type is "visual" or "script", enter your total number of pages instead. See also
        `.help checkin type`.

        Arguments:
        * word_count: Required. Your total word count (or total pages, depending on project type).
        * message: Required. Your progress update. Maximum length 1000 characters.

        Examples:
            .checkin 304882 Finished chapter 82 and developed some of the social and economic
                fallout of the Potato Battle of 1912.
        """
        word_count = word_count  # type: int  # for IDE type checking
        if word_count < 0:
            raise commands.BadArgument("word_count must be greater than 0.")
        if not message:
            raise commands.BadArgument("Check-in message is required.")

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
        """
        Check or set project type for check-ins.

        If no argument is provided, checks your project type. If an argument is provided, sets the
        project type to the specified value.

        This command determines the unit for the word_count you enter when you check in. If your
        project type is "words" (the default), enter it in words. If your project type is
        "visual" or "script", enter it in pages. See also `.help checkin`.

        Arguments:
        * project_type: Optional. One of "words" (default), "visual" or "script".

        Examples:
            .checkin type - Check your current project type.
            .checkin type script - Set your project type to script.
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
        """
        Check your list of check-ins. The result is always PMed to you.

        Arguments:
        * page: Optional. The page number to access, if there are more than 1 page of check-ins.
          Default: last page.

        Examples:
            .checkin list - List all your check-ins (last page if multiple pages)..
            .checkin list 4 - List the 4th page of check-ins
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
        """
        [MOD ONLY] Query a user's list of check-ins.

        Arguments:
        * user: Required. The user to check (as an @mention or a Discord ID).
        * page: Optional. The page number to access, if there are more than 1 page of check-ins.
          Default: last page.

        Examples:
            .checkin query @JaneDoe - List all check-ins by JaneDoe (last page if multiple pages)..
            .checkin query @JaneDoe 4 - List the 4th page of check-ins by JaneDoe.
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
    async def check_in_report(self, ctx: commands.Context, datespec: NaturalDateConverter=None):
        """
        [MOD ONLY] Get a report of who has or has not checked in in a given week.

        Arguments:
        * datespec: Optional. A date in any unambiguous format (2018-03-14, March 14 2018,
          14 March 2018, today, 1 month ago, etc.). The report will be for the check-in week that
          includes this date. Default: 7 days ago.

        Examples:
            .checkin report - Get a report for last week.
            .checkin report 2018-04-18 - Get a report for the week including 18 April 2018.
        """
        if not datespec:
            datespec = datetime.utcnow() - timedelta(days=7)

        start, end = self.c.get_check_in_week(datespec)
        week_str = "the week from {} to {}".format(format_datetime(start), format_datetime(end))
        try:
            report = self.c.get_check_in_report(datespec)
        except orm.exc.NoResultFound:
            await self.bot.say("No check-ins for {}.".format(week_str))
            return

        users_checked_in = ["{0} ({1})".format(m.mention, format_datetime(c.timestamp))
                            for m, c in report.items() if c]
        users_not_checked_in = []
        if None in report.values():
            latest_check_ins = self.c.query_latest_check_ins()
            for m, c in report.items():
                if c is None:
                    try:
                        last_check_in = latest_check_ins[m]
                        date_str = format_date(last_check_in.timestamp)
                    except KeyError:
                        date_str = 'Never'
                    users_not_checked_in.append("{0} (last: {1})".format(m.mention, date_str))

        checked_in_str = "**CHECKED IN**\n{}"\
            .format('\n'.join(users_checked_in))
        if len(checked_in_str) > Limits.MESSAGE:  # if too long for one message, summarize
            checked_in_str = "**CHECKED IN**\n{:d} users (list too long)"\
                .format(len(users_checked_in))

        no_check_in_str = "**DID NOT CHECK IN**\n{}" \
            .format('\n'.join(users_not_checked_in))  # don't summarize: may need action

        await self.bot.say("**Check-In Report for {}**".format(week_str))
        for msg in split_chunks_on(checked_in_str, Limits.MESSAGE):
            await self.bot.say(msg[:Limits.MESSAGE])
        for msg in split_chunks_on(no_check_in_str, Limits.MESSAGE):
            await self.bot.say(msg[:Limits.MESSAGE])

    @check_in.command(name='exempt', pass_context=True, ignore_extra=True)
    @mod_only()
    @mod_channels()
    async def checkin_exempt(self,
                             ctx: commands.Context,
                             member: MemberConverter2=None,
                             val: BooleanConverter=None):
        """
        [MOD ONLY] Check or set exemptions from check-ins.

        Arguments:
        * user: Optional. The user to check (as an @mention or a Discord ID).
        * val: Optional, "yes" or "no". If not specified, check exemptions. If specified, changes
          that user's exemption status.

        Examples:
            .checkin exempt - Get a list of exempt users.
            .checkin exempt @JaneDoe - Check if JaneDoe is exempt from check-ins.
            .checkin exempt @JaneDoe yes - Set JaneDoe as exempt from check-ins.
        """
        if member is None:
            exempt_users = self.c.get_exempt_users()
            if exempt_users:
                full_msg = "**Exempt from check-ins**\n{}"\
                    .format('\n'.join(user_mention(u.discord_id) for u in exempt_users))
            else:
                full_msg = "**No users are exempt from check-ins.**"
            for msg in split_chunks_on(full_msg, Limits.MESSAGE):
                await self.bot.say(msg[:Limits.MESSAGE])
        elif val is None:
            member_ = member  # type: discord.Member  # IDE type detection
            if self.c.get_user(member_).is_exempt:
                await self.bot.say("{} is **exempt** from check-ins.".format(member_.mention))
            else:
                await self.bot.say("{} is **not** exempt from check-ins.".format(member_.mention))
        else:
            member_ = member  # type: discord.Member  # IDE type detection
            self.c.set_user_exempt(member_, val)
            await self.bot.say("{} has been set {} from check-ins."
                .format(member_.mention, "**exempt**" if val else "**not** exempt"))

    @commands.group(pass_context=True, ignore_extra=True, invoke_without_command=True)
    @mod_only()
    @mod_channels()
    async def milestone(self, ctx: commands.Context):
        """
        [MOD ONLY] Milestone management tools.
        """
        await self.bot.say(get_group_help(ctx))

    @milestone.command(name='report', pass_context=True, ignore_extra=True)
    @mod_only()
    @mod_channels()
    async def milestone_report(self, ctx: commands.Context):
        """
        [MOD ONLY] Give a report of each user's milestone compared to their last check-in.
        """
        report = self.c.get_milestone_report()
        report_text = ["**Milestone Updates Required**\n"]
        for role, ms_info_list in report.items():
            if role is not None:
                changed_milestone_list = [m for m in ms_info_list if m.milestone_changed]
                report_text.append("**{}**\n{}\n".format(
                    role.name,
                    self._ms_report_list_users(changed_milestone_list) or 'None'
                ))
            else:
                report_text.append("**No Check-Ins**\n{}\n".format(
                    self._ms_report_list_users(ms_info_list) or 'None'
                ))

        for msg in split_chunks_on('\n'.join(report_text), Limits.MESSAGE):
            await self.bot.say(msg[:Limits.MESSAGE])

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
    async def milestone_update(self, ctx: commands.Context, member: MemberConverter2):
        """
        [MOD ONLY] Update a user's milestone roles.

        Arguments:
        * `member`: An @mention, user highlight or exact name+discriminator for a server member.
        """
        member = member  # type: discord.Member  # IDE type checking
        try:
            last_check_in = self.c.query_check_ins(member=member)[-1]
            target_role = self.c.find_target_milestone(last_check_in)
        except orm.exc.NoResultFound:
            logger.warning("milestone_update: No check-ins for member {!s}".format(member))
            target_role = None

        milestone_roles = self.c.get_milestone_roles()
        logger.debug("Found milestone roles: {}".format(", ".join(r.name for r in milestone_roles)))

        updated_roles = (set(member.roles) - set(milestone_roles))

        if target_role:
            updated_roles |= {target_role}
            logger.info("Setting member {!s} milestone role to {.name}".format(member, target_role))
            await self.bot.replace_roles(member, *updated_roles)
            await self.bot.reply("Set {.mention} milestone role to {.name}."
                .format(member, target_role))
        else:
            logger.info("Removing member {!s} milestone roles.".format(member))
            await self.bot.replace_roles(member, *updated_roles)
            await self.bot.reply(("Member {.mention} has no check-ins; "
                                  "removing milestone roles (if any).").format(member))
