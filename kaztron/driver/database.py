# noinspection PyUnresolvedReferences
import functools

from sqlalchemy import *
from sqlalchemy import event
# noinspection PyUnresolvedReferences
from sqlalchemy.orm import relationship, sessionmaker, Query
# noinspection PyUnresolvedReferences
from sqlalchemy.orm import exc as orm_exc
# noinspection PyUnresolvedReferences
from sqlalchemy import exc as core_exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine import Engine


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


def make_error_handler_decorator(session, logger):
    def on_error_rollback(func):
        """
        Decorator for database operations. Any raised exceptions will cause a rollback, and then be
        re-raised.
        """
        @functools.wraps(func)
        def db_safe_exec(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error('Error ({!s}) - rolling back'.format(e))
                session.rollback()
                raise
        return db_safe_exec
    return on_error_rollback
