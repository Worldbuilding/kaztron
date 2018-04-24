import logging
from typing import Union

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.driver.wordfilter import WordFilter as WordFilterEngine
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.discord import check_role, MSG_MAX_LEN, Limits, get_command_str, get_help_str
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list, split_code_chunks_on, natural_truncate

from kaztron.utils.datetime import format_timestamp

logger = logging.getLogger(__name__)


class WordFilter(KazCog):

    display_filter_types = ['warn', 'del']

    filter_types_map = {
        'w': 'warn',
        'warn': 'warn',
        'warning': 'warn',
        'd': 'delete',
        'del': 'delete',
        'delete': 'delete'
    }

    engines = {
        'warn': WordFilterEngine(),
        'delete': WordFilterEngine()
    }

    list_headings = {
        'warn': '**Warn Filter - WordFilter**',
        'delete': '**Delete Filter - WordFilter**',
    }
    match_headings = {
        'warn': 'Warning-Only Filter Trigger - WordFilter',
        'delete': 'Auto-Delete Filter Trigger - WordFilter',
    }
    match_warn_color = {
        'warn': 0xffbf80,
        'delete': 0xff8080
    }

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults(
            'filter',
            warn=[],
            delete=[],
            channel=self.config.get('filter', 'channel_warning')
        )
        self._load_filter_rules()
        self.channel_warning = None
        self.channel_current = None

    def _load_filter_rules(self):
        for filter_type, engine in self.engines.items():
            logger.debug("Reloading {} rules".format(filter_type))
            engine.load_rules(self.state.get("filter", filter_type, []))

    async def on_ready(self):
        """
        Load information from the server.
        """
        dest_warning_id = self.config.get('filter', 'channel_warning')
        self.channel_warning = self.validate_channel(dest_warning_id)

        try:
            self.channel_current = self.validate_channel(self.state.get('filter', 'channel'))
        except ValueError:
            self.channel_current = self.channel_warning
            self.state.set('filter', 'channel', str(self.channel_warning.id))

        await super().on_ready()

    @ready_only
    async def on_message(self, message):
        """
        Message handler. Check all non-mod messages for filtered words.
        """
        is_mod = check_role(self.config.get("discord", "mod_roles", []) +
                            self.config.get("discord", "admin_roles", []), message)
        is_pm = isinstance(message.channel, discord.PrivateChannel)
        if not is_mod and not is_pm:
            message_string = str(message.content)
            del_match = self.engines['delete'].check_message(message_string)
            warn_match = self.engines['warn'].check_message(message_string)

            # logging
            if del_match or warn_match:
                if del_match:
                    log_fmt = "Found filter match [auto-delete] '{1}' in {0}"
                else:  # is_warn
                    log_fmt = "Found filter match (auto-warn) '{2}' in {0}"

                logger.info(log_fmt.format(message_log_str(message), del_match, warn_match))

            # delete
            if del_match:
                logger.debug("Deleting message")
                await self.bot.delete_message(message)

            # warn
            if del_match or warn_match:
                logger.debug("Preparing and sending filter warning")
                filter_type = 'delete' if del_match else 'warn'
                match_text = del_match if del_match else warn_match

                em = discord.Embed(color=self.match_warn_color[filter_type])
                em.set_author(name=self.match_headings[filter_type])
                em.add_field(name="User", value=message.author.mention, inline=True)
                em.add_field(name="Channel", value=message.channel.mention, inline=True)
                em.add_field(name="Timestamp", value=format_timestamp(message), inline=True)
                em.add_field(name="Match Text", value=match_text, inline=True)
                em.add_field(name="Content",
                             value=natural_truncate(message_string, Limits.EMBED_FIELD_VALUE),
                             inline=False)

                await self.bot.send_message(self.channel_current, embed=em)

    @commands.group(name="filter", invoke_without_command=True, pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def word_filter(self, ctx):
        """
        [MOD ONLY] Manages the filter lists. This feature is used to notify moderators of keywords
        and phrases in messages, and optionally auto-delete them.

        All commands permit single-letter mnemonics for convenience, e.g. `.filter l` is
        equivalent to `.filter list`.
        """
        command_list = list(self.word_filter.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

    @word_filter.command(name="list", pass_context=True, aliases=['l'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def filter_list(self, ctx, filter_type: str=None):
        """
        [MOD ONLY] Lists the current filters.

        If `filter_type` is not given, lists all filters; otherwise, lists the specified filter.

        Examples:

        .filter list - Shows both auto-warn and auto-delete lists.
        .filter list warn - Shows warn filter list.
        .filter list del - Shows auto-delete filter list.

        You can use single-letter mnemonics for convenience:

        .filter l w - Shows warn filter list.
        """
        logger.info("filter_list: {}".format(message_log_str(ctx.message)))
        if filter_type is None:  # not passed - list both
            await ctx.invoke(self.filter_list, 'del')
            await ctx.invoke(self.filter_list, 'warn')
        else:
            validated_type = await self.validate_filter_type(filter_type)
            if validated_type is None:
                # error messages and logging already managed
                return

            logger.info("filter_list: listing '{}' list for {}"
                .format(validated_type, ctx.message.author))
            filter_list = self.state.get("filter", validated_type)
            if filter_list:
                list_str = format_list(filter_list)
            else:
                list_str = 'Empty'

            heading_str = self.list_headings[validated_type]
            say_strings = split_code_chunks_on(list_str, MSG_MAX_LEN - len(heading_str) - 2)
            await self.bot.say("{}\n{}".format(heading_str, say_strings[0]))
            for say_str in say_strings[1:]:
                await self.bot.say(say_str)

    @word_filter.command(pass_context=True, ignore_extra=False, aliases=['a'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def add(self, ctx, filter_type: str, word: str):
        """
        [MOD ONLY] Add a new filter word/expression.

        Arguments:
        * filter_type: The list to add to. One of ["warn", "del"] (shorthand: ["w", "d"])
        * word: The word or expression to match. USE QUOTATION MARKS AROUND IT IF MULTI-WORD.
          You can use '%' at the beginning or end of the expression to match word boundaries
          otherwise substring matching is done).

        Examples:

        `.filter add warn %word%` - Adds "word" (as an exact word match) to the auto-warning list.
        `.filter add del "%pink flamingo%"` - Add "pink flamingo" (exact expression) to the auto-
                delete list.
        `.filter a w %talk` - Shorthand. Add "%talk" to the warning list - this will match any words
                that start with "talk".
        """
        logger.info("add: {}".format(message_log_str(ctx.message)))
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            # not a copy - can modify directly
            self.state.get("filter", validated_type).append(word)
            self.state.write()

            logger.info("add: {}: Added {!r} to the {} list."
                .format(ctx.message.author, word, validated_type))
            await self.bot.say("Added `{}` to the {} list.".format(word, validated_type))

            self._load_filter_rules()

    @word_filter.command(pass_context=True, ignore_extra=False, aliases=['r', 'remove'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def rem(self, ctx, filter_type: str, word: str):
        """
        [MOD ONLY] Remove a filter word/expression by word.

        Arguments:
        * filter_type: The list to remove from. One of ["warn", "del"] (shorthand: ["w", "d"])
        * word: The word or expression to remove from the filter list. If it has spaces, use
          quotation marks.

        Examples:

        `.filter rem warn %word%` - Remove "%word%" from the auto-warning list.
        `.filter rem del "%pink flamingo%"` - Remove "%pink flamingo%" from the auto-delete list.
        """
        logger.info("add: {}".format(message_log_str(ctx.message)))
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            filter_list = self.state.get("filter", validated_type)
            try:
                # not a copy - can modify directly
                filter_list.remove(word)
            except ValueError:
                err_msg = "No such item in filter list {}: {}".format(validated_type, word)
                logger.error("rem: " + err_msg)
                await self.bot.say(err_msg)
                return

            else:  # no exceptions
                self.state.write()

                logger.info("rem: {}: Removed {!r} from the {} list."
                    .format(ctx.message.author, word, validated_type))
                await self.bot.say("Removed `{}` from the {} list."
                    .format(word, validated_type))

                self._load_filter_rules()

    @word_filter.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def rnum(self, ctx, filter_type: str, index: int):
        """
        [MOD ONLY] Remove a filter word/expression by list index.

        Arguments:
        * filter_type: One of warn, del, w, d
        * index: The index number of the filter to remove. You can get this index number using the
          list command.

        Examples:

        `.filter rnum del 5` - Removes the 5th rule in the auto-delete filter.
        `.filter r w 3` - Shorthand. Removes the 3rd rule in the warning-only filter.
        """
        logger.info("rnum: {}".format(message_log_str(ctx.message)))
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            cfg_index = index - 1
            filter_list = self.state.get("filter", validated_type)
            try:
                # not a copy - can modify directly
                del_value = filter_list[cfg_index]
                del filter_list[cfg_index]

            except IndexError:
                err_msg = "Index out of range: {:d}".format(index)
                logger.error("rem: " + err_msg)
                await self.bot.say(err_msg)
                return

            else:  # no exceptions
                self.state.write()

                logger.info("rem: {}: Removed {!r} from the {} list."
                    .format(ctx.message.author, del_value, validated_type))
                await self.bot.say("Removed `{}` from the {} list."
                    .format(del_value, validated_type))

                self._load_filter_rules()

    @word_filter.command(name='switch', pass_context=True, ignore_extra=False, aliases=['s', 'sw'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def filter_switch(self, ctx):
        """
        [MOD ONLY] Change the bot output channel for wordfilter warnings.

        Switches between the configured filter warning channel and the general bot output channel
        (#mods and #bot_output at time of writing).
        """
        logger.info("switch: {}".format(message_log_str(ctx.message)))

        if self.channel_current is None and self.channel_warning is None:
            logger.warning("switch invoked before bot ready state???")
            await self.bot.say("Sorry, I'm still booting up. Try again in a few seconds.")
            return

        if self.channel_current is self.channel_warning:
            self.channel_current = self.channel_out
        else:
            self.channel_current = self.channel_warning
        self.state.set('filter', 'channel', str(self.channel_current.id))
        self.state.write()

        logger.info("switch(): Changed filter warning channel to #{}"
            .format(self.channel_current.name))
        await self.bot.say("Changed the filter warning channel to {}"
            .format(self.channel_current.mention))

    @add.error
    async def filter_add_error(self, exc, ctx: commands.Context):
        cmd_string = message_log_str(ctx.message)

        if isinstance(exc, commands.TooManyArguments):
            msg = "Too many arguments passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                ("Too many arguments.\n\n**Usage:** `{} <warn|del> \"<filter text>\"`\n\n"
                 "Did you forget quotation marks around the filter text? "
                 "Use `{}` for instructions.")
                    .format(get_command_str(ctx), get_help_str(ctx)))
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @commands.command(name='switch', pass_context=True)
    @mod_only()
    async def switch_deprecated(self, ctx):
        """ DEPRECATED. """
        await self.bot.say('This command is deprecated. Use `.filter switch` instead.')

    async def validate_filter_type(self, filter_type) -> Union[str, None]:
        """
        Validate the filter_type parameter for wordfilter commands.

        :param filter_type:
        :return: The canonical filter type string, or `None` if invalid.
        """
        filter_type_mapped = self.filter_types_map.get(filter_type, None)
        if filter_type_mapped is not None:
            return filter_type_mapped
        else:
            logger.debug("Invalid filter type '{}' passed.".format(filter_type))
            await self.bot.say(("'{}': Invalid filter type. "
                                "Valid values are {!s} (single-letter mnemonics accepted)")
                               .format(filter_type, self.display_filter_types))
            return None


def setup(bot):
    bot.add_cog(WordFilter(bot))
