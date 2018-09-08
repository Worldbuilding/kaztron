from datetime import datetime
import logging
from collections import OrderedDict
from typing import Optional, Sequence

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron import theme
from kaztron.driver import database as db
from kaztron.driver.pagination import Pagination
from kaztron.utils.converter import NaturalInteger
from kaztron.utils.datetime import parse as dt_parse
from kaztron.utils.checks import mod_only, mod_channels, admin_only, admin_channels
from kaztron.utils.discord import Limits, user_mention, get_command_str, get_help_str, \
    get_usage_str, get_group_help
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import parse_keyword_args

from kaztron.utils.datetime import format_timestamp

from kaztron.cog.modnotes.model import User, Record, RecordType
from kaztron.cog.modnotes import controller as c

logger = logging.getLogger(__name__)


class ModNotes(KazCog):
    """!kazhelp
    brief: Store moderation notes about users.
    description: |
        The ModNotes cog implements the storage of records for use by moderators in the course
        of their duty, and as a tool of communication between moderators. It allows arbitrary text
        records to be recorded, alongside with the author and timestamp, associated to various
        community users.
    contents:
        - notes:
            - finduser
            - add
            - expires
            - rem
            - watches
            - temps
            - name
            - alias
            - group:
                - add
                - rem
            - removed
            - restore
            - purge
    """
    NOTES_PAGE_SIZE = 10
    USEARCH_PAGE_SIZE = 20

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
        await super().on_ready()
        self.channel_log = self.validate_channel(self.channel_log.id)

    @staticmethod
    def format_display_user(db_user: User):
        return "{} (`*{}`)".format(user_mention(db_user.discord_id), db_user.user_id)

    def _get_user_fields(self, user: User, group: Sequence[User]) -> OrderedDict:
        user_fields = OrderedDict()
        user_fields[user.name] = self.format_display_user(user)
        # noinspection PyTypeChecker
        user_fields['Aliases'] = '\n'.join(a.name for a in user.aliases) or 'None'
        if group:
            user_fields['Links'] = '\n'.join(self.format_display_user(u)
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

        await self.send_message(dest, embed=em)

    async def show_record_page(self, dest: discord.Object, *,
                               user: Optional[User],
                               group: Sequence[User]=None,
                               records: Pagination,
                               title: str):

        if group is None:
            group = []

        es = EmbedSplitter(color=self.COLOR_MAP[None], title=title)
        es.set_footer(text='Page {page:d}/{total:d} (Total {len:d} records)'
            .format(page=records.page + 1, total=records.total_pages, len=len(records)))

        # user information
        if user:
            user_fields = self._get_user_fields(user, group)
            for field_name, field_value in user_fields.items():
                es.add_field_no_break(name=field_name, value=field_value, inline=True)

        # separator
        sep_name = 'Records Listing'
        sep_value = self.EMBED_SEPARATOR
        es.add_field_no_break(name=sep_name, value=sep_value, inline=False)

        # records page
        for record in records:
            record_fields, contents = self._get_record_fields(record, show_user=True)

            for field_name, field_value in record_fields.items():
                es.add_field_no_break(name=field_name, value=field_value, inline=True)

            for field_name, field_value in contents.items():
                es.add_field(name=field_name, value=field_value, inline=False)

        await self.send_message(dest, embed=es)

    @commands.group(aliases=['note'], invoke_without_command=True, pass_context=True,
        ignore_extra=False)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def notes(self, ctx, user: str, page: int=None):
        """!kazhelp
        description: "Access a user's moderation logs."
        details: |
            10 notes are shown per page. This is partly due to Discord message length limits, and
            partly to avoid too large a data dump in a single request.
        parameters:
            - name: user
              type: "@user"
              description: "The user for whom to retrieve moderation notes. This can be an
                `@mention`, a Discord ID (numerical only), or a KazTron ID (starts with `*`)."
            - name: page
              optional: true
              default: last page (latest notes)
              type: number
              description: "The page number to show, if there are more than 1 page of notes."
        examples:
            - command: .notes @User#1234
            - command: .notes 330178495568436157 3
        """
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
        """!kazhelp
        description: Show all watches currently in effect (i.e. all `watch`, `int` and `warn`
            records that are not expired).
        details: |
            10 notes are shown per page. This is partly due to Discord message length limits, and
            partly to avoid too large a data dump in a single request.
        parameters:
            - name: page
              optional: true
              default: last page (latest notes)
              type: number
              description: The page number to show, if there are more than 1 page of notes.
        """
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
        """!kazhelp
        description: Show all tempbans currently in effect (i.e. non-expired `temp` records).
        details: |
            10 notes are shown per page. This is partly due to Discord message length limits, and
            partly to avoid too large a data dump in a single request.
        parameters:
            - name: page
              optional: true
              default: last page (latest notes)
              type: number
              description: The page number to show, if there are more than 1 page of notes.
        """
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
        """!kazhelp
        description: Add a new note.
        details: Attachments in the same message as the command are saved to the note.
        parameters:
            - name: user
              type: "@user"
              description: User. See {{!notes}}.
            - name: type_
              type: string
              description: |
                Type of record. One of:

                  * `note`: Miscellaneous note
                  * `good`: Positive contributions
                  * `watch`: Behaviours to monitor
                  * `int`: Moderator intervention
                  * `warn`: Formal warning
                  * `temp`: Temporary ban (enforced by bot)
                  * `perma`: Permanent ban (not auto-enforced)
                  * `appeal`: Formal appeal received, decisions, etc.
            - name: note_contents
              type: string
              description: 'Complex field of the form:
                `[timestamp="timespec"] [expires="timespec"] <contents>`'
            - name: "timestamp|starts|start|time"
              type: timespec
              optional: true
              default: now
              description: "Set the note's time (e.g. of an incident). The timespec is \\"smart\\",
                and can accept a date/time (`3 Dec 2017 5PM` - default timezone is UTC), or relative
                times (`10 minutes ago`, `in 2 days`, `now`). Quotation marks required. Do not use
                days of the week (e.g. Monday)."
            - name: "expires|expire|ends|end"
              type: timespec
              optional: true
              default: never
              description: 'Set when a note expires. Affects tempbans and the {{!notes watches}}
                function, otherwise is a remark for moderators. See above for timespec formats.'
            - name: contents
              type: string
              description: The note text to store.
        examples:
            - command: ".notes add @BlitheringIdiot#1234 perma Repeated plagiarism."
              description: Create a permanent ban record with no expiry date.
            - command:
                '.notes add @BlitheringIdiot#1234 temp expires="in 7 days" Insulted @JaneDoe#0422'
              description: Create a temp ban record that expires in 7 days.
            - command:
                '.notes add @CalmPerson#4187 good timestamp="2 hours ago" Helped keep an argument in
                check'
              description: Create a record for an incident 2 hours ago.
        """

        # !!! WARNING !!!
        # WARNING: BE CAREFUL OF THE DOCSTRING ABOVE! Must be <1992 chars (w/o indent) for .help

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
            .format(record.record_id, self.format_display_user(record.user)))

    @notes.command(pass_context=True, ignore_extra=False, aliases=['x', 'expire'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def expires(self, ctx, note_id: NaturalInteger, *, timespec: str="now"):
        """!kazhelp
        description: Change the expiration time of an existing note.
        parameters:
            - name: note_id
              type: number
              description: The ID of the note to edit. See {{!notes}}.
            - name: timespec
              type: timespec
              optional: true
              default: now
              description: The time that the note will expire. Format is the same as {{!notes add}}
                (but quotation marks not required).
        examples:
            - command: .notes expires 122 tomorrow
              description: Change the expiration time of note #122 to tomorrow (24 hours from now).
            - command: .notes expires 138 2018-01-24
              description: Change the expiration time of note #138 to 24 January 2018.
        """
        note_id: int

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
    async def rem(self, ctx, note_id: NaturalInteger):
        """!kazhelp
        description: Remove an existing note.
        details: To prevent accidental data deletion, the removed note can be viewed and restored by
            admin users.
        parameters:
            - name: note_id
              type: number
              description: The ID of the note to remove. See {{!notes}}.
        examples:
            - command: .notes rem 122
              description: Remove note number 122.
        """
        note_id: int

        try:
            record = c.mark_removed_record(note_id)
            user = record.user
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note ID {:04d} does not exist.".format(note_id))
        else:
            await self.show_record(ctx.message.channel, record=record, title='Note removed')
            await self.bot.send_message(self.channel_log, "Removed note #{:04d} for {}"
                .format(note_id, self.format_display_user(user)))

    @notes.command(pass_context=True, ignore_extra=False)
    @admin_only()
    @admin_channels(delete_on_fail=True)
    async def removed(self, ctx, user: str, page: int=None):
        """!kazhelp
        description: Show all removed notes, optionally filtered by user.
        parameters:
            - name: user
              type: "@user"
              description: The user to filter by, or `all`. See {{!notes}} for user format.
            - name: page
              optional: true
              default: last page (latest notes)
              type: number
              description: The page number to show, if there are more than 1 page of notes.
        """
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
    async def restore(self, ctx, note_id: NaturalInteger):
        """!kazhelp
        description: Restore a removed note.
        parameters:
            - name: note_id
              type: number
              description: The ID of the note to remove. See {{!notes}}.
        """
        note_id: int

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
    async def purge(self, ctx, note_id: NaturalInteger):
        """!kazhelp
        description: |
            Permanently destroy a removed now.

            NOTE: This function intentionally does not include a mass purge, to prevent broad data
            loss, accidental or malicious.
        parameters:
            - name: note_id
              type: number
              description: The ID of the note to remove. See {{!notes}}.
        """
        note_id: int

        try:
            record = c.get_record(note_id, removed=True)
            user = record.user
            await self.show_record(ctx.message.channel, record=record, title='Purging...')
            c.delete_removed_record(note_id)
        except db.orm_exc.NoResultFound:
            await self.bot.say("Note #{:04d} does not exist or is not removed.".format(note_id))
        else:
            await self.bot.say("Record #{:04d} purged (user {})."
                .format(note_id, self.format_display_user(user)))
            # don't send to channel_log, this has no non-admin visibility

    @notes.command(pass_context=True, ignore_extra=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def finduser(self, ctx):
        """!kazhelp
        brief: DEPRECATED. Use {{!whois}}.
        description: |
            Deprecated as of version 2.2. Use {{!whois}}.
        """
        await self.send_message(ctx.message.channel, "Deprecated (v2.2). Use `.whois` instead.")

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def name(self, ctx, user: str, *, new_name: str):
        """!kazhelp
        description: "Set the primary name for a user. This replaces the old name; to add aliases,
            use {{!notes alias}}."
        parameters:
            - name: user
              type: "@user"
              description: The user to modify. See {{!notes}} for user format.
            - name: new_name
              type: string
              description: The new primary name for the user. Max 32 characters, no newlines.
        examples:
            - command: .notes name @BlitheringIdiot#1234 Blathers
        """
        new_name_s = new_name.split('\n', maxsplit=1)[0][:Limits.NAME]
        db_user = await c.query_user(self.bot, user)
        c.set_user_name(db_user, new_name_s)
        await self.bot.say("Updated user {} canonical name to '{}'"
            .format(self.format_display_user(db_user), db_user.name))

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def alias(self, ctx, addrem: str, user: str, *, alias: str):
        """!kazhelp
        description: "Command group. Set or remove user's aliases."
        details: |
            Recommended usage:

            * Reddit usernames: `/u/RedditUsername`
            * IRC NickServ accounts: `R:Nickname`
            * Unregistered IRC users: `nick!username@hostname` masks
            * Known previous names or nicknames the user's known by in the community.

            **For other Discord accounts**, use {{!notes group}} instead to group the accounts and their
            modnotes together.
        parameters:
            - name: addrem
              type: "`add` or `rem`"
              description: Whether to add or remove an alias.
            - name: user
              type: "@user"
              description: The user to modify. See {{!notes}} for user format.
            - name: alias
              type: string
              description: The alias to add or remove. Max 32 characters, no newlines.
        examples:
            - command: ".notes alias add @FireAlchemist#6543 The Flame Alchemist"
        """
        alias_s = alias.split('\n', maxsplit=1)[0][:Limits.NAME]
        addrem = addrem[0].lower()
        if addrem == 'a':
            db_user = await c.query_user(self.bot, user)
            try:
                c.add_user_alias(db_user, alias_s)
            except db.core_exc.IntegrityError:  # probably UNIQUE constraint
                msg_format = "Cannot update user {0}: alias '{1}' already exists"
            except ValueError as e:
                msg_format = "Cannot update user {0}: " + e.args[0]
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
        """!kazhelp
        description: |
            Command group. Group accounts belonging to the same user.

            A group identifiers different Discord accounts that are all considered to be the same
            individual. The {{!notes}} command will show the user info and records for both
            simultaneously when either user account is looked up.

            The users' notes remain separate and can be removed from the group later.
        """
        await self.bot.say(get_group_help(ctx))

    @group.command(name='add', pass_context=True, ignore_extra=False, aliases=['a'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def group_add(self, ctx, user1: str, user2: str):
        """!kazhelp
        description: |
            Group two users together.

            If one user is already in a group, the other user is added to that group.

            If both users are in separate groups, both groups are merged. This is irreversible.

            See {{!notes group}} for more information on grouping.
        parameters:
            - name: user1, user2
              type: "@user"
              description: The users to group. See {{!notes}} for user format.
        examples:
            - command: .notes group add @FireAlchemist#1234 @TinyMiniskirtEnthusiast#4444
        """
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
        """!kazhelp
        description: |
            Remove a user from the group.

            See {{!notes group}} for more information on grouping.

            NOTE: You only need to specify 1 user, who will be disassociated from all other users
            in the group. The other users will remain grouped together.
        parameters:
            - name: user
              type: "@user"
              description: The user to modify. See {{!notes}} for user format.
        examples:
            - command: .notes group rem #FireAlchemist#1234
        """
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
                    " User format is not valid. User must be specified as an @mention, as a "
                    "Discord ID (numerical only), or a KazTron ID (`*` followed by a number).")

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
                    .format(usage_str, get_help_str(ctx)))
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
