from datetime import timedelta
import logging
from typing import List

import discord
from discord.ext import commands

from kaztron import KazCog, task
from kaztron.cog.modnotes.model import RecordType
from kaztron.cog.modnotes.modnotes import ModNotes
from kaztron.cog.modnotes import controller, model, ModNotesConfig
from kaztron.errors import BotCogError
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.datetime import format_timedelta
from kaztron.utils.discord import get_named_role
from kaztron.utils.strings import parse_keyword_args

logger = logging.getLogger(__name__)


class BanToolsConfig(ModNotesConfig):
    """
    :ivar ban_check_interval: Interval (in seconds) to re-check bans.
    :ivar ban_role: The name of a role used to tempban (usually mute, deny channel access, etc.)
        a user.
    :ivar ban_temp_expires: Default expiration time. Timespec, same as `.notes add`'s `expires`
        argument.
    :ivar ban_temp_enforce: If true, periodically enforce active tempbans.
    :ivar ban_perma_enforce: If true, periodically validate active permabans. If tempban_enforce is
        also true, then permabans will be enforced with the tempban_role. (This bot will not
        enforce a Discord server ban - it is designed so as to limit granting the bot higher-risk
        permissions).
    """
    ban_check_interval: timedelta
    ban_role: discord.Role
    ban_temp_expires: str
    ban_temp_enforce: bool
    ban_perma_enforce: bool


class BanTools(KazCog):
    """!kazhelp
    category: Moderator
    brief: Mod notes tools to help enforce and keep track of bans.
    description: |
        Various tools for moderators to help enforce and track bans! This cog depends on the
        {{%ModNotes}} module.

        This module can automatically enforce modnotes of type 'temp' and 'perma', at startup and
        every {{check_interval}} hence.

        TODO: trigger an enforce on adding a note
    contents:
        - ban
            - enforce
            - list
        - tempban
    """
    cog_config: BanToolsConfig

    #####
    # Lifecycle
    #####

    def __init__(self, bot):
        super().__init__(bot, 'modnotes', BanToolsConfig)
        self.cog_config.set_defaults(
            ban_check_interval=3600,
            ban_temp_expires='in 7 days',
            ban_temp_enforce=False,
            ban_perma_enforce=False
        )
        self.cog_config.set_converters('ban_check_interval', lambda s: timedelta(seconds=s), None)
        self.cog_config.set_converters('ban_role',
            lambda r: get_named_role(self.server, r), None)
        self.cog_config.set_converters('channel_mod', self.get_channel, None)
        self.cog_modnotes: ModNotes = None

    async def on_ready(self):
        await super().on_ready()
        self.cog_modnotes = self.get_cog_dependency(ModNotes.__name__)
        _ = self.cog_config.ban_role  # validate that it is set and exists
        _ = self.cog_config.channel_mod  # validate that it is set and exists

        # schedule tempban update tick (unless already done i.e. reconnects)
        if self.cog_config.ban_temp_enforce or self.cog_config.ban_perma_enforce:
            if self.cog_modnotes and not self.scheduler.get_instances(self.task_update_tempbans):
                self.scheduler.schedule_task_in(
                    self.task_update_tempbans, 0, every=self.cog_config.ban_check_interval
                )

    def export_kazhelp_vars(self):
        return {
            'mod_channel': '#' + self.cog_config.channel_mod.name,
            'check_interval': format_timedelta(self.cog_config.ban_check_interval),
            'temp_expires': self.cog_config.ban_temp_expires
        }

    def unload_kazcog(self):
        self.scheduler.cancel_all(self.task_update_tempbans)

    #####
    # Core
    #####

    @staticmethod
    def _get_tempbanned_members_db(server: discord.Server, include_perma=False) \
            -> List[model.Record]:
        if include_perma:
            types = (RecordType.temp, RecordType.perma)
        else:
            types = (RecordType.temp,)
        records = controller.query_unexpired_records(types=types)
        members_raw = (server.get_member(record.user.discord_id) for record in records)
        return [m for m in members_raw if m is not None]

    def _get_tempbanned_members_server(self, server: discord.Server) -> List[discord.Member]:
        return [m for m in server.members if self.cog_config.ban_role in m.roles]

    async def _update_tempbans(self):
        """
        Check and update all current tempbans in modnotes. Unexpired tempbans will be applied and
        expired tempbans will be removed, when needed.
        """
        if not self.cog_config.ban_temp_enforce:
            return

        logger.info("Checking all tempbans.")
        try:
            server = self.cog_config.channel_mod.server  # type: discord.Server
        except AttributeError:  # get_channel failed
            logger.error("Can't find mod channel")
            await self.send_output("**ERROR**: update_tempbans: can't find mod channel")
            return

        bans_db = self._get_tempbanned_members_db(server)
        bans_server = self._get_tempbanned_members_server(server)

        # check if any members who need to be banned
        for member in bans_db:
            if member not in bans_server:
                logger.info("Applying tempban role '{role}' to {user!s}...".format(
                    role=self.cog_config.ban_role.name,
                    user=member
                ))
                await self.bot.add_roles(member, self.cog_config.ban_role)
                await self.bot.send_message(self.cog_config.channel_mod,
                    "Tempbanned {.mention}".format(member))

        # check if any members who need to be unbanned
        for member in bans_server:
            if member not in bans_db:
                logger.info("Removing tempban role '{role}' to {user!s}...".format(
                    role=self.cog_config.ban_role.name,
                    user=member
                ))
                await self.bot.remove_roles(member, self.cog_config.ban_role)
                await self.bot.send_message(self.cog_config.channel_mod,
                    "Unbanned {.mention}".format(member))

    #####
    # Discord
    #####

    @ready_only
    async def on_member_join(self, _: discord.Member):
        await self._update_tempbans()

    @task(is_unique=True)
    async def task_update_tempbans(self):
        await self._update_tempbans()

    @commands.command(pass_context=True)
    @mod_only()
    @mod_channels()
    async def tempban(self, ctx: commands.Context, user: str, *, reason: str = ""):
        """!kazhelp

        description: |
            Tempban a user.

            This command will immediately tempban (mute) the user, and create a modnote. It will not
            communicate with the user.

            The user will be unbanned (unmuted) when the tempban expires.

            Note that the ModTools module automatically enforces all tempban modules. See the
            {{%ModTools}} introduction or `.help ModTools` for more info.

            This command is shorthand for `.notes add <user> temp expires="[expires]" [reason]`.
        parameters:
            - name: user
              type: string
              description: The user to ban. See {{!notes}} for more information.
            - name: reason
              type: string
              optional: true
              description: "Complex parameter of the format `[expires=[expires]] [reason]`. `reason`
                is the reason for the tempban, to be recorded as a modnote (optional but highly
                recommended)."
            - name: expires
              type: datespec
              optional: true
              description: "The datespec for the tempban's expiration. Use quotation marks if the
                datespec has spaces in it. See {{!notes add}} for more information on accepted
                syntaxes."
              default: '"{{temp_expires}}"'
        examples:
            - command: .tempban @BlitheringIdiot#1234 Was being a blithering idiot.
              description: Issues a ban of default duration ({{temp_expires}}).
            - command: .tempban @BlitheringIdiot#1234 expires="in 3 days" Was being a slight
                blithering idiot only.
              description: Issues a 3-day ban.
        """
        if not self.cog_modnotes:
            raise BotCogError("ModNotes cog not loaded. This command requires ModNotes to run.")

        # Parse and validate kwargs (we won't use this, just want to validate valid keywords)
        try:
            kwargs, rem = parse_keyword_args(self.cog_modnotes.KW_EXPIRE, reason)
        except ValueError as e:
            raise commands.BadArgument(e.args[0]) from e
        else:
            if not kwargs:
                reason = 'expires="{}" {}'.format(self.cog_config.ban_temp_expires, reason)
            if not rem:
                reason += " No reason specified."

        # Write the note
        await ctx.invoke(self.cog_modnotes.add, user, 'temp', note_contents=reason)

        # Apply new mutes
        await self._update_tempbans()


def setup(bot):
    bot.add_cog(BanTools(bot))
