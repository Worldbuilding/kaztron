import logging
from typing import Optional, Union

import discord
from discord.ext import commands

import kaztron.wordfilter as engine
from kaztron.config import get_kaztron_config, get_runtime_config
from kaztron.utils.checks import mod_only
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list
from kaztron.utils.discord import check_role

logger = logging.getLogger('kaztron.wordfilter')


class WordFilter:

    display_filter_types = ['warn', 'del']

    filter_types_map = {
        'w': 'warn',
        'warn': 'warn',
        'warning': 'warn',
        'd': 'delete',
        'del': 'delete',
        'delete': 'delete'
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
        self.bot = bot
        self.config = get_kaztron_config()
        try:
            self.filter_cfg = get_runtime_config()
        except OSError as e:
            logger.error(str(e))
            raise RuntimeError("Failed to load module config") from e
        self._make_default_config()
        self.dest_output = None
        self.dest_warning = None
        self.dest_current = None

    def _make_default_config(self):
        changed = False
        c = self.filter_cfg
        try:
            c.get('filter', 'warn')
        except KeyError:
            c.set('filter', 'warn', [])
            changed = True

        try:
            c.get('filter', 'delete')
        except KeyError:
            c.set('filter', 'delete', [])
            changed = True

        try:
            c.get('filter', 'channel')
        except KeyError:
            c.set('filter', 'channel', self.config.get('filter', 'channel_warning'))
            changed = True

        if changed:
            c.write()

    async def on_ready(self):
        """
        Load information from the server.
        """
        self.dest_output = self.bot.get_channel(self.config.get('discord', 'channel_output'))
        self.dest_warning = self.bot.get_channel(self.config.get('filter', 'channel_warning'))
        self.dest_current = self.bot.get_channel(self.filter_cfg.get('filter', 'channel'))

        # validation
        if self.dest_output is None:
            raise ValueError('Output channel {} not found'.format(self.dest_output.id))

        if self.dest_warning is None:
            raise ValueError('WordFilter warning channel {} not found'.format(self.dest_warning.id))

        if self.dest_current is None:
            self.dest_current = self.dest_warning
            self.filter_cfg.set('filter', 'channel', str(self.dest_warning.id))

    async def on_message(self, message):
        """
        Message handler. Check all non-mod messages for filtered words.
        """

        is_mod = check_role(self.config.get("discord", "mod_roles", []), message)
        is_pm = isinstance(message, discord.PrivateChannel)
        if not is_mod and not is_pm:
            message_string = str(message.content)
            is_delete = engine.filter_func(
                self.filter_cfg.get("filter", "delete", []),
                message_string
            )
            is_warn = engine.filter_func(
                self.filter_cfg.get("filter", "warn", []),
                message_string
            )

            # logging
            if is_delete or is_warn:
                if is_delete:
                    log_fmt = "Found filter match (auto-delete) in {}"
                else:  # is_warn
                    log_fmt = "Found filter match (auto-warn) in {}"

                logger.info(log_fmt.format(message_log_str(message)))

            # delete
            if is_delete:
                logger.debug("Deleting message")
                await self.bot.delete_message(message)

            # warn
            if is_delete or is_warn:
                logger.debug("Preparing and sending filter warning")
                filter_type = 'delete' if is_delete else 'warn'

                em = discord.Embed(color=self.match_warn_color[filter_type])
                em.set_author(name=self.match_headings[filter_type])
                em.add_field(name="User", value=message.author.mention, inline=True)
                em.add_field(name="Channel", value=message.channel.mention, inline=True)
                em.add_field(name="Timestamp", value=message.timestamp, inline=True)
                # TODO: show rule matched
                em.add_field(name="Content", value=message_string, inline=True)

                await self.bot.send_message(self.dest_current, embed=em)

    @commands.group(name="filter", invoke_without_command=True, pass_context=True)
    @mod_only()
    async def word_filter(self, ctx):
        """
        [MOD ONLY] Manages the filter lists. This feature is used to notify moderators of keywords
        and phrases in messages, and optionally auto-delete them.

        All commands permit single-letter mnemonics for convenience, e.g. `.filter l` is
        equivalent to `.filter list`.
        """
        await self.bot.say('Invalid subcommand. Use `{}help {}` for instructions.'
            .format(self.bot.command_prefix, ctx.invoked_with))

    @word_filter.command(name="list", pass_context=True, aliases=['l'])
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
            await self.filter_list(ctx, 'del')
            await self.filter_list(ctx, 'warn')
        else:
            validated_type = await self.validate_filter_type(filter_type)
            if validated_type is None:
                # error messages and logging already managed
                return

            logger.info("filter_list: listing '{}' list for {}"
                .format(validated_type, ctx.message.author))
            filter_list = self.filter_cfg.get("filter", validated_type)
            if filter_list:
                list_str = format_list(filter_list)
            else:
                list_str = '```Empty```'
            await self.bot.say("{}\n\n{}".format(self.list_headings[validated_type], list_str))

    @word_filter.command(pass_context=True, ignore_extra=False, aliases=['a'])
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
            self.filter_cfg.get("filter", validated_type).append(word)
            self.filter_cfg.write()

            logger.info("add: {}: Added {!r} to the {} list."
                .format(ctx.message.author, word, validated_type))
            await self.bot.say("Added `{}` to the {} list.".format(word, validated_type))

    @word_filter.command(pass_context=True, ignore_extra=False, aliases=['r', 'remove'])
    async def rem(self, ctx, filter_type: str, index: int):
        """
        [MOD ONLY] Remove a new filter word/expression.

        Arguments:
        * filter_type: One of warn, del, w, d
        * index: The index number of the filter to remove. You can get this index number using the
          list command.

        Examples:

        `.filter rem del 5` - Removes the 5th rule in the auto-delete filter.
        `.filter r w 3` - Shorthand. Removes the 3rd rule in the warning-only filter.
        """
        logger.info("rem: {}".format(message_log_str(ctx.message)))
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            cfg_index = index - 1
            filter_list = self.filter_cfg.get("filter", validated_type)
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
                self.filter_cfg.write()

                logger.info("rem: {}: Removed {!r} from the {} list."
                    .format(ctx.message.author, del_value, validated_type))
                await self.bot.say("Removed `{}` from the {} list."
                    .format(del_value, validated_type))

    @word_filter.command(pass_context=True, aliases=['sw', 's'])
    @mod_only()
    async def switch(self, ctx):
        """
        [MOD ONLY] Change the bot output channel for wordfilter warnings.

        Switches between the configured filter warning channel and the general bot output channel
        (#mods and #bot_output at time of writing).
        """
        logger.info("switch: {}".format(message_log_str(ctx.message)))

        if self.dest_current is None and self.dest_warning is None:
            logger.warning("switch invoked before bot ready state???")
            await self.bot.say("Sorry, I'm still booting up. Try again in a few seconds.")
            return

        if self.dest_current is self.dest_warning:
            self.dest_current = self.dest_output
        else:
            self.dest_current = self.dest_warning
        self.filter_cfg.set('filter', 'channel', str(self.dest_current.id))
        self.filter_cfg.write()

        logger.info("switch(): Changed filter warning channel to #{}"
            .format(self.dest_current.name))
        await self.bot.say("Changed the filter warning channel to {}"
            .format(self.dest_current.mention))

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
