import logging

import discord

from kaztron import KazCog
from kaztron.utils.discord import remove_role_from_all

logger = logging.getLogger(__name__)


class VoiceLog(KazCog):
    """!kazhelp
    description: Voice chat support features. No commands.
    jekyll_description: |

        * Shows a log of users joining/leaving voice channels. Now you can avoid the "wait, who
          joined / who'd we lose?" conversation!
        * Voice role management. Allows people in voice to be assigned a role, e.g. to let voice
          users see a voice-only text channel or change their colour while in voice.

        **Channels**: {{voice_log_channels}}

        This cog has no commands. It is fully configured in the config.json file (see
        [config.example.json](https://github.com/Worldbuilding/KazTron/blob/master/config.example.json)).

        ## Voice user logging

        This feature replicates the join/part logging available in TeamSpeak, mumble and similar,
        mainly to avoid the "wait, who joined?" and "who'd we lose?" conversations while in voice
        chat on Discord. {{name}} will log voice join and parts in {{voice_log_out_channel}}
        like this:

        ```
        [07:40] KazTron: JaneDoe has joined voice channel #general
        [07:40] KazTron: JaneDoe has moved from voice channel #general to #tabletop
        [07:41] KazTron: JaneDoe has left voice channel #tabletop
        ```

        ## Voice state update

        This cog monitors users' voice channel state. When a user is in a voice channel, they will
        be given the {{voice_log_role}} role. This is normally used to allow only users currently
        in voice to access a voice-specific text channel, but may be used for other purposes.

        Currently, this functionality supports any number of voice channels but only one role.
        This could be extended if needed—mods, talk to DevOps.
     """
    def __init__(self, bot):
        super().__init__(bot)
        self.channel_voicelog = discord.Object(id=self.config.get("voicelog", "channel_text"))  # type: discord.Channel

        self.voice_channel_ids = self.config.get('voicelog', 'channels_voice', [])

        self.is_role_managed = False
        self.role_voice = None  # type: discord.Role
        self.role_voice_name = self.config.get('voicelog', 'role_voice', "")

    async def on_ready(self):
        await super().on_ready()

        self.channel_voicelog = self.validate_channel(self.channel_voicelog.id)

        if self.role_voice_name and self.voice_channel_ids:
            self.is_role_managed = True

            # find the voice role in config
            self.role_voice = None
            for server in self.bot.servers:  # type: discord.Server
                self.role_voice = discord.utils.get(server.roles, name=self.role_voice_name)
                if self.role_voice:
                    logger.info("In-voice role management feature enabled")
                    await self.update_all_voice_role()
                    break
            else:
                self.is_role_managed = False
                err_msg = "Cannot find voice role: {}" .format(self.role_voice_name)
                logger.warning(err_msg)
                await self.send_output("**Warning:** " + err_msg)
                # don't return here - is_role_managed flag OK, this feature not critical to cog
        else:
            self.is_role_managed = False
            err_msg = "In-voice role management is disabled (not configured)."
            logger.warning(err_msg)
            await self.send_output("**Warning:** " + err_msg)

    def export_kazhelp_vars(self):
        variables = {}
        channels = []
        for ch_id in self.voice_channel_ids:
            try:
                channel = self.validate_channel(ch_id)
                channels.append('#' + channel.name)
            except ValueError:
                channels.append('{} (unknown channel)'.format(ch_id))

        variables['voice_log_out_channel'] = '#' + self.channel_voicelog.name
        variables['voice_log_channels'] = ', '.join(channels)
        variables['voice_log_role'] = self.role_voice_name
        return variables

    async def update_all_voice_role(self):
        if not self.is_role_managed:
            return

        logger.debug("Collecting all members currently in voice channels {!r}"
            .format(self.voice_channel_ids))
        server = self.role_voice.server  # type: discord.Server
        voice_users = []
        for ch_id in self.voice_channel_ids:
            channel = server.get_channel(ch_id)  # type: discord.Channel
            try:
                logger.debug("In channel #{}, found users [{}]"
                    .format(channel.name, ', '.join(str(m) for m in channel.voice_members)))
                voice_users.extend(channel.voice_members)
            except AttributeError:
                logger.warning("Cannot find voice channel {}".format(ch_id))

        # clear the in_voice role
        logger.info("Removing role '{}' from all members...".format(self.role_voice.name))
        await remove_role_from_all(self.bot, server, self.role_voice)

        # and add all collected members to that role
        logger.info("Giving role '{}' to all members in voice channels [{}]..."
            .format(self.role_voice.name, ', '.join(str(m) for m in voice_users)))
        for member in voice_users:  # type: discord.Member
            await self.bot.add_roles(member, self.role_voice)

    def is_in_voice(self, member: discord.Member):
        """ Check if the passed member object is in a voice channel listed in the config. """
        return member.voice_channel and member.voice_channel.id in self.voice_channel_ids

    async def on_voice_state_update(self, before: discord.Member, after: discord.Member):
        """ Assigns "in voice" role to members who join voice channels. """
        await self.show_voice_message(before, after)
        await self.update_voice_role(before, after)

    async def show_voice_message(self, before: discord.Member, after: discord.Member):
        """ Show join/part messages in text channel when a user's voice status changes. """
        valid_before = self.is_in_voice(before)
        valid_after = self.is_in_voice(after)

        if valid_before and valid_after:
            msg = "{} has moved from voice channel {} to {}"\
                .format(before.nick if before.nick else before.name,
                        before.voice_channel.mention, after.voice_channel.mention)
        elif valid_after:
            msg = "{} has joined voice channel {}"\
                .format(after.nick if after.nick else after.name, after.voice_channel.mention)
        elif valid_before:
            msg = "{} has left voice channel {}"\
                .format(after.nick if after.nick else after.name, before.voice_channel.mention)
        else:
            msg = None

        if msg:
            # await self.bot.send_message(self.dest_output, msg)
            await self.bot.send_message(self.channel_voicelog, msg)

    async def update_voice_role(self, before: discord.Member, after: discord.Member):
        """ Assigns "in voice" role to members who join voice channels. """
        if not self.is_role_managed:
            return

        # determine the action to take
        if self.is_in_voice(after):
            await self.bot.add_roles(after, self.role_voice)
            logger.info("Gave '{}' role to {}".format(self.role_voice_name, after))
        elif self.role_voice in after.roles:
            await self.bot.remove_roles(after, self.role_voice)
            logger.info("Took '{}' role from {}".format(self.role_voice_name, after))


def setup(bot):
    bot.add_cog(VoiceLog(bot))
