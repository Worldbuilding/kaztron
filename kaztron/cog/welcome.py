import logging

import discord

from kaztron import KazCog
from kaztron.config import SectionView

logger = logging.getLogger(__name__)


class PendingKickData:

    def __init__(self,
                 *,
                 user_id: str,
                 timestamp: datetime,
                 kick_time: datetime
                 ):
        self.user_id = user_id
        self.timestamp = timestamp
        self.kick_time = kick_time
        self.retries = 0

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'timestamp': utctimestamp(self.timestamp),
            'kick_time': utctimestamp(self.kick_time),
        }

    def __repr__(self):
        return "<PendingKickData(user_id={}, timestamp={}, kick_time={})>" \
            .format(self.user_id, self.timestamp.isoformat(' '),
                    self.kick_time.isoformat(' '))

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            user_id=data['user_id'],
            timestamp=datetime.utcfromtimestamp(data['timestamp']),
            kick_time=datetime.utcfromtimestamp(data['kick_time'])
        )


class PendingKickState(SectionView):
    pending_kicks: List[PendingKickData]


class WelcomeConfig(SectionView):
    channel_welcome: str
    channel_rules: str
    public_join: bool
    public_quit: bool

    illegal_name_check: bool
    illegal_name_kick: bool
    illegal_name_notify: str
    illegal_name_kick: str
    illegal_name_kick_delay: int
    valid_name_pattern: str


class Welcome(KazCog):
    """!kazhelp
    category: Automation
    brief: Welcomes new users to the server and logs users joining/leaving.
    description: |
        The Welcome cog welcomes new users to the server in the {{welcome_channel}} channel. This
        serves as a replacement to Discord's terrible built-in welcome messages. It also announces
        users who leave the server.

        This cog also logs users joining and leaving the server to {{output_channel}}, for
        moderation purposes, such as detecting raids, impersonation and ban evasion.

        It has no usable commands.
    """
    cog_config: WelcomeConfig
    cog_state: PendingKickState

    RETRY_INTERVAL = 90

    def __init__(self, bot):
        super().__init__(bot, "welcome", WelcomeConfig, PendingKickState)
        self.cog_config.set_defaults(public_join=True, public_quit=False)
        self.channel_welcome: discord.Channel = \
            discord.Object(id=self.cog_config.channel_welcome)
        self.cog_state.set_defaults(pending_kicks=[])
        self.cog_state.set_converters('pending_kicks',
                                      lambda l: [PendingKickData.from_dict(pk) for pk in l],
                                      lambda l: [pk.to_dict() for pk in l]
                                      )
        self.pending_kicks = []  # type: List[PendingKickData]

    async def on_ready(self):
        await super().on_ready()
        self.channel_welcome = self.validate_channel(self.cog_config.channel_welcome)
        if not self.pending_kicks:
            self._load_pending_kicks()

    def export_kazhelp_vars(self):
        return {'welcome_channel': '#' + self.channel_welcome.name}

    async def on_member_join(self, member: discord.Member):
        """
        On member join, welcome the member and log their join to the output channel.
        """
        rules_channel = self.bot.get_channel(id=self.cog_config.channel_rules)
        server = member.server
        fmt = 'Welcome {0.mention} to {1.name}! Please read the server rules at {2}'
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has joined the server."

        await self.send_output(out_fmt.format(member))
        if self.cog_config.public_join:
            await self.bot.send_message(self.channel_welcome, fmt.format(member, server,
                                                                         rules_channel.mention if rules_channel else "#welcome-rules-etc"))
        logger.info("New user welcomed: %s \n" % str(member))

        if self.cog_config.illegal_name_check
            handle_invalid_characters_in_username(member)

    async def on_member_remove(self, member: discord.Member):
        """
        On member part, log the departure in the output channel and public channel.
        """
        server = member.server
        fmt = "{0.mention} has quit {1.name}! Fare thee well!"
        out_fmt = "{0.mention} (`{0!s}` - Nickname: `{0.nick}`) has left the server."
        await self.send_output(out_fmt.format(member))
        if self.cog_config.public_quit:
            await self.bot.send_message(self.channel_welcome, fmt.format(member, server))
        logger.info("User quit: %s \n" % str(member))

    async def on_name_change(self, user: discord.User):
        if self.cog_config.illegal_name_check
            handle_invalid_characters_in_username(user)

    async def on_nick_change(self, member: discord.Member):
        if self.cog_config.illegal_name_check
            handle_invalid_characters_in_username(member)

    async def handle_invalid_characters_in_username(user)
        if is_username_valid(user):
            clear_pending_kicks(user)
            return

        if self.cog_config.illegal_name_kick
            timestamp = datetime.utcnow()
            pk_time = timestamp + datetime.timedelta(minutes=self.cog_config.illegal_name_kick_delay)

            pending_kick = PendingKickData(
                user_id=user.id, timestamp=timestamp, kick_time=pk_time
            )
            self.add_pending_kick(pending_kick)

        self.bot.send_message(user, self.cog_config.illegal_name_notify)

        logMessage = "Notified user {} with name {} to change their name to something easy to ping".format(user.id,
                                                                                                           user.name)
        logger.info(logMessage)
        await self.send_output(logMessage)

    @pending_kick.error
    async def pending_kick_error(self, exc, ctx):
        core_cog = self.bot.get_cog("CoreCog")
        await core_cog.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @task(is_unique=False)
    async def task_kick_illegally_named_user(self, pending_kick: PendingKickData):
        logger.info("Kicking User for Illegal Name: {!r}".format(pending_kick))
        # because send_message assumes discord.Object is a channel, not user
        user = discord.utils.get(self.bot.get_all_members(), id=pending_kick.user_id)

        await self.bot.kick(user.name)

        await self.bot.send_message(
            user,
            self.cog_config.illegal_name_kick
        )  # if problem, will raise an exception...

        clear_pending_kicks(user)

    async def clear_pending_kicks(user)
        try:
            for instance in self.scheduler.get_instances(self.task_kick_illegally_named_user):
                pk = instance.args[0]
                if pk.user_id == user.id:
                    instance.cancel()
                    try:
                        self.pending_kicks.remove(pk)
                    except ValueError:
                        logger.warning("clear pending kicks: pending kick not in list of pending kicks - "
                                       "already removed? {!r}".format(pk))
        except asyncio.InvalidStateError:
            pass

        self._save_pending_kicks()

    @task_kick_illegally_named_user.error
    async def on_kick_illegally_named_user_error(self, e: Exception, t: TaskInstance):
        logger.error("Error trying to kick illegally named user: {}".format(exc_log_str(e)))

    @handle_invalid_characters_in_username.error
    async def on_handle_invalid_characters_in_username_error(self, e: Exception, user: discord.User):
        logger.error("Error trying to warn illegally named user: {}".format(exc_log_str(e)))
        if not isinstance(e, discord.HTTPException):
            logger.error("PendingKicks: non-HTTP error; giving up trying to warn: {!r}".format(user))
            await self.send_output(
                "Giving up on warning user about pending kick: {!r}. Non-HTTP error occurred".format(user))
        elif isinstance(e, discord.Forbidden) and e.code == DiscordErrorCodes.CANNOT_PM_USER:
            logger.error("PendingKick: can't send PM to user; trying public channel: {!r}".format(user))
            await self.send_public(
                "{} You seem to have PMs from this server disabled or you've blocked me. {}"
                    .format(user_mention(user.id), self.cog_config.illegal_name_notify)
            )
            await self.send_output(
                "Giving up PMing warning about pending kick: {!r}. User has PMs disabled. Trying public channel".format(
                    user))
        else:
            logger.error("User has a pending kick and will not be warned: {!r}".format(user))

    def is_username_valid(user):
        if user instanceof member:
            return re.match(self.cog_config.valid_name_pattern, user.nickname)
        else:
            return re.match(self.cog_config.valid_name_pattern, user.name)

    def add_pending_kick(self, pk: PendingKickData):
        self.pending_kicks.append(pk)
        self.scheduler.schedule_task_at(self.task_kick_illegally_named_user, pk.kick_time, args=(pk,),
                                        every=self.RETRY_INTERVAL)
        self._save_pending_kicks()
        logger.info("Kick pending: {!r}".format(pk))

    def _save_pending_kicks(self):
        if not self.is_ready:
            logger.debug("_save_pending_kicks: not ready, skipping")
            return
        logger.debug("_save_pending_kicks")
        self.cog_state.pending_kicks = self.pending_kicks
        self.state.write()

    def _load_pending_kicks(self):
        logger.info("Loading user pending kick for illegal name from persisted state...")
        try:
            self.scheduler.cancel_all(self.task_kick_illegally_named_user)
        except asyncio.InvalidStateError:
            pass
        self.pending_kicks.clear()
        for pk in self.cog_state.pending_kicks:
            self.add_pending_kick(pk)


def setup(bot):
    bot.add_cog(Welcome(bot))