import logging
from typing import List, Union, Tuple

import discord

from kaztron.cog.projects.wizard import ProjectWizard, AuthorWizard
# noinspection PyUnresolvedReferences
from kaztron.driver import database as db
from .model import *
from kaztron.driver.database import format_like, make_transaction_manager

logger = logging.getLogger(__name__)

db_file = 'projects.sqlite'

engine = None
Session = db.sessionmaker()
session = None


class RowReferencedError(RuntimeError):
    pass


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


def query_users(*, genre: Genre=None, type_: ProjectType=None) -> List[User]:
    q = session.query(User)
    if genre:
        q = q.filter_by(genre=genre)
    if type_:
        q = q.filter_by(type=type_)
    return q.all()


def update_user_from_projects(user: User):
    """
    Sync user's genre/type to their project, if they have only one. Otherwise, do nothing.
    """
    if len(user.projects) == 1:
        user.genre = user.projects[0].genre
        user.type = user.projects[0].type


def update_user(wizard: AuthorWizard) -> User:
    user = get_or_make_user(discord.Object(wizard.user_id))
    for k, v in wizard.items():
        if v is not None:
            setattr(user, k, v)
    return user


def get_genre(name: str) -> Genre:
    try:
        return session.query(Genre).filter_by(name=name).one()
    except db.NoResultFound:
        raise KeyError("Unknown genre: " + name)


def query_genres() -> List[Genre]:
        return session.query(Genre).order_by(Genre.name).all()


def safe_delete_genre(name: str, replace_name: str=None) -> Tuple[List[User], List[Project]]:
    """
    Safely delete a genre. Any projects or users referencing the genre will be updated with the
    replace_name genre, if specified, else a :cls:`~.RowReferencedError` is raised.

    :return: List of objects updated by this action.
    """
    # Replace the deleted genre in projects/users
    genre = get_genre(name)
    replace_genre = get_genre(replace_name) if replace_name else None

    users = query_users(genre=genre)
    projects = query_projects(genre=genre)

    if (users or projects) and not replace_genre:
        raise RowReferencedError(repr(genre))

    logger.info("Replacing genre {!r} with genre {!r}".format(genre, replace_genre))
    logger.debug("...for users: {}".format(', '.join(repr(u) for u in users)))
    logger.debug("...for projects: {}".format(', '.join(repr(p) for p in projects)))
    for u in users:
        u.genre = replace_genre
    for p in projects:
        p.genre = replace_genre

    # finally, delete the genre
    logger.info("Deleting genre {!r}".format(genre))
    session.delete(genre)
    return users, projects


def get_project_type(name: str) -> ProjectType:
    try:
        return session.query(ProjectType).filter_by(name=name).one()
    except db.NoResultFound:
        raise KeyError("Unknown project type: " + name)


def query_project_types() -> List[ProjectType]:
    return session.query(ProjectType).order_by(ProjectType.name).all()


def safe_delete_project_type(name: str, replace_name: str=None) -> Tuple[List[User], List[Project]]:
    """
    Safely delete a project type. Any projects or users referencing the type will be updated with
    the replace_name type, if specified, else a :cls:`~.RowReferencedError` is raised.

    :return: List of objects updated by this action.
    """
    p_type = get_project_type(name)
    replace_type = get_project_type(replace_name) if replace_name else None

    users = query_users(type_=p_type)
    projects = query_projects(type_=p_type)

    if (users or projects) and not replace_type:
        raise RowReferencedError(repr(p_type))

    logger.info("Replacing project type {!r} with {!r}".format(p_type, replace_type))
    logger.debug("...for users: {}".format(', '.join(repr(u) for u in users)))
    logger.debug("...for projects: {}".format(', '.join(repr(p) for p in projects)))
    for u in users:
        u.type = replace_type
    for p in projects:
        p.type = replace_type

    # finally, delete the type
    logger.info("Deleting project type {!r}".format(p_type))
    session.delete(p_type)
    return users, projects


# noinspection PyUnresolvedReferences
def query_projects(*,
                   user: User=None,
                   genre: Genre=None,
                   type_: ProjectType=None,
                   title: str=None,
                   body: str=None)\
        -> List[Project]:
    q = session.query(Project)
    if user:
        q = q.filter_by(user_id=user.user_id)
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


def query_unsent_projects():
    return session.query(Project).filter_by(whois_message_id=None).all()


# noinspection PyTypeChecker
def add_project(wizard: ProjectWizard) -> Project:
    member = discord.Object(wizard.user_id)
    user = get_or_make_user(member)
    p = Project(**wizard)
    user.projects.append(p)
    return p


def update_project(wizard: ProjectWizard) -> Project:
    """ Update user's current active project with the passed data. """
    user = get_or_make_user(discord.Object(wizard.user_id))
    if not user.active_project:
        raise discord.ClientException(
            "Can't edit: you don't have an active (selected) project.")
    for k, v in wizard.items():
        if v is not None:
            setattr(user.active_project, k, v)
    return user.active_project


def delete_project(project: Project):
    if project.user.active_project_id == project.project_id:
        project.user.active_project = None
    session.delete(project)

