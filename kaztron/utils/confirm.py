import logging
from datetime import datetime, timedelta
from typing import Any, Dict

import discord
from discord.ext import commands

from kaztron.utils.datetime import utctimestamp

__all__ = ['ConfirmManager', 'REQUEST', 'CONFIRM']

logger = logging.getLogger(__name__)


class ConfirmData:
    @classmethod
    def from_dict(cls, data: dict):
        o = cls()
        o.user = data['user_id']
        o.timestamp = datetime.utcfromtimestamp(data['timestamp'])
        o.data = data['data']
        return o

    def __init__(self):
        self.user_id = None  # type: str
        self.timestamp = None  # type: datetime
        self.data = None  # type: Any

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'timestamp': utctimestamp(self.timestamp),
            'data': self.data
        }


REQUEST = 0
CONFIRM = 1


class ConfirmManager:
    """
    Manages logic for commands that need to be confirmed before an action is executed, and similar
    situations. This manager tracks the user who invoked the command, the time of the command, and
    any additional data; it can also auto-timeout a command if no confirmation is given (either
    when :meth:`~.check_timeouts()` is called or when that user is accessed again).

    This class can be serialised to JSON if and only if the data passed to requests is JSON
    serialisable. Use :meth:`~.to_dict` and :meth:`~.from_dict` to get and restore from a
    serialisable dict.

    :param timeout: Timeout in seconds. None for no timeout. Default: None.
    """
    @classmethod
    def from_dict(cls, data: dict):
        o = cls(data['timeout'])
        for uid, cd_data in data['user_map'].items():
            o.user_map[uid] = ConfirmData.from_dict(cd_data)
        return o

    def __init__(self, timeout: int=None):
        self.timeout = timedelta(seconds=timeout) if timeout is not None else None
        self.user_map = {}  # type: Dict[str, ConfirmData]

    def has_request(self, user: discord.Member):
        """ Check if a user has an outstanding request. """
        self.purge(user)
        return user.id in self.user_map

    def request(self, ctx: commands.Context, data=None):
        """
        Save a request that needs to be confirmed.

        :param ctx: Command context that triggered this request.
        :param data: Any data to store with the request.
        :raise KeyError: User already has an outstanding request.
        """
        self.purge(ctx.message.author)
        if not self.has_request(ctx.message.author):
            d = ConfirmData()
            d.user_id = ctx.message.author.id
            d.timestamp = ctx.message.timestamp
            d.data = data
            self.user_map[ctx.message.author.id] = d
        else:
            raise KeyError("User has outstanding request.")

    def confirm(self, ctx: commands.Context) -> Any:
        """
        Delete the request and return the data that was saved with it (if any).

        :param ctx: Command context that triggered this confirmation.
        :return: The data originally stored with the request.
        :raise KeyError: User has no outstanding request.
        """
        self.purge(ctx.message.author)
        data = self.user_map[ctx.message.author.id].data
        del self.user_map[ctx.message.author.id]
        return data

    def request_confirm(self, ctx: commands.Context, data=None) -> Any:
        """
        For cases where the request and confirmation are the same command.
        :param ctx: Command context that triggered this confirmation.
        :param data:
        :return: Tuple. 0 = whether this is interpreted as a REQUEST or CONFIRM. 1 = the data passed
            at the request time, or None.
        """
        self.purge(ctx.message.author)
        try:
            self.request(ctx, data)
            return REQUEST, data
        except KeyError:
            return CONFIRM, self.confirm(ctx)

    def purge(self, member: discord.Member):
        if self.timeout is None:
            return
        try:
            if datetime.utcnow() - self.user_map[member.id].timestamp > self.timeout:
                del self.user_map[member.id]
        except KeyError:
            pass  # oh well

    def purge_all(self):
        if self.timeout is None:
            return
        now = datetime.utcnow()
        purge_uids = []
        for uid, cd in self.user_map.items():
            if now - cd.timestamp > self.timeout:
                purge_uids.append(uid)
        for uid in purge_uids:
            del self.user_map[uid]

    def to_dict(self):
        return {
            'timeout': self.timeout.total_seconds(),
            'user_map': {uid: cd.to_dict() for uid, cd in self.user_map.items()}
        }
