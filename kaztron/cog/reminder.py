import asyncio
import logging
import re
from datetime import datetime
from functools import reduce
from typing import List, Callable, Awaitable

import discord
from discord.ext import commands

from kaztron import KazCog, Scheduler, TaskInstance, task
from kaztron.utils.datetime import utctimestamp, format_datetime, format_timedelta, \
    parse as dt_parse
from kaztron.utils.discord import Limits
from kaztron.utils.logging import exc_log_str
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
        self.task_inst = None  # type: TaskInstance
        self.retries = 0

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
    MAX_PER_USER = 10
    MAX_RETRIES = 10
    RETRY_INTERVAL = 90

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
            try:
                reminder.task_inst.cancel()
            except asyncio.InvalidStateError:
                pass
        self.reminders.clear()
        for reminder_data in self.state.get(self.CFG_SECTION, 'reminders'):
            self.add_reminder(ReminderData.from_dict(reminder_data))

    def _save_reminders(self):
        if not self.is_ready:
            logger.debug("_save_reminders: not ready, skipping")
            return
        logger.debug("_save_reminders")
        self.state.set(self.CFG_SECTION, 'reminders', [r.to_dict() for r in self.reminders])
        self.state.write()

    async def on_ready(self):
        await super().on_ready()
        if not self.reminders:
            self._load_reminders()

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
            user_id=ctx.message.author.id, timestamp=timestamp, remind_time=timespec, msg=msg
        )
        self.add_reminder(reminder)
        await self.bot.say("Got it! I'll remind you by PM at {} UTC (in {!s}).".format(
            format_datetime(reminder.remind_time),
            format_timedelta(reminder.remind_time - datetime.utcnow())
        ))

    def add_reminder(self, r: ReminderData):
        @task()
        async def reminder_expired():
            await self.on_reminder_expired(r)

        @reminder_expired.error
        async def error(e: Exception):
            r.retries += 1
            logger.error("Error sending reminder: {}".format(exc_log_str(e)))
            if r.retries > self.MAX_RETRIES:
                logger.error("Reminders: max retries reached; giving up: {!r}".format(r))
                r.task_inst.cancel()
                self.reminders.remove(r)
                await self.send_output("Giving up on reminder: {!r}. Too many retries".format(r))

        self.reminders.append(r)
        r.task_inst = self.scheduler.schedule_task_at(
            reminder_expired, r.remind_time, every=self.RETRY_INTERVAL)
        self._save_reminders()
        logger.info("Set reminder: {!r}".format(r))

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

    async def on_reminder_expired(self, reminder: ReminderData):
        logger.info("Reminder has expired: {!r}".format(reminder))
        # because send_message assumes discord.Object is a channel, not user
        user = discord.utils.get(self.bot.get_all_members(), id=reminder.user_id)
        await self.bot.send_message(
            user,
            "**Reminder** At {} UTC, you asked me to send you a reminder: {}".format(
                format_datetime(reminder.timestamp),
                reminder.message
            )
        )  # if problem, will raise an exception...

        # stop scheduled retries and remove the reminder
        try:
            reminder.task_inst.cancel()
        except asyncio.InvalidStateError:
            pass

        try:
            self.reminders.remove(reminder)
        except ValueError:
            logger.warning("on_reminder_expired: Reminder not in list of reminders - "
                           "already removed? {!r}".format(reminder))
        self._save_reminders()

    @reminder.command(ignore_extra=False, pass_context=True)
    async def list(self, ctx: commands.Context):
        """ Lists all future reminders you've requested. """
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
        reminders_to_keep = []
        for reminder in self.reminders:  # type: ReminderData
            if reminder.user_id == ctx.message.author.id:
                try:
                    reminder.task_inst.cancel()
                except asyncio.InvalidStateError:
                    pass
            else:
                reminders_to_keep.append(reminder)
        self.reminders = reminders_to_keep
        self._save_reminders()
        await self.bot.say("All your reminders have been cleared.")


def setup(bot):
    bot.add_cog(ReminderCog(bot))
