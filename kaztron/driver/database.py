# noinspection PyUnresolvedReferences
import functools

from sqlalchemy import *
from sqlalchemy import event, orm
# noinspection PyUnresolvedReferences
from sqlalchemy.orm import relationship, sessionmaker, Query, aliased
# noinspection PyUnresolvedReferences
from sqlalchemy.orm import exc as orm_exc
# noinspection PyUnresolvedReferences
from sqlalchemy import exc as core_exc
# noinspection PyUnresolvedReferences
from sqlalchemy.ext.declarative import declarative_base  # DON'T REMOVE THIS - import into module
# noinspection PyProtectedMember
from sqlalchemy.engine import Engine

# noinspection PyUnresolvedReferences
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound


def make_sqlite_engine(filename):
    """
    Make an SQLAlchemy engine. Filename should be unique to the cog/module using it to avoid
    filename conflicts.
    """
    return create_engine('sqlite:///' + filename)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_error_handler_decorator(session_callback, logger):
    """

    :param session_callback: Signature session_callback(*args, **kwargs) -> Session. Should retrieve
    the session being used by the wrapped function. Args, kwargs are the args to the wrapped
    function (possibly useful to extract `self` if the wrapped function is a method).
    :param logger:
    :return:
    """
    # noinspection PyShadowingNames
    def on_error_rollback(func):
        """
        Decorator for database operations. Any raised exceptions will cause a rollback, and then be
        re-raised.
        """
        @functools.wraps(func)
        def db_safe_exec(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                logger.error('Error ({!s}) - rolling back'.format(e))
                session_callback(*args, **kwargs).rollback()
                raise
        return db_safe_exec
    return on_error_rollback


def make_transaction_manager(session_callback, logger):
    """
    :param session_callback: Signature session_callback(*args, **kwargs) -> Session. Should retrieve
    the session being used by the wrapped function. Args, kwargs are the args to the wrapped
    function (possibly useful to extract `self` if the wrapped function is a method).
    :param logger:
    :return: A context manager that wraps a single transaction.
    """
    from contextlib import contextmanager

    @contextmanager
    def transaction_scope():
        """Provide a transactional scope around a series of operations."""
        session = session_callback()  # type: orm.Session
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.error('Error ({!s}) - rolling back'.format(e))
            session.rollback()
            raise
        except:
            logger.error('Exit event - rolling back')
            session.rollback()
            raise

    return transaction_scope


def format_like(s: str, escape='\\') -> str:
    """ Format and escape a string for a LIKE or ILIKE substring search. """
    return '%{}%'.format(s.replace('%', escape+'%').replace('_', escape+'_'))
