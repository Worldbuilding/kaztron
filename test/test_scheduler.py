from datetime import datetime, timedelta
from types import MethodType

import pytest

import asyncio

from kaztron.scheduler import Scheduler, task


class MockTaskFunction:
    def __init__(self, loop):
        self.calls = []
        self.err = None
        self.cancelled_at = 0
        self.loop = loop

    @task(is_unique=True)
    async def my_task(self):
        self.calls.append(self.loop.time())

    @task(is_unique=True)
    async def err_task(self):
        self.calls.append(self.loop.time())
        raise ValueError("blah")

    @my_task.error
    @err_task.error
    async def eh(self, e):
        self.err = (e, self.loop.time())

    @my_task.cancel
    @err_task.cancel
    async def ch(self):
        self.cancelled_at = self.loop.time()


@pytest.fixture
def scheduler(mocker):
    bot = mocker.Mock()
    bot.loop = asyncio.get_event_loop()

    async def dispatch(self, *args, **kwargs):
        self.dispatched = (args, kwargs)

    bot.dispatch = MethodType(dispatch, bot)
    bot.dispatched = None
    return Scheduler(bot)


def test_single_run_dt(scheduler):
    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.8
    start = mock_task.loop.time()
    dt = datetime.utcnow() + timedelta(seconds=delay)
    scheduler.schedule_task_at(mock_task.my_task, dt)
    scheduler.loop.run_until_complete(asyncio.sleep(2))
    assert len(mock_task.calls) == 1
    assert (delay - 0.05) <= mock_task.calls[0] - start <= (delay + 0.05)


def test_single_run_in_float(scheduler):
    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.8
    start = mock_task.loop.time()
    scheduler.schedule_task_in(mock_task.my_task, delay)
    scheduler.loop.run_until_complete(asyncio.sleep(2))
    assert len(mock_task.calls) == 1
    assert (delay - 0.05) <= mock_task.calls[0] - start <= (delay + 0.05)


def test_single_run_in_delta(scheduler):
    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.8
    start = mock_task.loop.time()
    scheduler.schedule_task_in(mock_task.my_task, timedelta(seconds=delay))
    scheduler.loop.run_until_complete(asyncio.sleep(2))
    assert len(mock_task.calls) == 1
    assert (delay - 0.05) <= mock_task.calls[0] - start <= (delay + 0.05)


def test_recurring_in_float(scheduler):
    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.8
    increment = 0.5
    start = mock_task.loop.time()
    scheduler.schedule_task_in(mock_task.my_task, delay, every=increment, times=4)
    scheduler.loop.run_until_complete(asyncio.sleep(5))
    assert len(mock_task.calls) == 4
    for i in range(4):
        target_time = delay + i*increment
        assert (target_time - 0.05) <= mock_task.calls[i] - start <= (target_time + 0.05)


def test_cancel(scheduler):
    cancel_at = 0.4

    async def canceller(inst):
        await asyncio.sleep(cancel_at)
        inst.cancel()
        await asyncio.sleep(1)

    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.8
    start = mock_task.loop.time()
    instance = scheduler.schedule_task_in(mock_task.my_task, delay)
    scheduler.loop.run_until_complete(canceller(instance))
    assert len(mock_task.calls) == 0
    assert mock_task.cancelled_at != 0  # check that a cancellation happened
    assert (cancel_at - 0.05) <= mock_task.cancelled_at - start <= (cancel_at + 0.05)


def test_error(scheduler):
    mock_task = MockTaskFunction(scheduler.loop)
    delay = 0.4
    start = mock_task.loop.time()
    scheduler.schedule_task_in(mock_task.err_task, delay)
    scheduler.loop.run_until_complete(asyncio.sleep(1))
    assert scheduler.bot.dispatched is not None
    assert len(mock_task.calls) == 1
    assert isinstance(mock_task.err[0], ValueError) and mock_task.err[0].args[0] == 'blah'
    assert (delay - 0.05) <= mock_task.err[1] - start <= (delay + 0.05)


def test_task_cleanup(scheduler):
    @task()
    async def a():
        pass

    scheduler.schedule_task_in(a, 0.1)
    scheduler.loop.run_until_complete(asyncio.sleep(0.2))
    assert a not in scheduler.tasks
