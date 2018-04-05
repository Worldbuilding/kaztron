import copy
import enum
import logging
from datetime import datetime, timedelta

import discord
from collections import deque
from functools import total_ordering
from typing import Dict, Callable, List, Tuple

from kaztron.driver.stats import MeanVarianceAccumulator
from kaztron.utils.datetime import utctimestamp

logger = logging.getLogger(__name__)


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
        self.words = 0
        self.time = 0
        self.wins = 0
        self.rate_acc = MeanVarianceAccumulator()
        self.since = datetime.utcnow()

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
        self.words += words
        self.time += time
        self.rate_acc.update(rate)

    @property
    def sprints(self):
        return self.rate_acc.count

    @property
    def words_mean(self):
        """ Number of words per sprint on average. """
        return self.words / self.sprints if self.sprints > 0 else 0

    @property
    def wpm_mean(self):
        """ Writing speed, average per sprint, in wpm. """
        return self.rate_acc.mean

    @property
    def wpm_stdev(self):
        """ Standard deviation of writing speed (wpm) over all sprints. """
        return self.rate_acc.std_dev

    @property
    def time_mean(self):
        """ Time per sprint, average, in seconds. """
        return (self.time / self.sprints) if self.sprints > 0 else 0

    @property
    def win_rate(self):
        """ Win rate as a fractional value (0 <= x <= 1). """
        return self.wins / self.sprints

    def to_dict(self):
        return {
            "words": self.words,
            "rate_acc": self.rate_acc.dump_state(),
            "time": self.time,
            "wins": self.wins,
            "since": utctimestamp(self.since)
        }

    @classmethod
    def from_dict(cls, stats_dict: Dict):
        s = SprintStats()
        s.words = stats_dict.get('words', 0)
        s.rate_acc = MeanVarianceAccumulator(*stats_dict.get('rate_acc'))
        s.time = stats_dict.get('time', 0)
        s.wins = stats_dict.get('wins', 0)
        s.since = datetime.utcfromtimestamp(stats_dict.get('since', 0))
        return s


class SprintUserStats:
    def __init__(self):
        self.overall = SprintStats()
        self.users = {}  # type: Dict[str, SprintStats]

    def update(self, data: 'SprintData'):
        duration = int(round(data.duration))
        total_words = 0
        total_rate = 0

        for u in data.members:
            try:
                stats_user = self.users[u.id]
            except KeyError:
                stats_user = SprintStats()
                self.users[u.id] = stats_user

            winner_id = data.find_winner().id
            stats_user.update(
                words=data.get_wordcount(u),
                rate=data.get_wpm(u),
                time=duration,
                winner=(winner_id == u.id)
            )
            total_words += data.get_wordcount(u)
            total_rate += data.get_wpm(u)

        self.overall.update(
            words=total_words,
            rate=total_rate,
            time=duration,
            winner=False  # not meaningful for global stats
        )

    def clear_overall(self):
        self.overall = SprintStats()

    def clear_user(self, user: discord.User):
        del self.users[user.id]

    def to_dict(self):
        return {
            'global': self.overall.to_dict(),
            'users': {u: s.to_dict() for u, s in self.users.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict):
        self = cls()
        self.overall = SprintStats.from_dict(data['global'])
        self.users = {u: SprintStats.from_dict(d) for u, d in data['users'].items()}
        return self


class SprintData:
    def __init__(self, time_callback: Callable[[], float]):
        self.time_callback = time_callback
        self.founder = None  # type: discord.Member
        self.members = []  # type: List[discord.Member]

        # {user_id: start/end wordcounts}
        self.start = {}  # type: Dict[str, int]
        self.end = {}  # type: Dict[str, int]
        self.finalized = set()

        # loop times
        self.start_time = 0  # type: float
        self.end_time = 0  # type: float
        self.warn_times = deque()  # type: deque[float]
        self.finalize_time = 0  # type: float

    def to_dict(self):
        return {
            'founder': self.founder.id if self.founder else None,
            'members': [u.id for u in self.members],
            'start': copy.deepcopy(self.start),
            'end': copy.deepcopy(self.end),
            'finalized': list(self.finalized),
            'start_time': utctimestamp(self._datetime(self.start_time)) if self.start_time else 0,
            'end_time': utctimestamp(self._datetime(self.end_time)) if self.end_time else 0,
            'warn_times': [self._datetime(t).timestamp() for t in self.warn_times],
            'finalize_time': (
                utctimestamp(self._datetime(self.finalize_time)) if self.finalize_time else 0
            ),
        }

    def _loop_time(self, timestamp: float) -> float:
        now_loop = self.time_callback()
        now_timestamp = utctimestamp(datetime.utcnow())
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
        self.finalized = set(data['finalized'])
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

    def get_wordcount(self, user: discord.Member):
        try:
            return self.end[user.id] - self.start[user.id]
        except KeyError:
            return 0

    def get_wpm(self, user: discord.Member):
        return self.get_wordcount(user) / (self.duration / 60)

    def find_winner(self):
        return max(self.members, key=lambda u: self.get_wordcount(u))

    def get_sorted_members(self):
        """ Get members sorted by wordcount. """
        return sorted(self.members, key=lambda m: self.get_wordcount(m), reverse=True)


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

    # noinspection PyArgumentList
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
