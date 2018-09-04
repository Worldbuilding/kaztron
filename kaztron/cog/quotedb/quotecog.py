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
from kaztron.utils.datetime import format_datetime, format_date

from kaztron.cog.quotedb.model import Quote
from kaztron.cog.quotedb import controller as c, model

logger = logging.getLogger(__name__)


class QuoteCog(KazCog):
    """!kazhelp
    brief: Capture the best moments on the server!
    description: |
        The Quotes Database helps you capture the best moments on the server! Store your fellow
        members' funniest moments so that you can revisit them time and time again.
    contents:
        - quote:
            - find
            - list
            - add
            - grab
            - rem
            - undo
            - del
    """
    QUOTES_PER_PAGE = 15
    EMBED_COLOR = solarized.blue

    def __init__(self, bot):
        super().__init__(bot)
        self.grab_max = self.config.get("quotedb", "grab_search_max", 100)
        self.show_channel = self.config.get('quotedb', 'show_channel', True)
        self.date_format = self.config.get('quotedb', 'datetime_format', 'datetime')
        if self.date_format not in ('seconds', 'datetime', 'date'):
            raise ValueError("quotedb:date_format value invalid (seconds, datetime, date): {}"
                .format(self.date_format))

    def export_kazhelp_vars(self):
        return {
            'grab_search_max': "{:d}".format(self.grab_max)
        }

    def make_single_embed(self, quote: Quote,
                          index: int=None, total: int=None, title: str=None):
        quote_str = self.format_quote(quote, show_saved=False)
        if title is None:
            title = discord.Embed.Empty
        em = discord.Embed(title=title, description=quote_str, color=self.EMBED_COLOR)
        if index is None:
            index = quote.get_index() + 1
        if total is None:
            total = len(quote.author.quotes)
        em.set_footer(text="saved by {u} | {n:d}/{total:d}"
            .format(u=quote.saved_by.name, n=index, total=total))
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

    def format_quote(self, quote: Quote, show_saved=True):
        s_fmt = "[{0}] <#{1}> <{2}> {3}" if self.show_channel else "[{0}] <{2}> {3}"

        if self.date_format == 'seconds':
            timestamp_str = format_datetime(quote.timestamp, seconds=True)
        elif self.date_format == 'datetime':
            timestamp_str = format_datetime(quote.timestamp, seconds=False)
        elif self.date_format == 'date':
            timestamp_str = format_date(quote.timestamp)
        else:
            raise RuntimeError("Invalid date_format??")

        s = s_fmt.format(
            timestamp_str,
            quote.channel_id,
            quote.author.mention,
            quote.message
        )
        if show_saved:
            s += "\n*(saved by {})*".format(quote.saved_by.name)
        return s

    @commands.group(aliases=['quotes'], pass_context=True, invoke_without_command=True,
                    ignore_extra=False)
    async def quote(self, ctx: commands.Context, user: str=None, number: int=None):
        """!kazhelp
        description: |
            Retrieve a quote.

            If a user isn't given, pick a random quote. If a quote number isn't given, picks a
            random quote by that user.

            TIP: To search for a quote by keyword, use {{!quote find}}.
        parameters:
            - name: user
              type: "@user"
              optional: true
              default: all users
              description: >
                The user to find a quote for. Should be an @mention or a discord ID.
            - name: number
              type: number
              optional: true
              description: >
                The ID number of the quote to find (starting from 1), as shown by the {{!quote}},
                {{!quote find}} and {{!quote list}} commands.
        examples:
            - command: .quote
              description: Find a random quote.
            - command: .quote @JaneDoe#0921
              description: Find a random quote by JaneDoe.
            - command: .quote @JaneDoe#0921 4
              description: Find the 4th quote by JaneDoe.
        """
        if user:
            db_user = c.query_user(self.server, user)
            len_recs = len(db_user.quotes)

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
            quote = db_user.quotes[number - 1]
        else:
            quote = c.random_quote()
            number = quote.get_index() + 1
            len_recs = len(quote.author.quotes)
            logger.info("Selected random quote id={:d} from all users".format(quote.quote_id))

        em = self.make_single_embed(quote, number, len_recs)
        await self.bot.say(embed=em)

    @quote.command(name='find', pass_context=True)
    async def quote_find(self, ctx: commands.Context, user: str, *, search: str=None):
        """!kazhelp
        description: >
            Find a quote matching a user and/or text search. If multiple quotes are found, return
            a random one.
        parameters:
            - name: user
              type: "@user or string or \\"all\\""
              description: >
                The user to find a quote for. This can be an @mention, user ID, part
                of their name or nickname to search, or the special string "all" to find any user
                (i.e. search only by keyword).
            - name: search
              type: string
              optional: true
              description: The text to search.
        examples:
            - command: .quote find Jane
              description: Find a quote from any user whose name/nickname contains "Jane".
            - command: .quote find @JaneDoe#0921 flamingo
              description: Find a quote by JaneDoe containing "flamingo".
            - command: .quote find Jane flamingo
              description: Find a quote both matching user "Jane" and containing
                "flamingo".
        """
        try:
            db_user = c.query_user(self.server, user)
        except ValueError:  # not a valid user ID format
            if user != 'all':
                db_user = c.search_users(user)
            else:
                db_user = None

        db_records = c.search_quotes(search, db_user)
        quote = db_records[random.randint(0, len(db_records) - 1)]
        logger.debug("Selected: {!r}".format(quote))
        em = self.make_single_embed(quote)
        await self.bot.say(embed=em)

    @quote.command(name='list', pass_context=True, ignore_extra=False)
    async def quote_list(self, ctx: commands.Context, user: str, page: int=None):
        """!kazhelp
        description: Retrieve a list of quotes. Always PMed.
        parameters:
            - name: user
              type: "@user"
              description: >
                The user to find a quote for. Should be an @mention or a discord ID.
            - name: page
              type: number
              optional: true
              default: last page (most recent)
              description: The page number to show, if there are more than 1 page of quotes.
        examples:
            - command: .quote list @JaneDoe#0921
              description: List all quotes by JaneDoe.
            - command: .quote list @JaneDoe#0921 4
              description: List the 4th page of quotes by JaneDoe.
        """
        db_user = c.query_user(self.server, user)
        paginator = Pagination(db_user.quotes, self.QUOTES_PER_PAGE, align_end=True)
        if page is not None:
            paginator.page = max(0, min(paginator.total_pages - 1, page-1))
        await self.send_quotes_list(ctx.message.author, paginator, db_user, ctx.message.server)

    @quote.command(name='add', pass_context=True, no_pm=True)
    async def quote_add(self, ctx: commands.Context, user: str, *, message: str):
        """!kazhelp
        description: |
            Add a new quote manually.

            TIP: To automatically find and add a recent message, use {{!quote grab}}.
        parameters:
            - name: user
              type: "@user"
              description: >
                The user being quoted. Should be an @mention or a discord ID.
            - name: message
              type: string
              description: The quote text to add.
        examples:
            - command: .quote add @JaneDoe#0921 Ready for the mosh pit, shaka brah.
        """
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
        """!kazhelp
        description: |
            Find the most recent matching message and add it as a quote.

            This command searches the {{grab_search_max}} most recent messages in the channel. The
            most recent message matching both the user and (if specified) search text is added as a
            quote.

            TIP: To manually add a quote, use {{!quote add}}.
        parameters:
            - name: user
              type: "@user"
              description: >
                The user being quoted. Should be an @mention or a discord ID.
            - name: search
              type: string
              optional: true
              description: The quote text to find.
        examples:
            - command: .quote grab @JaneDoe#0921
              description: Quote the most recent message from JaneDoe.
            - command: .quote grab @JaneDoe#0921 mosh pit
              description: Finds the most recent message from @JaneDoe containing "mosh pit".
        """
        async for message in self.bot.logs_from(ctx.message.channel, self.grab_max): \
                # type: discord.Message
            # if requested author, and this message isn't the invoking one (in case of self-grab)
            if message.author == user and message.id != ctx.message.id:
                if not search or search.lower() in message.content.lower():
                    grabbed_message = message
                    break
        else:  # Nothing found
            if search:
                await self.bot.say(("No message from {} matching '{}' "
                                   "found in the last {:d} messages")
                    .format(user.nick if user.nick else user.name, search, self.grab_max))
            else:
                await self.bot.say("No message from {} found in the last {:d} messages"
                    .format(user.nick if user.nick else user.name, self.grab_max))
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
        """!kazhelp
        description: |
            Remove one of your own quotes.

            WARNING: This command cannot be undone!

            IMPORTANT: If you are being harassed via quotes, or quote are otherwise being abused,
            please report this to the mods.

            TIP: To delete a quote you quoted (instead of a quote attributed to you), use
            {{!quote undo}} to remove the most recent one. For any other situation, contact the
            mods.
        parameters:
            - name: number
              type: number
              description: The ID number of the quote to delete (starting from 1), as shown by the
                {{!quote}}, {{!quote find}} and {{!quote list}} commands.
        examples:
            - command: .quote del 4
              description: Delete the 4th quote attributed to you.
        """
        db_user = c.query_user(self.server, ctx.message.author.id)
        len_recs = len(db_user.quotes)

        if number < 1 or number > len_recs:
            logger.warning("Invalid index {:d}".format(number))
            await self.bot.say("Oops, I can't get quote {:d} for {}! Valid quotes are 1 to {:d}"
                .format(number, db_user.name, len_recs))
            return

        quote = db_user.quotes[number - 1]
        message_text = "Removed quote (remove): {}".format(self.format_quote(quote))
        em = self.make_single_embed(quote, number, len_recs, title="Quote deleted.")
        c.remove_quotes([quote])
        await self.bot.say(embed=em)
        await self.send_output(message_text)

    @quote.command(name='undo', pass_context=True, ignore_extra=False)
    async def quote_undo(self, ctx: commands.Context):
        """!kazhelp
        description: |
            Remove the last quote you added.

            WARNING: This command cannot be undone!

            TIP: This command only undoes your own calls to {{!quote add}} or {{!quote grab}}. It
            does **not** undo {{!quote rem}}, and does not undo quote commands by other users.

            TIP: To delete quotes attributed to you, use {{!quote rem}}.
        """
        db_user = c.query_user(self.server, ctx.message.author.id)
        quote = db_user.saved_quotes[-1]
        message_text = "Removed quote (undo): {}".format(self.format_quote(quote))
        em = self.make_single_embed(quote, title="Quote deleted.")
        c.remove_quotes([quote])
        await self.bot.say(embed=em)
        await self.send_output(message_text)

    @quote.command(name='del', pass_context=True, ignore_extra=False)
    @mod_only()
    async def quote_delete(self, ctx: commands.Context, user: str, number):
        """!kazhelp
        description: Delete one or all quotes attributed to a user. This is a moderative command;
            regular users should use {{!quote undo}} or {{!quote rem}}.
        parameters:
            - name: user
              type: "@user"
              description: The user whose quote to delete. Can be an @mention or discord ID.
            - name: number
              type: number or "all"
              description: The ID number of the quote to delete (starting from 1), or "all".
        examples:
            - command: .quote rem @JaneDoe#0921 4
              description: Delete the 4th quote by JaneDoe.
            - command: .quote rem @JaneDoe#0921 all
              description: Remove all quotes by JaneDoe.
        """
        db_user = c.query_user(self.server, user)
        len_recs = len(db_user.quotes)

        if number == 'all':
            logger.info("Removing all {} quotes for {!r}...".format(len_recs, db_user))
            c.remove_quotes(db_user.quotes)
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

            quote = db_user.quotes[number - 1]
            message_text = "Removed quote (mod): {}".format(self.format_quote(quote))
            em = self.make_single_embed(quote, number, len_recs, title="Quote deleted.")
            c.remove_quotes([quote])
            await self.bot.say(embed=em)
            await self.send_output(message_text)

    @quote.error
    @quote_find.error
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
