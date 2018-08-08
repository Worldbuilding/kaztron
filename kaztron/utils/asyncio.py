import asyncio
from datetime import datetime

from kaztron.utils.datetime import utctimestamp


def loop2timestamp(loop_time: float, loop: asyncio.AbstractEventLoop=None) -> float:
    if loop is None:
        loop = asyncio.get_event_loop()
    now_loop = loop.time()
    now_timestamp = utctimestamp(datetime.utcnow())
    return now_timestamp + (loop_time - now_loop)


def timestamp2loop(timestamp: float, loop: asyncio.AbstractEventLoop=None) -> float:
    if loop is None:
        loop = asyncio.get_event_loop()
    now_loop = loop.time()
    now_timestamp = utctimestamp(datetime.utcnow())
    return now_loop + (timestamp - now_timestamp)


def loop2datetime(loop_time: float, loop: asyncio.AbstractEventLoop=None) -> datetime:
    return datetime.utcfromtimestamp(loop2timestamp(loop_time, loop))


def datetime2loop(dt: datetime, loop: asyncio.AbstractEventLoop=None) -> float:
    return timestamp2loop(utctimestamp(dt), loop)
