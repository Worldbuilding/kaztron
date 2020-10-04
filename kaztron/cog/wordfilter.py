import logging
from typing import Union, List

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.driver.wordfilter import WordFilter as WordFilterEngine
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.discord import check_role, MSG_MAX_LEN, Limits, get_command_str, get_help_str, \
    get_group_help, get_jump_url
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list, split_code_chunks_on, natural_truncate

from kaztron.utils.datetime import format_timestamp

logger = logging.getLogger(__name__)


class WordFilterConfig(SectionView):
    channel_warning: discord.Channel


class WordFilterState(SectionView):
    warn: List[str]
    delete: List[str]
    channel: discord.Channel


class WordFilter(KazCog):
    """!kazhelp
    category: Moderator
    brief: "Watch for words or expressions in user messages, and either warn moderators or
        auto-delete messages on detection."
    description: "Watch for words or expressions in user messages, and either warn moderators or
        auto-delete messages on detection."
    jekyll_description: |
        The WordFilter cog is a moderation tool. It watches all messages on the server for the use
        of certain words, expressions or other strings. The bot has two separate lists of filter
        strings, both fully configurable using bot commands:

        * `del` list: Any messages that match will be auto-deleted. Moderators are notified.
        * `warn` list: Moderators are notified of the matching message.

        Moderator notifications are output to either {{output_channel}} or {{warn_channel}}; this
        can be switched using the {{!filter switch}} command.

        ## Filter string syntax

        The special character `%` will match a word boundary (any non-letter character).
        Each word/expression in the list can be matched in four  different ways:

        * `foo` : Matches any sub-string `foo`, even if inside a word; for example, the words
          `foobar`, `zoboomafoo`, and `afoot` inside a message will all be caught.
        * `%foo` : Matches any word that *starts* with `foo`. For example, `fooing` will match, but
          `zoboomafoo` will *not* match.
        * `foo%` : Matches any word that *ends* with `foo`. For example, `zoboomafoo` will match,
          but *not* `foobar`.
        * `%foo%` : Matches whole words only.

        You can also refer to the table below to see examples of which method will catch which
        sub-strings.

        |           | foo | %foo | foo% | %foo% |
        |:----------|:---:|:----:|:----:|:-----:|
        | foo       | <i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |<i class="fas fa-check text-success"></i> |
        | foobar    | <i class="fas fa-check text-success"></i> | <i class="fas fa-check text-success"></i> | | |
        | barfoo    |<i class="fas fa-check text-success"></i> | | <i class="fas fa-check text-success"></i> | |
        | barfoobar | <i class="fas fa-check text-success"></i> | | | |

        TIP: Filters are always case insensitive.
    contents:
        - filter:
            - list
            - add
            - rem
            - rnum
            - switch
        - switch
    """
    cog_config: WordFilterConfig
    cog_state: WordFilterState

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
        super().__init__(bot, 'filter', WordFilterConfig, WordFilterState)
        self.cog_state.set_defaults(
            warn=[],
            delete=[],
            channel=self.cog_config.channel_warning
        )
        self.cog_config.set_converters('channel_warning',
            lambda cid: self.get_channel(cid),
            lambda _: None)
        self.cog_state.set_converters('channel',
            lambda cid: self.get_channel(cid),
            lambda c: str(c.id))
        self._load_filter_rules()
        self.channel_warning = None
        self.channel_current = None

    def _load_filter_rules(self):
        for filter_type, engine in self.engines.items():
            logger.debug("Reloading {} rules".format(filter_type))
            engine.load_rules(self.cog_state.get(filter_type))

    async def on_ready(self):
        """
        Load information from the server.
        """
        await super().on_ready()
        self.channel_warning = self.cog_config.channel_warning

        try:
            self.channel_current = self.cog_state.channel
        except ValueError:
            self.cog_state.channel = self.channel_current = self.channel_warning

    def export_kazhelp_vars(self):
        return {'warn_channel': '#' + self.channel_warning.name}

    @ready_only
    async def on_message(self, message: discord.Message):
        """
        Message handler. Check all non-mod messages for filtered words.
        """
        is_mod = check_role(self.config.discord.get("mod_roles", []) +
                            self.config.discord.get("admin_roles", []), message)
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
                em.add_field(name="Message Link",
                             value='[Message link]({})'.format(get_jump_url(message)),
                             inline=True)
                em.add_field(name="Content",
                             value=natural_truncate(message_string, Limits.EMBED_FIELD_VALUE),
                             inline=False)

                await self.bot.send_message(self.channel_current, embed=em)

    @commands.group(name="filter", invoke_without_command=True, pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def word_filter(self, ctx):
        """!kazhelp
        description: |
            Command group to manages the filter lists. This module watches for words or expressions
            in user messages, and either warn moderators or auto-delete messages on detection.

            FOR INFORMATION ON FILTER LISTS AND SYNTAX, SEE `.help WordFilter`.

            TIP: For convenience, all sub-commands support a single-letter shorthand. Check each
            command's Usage section.
        jekyll_description: |
            Command group to manages the filter lists.

            For all sub-commands except {{!filter switch}}, you need to specify the filter list,
            either `del` (auto-delete list) or `warn` (warn-only list). You can also use the
            shorthand `d` or `w`.

            TIP: For convenience, all sub-commands support a single-letter shorthand. Check each
            command's Usage section.
        """
        await self.bot.say(get_group_help(ctx))

    @word_filter.command(name="list", pass_context=True, aliases=['l'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def filter_list(self, ctx, filter_type: str=None):
        """!kazhelp
        description: |
            Lists the current filters.

            If `filter_type` is not given, lists all filters; otherwise, lists the specified filter.
        parameters:
            - name: filter_type
              optional: True
              default: both
              description: "Filter list: `del` or `warn` (shorthand: `d` or `w`)."
        examples:
            - command: .filter list
              description: Shows both auto-warn and auto-delete lists.
            - command: .filter list warn
              description: Shows warn filter list.
            - command: .filter list del
              description: Shows auto-delete filter list.
            - command: .filter l w
              description: "Shorthand version of `.filter list warn`."
        """
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
            filter_list = self.cog_state.get(validated_type)
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
        """!kazhelp
        description: |
            Adds a new filter word/expression.
        parameters:
            - name: filter_type
              description: "Filter list: `del` or `warn` (shorthand: `d` or `w`)."
            - name: word
              type: string
              description: |
                The word or expression to filter. **If it has spaces, use quotation marks.** See
                {{%WordFilter}} (or `.help WordFilter` in-bot) for information on matching syntax.
        examples:
            - command: ".filter add warn %word%"
              description: 'Adds "word" (as an exact word match) to the auto-warning list.'
            - command: '.filter add del "%pink flamingo%"'
              description: 'Add "pink flamingo" (exact expression) to the auto-delete list.'
            - command: 'filter a w %talk'
              description: 'Shorthand. Add "%talk" to the warning list - this will match any words
                that start with "talk".'
        """
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            filter_list = self.cog_state.get(validated_type)
            filter_list.append(word)
            self.cog_state.set(validated_type, filter_list)

            logger.info("add: {}: Added {!r} to the {} list."
                .format(ctx.message.author, word, validated_type))
            await self.bot.say("Added `{}` to the {} list.".format(word, validated_type))

            self._load_filter_rules()

    @word_filter.command(pass_context=True, ignore_extra=False, aliases=['r', 'remove'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def rem(self, ctx, filter_type: str, word: str):
        """!kazhelp
        description: |
            Remove a filter word/expression by word.
        parameters:
            - name: filter_type
              description: "Filter list: `del` or `warn` (shorthand: `d` or `w`)."
            - name: word
              type: string
              description: |
                The word or expression to remove. **If it has spaces, use quotation marks.**
        examples:
            - command: ".filter rem warn %word%"
              description: 'Remove "%word%" from the auto-warning list.'
            - command: '.filter r d "%pink flamingo%"'
              description: 'Shorthand. Remove "%pink flamingo%" from the auto-delete list.'
        """
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            filter_list = self.cog_state.get(validated_type)
            try:
                filter_list.remove(word)
                self.cog_state.set(validated_type, filter_list)
            except ValueError:
                err_msg = "No such item in filter list {}: {}".format(validated_type, word)
                logger.error("rem: " + err_msg)
                await self.bot.say(err_msg)
                return

            else:  # no exceptions
                logger.info("rem: {}: Removed {!r} from the {} list."
                    .format(ctx.message.author, word, validated_type))
                await self.bot.say("Removed `{}` from the {} list."
                    .format(word, validated_type))

                self._load_filter_rules()

    @word_filter.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def rnum(self, ctx, filter_type: str, index: int):
        """!kazhelp
        description: |
            Remove a filter word/expression by list index.
        parameters:
            - name: filter_type
              description: "Filter list: `del` or `warn` (shorthand: `d` or `w`)."
            - name: index
              type: number
              description: |
                The index number of the filter to remove. You can get this index number using the
                {{!filter list}} command.
        examples:
            - command: '.filter rnum del 5'
              description: 'Removes the 5th rule in the auto-delete filter.'
            - command: '.filter rnum w 3'
              description: 'Shorthand. Removes the 3rd rule in the warning-only filter.'
        """
        validated_type = await self.validate_filter_type(filter_type)
        if validated_type is None:
            # error messages and logging already managed
            return
        else:
            cfg_index = index - 1
            filter_list = self.cog_state.get(validated_type)
            try:
                # not a copy - can modify directly
                del_value = filter_list[cfg_index]
                del filter_list[cfg_index]
                self.cog_state.set(validated_type, filter_list)
            except IndexError:
                err_msg = "Index out of range: {:d}".format(index)
                logger.error("rem: " + err_msg)
                await self.bot.say(err_msg)
                return

            else:  # no exceptions
                logger.info("rem: {}: Removed {!r} from the {} list."
                    .format(ctx.message.author, del_value, validated_type))
                await self.bot.say("Removed `{}` from the {} list."
                    .format(del_value, validated_type))

                self._load_filter_rules()

    @word_filter.command(name='switch', pass_context=True, ignore_extra=False, aliases=['s', 'sw'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def filter_switch(self, ctx):
        """!kazhelp
        description: |
            Change the bot output channel for WordFilter warnings.

            Switches between the {{output_channel}} and {{warn_channel}} channels.
        """
        if self.channel_current is None and self.channel_warning is None:
            logger.warning("switch invoked before bot ready state???")
            await self.bot.say("Sorry, I'm still booting up. Try again in a few seconds.")
            return

        if self.channel_current is self.channel_warning:
            self.channel_current = self.channel_out
        else:
            self.channel_current = self.channel_warning
        self.cog_state.channel = self.channel_current

        logger.info("switch(): Changed filter warning channel to #{}"
            .format(self.channel_current.name))
        await self.bot.say("Changed the filter warning channel to {}"
            .format(self.channel_current.mention))

    @add.error
    async def filter_add_error(self, exc, ctx: commands.Context):
        cmd_string = message_log_str(ctx.message)

        if isinstance(exc, commands.TooManyArguments):
            msg = "Too many parameters passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel,
                ("Too many parameters.\n\n**Usage:** `{} <warn|del> \"<filter text>\"`\n\n"
                 "Did you forget quotation marks around the filter text? "
                 "Use `{}` for instructions.")
                    .format(get_command_str(ctx), get_help_str(ctx)))
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @commands.command(name='switch', pass_context=True)
    @mod_only()
    async def switch_deprecated(self, ctx):
        """!kazhelp
        description: DEPRECATED.
        """
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
