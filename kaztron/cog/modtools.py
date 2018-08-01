import logging
import random
from typing import List

import discord
from discord.ext import commands

from kaztron import KazCog, task
from kaztron.cog.modnotes.model import RecordType
from kaztron.cog.modnotes.modnotes import ModNotes
from kaztron.cog.modnotes import controller as c, model
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.converter import MemberConverter2
from kaztron.utils.discord import get_named_role, Limits
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import parse_keyword_args, split_chunks_on

logger = logging.getLogger(__name__)


class ModToolsCog(KazCog):
    """!kazhelp

    brief: Miscellaneous tools for moderators.
    description: |
        Various tools for moderators to help them in their day-to-day! Some commands are
        dependent on the {{%ModNotes}} module.

        This module will automatically enforce modnotes of type "temp", at startup and every hour
        hence. Use {{!tempban}} in order to immediately apply and enforce a new tempban. (Using
        {{!notes add}} to add a "temp" record will not enforce it until the next hourly check.)
    contents:
        - up
        - down
        - tempban
        - whois
        - wb
    """
    def __init__(self, bot):
        super().__init__(bot)
        self.distinguish_map = self.config.get("modtools", "distinguish_map", {})
        self.wb_images = self.config.get("modtools", "wb_images", [])
        self.ch_mod = discord.Object(self.config.get("modtools", "channel_mod"))
        self.role_name = self.config.get("modtools", "tempban_role")
        self.cog_modnotes = None  # type: ModNotes

    async def on_ready(self):
        await super().on_ready()
        logger.debug("Getting modnotes cog")
        self.cog_modnotes = self.bot.get_cog("ModNotes")
        if self.cog_modnotes is None:
            logger.error("Can't find ModNotes cog. Tempban command will not work.")
            self.send_output(
                "**ERROR**: Can't find ModNotes cog. The `.tempban` command and automatic tempban "
                "management will not work."
            )
            raise RuntimeError("Can't find ModNotes cog")
        self.ch_mod = self.validate_channel(self.ch_mod.id)

        if not self.scheduler.get_instances(self.task_update_tempbans):
            self.scheduler.schedule_task_in(self.task_update_tempbans, 0, every=3600)

    def unload_kazcog(self):
        self.scheduler.cancel_all(self.task_update_tempbans)

    @ready_only
    async def on_member_joined(self, member: discord.Member):
        await self._update_tempbans()

    @commands.command(pass_context=True)
    @mod_only()
    async def up(self, ctx):
        """!kazhelp
        brief: "Colours a moderator's username."
        description: |
            This command colours the moderator's username by applying a special role to it. This
            allows moderators to clearly show when they are speaking in an official capacity as
            moderators.
        """
        for status_role_name, distinguish_role_name in self.distinguish_map.items():
            status_role = discord.utils.get(ctx.message.server.roles, name=status_role_name)
            if status_role and status_role in ctx.message.author.roles:
                distinguish_role = get_named_role(ctx.message.server, distinguish_role_name)
                await self.bot.add_roles(ctx.message.author, distinguish_role)
                await self.bot.delete_message(ctx.message)
                logger.info("up: Gave {} the {} role"
                    .format(ctx.message.author, distinguish_role_name))
                break
        else:
            err_msg = "up: user's roles not recognised: {}".format(message_log_str(ctx.message))
            logger.warning(err_msg)
            await self.bot.say("That command is only available to mods and admins.")
            await self.send_output("[WARNING] " + err_msg)

    @commands.command(pass_context=True)
    @mod_only()
    async def down(self, ctx):
        """!kazhelp
        description: |
            Uncolours a moderator's username.

            This command undoes the {{!up}} command.
        """
        for status_role_name, distinguish_role_name in self.distinguish_map.items():
            status_role = discord.utils.get(ctx.message.server.roles, name=status_role_name)
            if status_role and status_role in ctx.message.author.roles:
                distinguish_role = get_named_role(ctx.message.server, distinguish_role_name)
                await self.bot.remove_roles(ctx.message.author, distinguish_role)
                await self.bot.delete_message(ctx.message)
                logger.info("down: Took away from {} the {} role"
                    .format(ctx.message.author, distinguish_role_name))
                break
        else:
            err_msg = "down: user's roles not recognised: {}".format(message_log_str(ctx.message))
            logger.warning(err_msg)
            await self.bot.say("That command is only available to mods and admins.")
            await self.send_output("[WARNING] " + err_msg)

    @staticmethod
    def _get_tempbanned_members_db(server: discord.Server) -> List[model.Record]:
        records = c.query_unexpired_records(types=RecordType.temp)
        members_raw = (server.get_member(record.user.discord_id) for record in records)
        return [m for m in members_raw if m is not None]

    def _get_tempbanned_members_server(self, server: discord.Server) -> List[discord.Member]:
        tempban_role = get_named_role(server, self.role_name)
        return [m for m in server.members if tempban_role in m.roles]

    @task(is_unique=True)
    async def task_update_tempbans(self):
        await self._update_tempbans()

    async def _update_tempbans(self):
        """
        Check and update all current tempbans in modnotes. Unexpired tempbans will be applied and
        expired tempbans will be removed, when needed.
        """
        logger.info("Checking all tempbans.")
        try:
            server = self.bot.get_channel(self.ch_mod.id).server  # type: discord.Server
        except AttributeError:  # get_channel failed
            logger.error("Can't find mod channel")
            await self.send_output("**ERROR**: update_tempbans: can't find mod channel")
            return

        tempban_role = get_named_role(server, self.role_name)
        bans_db = self._get_tempbanned_members_db(server)
        bans_server = self._get_tempbanned_members_server(server)

        # check if any members who need to be banned
        for member in bans_db:
            if member not in bans_server:
                logger.info("Applying tempban role '{role}' to {user!s}...".format(
                    role=tempban_role.name,
                    user=member
                ))
                await self.bot.add_roles(member, tempban_role)
                await self.bot.send_message(self.ch_mod, "Tempbanned {.mention}".format(member))

        # check if any members who need to be unbanned
        for member in bans_server:
            if member not in bans_db:
                logger.info("Removing tempban role '{role}' to {user!s}...".format(
                    role=tempban_role.name,
                    user=member
                ))
                await self.bot.remove_roles(member, tempban_role)
                await self.bot.send_message(self.ch_mod, "Unbanned {.mention}".format(member))

    @commands.command(pass_context=True)
    @mod_only()
    @mod_channels()
    async def tempban(self, ctx: commands.Context, user: str, *, reason: str=""):
        """!kazhelp

        description: |
            Tempban a user.

            This method will automatically create a modnote. It will not communicate with the user.

            This module integrates with modnotes, and will automatically enforce "temp" notes,
            giving a role to users with unexpired "temp" notes and removing that role when the note
            expires. This command is shorthand for
            `.notes add <user> temp expires="[expires]" [reason]`.
        parameters:
            - name: user
              type: string
              description: The user to ban. See {{!notes}}  for more information.
            - name: reason
              type: string
              optional: true
              description: Complex parameter of the format `[expires=[expires]] [reason]`. `reason`
                is optional but recommended. The reason to record in the modnote.
            - name: expires
              type: datespec
              optional: true
              description: |
                The datespec for the tempban's expiration. Use quotation marks if the
                datespec has spaces in it. See {{!notes add}} for more information on accepted
                syntaxes.
              default: '"in 7 days"'
        examples:
            - command: .tempban @BlitheringIdiot#1234 Was being a blithering idiot.
              description: Issues a 7-day ban.
            - command: .tempban @BlitheringIdiot#1234 expires="in 3 days" Was being a slight
                blithering idiot only.
              description: Issues a 3-day ban.
        """
        if not self.cog_modnotes:
            raise RuntimeError("Can't find ModNotes cog")

        # Parse and validate kwargs (we won't use this, just want to validate valid keywords)
        try:
            kwargs, rem = parse_keyword_args(self.cog_modnotes.KW_EXPIRE, reason)
        except ValueError as e:
            raise commands.BadArgument(e.args[0]) from e
        else:
            if not kwargs:
                reason = 'expires="{}" {}'.format("in 7 days", reason)
            if not rem:
                reason += " No reason specified."

        # Write the note
        await ctx.invoke(self.cog_modnotes.add, user, 'temp', note_contents=reason)

        # Apply new mutes
        await self._update_tempbans()

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def whois(self, ctx, user: str):
        """!kazhelp

        brief: Find a Discord user.
        description: |
            Finds a Discord user from their ID, name, or name with discriminator.

            If an exact match isn't found, then this tool will do a substring search on all visible
            users' names and nicknames.

            WARNING: If the user is in the channel where you use this command, the user will receive
            a notification.
        parameters:
            - name: user
              type: string
              description: An ID number, name, name with discriminator, etc. of a user to find.
        examples:
            - command: .whois 123456789012345678
              description: Find a user with ID 123456789012345678.
            - command: .whois JaneDoe#0921
              description: Find a user exactly matching @JaneDoe#0921.
            - command: .whois JaneDoe
              description: Find a user whose name matches JaneDoe, or if not found, a user whose
                name or nickname contains JaneDoe.
        """
        await self._whois_match(ctx, user) or await self._whois_search(ctx, user)

    async def _whois_match(self, ctx, user: str):
        try:
            member = MemberConverter2(ctx, user).convert()
            msg = "Found user {0.mention} with ID {0.id}".format(member)
            logger.debug(msg)
            await self.bot.say(msg)
            return True
        except commands.BadArgument:
            return False

    async def _whois_search(self, ctx, user: str):
        logger.info("whois: searching for name match")
        members = [m for m in ctx.message.server.members
                   if (m.nick and user.lower() in m.nick.lower()) or user.lower() in m.name.lower()]
        if members:
            member_list_str = ', '.join(str(m) for m in members)
            logger.debug("Found {:d} users: {}".format(len(members), member_list_str))

            s = '**{:d} users found**\n'.format(len(members)) +\
                '\n'.join("{0.mention} ID {0.id}".format(m) for m in members)
            for part in split_chunks_on(s, maxlen=Limits.MESSAGE):
                await self.bot.say(part)
            return True
        else:
            await self.bot.say("No matching user found.")
            return False

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def wb(self, ctx, index: int=None):
        """!kazhelp

        description: |
            Show a "Please talk about worldbuilding" image.

            For mod intervention, when discussions get off-topic.
        parameters:
            - name: index
              type: string
              optional: true
              description: If specified, the index of the image to show (starting at `0`).
                If not specified, a random image is shown.
        examples:
            - command: .wb
              description: Show a random image.
            - command: .wb 3
              description: Show image at index 3 (the 4th image).
        """
        if index is None:
            index = random.randint(0, len(self.wb_images) - 1)
            logger.debug("wb: random image = {:d}".format(index))

        try:
            image_data = self.wb_images[index]
        except IndexError:
            logger.warning("wb: Invalid index: {}. {}".format(index, message_log_str(ctx.message)))
            await self.bot.say("{} (wb) That image doesn't exist! Valid index range: 0-{:d}"
                .format(ctx.message.author.mention, len(self.wb_images) - 1))
        else:
            if len(image_data) != 2:
                err_msg = "Configuration error: invalid entry at index {:d}".format(index)
                logger.error("wb: " + err_msg)
                await self.bot.say("{} (wb) " + err_msg)
                return

            image_url = image_data[0]
            author = image_data[1]
            logger.debug("wb: displaying image {:d}".format(index))
            await self.bot.say(image_url)
            await self.bot.say("_Artist: {}_ (Image #{})".format(author.replace('_', '\_'), index))
            await self.bot.delete_message(ctx.message)


def setup(bot):
    bot.add_cog(ModToolsCog(bot))
