import asyncio
import logging
from collections.abc import Hashable
from datetime import datetime, timedelta
from typing import Callable, Union, Tuple, Dict, Awaitable

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.asyncio import datetime2loop

logger = logging.getLogger(__name__)


TaskInstance = Tuple['Task', float]
TaskFunction = Callable[[], Awaitable[None]]  #: async def name() -> None


class Task(Hashable):
    """
    Class that implements scheduled tasks. This should not be instantiated directly, but using the
    :func:`~.task` decorator.

    :param callback: A callback coroutine.
    :param is_unique: If True, this task can only be scheduled once at a time (includes recurring).
        If False, this task can be scheduled to run multiple times in the future.
    """
    def __init__(self, callback: TaskFunction, is_unique=True):
        if not asyncio.iscoroutinefunction(callback):
            raise discord.ClientException("Task callback must be a coroutine.")

        self.callback = callback
        self.is_unique = is_unique
        self.cog = None  # type: KazCog
        self.on_error = None  # type: Callable[[Exception], Awaitable[None]]
        self.on_cancel = None  # type: Callable[[], Awaitable[None]]

    def __get__(self, cog, owner):
        if cog is not None:
            self.cog = cog
        return self

    async def execute(self):
        if self.cog:
            await self.callback(self.cog)
        else:
            await self.callback()

    def error(self, coro: Callable[[Exception], Awaitable[None]]):
        """
        Decorator. Sets a coroutine as a local error handler for this task. This handler will be
        called for any exception raised by the task.

        :param coro: Coroutine to handle errors, signature func(exception) -> None.
        :raise discord.ClientException: Argument is not a coroutine
        """

        if not asyncio.iscoroutinefunction(coro):
            raise discord.ClientException("Error handler must be a coroutine.")

        self.on_error = coro
        return coro

    async def handle_error(self, exc: Exception):
        if self.on_error:
            if self.cog:
                await self.on_error(self.cog, exc)
            else:
                await self.on_error(exc)

    def cancel(self, coro: Callable[[], Awaitable[None]]):
        """
        Decorator. Sets a coroutine as a cancellation handler. This handler is called whenever the
        task is cancelled prior to or while running.

        :param coro: Coroutine to handle cancellation. Takes no parameters.
        :raise discord.ClientException: Argument is not a coroutine
        """

        if not asyncio.iscoroutinefunction(coro):
            raise discord.ClientException("Error handler must be a coroutine.")

        self.on_cancel = coro
        return coro

    async def handle_cancel(self):
        if self.on_cancel:
            if self.cog:
                await self.on_cancel(self.cog)
            else:
                await self.on_cancel()

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return self.callback.__qualname__

    def __hash__(self):
        return hash((self.callback, self.is_unique))

    def __eq__(self, other):
        return self.callback == other.callback and self.is_unique == other.is_unique


def task(is_unique=True):
    """
    Decorator for a task that can be scheduled. Generally to be used similarly to
    ``discord.Command`` on async functions.

    :param is_unique: If True, this task can only be scheduled once at a time (includes
        recurring). If False, this task can be scheduled to run multiple times in the future.
    """
    def decorator(func):
        if isinstance(func, Task):
            raise TypeError("Callback is already a schedulable task.")
        elif isinstance(func, commands.Command):
            func = func.callback
        return Task(callback=func, is_unique=is_unique)
    return decorator


class Scheduler:
    """
    Allows scheduling coroutines for execution at a future point in time, either once or on a
    recurring basis. Use the :func:`~.task` decorator on functions or cog methods to mark it as a
    task for scheduling, and then use this class's methods to schedule it for future execution.

    Tasks allow defining error and cancellation handlers, similar to discord Commands: for instance,

    .. code-block:: py

    class MyCog(KazCog):

        # ... other commands etc. here ...

        @scheduler.task(is_unique=False)
        async def my_task(self):
            pass # task code here

        @my_task.error
        async def my_task_error_handler(self, exc: Exception):
            pass # handle exception here

        @my_task.cancel
        async def my_task_cancellation_handler(self):
            pass # handle cancellation here: cleanup, etc.

    Furthermore, any errors will call the discord Client's `on_error` event, with
    event_type = ``'scheduled_task'`` and two arguments corresponding to the TaskInstance tuple
    (i.e. Task object, timestamp/id as a float). This is called even if a local error handler is
    defined as per above.
    """
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.tasks = {}  # type: Dict[Task, Dict[float, asyncio.Task]]

    @property
    def loop(self):
        return self.bot.loop

    def _add_task(self, task: Task, at_loop_time: float, every: float=None, times: float=None):
        async_task = self.loop.create_task(self._runner(task, at_loop_time, every, times))
        try:
            self.tasks[task][at_loop_time] = async_task
        except KeyError:
            self.tasks[task] = {at_loop_time: async_task}
        logger.debug("Task added: {!s}, {:.2f} (now={:.2f})"
            .format(task, at_loop_time, self.loop.time()))

    def _del_task(self, task: Task, at_loop_time: float):
        del self.tasks[task][at_loop_time]

    def schedule_task_at(self, task: Task, dt: datetime,
                         *, every: Union[float, timedelta]=None, times: int=None) -> TaskInstance:
        """
        Schedule a task to run at a given time.
        :param task: The task to run (a coroutine decorated with :meth:`scheduler.task`)
        :param dt: When to run the task.
        :param every: How often to repeat the task, in seconds or as a timedelta. Optional.
        :param times: How many times to repeat the command. If ``every`` is set but ``times`` is
            not, the task is repeated forever.
        :return: A TaskInstance, which can be used to later cancel this task.
        """

        # TODO: consider is_unique ...

        if not isinstance(task, Task):
            raise ValueError("Scheduled tasks must be decorated with scheduler.task")
        if isinstance(every, timedelta):
            every = every.total_seconds()

        if every:
            logger.info("Scheduling task {!s} at {}, recurring every {:.2f}s for {} times"
                .format(task, dt.isoformat(' '), every, str(times) if times else 'infinite'))
        else:
            logger.info("Scheduling task {!s} at {}".format(task, dt.isoformat(' ')))

        at_loop_time = datetime2loop(dt, self.loop)
        self._add_task(task, at_loop_time, every, times)
        return task, at_loop_time

    def schedule_task_in(self, task: Task, in_time: Union[float, timedelta],
                         *, every: Union[float, timedelta]=None, times: int=None) -> TaskInstance:
        """
        Schedule a task to run in a certain amount of time. By default, will run the task only once;
        if ``every`` is specified, runs the task recurrently up to ``times`` times.

        :param task: The task to run (a coroutine decorated with :meth:`scheduler.task`).
        :param in_time: In how much time to run the task, in seconds or as a timedelta.
        :param every: How often to repeat the task, in seconds or as a timedelta (> 0s). Optional.
        :param times: How many times to repeat the command. If ``every`` is set but ``times`` is
            not, the task is repeated forever. If ``every`` is not set, this has no effect.
        :return: A TaskInstance, which can be used to later cancel this task.
        """
        if not isinstance(task, Task):
            raise ValueError("Scheduled tasks must be decorated with scheduler.task")
        if isinstance(every, timedelta):
            every = every.total_seconds()
        if isinstance(in_time, timedelta):
            in_time = in_time.total_seconds()

        if every:
            logger.info("Scheduling task {!s} in {:.2f}s, recurring every {:.2f}s for {} times"
                .format(task, in_time, every, str(times) if times else 'infinite'))
        else:
            logger.info("Scheduling task {!s} in {:.2f}s".format(task, in_time))

        at_loop_time = self.loop.time() + in_time
        self._add_task(task, at_loop_time, every, times)
        return task, at_loop_time

    async def _runner(self, task: Task, at_loop_time: float, every: float=None, times: float=None):
        task_id = '{!s}@{:.2f}'.format(task, at_loop_time)

        if not every or every <= 0:
            times = 1

        target_time = at_loop_time
        count = 0
        try:
            while times is None or count < times:
                wait_time = target_time - self.loop.time()
                logger.debug("Task {}: Waiting {:.1f}s...".format(task_id, wait_time))
                await asyncio.sleep(wait_time)

                logger.info("Task {}: Running (count so far: {:d})".format(task_id, count))
                await self._run_task_once(task, at_loop_time)

                count += 1
                if every and every > 0:
                    target_time += every
        except asyncio.CancelledError:
            logger.warning("Task {!s} cancelled.".format(task_id))
            try:
                await task.handle_cancel()
            except TypeError:
                logger.exception("Task {!s} cancellation handler cannot be run")
            finally:
                self._del_task(task, at_loop_time)
            raise
        else:
            if count > 1:
                logger.info("Recurrent task {} finished (run {:d} times)".format(task_id, count))

    async def _run_task_once(self, task: Task, at_loop_time: float):
        task_id = '{!s}@{:.2f}'.format(task, at_loop_time)
        # noinspection PyBroadException
        try:
            return await task.execute()
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logger.exception("Error in Task {!s}.".format(task_id))
            # noinspection PyBroadException
            try:
                await task.handle_error(e)
            except TypeError:
                logger.exception("Task {!s} error handler cannot be run.")
            except Exception:
                logger.exception("Error in Task {!s} while handling error.".format(task_id))
            finally:
                await self.bot.dispatch('error', 'scheduled_task', task, at_loop_time)

    def cancel_task(self, instance: TaskInstance):
        """
        Cancel a specific instance of a scheduled task.

        :param instance: The task instance (returned by :meth:`~.schedule_task_at` and
        :meth:`~.schedule_task_in`) to cancel.
        :raise asyncio.InvalidStateError: Task is already done, does not exist or was previously
        cancelled.
        """
        self.tasks[instance[0]][instance[1]].cancel()

    def cancel_all(self, task: Task=None):
        """
        Cancel all future-scheduled tasks, either of a specific task method (if specified) or
        globally.

        :param task: If specified, cancel only instances of this task method.
        """
        if task is not None:
            for async_task in self.tasks[task].values():
                async_task.cancel()
        else:
            for task_map in self.tasks.values():
                for async_task in task_map.values():
                    async_task.cancel()
