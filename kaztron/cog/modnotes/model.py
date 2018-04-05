import enum

from kaztron.driver import database as db
from kaztron.utils.discord import Limits

Base = db.declarative_base()


class User(Base):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, db.Sequence('user_id_seq'), primary_key=True, nullable=False)
    discord_id = db.Column(db.String(24), unique=True, nullable=False)
    name = db.Column(db.String(Limits.NAME, collation='NOCASE'))
    aliases = db.relationship('UserAlias', back_populates='user', lazy='joined')
    group_id = db.Column(db.Integer, nullable=True)
    records = db.relationship('Record', foreign_keys='Record.user_id',
        back_populates='user')
    authorship = db.relationship('Record', foreign_keys='Record.author_id',
        back_populates='author')

    def __repr__(self):
        # noinspection PyTypeChecker
        return ("<User(user_id={:d}, discord_id={!r}, name={!r}, aliases=[{}], "
               "group_id={!s})>") \
            .format(self.user_id, self.discord_id, self.name,
                    ', '.join([repr(a) for a in self.aliases]),
                    self.group_id)

    def __str__(self):
        return "{1} (*{0:d})".format(self.user_id, self.name)


class UserAlias(Base):
    __tablename__ = 'aliases'
    __table_args__ = (
        db.UniqueConstraint('alias_id', 'name', 'user_id'),
    )

    alias_id = db.Column(db.Integer, db.Sequence('alias_id_seq'), primary_key=True, nullable=False)
    name = db.Column(db.String(Limits.NAME, collation='NOCASE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False, index=True)
    user = db.relationship('User')

    def __repr__(self):
        return "<Alias(alias_id={:d}, user_id={:d}, name={!r})>" \
            .format(self.alias_id, self.user_id, self.name)

    def __str__(self):
        return "{1} (alias *{0:d})".format(self.user_id, self.name)


class RecordType(enum.Enum):
    note = 0
    good = 1
    watch = 2
    int = 3
    warn = 4
    temp = 5
    perma = 6
    appeal = 7


class Record(Base):
    __tablename__ = 'records'

    record_id = db.Column(db.Integer, db.Sequence('record_id_seq'), primary_key=True)
    timestamp = db.Column(db.TIMESTAMP, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    user = db.relationship('User', lazy='joined', foreign_keys=[user_id])
    author_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    author = db.relationship('User', lazy='joined', foreign_keys=[author_id])
    type = db.Column(db.Enum(RecordType), nullable=False)
    expires = db.Column(db.DateTime, nullable=True)
    body = db.Column(db.String(2048), nullable=False)
    is_removed = db.Column(db.Boolean, nullable=False, default=False, server_default="FALSE")

    def __repr__(self):
        return "<Record(record_id={:d}, is_removed={!s})>" \
            .format(self.record_id, self.is_removed)

    def __str__(self):
        raise NotImplementedError()  # TODO
