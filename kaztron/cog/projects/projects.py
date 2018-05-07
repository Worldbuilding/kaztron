import logging
from datetime import timedelta

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.confirm import ConfirmManager
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
from kaztron.utils.strings import split_chunks_on, format_list, parse_keyword_args

logger = logging.getLogger(__name__)


class ProjectsCog(KazCog):
    """
    Configuration section ``projects``:

    * ``project_channel``: String (channel ID). Channel in which to output/archive projects.
    * ``max_projects``: Maximum number of projects. This can be overridden on a per-user
      basis.
    * ``timeout_confirm``: Timeout (in seconds) for confirming certain commands like delete.
    * ``timeout_wizard``: Timeout (in seconds) for wizards.

    Initial set-up:
    * Use the `.project admin` commands to set up the genre and type list.
    """
    channel_id = KazCog._config.get('projects', 'project_channel')

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults('projects', wizards={})
        self.wizard_manager = None  # type: WizardManager
        self.channel = None  # type: discord.Channel
        self.confirm_del = None  # type: ConfirmManager

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
            self.bot, self.server, self.state.get('projects', 'wizards'),
            timeout=self.config.get('projects', 'timeout_wizard')
        )
        try:
            self.confirm_del = ConfirmManager.from_dict(self.state.get('projects', 'confirm_del'))
            self.confirm_del.timeout = timedelta(  # update this from config
                seconds=self.config.get('projects', 'timeout_confirm'))
        except KeyError:
            timeout_confirm = self.config.get('projects', 'timeout_confirm')
            self.confirm_del = ConfirmManager(timeout=timeout_confirm)

    def _save_state(self):
        self.confirm_del.purge_all()
        self.state.set('projects', 'wizards', self.wizard_manager.to_dict())
        self.state.set('projects', 'confirm_del', self.confirm_del.to_dict())
        self.state.write()

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=False,
        aliases=['projects'])
    async def project(self, ctx: commands.Context, member: MemberConverter2=None, name: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        member = member  # type: discord.Member

        if not member:
            member = ctx.message.author
            logger.debug("project: self-request for {}".format(member))

        with q.transaction():
            user = q.get_or_make_user(member)

        if len(user.projects) == 1:  # only one project to show
            logger.debug("project: {} has only 1 project, showing: {!r}"
                .format(member, user.projects[0]))
            await self.bot.say("**{} Project**".format(member.mention),
                               embed=get_project_embed(user.projects[0]))

        elif len(user.projects) > 1 and name is None:  # list and active project
            listed = format_list(['{0.title} ({0.genre.name}, {0.type.name})'.format(p)
                                  for p in user.projects])
            if user.active_project:
                logger.debug("project: listing {:d} projects for {} + showing active project {!r}"
                    .format(len(user.projects), member, user.active_project))
                await self.bot.say(
                    '**{} Projects**\n{}\n\n**Active Project**'.format(member.mention, listed),
                    embed=get_project_embed(user.active_project)
                )
            else:
                logger.debug("project: listing {:d} projects for {} + no active project"
                    .format(len(user.projects), member))
                await self.bot.say('**{} Projects**\n{}'.format(member.mention, listed))

        elif len(user.projects) > 1 and name:  # find project
            try:
                project = user.find_project(name)
                logger.debug("project: search for user {} title {!r} found {!r}. Showing."
                    .format(member, name, project))
                await self.bot.say(embed=get_project_embed(project))
            except KeyError:
                raise commands.UserInputError(
                    "{} does not have any projects containing \"{}\" in its title."
                    .format(member.nick if member.nick else member.name,
                            name)
                )

        else:
            await self.bot.say("{} doesn't have any projects yet!".format(member.mention))

    @project.command(pass_context=True, ignore_extra=False)
    async def search(self, ctx: commands.Context, *, search: str):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
        kwargs, body_search = parse_keyword_args(['genre', 'type', 'title'], search)

        try:
            genre = q.get_genre(kwargs['genre']) if 'genre' in kwargs else None
        except KeyError:
            raise commands.UserInputError("No such genre: {}. Available genres: {}"
                .format(kwargs['genre'], ', '.join(o.name for o in q.query_genres())))

        try:
            p_type = q.get_project_type(kwargs['type']) if 'type' in kwargs else None
        except KeyError:
            raise commands.UserInputError("No such project type: {}. Available project types: {}"
                .format(kwargs['type'], ', '.join(o.name for o in q.query_project_types())))

        title_search = kwargs.get('title', None)

        results = q.query_projects(genre=genre, type_=p_type, title=title_search, body=body_search)
        listed = []
        for p in results:
            listed.append('{1} - *{0.title}* ({0.genre.name}, {0.type.name})'
                .format(p, user_mention(p.user.discord_id)))
        if not listed:
            listed.append('No results')
        fields = split_chunks_on('\n'.join(listed), Limits.EMBED_FIELD_VALUE, '\n')

        es = EmbedSplitter(auto_truncate=True, title="Project Search Results")
        es.set_footer(text="Results: {:d} projects".format(len(results)))
        es.add_field(name='Results', value=fields[0])
        for field in fields[1:]:
            es.add_field(name='_', value=field)

    @project.command(pass_context=True, ignore_extra=False)
    async def select(self, ctx: commands.Context, name: str):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        await self.wizard_manager.cancel_wizards(ctx.message.author)
        self._save_state()

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)

            try:
                user.active_project = user.find_project(name)
            except KeyError:
                raise commands.UserInputError(
                    "You don't have any projects containing \"{}\" in its title.".format(name)
                )

        logger.info("select: User {0}: active project set to {1.id:d} {1.title!r}"
            .format(ctx.message.author, user.active_project))
        await self.bot.say("{} Your active project has been set to {}"
            .format(ctx.message.author.mention, user.active_project.title))

    @project.command(pass_context=True, ignore_extra=False)
    async def new(self, ctx: commands.Context):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if self.wizard_manager.has_open_wizard(ctx.message.author):
            raise commands.UserInputError("You already have an ongoing wizard!")

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)
            if not user.can_add_projects(self.config.get('projects', 'max_projects')):
                raise commands.UserInputError("You can't have more than {:d} projects!"
                    .format(user.max_projects_eff(self.config.get('projects', 'max_projects'))))

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
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def delete(self, ctx: commands.Context, name: str=None):
        logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))

        if not self.confirm_del.has_request(ctx.message.author):
            await self.delete_request(ctx, name)
        else:
            try:
                await self.delete_confirm(ctx, name)
            except ValueError:
                await self.delete_request(ctx, name)
        self._save_state()

    async def delete_request(self, ctx: commands.Context, name: str):
        logging.info("Received delete request.")

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)

        # Find project reference
        if name:
            try:
                project = user.find_project(name)
                logging.debug("Found {!r} for search {}".format(project, name))
            except KeyError:
                raise commands.UserInputError(
                    "You don't have any projects containing \"{}\" in its title.".format(name)
                )
        elif user.active_project:
            project = user.active_project
            logging.debug("Using active project {!r}".format(user.active_project))
        elif len(user.projects) == 1:
            project = user.projects[0]
            logging.debug("Using only project {!r}".format(user.projects[0]))
        else:
            raise commands.BadArgument("You didn't specify a project to delete!")

        if self.confirm_del.has_request(ctx.message.author):
            pid = self.confirm_del.confirm(ctx)
            logging.info("Overriding previous unconfirmed deletion request for {:d}"
                .format(pid))

        self.confirm_del.request(ctx, project.project_id)
        logging.info("Stored deletion request, pending confirmation.")

        await self.bot.reply(
            ("You are about to delete your project, \"{}\". You will lose all metadata, "
             "wordcount history, goals, etc. for this project. **This cannot be undone.**\n\n"
             "Are you sure? Type `.project delete confirm` or `.project delete cancel`.")
            .format(project.title)
        )

    async def delete_confirm(self, ctx: commands.Context, name: str):
        if name == 'confirm':
            project_id = self.confirm_del.confirm(ctx)
            with q.transaction() as session:
                project = session.query(m.Project).filter_by(project_id=project_id).one()
                title = project.title
                logger.info("Received confirmation. Deleting {!r}.".format(project))
                session.delete(project)
            await self.bot.reply("Project \"{}\" deleted.".format(title))
        elif name == 'cancel':
            pid = self.confirm_del.confirm(ctx)  # just clear and do nothing
            logger.info("Cancelling deletion request for project id {:d}".format(pid))
            await self.bot.reply("Deletion cancelled.")
        else:
            raise ValueError(name)

    @ready_only
    async def on_message(self, message: discord.Message):
        """ Process wizard responses in PM. """
        if not message.channel.is_private:
            return  # wizards only in PM

        try:
            await self.wizard_manager.process_answer(message)
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

                    q.update_user_from_projects(project.user)
                    await update_user_roles(self.bot, self.server, [project.user])

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
        await self.send_output("[Projects] Genre '{}' edited: {}"
            .format(old_name, genre.discord_str()))

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
                logger.info("Replacing genre {!r} with genre {!r}".format(genre, replace_genre))
                logger.debug("...for users: {}".format(', '.join(repr(u) for u in users)))
                logger.debug("...for projects: {}".format(', '.join(repr(p) for p in projects)))
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

            await update_user_roles(self.bot, self.server, q.query_users(type_=p_type))

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

            users = q.query_users(type_=p_type)
            projects = q.query_projects(type_=p_type)
            if replace_type:
                logger.info("Replacing type {!r} with type {!r}".format(p_type, replace_type))
                logger.debug("...for users: {}".format(', '.join(repr(u) for u in users)))
                logger.debug("...for projects: {}".format(', '.join(repr(p) for p in projects)))
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

    # TODO: set (for individual fields), delete - will cancel an open wizard implicitly. Should automatically set user prefs if single project.
    # TODO: *, search {genre|type|title|body}
    # TODO: stats/progress stuff
    # TODO: admin commands - set max projects (+ 'default' keyword), delete project
    # TODO: configure user prefs (role/type/aboutme)

    # TODO: max projects with role support? maybe something for BLOTS to handle
    # TODO: creating/setting follow roles, join/leave
