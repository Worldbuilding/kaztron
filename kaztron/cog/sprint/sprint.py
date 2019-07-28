import asyncio
from datetime import timedelta
from typing import Optional

from discord.ext import commands

from kaztron import KazCog, task, TaskInstance
from kaztron.cog.sprint.model import *
from kaztron.errors import UnauthorizedUserError, ModOnlyError
from kaztron.theme import solarized
from kaztron.utils.checks import in_channels_cfg
from kaztron.utils.converter import NaturalDateConverter, NaturalInteger
from kaztron.utils.datetime import format_date, format_timedelta, parse as dt_parse, \
    get_weekday
from kaztron.utils.discord import check_mod, get_named_role, remove_role_from_all, \
    get_member, get_group_help
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list

logger = logging.getLogger(__name__)


class SprintError(RuntimeError):
    pass


class SprintNotRunningError(RuntimeError):
    pass


class SprintRunningError(RuntimeError):
    pass


def format_seconds(seconds: float, timespec='seconds'):
    return format_timedelta(timedelta(microseconds=int(seconds*1e6)), timespec=timespec)


class WritingSprint(KazCog):
    """!kazhelp
    brief: Hold writing sprints, where a group of writers get together to work on their writing
        projects for a fixed amount of time and compete on word count.
    contents:
        - sprint:
            - status
            - start
            - stop
            - join
            - leave
            - wordcount
            - final
            - follow
            - unfollow
            - leader
            - stats
            - statreset
    """

    INLINE = True  # makes DISP_EMBEDS prettier
    MAX_LEADERS = 5

    DISP_COLORS = {
        SprintState.PREPARE: solarized.cyan,
        SprintState.SPRINT: solarized.violet,
        SprintState.COLLECT_RESULTS: solarized.green,
        SprintState.IDLE: solarized.blue,
        "leader": solarized.blue,
        "stats": solarized.blue
    }

    DISP_EMBEDS = {
        "status": EmbedInfo(
            title=discord.Embed.Empty,
            color=discord.Embed.Empty,
            msg="",
            strings=[
                # don't change the order of these - status command uses indices to decide on them
                ("Placeholder", "Placeholder", not INLINE),
                ("Started by", "{founder}", INLINE),
                ("Starts in", "{delay}", INLINE),
                ("Duration", "{duration}", INLINE),
                ("Remaining", "{remaining}", INLINE),
                ("Results in", "{finalize}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "start": EmbedInfo(
            title="Pre-sprint",
            color=DISP_COLORS[SprintState.PREPARE],
            msg="**Get ready! A writing sprint is starting soon!** "
                "Type `.w join <initial_wordcount>` to join! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Starts in", "{delay}", INLINE),
                ("Duration", "{duration}", INLINE),
            ]
        ),
        "stop": EmbedInfo(
            title="Sprint cancelled",
            color=0xcb4b16,
            msg="**The sprint has been cancelled!** {msg} {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "task_on_sprint_start": EmbedInfo(
            title="Sprint start",
            color=DISP_COLORS[SprintState.SPRINT],
            msg="**The sprint is starting!** Get to writing! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Duration", "{duration}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "task_on_sprint_warning": EmbedInfo(
            title="Sprint reminder",
            color=solarized.orange,
            msg="**Sprint reminder!** {remaining!s} left. You better still be writing! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Time remaining", "{remaining}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "task_on_sprint_end": EmbedInfo(
            title="Sprint end",
            color=DISP_COLORS[SprintState.COLLECT_RESULTS],
            msg="**Pencils down!** The sprint has ended! "
                "Report your final wordcount with `.w c <wordcount>`! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Results in", "{finalize}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "task_on_sprint_results": EmbedInfo(
            title="Sprint results",
            color=DISP_COLORS[SprintState.IDLE],
            msg="**And here are the sprint's results!** "
                "Congrats to {winner}, with {wc} words!\n\n"
                "Who cares about the winner, though? You got some writing done! Right?\n\n"
                "On to the next sprint! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Duration", "{duration}", INLINE),
                ("Final results", "{participants}", INLINE)
            ]
        ),
        "leader": EmbedInfo(
            title="Leaderboard ({weekname})",
            color=DISP_COLORS["leader"],
            msg="",
            strings=[
                ("Most prolific", "{leaders_words}", INLINE),
                ("Fastest writers", "{leaders_wpm}", INLINE),
                ("Sprint time", "{leaders_time}", INLINE),
                ("Most wins", "{leaders_wins}", INLINE)
            ]
        ),
        "stats_global": EmbedInfo(
            title="Global stats ({weekname})",
            color=DISP_COLORS["stats"],
            msg="",
            strings=[
                ("Sprints", "{stats.sprints:.0f}", INLINE),
                ("Total time",  "{total_time}", INLINE),
                ("Total words", "{stats.words:.0f} words", INLINE),
                ("Average sprint", "{average_time}", INLINE),
                ("Average cumulative productivity",
                 "{stats.wpm_mean:.1f} wpm overall (σ = {stats.wpm_stdev:.1f})", INLINE),
                ("Since", "{since}", INLINE)
            ]
        ),
        "stats": EmbedInfo(
            title=discord.Embed.Empty,
            color=DISP_COLORS["stats"],
            msg="",
            strings=[
                ("User Stats", "<@{user_id}>", INLINE),
                ("Period", "{weekname}", INLINE),
                ("Sprints", "{stats.sprints:.0f}", INLINE),

                ("Wins", "{stats.wins:.0f} ({stats.win_rate:.0%})", INLINE),
                ("Total time",  "{total_time}", INLINE),
                ("Total words", "{stats.words:.0f} words", INLINE),

                ("Average sprint", "{average_time}", INLINE),
                ("Average speed",
                 "{stats.wpm_mean:.1f} wpm (σ = {stats.wpm_stdev:.1f})", INLINE),
                ("Since", "{since}", INLINE)
            ]
        ),
    }

    DISP_STRINGS = {
        "join": "{mention} You have joined the sprint with an initial wordcount of {wc:d} words! "
                "Have fun writing!",
        "rejoin": "{mention} Updated your initial wordcount to {wc:d} words.",
        "leave": "{mention} You have left the writing sprint! Sorry you can't stick around.",
        "leave_error": "{mention} You're not in the writing sprint!",
        "wordcount": "{mention} Your wordcount is now {wc:d} ({diff:+d}). "
                     "If you're done writing for this sprint, don't forget to use `.w final`!",
        "wordcount_error": "{mention} You're not in the writing sprint! "
                           "Use `.w join <wordcount>` to join.",
        "final": "{mention} Your wordcount has been finalized at {wc:d} words.",
        'finalize_error': "{mention} You haven't submitted an end wordcount yet! "
                          "Use `.w wc <count>` to set your current wordcount.",

        "status_idle_tuple": ("Nobody's sprinting right now!",
                              "Start a sprint with `.w start`! Type `.help w start` for help.",
                              not INLINE),
        "status_prepare_tuple": ("A sprint is starting soon!",
                                 "Join the sprint with `.w join <initial_wordcount>`!",
                                 not INLINE),
        "status_sprint_tuple": ("A sprint is ongoing!",
                                "Think you can catch up? "
                                "Join the sprint with `.w join <initial_wordcount>`!",
                                not INLINE),
        "status_collect_tuple": ("A sprint is ongoing!",
                                 "Think you can catch up? "
                                 "Join the sprint with `.w join <initial_wordcount>`!",
                                 not INLINE),

        "cancel_leave": "No participants are left in the sprint.",
        "cancel_start": "I can't start a sprint with no participants.",
        "report": "**Weekly report now available!** You can use `.w stats` and `.w leader` "
                  "to re-show these reports or get individual statistics.",

        "err_running_general": "Sorry, you can't do that while a sprint is running. "
                               "Please wait for the sprint to end.\n\nSprint creator and mods "
                               "can use `.w stop` to cancel the sprint.",
        "err_running_suggest_join": "A sprint's already running! "
                                    "You can join in with `.w join <initial_wordcount>`!",
        "err_running_wordcount": "A sprint's running! Please wait until the end of the sprint to "
                                 "report your wordcount.",
        "err_running_collect": "Sorry, you can't do that while the sprint is wrapping up. "
                               "Please wait for the results to be announced.",
        "err_not_running_general": "There isn't a sprint running right now! "
                                   "You can start a sprint using `.w start` "
                                   "(see `.help start` for usage information).",
        "err_unauthorized_user": "You have to be the sprint founder ({}) or a mod to do that.",
        "err_stats_user": "{user.name} hasn't participated in any sprints!",
        "err_wtf": "NonsenseError: You can't do that, there's a blazing bunny on your head."
    }

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults(
            'sprint',
            state=SprintState.IDLE.value,
            sprint_data=SprintData().to_dict(),
            stats=SprintUserStats().to_dict(),
            weekly_stats={}
        )

        self.channel_id = self.config.get('sprint', 'channel')
        self.channel = None

        self.role_sprint_name = self.config.get('sprint', 'role_sprint')
        self.role_follow_name = self.config.get('sprint', 'role_follow')

        self.role_sprint = None
        self.role_follow = None

        self.role_follow_mention = '<Follow Role Missing>'
        self.role_sprint_mention = '<Sprint Role Missing>'

        self.delay_default = self.config.get('sprint', 'delay_default')
        self.delay_max = self.config.get('sprint', 'delay_max')
        self.delay_min = 15  # short hardcoded delay to allow at least one person to join
        self.duration_default = self.config.get('sprint', 'duration_default')
        self.duration_min = self.config.get('sprint', 'duration_min')
        self.duration_max = self.config.get('sprint', 'duration_max')
        self.finalize = self.config.get('sprint', 'finalize_time')

        self.sprint_data = SprintData()
        self.state_tasks = []  # type: List[TaskInstance]

        self.report_time = dt_parse(self.config.get('sprint', 'report_time', '17:00')).time()
        self.report_task = None  # type: TaskInstance

    def get_state(self):
        return SprintState(self.state.get('sprint', 'state'))

    def set_state(self, state: SprintState):
        self.state.set('sprint', 'state', state.value)

    def _save_sprint(self):
        self.state.set('sprint', 'sprint_data', self.sprint_data.to_dict())
        try:
            self.state.write()
        except OSError:
            logger.error("Error persisting sprint")

    def _load_sprint(self):
        # state is always directly read from the config (see get_state), so no need to set it here
        if self.get_state() is not SprintState.IDLE:
            try:
                self.sprint_data = SprintData.from_dict(self.channel.server,
                    self.state.get('sprint', 'sprint_data'))
            except KeyError:
                logger.warning("Old sprint data incorrectly formatted, ignoring")

    def save_stats(self, s: SprintUserStats):
        """
        Store the stats in the config. This does NOT write to disk (call :meth:`_save_sprint`).
        """
        self.state.set('sprint', 'stats', s.to_dict())

    def load_stats(self) -> SprintUserStats:
        return SprintUserStats.from_dict(self.state.get('sprint', 'stats'))

    def save_weekly_stats(self, dt: datetime, stats: SprintUserStats):
        """
        Store the weekly stats to the config. The stats will be associated to the week that
        includes the given date.
        """
        self.state.get('sprint', 'weekly_stats')[dt.strftime('%Y%U')] = stats.to_dict()

    def load_weekly_stats(self, dt: datetime) -> SprintUserStats:
        """ Load the weekly stats that include the given date. """
        try:
            return SprintUserStats.from_dict(
                self.state.get('sprint', 'weekly_stats')[dt.strftime('%Y%U')]
            )
        except KeyError:
            return SprintUserStats()

    async def _display_embed(self, dest, embed_info: EmbedInfo, *args, **kwargs):
        """ Convenience function: display an embed from the EmbedInfo """
        if isinstance(embed_info.title, str):
            title = embed_info.title.format(*args, **kwargs)
        else:
            title = embed_info.title

        em = discord.Embed(title=title, color=embed_info.color)

        if embed_info.author:
            em.set_author(name=embed_info.author)

        for name, val, inline in embed_info.strings:
            try:
                em.add_field(name=name, value=val.format(*args, **kwargs), inline=inline)
            except (ValueError, KeyError) as e:
                raise type(e)("Error processing field {!r}".format(name)) from e

        await self.bot.send_message(dest, embed_info.msg.format(*args, **kwargs), embed=em)
        try:
            pass
        except Exception:
            logger.debug("Failed to send: {!r}".format(embed_info))
            logger.debug("With args:\n\n{!r}\n\n{!r}".format(args, kwargs))
            raise

    def _format_wordcount_list(self, wordcounts: Dict[str, int]):
        """ Format a wordcount dict into a list of participants. Keys should be Discord IDs. """
        return sorted(['{} ({:d} words)'.format(u.mention, wordcounts[u.id])
                       for u in self.sprint_data.members]) if wordcounts else ['None']

    def _update_roles(self):
        server = self.channel.server
        try:
            self.role_follow = get_named_role(server, self.role_follow_name)
            self.role_follow_mention = self.role_follow.mention
        except ValueError:
            self.role_follow = None
            self.role_follow_mention = ''
            raise

        try:
            self.role_sprint = get_named_role(server, self.role_sprint_name)
            self.role_sprint_mention = self.role_sprint.mention
        except ValueError:
            self.role_sprint = None
            self.role_sprint_mention = ''
            raise

    async def _cancel_sprint(self, msg: str=None):
        """
        Utility method: cancels the current sprint, if one is running
        """
        await self._reset_sprint_tasks()

        old_participants = self._format_wordcount_list(self.sprint_data.start)
        self.set_state(SprintState.IDLE)
        self.sprint_data = SprintData()
        self._save_sprint()

        self._update_roles()
        await self._display_embed(
            self.channel, self.DISP_EMBEDS['stop'],
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            notif=self.role_sprint_mention,
            msg=msg if msg else "",
            participants='\n'.join(old_participants)
        )

        await remove_role_from_all(self.bot, self.channel.server, self.role_sprint)
        logger.debug("Removed all users from {} role".format(self.role_sprint_name))

    async def on_ready(self):
        """
        Load information from the server.
        """
        logger.debug("on_ready")
        await super().on_ready()

        logger.debug("Validating sprint channel...")
        self.channel = self.validate_channel(self.channel_id)

        try:
            self.rolemanager.add_managed_role(
                role_name=self.role_follow_name,
                join_name="follow",
                leave_name="unfollow",
                join_msg="You will now receive notifications when others start a sprint. You "
                         "can stop getting notifications by using the `.w unfollow` command.",
                leave_msg="You will no longer receive notifications when others start a "
                          "sprint. "
                          "You can get notifications again by using the `.w follow` command.",
                join_err="Oops! You're already receiving notifications for sprints. "
                         "Use the `.w unfollow` command to stop getting notifications.",
                leave_err="Oops! You're not currently getting notifications for sprints. Use "
                          "the `.w follow` command if you want to start getting notifications.",
                join_doc="Get notified when sprints are happening.",
                leave_doc="Stop getting notifications about sprints.\n\n"
                          "You will still get notifications for sprints you have joined.",
                group=self.sprint,
                cog_instance=self,
                ignore_extra=False
            )
        except discord.ClientException:
            logger.warning("`sprint follow` command already defined - "
                           "this is OK if client reconnected")

        state = self.get_state()
        if state is not SprintState.IDLE:
            logger.info("Loading previous sprint data...")
            self._load_sprint()
            logger.info("Restoring tasks for current sprint...")
            await self._schedule_sprint_tasks()
        else:
            logger.info("No sprint, no task needs restoring.")

        self._update_roles()

        self._schedule_report()

    async def _schedule_sprint_tasks(self):
        # clear any old sprint tasks
        await self._reset_sprint_tasks()

        state = self.get_state()
        prev_state = False

        if state is SprintState.PREPARE:
            prev_state = True
            self.state_tasks.append(self.scheduler.schedule_task_at(
                self.task_on_sprint_start, self.sprint_data.start_time
            ))

        if prev_state or state is SprintState.SPRINT:
            prev_state = True
            for wt in self.sprint_data.warn_times:
                self.state_tasks.append(self.scheduler.schedule_task_at(
                    self.task_on_sprint_warning, wt
                ))
            self.state_tasks.append(self.scheduler.schedule_task_at(
                self.task_on_sprint_end, self.sprint_data.end_time
            ))

        if prev_state or state is SprintState.COLLECT_RESULTS:
            self.state_tasks.append(self.scheduler.schedule_task_at(
                self.task_on_sprint_results, self.sprint_data.finalize_time
            ))

    async def _reset_sprint_tasks(self, join=False):
        logger.debug("Resetting all sprint tasks...")
        for ti in self.state_tasks:
            if not ti.is_current():
                try:
                    logger.debug("Cancelling {!s}".format(ti))
                    ti.cancel()
                    if join:
                        await ti
                except asyncio.InvalidStateError:
                    pass
                except asyncio.CancelledError:
                    pass  # error gets bubbled up on awaiting a cancelled task...
            else:
                logger.debug("Not cancelling {!s}: is the current task".format(ti))
        self.state_tasks.clear()

    def _schedule_report(self):
        today_report_time = datetime.combine(datetime.utcnow().date(), self.report_time)
        next_report_time = get_weekday(today_report_time, weekday=6, future=True)
        if next_report_time < datetime.utcnow():  # if today, check if we've passed the report time
            next_report_time += timedelta(days=7)
        try:
            self.report_task = self.scheduler.schedule_task_at(
                self.weekly_report, next_report_time, every=timedelta(days=7)
            )
        except asyncio.InvalidStateError as e:
            if 'unique' in e.args[0]:
                logger.debug("Report task already scheduled: not rescheduling")
            else:
                raise

    def unload_kazcog(self):
        self.report_task.cancel()
        self.report_task = None

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=True,
        aliases=['w'])
    @in_channels_cfg('sprint', 'channel')
    async def sprint(self, ctx: commands.Context):
        """!kazhelp
        brief: Command group for writing sprints.
        description: |
            Welcome to writing sprints, where everything's made up and the words don't matter!

            In writing sprints (a.k.a. word wars), you get together with a group of other writers,
            agree on a time limit, and then write together!

            At the end of the sprint, you report your word count, and whoever wrote the most wins!
            Not that it matters. Because you got some writing done, so you're always a winner!

            Writing sprints are a great way of getting you to focus on your writing and get some
            words down on your page. And, y'know, not just chatting with them the entire time when
            you told yourself you'd make some progress tonight.

            Get writing!

            TIP: Most sub-commands support a single-letter shorthand for convenience. Check each
            command's Usage section for more information.
        """
        await self.bot.say(get_group_help(ctx))

    @sprint.command(pass_context=True, ignore_extra=False, aliases=['?'])
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def status(self, ctx: commands.Context):
        """!kazhelp
        description: Get the current status of the sprint.
        """
        em_data = copy.deepcopy(self.DISP_EMBEDS['status'])
        state = self.get_state()

        try:
            em_data.color = self.DISP_COLORS[state]
        except KeyError:
            em_data.color = 0xFF9999  # something visible and wrong
            logger.warning("DISP_COLORS does not contain key {!r}".format(state))

        if state is SprintState.IDLE:
            em_data.strings = [self.DISP_STRINGS['status_idle_tuple']]
        elif state is SprintState.PREPARE:
            em_data.strings[0] = self.DISP_STRINGS['status_prepare_tuple']
            em_data.strings = em_data.strings[0:4] + em_data.strings[6:]
        elif state is SprintState.SPRINT:
            em_data.strings[0] = self.DISP_STRINGS['status_sprint_tuple']
            em_data.strings = em_data.strings[0:2] + em_data.strings[4:5] + em_data.strings[6:]
        elif state is SprintState.COLLECT_RESULTS:
            em_data.strings[0] = self.DISP_STRINGS['status_collect_tuple']
            em_data.strings = em_data.strings[0:2] + em_data.strings[3:4] + em_data.strings[5:]
        else:
            logger.error("Unknown state! {!r}".format(state))
            await self.send_output(
                "status: Unknown sprint state {!r} - probably a bug somewhere!"
                .format(state)
            )
            await self.bot.send_message(
                ctx.message.channel,
                "Oops - the sprint seems to be in an invalid state! "
                "This is probably a bug, please report it to the bot operator. "
                "In the meantime, try cancelling the sprint with `.w stop` (or ask a mod to do it)?"
            )
            return

        await self._display_embed(
            ctx.message.channel, em_data,
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            delay=format_seconds(self.sprint_data.starts_in),
            duration=format_seconds(self.sprint_data.duration),
            remaining=format_seconds(self.sprint_data.remaining),
            finalize=format_seconds(self.sprint_data.remaining_finalize),
            participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
        )

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['s'])
    @in_channels_cfg('sprint', 'channel')
    async def start(self, ctx: commands.Context, duration: float=None, delay: float=None):
        """!kazhelp
        description: |
            Start a new sprint.

            You will also need to join the sprint with `.w j` ({{!sprint join}}), in order to set
            your starting wordcount.

            TIP: Only one sprint can happen at once. If a sprint is currently running, join the
            ongoing sprint or wait until it's over.
        parameters:
            - name: duration
              type: number in minutes
              default: 25
              description: The amount of time the sprint will last.
            - name: delay
              type: number in minutes
              default: 5
              description: The amount of time to wait before starting the sprint.
        examples:
            - command: .w start
              description: Create a 25 minute sprint, starting in 5 minutes.
            - command: .w start 15
              description: Create a 15-minute sprint, starting in 5 minutes.
            - command: .w start 25 1
              description: Create a 25-minute sprint, starting in 1 minute.
        """
        state = self.get_state()
        if state is not SprintState.IDLE:
            raise SprintRunningError()

        if duration is not None:
            duration_s = 60 * duration
        else:
            duration = self.duration_default/60
            duration_s = self.duration_default

        if delay is not None:
            delay_s = 60 * delay
        else:
            delay = self.delay_default/60
            delay_s = self.delay_default

        if duration_s < self.duration_min or duration_s > self.duration_max:
            raise commands.BadArgument("The duration must be between {:.1f} and {:.1f} minutes"
                .format(self.duration_min/60, self.duration_max/60))

        if delay_s > self.delay_max:
            raise commands.BadArgument("The delay can't be longer than {:.1f} minutes"
                .format(self.delay_max/60))
        elif delay_s < self.delay_min:
            delay_s = self.delay_min

        logger.info("Creating new sprint: {0:.2f} minutes starting in {1:.2f} minutes..."
            .format(duration, delay))

        self.set_state(SprintState.PREPARE)
        sprint = SprintData()
        sprint.founder = ctx.message.author
        sprint.start_time = datetime.utcnow() + timedelta(seconds=delay_s)
        sprint.end_time = sprint.start_time + timedelta(seconds=duration_s)
        sprint.finalize_time = sprint.end_time + timedelta(seconds=self.finalize)

        # For now, warnings only in the last 1 minute, if sprint at least 10 minutes
        # if sprint.duration >= 600:
        #     sprint.warn_times.append(sprint.end_time - 60)

        self.sprint_data = sprint
        await self._schedule_sprint_tasks()

        self._update_roles()
        await self._display_embed(
            self.channel, self.DISP_EMBEDS['start'],
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            duration=format_seconds(duration_s),
            delay=format_seconds(delay_s),
            notif=self.role_follow_mention
        )

        self._save_sprint()

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['x', 'cancel'])
    @in_channels_cfg('sprint', 'channel')
    async def stop(self, ctx: commands.Context):
        """!kazhelp
        description:
            Cancel the current sprint.

            This can only be done by the creator of the sprint or moderators.
        """
        state = self.get_state()
        if state is SprintState.IDLE:
            raise SprintNotRunningError()
        elif state is SprintState.COLLECT_RESULTS:
            raise SprintRunningError()

        # Validate allowed to stop
        asker_is_founder = ctx.message.author.id == self.sprint_data.founder.id

        is_founder_in_sprint = self.sprint_data.founder.id in self.sprint_data.start
        is_asker_in_sprint = ctx.message.author.id in self.sprint_data.start
        is_asker_allowed = (state is not SprintState.PREPARE
                            and not is_founder_in_sprint and is_asker_in_sprint)

        if asker_is_founder or check_mod(ctx) or is_asker_allowed:
            logger.info("Stopping sprint by request.")
            await self._cancel_sprint()
        else:
            raise UnauthorizedUserError

    async def update_initial_wordcount(self, user: discord.Member, wordcount: int):
        logger.info("User {} updated initial wc to {:d} words".format(user.name, wordcount))
        self.sprint_data.start[user.id] = wordcount
        await self.bot.say(self.DISP_STRINGS['rejoin'].format(mention=user.mention, wc=wordcount))
        self._save_sprint()

    async def update_final_wordcount(self, user: discord.Member, wordcount: int):
        logger.info("User {} set wordcount {:d}".format(user.name, wordcount))
        self.sprint_data.end[user.id] = wordcount
        await self.bot.say(self.DISP_STRINGS['wordcount'].format(
            mention=user.mention,
            wc=wordcount,
            diff=wordcount - self.sprint_data.start[user.id]
        ))
        self._save_sprint()

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['j'])
    @in_channels_cfg('sprint', 'channel')
    async def join(self, ctx: commands.Context, wordcount: NaturalInteger):
        """!kazhelp
        description: |
            Join the current sprint and set your starting wordcount.

            You can also use this command to edit your starting wordcount, e.g. if you made a
            mistake.

            If no sprint is running, first start one with `.w s` ({{!sprint start}}).

            TIP: You can join a sprint even if it has started.
        parameters:
            - name: wordcount
              optional: true
              type: number in words
              description: Your starting wordcount, before the start of the sprint. When you later
                report your wordcount at the end of the sprint, your total words written during the
                sprint will automatically be calculated.
        examples:
            - command: .w j 12044
              description: Join the sprint with an initial wordcount of 12,044 words.
        """
        wordcount = wordcount  # type: int
        state = self.get_state()
        if state is SprintState.IDLE:
            raise SprintNotRunningError()
        elif state is SprintState.COLLECT_RESULTS:
            raise SprintRunningError()

        if wordcount < 0:
            raise commands.BadArgument("wordcount must be a nonnegative integer.")

        user = ctx.message.author

        if user.id not in self.sprint_data.start:
            logger.info("User {} joined sprint with {:d} words".format(user.name, wordcount))
            self.sprint_data.members.append(user)
            self.sprint_data.start[user.id] = wordcount

            # give role
            if self.role_sprint not in ctx.message.author.roles:
                await self.bot.add_roles(ctx.message.author, self.role_sprint)
                logger.info("join: Gave role {} to user {}"
                    .format(self.role_sprint_name, ctx.message.author))

            await self.bot.say(self.DISP_STRINGS['join'].format(mention=user.mention, wc=wordcount))

            self._save_sprint()
        else:
            await self.update_initial_wordcount(user, wordcount)

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['l'])
    @in_channels_cfg('sprint', 'channel')
    async def leave(self, ctx: commands.Context):
        """!kazhelp
        description: |
            Leave a sprint you previously joined.

            Note that, if you can't stay for the entire sprint, you can also use `.w wc`
            ({{!sprint wordcount}}) and `.w final` ({{!sprint final}}) to enter your current
            wordcount during the sprint.
        """
        state = self.get_state()
        if state is SprintState.IDLE:
            raise SprintNotRunningError()
        elif state is SprintState.COLLECT_RESULTS:
            raise SprintRunningError()

        user = ctx.message.author

        if user.id in self.sprint_data.start:
            logger.info("User {} left the sprint".format(user.name))
            # not sure if user objects always equal - filter by ID
            self.sprint_data.members = [m for m in self.sprint_data.members if m.id != user.id]
            del self.sprint_data.start[user.id]
            await self.bot.say(self.DISP_STRINGS['leave'].format(mention=user.mention))

            # take role
            if self.role_sprint in ctx.message.author.roles:
                await self.bot.remove_roles(ctx.message.author, self.role_sprint)
                logger.info("leave: Removed role {} from user {}"
                    .format(self.role_sprint_name, ctx.message.author))

            # If sprint has started and no members
            if state is SprintState.SPRINT and not self.sprint_data.members:
                logger.info("No more participants in sprint. Cancelling.")
                await self._cancel_sprint(self.DISP_STRINGS['cancel_leave'])
            else:  # just save the sprint state
                self._save_sprint()
        else:
            logger.warning("Cannot remove user {} from sprint: not in sprint".format(user.name))
            await self.bot.say(self.DISP_STRINGS['leave_error'].format(mention=user.mention))

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['wc', 'c'])
    @in_channels_cfg('sprint', 'channel')
    async def wordcount(self, ctx, wordcount: int):
        """!kazhelp
        description:
            Report your wordcount at the end of a sprint.
        parameters:
            - name: wordcount
              optional: true
              type: number in words
              description: Your final total wordcount. Your total words written during the sprint
                will automatically be calculated from your starting and final wordcount.
        examples:
            - command: .w wc 13012
              description: Report that your total wordcount at the end of the sprint was 13,012.
        """
        state = self.get_state()
        if state is SprintState.IDLE:
            raise SprintNotRunningError()

        if wordcount < 0:
            raise commands.BadArgument("wordcount must be a nonnegative integer.")

        user = ctx.message.author

        if user.id not in self.sprint_data.start:
            logger.warning("Cannot set wordcount: user {} not in sprint".format(user.name))
            await self.bot.say(self.DISP_STRINGS['wordcount_error'].format(mention=user.mention))
            return

        if state is SprintState.PREPARE:
            await self.update_initial_wordcount(user, wordcount)
        elif state is SprintState.SPRINT or state is SprintState.COLLECT_RESULTS:
            await self.update_final_wordcount(user, wordcount)

    @sprint.command(pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def final(self, ctx: commands.Context):
        """!kazhelp
        description: Finalize your wordcount. Use this when you're sure you're done and that you've
            correctly entered your wordcount.
        """
        state = self.get_state()
        if state is SprintState.IDLE or state is SprintState.PREPARE:
            raise SprintNotRunningError()

        user = ctx.message.author

        # check if user is in sprint and has submitted a final wordcount
        if user.id not in self.sprint_data.start:
            logger.warning("Cannot finalize: user {} not in sprint".format(user.name))
            await self.bot.say(self.DISP_STRINGS['wordcount_error'].format(mention=user.mention))
            return
        elif user.id not in self.sprint_data.end:
            logger.warning("Cannot finalize: user {} has not submitted a wordcount"
                .format(user.name))
            await self.bot.say(self.DISP_STRINGS['finalize_error'].format(mention=user.mention))
            return

        # record user's finalization
        self.sprint_data.finalized.add(user.id)
        await self.bot.say(self.DISP_STRINGS['final'].format(
            mention=user.mention,
            wc=self.sprint_data.end[user.id] - self.sprint_data.start[user.id])
        )

        # If everyone has submitted, fast forward
        if state is SprintState.COLLECT_RESULTS and \
                set(self.sprint_data.start.keys()) == self.sprint_data.finalized:
            logger.info("All wordcounts submitted. Fast-forwarding to result announcement.")
            await self._reset_sprint_tasks(True)
            # finalize NOW
            self.state_tasks.append(self.scheduler.schedule_task_in(self.task_on_sprint_results, 0))
        else:
            self._save_sprint()

    @sprint.command(pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def leader(self, ctx, *, date: NaturalDateConverter=None):
        """!kazhelp
        description: |
            Show the leaderboards, either all-time or weekly.

            If no date is specified, shows leaderboard for all time. If a date is specified, shows
            the leaderboard for the week that contains that date.
        parameters:
            - name: date
              type: date
              optional: true
              default: None (all time)
              description: Specifies the leaderboard week to show. Various date formats are
                accepted like 2018-03-14, 14 Mar 2018, three days ago, etc.
        examples:
            - command: .w leader
              description: All-time leaderboard.
            - command: .w leader 2018-03-14
              description: Leaderboard for the week that contains 14 March 2018.
        """
        date = date  # type: datetime
        await self._leader_inner(ctx.message.channel, date)

    async def _leader_inner(self, dest, date: datetime):
        # Get stats and sort them by each leaderboard criterion
        if date is None:
            entry_user_map = {uid: d for uid, d in self.load_stats().users.items()}
        else:
            entry_user_map = {uid: d for uid, d in self.load_weekly_stats(date).users.items()}
        entries_by_t = sorted(entry_user_map.items(), key=lambda e: e[1].time, reverse=True)
        entries_by_w = sorted(entry_user_map.items(), key=lambda e: e[1].words, reverse=True)
        entries_by_wpm = sorted(entry_user_map.items(), key=lambda e: e[1].wpm_mean, reverse=True)
        entries_by_wins = sorted(entry_user_map.items(), key=lambda e: e[1].wins, reverse=True)

        # Generate strings for each
        list_by_t = ["<@{}>: {:.1f} hours".format(uid, s.time/3600)
                     for uid, s in entries_by_t[:self.MAX_LEADERS]]
        list_by_w = ["<@{}>: {:d} words".format(uid, s.words)
                     for uid, s in entries_by_w[:self.MAX_LEADERS]]
        list_by_wpm = ["<@{}>: {:.1f} wpm".format(uid, s.wpm_mean)
                       for uid, s in entries_by_wpm[:self.MAX_LEADERS]]
        list_by_wins = ["<@{}>: {:d} wins".format(uid, s.wins)
                       for uid, s in entries_by_wins[:self.MAX_LEADERS]]

        await self._display_embed(
            dest, self.DISP_EMBEDS['leader'],
            weekname="all time" if not date else date.strftime("%Y week %U"),
            leaders_time=format_list(list_by_t) or "None",
            leaders_words=format_list(list_by_w) or "None",
            leaders_wpm=format_list(list_by_wpm) or "None",
            leaders_wins=format_list(list_by_wins) or "None"
        )

    @sprint.command(pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def stats(self, ctx, user: str, *, date: NaturalDateConverter=None):
        """!kazhelp
        description: |
            Show stats, either global or per-user and either all-time or weekly.

            If no date is specified, shows stats for all time. If a date is specified, shows stats
            for the week that contains that date.
        parameters:
            - name: user
              type: '@user or "all"'
              description: An @mention of the user to look up, or "all" for global stats.
            - name: date
              type: date
              optional: true
              default: None (all time)
              description: Specifies the stats week to show. Various date formats are
                accepted like 2018-03-14, 14 Mar 2018, three days ago, etc.
        examples:
            - command: .w stats all
              description: Global stats for all time.
            - command: .w stats @JaneDoe#0921
              description: Stats for JaneDoe for all time.
            - command: .w stats all 2018-03-14
              description: Global stats for the week including 14 March.
        """
        date = date  # type: datetime
        member = get_member(ctx, user) if user != 'all' else None

        if member:
            await self._stats_user(ctx.message.channel, member, date)
        else:
            await self._stats_global(ctx.message.channel, date)

    async def _stats_user(self, dest, user: Optional[discord.Member], date: datetime):
        logger.debug("stats: user: id={user.id} name={user.name}".format(user=user))
        try:
            if not date:
                stats = self.load_stats().users[user.id]
            else:
                stats = self.load_weekly_stats(date).users[user.id]
        except KeyError:
            await self.bot.say(self.DISP_STRINGS["err_stats_user"].format(user=user))
        else:
            await self._display_embed(
                dest, self.DISP_EMBEDS['stats'],
                user_id=user.id,
                stats=stats,
                weekname="all time" if not date else date.strftime("%Y week %U"),
                average_time=format_seconds(stats.time_mean),
                total_time=format_seconds(stats.time, timespec='minutes'),
                since=format_date(stats.since)
            )

    async def _stats_global(self, dest, date: datetime):
        logger.debug("stats: requested global")
        if not date:
            stats = self.load_stats().overall
        else:
            stats = self.load_weekly_stats(date).overall
        await self._display_embed(
            dest, self.DISP_EMBEDS['stats_global'],
            stats=stats,
            weekname="all time" if not date else date.strftime("%Y week %U"),
            average_time=format_seconds(stats.time_mean),
            total_time=format_seconds(stats.time, timespec='minutes'),
            since=format_date(stats.since)
        )

    @sprint.command(name="statreset", pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def stats_reset(self, ctx, user: str=None):
        """!kazhelp
        description: |
            Reset your own stats. Mods can reset any stats.

            Resetting your own stats will not change your contribution to the global stats.

            IMPORTANT: This cannot be undone.
        parameters:
            - name: user
              type: '@user, "global" or "all"'
              description: Mods only. An @mention of the user whose stats are to be deleted.
                "global" deletes the global stats, but does not touch individual user stats.
                "all" deletes global stats and all user stats.
        examples:
            - command: .w statreset
              description: Reset your own stats.
            - command: .w statreset @JaneDoe#0921
              description: Reset Jane Doe's stats. Mods only.
            - command: .w statreset global
              description: Reset global stats only (user stats are preserved). Mods only.
        """
        if user == 'global' or user == 'all':
            member = user
        elif user:
            member = get_member(ctx, user)
        elif user is None:
            member = ctx.message.author
        else:
            raise commands.BadArgument("Invalid user argument")

        if not check_mod(ctx) and not member == ctx.message.author:
            raise ModOnlyError("Only moderators can reset stats.")

        if member == 'global':
            logger.info("Clearing global stats...")
            stats = self.load_stats()
            stats.clear_overall()
            self.save_stats(stats)

            now = datetime.utcnow()
            w_stats = self.load_weekly_stats(now)
            w_stats.clear_overall()
            self.save_weekly_stats(now, w_stats)
            await self.bot.say("Cleared global stats.")
        elif member == 'all':
            logger.info("Clearing all stats...")
            self.save_stats(SprintUserStats())
            await self.bot.say("Cleared all stats.")
        else:
            logger.info("Clearing stats for {}...".format(member.nick or member.name))
            stats = self.load_stats()
            stats.clear_user(member)
            self.save_stats(stats)

            now = datetime.utcnow()
            w_stats = self.load_weekly_stats(now)
            w_stats.clear_user(member)
            self.save_weekly_stats(now, w_stats)
            await self.bot.say("Cleared all stats for {}.".format(member.mention))

        self._save_sprint()

    @task(is_unique=True)
    async def weekly_report(self):
        logger.info("Generating weekly report...")
        report_date = datetime.utcnow() - timedelta(days=1)
        await self._stats_global(self.channel, report_date)
        await self._leader_inner(self.channel, report_date)
        await self.bot.send_message(self.channel, self.DISP_STRINGS['report'])

    @task(is_unique=True)
    async def task_on_sprint_start(self):
        if not self.sprint_data.members:
            logger.warning("Cancelling sprint: no participants")
            await self._cancel_sprint(self.DISP_STRINGS['cancel_start'])
            return

        logger.info("Starting sprint...")
        self.set_state(SprintState.SPRINT)

        await self._display_embed(
            self.channel, self.DISP_EMBEDS['task_on_sprint_start'],
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            duration=format_seconds(self.sprint_data.duration),
            notif=self.role_sprint_mention,
            participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
        )
        self._save_sprint()

    @task(is_unique=False)
    async def task_on_sprint_warning(self):
        logger.info("Sending warning...")
        await self._display_embed(
            self.channel, self.DISP_EMBEDS['task_on_sprint_warning'],
            founder=self.sprint_data.founder.mention
            if self.sprint_data.founder else "None",
            remaining=format_seconds(self.sprint_data.remaining),
            notif=self.role_sprint_mention,
            participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
        )

    @task(is_unique=True)
    async def task_on_sprint_end(self):
        logger.info("Ending sprint...")
        self.set_state(SprintState.COLLECT_RESULTS)

        # if everyone's already finalized, give results now
        if set(self.sprint_data.start.keys()) == self.sprint_data.finalized:
            logger.info("All participants already finalised; scheduling results task...")
            await self._reset_sprint_tasks(True)
            self.state_tasks.append(self.scheduler.schedule_task_in(
                self.task_on_sprint_results, 0
            ))  # finalize NOW
        else:
            await self._display_embed(
                self.channel, self.DISP_EMBEDS['task_on_sprint_end'],
                founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
                finalize=format_seconds(self.finalize),
                notif=self.role_sprint_mention,
                participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
            )
        self._save_sprint()

    @task_on_sprint_start.error
    @task_on_sprint_warning.error
    @task_on_sprint_end.error
    async def task_error(self, e: Exception, i: TaskInstance):
        logger.exception("Error while executing sprint event task")
        self._save_sprint()

    @task(is_unique=True)
    async def task_on_sprint_results(self):
        logger.info("Finalize done; announcing results...")

        # update stats with this sprint's results
        stats = self.load_stats()
        stats.update(self.sprint_data)
        self.save_stats(stats)

        now = datetime.utcnow()
        w_stats = self.load_weekly_stats(now)
        w_stats.update(self.sprint_data)
        self.save_weekly_stats(now, w_stats)

        #
        # Prepare the output message
        #
        sorted_members = self.sprint_data.get_sorted_members()
        results = []
        for u in sorted_members:
            results.append('{} ({:d} words, {:.1f} wpm)'.format(
                u.mention, self.sprint_data.get_wordcount(u), self.sprint_data.get_wpm(u)))
        results_str = '\n'.join('{:d}. {}'.format(i+1, s) for i, s in enumerate(results))

        try:
            winner = self.sprint_data.find_winner()
            winner_name = winner.mention
            winner_wc = self.sprint_data.get_wordcount(winner)
        except ValueError:
            winner_name = 'nobody'
            winner_wc = 0

        await remove_role_from_all(self.bot, self.channel.server, self.role_sprint)
        logger.debug("Removed all users from {} role".format(self.role_sprint_name))

        await self._display_embed(
            self.channel, self.DISP_EMBEDS['task_on_sprint_results'],
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            winner=winner_name, wc=winner_wc,
            duration=format_seconds(self.sprint_data.duration),
            participants=results_str if results_str else 'None',
            notif=self.role_sprint_mention
        )

        logger.debug("Resetting sprint state...")
        self.set_state(SprintState.IDLE)
        self.sprint_data = SprintData()
        self._save_sprint()  # also calls self.state.write() - OK for stats too

    @task_on_sprint_results.error
    async def task_results_error(self, e: Exception, i: TaskInstance):
        logger.exception("Error while executing sprint event task")
        logger.debug("Resetting sprint state...")
        self.set_state(SprintState.IDLE)
        self.sprint_data = SprintData()
        self._save_sprint()

    @task_on_sprint_results.cancel
    async def task_results_cancel(self, i: TaskInstance):
        # should only happen when 'fast-forwarding' the results, after all participants finalise
        # so reverting is enough: no need to resched the results
        logger.info("Sprint results task cancelled: reverting state.")
        self.state.read()
        self._load_sprint()

    @start.error
    @stop.error
    @join.error
    @leave.error
    @wordcount.error
    @final.error
    async def sprint_on_error(self, exc, ctx: commands.Context):
        cmd_string = message_log_str(ctx.message)
        state = self.get_state()
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc

            # noinspection PyUnresolvedReferences
            if isinstance(root_exc, SprintRunningError):
                logger.warning("Cannot process command while sprint running: {}"
                    .format(cmd_string))

                if state is SprintState.PREPARE or state is SprintState.SPRINT:
                    if ctx.command is self.start:
                        msg = self.DISP_STRINGS["err_running_suggest_join"]
                    elif ctx.command is self.wordcount:
                        msg = self.DISP_STRINGS["err_running_wordcount"]
                    else:
                        msg = self.DISP_STRINGS["err_running_general"]
                elif state is SprintState.COLLECT_RESULTS:
                    msg = self.DISP_STRINGS["err_running_collect"]
                else:
                    logger.error("Invalid state??? {!r}".format(state))
                    msg = self.DISP_STRINGS["err_wtf"]

                await self.bot.send_message(ctx.message.channel, msg)

            elif isinstance(root_exc, SprintNotRunningError):
                logger.warning("Cannot process command without running sprint: {}"
                    .format(cmd_string))
                msg = self.DISP_STRINGS["err_not_running_general"]
                await self.bot.send_message(ctx.message.channel, msg)

            else:
                core_cog = self.bot.get_cog("CoreCog")
                await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

        elif isinstance(exc, UnauthorizedUserError):
            logger.warning("Unauthorized user (not founder or mod): {!s}"
                .format(ctx.message.author))
            msg = self.DISP_STRINGS["err_unauthorized_user"] \
                .format(self.sprint_data.founder.mention if self.sprint_data.founder else '?')
            await self.bot.send_message(ctx.message.channel, msg)

        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(WritingSprint(bot))
