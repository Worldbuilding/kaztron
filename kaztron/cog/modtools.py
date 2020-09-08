from datetime import datetime
import logging
import random
from typing import List, Dict, Optional

import discord
from discord import Member
from discord.ext import commands

from kaztron import KazCog, task
from kaztron.cog.modnotes.model import RecordType
from kaztron.cog.modnotes.modnotes import ModNotes
from kaztron.cog.modnotes import controller, model
from kaztron.config import SectionView
from kaztron.errors import BotCogError
from kaztron.kazcog import ready_only
from kaztron.theme import solarized
from kaztron.utils.checks import mod_only, mod_channels, pm_only
from kaztron.utils.converter import MemberConverter2
from kaztron.utils.discord import get_named_role, Limits
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import parse_keyword_args

logger = logging.getLogger(__name__)


class ModToolsConfig(SectionView):
    """
    :ivar distinguish_map: A mapping of user roles. The key is the user's regular role name, and
        the value is the corresponding role to give the user to distinguish them when they use
        `.up` (and to remove when they use `.down`).
    :ivar tempban_role: The name of a role used to tempban (usually mute, deny channel access, etc.)
        a user.
    :ivar notif_role: The name of the rule used to send notifications to all mods
    :ivar channel_mod: ID of a channel used for mod messages (e.g. timed unbans)
    :ivar wb_images: List of images used for the `.wb` command. Each list item should be a two-
        element list ["url", "artist name/attribution"].
    """
    distinguish_map: Dict[str, str]
    tempban_role: str
    notif_role: str
    channel_mod: str
    wb_images: List[List[str]]


class ModTools(KazCog):
    """!kazhelp
    category: Moderator
    brief: Miscellaneous tools for moderators.
    description: |
        Various tools for moderators to help them in their day-to-day! Some commands are
        dependent on the {{%ModNotes}} module.

        This module will automatically enforce modnotes of type "temp", at startup and every hour
        hence. Use {{!tempban}} in order to immediately apply and enforce a new tempban. (Using
        {{!notes add}} to add a "temp" record will not enforce it until the next hourly check.)
    contents:
        - report
        - up
        - down
        - say
        - tempban
        - whois
        - wb
    """
    cog_config: ModToolsConfig

    def __init__(self, bot):
        super().__init__(bot, 'modtools', ModToolsConfig)
        self.cog_config.set_defaults(distinguish_map={}, wb_images=tuple())
        self.ch_mod = discord.Object(self.cog_config.channel_mod)
        self.cog_modnotes: ModNotes = None
        self.notes = None
        self.tempban_role: discord.Role = None

    async def on_ready(self):
        await super().on_ready()
        try:
            await self.check_for_modnotes()
        except RuntimeError:
            await self.send_output(
                "**ERROR**: Can't find ModNotes cog. The `.tempban` command and automatic tempban "
                "management will not work. `.whois` reverted to basic functionality."
            )
        self.tempban_role = get_named_role(self.server, self.cog_config.tempban_role)
        self.ch_mod = self.validate_channel(self.ch_mod.id)

        # schedule tempban update tick (unless already done i.e. reconnects)
        if self.cog_modnotes and not self.scheduler.get_instances(self.task_update_tempbans):
            self.scheduler.schedule_task_in(self.task_update_tempbans, 0, every=3600)

    async def check_for_modnotes(self):
        logger.debug("Getting modnotes cog")
        self.cog_modnotes = self.bot.get_cog("ModNotes")
        if self.cog_modnotes is None:
            logger.error("Can't find ModNotes cog.")
            raise RuntimeError("Can't find ModNotes cog")
        else:
            self.notes = controller

    def unload_kazcog(self):
        self.scheduler.cancel_all(self.task_update_tempbans)

    @ready_only
    async def on_member_join(self, member: discord.Member):
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
        for status_role_name, distinguish_role_name in self.cog_config.distinguish_map.items():
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
        for status_role_name, distinguish_role_name in self.cog_config.distinguish_map.items():
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

    @commands.command(pass_context=True)
    @mod_only()
    @mod_channels()
    async def say(self, ctx: commands.Context, channel: discord.Channel, *, message: str):
        """!kazhelp

        description: Make the bot say something in a channel.
        parameters:
            - name: channel
              type: string
              description: The channel to say the message in.
            - name: message
              type: string
              description: "The message to say. This will be copied exactly. This includes any
                formatting, @mentions, commands that OTHER bots might react to, and @everyone/@here
                (if the bot is allowed to use them)."
        examples:
            - command: .say #meta HELLO, HUMANS. I HAVE GAINED SENTIENCE.
              description: Says the message in the #meta channel.
        """
        await self.send_message(channel, message)
        await self.send_output(f"Said in {channel} ({ctx.message.author.mention}): {message}")

    def _get_tempbanned_members_db(self, server: discord.Server) -> List[model.Record]:
        if self.notes:
            records = self.notes.query_unexpired_records(types=RecordType.temp)
            members_raw = (server.get_member(record.user.discord_id) for record in records)
            return [m for m in members_raw if m is not None]
        else:
            raise BotCogError("ModNotes cog not loaded. This command requires ModNotes to run.")

    def _get_tempbanned_members_server(self, server: discord.Server) -> List[discord.Member]:
        return [m for m in server.members if self.tempban_role in m.roles]

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

        bans_db = self._get_tempbanned_members_db(server)
        bans_server = self._get_tempbanned_members_server(server)

        # check if any members who need to be banned
        for member in bans_db:
            if member not in bans_server:
                logger.info("Applying tempban role '{role}' to {user!s}...".format(
                    role=self.tempban_role.name,
                    user=member
                ))
                await self.bot.add_roles(member, self.tempban_role)
                await self.bot.send_message(self.ch_mod, "Tempbanned {.mention}".format(member))

        # check if any members who need to be unbanned
        for member in bans_server:
            if member not in bans_db:
                logger.info("Removing tempban role '{role}' to {user!s}...".format(
                    role=self.tempban_role.name,
                    user=member
                ))
                await self.bot.remove_roles(member, self.tempban_role)
                await self.bot.send_message(self.ch_mod, "Unbanned {.mention}".format(member))

    @commands.command(pass_context=True)
    @mod_only()
    @mod_channels()
    async def tempban(self, ctx: commands.Context, user: str, *, reason: str=""):
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
              default: '"in 7 days"'
        examples:
            - command: .tempban @BlitheringIdiot#1234 Was being a blithering idiot.
              description: Issues a 7-day ban.
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
            Finds a Discord user from their ID, name, or name with discriminator. If modnotes is
            enabled, will also search the name and alias fields of modnotes users.

            If an exact match isn't found, then this tool will do a substring search on all visible
            users' names and nicknames.
        parameters:
            - name: user
              type: string
              description: "An ID number, name, name with discriminator, etc. of a user to find. If
                this contains spaces, use quotation marks."
        examples:
            - command: .whois 123456789012345678
              description: Find a user with ID 123456789012345678.
            - command: .whois JaneDoe#0921
              description: Find a user exactly matching @JaneDoe#0921.
            - command: .whois JaneDoe
              description: Find a user whose name matches JaneDoe, or if not found, a user whose
                name or nickname contains JaneDoe.
        """

        # execute searches
        match_user = self._whois_match(ctx, user)  # exact match
        search_users = self._whois_search(ctx, user)  # partial match
        st = user[:Limits.NAME]
        if self.cog_modnotes:  # search modnotes
            notes_users = self.notes.search_users(st)
            notes_map = {}
            notes_orphans = []
            for u in notes_users:
                member = self.server.get_member(u.discord_id)
                if member is not None:
                    notes_map[member] = u
                else:
                    notes_orphans.append(u)
            title_fmt = 'whois {} (with modnotes)'
            field_name = 'Partial and usernote matches'
        else:
            notes_map = {}
            notes_orphans = []
            title_fmt = 'whois {} (NO MODNOTES)'
            field_name = 'Partial matches'

        # prepare the results listing (str_data)
        members = list(set(search_users) | set(notes_map.keys()) - {None})
        str_data = []
        for m in members:
            try:  # prioritise modnote results
                u = notes_map[m]
                str_data.append(self._whois_notes_info(m, u, st))
            except KeyError:  # if no modnote result, show the userlist result
                str_data.append(self._whois_info(m, await self._whois_find_notes_id(m)))
        for u in notes_orphans:
            str_data.append(self._whois_notes_info(None, u, st))
        str_data.sort(key=lambda t: t[0])

        # prepare output
        out = ["**" + title_fmt.format(user) + "**"]
        if match_user:
            out.append("")
            out.append("**Exact match**")
            out.append(self._whois_info(match_user, await self._whois_find_notes_id(match_user))[1])
        if str_data:
            out.append("")
            out.append("**{}**".format(field_name))
            for t in str_data[:50]:
                out.append("→ " + t[1])
            out.append("")

            if len(str_data) > 50:
                out.append("_{:d}/{:d} results (too many matches)_".format(50, len(search_users)))
            else:
                out.append("_{:d} results_".format(len(str_data) + (1 if match_user else 0)))

        if len(out) == 1:
            out.append("No results")

        await self.send_message(ctx.message.channel, "\n".join(out), split='line')

    @staticmethod
    def _whois_match(ctx, user: str) -> Optional[Member]:
        try:
            m = MemberConverter2(ctx, user).convert()
            logger.debug("Found exact match {0.mention} with ID {0.id}".format(m))
            return m
        except commands.BadArgument:
            return None

    @staticmethod
    def _whois_search(ctx, user: str):
        logger.info("whois: searching for name match")
        search = user.lower()
        members = [m for m in ctx.message.server.members
                   if (m.nick and search in m.nick.lower()) or search in m.name.lower()]
        if members:
            member_list_str = ', '.join(str(m) for m in members)
            logger.debug("Found {:d} users: {}".format(len(members), member_list_str))
        else:
            logger.debug("Found no matches")
        return members

    @staticmethod
    def _whois_info(member: discord.Member, notes_id: int=None):
        key = member.nick if member.nick else member.name
        if notes_id is not None:
            info = "{0.mention} (`{0!s}` - nick: `{0.nick}` - notes `*{1}` - id: `{0.id}`)"\
                .format(member, notes_id)
        else:
            info = "{0.mention} (`{0!s}` - nick: `{0.nick}` - id: `{0.id}`)".format(member)
        return key.lower(), info

    async def _whois_find_notes_id(self, member: discord.Member):
        if self.cog_modnotes:
            db_user = await self.notes.query_user(self.bot, member.id)
            return db_user.user_id
        else:
            return None

    def _whois_notes_info(self,
                          member: Optional[discord.Member],
                          user: model.User,
                          search_term: str):
        matched_alias = self._find_match_field(user, search_term)
        info = ("{0} (matched {2}: `{3}` - notes `*{1.user_id}` - canonical name `{1.name}` - "
                "id: `{1.discord_id}`)").format(
            member.mention if member else '`{}`'.format(user.name), user,
            'alias' if matched_alias else 'canonical name',
            matched_alias.name if matched_alias else user.name
        )
        return user.name.lower(), info

    @staticmethod
    def _find_match_field(user: model.User, search_term: str) -> Optional[model.UserAlias]:
        """
        Find whether the canonical name or alias of a user was matched.

        Needed because the results don't indicate whether the canonical name or an alias was
        matched - only 20 results at a time so the processing time shouldn't be a concern.

        :param user:
        :param search_term:
        :return: The UserAlias object that matched, or None if the canonical name matches or
            no match is found (for now this is non-critical, it's a should-not-happen error case
            that just ends up displaying the canonical name - can change to raise ValueError
            in the future?)
        """
        if search_term.lower() in user.name.lower():
            return None

        # noinspection PyTypeChecker
        for alias_ in filter(lambda a: search_term.lower() in a.name.lower(), user.aliases):
            return alias_  # first one is fine
        else:  # if no results from the filter()
            logger.warning(("User is in results set but doesn't seem to match query? "
                            "Is something buggered? "
                            "Q: {!r} User: {!r} Check sqlalchemy output...")
                .format(search_term, user))

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
            index = random.randint(0, len(self.cog_config.wb_images) - 1)
            logger.debug("wb: random image = {:d}".format(index))

        try:
            image_data = self.cog_config.wb_images[index]
        except IndexError:
            logger.warning("wb: Invalid index: {}. {}".format(index, message_log_str(ctx.message)))
            await self.bot.say("{} (wb) That image doesn't exist! Valid index range: 0-{:d}"
                .format(ctx.message.author.mention, len(self.cog_config.wb_images) - 1))
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

    @commands.command(pass_context=True, ignore_extra=False)
    @commands.cooldown(rate=3, per=120)
    @pm_only()
    async def report(self, ctx: commands.Context, *, text: str):
        """!kazhelp
        description: |
            Report an incident to the moderators confidentially.

            Please remember to mention **who** is involved and **where** it's happening (i.e. the
            channel). Your name and the time at which you sent your report are automatically
            recorded.

            IMPORTANT: This will send notifications to mods. Please use only for incidents that need
            to be handled in a time-sensitive manner. For non-time-sensitive situations, ask in the
            #meta channel (or ask there for an available mod to PM, if it's confidential).
        parameters:
            - name: text
              type: string
              description: The text you want to send the mod team. Make sure to mention the **who**
                and **where** (channel).
        examples:
            - command: ".report There's a heated discussion about politics in #worldbuilding, mostly
                between BlitheringIdiot and AggressiveDebater, that might need a mod to intervene."
        """
        es = EmbedSplitter(
            title="User Report",
            timestamp=ctx.message.timestamp,
            colour=solarized.magenta,
            auto_truncate=True
        )
        es.add_field_no_break(name="Sender", value=ctx.message.author.mention, inline=True)
        es.add_field(name="Report Message", value=text, inline=False)
        try:
            notif_role = get_named_role(self.server, self.cog_config.notif_role)
            notif_role_mention = notif_role.mention
        except ValueError:
            notif_role_mention = ''
            logger.warning("Notification role not found: {}".format(self.cog_config.notif_role))
            await self.send_output('[WARNING] Notif role not found: {}'
                .format(self.cog_config.notif_role))
        await self.send_message(self.ch_mod, notif_role_mention, embed=es)
        await self.send_message(
            ctx.message.channel,
            "Thank you. I've forwarded your report to the mods, who will handle it shortly. You "
            "may be contacted by PM or in #meta if we need more information."
        )


def setup(bot):
    bot.add_cog(ModTools(bot))
