import logging
import math
from typing import List, Optional

import discord
from discord.ext import commands
from kaztron.config import get_kaztron_config
from kaztron.driver import database as db
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.discord import Limits, user_mention
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import format_list, get_help_str

from kaztron.cog.modnotes.model import User, UserAlias
from kaztron.cog.modnotes import controller as c

logger = logging.getLogger(__name__)


class ModNotes:
    NOTES_PAGE_SIZE = 20
    USEARCH_PAGE_SIZE = 20

    USEARCH_HEADING_F = "**USER SEARCH RESULTS [{page}/{pages}]** - {total} results for `{query!r}`"

    def __init__(self, bot):
        self.bot = bot  # type: commands.Bot
        self.config = get_kaztron_config()
        self.ch_output = discord.Object(self.config.get("discord", "channel_output"))

    @staticmethod
    def format_display_user(db_user: User):
        return "<@{}> (\*{})".format(db_user.discord_id, db_user.user_id)

    @commands.group(aliases=['note'], invoke_without_command=True, pass_context=True,
        ignore_extra=False)
    @mod_only()
    @mod_channels()
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
        db_user = await c.query_user(self.bot, user)
        db_group = c.query_user_group(db_user)

        em = discord.Embed(color=0xAA80FF, title=db_user.name)
        em.set_author(name="Moderation Record")
        em.add_field(name="Mention", value=user_mention(db_user.discord_id), inline=True)

        alias_str = '\n'.join(a.name for a in db_user.aliases)
        em.add_field(name="Aliases", value=alias_str if alias_str else 'None', inline=True)

        links_str = '\n'.join(user_mention(u.discord_id) for u in db_group)
        em.add_field(name="Links", value=links_str if links_str else 'None', inline=True)
        await self.bot.say(embed=em)

        # TODO: records

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels()
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
        # TODO: log all contents to a dedicated #mods-logs channel

    @notes.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
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
        # TODO: soft delete, unless permanently deleted by Admin - purge command?

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels()
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
        search_term_s = search_term[:Limits.NAME]
        logger.info("notes usearch: {}".format(message_log_str(ctx.message)))

        # Get results
        results = c.search_users(search_term_s)

        # Prepare for display
        len_results = len(results)
        total_pages = int(math.ceil(len_results/self.USEARCH_PAGE_SIZE))

        if page > total_pages:
            page = total_pages

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

        for alias_ in filter(lambda a: search_term.lower() in a.name.lower(), user.aliases):
            return alias_  # first one is fine
        else:  # if no results from the filter()
            logger.warning(("User is in results set but doesn't seem to match query? "
                            "Is something buggered? "
                            "Q: {!r} User: {!r} Check sqlalchemy output...")
                .format(search_term, user))

    @notes.command(pass_context=True)
    @mod_only()
    @mod_channels()
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
    @mod_channels()
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

    @notes.group(pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    @mod_channels()
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
    @mod_channels()
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
        db_user1 = await c.query_user(self.bot, user1)
        db_user2 = await c.query_user(self.bot, user2)
        c.group_users(db_user1, db_user2)
        await self.bot.say("Added link between users {} and {}"
            .format(self.format_display_user(db_user1), self.format_display_user(db_user2)))

    @link.command(name='rem', pass_context=True, ignore_extra=False, aliases=['r'])
    @mod_only()
    @mod_channels()
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
        db_user = await c.query_user(self.bot, user)
        c.ungroup_user(db_user)
        await self.bot.say("Updated user {0} - unlinked"
            .format(self.format_display_user(db_user)))
