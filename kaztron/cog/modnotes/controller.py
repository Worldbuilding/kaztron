import logging
from datetime import datetime
from typing import List, Union, Tuple

import discord

from kaztron.driver import database as db
from kaztron.cog.modnotes.model import *
from kaztron.utils.strings import get_timestamp_str

logger = logging.getLogger(__name__)

db_file = 'modnotes.sqlite'

engine = None
Session = db.sessionmaker()
session = Session()


class UserNotFound(RuntimeError):
    pass


def on_error_rollback(func):
    """
    Decorator for database operations. Any raised exceptions will cause a rollback, and then be
    re-raised.
    """
    def db_safe_exec(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error('Error ({!s}) - rolling back'.format(e))
            session.rollback()
            raise
    return db_safe_exec


def init_db():
    global engine, session
    engine = db.make_sqlite_engine(db_file)
    Session.configure(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)


async def query_user(bot, id_: str):
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
            db_user = session.query(User).filter_by(discord_id=discord_id).one_or_none()
        except db.orm_exc.MultipleResultsFound:
            logger.exception("Er, mate, I think we've got a problem here. "
                             "The database is buggered.")
            raise

        if db_user:
            logger.debug('_query_user: found user: {!r}'.format(db_user))
        else:  # If does not exist - make a new user in database
            logger.debug('_query_user: user not found, creating record')
            try:
                user = await bot.get_user_info(discord_id)
            except discord.NotFound as e:
                raise UserNotFound('Discord user not found') from e
            db_user = User(discord_id=discord_id, name=user.name)
            try:
                session.add(db_user)
                session.commit()
            except:
                session.rollback()
                raise
            else:
                logger.debug('_query_user: created user: {!r}'.format(db_user))

        # either way, return the dbuser
        return db_user

    else:  # database ID was passed
        logger.debug('_query_user: passed database ID: {}'.format(db_id))
        try:
            db_user = session.query(User).filter_by(user_id=db_id).one()
        except db.orm_exc.NoResultFound as e:
            raise UserNotFound('Database user not found') from e
        except db.orm_exc.MultipleResultsFound:
            logger.exception("Er, mate, I think we've got a problem here. "
                             "The database is buggered.")
            raise
        else:
            logger.debug('_query_user: found user: {!r}'.format(db_user))
        return db_user


def query_user_group(user: User) -> List[User]:
    """
    Get all users in a user's group. If no group, returns a list containing only the passed user.
    """
    if user.group_id is not None:
        return session.query(User).filter(User.group_id == user.group_id).all()
    else:
        return [user]


def query_user_records(user_group: Union[User, List[User]]) -> List[Record]:
    """
    :param user_group: User or user group as a list of users.
    :return:
    """
    if isinstance(user_group, User):
        user_list = [User]
    else:
        user_list = user_group  # type: List[User]

    user_ids = [u.user_id for u in user_list]

    results = session.query(Record) \
        .filter(Record.user_id.in_(user_ids)) \
        .order_by(db.desc(Record.timestamp)) \
        .all()
    logger.info("query_user_records: "
                "Found {:d} records for user group: {!r}".format(len(results), user_group))
    return results


def search_users(search_term: str) -> List[User]:
    """
    Search for users.

    :param search_term: The substring to search for - should already be sanitised!
    :return:
    """
    search_term_like = '%{}%'.format(search_term.replace('%', '\\%').replace('_', '\\_'))
    results = session.query(User).outerjoin(UserAlias) \
        .filter(db.or_(User.name.ilike(search_term_like),
                UserAlias.name.ilike(search_term_like))) \
        .order_by(User.name) \
        .all()
    logger.info("search_users: Found {:d} results for {!r}".format(len(results), search_term))
    return results


@on_error_rollback
def set_user_name(user: User, new_name: str) -> User:
    if '\n' in new_name or len(new_name) > Limits.NAME:
        raise ValueError('Invalid alias')

    logger.info("Updating user {0!r} name from {0.name!r} to {1!r}".format(user, new_name))
    user.name = new_name
    session.commit()
    return user


@on_error_rollback
def add_user_alias(user: User, alias: str) -> UserAlias:
    """
    :return: the created UserAlias object
    :raise db.core_exc.IntegrityError: Alias already exists for user
    """
    if '\n' in alias or len(alias) > Limits.NAME:
        raise ValueError('Invalid alias')

    logger.info("Updating user {0!r} - adding alias {1!r}".format(user, alias))
    db_alias = UserAlias(user=user, name=alias)
    user.aliases.append(db_alias)
    session.commit()
    return db_alias


@on_error_rollback
def remove_user_alias(user: User, alias: str):
    """
    :raise db.exc.NoResultFound: Alias could not be found for user
    """
    try:
        alias = [a for a in user.aliases if a.name.lower() == alias.lower()][0]
    except IndexError as e:
        err_msg = "User {!r} - cannot remove alias - no such alias {!r}".format(user, alias)
        logger.warning(err_msg)
        raise db.orm_exc.NoResultFound(err_msg) from e

    logger.info("Updating user {0!r} - removing alias {1!r}".format(user, alias))
    session.delete(alias)
    session.commit()


@on_error_rollback
def group_users(user1: User, user2: User) -> Tuple[User, User]:
    logger.info("Adding link between {!r} and {!r}".format(user1, user2))
    # If both are in groups, merge the groups
    if user1.group_id is not None and user2.group_id is not None:
        logger.debug("Merging group {1.group_id:d} into group {0.group_id:d}"
            .format(user1, user2))
        for user in query_user_group(user2):
            user.group_id = user1.group_id

    # if one is in a group, assign the ungrouped user to the grouped user
    elif user1.group_id is not None:
        logger.debug("Assigning user {1.user_id:d} to group {0.group_id:d}"
            .format(user1, user2))
        user2.group_id = user1.group_id

    elif user2.group_id is not None:
        logger.debug("Assigning user {0.user_id:d} to group {1.group_id:d}"
            .format(user1, user2))
        user1.group_id = user2.group_id

    # If neither are in a group, assign a new group
    else:
        logger.debug("Assigning users {0.user_id:d}, {1.user_id:d} to group {0.user_id:d}"
            .format(user1, user2))
        user1.group_id = user2.group_id = user1.user_id

    session.commit()
    return user1, user2


@on_error_rollback
def ungroup_user(user: User) -> User:
    logger.info("Updating user {!r} - remove from group".format(user))
    user.group_id = None
    session.commit()
    return user


@on_error_rollback
def insert_note(*, user: User, author: User, type_: RecordType,
                timestamp: datetime, expires: datetime, body: str) -> Record:
    logger.info("Inserting note...")
    logger.debug("note: user={!r} author={!r} type={.name} timestamp={} expires={} body={!r}"
        .format(
                user, author, type_,
                get_timestamp_str(timestamp),
                get_timestamp_str(expires) if expires else None,
                body)
    )
    rec = Record(user=user, author=author, type=type_,
                 timestamp=timestamp, expires=expires, body=body)
    session.add(rec)
    session.commit()
    return rec
