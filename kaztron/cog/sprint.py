import asyncio
import copy
import enum
import logging
import math
from collections import deque
from datetime import datetime, timedelta
from functools import total_ordering
from typing import Dict, List, Callable, Tuple, Deque

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.cog.role_man import RoleManager
from kaztron.config import get_kaztron_config, get_runtime_config
from kaztron.errors import UnauthorizedUserError
from kaztron.theme import solarized
from kaztron.utils.checks import in_channels_cfg
from kaztron.utils.decorators import task_handled_errors
from kaztron.utils.discord import check_mod, get_named_role, remove_role_from_all
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import get_help_str, format_list, format_timedelta

logger = logging.getLogger(__name__)


class SprintError(RuntimeError):
    pass


class SprintNotRunningError(RuntimeError):
    pass


class SprintRunningError(RuntimeError):
    pass


def format_seconds(seconds: float, timespec='seconds'):
    return format_timedelta(timedelta(microseconds=int(seconds*1e6)), timespec=timespec)


@total_ordering
class SprintState(enum.Enum):
    IDLE = 0
    PREPARE = 10
    SPRINT = 20
    COLLECT_RESULTS = 30

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class SprintStats:
    def __init__(self):
        self.sprints = 0
        self.words = 0
        self.rate_sum = 0  # sum of writing rate (words/s) for each sprint
        self.time = 0
        self.wins = 0
        # cumulative quantity related to variance of rate for each sprint
        self.m2rate = 0

    def update(self, words: int, rate: float, time: int, winner=False):
        """
        Update the stats with info from a new sprint.

        For the M2/variance algorithm:
        https://en.wikipedia.org/w/index.php?title=Algorithms_for_calculating_variance&oldid=824616944#Online_algorithm

        :param words: Words written this sprint.
        :param rate: Rate (words per minute)
        :param time: Total time this sprint.
        :param winner: Whether the user associated to this record is the sprint winner.
        """
        if winner:
            self.wins += 1

        prev_rate_avg = self.rate_sum/self.sprints if self.sprints > 0 else 0

        self.sprints += 1
        self.words += words
        self.rate_sum += rate
        self.time += time

        next_rate_avg = self.rate_sum/self.sprints

        last_delta = rate - prev_rate_avg
        new_delta = rate - next_rate_avg

        self.m2rate = self.m2rate + last_delta * new_delta

    @property
    def words_mean(self):
        """ Number of words per sprint on average. """
        return self.words / self.sprints if self.sprints > 0 else 0

    @property
    def wpm_mean(self):
        """ Writing speed, average per sprint, in wpm. """
        return self.rate_sum / self.sprints if self.sprints > 0 else 0

    @property
    def wpm_stdev(self):
        """ Standard deviation of writing speed (wpm) over all sprints. """
        return math.sqrt(self.m2rate / (self.sprints - 1)) if self.sprints > 1 else 0

    @property
    def time_mean(self):
        """ Time per sprint, average, in minutes. """
        return (self.time / 60 / self.sprints) if self.sprints > 0 else 0

    @property
    def win_rate(self):
        """ Win rate as a fractional value (0 <= x <= 1). """
        return self.wins / self.sprints

    def to_dict(self):
        return {
            "sprints": self.sprints,
            "words": self.words,
            "rate_sum": self.rate_sum,
            "m2rate": self.m2rate,
            "time": self.time,
            "wins": self.wins
        }

    @classmethod
    def from_dict(cls, stats_dict: Dict):
        s = SprintStats()
        s.sprints = stats_dict.get('sprints', 0)
        s.words = stats_dict.get('words', 0)
        s.rate_sum = stats_dict.get('rate_sum', 0)
        s.m2rate = stats_dict.get('m2rate', 0)
        s.time = stats_dict.get('time', 0)
        s.wins = stats_dict.get('wins', 0)
        return s


class SprintData:
    def __init__(self, time_callback: Callable[[], float]):
        self.time_callback = time_callback
        self.founder = None  # type: discord.Member
        self.members = []  # type: List[discord.Member]

        # {user_id: start/end wordcounts}
        self.start = {}  # type: Dict[str, int]
        self.end = {}  # type: Dict[str, int]

        # loop times
        self.start_time = 0  # type: float
        self.end_time = 0  # type: float
        self.warn_times = deque()  # type: Deque[float]
        self.finalize_time = 0  # type: float

    def to_dict(self):
        return {
            'founder': self.founder.id if self.founder else None,
            'members': [u.id for u in self.members],
            'start': copy.deepcopy(self.start),
            'end': copy.deepcopy(self.end),
            'start_time': self._datetime(self.start_time).timestamp() if self.start_time else 0,
            'end_time': self._datetime(self.end_time).timestamp() if self.end_time else 0,
            'warn_times': [self._datetime(t).timestamp() for t in self.warn_times],
            'finalize_time': (
                self._datetime(self.finalize_time).timestamp() if self.finalize_time else 0
            ),
        }

    def _loop_time(self, timestamp: float) -> float:
        now_loop = self.time_callback()
        now_timestamp = datetime.utcnow().timestamp()
        return now_loop + (timestamp - now_timestamp)

    def _datetime(self, loop_time: float) -> datetime:
        return datetime.utcnow() + timedelta(seconds=loop_time - self.time_callback())

    @classmethod
    def from_dict(cls, time_callback: Callable[[], float], server: discord.Server, data: Dict):
        self = SprintData(time_callback)
        self.founder = server.get_member(data['founder'])
        member_uids = []
        for u_id in data['members']:
            member = server.get_member(u_id)
            if member is not None:
                self.members.append(member)
                member_uids.append(member.id)
            else:
                logger.warning("Can't restore member: ID {} not found on server".format(u_id))
        self.start = {u_id: value for u_id, value in data['start'].items() if u_id in member_uids}
        self.end = {u_id: value for u_id, value in data['end'].items() if u_id in member_uids}
        self.start_time = self._loop_time(data['start_time'])
        self.end_time = self._loop_time(data['end_time'])
        self.warn_times = deque(self._loop_time(t) for t in data['warn_times'])
        self.finalize_time = self._loop_time(data['finalize_time'])
        return self

    @property
    def start_dt(self):
        return self._datetime(self.start_time)

    @property
    def end_dt(self):
        return self._datetime(self.end_time)

    @property
    def warn_dts(self):
        for loop_time in self.warn_times:
            yield self._datetime(loop_time)

    @property
    def starts_in(self):
        return self.start_time - self.time_callback()

    @property
    def duration(self):
        return self.end_time - self.start_time

    @property
    def remaining(self):
        return min(self.duration, self.end_time - self.time_callback())

    @property
    def remaining_finalize(self):
        return self.finalize_time - self.time_callback()


class EmbedInfo:
    """
    Data container for display information (mostly strings) in Discord's Embeds.
    """
    def __init__(self, *, title: str, author: str=None, color: int, msg: str,
                 strings: List[Tuple[str, str, bool]]):
        self.title = title
        self.author = author
        self.color = color
        self.msg = msg
        self.strings = strings

    def __copy__(self):
        return EmbedInfo(
            title=self.title,
            author=self.author,
            color=self.color,
            msg=self.msg,
            strings=list(self.strings)
        )

    def __deepcopy__(self, memo):
        return EmbedInfo(
            title=copy.deepcopy(self.title, memo),
            author=copy.deepcopy(self.author, memo),
            color=copy.deepcopy(self.color, memo),
            msg=copy.deepcopy(self.msg, memo),
            strings=copy.deepcopy(self.strings, memo)
        )

    def __repr__(self):
        return "<EmbedInfo {}>".format(' '.join(
            '{!r}={!r}'.format(title, value) for title, value in [
                ('title', self.title),
                ('author', self.author),
                ('color', self.color),
                ('msg', self.msg),
            ] + [(title, value) for title, value, _ in self.strings]
        ))


class WritingSprint(KazCog):
    """
    Welcome to writing sprints, where everything's made up and the words don't matter!

    For help with this feature, please type `.help sprint`.
    """

    INLINE = True
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
        "on_sprint_start": EmbedInfo(
            title="Sprint start",
            color=DISP_COLORS[SprintState.SPRINT],
            msg="**The sprint is starting!** Get to writing! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Duration", "{duration}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "on_sprint_warning": EmbedInfo(
            title="Sprint reminder",
            color=solarized.orange,
            msg="**Sprint reminder!** {remaining!s} left. You better still be writing! {notif}",
            strings=[
                ("Started by", "{founder}", INLINE),
                ("Time remaining", "{remaining}", INLINE),
                ("Participants", "{participants}", INLINE)
            ]
        ),
        "on_sprint_end": EmbedInfo(
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
        "on_sprint_results": EmbedInfo(
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
            title="Leaderboards",
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
            title="Global Stats",
            color=DISP_COLORS["stats"],
            msg="",
            strings=[
                ("Sprints", "{stats.sprints:.0f}", INLINE),
                ("Total time",  "{total_time}", INLINE),
                ("Total words", "{stats.words:.0f} words", INLINE),
                ("Average sprint", "{average_time}", INLINE),
                ("Average cumulative productivity",
                 "{stats.wpm_mean:.1f} wpm overall (σ = {stats.wpm_stdev:.1f})", INLINE)
            ]
        ),
        "stats": EmbedInfo(
            title=discord.Embed.Empty,
            color=DISP_COLORS["stats"],
            msg="",
            strings=[
                ("User Stats", "<@{user_id}>", not INLINE),
                ("Sprints", "{stats.sprints:.0f}", INLINE),
                ("Wins", "{stats.wins:.0f} ({stats.win_rate:.0%})", INLINE),
                ("Total time",  "{total_time}", INLINE),
                ("Total words", "{stats.words:.0f} words", INLINE),
                ("Average sprint", "{average_time}", INLINE),
                ("Average speed",
                 "{stats.wpm_mean:.1f} wpm (σ = {stats.wpm_stdev:.1f})", INLINE),
            ]
        ),
    }

    DISP_STRINGS = {
        "join": "{mention} You have joined the sprint with an initial wordcount of {wc:d} words! "
                "Have fun writing!",
        "rejoin": "{mention} Updated your initial wordcount to {wc:d} words.",
        "leave": "{mention} You have left the writing sprint! Sorry you can't stick around.",
        "leave_error": "{mention} You're not in the writing sprint!",
        "wordcount": "{mention} Your wordcount has been recorded.",
        "wordcount_error": "{mention} You're not in the writing sprint!",

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

    TICK_INTERVAL = 15

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults(
            'sprint',
            state=SprintState.IDLE.value,
            sprint_data=SprintData(self._get_time).to_dict(),
            stats_global=SprintStats().to_dict(),
            stats_users={}
        )

        self.channel_id = self.config.get('sprint', 'channel')
        self.channel = None
        self.dest_output_id = self.config.get('discord', 'channel_output')
        self.dest_output = discord.Object(id=self.dest_output_id)

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

        self.sprint_data = SprintData(self._get_time)
        self.state_task = None

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
        # state is always directly read from the config, so no need to set it here
        if self.get_state() is not SprintState.IDLE:
            try:
                self.sprint_data = SprintData.from_dict(self._get_time, self.channel.server,
                    self.state.get('sprint', 'sprint_data'))
            except KeyError:
                logger.warning("Old sprint data incorrectly formatted, ignoring")

    def _get_time(self) -> float:
        """ Convenience function: get the current event loop time, in seconds. """
        return self.bot.loop.time()

    async def _display_embed(self, dest, embed_info: EmbedInfo, *args, **kwargs):
        """ Convenience function: display an embed from the EmbedInfo """
        em = discord.Embed(title=embed_info.title, color=embed_info.color)

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
            logger.warning("Cannot find role: " + self.role_follow_name)
            self.role_follow = None
            self.role_follow_mention = ''

        try:
            self.role_sprint = get_named_role(server, self.role_sprint_name)
            self.role_sprint_mention = self.role_sprint.mention
        except ValueError:
            logger.warning("Cannot find role: " + self.role_sprint_name)
            self.role_sprint = None
            self.role_sprint_mention = ''

    async def _cancel_sprint(self, msg: str=None):
        """
        Utility method: cancels the current sprint, if one is running
        """
        if self.state_task and self.state_task is not asyncio.Task.current_task():
            self.state_task.cancel()
            self.state_task = None

        old_participants = self._format_wordcount_list(self.sprint_data.start)
        self.set_state(SprintState.IDLE)
        self.sprint_data = SprintData(self._get_time)
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
        logger.debug("Validating sprint channel...")
        self.channel = self.bot.get_channel(self.channel_id)
        if self.channel is None:
            err_msg = "Channel does not exist: {}".format(self.channel_id)
            logger.warning(err_msg)
            try:
                await self.bot.send_message(self.dest_output, err_msg)
            except discord.HTTPException:
                logger.exception("Error sending error to {}".format(self.dest_output_id))

        state = self.get_state()
        if state is not SprintState.IDLE:
            logger.info("Loading previous sprint data...")
            self._load_sprint()

        self._update_roles()

        roleman = self.bot.get_cog("RoleManager")  # type: RoleManager
        if roleman:
            try:
                roleman.add_managed_role(
                    role_name=self.role_follow_name,
                    join="follow",
                    leave="unfollow",
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
        else:
            err_msg = "Cannot find RoleManager - is it enabled in config?"
            logger.error(err_msg)
            try:
                await self.bot.send_message(self.dest_output, err_msg)
            except discord.HTTPException:
                logger.exception("Error sending error to {}".format(self.dest_output_id))

        logger.info("Restoring task for current state...")
        if self.state_task:  # in case this isn't the first time on_ready is called (reconnect)
            self.state_task.cancel()

        if state is SprintState.IDLE:
            logger.info("No sprint, no task needs restoring.")
        elif state is SprintState.PREPARE:
            self.state_task = self.bot.loop.create_task(self.on_sprint_start())
        elif state is SprintState.SPRINT:
            if self.sprint_data.warn_times:
                self.state_task = self.bot.loop.create_task(self.on_sprint_warning())
            else:
                self.state_task = self.bot.loop.create_task(self.on_sprint_end())
        elif state is SprintState.COLLECT_RESULTS:
            self.state_task = self.bot.loop.create_task(self.on_sprint_results())

        await super().on_ready()

    @commands.group(invoke_without_command=True, pass_context=True, aliases=['w'])
    @in_channels_cfg('sprint', 'channel')
    async def sprint(self, ctx: commands.Context, *, extra: str=None):
        """
        Welcome to writing sprints, where everything's made up and the words don't matter!

        In writing sprints (a.k.a. word wars), you get together with a group of other server members
        and write for a fixed amount of time, usually 15 or 30 minutes, on whatever project you
        choose.

        At the end of the sprint, you report your word count, and whoever wrote the most wins!
        Not that they matter. Because you got some writing done. So you're always a winner.

        Writing sprints are a great way of getting you to focus on your writing with a group of
        other people. And, y'know, not just chatting with them the entire time when you told
        yourself you'd get some writing done this evening.

        Get writing!
        """
        logger.info("sprint: {}".format(message_log_str(ctx.message)))
        command_list = list(self.sprint.commands.keys())
        if not extra:
            err_prefix = "Sorry, I don't know that command. "
        else:
            err_prefix = ""
        await self.bot.say((err_prefix + "Valid subcommands are {0!s}. "
                            'For help with sprints, type `{1}` or `{1} <subcommand>`.')
            .format(command_list, get_help_str(ctx)))

    @sprint.command(pass_context=True, ignore_extra=False, aliases=['?'])
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def status(self, ctx: commands.Context):
        """
        Get the current status of the sprint.
        """
        logger.info("status: {}".format(message_log_str(ctx.message)))
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
            await self.bot.send_message(
                self.dest_output,
                "status: Unknown modnotes state {!r} - probably a bug somewhere!"
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
        """
        Start a new sprint.

        After starting the sprint, you need to join the sprint with .w join in order to specify your
        initial wordcount.

        Arguments:
        * duration: Optional. The amount of time, in minutes, for the sprint to last.
          Default: 25 minutes.
        * delay: Optional. The amount of time, in minutes, to wait before starting the sprint.
          Default: 5 minutes.

        Examples:
            .w start - Create a 25 minute sprint, starting in 5 minutes.
            .w start 15 - Create a 15-minute sprint, starting in 5 minutes.
            .w start 25 1 - Create a 25-minute sprint, starting in 1 minute.
        """
        logger.debug("start: {}".format(message_log_str(ctx.message)))
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
        sprint = SprintData(self._get_time)
        sprint.founder = ctx.message.author
        sprint.start_time = self._get_time() + delay_s
        sprint.end_time = sprint.start_time + duration_s
        sprint.finalize_time = sprint.end_time + self.finalize

        # For now, warnings only in the last 1 minute, if sprint at least 10 minutes
        # if sprint.duration >= 600:
        #     sprint.warn_times.append(sprint.end_time - 60)
        self.sprint_data = sprint

        # Set up events
        self.state_task = self.bot.loop.create_task(self.on_sprint_start())

        self._update_roles()
        await self._display_embed(
            self.channel, self.DISP_EMBEDS['start'],
            founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
            duration=format_seconds(duration_s),
            delay=format_seconds(delay_s),
            notif=self.role_follow_mention
        )

        self._save_sprint()

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['x'])
    @in_channels_cfg('sprint', 'channel')
    async def stop(self, ctx: commands.Context):
        """
        Cancel the current sprint.

        This can only be done by the creator of the sprint or moderators, and only if a sprint is
        ongoing or is about to start.
        """
        logger.info("stop: {}".format(message_log_str(ctx.message)))
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

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['j'])
    @in_channels_cfg('sprint', 'channel')
    async def join(self, ctx: commands.Context, wordcount: int):
        """
        Join a sprint and set your initial wordcount.

        You can also use this command to fix your initial wordcount, if you made a mistake when
        initially joining the sprint.

        This will only work if a sprint is ongoing or has been created with .w start.

        Arguments:
        * <wordcount>: Required. Your initial wordcount, before the start of the sprint. When you
          report your wordcount at the end of the sprint, your total words written during the sprint
          will automatically be calculated.

        Example:
            .w join 12044 - Join the sprint with an initial wordcount of 12,044 words.
        """
        logger.info("join: {}".format(message_log_str(ctx.message)))
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
            logger.info("User {} updated initial wc to {:d} words".format(user.name, wordcount))
            self.sprint_data.start[user.id] = wordcount
            await self.bot.say(self.DISP_STRINGS['rejoin']
                .format(mention=user.mention, wc=wordcount))
            self._save_sprint()

    @sprint.command(pass_context=True, ignore_extra=False, no_pm=True, aliases=['l'])
    @in_channels_cfg('sprint', 'channel')
    async def leave(self, ctx: commands.Context):
        """
        Leave a sprint you previously joined.

        You should normally only need to use this if you realise you can't stay for the entire
        sprint, or otherwise can't participate in the sprint.
        """
        logger.info("leave: {}".format(message_log_str(ctx.message)))
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
    async def wordcount(self, ctx, count: int):
        """
        Report your wordcount at the end of the sprint.

        Arguments:
        * <wordcount>: Required. Your final wordcount at the end of the sprint. The bot will
          automatically calculate your total words written during the sprint.

        Example:
            .w c 12888 - Report that your wordcount at the end of the sprint is 12888.
        """
        logger.info("wordcount: {}".format(message_log_str(ctx.message)))
        state = self.get_state()
        if state is SprintState.IDLE:
            raise SprintNotRunningError()
        elif state is SprintState.PREPARE or state is SprintState.SPRINT:
            raise SprintRunningError()

        user = ctx.message.author

        if user.id in self.sprint_data.start:
            logger.info("User {} set final wordcount {:d}".format(user.name, count))
            self.sprint_data.end[user.id] = count
            await self.bot.say(self.DISP_STRINGS['wordcount']
                .format(mention=user.mention, wc=count))

            # If everyone has submitted, fast forward
            if set(self.sprint_data.start.keys()) == set(self.sprint_data.end.keys()):
                logger.info("All wordcounts submitted. Fast-forwarding to result announcement.")
                self.state_task.cancel()
                self.sprint_data.finalize_time = self._get_time()  # finalize NOW
                self.state_task = self.bot.loop.create_task(self.on_sprint_results())
            else:
                self._save_sprint()
        else:
            logger.warning("Cannot set wordcount: user {} not in sprint".format(user.name))
            await self.bot.say(self.DISP_STRINGS['wordcount_error'].format(user.mention))

    @sprint.command(pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def leader(self, ctx):
        """
        Show the leaderboards.
        """
        logger.info("leader: {}".format(message_log_str(ctx.message)))
        entry_user_map = {uid: SprintStats.from_dict(d)
                          for uid, d in self.state.get('sprint', 'stats_users').items()}
        entries_by_t = sorted(entry_user_map.items(), key=lambda e: e[1].time, reverse=True)
        entries_by_w = sorted(entry_user_map.items(), key=lambda e: e[1].words, reverse=True)
        entries_by_wpm = sorted(entry_user_map.items(), key=lambda e: e[1].wpm_mean, reverse=True)
        entries_by_wins = sorted(entry_user_map.items(), key=lambda e: e[1].wins, reverse=True)

        list_by_t = ["<@{}>: {:.1f} hours".format(uid, s.time/3600)
                     for uid, s in entries_by_t[:self.MAX_LEADERS]]
        list_by_w = ["<@{}>: {:d} words".format(uid, s.words)
                     for uid, s in entries_by_w[:self.MAX_LEADERS]]
        list_by_wpm = ["<@{}>: {:.1f} wpm".format(uid, s.wpm_mean)
                       for uid, s in entries_by_wpm[:self.MAX_LEADERS]]
        list_by_wins = ["<@{}>: {:d} wins".format(uid, s.wins)
                       for uid, s in entries_by_wins[:self.MAX_LEADERS]]

        await self._display_embed(
            ctx.message.channel, self.DISP_EMBEDS['leader'],
            leaders_time=format_list(list_by_t) or "None",
            leaders_words=format_list(list_by_w) or "None",
            leaders_wpm=format_list(list_by_wpm) or "None",
            leaders_wins=format_list(list_by_wins) or "None"
        )

    @sprint.command(pass_context=True, ignore_extra=False)
    @in_channels_cfg('sprint', 'channel', allow_pm=True)
    async def stats(self, ctx, user: discord.Member=None):
        """
        Show stats, either global or per-user.

        Arguments:
        * [user]: Optional. An @mention of the user to look up. If not specified, shows global
          stats.
        """
        logger.info("stats: {}".format(message_log_str(ctx.message)))

        if user:
            logger.debug("stats: user: id={user.id} name={user.name}".format(user=user))
            try:
                stats = SprintStats.from_dict(self.state.get('sprint', 'stats_users')[user.id])
            except KeyError:
                await self.bot.say(self.DISP_STRINGS["err_stats_user"].format(user=user))
            else:
                await self._display_embed(
                    ctx.message.channel, self.DISP_EMBEDS['stats'],
                    user_id=user.id,
                    stats=stats,
                    average_time=format_seconds(stats.time_mean),
                    total_time=format_seconds(stats.time, timespec='minutes')
                )
        else:  # global stats
            logger.debug("stats: requested global")
            stats = SprintStats.from_dict(self.state.get('sprint', 'stats_global'))
            await self._display_embed(
                ctx.message.channel, self.DISP_EMBEDS['stats_global'],
                stats=stats,
                average_time=format_seconds(stats.time_mean),
                total_time=format_seconds(stats.time, timespec='minutes')
            )

    @task_handled_errors
    async def on_sprint_start(self):
        wait_time = self.sprint_data.start_time - self._get_time()
        logger.debug("Waiting for sprint start ({:.1f}s)...".format(wait_time))
        await asyncio.sleep(wait_time)

        if not self.sprint_data.members:
            logger.warning("Cancelling sprint: no participants")
            await self._cancel_sprint(self.DISP_STRINGS['cancel_start'])
            return

        logger.info("Starting sprint...")
        self.set_state(SprintState.SPRINT)

        try:
            await self._display_embed(
                self.channel, self.DISP_EMBEDS['on_sprint_start'],
                founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
                duration=format_seconds(self.sprint_data.duration),
                notif=self.role_sprint_mention,
                participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
            )
        finally:
            logger.debug("Scheduling on_sprint_warning")
            self.state_task = self.bot.loop.create_task(self.on_sprint_warning())
            self._save_sprint()

    @task_handled_errors
    async def on_sprint_warning(self):
        while self.sprint_data.warn_times:
            wait_time = self.sprint_data.warn_times[0] - self._get_time()
            logger.debug("Waiting for next warning time ({:.1f}s)...".format(wait_time))
            await asyncio.sleep(wait_time)

            logger.info("Sending warning...")
            self.sprint_data.warn_times.popleft()

            # noinspection PyBroadException
            try:
                await self._display_embed(
                    self.channel, self.DISP_EMBEDS['on_sprint_warning'],
                    founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
                    remaining=format_seconds(self.sprint_data.remaining),
                    notif=self.role_sprint_mention,
                    participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error while issuing warning; ignoring")
            finally:
                self._save_sprint()
        logger.debug("Warnings done. Scheduling on_sprint_end")
        self.state_task = self.bot.loop.create_task(self.on_sprint_end())

    @task_handled_errors
    async def on_sprint_end(self):
        wait_time = self.sprint_data.end_time - self._get_time()
        logger.debug("Waiting for sprint end ({:.1f}s)...".format(wait_time))
        await asyncio.sleep(wait_time)

        logger.info("Ending sprint...")
        self.set_state(SprintState.COLLECT_RESULTS)

        try:
            await self._display_embed(
                self.channel, self.DISP_EMBEDS['on_sprint_end'],
                founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
                finalize=format_seconds(self.finalize),
                notif=self.role_sprint_mention,
                participants='\n'.join(self._format_wordcount_list(self.sprint_data.start))
            )
        finally:
            logger.debug("Scheduling on_sprint_results")
            self.state_task = self.bot.loop.create_task(self.on_sprint_results())
            self._save_sprint()

    @task_handled_errors
    async def on_sprint_results(self):
        wait_time = self.sprint_data.finalize_time - self._get_time()
        logger.debug("Waiting for sprint finalize time ({:.1f}s)...".format(wait_time))
        await asyncio.sleep(wait_time)

        try:
            logger.info("Finalize done; announcing results...")

            results_struct = {}  # type: Dict[discord.User, Tuple[int, float]]
            for u in self.sprint_data.members:
                try:
                    wc = self.sprint_data.end[u.id] - self.sprint_data.start[u.id]
                    rate = wc/(self.sprint_data.duration/60)
                    results_struct[u] = (wc, rate)
                except KeyError:
                    logger.warning("User {!s} did not submit a wordcount".format(u))
                    results_struct[u] = (0, 0.0)

            results_list = sorted(results_struct.items(), key=lambda kv: kv[1][0], reverse=True)
            results = ['{} ({:d} words, {:.1f} wpm)'.format(u.mention, v[0], v[1])
                       for u, v in results_list]
            results_str = '\n'.join('{:d}. {}'.format(i+1, s) for i, s in enumerate(results))

            if results_list:
                winner, winner_info = results_list[0]
                winner_id = winner.id
                winner_name = winner.name
                winner_wc = winner_info[0]
            else:
                winner_id = None
                winner_name = 'nobody'
                winner_wc = 0

            # update stats with this sprint
            self.update_stats(results_struct, winner_id)

            await remove_role_from_all(self.bot, self.channel.server, self.role_sprint)
            logger.debug("Removed all users from {} role".format(self.role_sprint_name))

            await self._display_embed(
                self.channel, self.DISP_EMBEDS['on_sprint_results'],
                founder=self.sprint_data.founder.mention if self.sprint_data.founder else "None",
                winner=winner_name, wc=winner_wc,
                duration=format_seconds(self.sprint_data.duration),
                participants=results_str if results_str else 'None',
                notif=self.role_sprint_mention
            )

        finally:
            logger.debug("Resetting sprint state...")
            self.set_state(SprintState.IDLE)
            self.sprint_data = SprintData(self._get_time)
            self._save_sprint()  # also calls self.state.write() - OK for stats too

    def update_stats(self, results: Dict[discord.User, Tuple[int, float]], winner_id: str):
        """
        Update stats with the current sprint_data (should be a finished sprint!).
        Won't save - you need to call self.state.write()
        """
        duration = int(round(self.sprint_data.duration))
        total_words = 0
        total_rate = 0

        stats_users_map = self.state.get('sprint', 'stats_users')
        for u, result in results.items():
            try:
                stats_user = SprintStats.from_dict(stats_users_map[u.id])
            except KeyError:
                stats_user = SprintStats()
            stats_user.update(
                words=result[0],
                rate=result[1],
                time=duration,
                winner=(winner_id == u.id)
            )
            total_words += result[0]
            total_rate += result[1]
            stats_users_map[u.id] = stats_user.to_dict()

        stats_global = SprintStats.from_dict(self.state.get('sprint', 'stats_global'))
        stats_global.update(
            words=total_words,
            rate=total_rate,
            time=duration,
            winner=False  # not meaningful for global stats
        )

        self.state.set('sprint', 'stats_global', stats_global.to_dict())
        self.state.set('sprint', 'stats_users', stats_users_map)

    @start.error
    @stop.error
    @join.error
    @leave.error
    @wordcount.error
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
