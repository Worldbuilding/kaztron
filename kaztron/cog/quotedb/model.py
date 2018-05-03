from kaztron.driver import database as db
from kaztron.utils.discord import Limits, user_mention

Base = db.declarative_base()


class User(Base):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, db.Sequence('user_id_seq'), primary_key=True, nullable=False)
    discord_id = db.Column(db.String(24), unique=True, nullable=False)
    name = db.Column(db.String(Limits.NAME, collation='NOCASE'))
    username = db.Column(db.String(Limits.NAME, collation='NOCASE'))
    quotes = db.relationship('Quote', foreign_keys='Quote.author_id', back_populates='author')
    saved_quotes = db.relationship('Quote', foreign_keys='Quote.saved_by_id',
        back_populates='saved_by')

    # not used for now: disallow user from being quoted
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return "<User(user_id={:d}, discord_id={!r}, name={!r}, username={!r}>" \
            .format(self.user_id, self.discord_id, self.name, self.username)

    def __str__(self):
        return "{}".format(self.name)

    @property
    def mention(self):
        return user_mention(self.discord_id)


class Quote(Base):
    __tablename__ = 'quotes'

    MAX_MESSAGE_LEN = 1000

    quote_id = db.Column(db.Integer, db.Sequence('quote_id_seq'), primary_key=True)
    timestamp = db.Column(db.TIMESTAMP, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    author = db.relationship('User', lazy='joined', foreign_keys=[author_id])
    saved_by_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    saved_by = db.relationship('User', lazy='joined', foreign_keys=[saved_by_id])
    channel_id = db.Column(db.String(24), nullable=False)
    message = db.Column(db.String(MAX_MESSAGE_LEN), nullable=False)

    def __repr__(self):
        return "<Quote(quote_id={:d}, timestamp={}, author_id={}, channel_id={}, message={})>" \
            .format(self.quote_id, self.timestamp.isoformat(' '), self.author_id, self.channel_id,
                    self.message[:97] + '...' if len(self.message) > 100 else self.message)

    def __str__(self):
        raise NotImplementedError()
