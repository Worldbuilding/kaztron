from datetime import datetime
from datetime import timedelta
import logging

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.cog.modnotes.model import JoinDirection
from kaztron.cog.modnotes.modnotes import ModNotes
from kaztron.cog.modnotes import controller, ModNotesConfig
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.discord import get_group_help

logger = logging.getLogger(__name__)


class JoinTools(KazCog):
    """!kazhelp
    category: Moderator
    brief: Mod notes tools to help keep track of when users join and leave the guild.
    description: |
        Mod notes tools to help keep track of when users join and parts the guild. This cog depends
        on the {{%ModNotes}} module.

        Join/part records are displayed when looking up a user's history using {{!notes}}. They are
        not logged on Discord otherwise. If join/part logging is desired, use the {{%Welcome}}
        module.
    contents:
        - jointools:
            - purge
    """
    cog_config: ModNotesConfig

    #####
    # Lifecycle
    #####

    def __init__(self, bot):
        super().__init__(bot, 'modnotes', ModNotesConfig)
        self.cog_config.set_defaults()
        self.cog_config.set_converters('channel_mod', self.get_channel, None)
        self.cog_modnotes: ModNotes = None

    async def on_ready(self):
        await super().on_ready()
        self.cog_modnotes = self.get_cog_dependency(ModNotes.__name__)  # type: ModNotes
        _ = self.cog_config.channel_mod  # validate that it is set and exists

    def export_kazhelp_vars(self):
        return {
            'mod_channel': '#' + self.cog_config.channel_mod.name
        }

    #####
    # Core
    #####

    #####
    # Discord
    #####

    @ready_only
    async def on_member_join(self, user: discord.Member):
        db_user = await controller.query_user(self.bot, user.id)
        controller.insert_join(user=db_user, direction=JoinDirection.join)

    @ready_only
    async def on_member_remove(self, user: discord.Member):
        db_user = await controller.query_user(self.bot, user.id)
        controller.insert_join(user=db_user, direction=JoinDirection.part)

    @commands.group(pass_context=True, invoke_without_command=True, ignore_extra=True)
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def jointools(self, ctx):
        """!kazhelp
        description: |
            Command group. Utilities for managing the JoinTools functionality.
        """
        await self.bot.say(get_group_help(ctx))

    @jointools.command(pass_context=True, aliases=['a'])
    @mod_only()
    @mod_channels(delete_on_fail=True)
    async def purge(self, ctx: commands.Context):
        """!kazhelp
        description: |
            Purges join/part records of users who a) haven't been seen in at least 30 days; b) have
            no modnotes.
        """
        limit_time = datetime.utcnow() - timedelta(days=30)
        purge_list = controller.purge_joins(before=limit_time)
        await self.send_message(ctx.message.channel, ctx.message.author.mention +
         " Purged {} records".format(len(purge_list)))


def setup(bot):
    bot.add_cog(JoinTools(bot))
