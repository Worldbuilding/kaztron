import logging
from typing import Tuple, Iterable

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.cog.projects.model import Project
from kaztron.utils.converter import MemberConverter2
from . import model as m, query as q, wizard as w
from .discord import *
from .wizard import WizardManager
from kaztron.kazcog import ready_only
from kaztron.driver.database import core_exc
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import user_mention, Limits, get_command_str, \
    get_group_help, get_member
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils.logging import message_log_str, tb_log_str
from kaztron.utils.strings import split_chunks_on, format_list, parse_keyword_args

logger = logging.getLogger(__name__)


class ProjectsCog(KazCog):
    """
    Configuration section ``projects``:

    * ``project_channel``: String (channel ID). Channel in which to output/archive projects.
    * ``max_projects``: Maximum number of projects. This can be overridden on a per-user basis.
    * ``max_projects_map``: Dict that associates role names to max projects. Takes priority over
      the ``max_projects`` configuration value, but is superseded by individual project numbers.
    * ``timeout_confirm``: Timeout (in seconds) for confirming certain commands like delete.
    * ``timeout_wizard``: Timeout (in seconds) for wizards.

    Initial set-up:
    * Use the `.project admin` commands to set up the genre and type list.
    """
    channel_id = KazCog.config.get('projects', 'project_channel')
    emoji = {
        'ok': '\U0001f197',
        'cancel': '\u274c'
    }

    def __init__(self, bot):
        super().__init__(bot)
        self.state.set_defaults('projects', wizards={})
        self.wizard_manager = None  # type: WizardManager
        self.channel = None  # type: discord.Channel

        self.project_setters = {}
        self.setup_project_setter_commands()

    def setup_project_setter_commands(self):
        data = {
            'title': {
                'msg_help': "Set the active project's title.",
                'msg_success': "Project title changed to \"{project.title}\"",
                'msg_err': "Title too long"
            },
            'genre': {
                'msg_help': "Set the active project's genre.",
                'msg_success': "Genre changed to {project.genre.name} "
                               "for project '{project.title}'",
                'msg_err': "Unknown genre: {value}",
                'msg_none': "Available genres: {}"
                            .format(', '.join(o.name for o in q.query_genres()))
            },
            'subgenre':  {
                'msg_help': "Set the active project's subgenre.",
                'msg_success': "Subgenre changed to {project.subgenre} "
                               "for project '{project.title}'",
                'msg_err': "Subgenre too long"
            },
            'type': {
                'msg_help': "Set the active project's type.",
                'msg_success': "Project type changed to {project.type.name} "
                               "for project '{project.title}'",
                'msg_err': "Unknown project type: {value}",
                'msg_none': "Available project types: {}"
                            .format(', '.join(o.name for o in q.query_genres()))
            },
            'pitch': {
                'msg_help': "Set the active project's elevator pitch.",
                'msg_success': "Elevator pitch updated for '{project.title}'",
                'msg_err': "Elevator pitch too long (max {:d} words)"
                            .format(m.Project.MAX_PITCH_WORDS)
            },
            'url': {
                'msg_help': "Set the active project's website URL.",
                'msg_success': "URL updated to {project.url} for '{project.title}'",
                'msg_err': "URL too long (max {:d} characters)"
                            .format(m.Project.MAX_SHORT)
            },
            'description': {
                'msg_help': "Set the active project's long description.",
                'msg_success': "Description updated for '{project.title}'",
                'msg_err': "Description too long (max {:d} characters)"
                            .format(m.Project.MAX_FIELD)
            }
        }
        for attr_name, msgs in data.items():
            try:
                setter = self.make_project_setter(attr_name, **msgs)
                command_params = {
                    'name': attr_name,
                    'pass_context': True,
                    'ignore_extra': False
                }
                cmd = self.project.command(**command_params)(setter)
                cmd.instance = self
                self.project_setters[attr_name] = cmd
            except discord.ClientException as e:
                logger.warning("{}".format(tb_log_str(e)))

    @staticmethod
    def make_project_setter(attr_name: str, msg_help: str,
                            msg_success: str, msg_err: str, msg_none: str=None):
        """
        :param attr_name: Name of the attribute to set on the Project model object.
        :param msg_help: Help message.
        :param msg_success: Format of message to send on success. Variables "project" and
            "value" are available.
        :param msg_err: Format of message to send on invalid value passed. Variables "project"
            and "value" are available.
        :param msg_none: Format of message to send on no value passed. Variable "project"
            is available. Optional; if not passed, None values are not allowed.
        :return:
        """
        async def setter(self: ProjectsCog, ctx: commands.Context, *, new_value: str=None):
            logger.info("{}: {}".format(get_command_str(ctx), message_log_str(ctx.message)))
            with q.transaction():
                project = self.check_active_project(ctx.message.author)
                if new_value:
                    try:
                        setattr(project, attr_name, w.validators[attr_name](new_value))
                    except ValueError:
                        raise commands.BadArgument(msg_err.format(project=project, value=new_value))
                    msg = msg_success.format(project=project, value=new_value)

                    await update_project_message(self.bot, self.channel, project)
                    q.update_user_from_projects(project.user)
                    await update_user_roles(self.bot, self.server, [project.user])
                else:
                    if msg_none:
                        msg = msg_none.format(project=project)
                    else:
                        raise commands.MissingRequiredArgument("new_value")

                await self.bot.say(msg)

        setter.__doc__ = msg_help
        return setter

    def get_default_max_for(self, member: discord.Member):
        """
        Return the default maximum projects number from configuration for a given user (based on
        their roles). This does NOT check whether that user has a specific maximum set for them;
        for that, use :meth:`.model.User.max_projects_eff`, e.g.:

        ..code:: python
            with q.transaction():
                user = q.get_or_make_user(member)
                max_projects = user.max_projects_eff(self.get_default_max_for(member))
        """
        max_projects_map = self.config.get('projects', 'max_projects_map')  # type: dict
        cur_max = 0
        role_found = False
        for role in member.roles:
            if role.name in max_projects_map:
                cur_max = max(cur_max, max_projects_map[role.name])
                role_found = True
        return cur_max if role_found else self.config.get('projects', 'max_projects')

    async def on_ready(self):
        await super().on_ready()
        channel_id = self.config.get('projects', 'project_channel')
        self.channel = self.validate_channel(channel_id)
        await self._update_unsent_projects()
        self._load_state()

    def unload_kazcog(self):
        self._save_state()

    def _load_state(self):
        self.wizard_manager = WizardManager.from_dict(
            self.bot, self.server, self.state.get('projects', 'wizards'),
            timeout=self.config.get('projects', 'timeout_wizard')
        )

    def _save_state(self):
        self.state.set('projects', 'wizards', self.wizard_manager.to_dict())
        self.state.write()

    async def _update_unsent_projects(self):
        unsent_projects = q.query_unsent_projects()
        if unsent_projects:
            logger.info("Posting projects without whois message...")
        for project in unsent_projects:
            logger.debug("Posting project: {!r}".format(project))
            await update_project_message(self.bot, self.channel, project)

    @staticmethod
    def check_active_project(member: discord.Member) -> m.Project:
        """ Should always be called in a transaction context. """
        user = q.get_or_make_user(member)
        if not user.active_project:
            raise commands.UserInputError("You need an active project to use that command! "
                                          "See `.help projects select`.")
        return user.active_project

    @commands.group(invoke_without_command=True, pass_context=True, ignore_extra=False,
        aliases=['projects'])
    async def project(self, ctx: commands.Context, member: MemberConverter2=None, name: str=None):
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
                                  for p in sorted(user.projects, key=lambda p: p.title.lower())])
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
                    .format(member.nick if member.nick else member.name, name)
                )

        else:
            await self.bot.say("{} doesn't have any projects yet!".format(member.mention))

    @project.command(pass_context=True, ignore_extra=False)
    async def search(self, ctx: commands.Context, *, search: str):
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

        logger.info("select: User {0}: active project set to {1.project_id:d} {1.title!r}"
            .format(ctx.message.author, user.active_project))
        await self.bot.say("{} Your active project has been set to {}"
            .format(ctx.message.author.mention, user.active_project.title))

    def get_follow_role(self, member: discord.Member, title: str) -> Tuple[m.Project, discord.Role]:
        with q.transaction():
            user = q.get_or_make_user(member)

        if not user.projects:
            raise commands.UserInputError("User {} does not have any projects."
                .format(member.nick if member.nick else member.name))

        if not title:
            if not user.active_project:
                raise commands.UserInputError(
                    ("User {} does not have an active project. "
                     "Please specify a project title to follow.")
                    .format(member.nick if member.nick else member.name))
            project = user.active_project
        else:
            try:
                project = user.find_project(title)
            except KeyError:
                raise commands.UserInputError(
                    "User {} does not have a project matching '{}'".format(member.mention, title)
                )

        if not project.follow_role_id:
            raise commands.UserInputError("Project {.title} does not have a follow role."
                .format(project))

        try:
            role = get_role(self.server, project.follow_role_id)
        except commands.BadArgument:
            raise commands.UserInputError(
                "The follow role can't be found! Please inform a mod/admin."
            )

        return project, role

    @project.command(pass_context=True, ignore_extra=False)
    async def follow(self, ctx: commands.Context, member: MemberConverter2, *, title: str=None):
        member = member  # type: discord.Member  # for type checking
        project, role = self.get_follow_role(member, title)
        await self.bot.add_roles(ctx.message.author, role)
        await self.bot.reply("you are now following the project {.title}".format(project))

    @project.command(pass_context=True, ignore_extra=False, aliases=['followables'])
    async def followable(self, ctx: commands.Context):
        def sort_key(project: m.Project):
            try:
                member = get_member(ctx, project.user.discord_id)
                return (member.nick if member.nick else member.name).lower()
            except discord.InvalidArgument:
                return "\xff"*5  # sort these users at the end
        projects = sorted(q.query_projects(followable=True), key=sort_key)
        listed = format_list(['{1} - {0.title} ({0.genre.name}, {0.type.name})'
                              .format(p, user_mention(p.user.discord_id))
                              for p in projects]) if projects else 'None'
        logger.debug("followable: listing {:d} followable projects".format(len(projects)))
        await self.bot.say(
            ('**Followable Projects**\n\n'
             'Following allows the creator of the project to notify you of updates, discussions, '
             'etc. surrounding their project. Use `.project follow @nickname title-word` to follow '
             '(`.project unfollow ...` to unfollow).\n\n{}').format(listed))

    @project.command(pass_context=True, ignore_extra=False)
    async def unfollow(self, ctx: commands.Context, member: MemberConverter2, *, title: str=None):
        member = member  # type: discord.Member  # for type checking
        project, role = self.get_follow_role(member, title)
        await self.bot.remove_roles(ctx.message.author, role)
        await self.bot.reply("you are no longer following the project {.title}".format(project))

    @project.command(pass_context=True, ignore_extra=False)
    async def new(self, ctx: commands.Context):
        if self.wizard_manager.has_open_wizard(ctx.message.author):
            raise commands.UserInputError("You already have an ongoing wizard!")

        with q.transaction():
            user = q.get_or_make_user(ctx.message.author)
            default_max = self.get_default_max_for(ctx.message.author)
            if not user.can_add_projects(default_max):
                raise commands.UserInputError("You can't have more than {:d} projects!"
                    .format(user.max_projects_eff(default_max)))

        await self.bot.reply("I've sent you a PM! Answer my questions to create your project.")
        await self.wizard_manager.create_new_wizard(ctx.message.author, ctx.message.timestamp)
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def wizard(self, ctx: commands.Context):
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
    async def aboutme(self, ctx: commands.Context):
        if self.wizard_manager.has_open_wizard(ctx.message.author):
            raise commands.UserInputError("You already have an ongoing wizard!")

        await self.bot.reply("I've sent you a PM! Answer my questions to set up your user profile.")
        await self.wizard_manager.create_author_wizard(ctx.message.author, ctx.message.timestamp)
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def cancel(self, ctx: commands.Context):
        await self.wizard_manager.cancel_wizards(ctx.message.author)
        self._save_state()

    @project.command(pass_context=True, ignore_extra=False)
    async def delete(self, ctx: commands.Context, name: str=None):
        await self._confirmed_delete(ctx, name)

    async def _confirmed_delete(self, ctx: commands.Context,
                                name: str, target_user: discord.Member=None):
        """
        Set a deletion request from a user. A reaction confirm is required by the user.

        :param ctx: Context
        :param name: Title, or part of the title, of the project to delete.
        :param target_user: Optional, for use only with admin delete commands. The user whose
            project to delete.
        :return:
        """
        member = target_user if target_user is not None else ctx.message.author

        with q.transaction():
            user = q.get_or_make_user(member)

        # Find project reference
        if name:
            try:
                project = user.find_project(name)
                logging.debug("delete: Found {!r} for search {}".format(project, name))
            except KeyError:
                raise commands.UserInputError(
                    "{} have any projects containing \"{}\" in its title."
                    .format(target_user.nick + " doesn't" if target_user else "You don't", name)
                )
        elif user.active_project:
            project = user.active_project
            logging.debug("delete: Using active project {!r}".format(user.active_project))
        elif len(user.projects) == 1:
            project = user.projects[0]
            logging.debug("delete: Using sole project {!r}".format(user.projects[0]))
        else:
            raise commands.BadArgument("You didn't specify a project to delete!")

        # wait for confirmation
        msg = await self.bot.reply(
            ("you are about to delete {} project, \"{}\". You will lose all metadata, "
             "wordcount history, goals, etc. for this project. **This cannot be undone.**\n\n"
             "Are you sure? Click one of the buttons below.")
            .format(member.mention + "'s" if target_user else "your", project.title)
        )
        await self.bot.add_reaction(msg, self.emoji['ok'])
        await self.bot.add_reaction(msg, self.emoji['cancel'])
        logging.info("Waiting on confirmation to delete {!r}".format(project))
        res = await self.bot.wait_for_reaction(
            [self.emoji['ok'], self.emoji['cancel']],
            user=member,
            timeout=self.config.get('projects', 'timeout_confirm')
        )

        if res is None:
            logging.info("timeout for {!r}'s request to delete {!r})".format(target_user, project))

        if res.reaction.emoji == self.emoji['ok']:
            logging.info("{!r} confirmed request to delete {!r}".format(target_user, project))
            await self._delete(ctx, project)
        else:
            logging.info("{!r} cancelled request to delete {!r}".format(target_user, project))
            await self.bot.reply("deletion of {} project, \"{}\", has been cancelled."
                .format(member.mention + "'s" if target_user else "your", project.title))
        await self.bot.delete_message(msg)

    async def _delete(self, ctx: commands.Context, project: m.Project):

        with q.transaction():
            title = project.title
            user_id = project.user.discord_id
            admin_deletion = (user_id != ctx.message.author.id)
            q.delete_project(project)

        await delete_project_message(self.bot, self.channel, project)

        await self.bot.reply("{} project \"{}\" has been deleted."
            .format((user_mention(user_id) + "'s") if admin_deletion else "your", title))

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
            project = None
            if name == 'new':
                with q.transaction():
                    project = q.add_project(wizard)
                    project.user.active_project = project
            elif name == 'edit':
                with q.transaction():
                    project = q.update_project(wizard)
            elif name == 'author':
                with q.transaction():
                    q.update_user(wizard)
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
        await self.bot.say("{}".format(get_group_help(ctx)))

    @admin.group(name='genre', pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def admin_genre(self, ctx: commands.Context):
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
        genre = None  # type: m.Genre
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
        with q.transaction():
            try:
                users, _ = q.safe_delete_genre(name, replace_name)
            except KeyError as e:
                raise commands.BadArgument(e.args[0])
            except q.RowReferencedError:
                raise commands.UserInputError(
                    "Can't delete this genre: there are still users or projects using it! "
                    "Make sure no users/projects are using the genre, or provide a replacement.")
            await update_user_roles(self.bot, self.server, users)
        await self.bot.say("Genre deleted: {}".format(name))
        await self.send_output("[Projects] Genre deleted: {}".format(name))

    @admin.group(name='type', pass_context=True, ignore_extra=False, invoke_without_command=True)
    @mod_only()
    async def admin_type(self, ctx: commands.Context):
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
        p_type = None  # type: m.ProjectType
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
        with q.transaction():
            try:
                users, _ = q.safe_delete_project_type(name, replace_name)
            except KeyError as e:
                raise commands.BadArgument(e.args[0])
            except q.RowReferencedError:
                raise commands.UserInputError(
                    "Can't delete this project type: there are still users or projects using it! "
                    "Make sure no users/projects are using the genre, or provide a replacement.")
            await update_user_roles(self.bot, self.server, users)
        await self.bot.say("Project type deleted: {}".format(name))
        await self.send_output("[Projects] Project type deleted: {}".format(name))

    @admin.command(name='delete', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_delete(self, ctx: commands.Context, member: MemberConverter2, title: str=None):
        member = member  # type: discord.Member  # for type checking
        await self._confirmed_delete(ctx, title, member)

    @admin.command(name='limit', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_limit(self, ctx: commands.Context, member: MemberConverter2, limit: int):
        """
        Set a maximum number of projects that a user can have.

        If the user exceeds this number of projects, their old projects will not be deleted.
        However, they will be denied creating new projects until they delete enough projects to be
        below this limit.

        Arguments
        * member: The member to change, as an @mention or user ID.
        * limit: The new maximum number of projects. Use -1 to set this to the default value
          (as specified in the configuration file).

        Examples
            .projects admin limit @MultiCoreProcessor#1234 8
        """
        member = member  # type: discord.Member  # for type checking
        if limit < 0:
            limit = None

        with q.transaction():
            logger.info("Setting {} limit to {}".format(member, limit))
            user = q.get_or_make_user(member)
            user.max_projects = limit

        await self.bot.reply("set {}'s project limit to {:d}{}".format(
            member.mention,
            limit if limit is not None else self.get_default_max_for(member),
            " (default)" if limit is None else ""
        ))

    @admin.command(name='followable', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_followable(self, ctx: commands.Context,
                          member: MemberConverter2, title: str, role: discord.Role=None):
        """
        Set a follow role for a project.

        The follow role must already exist. It should generally be mentionable so that the project
        author is able to notify followers.

        Arguments
        * member: The member who owns the project.
        * title: The title, or an excerpt of the title to search for. If it contains spaces, must
          be enclosed in double quotes.
        * role: A mention of the role to use as a follow role.

        Examples
            .projects admin followable @JaneDoe#0522 "Potato Mansion" @PotatoMansion
        """
        member = member  # type: discord.Member  # for type checking
        project = None  # type: m.Project
        with q.transaction():
            user = q.get_or_make_user(member)
            try:
                project = user.find_project(title)
            except KeyError:
                raise commands.UserInputError(
                    "User {} does not have a project matching '{}'".format(member.mention, title)
                )

            logger.info("Setting project follow role {} for project {!r}"
                .format(role.name if role else "<None>", project))
            project.follow_role_id = role.id if role else None

        if project.follow_role_id:
            await self.bot.reply("set {}'s project follow role to {}"
                .format(member.mention, role.name))
        else:
            await self.bot.reply("removed {}'s project follow role".format(member.mention))
        await update_project_message(self.bot, self.channel, project)

    @admin_followable.error
    async def admin_followable_error(self, exc, ctx):
        if isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc
            if isinstance(root_exc, core_exc.IntegrityError) and \
                    'UNIQUE constraint failed: projects.follow_role' in root_exc.args[0]:
                logger.warning("Can't set follow role: already in use")
                await self.bot.reply("**error**: that follow role is already in use!")
            else:
                await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up
        else:
            await self.core.on_command_error(exc, ctx, force=True)  # Other errors can bubble up

    @admin.command(name='purge', pass_context=True, ignore_extra=False)
    @mod_only()
    async def admin_purge(self, ctx: commands.Context):
        """
        Purge all projects from users who have left the server.

        Examples
            .projects admin purge
        """
        n_deleted = 0
        with q.transaction() as session:
            for user in q.query_users():
                try:
                    get_member(ctx, user.discord_id)
                except discord.InvalidArgument:
                    logging.info("User {} not found: deleting user and projects".format(user))
                    n_deleted += 1
                    projects = user.projects  # type: Iterable[Project]
                    for project in projects:  # type: Project
                        await delete_project_message(self.bot, self.channel, project)
                        session.delete(project)
                    session.delete(user)
        await self.bot.reply("{:d} user(s) purged".format(n_deleted))
