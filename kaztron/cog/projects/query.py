import logging
from datetime import datetime
from typing import List, Union

import discord

from kaztron.cog.projects.wizard import ProjectWizard
# noinspection PyUnresolvedReferences
from kaztron.driver import database as db
from .model import *
from kaztron.driver.database import make_error_handler_decorator, format_like, \
    make_transaction_manager
from kaztron.utils.discord import extract_user_id
from kaztron.utils.datetime import format_timestamp

logger = logging.getLogger(__name__)

db_file = 'projects.sqlite'

engine = None
Session = db.sessionmaker()
session = None


def init_db():
    global engine, session
    engine = db.make_sqlite_engine(db_file)
    Session.configure(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)


transaction = make_transaction_manager(lambda *_, **__: session, logger)


def get_or_make_user(member: Union[discord.Member, discord.Object]):
    """
    Get the database user for a given member.
    :param member:
    :return:
    :raise db.orm_exc.MultipleResultsFound: database is buggered
    """
    try:
        return session.query(User).filter_by(discord_id=member.id).one()
    except db.orm_exc.NoResultFound:
        user = User(discord_id=member.id)
        session.add(user)
        return user


def query_users(*, genre: Genre=None, type_: ProjectType=None) \
        -> List[User]:
    q = session.query(User)
    if genre:
        q = q.filter_by(genre=genre)
    if type_:
        q = q.filter_by(type=type_)
    return q.all()


def get_genre(name: str) -> Genre:
    try:
        return session.query(Genre).filter_by(name=name).one()
    except db.NoResultFound:
        raise KeyError("Unknown genre: " + name)


def query_genres() -> List[Genre]:
        return session.query(Genre).order_by(Genre.name).all()


def get_project_type(name: str) -> ProjectType:
    try:
        return session.query(ProjectType).filter_by(name=name).one()
    except db.NoResultFound:
        raise KeyError("Unknown project type: " + name)


def query_project_types() -> List[ProjectType]:
    return session.query(ProjectType).order_by(ProjectType.name).all()


# noinspection PyUnresolvedReferences
def query_projects(*,
                   user: discord.Member=None,
                   genre: Genre=None,
                   type_: ProjectType=None,
                   title: str=None,
                   body: str=None)\
        -> List[Project]:
    q = session.query(Project)
    if user:
        q = q.filter_by(user_id=user.id)
    if genre:
        q = q.filter_by(genre=genre)
    if type_:
        q = q.filter_by(type=type_)
    if title:
        title_like = format_like(title)
        q = q.filter(Project.title.ilike(title_like))
    if body:
        body_like = format_like(body)
        q = q.filter(db.or_(
            Project.pitch.ilike(body_like),
            Project.description.ilike(body_like),
            Project.title.ilike(body_like)
        ))
    return q.all()


# noinspection PyTypeChecker
def add_project(wizard: ProjectWizard) -> Project:
    member = discord.Object(wizard.user_id)
    user = get_or_make_user(member)
    p = Project(**wizard)
    user.projects.append(p)
    return p


def update_project(wizard: ProjectWizard) -> Project:
    user = get_or_make_user(discord.Object(wizard.user_id))
    if user.active_project is None:
        raise discord.ClientException(
            "Can't edit: you don't have an active (selected) project.")
    for k, v in wizard.items():
        if v is not None:
            setattr(user.active_project, k, v)
    return user.active_project


def update_user_from_projects(user: User):
    """ If the user has only one project, sync their genre/type to that project. """
    if len(user.projects) == 1:
        user.genre = user.projects[0].genre
        user.type = user.projects[0].type

