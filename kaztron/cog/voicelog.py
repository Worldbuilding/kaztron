import logging
from typing import Dict

import discord

from kaztron import KazCog
from kaztron.config import SectionView
from kaztron.utils.discord import remove_role_from_all, get_named_role

logger = logging.getLogger(__name__)


class VoiceLogConfig(SectionView):
    """
    :ivar voice_text_channel_map: Map of channel IDs, from voice channel to text channel.
    :ivar role_voice: The voice channel role to set for voice users.
    """
    voice_text_channel_map: Dict[str, str]
    role_voice: str


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
        chat on Discord. {{name}} will log voice join and parts in the associated text channel like
        this:

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
    cog_config: VoiceLogConfig

    def __init__(self, bot):
        super().__init__(bot, 'voicelog', VoiceLogConfig)
        self.cog_config.set_defaults(voice_text_channel_map={}, role_voice='')
        self.cog_config.set_converters('role_voice',
            lambda name: discord.utils.get(self.server.roles, name=name),
            lambda _: None)

        self.is_role_managed = False
        self.channel_map = {}  # type: Dict[discord.Channel, discord.Channel]  # voice -> text ch
        self.role_voice = None  # type: discord.Role

    async def on_ready(self):
        await super().on_ready()

        self.channel_map = {}
        for voice_cid, text_cid in self.cog_config.voice_text_channel_map.items():
            try:
                voice_ch = self.validate_channel(voice_cid)
                text_ch = self.validate_channel(text_cid)
            except ValueError:
                msg = "Failed to find one or both channels for voicelog: voice={!r} text={!r}"\
                    .format(voice_cid, text_cid)
                logger.warning(msg)
                await self.send_output("[WARNING] " + msg)
            else:
                self.channel_map[voice_ch] = text_ch

        if self.channel_map and self.cog_config.role_voice:
            try:
                self.role_voice = self.cog_config.role_voice
                self.is_role_managed = True
                logger.info("Voice role management is enabled")
            except ValueError:
                self.is_role_managed = False
                err_msg = "Cannot find voice role: {}" .format(self.cog_config.role_voice)
                logger.warning(err_msg)
                await self.send_output("[WARNING] " + err_msg)
                # don't return here - is_role_managed flag OK, this feature not critical to cog
        else:
            self.is_role_managed = False
            err_msg = "In-voice role management is disabled (not configured)."
            logger.warning(err_msg)
            await self.send_output("[WARNING] " + err_msg)

        await self.update_all_voice_role()

    def export_kazhelp_vars(self):
        variables = {}
        variables['voice_log_channels'] = ', '.join('#' + c.name for c in self.channel_map.keys())
        variables['voice_log_role'] = self.role_voice.name if self.role_voice else 'None'
        return variables

    async def update_all_voice_role(self):
        if not self.is_role_managed:
            return

        voice_channels = list(self.channel_map.keys())
        logger.debug("Collecting all members currently in voice channels {!r}"
            .format(voice_channels))
        voice_users = []
        for channel in voice_channels:
            logger.debug("In channel #{}, found users [{}]"
                .format(channel.name, ', '.join(str(m) for m in channel.voice_members)))
            voice_users.extend(channel.voice_members)

        # clear the in_voice role
        logger.info("Removing role '{}' from all members...".format(self.role_voice.name))
        await remove_role_from_all(self.bot, self.server, self.role_voice)

        # and add all collected members to that role
        logger.info("Giving role '{}' to all members in voice channels [{}]..."
            .format(self.role_voice.name, ', '.join(str(m) for m in voice_users)))
        for member in voice_users:  # type: discord.Member
            await self.bot.add_roles(member, self.role_voice)

    def is_in_voice(self, member: discord.Member):
        """ Check if the passed member object is in a voice channel listed in the config. """
        return member.voice_channel and member.voice_channel in self.channel_map.keys()

    async def on_voice_state_update(self, before: discord.Member, after: discord.Member):
        """ Assigns "in voice" role to members who join voice channels. """
        if before.voice_channel != after.voice_channel:
            await self.show_voice_message(before, after)
            await self.update_voice_role(before, after)

    async def show_voice_message(self, before: discord.Member, after: discord.Member):
        """ Show join/part messages in text channel. Called when a user's voice channel changes. """
        valid_before = self.is_in_voice(before)
        valid_after = self.is_in_voice(after)
        text_before = self.channel_map[before.voice_channel] if valid_before else None
        text_after = self.channel_map[after.voice_channel] if valid_after else None
        same_text_ch = text_before == text_after

        if valid_after and (not valid_before or not same_text_ch):
            await self.send_message(text_after, "{} has joined voice channel {}"
                .format(after.nick if after.nick else after.name, after.voice_channel.mention))

        if valid_before and (not valid_after or not same_text_ch):
            await self.send_message(text_before, "{} has left voice channel {}"
                .format(after.nick if after.nick else after.name, before.voice_channel.mention))

        if valid_before and valid_after and same_text_ch:
            await self.send_message(text_after, "{} has moved from voice channel {} to {}"
                .format(before.nick if before.nick else before.name,
                        before.voice_channel.mention, after.voice_channel.mention))

    async def update_voice_role(self, before: discord.Member, after: discord.Member):
        """ Assigns "in voice" role to members who join voice channels. """
        if not self.is_role_managed:
            return

        # determine the action to take
        if self.is_in_voice(after):
            await self.bot.add_roles(after, self.role_voice)
            logger.info("Gave '{}' role to {}".format(self.role_voice.name, after))
        elif self.role_voice in after.roles:  # if not in voice channel but has voice role
            await self.bot.remove_roles(after, self.role_voice)
            logger.info("Took '{}' role from {}".format(self.role_voice.name, after))


def setup(bot):
    bot.add_cog(VoiceLog(bot))
