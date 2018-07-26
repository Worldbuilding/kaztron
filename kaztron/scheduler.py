import asyncio
import logging

from collections.abc import Hashable
from datetime import datetime, timedelta
from typing import Callable, Union, Dict, Awaitable, Any, List, Sequence, Mapping

import discord
from discord.ext import commands

from kaztron.utils.asyncio import datetime2loop

logger = logging.getLogger(__name__)


TaskFunction = Union[
    Callable[[], Awaitable[None]],
    Callable[[Any], Awaitable[None]]]  #: async def name() -> None


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
        self.instance = None  # instance the last time this Task was accessed as a descriptor
        self.on_error = None  # type: Callable[[Exception], Awaitable[None]]
        self.on_cancel = None  # type: Callable[[], Awaitable[None]]

    def __get__(self, instance, owner):
        if instance:
            self.instance = instance
        return self

    def run(self, instance=None, *args, **kwargs):
        # coroutine - returns the un-awaited coroutine object
        return self.callback(instance, *args, **kwargs) if instance else \
               self.callback(*args, **kwargs)

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

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return self.callback.__qualname__

    def __hash__(self):
        return hash((self.callback, self.is_unique))

    def __eq__(self, other):
        return self.callback == other.callback and self.is_unique == other.is_unique


# noinspection PyShadowingNames
class TaskInstance:
    def __init__(self,
                 scheduler: 'Scheduler', task: Task, timestamp: float,
                 instance: Any, args: Sequence[Any], kwargs: Mapping[str, Any]):
        self.scheduler = scheduler
        self.task = task
        self.instance = instance
        self.timestamp = timestamp
        self.async_task = None
        self.args = tuple(args) if args else ()
        self.kwargs = dict(kwargs.items()) if kwargs else {}

    def cancel(self):
        self.scheduler.cancel_task(self)

    def __await__(self):
        return self.async_task.__await__()

    def is_current(self):
        """ Return True if called from within this task. """
        return self.async_task is asyncio.Task.current_task()

    # noinspection PyBroadException
    async def run(self):
        task_id = '{!s}@{:.2f}'.format(self.task, self.timestamp)
        # noinspection PyBroadException
        try:
            if self.instance:
                return await self.task.run(self.instance, *self.args, **self.kwargs)
            else:
                return await self.task.run(*self.args, **self.kwargs)
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logger.exception("Error in Task {!s}.".format(task_id))
            try:
                await self.on_error(e)
            except Exception:
                logger.exception("Error in Task {!s} while handling error.".format(task_id))
            await self.scheduler.bot.dispatch('error', 'scheduled_task', self.task, self.timestamp)

    async def on_error(self, e: Exception):
        if self.task.on_error:
            if self.instance:
                await self.task.on_error(self.instance, e)
            else:
                await self.task.on_error(e)
        else:
            logger.debug("Task {!s} has no error handler".format(self.task))

    async def on_cancel(self):
        if self.task.on_cancel:
            if self.instance:
                await self.task.on_cancel(self.instance)
            else:
                await self.task.on_cancel()
        else:
            logger.debug("Task {!s} has no cancellation handler".format(self.task))

    def __str__(self):
        return str(self.task) + "@{:.2f}".format(self.timestamp)


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


# noinspection PyShadowingNames
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

    A task can be called via a scheduler instance (normally available via ``KazCog.scheduler``),
    e.g.:

    .. code-block:: py

        self.scheduler.schedule_task_in(self.my_task, 300)  # scheduled in 5 minutes (300s)

    """
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.tasks = {}  # type: Dict[Task, Dict[float, TaskInstance]]

    @property
    def loop(self):
        return self.bot.loop

    def _add_task(self,
                  task: Task, at_loop_time: float,
                  args: Sequence[Any], kwargs: Mapping[str, Any],
                  every: float=None, times: float=None) -> TaskInstance:

        # validate
        if not isinstance(task, Task):
            raise ValueError("Scheduled tasks must be decorated with scheduler.task")

        if task.is_unique:
            # if already have task, and not rescheduling from within the same task
            existing_tasks = self.get_instances(task)
            is_resched = len(existing_tasks) == 1 and existing_tasks[0].is_current()
            if existing_tasks and not is_resched:
                raise asyncio.InvalidStateError(
                    'Task {} is set unique and already exists'.format(task)
                )

        # set up task
        task_inst = TaskInstance(self, task, at_loop_time, task.instance, args, kwargs)
        task_inst.async_task = self.loop.create_task(
            self._runner(task_inst, at_loop_time, every, times)
        )
        try:
            self.tasks[task][at_loop_time] = task_inst
        except KeyError:
            self.tasks[task] = {at_loop_time: task_inst}
        logger.debug("Task added: {!s}, {:.2f} (now={:.2f})"
            .format(task, at_loop_time, self.loop.time()))
        return task_inst

    def _del_task(self, task_inst: TaskInstance):
        del self.tasks[task_inst.task][task_inst.timestamp]
        if not self.tasks[task_inst.task]:
            del self.tasks[task_inst.task]  # avoids leaking memory on a transient task object

    def schedule_task_at(self, task: Task, dt: datetime,
                         *, args: Sequence[Any]=(), kwargs: Mapping[str, Any]=None,
                         every: Union[float, timedelta]=None, times: int=None) -> TaskInstance:
        """
        Schedule a task to run at a given time.
        :param task: The task to run (a coroutine decorated with :meth:`scheduler.task`)
        :param dt: When to run the task.
        :param args: Positional args to pass to the task, as a sequence (list/tuple) of values. If
            the task is a method/descriptor, do NOT include the ``self`` argument's value here.
        :param kwargs: Keyword args to pass to the task, as a mapping (dict or similar).
        :param every: How often to repeat the task, in seconds or as a timedelta. Optional.
        :param times: How many times to repeat the command. If ``every`` is set but ``times`` is
            not, the task is repeated forever.
        :return: A TaskInstance, which can be used to later cancel this task.
        """
        if not kwargs:
            kwargs = {}

        if every:
            try:
                every = every.total_seconds()
            except AttributeError:
                every = float(every)

            logger.info("Scheduling task {!s} at {}, recurring every {:.2f}s for {} times"
                .format(task, dt.isoformat(' '), every, str(times) if times else 'infinite'))
        else:
            logger.info("Scheduling task {!s} at {}".format(task, dt.isoformat(' ')))

        return self._add_task(task, datetime2loop(dt, self.loop), args, kwargs, every, times)

    def schedule_task_in(self, task: Task, in_time: Union[float, timedelta],
                         *, args: Sequence[Any]=(), kwargs: Mapping[str, Any]=None,
                         every: Union[float, timedelta]=None, times: int=None) -> TaskInstance:
        """
        Schedule a task to run in a certain amount of time. By default, will run the task only once;
        if ``every`` is specified, runs the task recurrently up to ``times`` times.

        :param task: The task to run (a coroutine decorated with :meth:`scheduler.task`).
        :param in_time: In how much time to run the task, in seconds or as a timedelta.
        :param args: Positional args to pass to the task, as a sequence (list/tuple) of values. If
            the task is a method/descriptor, do NOT include the ``self`` argument's value here.
        :param kwargs: Keyword args to pass to the task, as a mapping (dict or similar).
        :param every: How often to repeat the task, in seconds or as a timedelta (> 0s). Optional.
        :param times: How many times to repeat the command. If ``every`` is set but ``times`` is
            not, the task is repeated forever. If ``every`` is not set, this has no effect.
        :return: A TaskInstance, which can be used to later cancel this task.
        """
        if not kwargs:
            kwargs = {}

        try:
            in_time = in_time.total_seconds()
        except AttributeError:
            in_time = float(in_time)

        if every:
            try:
                every = every.total_seconds()
            except AttributeError:
                every = float(every)

            logger.info("Scheduling task {!s} in {:.2f}s, recurring every {:.2f}s for {} times"
                .format(task, in_time, every, str(times) if times else 'infinite'))
        else:
            logger.info("Scheduling task {!s} in {:.2f}s".format(task, in_time))

        at_loop_time = self.loop.time() + in_time
        return self._add_task(task, at_loop_time, args, kwargs, every, times)

    async def _runner(self,
                      task_inst: TaskInstance,
                      at_loop_time: float,
                      every: float=None,
                      times: float=None
                      ):
        task_id = '{!s}@{:.2f}'.format(task_inst.task, task_inst.timestamp)

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
                await task_inst.run()

                count += 1
                if every and every > 0:
                    target_time += every
        except asyncio.CancelledError:
            logger.warning("Task {!s} cancelled.".format(task_id))
            # noinspection PyBroadException
            try:
                await task_inst.on_cancel()
            except Exception:
                logger.exception("Error in Task {!s} while handling cancellation.".format(task_id))
            raise
        finally:
            self._del_task(task_inst)
            if count > 1:
                logger.info("Recurring task {} ran {:d} times".format(task_id, count))

    def get_instances(self, task: Task) -> List[TaskInstance]:
        try:
            return list(self.tasks[task].values())
        except KeyError:
            return []

    def cancel_task(self, instance: TaskInstance):
        """
        Cancel a specific instance of a scheduled task.

        :param instance: The task instance (returned by :meth:`~.schedule_task_at` and
        :meth:`~.schedule_task_in`) to cancel.
        :raise asyncio.InvalidStateError: Task is already done, does not exist or was previously
        cancelled.
        """
        try:
            self.tasks[instance.task][instance.timestamp].async_task.cancel()
        except KeyError:
            raise asyncio.InvalidStateError("Task {!s} does not exist, is finished or cancelled"
                .format(instance))
        except TypeError:
            raise asyncio.InvalidStateError("Task was not started (??? should not happen?"
                .format(instance))

    def cancel_all(self, task: Task=None):
        """
        Cancel all future-scheduled tasks, either of a specific task method (if specified) or
        globally. This method will not cancel the currently running task (since that would
        immediately interrupt it!).

        :param task: If specified, cancel only instances of this task method.
        """
        if task is not None:
            try:
                for task_inst in self.tasks[task].values():  # type: TaskInstance
                    if not task_inst.is_current():
                        task_inst.cancel()
            except KeyError:
                logger.warning("No task instances for task {!s}".format(task))
        else:
            for task_map in self.tasks.values():
                for task_inst in task_map.values():  # type: TaskInstance
                    if not task_inst.is_current():
                        task_inst.cancel()
