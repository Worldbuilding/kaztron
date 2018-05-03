import logging

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.converter import MemberConverter2
from . import model as m, query as q
from .discord import *
from .wizard import WizardManager
from kaztron.kazcog import ready_only
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import user_mention, role_mention, Limits, get_command_str,\
    get_group_help
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import split_chunks_on, format_list

logger = logging.getLogger(__name__)


class ProjectsCog(KazCog):
    """
    Configuration section ``projects``:

    * ``project_channel``: String (channel ID). Channel in which to output/archive projects.

    Initial set-up:
    * Use the `.project admin` commands to set up the genre and type list.
    """
    channel_id = KazCog._config.get('projects', 'project_channel')

    # TODO: optional followable roles (configurable)

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults('projects', wizards=WizardManager(self.bot).to_dict())
        self.wizard_manager = None
        self.channel = None  # type: discord.Channel

    async def on_ready(self):
        channel_id = self.config.get('projects', 'project_channel')
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
        self.wizard_manager = WizardManager.from_dict(
            self.bot, self.state.get('projects', 'wizards')
        )

    def _save_state(self):
        self.state.set('projects', 'wizards', self.wizard_manager.to_dict())
        self.state.write()

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
            await self.bot.say("**{} Project**".format(member.mention),
                               embed=get_project_embed(user.projects[0]))

        elif len(user.projects) > 1:
            if num is None:
                list_str = format_list(['{0.title} ({0.genre.name}, {0.type.name})'.format(p)
                                        for p in user.projects])
                if user.active_project:
                    await self.bot.say(
                        '**{} Projects**\n{}\n\n**Active Project**'.format(member.mention, list_str),
                        embed=get_project_embed(user.active_project)
                    )
                else:
                    await self.bot.say('**{} Projects**\n{}'.format(member.mention, list_str))

            elif 1 <= num <= len(user.projects):
                await self.bot.say("**{} Project #{}**".format(member.mention, num),
                    embed=get_project_embed(user.projects[num-1]))

            else:
                raise commands.BadArgument("`num` is out of range (1-{:d})"
                    .format(len(user.projects)))

        else:
            await self.bot.say("{} doesn't have any projects yet!".format(member.mention))

    @project.command(pass_context=True, ignore_extra=False)
    async def select(self, ctx: commands.Context, num: int):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        await self.wizard_manager.cancel_wizards(ctx.message.author)
        self._save_state()

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)

            if 1 <= num <= len(user.projects):
                user.active_project = user.projects[num-1]
            else:
                raise commands.BadArgument(
                    "`num` is out of range (1-{:d})".format(len(user.projects)))

        await self.bot.say("{} Your active project has been set to {}"
            .format(ctx.message.author.mention, user.active_project.title))

    @project.command(pass_context=True, ignore_extra=False)
    async def new(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.wizard_manager.has_open_wizard(ctx.message.author):
            raise commands.UserInputError("You already have an ongoing wizard!")

        await self.bot.reply("I've sent you a PM! Answer my questions to create your project.")
        await self.wizard_manager.create_new_wizard(ctx.message.author, ctx.message.timestamp)
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def wizard(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.wizard_manager.has_open_wizard(ctx.message.author):
            raise commands.UserInputError("You already have an ongoing wizard!")

        # check active project
        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)
        if user.active_project is None:
            raise commands.UserInputError("Oops, you can't edit when you don't have "
                                          "an active (selected) project!")

        await self.bot.reply("I've sent you a PM! "
                             "Answer my questions to modify your current project.")

        await self.wizard_manager.create_edit_wizard(
            ctx.message.author, ctx.message.timestamp, user.active_project
        )
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def cancel(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        await self.wizard_manager.cancel_wizards(ctx.message.author)

    @ready_only
    async def on_message(self, message: discord.Message):
        """ Process wizard responses in PM. """
        if not message.channel.is_private:
            return  # wizards only in PM

        try:
            self.wizard_manager.process_answer(message)
        except KeyError:
            return  # no active wizard, ignore
        except ValueError as e:
            await self.bot.send_message(message.channel, e.args[0])
            return

        try:
            await self.wizard_manager.send_question(message.author)
        except IndexError:
            pass

        try:
            name, wizard = await self.wizard_manager.close_wizard(message.author)
        except KeyError:  # wizard not yet complete
            pass
        else:
            if name == 'new':
                with q.transaction():
                    project = q.add_project(wizard)
                    project.user.active_project = project
            elif name == 'edit':
                with q.transaction():
                    project = q.update_project(wizard)
            else:
                project = None
                logger.error("Unknown wizard type {!r}???".format(name))
                await self.send_output("Unknown wizard type {!r}???".format(name))

            if project:
                with q.transaction():
                    await update_project_message(self.bot, self.channel, project)

        self._save_state()

    @project.group(pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def admin(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        await self.bot.say("{}".format(get_group_help(ctx)))

    @admin.group(name='genre', pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def admin_genre(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        genres = q.query_genres()
        genre_strings = []
        for genre in genres:
            role = discord.utils.get(self.server.roles, id=genre.role_id)  # type: discord.Role
            genre_strings.append('{.name} (role: {})'.format(genre, role.name if role else 'None'))
        genre_list = "**Genres**\n\n" + (format_list(genre_strings) if genre_strings else 'None')
        for s in split_chunks_on(genre_list, Limits.MESSAGE):
            await self.bot.say(s)

    @admin_genre.command(name='add', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_genre_add(self, ctx: commands.Context, name: str, role: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction() as session:
            logger.info("Adding new genre: name={!r} role={!r}".format(name, role))
            role_id = get_role(self.server, role).id if role else None
            genre = m.Genre(name=name, role_id=role_id)
            session.add(genre)
        await self.bot.say("Genre added: {}".format(name))
        await self.send_output("[Projects] Genre added: {}".format(genre.discord_str()))

    @admin_genre.command(name='edit', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_genre_edit(self, ctx: commands.Context,
                               old_name: str, new_name: str, new_role: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction() as _:

            try:
                genre = q.get_genre(old_name)
            except KeyError:
                raise commands.BadArgument("No such genre: {}".format(old_name))

            logger.info("Editing genre {!r} to: name={!r} role={!r}"
                .format(old_name, new_name, new_role))
            genre.name = new_name
            genre.role_id = get_role(self.server, new_role).id if new_role else None

            await update_user_roles(self.bot, self.server, q.query_users(genre=genre))

        await self.bot.say("Genre '{}' edited to '{}'".format(old_name, new_name))
        await self.send_output("[Projects] Genre '{}' edited: {}".format(old_name, genre.discord_str()))

    @admin_genre.command(name='rem', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_genre_remove(self, ctx: commands.Context, name: str, replace_name: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction() as session:
            # Replace the deleted genre in projects/users
            try:
                genre = q.get_genre(name)
                if replace_name:
                    replace_genre = q.get_genre(replace_name)
                else:
                    replace_genre = None
            except KeyError as e:
                raise commands.BadArgument(e.args[0])

            users = q.query_users(genre=genre)
            projects = q.query_projects(genre=genre)
            if replace_genre:
                for u in users:
                    u.genre = replace_genre
                for p in projects:
                    p.genre = replace_genre

                await update_user_roles(self.bot, self.server, users)

            elif users or projects:  # no replace_genre but genre is in use
                raise commands.UserInputError(
                    "Can't delete this genre: there are still users or projects using it! "
                    "Make sure no users/projects are using the genre or to provide a substitute.")

            # finally, delete the genre
            logger.info("Deleting genre {!r}".format(name))
            session.delete(genre)
        await self.bot.say("Genre deleted: {}".format(name))
        await self.send_output("[Projects] Genre deleted: {}".format(genre.discord_str()))

    @admin.group(name='type', pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def admin_type(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        p_types = q.query_project_types()
        types_strings = []
        for t in p_types:
            role = discord.utils.get(self.server.roles, id=t.role_id)  # type: discord.Role
            types_strings.append('{.name} (role: {})'.format(t, role.name if role else 'None'))
        types_list = "**Project Types**\n\n" + \
                     (format_list(types_strings) if types_strings else 'None')
        for s in split_chunks_on(types_list, Limits.MESSAGE):
            await self.bot.say(s)

    @admin_type.command(name='add', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_type_add(self, ctx: commands.Context, name: str, role: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction() as session:
            logger.info("Adding new project type: name={!r} role={!r}".format(name, role))
            pt = m.ProjectType(name=name, role_id=get_role(self.server, role).id if role else None)
            session.add(pt)
        await self.bot.say("Project type added: {}".format(name))
        await self.send_output("[Projects] Project type added: {}".format(pt.discord_str()))

    @admin_type.command(name='edit', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_type_edit(self, ctx: commands.Context,
                              old_name: str, new_name: str, new_role: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction():
            try:
                p_type = q.get_project_type(old_name)
            except KeyError:
                raise commands.BadArgument("No such project type: {}".format(old_name))

            logger.info("Editing project type {!r} to: name={!r} role={!r}"
                .format(old_name, new_name, new_role))

            p_type.name = new_name
            p_type.role_id = get_role(self.server, new_role).id if new_role else None

            await update_user_roles(self.bot, self.server, q.query_users(type=p_type))

        await self.bot.say("Project type '{}' edited to '{}'".format(old_name, new_name))
        await self.send_output("[Projects] Project type '{}' edited: {}"
            .format(old_name, p_type.discord_str()))

    @admin_type.command(name='rem', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_type_remove(self, ctx: commands.Context, name: str, replace_name: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        with q.transaction() as session:
            # Replace the deleted genre in projects/users
            try:
                p_type = q.get_project_type(name)
                if replace_name:
                    replace_type = q.get_project_type(replace_name)
                else:
                    replace_type = None
            except KeyError as e:
                raise commands.BadArgument(e.args[0])

            users = q.query_users(type=p_type)
            projects = q.query_projects(type=p_type)
            if replace_type:
                for u in users:
                    u.type = replace_type
                for p in projects:
                    p.type = replace_type

                await update_user_roles(self.bot, self.server, users)

            elif users or projects:  # no replace_type but genre is in use
                raise commands.UserInputError(
                    "Can't delete this genre: there are still users or projects using it! "
                    "Make sure no users/projects are using the genre or to provide a substitute.")

            # finally, delete the genre
            logger.info("Deleting project type {!r}".format(name))
            session.delete(p_type)
        await self.bot.say("Project type deleted: {}".format(name))
        await self.send_output("[Projects] Project type deleted: {}".format(p_type.discord_str()))

    # TODO: set (for individual fields), delete - will cancel an open wizard implicitly
    # TODO: *, search {genre|type|title|body}
    # TODO: stats/progress stuff
    # TODO: admin commands - set max projects, delete project
    # TODO: configure user prefs (role/type/aboutme)

    # TODO: max projects on `new` command
    # TODO: for user's first project or max_projects=1, automatically associate their user genre/type preferences to their primary project

    # TODO: time limit on wizard
    # TODO: automatically set user prefs if single project
    # TODO: max projects default value as a config value (with role support?)
    # TODO: select - on invalid num, give list in error message?

    # TODO: creating/setting follow roles
