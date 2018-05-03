from kaztron.driver import database as db
from kaztron.utils.discord import user_mention, role_mention

Base = db.declarative_base()


class User(Base):
    __tablename__ = 'users'
    MAX_FIELD = 1000
    MAX_TITLE = 256

    user_id = db.Column(db.Integer, db.Sequence('user_id_seq'), primary_key=True, nullable=False)
    discord_id = db.Column(db.String(24), unique=True, nullable=False, index=True)
    active_project_id = db.Column(db.Integer, db.ForeignKey('projects.project_id'), nullable=True)
    active_project = db.relationship('Project', foreign_keys=[active_project_id],
        uselist=False, post_update=True)
    projects = db.relationship('Project', foreign_keys='Project.user_id',
        order_by='Project.project_id', back_populates='user')
    max_projects = db.Column(db.Integer, nullable=False, default=1)

    about = db.Column(db.String(MAX_FIELD), nullable=True)
    type_id = db.Column(db.Integer, db.ForeignKey('type.id'), nullable=True, index=True)
    type = db.relationship('ProjectType', lazy='joined')
    genre_id = db.Column(db.Integer, db.ForeignKey('genre.id'), nullable=True, index=True)
    genre = db.relationship('Genre', lazy='joined')

    url_title = db.Column(db.String(MAX_TITLE), nullable=True)
    url = db.Column(db.String(MAX_TITLE), nullable=True)

    def __repr__(self):
        return 'User<{:d}, discord_id={}>'.format(self.user_id, self.discord_id)

    def __str__(self):
        return repr(self)

    @property
    def mention(self):
        return user_mention(self.discord_id)


class Project(Base):
    __tablename__ = 'projects'
    MAX_TITLE = 256
    MAX_SHORT = 32
    MAX_FIELD = 1000

    MAX_PITCH_WORDS = 70

    project_id = db.Column(db.Integer, db.Sequence('project_id_seq'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    user = db.relationship('User', lazy='joined', foreign_keys='Project.user_id',
        back_populates='projects')
    whois_message_id = db.Column(db.String(24), unique=True, nullable=True, index=True)

    title = db.Column(db.String(MAX_TITLE, collation='NOCASE'), nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('type.id'), nullable=False, index=True)
    type = db.relationship('ProjectType', lazy='joined')
    genre_id = db.Column(db.Integer, db.ForeignKey('genre.id'), nullable=False, index=True)
    genre = db.relationship('Genre', lazy='joined')
    subgenre = db.Column(db.String(MAX_SHORT), nullable=True)

    url_title = db.Column(db.String(MAX_TITLE), nullable=True)
    url = db.Column(db.String(MAX_TITLE), nullable=True)
    follow_role = db.Column(db.String(MAX_SHORT), unique=True, nullable=True, index=True)

    pitch = db.Column(db.String(MAX_FIELD), nullable=False)
    description = db.Column(db.String(MAX_FIELD), nullable=True)

    def __repr__(self):
        return 'Project<{:d}, user_id={:d}, title={!r}>'\
            .format(self.project_id, self.user_id, self.whois_message_id, self.title)

    def __str__(self):
        raise NotImplementedError()


class Genre(Base):
    __tablename__ = 'genre'
    MAX_NAME = 32

    id = db.Column(db.Integer, db.Sequence('genre_id_seq'), primary_key=True)
    name = db.Column(db.String(MAX_NAME, collation='NOCASE'), unique=True, nullable=False,
        index=True)
    role_id = db.Column(db.String(24), nullable=True, index=True)
    projects = db.relationship('Project', back_populates='genre')

    def __repr__(self):
        return 'Genre<{:d}, {}, {}>'.format(self.id, self.name, self.role_id)

    def __str__(self):
        return self.name

    def discord_str(self):
        return "{} ({})"\
            .format(self.name, role_mention(self.role_id) if self.role_id else 'No role')


class ProjectType(Base):
    __tablename__ = 'type'
    MAX_NAME = 32

    id = db.Column(db.Integer, db.Sequence('type_id_seq'), primary_key=True)
    name = db.Column(db.String(MAX_NAME, collation='NOCASE'), unique=True, nullable=False,
        index=True)
    role_id = db.Column(db.String(24), nullable=True, index=True)
    projects = db.relationship('Project', back_populates='type')

    def __repr__(self):
        return 'ProjectType<{:d}, {}, {}>'.format(self.id, self.name, self.role_id)

    def __str__(self):
        return self.name

    def discord_str(self):
        return "{} ({})" \
            .format(self.name, role_mention(self.role_id) if self.role_id else 'No role')
