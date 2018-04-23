import logging
from typing import List, Sequence

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.converter import MemberConverter2
from . import model as m, query as q, wizard as w
from .wizard import ProjectWizard
from kaztron.driver import database
from kaztron.kazcog import ready_only
from kaztron.theme import solarized
from kaztron.utils.checks import mod_channels, mod_only
from kaztron.utils.discord import user_mention, Limits, get_command_str
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import split_chunks_on, format_list

logger = logging.getLogger(__name__)


class ProjectsCog(KazCog):
    """
    Configuration section ``projects``:

    * ``pm_wizard`` Boolean (true|false). If true, the new projects wizard is PM'd. If false, it
      is conducted in-channel.
    * ``project_channel``: String (channel ID). Channel in which to output/archive projects.
    """
    EMBED_COLOUR = solarized.orange

    channel_id = KazCog._config.get('projects', 'project_channel')

    # TODO: optional followable roles (configurable)

    def __init__(self, bot):
        super().__init__(bot)
        self.config.set_defaults('projects', new_wizards={}, edit_wizards={})
        self.new_wizards = {}
        self.edit_wizards = {}
        self.channel = None  # type: discord.Channel

    async def on_ready(self):
        channel_id = self.config.get('projects', 'proj_channel')
        self.channel = self.validate_channel(channel_id)
        await super().on_ready()
        try:
            self._load_state()
        except Exception:
            self.core.set_cog_shutdown(self)
            raise

    def unload_kazcog(self):
        self._save_state()

    def _load_state(self):
        for uid, wizard_dict in self.state.get('projects', 'new_wizards').items():
            self.new_wizards[uid] = ProjectWizard.from_dict(wizard_dict)

        for uid, wizard_dict in self.state.get('projects', 'edit_wizards').items():
            self.edit_wizards[uid] = ProjectWizard.from_dict(wizard_dict)
            self.edit_wizards[uid].opts = ProjectWizard.keys

    def _save_state(self):
        for section, wizards_dict in (
                ('new_wizards', self.new_wizards),
                ('edit_wizards', self.edit_wizards)
                ):
            self.state.set('projects', section,
                {u.id: wiz.to_dict() for u, wiz in wizards_dict.items()}
            )

    def get_project_embed(self, project: m.Project) -> discord.Embed:
        em = discord.Embed(
            title=project.title,
            description='by {}\n\n{}'.format(user_mention(project.user.discord_id), project.pitch),
            color=self.EMBED_COLOUR
        )
        em.add_field(name='Genre', value='{0.genre.name} - {0.subgenre}'.format(project))
        em.add_field(name='Type', value=project.type.name)
        if project.follow_role:
            em.add_field(name='Follow Role', value=project.follow_role)
        if project.url:
            em.add_field(name='More Info', value=project.url)
        return em

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=False,
        aliases=['projects'])
    async def project(self, ctx: commands.Context, member: MemberConverter2=None, num: int=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        member = member  # type: discord.Member

        if not member:
            member = ctx.message.author

        with q.transaction():
            user = q.get_or_make_user(member)

        if len(user.projects) == 1:
            await self.bot.say("**{} Project #1**".format(member.mention),
                               embed=self.get_project_embed(user.projects[0]))

        elif len(user.projects) > 1:
            if num is None:
                list_str = format_list(['{0.title} ({0.genre.name}, {0.type.name})'.format(p)
                                        for p in user.projects])
                await self.bot.say('**{} Projects**\n{}'.format(member.mention, list_str))
            elif 1 <= num <= len(user.projects):
                await self.bot.say("**{} Project #{}**".format(member.mention, num),
                    embed=self.get_project_embed(user.projects[num-1]))
            else:
                raise commands.BadArgument(
                    "`num` is out of range (1-{:d})".format(len(user.projects)))

        else:
            await self.bot.say("{} doesn't have any projects yet!".format(member.mention))

    @project.command(pass_context=True, ignore_extra=False)
    async def select(self, ctx: commands.Context, num: int):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.has_open_wizard(ctx.message.author):
            await self._cancel_wizards(ctx.message.author)

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)

            if 1 <= num <= len(user.projects):
                user.active_project = user.projects[num-1]
            else:
                raise commands.BadArgument(
                    "`num` is out of range (1-{:d})".format(len(user.projects)))

        await self.bot.say("{} Your active project has been set to {}"
            .format(ctx.message.author.mention, user.active_project.title))

    def has_open_wizard(self, member: discord.Member):
        return member.id in self.new_wizards or member.id in self.edit_wizards

    async def _cancel_wizards(self, member: discord.Member):
        try:
            del self.new_wizards[member.id]
        except KeyError:
            pass
        else:
            logger.info("Cancelled new project wizard for user {}".format(member))
            await self.bot.send_message(member, "Creation of a new project has been cancelled.")

        try:
            del self.edit_wizards[member.id]
        except KeyError:
            pass
        else:
            logger.info("Cancelled project edit wizard for user {}".format(member))
            await self.bot.send_message(member, "Editing your current project has been cancelled.")

        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def new(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.has_open_wizard(ctx.message.author):
            raise commands.CommandError("You already have a wizard open!")

        # send start message
        await self.bot.send_message(ctx.message.author, w.start_msg)

        # set up wizard
        wizard = ProjectWizard(ctx.message.author.id, ctx.message.timestamp)
        self.new_wizards[ctx.message.author.id] = wizard
        self._save_state()

        # Send the first question
        await self.bot.send_message(ctx.message.author, wizard.question)

    @project.command(pass_context=True, ignore_extra=False)
    async def wizard(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.has_open_wizard(ctx.message.author):
            raise commands.CommandError("You already have a wizard open!")

        # check active project
        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)

        if user.active_project is None:
            await self.bot.reply(
                "Oops, you can't edit when you don't have an active (selected) project!")
            return

        # send start message
        start_msg = w.start_edit_msg_fmt.format(user.active_project)
        await self.bot.send_message(ctx.message.author, start_msg)
        self._save_state()

        # set up wizard
        wizard = ProjectWizard(ctx.message.author.id, ctx.message.timestamp)
        self.edit_wizards[ctx.message.author.id] = wizard

        # Send the first question
        await self.bot.send_message(ctx.message.author, wizard.question)

    @project.command(pass_context=True, ignore_extra=False)
    async def cancel(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        await self._cancel_wizards(ctx.message.author)

    @ready_only
    async def on_message(self, message: discord.Message):
        if message.channel.is_private:
            await self._answer_new_wizard(message) or await self._answer_edit_wizard(message)

    async def _answer_new_wizard(self, message: discord.Message) -> bool:
        try:
            wizard = self.new_wizards[message.author.id]
        except KeyError:
            return False

        try:
            logger.debug("{}: {}".format('new wizard', message_log_str(message)))
            wizard.answer(message.content)
            await self.bot.send_message(message.author, wizard.question)
        except StopIteration:
            del self.new_wizards[message.author.id]
            with q.transaction():
                project = q.add_project(wizard)
                out_msg = await self.bot.send_message(
                    self.channel, embed=self.get_project_embed(project)
                )
                project.whois_message_id = out_msg.id
                project.user.active_project = project
            await self.bot.send_message(message.author, w.end_msg)
        self._save_state()

        return True

    async def _answer_edit_wizard(self, message: discord.Message) -> bool:
        try:
            wizard = self.edit_wizards[message.author.id]
        except KeyError:
            return False

        try:
            logger.debug("{}: {}".format('edit wizard', message_log_str(message)))
            wizard.answer(message.content)
            await self.bot.send_message(message.author, wizard.question)
        except StopIteration:
            del self.edit_wizards[message.author.id]
            with q.transaction():
                project = q.update_project(wizard)
            whois_msg = await self.bot.get_message(self.channel, project.whois_message_id)
            new_embed = self.get_project_embed(project)
            await self.bot.edit_message(whois_msg, embed=new_embed)
            await self.bot.send_message(message.author, w.end_msg)
        self._save_state()

        return True

    # TODO: edit, delete - all of these will either fail if wizard is open (new, wizard) or cancel an open wizard implicitly (cancel, select, edit, delete)
    # TODO: *, search {genre|type|title|body}
    # TODO: stats/management stuff
    # TODO: admin commands - max projects

    # todo: auto-output new project into a channel
    # TODO: time limit on wizard
    # TODO: max commands as a config value
    # TODO: select - on invalid num, give list in error message?


