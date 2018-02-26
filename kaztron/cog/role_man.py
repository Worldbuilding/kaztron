import logging

import discord

from kaztron.config import get_kaztron_config
from kaztron.utils.discord import get_named_role

logger = logging.getLogger(__name__)


class RoleManager:
    def __init__(self, bot):
        self.bot = bot  # type: discord.Client
        self.config = get_kaztron_config()
        self.dest_output = discord.Object(id=self.config.get('discord', 'channel_output'))
        self.voice_channel_ids = self.config.get('role_man', 'channels_voice')
        self.role_voice_name = self.config.get('role_man', 'role_voice')
        self.role_voice = None
        self.voice_feature = False

    async def on_ready(self):
        if self.role_voice_name and self.voice_channel_ids:
            self.voice_feature = True
            logger.info("Voice feature enabled (config is not pre-validated)")
        else:
            self.voice_feature = False
            err_msg = "Voice role management is disabled (incomplete config)."
            logger.warning(err_msg)
            await self.bot.send_message(self.dest_output, "[WARNING] " + err_msg)

    async def on_voice_state_update(self, before: discord.Member, after: discord.Member):
        """ Assigns "in voice" role to members who join voice channels. """
        if not self.voice_feature:
            return

        # get the role
        role_voice = get_named_role(before.server, self.role_voice_name)
        if role_voice is None:
            err_msg = "Cannot find voice role: {}" .format(self.role_voice_name)
            logger.warning(err_msg)
            await self.bot.send_message(self.dest_output, "[WARNING] " + err_msg)
            return

        # determine the action to take
        if after.voice_channel and after.voice_channel.id in self.voice_channel_ids:
            await self.bot.add_roles(after, role_voice)
            logger.info("Gave '{}' role to {}".format(self.role_voice_name, after))
        else:
            await self.bot.remove_roles(after, role_voice)
            logger.info("Took '{}' role from {}".format(self.role_voice_name, after))


def setup(bot):
    bot.add_cog(RoleManager(bot))
