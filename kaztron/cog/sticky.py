import logging
from typing import List, Dict

import asyncio
from datetime import timedelta

import discord
from discord.ext import commands

from kaztron import KazCog, task, TaskInstance
from kaztron.config import SectionView
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only
from kaztron.utils.datetime import format_timedelta
from kaztron.utils.discord import get_group_help, get_jump_url
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import tb_log_str, exc_log_str
from kaztron.utils.strings import natural_truncate, format_list

logger = logging.getLogger(__name__)


class StickyConfig(SectionView):
    """
    :ivar delay: Default value for all stickies. Amount of channel idle time before refreshing
        (reposting) the sticky message.
    """
    delay: timedelta  # default delay (s) between a channel message and refreshing the info message

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_converters('delay', lambda t: timedelta(seconds=t), None)


class StickyData:
    """
    Configuration for a sticky message to maintain in a specific channel.

    :ivar str channel: Channel in which to maintain a sticky.
    :ivar str message: Text of the message to post in the sticky. Max 2000 characters.
    :ivar Optional[timedelta] delay: Amount of channel idle time before refreshing (reposting) the
        sticky message. Optional; if None, uses the global delay value.
    :ivar str Optional[str] posted_message_id: Discord ID for the current posted sticky. If not yet
        posted, may be None.
    """
    def __init__(self, channel: discord.Channel, message: str, delay: timedelta = None,
                 posted_message_id: str = None):
        self.channel = channel
        self.message = message
        self.delay = delay
        self.posted_message_id = posted_message_id
        # Lazy caching of the posted message
        self._posted_message = None  # type: discord.Message

    def __repr__(self):
        return '<InfoMessageData channel=#{} message={} delay={}, posted_message={}>'.format(
            self.channel.name,
            self.message[:50],
            format_timedelta(self.delay) if self.delay else 'None',
            self.posted_message_id
        )

    def to_dict(self):
        return {
            'channel': self.channel.id,
            'message': self.message,
            'delay': self.delay.total_seconds() if self.delay is not None else None,
            'posted_message': self.posted_message_id
        }

    @staticmethod
    def from_dict(client: discord.Client, data):
        return StickyData(
            channel=client.get_channel(data['channel']) or discord.Object(id=data['channel']),
            message=data['message'],
            delay=timedelta(seconds=data['delay']) if data.get('delay', None) is not None else None,
            posted_message_id=data.get('posted_message', None)
        )

    async def get_posted_message(self, client: discord.Client) -> discord.Message:
        """
        Retrieve the posted message, if any.
        :raises discord.NotFound: Message not found
        :raises discord.Forbidden: Client lack required permissions (e.g. view history permissions
            in channel)
        :raises discord.HTTPException: Other problems retrieving message
        :raises ValueError: no message posted
        """
        if self._posted_message:
            return self._posted_message  # cached

        if not self.posted_message_id:
            raise ValueError('no posted_message')

        self._posted_message = await client.get_message(self.channel, self.posted_message_id)
        return self._posted_message


class StickyState(SectionView):
    """
    :ivar messages: Dictionary of channel ID -> data. See also :class:`StickyData`. This is stored
        in JSON as a list, and converted at access time into a dict for efficiency of lookup.
    """
    messages: Dict[str, StickyData]


class Sticky(KazCog):
    """!kazhelp
        category: Moderator
        brief: "Maintain a sticky message at the bottom of a channel."
        description: "Maintain a sticky message at the end of a channel."
        jekyll_description: |
            This module allows a moderator to set a "sticky" message to be maintained at the end
            of a channel. This can be used for special-purpose or static channels, such as a
            resource-sharing or feedback-sharing channel, to ensure that critical information about
            the channel's purpose or rules are always visible to users.
        contents:
            - sticky:
                - add
                - delay
                - rem
                - list
                - refresh
    """
    cog_config: StickyConfig
    cog_state: StickyState

    ####
    # COG LIFECYCLE
    ####

    def __init__(self, bot):
        super().__init__(bot, 'sticky', StickyConfig, StickyState)
        self.cog_config.set_defaults(delay=0)
        self.cog_state.set_defaults(messages=[])
        self.cog_state.set_converters('messages',
                                      self.state_converter,
                                      lambda d: [data.to_dict() for data in d.values()])

    def state_converter(self, config_list: List[Dict[str, str]]):
        conv = {}
        for data in config_list:
            conv_el = StickyData.from_dict(self.bot, data)
            conv[conv_el.channel.id] = conv_el
        return conv

    async def on_ready(self):
        await super().on_ready()

        # validate channels
        for ch_id, data in self.cog_state.messages.items():
            if isinstance(data.channel, discord.Object):
                logger.warning("Unknown channel: {}".format(ch_id))
                await self.send_output("[WARNING] info_message: unknown channel {}".format(ch_id))
            else:
                await self.update_sticky(data.channel)

    def export_kazhelp_vars(self):
        return {'default_delay': format_timedelta(self.cog_config.delay)}

    ####
    # BUSINESS LOGIC METHODS
    ####

    async def update_sticky(self, channel: discord.Channel):
        """
        Update a channel's sticky, if needed.
        :raises KeyError: channel not configured
        :raises discord.NotFound: Message not found
        :raises discord.Forbidden: Client lack required permissions (e.g. view history permissions
            in channel)
        :raises discord.HTTPException: Other problems retrieving messages
        """
        data = self.cog_state.messages[channel.id]
        try:
            message = await data.get_posted_message(self.bot)
            last_message = None
            _logs = self.bot.logs_from(channel, limit=1)
            async for msg in _logs:
                last_message = msg
                break
        except ValueError:
            await self.post_sticky(channel)  # no message posted, just go ahead and post it
        else:
            if last_message and message.id == last_message.id:  # latest message is still the sticky
                if message.content != data.message:
                    logger.info("Editing sticky message for #{.name:s}".format(channel))
                    await self.bot.edit_message(message, data.message)
            else:  # latest message is not the sticky
                logger.info("Deleting old sticky message in #{.name:s}".format(channel))
                await self.bot.delete_message(message)
                await self.post_sticky(channel)

    async def post_sticky(self, channel: discord.Channel):
        """
        Post a new sticky message.
        :raises KeyError: channel not configured
        :raises discord.NotFound: Message not found
        :raises discord.Forbidden: Client lack required permissions (e.g. view history permissions
            in channel)
        :raises discord.HTTPException: Other problems retrieving messages
        """
        logger.info("Posting sticky message to #{.name:s}".format(channel))
        data = self.cog_state.messages[channel.id]
        msgs = await self.send_message(channel, data.message, auto_split=False)
        data.posted_message_id = msgs[0].id
        self.cog_state.set('messages', self.cog_state.messages)  # notify changes to config

    ####
    # SCHEDULER
    ####

    @task(is_unique=False)
    async def task_update_sticky(self, data: StickyData):
        """ Task for delayed sticky update. """
        await self.update_sticky(data.channel)

    def cancel_channel_task(self, channel: discord.Channel):
        """ Cancel delayed task for the passed channel. """
        for inst in self.scheduler.get_instances(self.task_update_sticky):  # type: TaskInstance
            if inst.args[0].channel.id == channel.id:
                try:
                    inst.cancel()
                except asyncio.InvalidStateError:
                    pass

    ####
    # EVENTS
    ####

    @ready_only
    async def on_message(self, message: discord.Message):
        """ Message handler. Set up sticky message in the channel, if configured. """
        if message.author.id == self.bot.user.id:
            return  # ignore own messages

        try:
            data = self.cog_state.messages[message.channel.id]
        except KeyError:
            return  # not configured for stickies: ignore
        else:
            self.cancel_channel_task(message.channel)  # in case already scheduled
            delay = data.delay if data.delay is not None else self.cog_config.delay
            if delay.total_seconds() <= 0:
                await self.update_sticky(message.channel)
            else:
                self.scheduler.schedule_task_in(self.task_update_sticky, delay, args=(data,))

    ####
    # CONTROL COMMANDS
    ####

    @commands.group(pass_context=True, invoke_without_command=True, ignore_extra=True)
    @mod_only()
    async def sticky(self, ctx):
        """!kazhelp
        brief: Maintain an informational message at the bottom of a channel.
        description: |
            Command group. Maintain an informational message at the bottom of a channel.

            This module allows a moderator to set an informational message to be maintained at the
            end of a channel. This can be used for special-purpose or static channels, such as a
            resource-sharing or feedback-sharing channel, to ensure that critical information about
            the channel's purpose or rules are always visible to users.
        """
        await self.bot.say(get_group_help(ctx))

    @sticky.command(pass_context=True)
    @mod_only()
    async def add(self, ctx: commands.Context, channel: discord.Channel, *, msg: str):
        """!kazhelp
            brief: Add or update a sticky message.
            description: |
                Add or update the sticky message for a channel.

                This will immediately update the sticky message.

                By default, the sticky message will be updated {{default_delay}} after a message is
                posted to the channel. If multiple messages are posted before the delay elapses,
                the timer is reset. Use {{!sticky delay}} to change the delay for this channel.
            parameters:
                - name: channel
                  type: channel
                  description: Channel to change
                - name: msg
                  type: str
                  description: The message contents.
            examples:
                - command: ".sticky add #meta To contact the moderators, [...]"
                  description: "Add or update the #meta sticky with a message about how to contact
                    moderators."
        """
        sticky_config = self.cog_state.messages
        try:
            sticky_config[channel.id].message = msg
        except KeyError:
            sticky_config[channel.id] = StickyData(channel, msg)
        self.cog_state.set('messages', sticky_config)
        logger.info("Updated sticky message for #{} to: {}".format(channel.name, msg))
        await self.send_message(ctx.message.channel,
                                "Updated sticky message for #{}".format(channel.name))
        await self.send_output("Update sticky message for #{} to:\n\n{}".format(channel.name, msg))
        await self.update_sticky(channel)

    @sticky.command(pass_context=True)
    @mod_only()
    async def delay(self, ctx: commands.Context, channel: discord.Channel, *, delay: int):
        """!kazhelp
            brief: Set delay for updating sticky message.
            description: |
                Set a non-default delay for updating the sticky message in a channel.

                If a sticky message update is already scheduled, the delay will not be updated until
                the next event that would trigger a delayed update.
            parameters:
                - name: channel
                  type: channel
                  description: Channel to change
                - name: delay
                  type: int
                  description: Delay before updating the sticky message (seconds)
            examples:
                - command: ".sticky delay #meta 300"
                  description: Set the sticky to update after 300 seconds in #meta.
        """
        sticky_config = self.cog_state.messages
        try:
            sticky_config[channel.id].delay = timedelta(seconds=delay)
        except KeyError:
            raise commands.BadArgument("channel", channel)
        self.cog_state.set('messages', sticky_config)
        await self.send_message(ctx.message.channel, "Set delay for sticky in #{} to {}".format(
            channel, format_timedelta(sticky_config[channel.id].delay)
        ))

    @sticky.command(pass_context=True, aliases=['rem'])
    @mod_only()
    async def remove(self, ctx: commands.Context, channel: discord.Channel):
        """!kazhelp
            brief: Disable a configured sticky message in a channel.
            description: |
                Disables the sticky message in the specified channel. This will delete any
                existing sticky message in that channel.
            parameters:
                - name: channel
                  type: channel
                  description: Channel to change
            examples:
                - command: ".sticky rem #resources"
                  description: "Disables the sticky message in the #resources channel and removes
                      any existing messages."
        """
        try:
            data = self.cog_state.messages[channel.id]
        except KeyError:
            raise commands.BadArgument("channel", channel)

        if data.posted_message_id:
            try:
                message = await data.get_posted_message(self.bot)
                logger.info("Deleting old sticky message in #{.name:s}".format(channel))
                await self.bot.delete_message(message)
            except discord.HTTPException as e:
                logger.warning(
                    "Failed to delete existing sticky message in #{}; skipping: {}"
                    .format(channel.name, tb_log_str(e))
                )
                await self.send_output(
                    "[WARNING] Failed to delete existing sticky message in #{}; skipping.\n\n{}"
                    .format(channel.name, exc_log_str(e))
                )
        self.cancel_channel_task(channel)
        sticky_config = self.cog_state.messages
        del sticky_config[channel.id]
        self.cog_state.set('messages', sticky_config)
        await self.send_message(ctx.message.channel, "Removed sticky in #{}".format(data.channel))

    @sticky.command(pass_context=True)
    @mod_only()
    async def list(self, ctx: commands.Context):
        """!kazhelp
            brief: List all configured sticky messages.
            description: |
                List all configured sticky messages.
        """
        sorted_data = sorted(self.cog_state.messages.values(), key=lambda v: v.channel.name)
        if sorted_data:
            es = EmbedSplitter(title="Channel Sticky Messages")
        else:
            es = EmbedSplitter(title="Channel Sticky Messages", description="None.")
        for data in sorted_data:
            try:
                jump_url = ' *([link]({}))*'.format(
                    get_jump_url(await data.get_posted_message(self.bot))
                )
            except ValueError:
                jump_url = ''
            delay_string = ' (delay: {})'.format(format_timedelta(data.delay)) if data.delay else ''

            es.add_field(
                name="#{}{}".format(data.channel.name, delay_string),
                value="{}{}".format(natural_truncate(data.message, 512), jump_url),
                inline=False
            )
        await self.send_message(ctx.message.channel, embed=es)

    @sticky.command(pass_context=True)
    @mod_only()
    async def refresh(self, ctx: commands.Context):
        """!kazhelp
            brief: Refresh all sticky messages.
            description: |
                Immediately refresh all sticky messages in all channels.
        """
        for data in self.cog_state.messages.values():
            await self.update_sticky(data.channel)
        await self.send_message(ctx.message.channel, 'Done.')

    @task_update_sticky.error
    async def on_task_update_sticky_error(self, e: Exception, t: TaskInstance):
        data = t.args[0]  # type: StickyData
        if isinstance(e, discord.Forbidden):
            await self.send_output("Error updating sticky {!r}. Permission error: {}"
                .format(data, exc_log_str(e)))
        elif isinstance(e, discord.HTTPException):
            await self.send_output("Error updating sticky {!r}. Will retry. HTTP error: {}"
                .format(data, exc_log_str(e)))
            self.scheduler.schedule_task_in(self.task_update_sticky, 60, args=(data,))
        else:
            logger.error("Error updating sticky {!r}: {}".format(data, tb_log_str(e)))
            await self.send_output("Error updating sticky {!r}: {}"
                .format(data, exc_log_str(e)))

    @sticky.error
    @delay.error
    @add.error
    @remove.error
    @list.error
    @refresh.error
    async def _command_error(self, e: Exception, ctx: commands.Context):
        if isinstance(e, commands.BadArgument) and e.args[0] == 'channel':
            logger.error("No sticky for channel #{}".format(e.args[1].name))
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                " Error: No sticky configured for channel #{}".format(e.args[1].name))
        if isinstance(e, discord.Forbidden):
            data = self.cog_state.get(ctx.args[0].id)
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                "Error updating sticky {!r}. Permission error: {}"
                .format(data, exc_log_str(e)))
        elif isinstance(e, discord.HTTPException):
            data = self.cog_state.get(ctx.args[0].id)
            await self.send_message(ctx.message.channel, ctx.message.author.mention +
                "Error updating sticky {!r}. HTTP error: {}"
                .format(data, exc_log_str(e)))
        else:
            await self.core.on_command_error(e, ctx, force=True)  # Other errors can bubble up


def setup(bot):
    bot.add_cog(Sticky(bot))
