import logging
from datetime import datetime
from typing import List, Union

import discord
from sqlalchemy import orm

# noinspection PyUnresolvedReferences
from kaztron.driver import database as db
from kaztron.cog.quotedb.model import *
from kaztron.driver.database import make_error_handler_decorator
from kaztron.utils.discord import extract_user_id

logger = logging.getLogger(__name__)

db_file = 'quotedb.sqlite'

engine = None
Session = db.sessionmaker()
session = Session()


class UserNotFound(RuntimeError):
    pass


def init_db():
    global engine, session
    engine = db.make_sqlite_engine(db_file)
    Session.configure(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)


on_error_rollback = make_error_handler_decorator(session, logger)


def query_user(server: discord.Server, id_: str):
    """
    Find a user given an ID string passed by command, or create it if it does not exist.

    id_ can be passed to a command as a discord mention ``<@123456789012345678>`` or
    ``<@!123456789012345678>``, or as a Discord ID ``123456789012345678`` (various malformed
    inputs may also be accepted, e.g., ``@123456789012345678``).

    For Discord Mention or Discord ID, if the user is not found but exists on Discord, a new
    entry is created. In other cases, a :cls:`~.UserNotFound` error is raised.

    :raises UserNotFound: User was not found. Either the Discord user exists neither on Discord
        nor in the database, or a database ID was passed and could not be found.
    :raises discord.HTTPException: Discord API error occurred
    :raises db.exc.MultipleResultsFound: Should never happen - database is buggered.
    """

    # Parse the passed ID
    try:
        discord_id = extract_user_id(id_)
    except discord.InvalidArgument:
        raise ValueError('Invalid Discord user ID format')
    logger.debug('query_user: passed Discord ID: {}'.format(discord_id))

    # Check if user exists
    try:
        db_user = session.query(User).filter_by(discord_id=discord_id).one()
    except db.orm_exc.MultipleResultsFound:
        logger.exception("Er, mate, I think we've got a problem here. "
                         "The database is buggered.")
        raise
    except db.orm_exc.NoResultFound:
        logger.debug('query_user: user not found, creating user')
        try:
            member = server.get_member(discord_id)  # type: discord.Member
        except discord.NotFound as e:
            raise UserNotFound('Discord user not found') from e
        db_user = create_user(member)
        logger.debug('query_user: created user: {!r}'.format(db_user))
    else:
        logger.debug('query_user: found user: {!r}'.format(db_user))

        try:
            member = server.get_member(discord_id)  # type: discord.Member
        except discord.NotFound:
            logger.warning("Can't find user {!r} on Discord, skipping update nicknames"
                .format(db_user))
        else:
            update_nicknames(db_user, member)

    return db_user


@on_error_rollback
def create_user(member: discord.Member) -> User:
    db_user = User(
        discord_id=member.id,
        name=member.nick if member.nick else member.name,
        username=member.name
    )
    session.add(db_user)
    session.commit()
    return db_user


def query_author_quotes(user: User) -> List[Quote]:
    results = session.query(Quote)\
        .filter_by(author_id=user.user_id)\
        .order_by(Quote.timestamp)\
        .all()
    try:
        results[0]
    except IndexError:
        raise orm.exc.NoResultFound
    logger.info("query_author_quotes: Found {:d} records by user {!r}".format(len(results), user))
    return results


def query_saved_quotes(user: User) -> List[Quote]:
    results = session.query(Quote) \
        .filter_by(saved_by_id=user.user_id) \
        .order_by(Quote.timestamp) \
        .all()
    try:
        results[0]
    except IndexError:
        raise orm.exc.NoResultFound
    logger.info("query_saved_quotes: Found {:d} records saved by user {!r}"
        .format(len(results), user))
    return results


def search_users(query: str) -> List[User]:
    """
    Search for users.
    :param query: The substring to search for.
    :return:
    """
    search_term_like = '%{}%'.format(query.replace('%', '\\%').replace('_', '\\_'))
    # noinspection PyUnresolvedReferences
    results = session.query(User) \
        .filter(db.or_(User.name.ilike(search_term_like, escape='\\'),
                       User.username.ilike(search_term_like, escape='\\'))) \
        .order_by(User.name) \
        .all()
    try:
        results[0]
    except IndexError:
        raise UserNotFound
    logger.info("search_users: Found {:d} results for {!r}".format(len(results), query))
    return results


def search_quotes(search_term: str=None, user: Union[User, List[User]]=None) -> List[Quote]:
    """
    Fulltext search for quotes.
    :param search_term: The substring to search for.
    :param user: optional user to filter by
    """

    if not user and not search_term:
        raise ValueError("Must specify at least 1 search criterion")

    if user:
        user_list = [user] if isinstance(user, User) else user  # type: List[User]
    else:
        user_list = []

    query = session.query(Quote)
    if user_list:
        # noinspection PyUnresolvedReferences
        query = query.filter(Quote.author_id.in_(u.user_id for u in user_list))

    if search_term:
        search_term_like = db.format_like(search_term)
        # noinspection PyUnresolvedReferences
        query = query.filter(Quote.message.ilike(search_term_like, escape='\\'))

    results = query.order_by(Quote.timestamp).all()
    try:
        results[0]
    except IndexError:
        raise orm.exc.NoResultFound
    logger.info("search_quotes: Found {:d} results for {!r}".format(len(results), query))
    return results


@on_error_rollback
def store_quote(
        user: User,
        saved_by: User,
        channel_id: str,
        message: str,
        timestamp: datetime=None):
    """
    Store a new quote.
    :param user: Author of the note.
    :param saved_by: User who initiated storage of this note.
    :param channel_id: Channel in which the quote was said.
    :param message: User's message to retain as a quote.
    :param timestamp: Time at which quote was said (or stored, if unavailable).
    :return:
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    logger.info("Inserting quote by {}...".format(user))
    logger.debug("store_quote: user={!s} saved_by={!s} timestamp={} message={!r}"
        .format(user, saved_by, timestamp.isoformat(' '), message))
    quote = Quote(
        timestamp=timestamp, author=user, saved_by=saved_by, channel_id=channel_id, message=message
    )
    session.add(quote)
    session.commit()
    return quote


@on_error_rollback
def update_nicknames(user: User, member: discord.Member):
    """
    Update a user's nicknames and usernames.
    """
    logger.debug("update_nicknames: Updating names: {!r}...".format(user))
    user.name = member.nick if member.nick else member.name
    user.username = member.name
    session.commit()
    logger.info("update_nicknames: Updated names: {!r}".format(user))


@on_error_rollback
def remove_quotes(quotes: List[Quote]):
    """
    Delete a quote object from the database.
    """
    for quote in quotes:
        logger.info("remove_quotes: Deleting quote {!r}...".format(quote))
        session.delete(quote)
    session.commit()
