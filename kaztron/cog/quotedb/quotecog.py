import random
import logging

import discord
from discord.ext import commands
from sqlalchemy import orm

from kaztron import KazCog
from kaztron.driver.pagination import Pagination
from kaztron.theme import solarized
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import Limits
from kaztron.utils.logging import message_log_str
from kaztron.utils.datetime import format_datetime

from kaztron.cog.quotedb.model import Quote
from kaztron.cog.quotedb import controller as c, model

logger = logging.getLogger(__name__)


class QuoteCog(KazCog):
    """
    The Quotes Database helps you capture the best moments on the server! Store your fellow members'
    funniest moments so that you can revisit them time and time again.
    """
    QUOTES_PER_PAGE = 15
    EMBED_COLOR = solarized.blue

    def __init__(self, bot):
        super().__init__(bot)
        self.grab_max = self.config.get("quotedb", "grab_search_max", 100)
        self.server = None  # type: discord.Server

    async def on_ready(self):
        await super().on_ready()
        self.server = self.channel_out.server

    def make_single_embed(self, quote: Quote,
                          index: int=None, total: int=None, title: str=None):
        quote_str = self.format_quote(quote, show_saved=False)
        if title is None:
            title = discord.Embed.Empty
        em = discord.Embed(title=title, description=quote_str, color=self.EMBED_COLOR)
        if index is not None and total is not None:
            em.set_footer(text="saved by {u} | {n:d}/{total:d}"
                .format(u=quote.saved_by.name, n=index, total=total))
        else:
            em.set_footer(text="saved by {u}".format(u=quote.saved_by.name))
        return em

    async def send_quotes_list(self,
                               dest: discord.Channel,
                               quotes: Pagination,
                               user: model.User,
                               server: discord.Server):
        title = "Quotes by {}".format(user.name)
        footer_text = "Page {:d}/{:d}".format(quotes.page + 1, quotes.total_pages)
        base_len = len(title) + len(footer_text)

        em = discord.Embed(title=title, color=self.EMBED_COLOR)

        start_index, end_index = quotes.get_page_indices()
        total_fields = 0
        total_len = base_len
        for i, quote in enumerate(quotes.get_page_records()):
            # Format strings for this quote
            f_name = "#{:d}".format(start_index + i + 1)
            f_message = self.format_quote(quote, show_saved=False) + '\n\\_\\_\\_'
            cur_len = len(f_name) + len(f_message)

            # check lengths and number of fields
            too_many_fields = total_fields + 1 > Limits.EMBED_FIELD_NUM
            embed_too_long = total_len + cur_len > int(0.95 * Limits.EMBED_TOTAL)

            # if we can't fit this quote in this embed, send it and start a new one
            if too_many_fields or embed_too_long:
                await self.bot.send_message(dest, embed=em)
                em = discord.Embed(title=title, color=self.EMBED_COLOR)
                total_len = base_len
                total_fields = 0

            # add the field for the current quote
            em.add_field(name=f_name, value=f_message, inline=False)

            # end of iteration updates
            total_len += cur_len

        em.set_footer(text=footer_text)
        await self.bot.send_message(dest, embed=em)

    @staticmethod
    def format_quote(quote: Quote, show_saved=True):
        s = "[{}] <#{}> <{}> {}".format(
            format_datetime(quote.timestamp, seconds=True),
            quote.channel_id,
            quote.author.mention,
            quote.message
        )
        if show_saved:
            s += "\n*(saved by {})*".format(quote.saved_by.name)
        return s

    @commands.group(aliases=['quotes'], pass_context=True, invoke_without_command=True,
                    ignore_extra=False)
    async def quote(self, ctx: commands.Context, user: str, number: int=None):
        """
        Retrieve a quote.

        If a quote number isn't given, find a random quote.

        Arguments:
        * user: Required. The user to find a quote for. Example formats:
            * @mention of the user (make sure it actually links them)
            * User's name + discriminator: JaneDoe#0921
            * Discord ID number: 123456789012345678
        * number: Optional. The ID number of the quote to delete (starting from 1), as shown by
            the `.quote` or `.quote list` commands.

        Examples:
            .quote @JaneDoe - Find a random quote by JaneDoe.
            .quote @JaneDoe 4 - Find the 4th quote by JaneDoe.
        """
        logger.info("quote: {}".format(message_log_str(ctx.message)))
        db_user = c.query_user(self.server, user)
        db_records = c.query_author_quotes(db_user)
        len_recs = len(db_records)

        if number is None:
            number = random.randint(1, len_recs)
            logger.info("Selected random quote {:d} by user {!r}...".format(number, db_user))
        else:
            logger.info("Requested quote {:d} by user {!r}".format(number, db_user))

        if number < 1 or number > len_recs:
            logger.warning("Invalid index {:d}".format(number))
            await self.bot.say("Oops, I can't get quote {:d} for {}! Valid quotes are 1 to {:d}"
                .format(number, db_user.name, len_recs))
            return

        em = self.make_single_embed(db_records[number - 1], number, len_recs)
        await self.bot.say(embed=em)

    @quote.command(name='find', pass_context=True)
    async def quote_find(self, ctx: commands.Context, user: str, *, search: str=None):
        """
        Find the most recent quote matching a user and/or text search.

        Arguments:
        * user: Required. The user to find a quote for, or part of their name or nickname to search,
            or "all". For exact user matches, see `.help quote` for valid formats.
        * search: Optional. Text to search in the quote.

        Examples:
            .quote find Jane - Find a quote for a user whose user/nickname contains "Jane".
            .quote find @JaneDoe flamingo - Find a quote containing "flamingo" by JaneDoe.
            .quote find Jane flamingo - Find a quote matching user "Jane" and containing "flamingo".
        """
        logger.info("quote find: {}".format(message_log_str(ctx.message)))

        try:
            db_user = c.query_user(self.server, user)
        except ValueError:  # not a valid user ID format
            if user != 'all':
                db_user = c.search_users(user)
            else:
                db_user = None

        db_records = c.search_quotes(search, db_user)
        em = self.make_single_embed(db_records[-1])
        await self.bot.say(embed=em)

    @quote.command(name='list', pass_context=True, ignore_extra=False)
    async def quote_list(self, ctx: commands.Context, user: str, page: int=None):
        """
        Retrieve a list of quotes. Reply is always PMed.

        Arguments:
        * user: Required. The user to find a quote for. See `.help quote` for valid formats.
        * page: Optional. The page number to access, if there are more than 1 pages of notes.
          Default: last page.

        Examples:
            .quote list @JaneDoe - List all quotes by JaneDoe (page 1 if multiple pages)..
            .quote list @JaneDoe 4 - List the 4th page of quotes by JaneDoe.
        """
        logger.info("quote list: {}".format(message_log_str(ctx.message)))
        db_user = c.query_user(self.server, user)
        db_records = c.query_author_quotes(db_user)
        paginator = Pagination(db_records, self.QUOTES_PER_PAGE, align_end=True)
        if page is not None:
            paginator.page = max(0, min(paginator.total_pages - 1, page-1))
        await self.send_quotes_list(ctx.message.author, paginator, db_user, ctx.message.server)

    @quote.command(name='add', pass_context=True, no_pm=True)
    async def quote_add(self, ctx: commands.Context, user: str, *, message: str):
        """
        Add a new quote manually.

        You can use `.quote grab` instead to automatically grab a recent message.

        Arguments:
        * user: Required. The user to find a quote for. See `.help quote` for valid formats.
        * message: Required. The quote text to add.

        Examples:
            .quote add @JaneDoe Ready for the mosh pit, shaka brah.
        """
        logger.info("quote add: {}".format(message_log_str(ctx.message)))
        if len(message) > Quote.MAX_MESSAGE_LEN:
            raise ValueError("That quote is too long! Maximum length {:d} characters."
                .format(Quote.MAX_MESSAGE_LEN))
        quote = c.store_quote(
            user=c.query_user(self.server, user),
            saved_by=c.query_user(self.server, ctx.message.author.id),
            channel_id=ctx.message.channel.id,
            message=message,
            timestamp=ctx.message.timestamp
        )

        message = "Added quote: {}".format(self.format_quote(quote))
        logger.info(message)
        await self.bot.say(embed=self.make_single_embed(quote, title="Added quote."))
        await self.send_output(message)

    @quote.command(name='grab', pass_context=True, no_pm=True)
    async def quote_grab(self, ctx: commands.Context, user: discord.Member, *, search: str=None):
        """
        Find the most recent matching message and add it as a quote.

        This command searches the most recent messages (default 100 messages). The most recent
        message matching both the user and (if specified) search text is added as a quote.

        You can use `.quote add` instead to manually add the quote.

        Arguments:
        * user: Required. The user to find a quote for. See `.help quote` for valid formats.
        * search: Optional. The quote text to find among the user's recent messages.

        Examples:
            .quote grab @JaneDoe
                Quote the most recent message from @JaneDoe.
            .quote grab @JaneDoe mosh pit
                Finds the most recent message from @JaneDoe containing "mosh pit".
        """
        logger.info("quote grab: {}".format(message_log_str(ctx.message)))
        async for message in self.bot.logs_from(ctx.message.channel, self.grab_max): \
                # type: discord.Message
            # if requested author, and this message isn't the invoking one (in case of self-grab)
            if message.author == user and message.id != ctx.message.id:
                if not search or search in message.content:
                    grabbed_message = message
                    break
        else:  # Nothing found
            if search:
                await self.bot.say(("No message from {} matching '{}' "
                                   "found in the last {:d} messages")
                    .format(user.nick, search, self.grab_max))
            else:
                await self.bot.say("No message from {} found in the last {:d} messages"
                    .format(user.nick, self.grab_max))
            return

        message_text = grabbed_message.content
        if grabbed_message.attachments:
            message_text = "{0}\n\n{1}".format(
                message_text,
                '\n'.join(a['url'] for a in ctx.message.attachments)
            )

        if len(message_text) > Limits.EMBED_FIELD_VALUE:
            raise ValueError("That quote is too long! Maximum length 1024 characters.")

        quote = c.store_quote(
            user=c.query_user(self.server, grabbed_message.author.id),
            saved_by=c.query_user(self.server, ctx.message.author.id),
            channel_id=grabbed_message.channel.id,
            message=message_text,
            timestamp=grabbed_message.timestamp
        )

        message_text = "Added quote: {}".format(self.format_quote(quote))
        logger.info(message_text)
        await self.bot.say(embed=self.make_single_embed(quote, title="Added quote."))
        await self.send_output(message_text)

    @quote.command(name='rem', pass_context=True, ignore_extra=False)
    @mod_only()
    async def quote_remove(self, ctx: commands.Context, number: int):
        """
        Remove one of your own quotes.

        THIS COMMAND CANNOT BE UNDONE.

        This command is limited to quotes attributed to you. For any other situations, please
        contact the moderators to delete quotes.

        Arguments:
        * number: Optional. The ID number of the quote to delete (starting from 1), as shown by
            the `.quote` or `.quote list` commands.

        Examples:
            .quote del 4 - Delete the 4th quote attributed to you.
        """
        logger.info("quote rem: {}".format(message_log_str(ctx.message)))
        db_user = c.query_user(self.server, ctx.message.author.id)
        db_records = c.query_author_quotes(db_user)
        len_recs = len(db_records)

        if number < 1 or number > len_recs:
            logger.warning("Invalid index {:d}".format(number))
            await self.bot.say("Oops, I can't get quote {:d} for {}! Valid quotes are 1 to {:d}"
                .format(number, db_user.name, len_recs))
            return

        quote = db_records[number - 1]
        message_text = "Removed quote (remove): {}".format(self.format_quote(quote))
        em = self.make_single_embed(quote, number, len_recs, title="Quote deleted.")
        c.remove_quotes([quote])
        await self.bot.say(embed=em)
        await self.send_output(message_text)

    @quote.command(name='undo', pass_context=True, ignore_extra=False)
    async def quote_undo(self, ctx: commands.Context):
        """
        Remove the last quote you added.

        THIS COMMAND CANNOT BE UNDONE.

        This command only undoes `.quote add` or `.quote grab` actions. It does NOT undo
        `.quote rem` actions.
        """
        logger.info("quote undo: {}".format(message_log_str(ctx.message)))
        db_user = c.query_user(self.server, ctx.message.author.id)
        db_records = c.query_saved_quotes(db_user)

        quote = db_records[-1]
        message_text = "Removed quote (undo): {}".format(self.format_quote(quote))
        em = self.make_single_embed(quote, title="Quote deleted.")
        c.remove_quotes([quote])
        await self.bot.say(embed=em)
        await self.send_output(message_text)

    @quote.command(name='del', pass_context=True, ignore_extra=False)
    @mod_only()
    async def quote_delete(self, ctx: commands.Context, user: str, number):
        """
        [MOD ONLY] Delete one or all quotes attributed to a user.

        Arguments:
        * user: Required. The user to find a quote for. See `.help quote` for valid formats.
        * number: Required. The ID number of the quote to delete (starting from 1), or "all".

        Examples:
            .quote rem @JaneDoe 4 - Delete the 4th quote by JaneDoe.
            .quote rem @JaneDoe all - Remove all quotes by JaneDoe.
        """
        logger.info("quote del: {}".format(message_log_str(ctx.message)))
        db_user = c.query_user(self.server, user)
        db_records = c.query_author_quotes(db_user)
        len_recs = len(db_records)

        if number == 'all':
            logger.info("Removing all {} quotes for {!r}...".format(len_recs, db_user))
            c.remove_quotes(db_records)
            await self.bot.say("Removed all {} quotes for {}.".format(len_recs, db_user.mention))
            await self.send_output("Removed all {} quotes for {}."
                .format(len_recs, db_user.mention))
        else:
            try:
                number = int(number)
            except ValueError:
                raise commands.BadArgument("Cannot convert number to int")

            if number < 1 or number > len_recs:
                logger.warning("Invalid index {:d}".format(number))
                await self.bot.say("Oops, I can't get quote {:d} for {}! Valid quotes are 1 to {:d}"
                    .format(number, db_user.name, len_recs))
                return

            quote = db_records[number - 1]
            message_text = "Removed quote (mod): {}".format(self.format_quote(quote))
            em = self.make_single_embed(quote, number, len_recs, title="Quote deleted.")
            c.remove_quotes([quote])
            await self.bot.say(embed=em)
            await self.send_output(message_text)

    @quote.error
    @quote_list.error
    @quote_add.error
    @quote_grab.error
    @quote_remove.error
    @quote_delete.error
    @quote_undo.error
    async def on_error_query_user(self, exc, ctx):
        cmd_string = message_log_str(ctx.message)
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc

            if isinstance(root_exc, ValueError) and root_exc.args and 'user ID' in root_exc.args[0]:
                logger.warning("Invalid user argument: {!s}. For {}".format(root_exc, cmd_string))
                await self.bot.send_message(ctx.message.channel,
                    "User format is not valid. User must be specified as an @mention or as a "
                    "Discord ID (numerical only).")

            elif isinstance(root_exc, c.UserNotFound):
                logger.warning("User not found: {!s}. For {}".format(root_exc, cmd_string))
                await self.bot.send_message(ctx.message.channel,
                    "No quotes found for that user.")

            elif isinstance(root_exc, orm.exc.NoResultFound):
                logger.warning("No quotes found: {!s}. For {}".format(root_exc, cmd_string))
                await self.bot.send_message(ctx.message.channel, "No quotes found.")

            else:
                await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
