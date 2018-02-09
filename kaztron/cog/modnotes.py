import enum
import math
import logging
from types import SimpleNamespace
from typing import List, Optional

import discord
from discord.ext import commands

from kaztron.driver import database as db
from kaztron.config import get_kaztron_config
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import user_mention, Limits
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list, get_help_str

logger = logging.getLogger(__name__)

cogdb = SimpleNamespace()
cogdb.engine = None
cogdb.Session = db.sessionmaker()
cogdb.Base = db.declarative_base()


class UserNotFound(RuntimeError):
    pass


class User(cogdb.Base):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, db.Sequence('user_id_seq'), primary_key=True, nullable=False)
    discord_id = db.Column(db.String(24), unique=True, nullable=False)
    name = db.Column(db.String(Limits.NAME))
    aliases = db.relationship('UserAlias', back_populates='user', lazy='joined')
    group_id = db.Column(db.Integer, nullable=True)
    records = db.relationship('Record', foreign_keys='Record.user_id',
                              back_populates='user')
    authorship = db.relationship('Record', foreign_keys='Record.author_id',
                                 back_populates='author')

    def __repr__(self):
        return "<User(user_id={:d}, discord_id={!r}, name={!r}, aliases=[{}])>"\
            .format(self.user_id,
            self.discord_id,
            self.name,
            ', '.join([repr(a) for a in self.aliases]))

    def __str__(self):
        return "{1} (*{0:d})".format(self.user_id, self.name)


class UserAlias(cogdb.Base):
    __tablename__ = 'aliases'

    alias_id = db.Column(db.Integer, db.Sequence('alias_id_seq'), primary_key=True, nullable=False)
    name = db.Column(db.String(Limits.NAME), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False, index=True)
    user = db.relationship('User')

    def __repr__(self):
        return "<Alias(alias_id={:d}, user_id={:d}, name={!r})>" \
            .format(self.alias_id, self.user_id, self.name)

    def __str__(self):
        return "{1} (alias *{0:d})".format(self.user_id, self.name)


class RecordType(enum.Enum):
    note = 0
    good = 1
    watch = 2
    int = 3
    warn = 4
    temp = 5
    perma = 6
    appeal = 7


class Record(cogdb.Base):
    __tablename__ = 'records'

    record_id = db.Column(db.Integer, db.Sequence('record_id_seq'), primary_key=True)
    timestamp = db.Column(db.TIMESTAMP, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    user = db.relationship('User', lazy='joined', foreign_keys=[user_id])
    author_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    author = db.relationship('User', lazy='joined', foreign_keys=[author_id])
    type = db.Column(db.Enum(RecordType), nullable=False)
    expires = db.Column(db.DateTime, nullable=True)
    body = db.Column(db.String(2048), nullable=False)

    def __repr__(self):
        return "<Record(record_id={:d})>" \
            .format(self.record_id)

    def __str__(self):
        raise NotImplementedError()  # TODO


class ModNotes:
    # TODO: Possible future enhancement: separate out all of the sqlalchemy database business logic
    # TODO: ... from the Discord API/"view" logic and make that its own class
    NOTES_PAGE_SIZE = 20
    USEARCH_PAGE_SIZE = 20

    USEARCH_HEADING_F = "**USER SEARCH RESULTS [{page}/{pages}]** - {total} results for `{query!r}`"

    def __init__(self, bot, session):
        self.bot = bot  # type: commands.Bot
        self.session = session
        self.config = get_kaztron_config()
        self.ch_output = discord.Object(self.config.get("discord", "channel_output"))

    async def _query_user(self, id_: str):
        """
        Find a user given an ID string passed by command, or create it if it does not exist.

        id_ can be passed to a command in three formats:
        * Discord Mention: <@123456789012345678>
        * Discord ID: 123456789012345678
        * Database ID: *134

        For Discord Mention or Discord ID, if the user is not found but exists on Discord, a new
        entry is created. In other cases, a :cls:`~.UserNotFound` error is raised.

        :raises UserNotFound: User was not found. Either the Discord user exists neither on Discord
            nor in the database, or a database ID was passed and could not be found.
        :raises discord.HTTPException: Discord API error occurred
        :raises db.exc.MultipleResultsFound: Should never happen - database is buggered.
        """
        discord_id = None
        db_id = None

        # Parse the passed ID
        if id_.isnumeric():
            discord_id = id_
        elif id_.startswith('<@') and id_.endswith('>'):
            discord_id = id_[2:-1]
            if not discord_id.isnumeric():
                raise ValueError('_query_user: Invalid discord ID format: must be numeric')
        elif id_.startswith('*'):
            db_id = int(id_[1:])
        else:
            raise ValueError('_query_user: Invalid user ID format')

        # Retrieve the user depending on the passed ID type
        if discord_id:
            logger.debug('_query_user: passed Discord ID: {}'.format(discord_id))
            # Try to find discord_id in database
            try:
                db_user = self.session.query(User).filter_by(discord_id=discord_id).one_or_none()
            except db.exc.MultipleResultsFound:
                logger.exception("Er, mate, I think we've got a problem here. "
                                 "The database is buggered.")
                raise

            if db_user:
                logger.debug('_query_user: found user: {!r}'.format(db_user))
            else:  # If does not exist - make a new user in database
                logger.debug('_query_user: user not found, creating record')
                try:
                    user = await self.bot.get_user_info(discord_id)
                except discord.NotFound as e:
                    raise UserNotFound('Discord user not found') from e
                db_user = User(discord_id=discord_id, name=user.name)
                try:
                    self.session.add(db_user)
                    self.session.commit()
                except:
                    self.session.rollback()
                    raise
                else:
                    logger.debug('_query_user: created user: {!r}'.format(db_user))

            # either way, return the dbuser
            return db_user

        else:  # database ID was passed
            logger.debug('_query_user: passed database ID: {}'.format(db_id))
            try:
                db_user = self.session.query(User).filter_by(user_id=db_id).one()
            except db.exc.NoResultFound as e:
                raise UserNotFound('Database user not found') from e
            except db.exc.MultipleResultsFound:
                logger.exception("Er, mate, I think we've got a problem here. "
                                 "The database is buggered.")
                raise
            else:
                logger.debug('_query_user: found user: {!r}'.format(db_user))
            return db_user

    def _query_group(self, user: User) -> List[User]:
        """ Get all users in a user's group. """
        return self.session.query(User).filter(User.group_id == user.group_id).all()

    @staticmethod
    def format_display_user(db_user: User):
        return "<@{}> (\*{})".format(db_user.discord_id, db_user.user_id)

    @commands.group(aliases=['note'], invoke_without_command=True, pass_context=True,
                    ignore_extra=False)
    @mod_only()
    async def notes(self, ctx, user: str, page: int=0):
        """
        [MOD ONLY] Access moderation logs.

        Arguments:
        * user: Required. The user for whom to find moderation notes. This can be an @mention, a
          Discord ID (numerical only), or a KazTron ID (starts with *).
        * page: Optional[int]. The page number to access, if there are more than 1 pages of notes.
          Default: 1.

        Example:
            .notes @User#1234
            .notes 330178495568436157 3
        """
        # TODO: remember to eager-load notes from the User object
        logger.info("notes: {}".format(message_log_str(ctx.message)))

    @notes.command(pass_context=True)
    @mod_only()
    async def add(self, ctx, user: str, type_: str, *, note_contents):
        """

        [MOD ONLY] Add a new note.

        If the <user> is not already known in the database, an entry will be created, using their
        current nickname as the canonical name. There is no need to create the user in advance.

        Arguments:
        * <user>: Required. The user to whom the note applies. See `.help notes`.
        * <type>: Required. The type of record. One of:
            * note: Generic note not falling under other categories.
            * good: Noteworthy positive contributions to the community.
            * watch: Moderation problems to watch out for.
            * int: Moderator intervention events.
            * warn: Formal warning issued.
            * temp: Temporary ban issued.
            * perma: Permanent ban issued.
            * appeal: Formal appeal received.
        * [OPTIONS]: Optional. Options of the form:
            * timestamp="timespec": Sets the note's time (e.g. the time at which a note happened).
              Default is now.
            * expires="timespec": Sets when a note expires. This is purely documentation: for
              example, to take note of when a temp ban ends, or a permaban appeal is available, etc.
              Default is no expiration.
            * The timespec is "smart". You can type a date and time (like "3 Dec 2017 5PM"), or
              relative times in natural language ("10 minutes ago", "in 2 days", "now"). Just make
              sure not to forget quotation marks.
        * <note_contents>: The remainder of the command message is stored as the note text.

        Example:

        .notes add @BlitheringIdiot#1234 perma Repeated plagiarism.
            This creates a record timestamped for right now, with no expiry date.

        .notes add @BlitheringIdiot#1234 temp expires="in 7 days" Insulting users, altercation with
        intervening mod.
            This creates a record timestamped for right now, that expires in 7 days.

        .notes add @CalmPerson#4187 good timestamp="2 hours ago" Cool-headed, helped keep the
        BlitheringIdiot plagiarism situation from exploding
            This creates a record for an event 2 hours ago.
        """
        logger.info("notes add: {}".format(message_log_str(ctx.message)))
        # TODO: parse note_contents for options

    @notes.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def rem(self, ctx, note_id: int):
        """

        [MOD ONLY] Remove an existing note.

        Arguments:
        * <user>: Required. The user to whom the note applies. See `.help notes`.

        Example:

        .notes rem 122
            Remove note number 122.
        """
        logger.info("notes rem: {}".format(message_log_str(ctx.message)))

    @notes.command(pass_context=True)
    @mod_only()
    async def usearch(self, ctx, search_term: str, page: int=1):
        """

        [MOD ONLY] User search.

        This command searches the name and aliases fields.

        Arguments:
        * <search_term>: Required. A substring to search for in the user database's name and aliases
          fields.

        Example:

        .notes search Indium
            If there is a user called "IndiumPhosphide", they would be matched.
        """
        search_term_s = search_term[:Limits.NAME].replace('%', '\\%').replace('_', '\\_')
        search_term_like = '%{}%'.format(search_term_s)
        logger.info("notes usearch: {}".format(message_log_str(ctx.message)))

        results = self.session.query(User).outerjoin(UserAlias)\
                      .filter(db.or_(User.name.ilike(search_term_like),
                                     UserAlias.name.ilike(search_term_like)))\
                      .order_by(User.name)\
                      .all()  # No limit/offset as sqlite is in-process - no transmission advantage

        logger.info("notes usearch: Found {:d} results for {!r}".format(len(results), search_term))
        await self._display_usearch(results, search_term_s, page)

    async def _display_usearch(self, results: List, search_term: str, page: int):
        """
        Format and send the results to the requesting channel.
        """
        len_results = len(results)
        total_pages = int(math.ceil(len_results/self.USEARCH_PAGE_SIZE))

        if page > total_pages:
            page = total_pages

        results_lines = []
        start_index = (page-1)*self.USEARCH_PAGE_SIZE
        end_index = start_index + self.USEARCH_PAGE_SIZE

        for user in results[start_index:end_index]:
            matched_alias = self._find_match_field(user, search_term)

            # Format this user for the list display
            if not matched_alias:
                results_lines.append("{} - Canonical name: {}"
                    .format(self.format_display_user(user), user.name))
            else:
                results_lines.append("{} - Alias: {}".format(
                    self.format_display_user(user), matched_alias.name
                ))

        # Output - should always be sub-2000 characters
        heading = self.USEARCH_HEADING_F.format(
            page=page, pages=total_pages,
            total=len_results, query=search_term
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

        for alias_ in filter(lambda a: search_term.lower() in a.name.lower(), user.aliases):
            return alias_  # first one is fine
        else:  # if no results from the filter()
            logger.warning(("User is in results set but doesn't seem to match query? "
                            "Is something buggered? "
                            "Q: {!r} User: {!r} Check sqlalchemy output...")
                .format(search_term, user))

    @notes.command(pass_context=True)
    @mod_only()
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
        db_user = await self._query_user(user)
        db_user_repr = repr(db_user)  # Want this before the update
        new_name_filt = new_name.split('\n', maxsplit=1)[0][:Limits.NAME]
        try:
            db_user.name = new_name_filt
            self.session.commit()
        except:
            self.session.rollback()
            raise
        else:
            logger.info("Updated user {} name to {!r}".format(db_user_repr, new_name_filt))
            await self.bot.say("Updated user {} canonical name to '{}'"
                .format(self.format_display_user(db_user), new_name_filt))

    @notes.command(pass_context=True)
    @mod_only()
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
        addrem = addrem[0].lower()
        if addrem == 'a':
            db_user = await self._query_user(user)
            await self._alias_add(db_user, alias)
        elif addrem == 'r':
            db_user = await self._query_user(user)
            await self._alias_rem(db_user, alias)
        else:
            raise commands.BadArgument("Argument 1 of `.notes alias` must be `add` or `rem`")

    async def _alias_add(self, db_user: User, alias: str):
        alias_filt = alias.split('\n', maxsplit=1)[0][:Limits.NAME]
        db_user_repr = repr(db_user)  # Want this before the update
        try:
            db_alias = UserAlias(user=db_user, name=alias_filt)
            db_user.aliases.append(db_alias)
            self.session.commit()
        except:
            self.session.rollback()
            raise
        else:
            logger.info("Updated user {} - added alias {!r}".format(db_user_repr, alias_filt))
            await self.bot.say("Updated user {0} - added alias '{1}'"
                .format(self.format_display_user(db_user), alias_filt))

    async def _alias_rem(self, user: User, alias: str):
        alias_filt = alias.split('\n', maxsplit=1)[0][:Limits.NAME]
        db_user_repr = repr(user)  # Want this before the update
        try:
            alias = [a for a in user.aliases if a.name.lower() == alias_filt.lower()][0]
        except IndexError:
            logger.warning("User {} - cannot remove alias - no such alias {!r}"
                .format(db_user_repr, alias_filt))
            await self.bot.say("Cannot remove alias for {0} - no such alias '{1}'"
                .format(self.format_display_user(user), alias_filt))
            return

        try:
            self.session.delete(alias)
            self.session.commit()
        except:
            self.session.rollback()
            raise
        else:
            logger.info("Updated user {} - removed alias {!r}".format(db_user_repr, alias_filt))
            await self.bot.say("Updated user {0} - removed alias '{1}'"
                .format(self.format_display_user(user), alias_filt))

    @notes.group(pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def link(self, ctx):
        """
        [MOD ONLY] Set or remove an identity link between two users.

        An identity link creates a group of users which are all considered to be the same
        individual. The .notes command will show the user info and records for both simultaneously,
        if one of them is looked up. The users remain separate and can be unlinked later.
        """

        command_list = list(self.link.commands.keys())
        await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                            'Use `{1}` or `{1} <subcommand>` for instructions.')
            .format(command_list, get_help_str(ctx)))

    @link.command(name='add', pass_context=True, ignore_extra=False, aliases=['a'])
    @mod_only()
    async def link_add(self, ctx, user1: str, user2: str):
        """
        Set an identity link between two users.

        If both users already have links to more users, the two linked groups are merged together.
        This is irreversible.

        See `.help link` for more information on linking.

        Arguments:
        * <user1> and <user2>: Required. The two users to link. See `.help notes`.

        Example:
        .notes link add @FireAlchemist#1234 @TinyMiniskirtEnthusiast#4444
        """
        logger.info("notes link: {}".format(message_log_str(ctx.message)))
        db_user1 = await self._query_user(user1)
        db_user2 = await self._query_user(user2)
        try:
            # If both are in groups, merge the groups
            if db_user1.group_id is not None and db_user2.group_id is not None:
                logger.debug("Merging group {1.group_id:d} into group {0.group_id:d}"
                    .format(db_user1, db_user2))
                for user in self._query_group(db_user2):
                    user.group_id = db_user1.group_id

            # if one is in a group, assign the ungrouped user to the grouped user
            elif db_user1.group_id is not None:
                logger.debug("Assigning user {1.user_id:d} to group {0.group_id:d}"
                    .format(db_user1, db_user2))
                db_user2.group_id = db_user1.group_id

            elif db_user2.group_id is not None:
                logger.debug("Assigning user {0.user_id:d} to group {1.group_id:d}"
                    .format(db_user1, db_user2))
                db_user1.group_id = db_user2.group_id

            # If neither are in a group, assign a new group
            else:
                logger.debug("Assigning users {0.user_id:d}, {1.user_id:d} to group {0.user_id:d}"
                    .format(db_user1, db_user2))
                db_user1.group_id = db_user2.group_id = db_user1.user_id

            self.session.commit()

        except:
            self.session.rollback()
            raise
        else:
            logger.info("Added link between {!r} and {!r}".format(db_user1, db_user2))
            await self.bot.say("Added link between users {} and {}"
                .format(self.format_display_user(db_user1), self.format_display_user(db_user2)))

    @link.command(name='rem', pass_context=True, ignore_extra=False, aliases=['r'])
    @mod_only()
    async def link_rem(self, ctx, user: str):
        """
        Unlink a user from other linked users.

        See `.help link` for more information on linking.

        Arguments:
        * <user>: Required. The user to unlink. See `.help notes`.

        Example:
        .notes link rem @FireAlchemist#1234
        """
        logger.info("notes link: {}".format(message_log_str(ctx.message)))
        db_user = await self._query_user(user)
        try:
            db_user.group_id = None
            self.session.commit()
        except:
            self.session.rollback()
            raise
        else:
            logger.info("Updated user {!r} -unlinked".format(db_user))
            await self.bot.say("Updated user {0} - unlinked"
                .format(self.format_display_user(db_user)))


def setup(bot):
    if cogdb.engine is None:
        cogdb.engine = db.make_sqlite_engine('modnotes.sqlite')
        cogdb.Session.configure(bind=cogdb.engine)
        cogdb.Base.metadata.create_all(cogdb.engine)
    bot.add_cog(ModNotes(bot, cogdb.Session()))
