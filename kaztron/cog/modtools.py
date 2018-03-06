import logging
import random

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config
from kaztron.utils.checks import mod_only, mod_channels
from kaztron.utils.discord import get_named_role
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class ModToolsCog:
    def __init__(self, bot):
        self.bot = bot
        self.config = get_kaztron_config()
        self.distinguish_map = self.config.get("modtools", "distinguish_map", {})
        self.wb_images = self.config.get("modtools", "wb_images", [])
        self.ch_output = discord.Object(self.config.get("discord", "channel_output"))

    @commands.command(pass_context=True)
    @mod_only()
    async def up(self, ctx):
        """
        [MOD ONLY] Colours a moderator's username.

        This command colours the moderator's username by applying a special role to it. This is
        used for moderators to be able to signal when they are speaking or intervening officially
        in their role as moderator.

        Arguments: None
        """
        logger.debug("up: {}".format(message_log_str(ctx.message)))

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
            await self.bot.send_message(self.ch_output, "[WARNING] " + err_msg)

    @commands.command(pass_context=True)
    @mod_only()
    async def down(self, ctx):
        """
        [MOD ONLY] Uncolours a moderator's username.

        This command undoes the `.up` command.

        Arguments: None
        """
        logger.debug("down: {}".format(message_log_str(ctx.message)))

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
            await self.bot.send_message(self.ch_output, "[WARNING] " + err_msg)

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    @mod_channels()
    async def whois(self, ctx, user_id: int):
        """
        [MOD ONLY] Finds a Discord user from their Discord ID.

        Arguments:
        * user_id: The ID number of the user.
        """
        user_id = str(user_id)  # int conversion to validate format, but we need string ultimately
        logger.info("finduser: {}".format(message_log_str(ctx.message)))
        user = discord.User(id=user_id)
        logger.info("finduser: user lookup: {!s}={!s}".format(user_id, user))
        await self.bot.say("ID {} is user {}".format(user_id, user.mention))

    @commands.command(pass_context=True, ignore_extra=False)
    @mod_only()
    async def wb(self, ctx, index: int=None):
        """
        [MOD ONLY] Shows a "Please talk about worldbuilding" image.

        For mod intervention, when discussions get off-topic.

        Arguments:
        * index: Optional. If specified, the index of the image to show. If not specified, a
          random image is shown.
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
