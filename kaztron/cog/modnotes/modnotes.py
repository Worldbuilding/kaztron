from datetime import datetime
import logging
import math
from collections import OrderedDict
from typing import Optional, Sequence

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron import theme
from kaztron.driver import database as db
from kaztron.driver.pagination import Pagination
from kaztron.utils.datetime import parse as dt_parse
from kaztron.utils.checks import mod_only, mod_channels, admin_only, admin_channels
from kaztron.utils.discord import Limits, user_mention, get_command_str, get_help_str, get_usage_str
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list, parse_keyword_args

from kaztron.utils.datetime import format_timestamp

from kaztron.cog.modnotes.model import User, UserAlias, Record, RecordType
from kaztron.cog.modnotes import controller as c

logger = logging.getLogger(__name__)


class ModNotes(KazCog):
    NOTES_PAGE_SIZE = 10
    USEARCH_PAGE_SIZE = 20

    USEARCH_HEADING_F = "**USER SEARCH RESULTS [{page}/{pages}]** - {total} results for `{query!r}`"
    EMBED_SEPARATOR = '\n{}'.format('\\_'*16)
    EMBED_FIELD_LEN = Limits.EMBED_FIELD_VALUE - len(EMBED_SEPARATOR)

    COLOR_MAP = {
        RecordType.note: theme.solarized.blue,
        RecordType.good: theme.solarized.green,
        RecordType.watch: theme.solarized.magenta,
        RecordType.int: theme.solarized.violet,
        RecordType.warn: theme.solarized.yellow,
        RecordType.temp: theme.solarized.orange,
        RecordType.perma: theme.solarized.red,
        RecordType.appeal: theme.solarized.cyan,
        None: theme.solarized.violet
    }

    KW_TIME = ('timestamp', 'starts', 'start', 'time')
    KW_EXPIRE = ('expires', 'expire', 'ends', 'end')

    def __init__(self, bot):
        super().__init__(bot)
        self.channel_log = discord.Object(self.config.get('modnotes', 'channel_log'))

    async def on_ready(self):
        self.channel_log = self.validate_channel(self.channel_log.id)
        await super().on_ready()

    @staticmethod
    def format_display_user(db_user: User):
        return "<@{}> (`*{}`)".format(db_user.discord_id, db_user.user_id)

    def _get_user_fields(self, user: User, group: Sequence[User]) -> OrderedDict:
        user_fields = OrderedDict()
        user_fields[user.name] = self.format_display_user(user)
        # noinspection PyTypeChecker
        user_fields['Aliases'] = '\n'.join(a.name for a in user.aliases) or 'None'
        if group:
            user_fields['Links'] = '\n'.join(user_mention(u.discord_id)
                                             for u in group if u != user) or 'None'
        return user_fields

    def _get_record_fields(self, record: Record, show_user=False, show_grouped_user=False)\
            -> (OrderedDict, OrderedDict):
        record_fields = OrderedDict()
        rec_title = "Record #{:04d}".format(record.record_id)
        record_fields[rec_title] = format_timestamp(record.timestamp)
        if record.expires:
            expire_str = format_timestamp(record.expires)
            if record.expires <= datetime.utcnow():
                record_fields['Expires'] = expire_str + '\n**EXPIRED**'
            else:
                record_fields['Expires'] = expire_str
        else:
            record_fields['Expires'] = 'Never'

        if show_grouped_user:
            record_fields['Linked from'] = self.format_display_user(record.user)
        elif show_user:
            record_fields['User'] = "{}\n{}" \
                .format(record.user.name, self.format_display_user(record.user))

        contents = OrderedDict()
        content_title = '{} by {}'.format(record.type.name.title(), record.author.name)
        contents[content_title] = '{}{}'\
            .format(record.body[:self.EMBED_FIELD_LEN], self.EMBED_SEPARATOR)

        return record_fields, contents

    async def show_record(self, dest: discord.Object, *,
                          record: Record,
                          title: str):
        embed_color = self.COLOR_MAP[record.type]
        em = discord.Embed(color=embed_color, title=title)

        record_fields, contents = self._get_record_fields(record, show_user=True)

        for field_name, field_value in record_fields.items():
            em.add_field(name=field_name, value=field_value, inline=True)

        for field_name, field_value in contents.items():
            em.add_field(name=field_name, value=field_value, inline=False)

        await self.bot.send_message(dest, embed=em)

    async def show_record_page(self, dest: discord.Object, *,
                               user: Optional[User],
                               group: Sequence[User]=None,
                               records: Pagination,
                               title: str):

        if group is None:
            group = []

        footer = 'Page {page:d}/{total:d} (Total {len:d} records)'\
            .format(page=records.page + 1, total=records.total_pages, len=len(records))

        em = discord.Embed(color=self.COLOR_MAP[None], title=title)
        em_len = 0
        em_n = 0

        # user information
        if user:
            user_fields = self._get_user_fields(user, group)
            em_len += len(title) + len(footer)
            em_n += len(user_fields) + 1  # user_fields + separator

            for field_name, field_value in user_fields.items():
                em.add_field(name=field_name, value=field_value, inline=True)
                em_len += len(field_name) + len(field_value)

        # separator
        sep_name = 'Records Listing'
        sep_value = self.EMBED_SEPARATOR
        em.add_field(name=sep_name, value=sep_value, inline=False)
        em_len += len(sep_name) + len(sep_value)

        # records page
        for record in records:
            record_fields, contents = self._get_record_fields(record, show_user=True)

            rec_n = len(record_fields) + len(contents)
            rec_len = sum(len(name) + len(value) for name, value in record_fields.items()) + \
                sum(len(name) + len(value) for name, value in contents.items())

            # If the length would be too long w/the current record, split the message here
            # Kinda hacky, we send the current embed and rebuild a new one here
            # 0.95 safety factor - I don't know how Discord counts the 6000 embed limit...
            too_many_fields = em_n + rec_n > Limits.EMBED_FIELD_NUM
            embed_too_long = em_len + rec_len > int(0.95 * Limits.EMBED_TOTAL)
            if too_many_fields or embed_too_long:
                await self.bot.send_message(dest, embed=em)
                em = discord.Embed(color=self.COLOR_MAP[None], title=title)
                em_len = len(title)  # that's all for this next embed
                em_n = 0

            for field_name, field_value in record_fields.items():
                em.add_field(name=field_name, value=field_value, inline=True)

            for field_name, field_value in contents.items():
                em.add_field(name=field_name, value=field_value, inline=False)

            em_len += rec_len
            em_n += rec_n

        em.set_footer(text=footer)
        await self.bot.send_message(dest, embed=em)

    @commands.group(aliases=['note'], invoke_without_command=True, pass_context=True,
        ignore_extra=False)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def notes(self, ctx, user: str, page: int=None):
        """
        [MOD ONLY] Access moderation logs.

        Arguments:
        * user: Required. The user for whom to find moderation notes. This can be an @mention, a
          Discord ID (numerical only), or a KazTron ID (starts with *).
        * page: Optional[int]. The page number to access, if there are more than 1 pages of notes.
          Default: last page.

        Example:
            .notes @User#1234
            .notes 330178495568436157 3
        """
        logger.info("notes: {}".format(message_log_str(ctx.message)))
        db_user = await c.query_user(self.bot, user)
        db_group = c.query_user_group(db_user)
        db_records = c.query_user_records(db_group)

        records_pages = Pagination(db_records, self.NOTES_PAGE_SIZE, True)
        if page is not None:
            records_pages.page = max(1, min(records_pages.total_pages, page))

        await self.show_record_page(
            ctx.message.channel,
            records=records_pages, user=db_user, group=db_group, title='Moderation Record'
        )

    @notes.command(aliases=['watch'], pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def watches(self, ctx, page: int=None):
        """
        [MOD ONLY] Show all watches currently in effect (i.e. non-expired watch, int, warn records).

        Arguments:
        * page: Optional[int]. The page number to access, if there are more than 1 pages of notes.
          Default: last page.
        """
        logger.info("notes watches: {}".format(message_log_str(ctx.message)))
        watch_types = (RecordType.watch, RecordType.int, RecordType.warn)
        db_records = c.query_unexpired_records(types=watch_types)

        records_pages = Pagination(db_records, self.NOTES_PAGE_SIZE, True)
        if page is not None:
            records_pages.page = max(1, min(records_pages.total_pages, page)) - 1

        await self.show_record_page(
            ctx.message.channel,
            records=records_pages, user=None, title='Active Watches'
        )

    @notes.command(aliases=['temp'], pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def temps(self, ctx, page: int=None):
        """
        [MOD ONLY] Show all tempbans currently in effect (i.e. non-expired temp records).

        Arguments:
        * page: Optional[int]. The page number to access, if there are more than 1 pages of notes.
          Default: last page.
        """
        logger.info("notes temps: {}".format(message_log_str(ctx.message)))
        db_records = c.query_unexpired_records(types=RecordType.temp)

        records_pages = Pagination(db_records, self.NOTES_PAGE_SIZE, True)
        if page is not None:
            records_pages.page = max(1, min(records_pages.total_pages, page)) - 1

        await self.show_record_page(
            ctx.message.channel,
            records=records_pages, user=None, title='Active Temporary Bans (Mutes)'
        )

    @notes.command(pass_context=True, aliases=['a'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def add(self, ctx, user: str, type_: str, *, note_contents):
        """
        [MOD ONLY] Add a new note.

        Attachments in the same message as the command are appended to the note.

        Arguments:
        * <user>: Required. The user to whom the note applies. See `.help notes`.
        * <type>: Required. The type of record. One of:
            * note: Miscellaneous note.
            * good: Noteworthy positive contributions
            * watch: Moderative problems to monitor
            * int: Moderator intervention
            * warn: Formal warning
            * temp: Temporary ban
            * perma: Permanent ban
            * appeal: Formal appeal or decision
        * [OPTIONS]: Optional. Options of the form:
            * timestamp="timespec": Sets the note's time (e.g. the time of an event).
              Default is "now". Instead of `timestamp`, you can also use the synonyms `starts`,
              `start`, `time`.
            * expires="timespec": Sets when a note expires. This is purely documentation. For
              example, when a temp ban ends, or a permaban appeal is available, etc.
              Default is no expiration. Instead of `expires`, you can also use the synonyms
              `expire`, `ends` or `end`.
            * The timespec is "smart". You can type a date and time (like "3 Dec 2017 5PM"), or
              relative times in natural language ("10 minutes ago", "in 2 days", "now"). Just make
              sure not to forget quotation marks. No days of the week.
        * <note_contents>: The remainder of the command message is stored as the note text.

        Example:

        .notes add @BlitheringIdiot#1234 perma Repeated plagiarism.
            Create a record timestamped for right now, with no expiry date.

        .notes add @BlitheringIdiot#1234 temp expires="in 7 days" Insulting users, altercation with
        intervening mod.
            Create a record timestamped for right now, that expires in 7 days.

        .notes add @CalmPerson#4187 good timestamp="2 hours ago" Cool-headed, helped keep the
        BlitheringIdiot plagiarism situation from exploding
            Create a record for an event 2 hours ago.
        """

        # !!! WARNING !!!
        # WARNING: BE CAREFUL OF THE DOCSTRING ABOVE! Must be <1992 chars (w/o indent) for .help

        logger.info("notes add: {}".format(message_log_str(ctx.message)))

        # load/preprocess positional arguments and defaults
        db_user = await c.query_user(self.bot, user)
        db_author = await c.query_user(self.bot, ctx.message.author.id)
        timestamp = None
        expires = None
        is_expires_set = False
        try:
            record_type = RecordType[type_.lower()]
        except KeyError as e:
            raise commands.BadArgument("'{}' is not a permitted record type ({})"
                .format(type_, ', '.join(t.name for t in RecordType))) from e

        # Parse and load kwargs from the note_contents, if present
        try:
            kwargs, note_contents = \
                parse_keyword_args(self.KW_TIME + self.KW_EXPIRE, note_contents)
        except ValueError as e:
            raise commands.BadArgument(e.args[0]) from e

        # Parse and validate the contents of the kwargs
        for key, arg in kwargs.items():
            if key.lower() in self.KW_TIME:
                if timestamp is None:
                    timestamp = dt_parse(arg, future=False)
                    if timestamp is None:  # dateparser failed to parse
                        raise commands.BadArgument("Invalid timespec: '{}'".format(arg))
                else:
                    raise commands.BadArgument("Several `timestamp`` arguments (+ synonyms) found.")
            elif key.lower() in self.KW_EXPIRE:
                if not is_expires_set:
                    is_expires_set = True  # to detect multiple args
                    if arg.lower() in ('none', 'never'):
                        expires = None
                    else:
                        expires = dt_parse(arg, future=True)
                        if expires is None:  # dateparser failed to parse
                            raise commands.BadArgument("Invalid timespec: '{}'".format(arg))
                else:
                    raise commands.BadArgument("Several `expires` arguments (+ synonyms) found.")

        # if any attachments, include a URL to it in the note
        if ctx.message.attachments:
            note_contents = "{0}\n\n{1}".format(
                note_contents,
                '\n'.join(a['url'] for a in ctx.message.attachments)
            )

        if len(note_contents) > self.EMBED_FIELD_LEN:
            raise commands.BadArgument('Note contents too long: '
                                       'max {:d} characters'.format(self.EMBED_FIELD_LEN))
        elif not note_contents:
            raise commands.BadArgument("No note contents.")

        # Record and user
        record = c.insert_note(user=db_user, author=db_author, type_=record_type,
                      timestamp=timestamp, expires=expires, body=note_contents)

        await self.show_record(self.channel_log, record=record, title='New Moderation Record')
        await self.bot.say("Added note #{:04d} for {}."
            .format(record.record_id, user_mention(record.user.discord_id)))

    @notes.command(pass_context=True, ignore_extra=False, aliases=['x', 'expire'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def expires(self, ctx, note_id: int, *, timespec: str="now"):
        """

        [MOD ONLY] Change the expiration time of an existing note.

        Arguments:
        * <note_id>: Required. The ID of the note. See `.help notes`.
        * [timespec]: Optional. The time at which the ban will expire. Default is now. Format
        accepted is the same as `.notes add` (quotation marks not required). See `.help notes add`.

        Example:
        .notes expires 122 tomorrow
            Change the expiration time of note #122 to tomorrow (24 hours from now).
        .notes expires 138 2018-01-24
            Change the expiration time of note #138 to 24 January 2018.
        """
        logger.info("notes expires: {}".format(message_log_str(ctx.message)))

        expires = dt_parse(timespec, future=True)
        if expires is None:  # dateparser failed to parse
            raise commands.BadArgument("Invalid timespec: '{}'".format(timespec))

        try:
            record = c.update_record(note_id, expires=expires)
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note ID {:04d} does not exist.".format(note_id))
        else:
            await self.show_record(ctx.message.channel,
                record=record, title='Note expiration updated')
            await self.show_record(self.channel_log,
                record=record, title='Note expiration updated')

    @notes.command(pass_context=True, ignore_extra=False, aliases=['r', 'remove'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def rem(self, ctx, note_id: int):
        """

        [MOD ONLY] Remove an existing note.

        To prevent accidental data deletion, the removed note can be viewed and restored by admin
        users.

        Arguments:
        * <note_id>: Required. The ID of the note to remove. See `.help notes`.

        Example:

        .notes rem 122
            Remove note number 122.
        """
        logger.info("notes rem: {}".format(message_log_str(ctx.message)))
        try:
            record = c.mark_removed_record(note_id)
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note ID {:04d} does not exist.".format(note_id))
        else:
            await self.show_record(ctx.message.channel, record=record, title='Note removed')
            await self.bot.send_message(self.channel_log, "Removed note #{:04d}".format(note_id))

    @notes.command(pass_context=True, ignore_extra=False)
    @admin_only()
    @admin_channels(delete_on_fail=True)
    async def removed(self, ctx, user: str, page: int=None):
        """

        [ADMIN ONLY] Show deleted notes.

        Arguments:
        * <user>: Required. The user to filter by, or `all`. See `.help notes`.
        * page: Optional[int]. The page number to access, if there are more than 1 pages of notes.
          Default: last page.
        """
        logger.info("notes removed: {}".format(message_log_str(ctx.message)))
        if user != 'all':
            db_user = await c.query_user(self.bot, user)
            db_group = c.query_user_group(db_user)
            db_records = c.query_user_records(db_group, removed=True)
        else:
            db_user = None
            db_group = None
            db_records = c.query_user_records(None, removed=True)

        records_pages = Pagination(db_records, self.NOTES_PAGE_SIZE, True)
        if page is not None:
            records_pages.page = max(1, min(records_pages.total_pages, page))

        await self.show_record_page(
            ctx.message.channel,
            records=records_pages, user=db_user, group=db_group, title='*** Removed Records'
        )

    @notes.command(pass_context=True, ignore_extra=False)
    @admin_only()
    @mod_channels(delete_on_fail=True)
    async def restore(self, ctx, note_id: int):
        """
        [ADMIN ONLY] Restore a removed note.

        Arguments:
        * <note_id>: Required. The ID of the note to remove. Use `.notes removed` to list.
        """
        logger.info("notes restore: {}".format(message_log_str(ctx.message)))
        try:
            record = c.mark_removed_record(note_id, removed=False)
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note #{:04d} does not exist or is not removed.".format(note_id))
        else:
            await self.show_record(ctx.message.channel, record=record, title='Note restored')
            await self.bot.send_message(self.channel_log, "Note #{:04d} restored".format(note_id))

    @notes.command(pass_context=True, ignore_extra=False)
    @admin_only()
    @mod_channels(delete_on_fail=True)
    async def purge(self, ctx, note_id: int):
        """
        [ADMIN ONLY] Permanently destroy a removed note.

        Arguments:
        * <note_id>: Required. The ID of the note to remove. Use `.notes removed` to list.
        """
        logger.info("notes purge: {}".format(message_log_str(ctx.message)))
        try:
            record = c.get_record(note_id, removed=True)
            await self.show_record(ctx.message.channel, record=record, title='Purging...')
            c.delete_removed_record(note_id)
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note #{:04d} does not exist or is not removed.".format(note_id))
        else:
            await self.bot.say("Record #{:04d} purged.".format(note_id))
            # don't send to channel_log, this has no non-admin visibility

    @notes.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def finduser(self, ctx, search_term: str, page: int=1):
        """

        [MOD ONLY] User search.

        This command searches the name and aliases fields.

        Arguments:
        * <search_term>: Required. A substring to search for in the user database's name and aliases
          fields.

        Example:

        .notes finduser Indium
            If there is a user called "IndiumPhosphide", they would be matched.
        """
        search_term_s = search_term[:Limits.NAME]
        logger.info("notes finduser: {}".format(message_log_str(ctx.message)))

        # Get results
        results = c.search_users(search_term_s)

        # Prepare for display
        len_results = len(results)
        total_pages = int(math.ceil(len_results/self.USEARCH_PAGE_SIZE))
        page = max(1, min(total_pages, page))

        results_lines = []
        start_index = (page-1)*self.USEARCH_PAGE_SIZE
        end_index = start_index + self.USEARCH_PAGE_SIZE

        for user in results[start_index:end_index]:
            matched_alias = self._find_match_field(user, search_term_s)

            # Format this user for the list display
            if not matched_alias:
                results_lines.append("{} - Canonical name: {}"
                    .format(self.format_display_user(user), user.name))
            else:
                results_lines.append("{} - Alias: {}".format(
                    self.format_display_user(user), matched_alias.name
                ))

        # Output - should always be sub-2000 characters (given length limits + page size)
        heading = self.USEARCH_HEADING_F.format(
            page=page, pages=total_pages,
            total=len_results, query=search_term_s
        )
        await self.bot.say("{}\n\n{}".format(heading, format_list(results_lines)))

    @staticmethod
    def _find_match_field(user: User, search_term: str) -> Optional[UserAlias]:
        """
        Find whether the canonical name or alias of a user was matched.

        Needed because the results don't indicate whether the canonical name or an alias was
        matched - only 20 results at a time so the processing time shouldn't be a concern.

        :param user:
        :param search_term:
        :return: The UserAlias object that matched, or None if the canonical name matches or
            no match is found (for now this is non-critical, it's a should-not-happen error case
            that just ends up displaying the canonical name - can change to raise ValueError
            in the future?)
        """
        if search_term.lower() in user.name.lower():
            return None

        # noinspection PyTypeChecker
        for alias_ in filter(lambda a: search_term.lower() in a.name.lower(), user.aliases):
            return alias_  # first one is fine
        else:  # if no results from the filter()
            logger.warning(("User is in results set but doesn't seem to match query? "
                            "Is something buggered? "
                            "Q: {!r} User: {!r} Check sqlalchemy output...")
                .format(search_term, user))

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def name(self, ctx, user: str, *, new_name: str):
        """

        [MOD ONLY] Set the canonical name by which a user is known. This replaces the previous name;
        to add aliases, see `.help notes alias`.

        This command searches the name and aliases fields.

        Arguments:
        * <user>: Required. The user to whom the note applies. See Section 1.
        * <new_name>: Required. The new canonical name to set for a user. Max 32 characters, no
          newlines.

        Example:

        .notes search Indium
            If there is a user called "IndiumPhosphide", they would be matched.
        """
        logger.info("notes name: {}".format(message_log_str(ctx.message)))
        new_name_s = new_name.split('\n', maxsplit=1)[0][:Limits.NAME]
        db_user = await c.query_user(self.bot, user)
        c.set_user_name(db_user, new_name_s)
        await self.bot.say("Updated user {} canonical name to '{}'"
            .format(self.format_display_user(db_user), db_user.name))

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def alias(self, ctx, addrem: str, user: str, *, alias: str):
        """

        [MOD ONLY] Set or remove alternative names a user is known under.

        Suggested usage: /u/RedditUsername for Reddit usernames, R:Nickname for IRC registered
        nicknames, nick!username@hostname masks for unregistered IRC users (or whatever format you
        prefer to communicate the relevant information, this is freeform).

        Arguments:
        * <add|rem>: Required. Whether to add or remove the indicated alias.
        * <user>: Required. The user to whom the note applies. See `.help notes`.
        * <alias>: Required. The alias to set for the user. Max 32 characters, no newlines.

        Example:
        .notes alias add @FireAlchemist#1234 The Flame Alchemist
        """
        logger.info("notes alias: {}".format(message_log_str(ctx.message)))
        alias_s = alias.split('\n', maxsplit=1)[0][:Limits.NAME]
        addrem = addrem[0].lower()
        if addrem == 'a':
            db_user = await c.query_user(self.bot, user)
            try:
                c.add_user_alias(db_user, alias_s)
            except db.core_exc.IntegrityError:  # probably UNIQUE constraint
                msg_format = "Cannot update user {0}: alias '{1}' already exists"
            else:
                msg_format = "Updated user {0} - added alias '{1}'"

        elif addrem == 'r':
            db_user = await c.query_user(self.bot, user)
            alias_s = alias.split('\n', maxsplit=1)[0][:Limits.NAME]
            try:
                c.remove_user_alias(db_user, alias)
            except db.orm_exc.NoResultFound:
                msg_format = "Cannot remove alias for {0} - no such alias '{1}'"
            else:
                msg_format = "Updated user {0} - removed alias '{1}'"

        else:
            raise commands.BadArgument("Argument 1 of `.notes alias` must be `add` or `rem`")

        await self.bot.say(msg_format.format(self.format_display_user(db_user), alias_s))

    @notes.group(pass_context=True, invoke_without_command=True, ignore_extra=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def group(self, ctx):
        """
        [MOD ONLY] Group and ungroup users together.

        An identity group identifies users which are all considered to be the same
        individual. The .notes command will show the user info and records for both simultaneously,
        if one of them is looked up. The users remain separate and can be removed from the group
        later.
        """

        command_list = list(self.group.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

    @group.command(name='add', pass_context=True, ignore_extra=False, aliases=['a'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def group_add(self, ctx, user1: str, user2: str):
        """
        Group two users together.

        If one user is not in a group, that user is added to the other user's group. If both users
        are in separate groups, both groups are merged. This is irreversible.

        See `.help group` for more information on grouping.

        Arguments:
        * <user1> and <user2>: Required. The two users to link. See `.help notes`.

        Example:
        .notes group add @FireAlchemist#1234 @TinyMiniskirtEnthusiast#4444
        """
        logger.info("notes group: {}".format(message_log_str(ctx.message)))
        db_user1 = await c.query_user(self.bot, user1)
        db_user2 = await c.query_user(self.bot, user2)

        if db_user1.group_id is None or db_user1.group_id != db_user2.group_id:
            c.group_users(db_user1, db_user2)
            msg = "Grouped users {0} and {1}"
        else:
            msg = "Error: Users {0} and {1} are already in the same group!"

        await self.bot.say(
            msg.format(self.format_display_user(db_user1), self.format_display_user(db_user2))
        )

    @group.command(name='rem', pass_context=True, ignore_extra=False, aliases=['r', 'remove'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def group_rem(self, ctx, user: str):
        """
        Remove a user from the group.

        See `.help group` for more information on grouping.

        Arguments:
        * <user>: Required. The user to ungroup. See `.help notes`.

        Example:
        .notes group rem @FireAlchemist#1234
        """
        logger.info("notes group: {}".format(message_log_str(ctx.message)))
        db_user = await c.query_user(self.bot, user)

        if db_user.group_id is not None:
            c.ungroup_user(db_user)
            msg = "Ungrouped user {0}"
        else:
            msg = "Error: Cannot ungroup user {0}: user is not in a group"

        await self.bot.say(msg.format(self.format_display_user(db_user)))

    @add.error
    @removed.error
    @name.error
    @alias.error
    async def on_error_query_user(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc

            if isinstance(root_exc, ValueError) and root_exc.args and 'user ID' in root_exc.args[0]:
                logger.warning("Invalid user argument: {!s}. For {}".format(root_exc, cmd_string))
                await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                    " User format is not valid. User must be specified as an @mention, as a Discord "
                    "ID (numerical only), or a KazTron ID (`*` followed by a number).")

            elif isinstance(root_exc, c.UserNotFound):
                logger.warning("User not found: {!s}. For {}".format(root_exc, cmd_string))
                await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                    " User was not found. The user must either exist in the KazTron modnotes "
                    "database already, or exist on Discord (for @mentions and Discord IDs).")

            else:
                core_cog = self.bot.get_cog("CoreCog")
                await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            core_cog = self.bot.get_cog("CoreCog")
            await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @notes.error
    async def on_error_notes(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)

        if ctx is not None and ctx.command is not None:
            usage_str = get_usage_str(ctx)
        else:
            usage_str = '(Unable to retrieve usage information)'

        if isinstance(exc, commands.BadArgument):
            msg = "Bad argument passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                (" Invalid argument(s). Did you mean `.notes add`?"
                 "\n\n**Usage:** `{}`\n\nUse `{}` for help.")
                    .format(get_command_str(ctx), usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.TooManyArguments):
            msg = "Too many arguments passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                (" Too many arguments. Did you mean `.notes add`?\n\n"
                 "**Usage:** `{}`\n\nUse `{}` for help.")
                    .format(usage_str, get_help_str(ctx)))
        else:
            await self.on_error_query_user(exc, ctx)

    @group_add.error
    async def on_error_group_add(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.TooManyArguments):
            logger.warning("Too many args: {}".format(exc, cmd_string))
            await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                " Too many arguments. Note that you can only `{}` two users at a time."
                .format(get_command_str(ctx)))
        else:
            await self.on_error_query_user(exc, ctx)

    @group_rem.error
    async def on_error_group_rem(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.TooManyArguments):
            logger.warning("Too many args: {}".format(exc, cmd_string))
            await self.bot.send_message(ctx.message.channel, ctx.message.author.mention +
                " Too many arguments. "
                "Note that you can only `{}` *one* user from its group at a time."
                    .format(get_command_str(ctx)))
        else:
            await self.on_error_query_user(exc, ctx)
