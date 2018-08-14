import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Union, Sequence, Mapping, \
    MutableMapping, Iterable

import discord
from discord.ext import commands
from sqlalchemy import orm

from kaztron.config import KaztronConfig, SectionView
# noinspection PyUnresolvedReferences
from kaztron.driver import database as db
from kaztron.cog.blots.model import *
from kaztron.driver.database import make_error_handler_decorator
from kaztron.utils.datetime import get_weekday, parse as dt_parse

logger = logging.getLogger(__name__)

db_file = 'blots.sqlite'

engine = None
Session = db.sessionmaker()
session = None


def init_db():
    global engine, session
    engine = db.make_sqlite_engine(db_file)
    Session.configure(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)


on_error_rollback = make_error_handler_decorator(lambda *args, **kwargs: args[0].session, logger)


class BlotsConfig(SectionView):
    check_in_channel: str
    check_in_period_weekdays: List[int]
    check_in_period_time: str
    check_in_window_exempt_roles: List[str]
    milestone_map: Dict[str, Dict[str, int]]


class MilestoneInfo:
    MULTIPLE_ROLES = discord.Object(id=0)

    def __init__(self,
                 user: discord.Member,
                 check_in: CheckIn,
                 current_role: Optional[Sequence[discord.Role]],
                 target_role: discord.Role):
        self.user = user
        self.check_in = check_in
        self.current_roles = list(current_role) if current_role is not None else None
        self.target_role = target_role

    @property
    def milestone_changed(self):
        return len(self.current_roles) != 1 or self.current_roles[0] != self.target_role


class BlotsController:
    def __init__(self, server: discord.Server, config: BlotsConfig):
        self.server = server
        self.config = config
        self.session = session

        if self.session is None:
            raise RuntimeError("no database session: init_db() not yet called?")

    @on_error_rollback
    def get_user(self, member: discord.Member):
        """
        Get the database user for a given member.
        :param member:
        :return:
        :raise db.orm_exc.MultipleResultsFound: database is buggered
        """
        try:
            return self.session.query(User).filter(User.discord_id == member.id).one()
        except db.orm_exc.NoResultFound:
            user = User(discord_id=member.id)
            self.session.add(user)
            self.session.commit()
            return user


class CheckInController(BlotsController):
    """
    :param server: Discord server that the bot/BLOTS module is to manage.
    :param config: System-wide KazTron config (not the state.json)
    :param milestone_map: Role mappings for each project type. The role mappings map the
        {MINIMUM wordcount value: corresponding role}.
    """
    def __init__(self, server: discord.Server, config: BlotsConfig,
                 milestone_map: Dict[ProjectType, Dict[discord.Role, int]]):
        super().__init__(server, config)
        self.checkin_weekdays = self.config.check_in_period_weekdays
        self.checkin_time = dt_parse(self.config.check_in_period_time).time()

        self.milestone_map = {}  # type: Dict[ProjectType, Dict[discord.Role, int]]

        for p, inner_map in milestone_map.items():
            # sorted by minimum wordcount value (descending)
            # noinspection PyTypeChecker
            self.milestone_map[p] = OrderedDict(
                sorted(inner_map.items(), key=lambda i: i[1], reverse=True))
            logger.info("Milestone map for {}: {{{}}}".format(
                p.name,
                ', '.join(['{0.name}: {1:d}'
                           .format(r, v) for r, v in self.milestone_map[p].items()])
            ))

    def get_exempt_users(self):
        return self.session.query(User).filter_by(is_exempt=True).all()

    def get_check_in_week(self, included_date: datetime=None) -> Tuple[datetime, datetime]:
        """
        Get the start and end times for a check-in week that includes the passed date.
        """
        if not included_date:
            included_date = datetime.utcnow()

        end_date = get_weekday(included_date, self.checkin_weekdays[1], future=True).date()
        start_date = end_date - timedelta(days=7)

        end_dt = datetime.combine(end_date, self.checkin_time)
        start_dt = datetime.combine(start_date, self.checkin_time)

        if included_date > end_dt:  # for the day-of, check if the time has already passed
            end_dt += timedelta(days=7)
            start_dt += timedelta(days=7)

        return start_dt, end_dt

    def get_check_in_window(self, included_date: datetime=None) -> Tuple[datetime, datetime]:
        """
        Get the start and end times for the current or future check-in window relative to the
        passed date.
        """
        if not included_date:
            included_date = datetime.utcnow()

        end_date = get_weekday(included_date, self.checkin_weekdays[1], future=True).date()
        start_date = get_weekday(included_date, self.checkin_weekdays[0], future=True).date()

        if start_date > end_date:
            start_date -= timedelta(days=7)

        end_dt = datetime.combine(end_date, self.checkin_time)
        start_dt = datetime.combine(start_date, self.checkin_time)

        if included_date > end_dt:  # for the day-of, check if the time has already passed
            end_dt += timedelta(days=7)
            start_dt += timedelta(days=7)

        return start_dt, end_dt

    def query_check_ins(self, *,
                        member: discord.Member=None,
                        included_date: datetime=None) -> List[CheckIn]:
        """
        Query all check-ins.

        :param member: If given, filter by this user.
        :param included_date: If given, query only for the check-in week that includes this date.
        :return: List of check-ins in chronological order.
        :raise db.NoResultFound: no results found
        """
        log_conds = []
        query = self.session.query(CheckIn)
        if member:
            query = query.join(User).filter(User.discord_id == member.id)
            log_conds.append("member {}".format(member))

        if included_date:
            start, end = self.get_check_in_week(included_date)
            query = query.filter(db.and_(start <= CheckIn.timestamp, CheckIn.timestamp <= end))
            log_conds.append("period {} to {}".format(start.isoformat(' '), end.isoformat(' ')))

        results = query.order_by(CheckIn.timestamp).all()

        try:
            results[0]
        except IndexError:
            raise db.NoResultFound

        logger.info("query_check_ins: Found {:d} records for {}"
            .format(len(results), ' and '.join(log_conds)))
        return results

    def query_latest_check_ins(self, members: List[discord.Member]=None)\
            -> Dict[discord.Member, CheckIn]:
        """
        :param members: List of members to query for. Default: all members.
        :return:
        """
        query = self.session \
            .query(CheckIn, db.func.max(CheckIn.timestamp).label('timestamp_max'))
        if members:
            query = query.filter(User.discord_id.in_(tuple(m.id for m in members)))
        results = query.group_by(CheckIn.user_id).all()
        logger.info("query_latest_check_ins: Found {:d} records".format(len(results)))
        return {self.server.get_member(check_in.user.discord_id): check_in
                for check_in, _ in results}

    def get_check_in_report(self, included_date: datetime=None) \
            -> Dict[discord.Member, Optional[CheckIn]]:
        """
        Get a report of all server users and their check-ins in a given report week.

        Note that this function checks all CURRENT users. The report does not account for users who
        had not joined during the requested report week, or who left after that week.

        :param included_date: The check-in week to report for must include this date.
        :return: Map of users to their last checkin in the checkin period. If the user did not
            check in during the checkin period, the mapped value is None. This map is guaranteed
            to contain keys for all users currently on the server.
        """
        logger.info("get_check_in_report: Generating report (included_date={})"
            .format(included_date.isoformat(' ')))

        check_ins = self.query_check_ins(included_date=included_date)

        member_check_in_map = {m: None for m in self.server.members}
        for c in check_ins:
            member_check_in_map[self.server.get_member(c.user.discord_id)] = c

        # Delete users who are no longer on the server - will all be filed under the None key
        try:
            del member_check_in_map[None]
        except KeyError:
            pass

        # Remove exempt users
        for user in self.session.query(User).filter_by(is_exempt=True).all():
            try:
                del member_check_in_map[self.server.get_member(user.discord_id)]
            except KeyError:
                pass
        return member_check_in_map

    def get_milestone_report(self) -> Mapping[Union[discord.Role, None], Sequence[MilestoneInfo]]:
        """
        Get a report of all users who have checked in and what their milestone role should be.

        :return: Ordered map of TARGET role to full milestone information. This map will
        always include a None key for any users who have not submitted valid check-ins.
        """
        logger.info("get_milestone_report: Generating report")

        # set up output structure with the full list of milestone roles
        milestones = OrderedDict() \
            # type: MutableMapping[Union[discord.Role, None], List[MilestoneInfo]]
        for role in self.get_milestone_roles():
            milestones[role] = []
        milestones[None] = []
        logger.debug("get_milestone_report: Detected milestone roles: {!r}"
            .format([r.name for r in milestones.keys() if r is not None]))

        check_in_map = self.query_latest_check_ins()
        for member in self.server.members:
            check_in = check_in_map.get(member, None)
            user = check_in.user if check_in else self.get_user(member)
            if user.is_exempt:
                continue
            project_type = check_in.project_type if check_in else user.project_type
            ms_info = MilestoneInfo(
                user=member,
                check_in=check_in,
                current_role=self.get_milestone_role(member, project_type),
                target_role=self.find_target_milestone(check_in) if check_in else None
            )
            milestones[ms_info.target_role].append(ms_info)
        return milestones

    def get_milestone_role(self, member: discord.Member, p_type: ProjectType)\
            -> List[discord.Role]:
        """ Return member's Milestone roles. """
        role_intersect = set(self.milestone_map[p_type].keys()) & set(member.roles)
        return list(role_intersect)

    def get_milestone_roles(self) -> List[discord.Role]:
        """ Get a set of all milestone roles. """
        ms_roles = []
        for p_type in ProjectType:
            for role in self.milestone_map[p_type].keys():
                if role not in ms_roles:
                    ms_roles.append(role)
        return ms_roles

    def find_target_milestone(self, check_in: CheckIn) -> discord.Role:
        """
        Get the milestone the user should be at for a given check-in.
        :raise KeyError: can't find matching milestone role for check-in's wordcount value
        """
        ms_map = self.milestone_map[check_in.project_type]
        for role, v in ms_map.items():
            if check_in.word_count >= v:
                return role
        raise KeyError("No milestone role for check_in: {!r} user: {!r}"
            .format(check_in, check_in.user))

    @on_error_rollback
    def save_check_in(self, *,
            member: discord.Member,
            word_count: int,
            message: str,
            timestamp: datetime=None) -> CheckIn:
        """ Store a new check-in. """
        if timestamp is None:
            timestamp = datetime.utcnow()

        if len(message) > CheckIn.MAX_MESSAGE_LEN:
            raise commands.BadArgument(
                "Message too long (max {:d} chars)".format(CheckIn.MAX_MESSAGE_LEN))

        logger.info("Inserting check-in by {}...".format(member.nick or member.name))
        user = self.get_user(member)
        check_in = CheckIn(timestamp=timestamp, user_id=user.user_id, word_count=word_count,
            project_type=user.project_type, message=message[:CheckIn.MAX_MESSAGE_LEN])
        self.session.add(check_in)
        logger.debug("save_checkin: {!r}".format(check_in))
        self.session.commit()
        return check_in

    @on_error_rollback
    def set_user_type(self, member: discord.Member, p_type: ProjectType):
        logger.info("Setting user's project type to {}".format(p_type.name))
        self.get_user(member).project_type = p_type
        self.session.commit()

    @on_error_rollback
    def set_user_exempt(self, member: discord.Member, is_exempt=False):
        logger.info("Setting user {} {} from checkin"
            .format(member.name, "exempt" if is_exempt else "not exempt"))
        self.get_user(member).is_exempt = is_exempt
        self.session.commit()


class BlotsBadgeController(BlotsController):
    """
    :param server: Discord server that the bot/BLOTS module is to manage.
    :param config: System-wide KazTron config (not the state.json)
    """

    def __init__(self, server: discord.Server, config: KaztronConfig):
        super().__init__(server, config)

    def query_badges(self, *, member: discord.Member):
        """ Query a user's badges. """
        results = self.session.query(Badge).join(User, User.user_id == Badge.user_id) \
            .filter(User.discord_id == member.id) \
            .order_by(Badge.timestamp).all()

        try:
            results[0]
        except IndexError:
            raise db.NoResultFound

        logger.info("query_badges: Found {:d} records for member {}".format(len(results), member))
        return results

    def query_badge_from_message(self, message: discord.Message) -> Optional[Badge]:
        """
        Check if a badge already exists from a given Discord message.
        """
        return self.session.query(Badge).filter_by(message_id=message.id).one_or_none()

    def query_badge_report(self, min_badges: int) -> Iterable[Tuple[User, int]]:
        """ Get a summary of number of badges per user (in descending order). """
        total = db.func.count(Badge.id).label('total')
        return self.session.query(User, total).having(total >= min_badges)\
            .filter(User.user_id == Badge.user_id)\
            .group_by(Badge.user_id).order_by(db.desc(total)).all()

    @on_error_rollback
    def save_badge(self, *,
                   message_id: str,
                   member: discord.Member,
                   from_member: discord.Member,
                   badge: BadgeType,
                   reason: str,
                   timestamp: datetime):
        if len(reason) > Badge.MAX_MESSAGE_LEN:
            raise commands.BadArgument(
                "Reason too long (max {:d} chars)".format(CheckIn.MAX_MESSAGE_LEN))

        # noinspection PyTypeChecker
        badge_row = self.query_badge_from_message(discord.Object(id=message_id))
        user = self.get_user(member)
        from_user = self.get_user(from_member)

        if not badge_row:
            logger.info("save_badge: Inserting badge...")
            badge_row = Badge(
                message_id=message_id, timestamp=timestamp,
                user_id=user.user_id, from_id=from_user.user_id,
                badge=badge, reason=reason[:CheckIn.MAX_MESSAGE_LEN]
            )
            logger.debug("save_badge: {!r}".format(badge_row))
            self.session.add(badge_row)
        else:
            logger.info("save_badge: Updating existing badge...")
            logger.debug("replace_badge: before={!r}".format(badge_row))
            badge_row.user = user
            badge_row.badge = badge
            badge_row.reason = reason
            logger.debug("replace_badge: after={!r}".format(badge_row))
        self.session.commit()
        return badge_row

    @on_error_rollback
    def delete_badge(self, message_id: str):
        # noinspection PyTypeChecker
        badge_row = self.query_badge_from_message(discord.Object(id=message_id))
        if badge_row:
            logger.info("delete_badge: Deleting row: {!r}".format(badge_row))
            self.session.delete(badge_row)
            self.session.commit()
        else:
            logger.warning("delete_badge: no badge found for message_id {}".format(message_id))
        return badge_row
