import asyncio
import logging
import re
from datetime import datetime
from functools import reduce
from typing import List, Callable, Awaitable

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.datetime import utctimestamp, format_datetime, format_timedelta, \
    parse as dt_parse
from kaztron.utils.decorators import task_handled_errors
from kaztron.utils.discord import Limits
from kaztron.utils.logging import message_log_str, exc_log_str
from kaztron.utils.strings import format_list

logger = logging.getLogger(__name__)


class ReminderData:
    MSG_LIMIT = Limits.MESSAGE//2

    def __init__(self,
                 *,
                 user_id: str,
                 timestamp: datetime,
                 remind_time: datetime,
                 msg: str
                 ):
        self.user_id = user_id
        self.timestamp = timestamp
        self.remind_time = remind_time
        self.message = msg[:self.MSG_LIMIT]
        self.task = None  # type: asyncio.Task

    def start_timer(self,
                    loop: asyncio.AbstractEventLoop,
                    callback: Callable[['ReminderData'], Awaitable[None]]
                    ) -> asyncio.Task:
        """
        Start a timer, in the given event loop, that will call the callback at the remind_time.

        :param loop: The loop to create a timer task in.
        :param callback: asyncio coroutine that will be called upon the reminder expiring. Must take
            a ReminderData instance as its first parameter.
        :return: The created Task object
        """
        @task_handled_errors
        async def timer_event():
            wait_time = (self.remind_time - datetime.utcnow()).total_seconds()
            logger.debug("Starting timer for {!r} ({!s})".format(self, wait_time))
            await asyncio.sleep(wait_time)
            logger.debug("Timer expired, calling callback for {!r}".format(self))
            await callback(self)
        self.task = loop.create_task(timer_event())
        return self.task

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'timestamp': utctimestamp(self.timestamp),
            'remind_time': utctimestamp(self.remind_time),
            'message': self.message
        }

    def __repr__(self):
        return "<ReminderData(user_id={}, timestamp={}, remind_time={}, message={!r})>"\
            .format(self.user_id, self.timestamp.isoformat(' '),
                    self.remind_time.isoformat(' '), self.message)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            user_id=data['user_id'],
            timestamp=datetime.utcfromtimestamp(data['timestamp']),
            remind_time=datetime.utcfromtimestamp(data['remind_time']),
            msg=data['message']
        )


class ReminderCog(KazCog):
    CFG_SECTION = 'reminder'
    DATEPARSER_SETTINGS = {
        'TIMEZONE': 'UTC',
        'TO_TIMEZONE': 'UTC',
        'RETURN_AS_TIMEZONE_AWARE': False
    }
    MAX_PER_USER = 10

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults(
            self.CFG_SECTION,
            reminders=[]
        )
        self.reminders = []  # type: List[ReminderData]

    def _load_reminders(self):
        logger.info("Loading reminders from persisted state...")
        for reminder in self.reminders:
            reminder.task.cancel()
        self.reminders.clear()
        for reminder_data in self.state.get(self.CFG_SECTION, 'reminders'):
            self.reminders.append(ReminderData.from_dict(reminder_data))

    def _save_reminders(self):
        if not self.is_ready:
            logger.debug("_save_reminders: not ready, skipping")
            return
        logger.debug("_save_reminders")
        self.state.set(self.CFG_SECTION, 'reminders', [r.to_dict() for r in self.reminders])
        self.state.write()

    async def on_ready(self):
        if not self.reminders:
            self._load_reminders()
            for reminder in self.reminders:
                reminder.start_timer(self.bot.loop, self.on_reminder_expired)
        await super().on_ready()

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['remind'])
    async def reminder(self, ctx: commands.Context, *, args: str):
        """
        Sends you a personal reminder by PM at some point in the future.

        TIP: Make sure you've enabled "Allow direct messages from server members" for the server
        the bot is on.

        TIP: You should double-check the reminder time in the confirmation PM, to make sure your
        timespec was interpreted correctly.

        **Usage:** `.remind <timespec>: <message>`

        **Arguments:**
        * `<timespec>: `: A time in the future to send you a reminder, followed by a colon
          and a space. This can be an absolute date and time `2018-03-07 12:00:00`, a
          relative time `in 2h 30m` (the space between hours and minutes, or other different units,
          is important), or combinations of the two (`tomorrow at 1pm`). Times are in UTC+0000,
          unless you specify your time zone (e.g. `12:00:00 UTC-5`).
        * `<message>`: The message to include with the reminder.

        **Examples:**
        .remind in 2 hours: Feed the dog
        .remind on 24 december at 4:50pm: Grandma's christmas call
        .remind tomorrow at 8am: Start Spotlight
        """

        logger.info("reminder: {}".format(message_log_str(ctx.message)))

        # check existing count
        n = reduce(lambda c, r: c+1 if r.user_id == ctx.message.author.id else c, self.reminders, 0)
        if n >= self.MAX_PER_USER:
            logger.warning("Cannot add reminder: user {} at limit".format(ctx.message.author))
            await self.bot.say(("Oops! You already have too many future reminders! "
                         "The limit is {:d} per person.").format(self.MAX_PER_USER))
            return

        try:
            timespec_s, msg = re.split(r':\s+|,', args, maxsplit=1)
        except ValueError:
            raise commands.BadArgument("message")

        timestamp = datetime.utcnow()
        # first one allows "10 minutes" as a future input, second is a fallback
        timespec = dt_parse('in ' + timespec_s, future=True) or dt_parse(timespec_s, future=True)

        if timespec is None:
            raise commands.BadArgument("timespec", timespec_s[:64])
        elif timespec <= timestamp:
            raise commands.BadArgument("past")
        reminder = ReminderData(
            user_id=ctx.message.author.id,
            timestamp=timestamp,
            remind_time=timespec,
            msg=msg
        )
        reminder.start_timer(self.bot.loop, self.on_reminder_expired)
        self.reminders.append(reminder)
        self._save_reminders()
        logger.info("Set reminder: {!r}".format(reminder))
        await self.bot.say("Got it! I'll remind you by PM at {} UTC (in {!s}).".format(
            format_datetime(reminder.remind_time),
            format_timedelta(reminder.remind_time - datetime.utcnow())
        ))

    @reminder.error
    async def reminder_error(self, exc, ctx):
        if isinstance(exc, commands.BadArgument) and exc.args[0] == 'timespec':
            logger.error("Passed unknown timespec: {}".format(exc.args[1]))
            await self.bot.say(
                "Sorry, I don't understand the timespec '{}'".format(exc.args[1])
            )
        elif isinstance(exc, commands.BadArgument) and exc.args[0] == 'past':
            await self.bot.say(
                "Oops! You can't set a reminder in the past!"
            )
        elif isinstance(exc, commands.BadArgument) and exc.args[0] == 'message':
            await self.bot.say(
                "You need to specify a message for your reminder! "
                "Separate it from the timespec with a colon *and* space: "
                "`.reminder in 10 minutes: message`"
            )
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @task_handled_errors
    async def on_reminder_expired(self, reminder: ReminderData):
        logger.info("Reminder has expired: {!r}".format(reminder))
        user = discord.utils.get(self.bot.get_all_members(), id=reminder.user_id)
        try:
            await self.bot.send_message(
                user,
                "**Reminder** At {} UTC, you asked me to send you a reminder: {}".format(
                    format_datetime(reminder.timestamp),
                    reminder.message
                )
            )
        except discord.errors.DiscordException as e:
            logger.error("Error sending reminder: {}".format(exc_log_str(e)))
            reminder.remind_time += 30  # try again a little later
            reminder.start_timer(self.bot.loop, self.on_reminder_expired)
        else:
            try:
                self.reminders.remove(reminder)
            except ValueError:
                logger.warning("on_reminder_expired: Reminder not in list of reminders - "
                               "already removed? {!r}".format(reminder))
        self._save_reminders()

    @reminder.command(ignore_extra=False, pass_context=True)
    async def list(self, ctx: commands.Context):
        """ Lists all future reminders you've requested. """
        logger.info("reminder list: {}".format(message_log_str(ctx.message)))

        items = []
        filtered = filter(lambda r: r.user_id == ctx.message.author.id, self.reminders)
        sorted_reminders = sorted(filtered, key=lambda r: r.remind_time)
        for reminder in sorted_reminders:
            items.append("At {} UTC (in {}): {}".format(
                format_datetime(reminder.remind_time),
                format_timedelta(reminder.remind_time - datetime.utcnow()),
                reminder.message
            ))
        if items:
            reminder_list = format_list(items)
        else:
            reminder_list = 'None'
        await self.bot.send_message(ctx.message.author, "**Your reminders**\n" + reminder_list)
        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            pass  # no permission or in a PM; oh well, this is not critical

    @reminder.command(pass_context=True, ignore_extra=False)
    async def clear(self, ctx: commands.Context):
        """ Remove all future reminders you've requested. """
        logger.info("reminder clear: {}".format(message_log_str(ctx.message)))
        reminders_to_keep = []
        for reminder in self.reminders:
            if reminder.user_id == ctx.message.author.id:
                reminder.task.cancel()
            else:
                reminders_to_keep.append(reminder)
        self.reminders = reminders_to_keep
        self._save_reminders()
        await self.bot.say("All your reminders have been cleared.")


def setup(bot):
    bot.add_cog(ReminderCog(bot))
