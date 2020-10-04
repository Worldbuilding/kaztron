import logging
import random
from typing import List, Dict, Optional

import discord
from discord import Member
from discord.ext import commands

from kaztron import KazCog
from kaztron.cog.modnotes.modnotes import ModNotes
from kaztron.cog.modnotes import controller, model
from kaztron.config import SectionView
from kaztron.theme import solarized
from kaztron.utils.checks import mod_only, mod_channels, pm_only
from kaztron.utils.converter import MemberConverter2
from kaztron.utils.discord import get_named_role, Limits
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str

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
    notif_role: str
    wb_images: List[List[str]]


class ModTools(KazCog):
    """!kazhelp
    category: Moderator
    brief: Miscellaneous tools for moderators.
    description: |
        Various tools for moderators to help them in their day-to-day! Some commands depend on the
        {{%ModNotes}} module.
    contents:
        - report
        - up
        - down
        - say
        - whois
        - wb
    """
    cog_config: ModToolsConfig

    def __init__(self, bot):
        super().__init__(bot, 'modtools', ModToolsConfig)
        self.cog_config.set_defaults(distinguish_map={}, wb_images=tuple())
        self.cog_modnotes: ModNotes = None

    async def on_ready(self):
        await super().on_ready()
        self.cog_modnotes = self.get_cog_dependency(ModNotes.__name__)

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

        description: Make the bot say something in a channel. If the {{%reminders}} cog is enabled,
            you can also schedule a message at a later time with {{!saylater}}.
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
            notes_users = controller.search_users(st)
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
            db_user = await controller.query_user(self.bot, member.id)
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
            await self.bot.say("_Artist: {}_ (Image #{})".format(author.replace('_', r'\_'), index))
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
        await self.send_message(self.cog_config.channel_mod, notif_role_mention, embed=es)
        await self.send_message(
            ctx.message.channel,
            "Thank you. I've forwarded your report to the mods, who will handle it shortly. You "
            "may be contacted by PM or in #meta if we need more information."
        )


def setup(bot):
    bot.add_cog(ModTools(bot))
