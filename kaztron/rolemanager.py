import copy
import logging
from typing import Iterable, Tuple

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.checks import mod_only, admin_only
from kaztron.utils.discord import get_named_role, get_group_help
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class ManagedRole:
    def __init__(self, bot: discord.Client, server: discord.Server, *,
                 name: str,
                 join_msg: str=None,
                 leave_msg: str=None,
                 join_err: str=None,
                 leave_err: str=None,
                 join_doc: str=None,
                 leave_doc: str=None,
                 delete=True,
                 pm=True,
                 join_aliases: Iterable[str]=tuple(),
                 leave_aliases: Iterable[str]=tuple(),
                 checks=tuple()
                 ):
        self.bot = bot
        self.server = server
        self.name = name
        self._join_msg = join_msg or "You have joined the {} role.".format(self.name)
        self._leave_msg = leave_msg or "You have left the {} role.".format(self.name)
        self._join_err = join_err or "Oops! You're already in the {} role.".format(self.name)
        self._leave_err = leave_err or "Oops! You're not in the {} role.".format(self.name)
        self.join_doc = join_doc if join_doc else "Join the {} role.".format(self.name)
        self.leave_doc = leave_doc if leave_doc else "Leave the {} role.".format(self.name)
        self.delete = delete
        self.pm = pm
        self.join_aliases = join_aliases
        self.leave_aliases = leave_aliases
        self.checks = checks
        self.commands = None  # type: Tuple[commands.Command]

    @property
    def role(self) -> discord.Role:
        return get_named_role(self.server, self.name)

    def reply_dest(self, ctx: commands.Context) -> discord.Object:
        return ctx.message.author if self.pm else ctx.message.channel

    def _pre_msg(self, ctx: commands.Context) -> str:
        return '' if self.pm else '{} '.format(ctx.message.author.mention)

    def join_message(self, ctx: commands.Context) -> str:
        return self._pre_msg(ctx) + self._join_msg

    def leave_message(self, ctx: commands.Context) -> str:
        return self._pre_msg(ctx) + self._leave_msg

    def join_error(self, ctx: commands.Context) -> str:
        return self._pre_msg(ctx) + self._join_err

    def leave_error(self, ctx: commands.Context) -> str:
        return self._pre_msg(ctx) + self._leave_err

    async def delete_message(self, ctx: commands.Context):
        if not self.delete:
            return
        try:
            await self.bot.delete_message(ctx.message)
        except discord.Forbidden:
            logger.warning(("Cannot delete command message '{}': "
                            "forbidden (Discord permissions)")
                .format(message_log_str(ctx.message)[:256]))
            # no output channel message - lack of delete isn't critical

    async def do_join(self, ctx: commands.Context):
        member = self.server.get_member(ctx.message.author.id)  # in case it's via PMs
        if self.role not in member.roles:
            await self.bot.add_roles(member, self.role)
            logger.info("join: Gave role {} to user {}".format(self.name, member))
            await self.bot.send_message(self.reply_dest(ctx), self.join_message(ctx))
        else:
            await self.bot.send_message(self.reply_dest(ctx), self.join_error(ctx))
        await self.delete_message(ctx)

    async def do_leave(self, ctx: commands.Context):
        member = self.server.get_member(ctx.message.author.id)  # in case it's via PMs
        if self.role in member.roles:
            await self.bot.remove_roles(member, self.role)
            logger.info("leave: Removed role {} from user {}".format(self.name, member))
            await self.bot.send_message(self.reply_dest(ctx), self.leave_message(ctx))
        else:
            await self.bot.send_message(self.reply_dest(ctx), self.leave_error(ctx))
        await self.delete_message(ctx)

    def get_command_functions(self):
        """
        Return a tuple of (join_func, leave_func). Each has a signature of
        ``func(self_dummy, ctx: commands.Context) -> None``.
        """

        async def _managed_role_join(self_dummy, ctx: commands.Context):
            await self.do_join(ctx)

        async def _managed_role_leave(self_dummy, ctx: commands.Context):
            await self.do_leave(ctx)

        _managed_role_join.__doc__ = self.join_doc
        _managed_role_leave.__doc__ = self.leave_doc

        # checks
        for check in self.checks:
            _managed_role_join = check(_managed_role_join)
            _managed_role_leave = check(_managed_role_leave)

        return _managed_role_join, _managed_role_leave


class RoleManager(KazCog):
    """!kazhelp
    category: Commands
    description: |
        Allows the creation of commands that allow users to join and leave specific roles on
        their own through bot commands.

        See the on-line documentation for more information.
    jekyll_description: |
        This cog provides generalised capabilities for creating commands that allow users to add and
        remove themselves from a role, using custom command names. This allows users to opt into
        certain features, events or programmes on the Discord server, such as getting notifications
        for special-interest news or live events.

        These commands can be defined either via the config file, or programmatically (e.g. from
        within a cog). They **cannot** dynamically be defined via commands.

        ## Programmatic

        Within a `KazCog`-derived cog class, it is possible to access `self.roleman` anytime after
        calling `super().on_ready()` in the `on_ready()` event.

        An example is shown below. In this example, the current cog has a command group called
        `sprint` already defined. The commands `.sprint follow` and `.sprint unfollow` would allow
        any user to join and leave the "Sprinters" role (this role must already be configured on the
        Discord server).

        To add checks like `mod_only()`, pass a list of checks as a `checks` keyword argument to
        `add_managed_role()`.

        ```python
        try:
            self.rolemanager.add_managed_role(
                role_name="Sprinters",
                join_name="follow",
                leave_name="unfollow",
                join_msg="You will now receive notifications when others start a sprint. "
                         "You can stop getting notifications by using the `.w unfollow` command.",
                leave_msg="You will no longer receive notifications when others start a sprint. "
                          "You can get notifications again by using the `.w follow` command.",
                join_err="Oops! You're already receiving notifications for sprints. "
                         "Use the `.w unfollow` command to stop getting notifications.",
                leave_err="Oops! You're not currently getting notifications for sprints. "
                          "Use the `.w follow` command if you want to start getting notifications.",
                join_doc="Get notified when sprints are happening.",
                leave_doc="Stop getting notifications about sprints.\\n\\n"
                          "You will still get notifications for sprints you have joined.",
                delete=True,
                pm=True,
                group=self.sprint,
                cog_instance=self,
                ignore_extra=False
            )
        except discord.ClientException:
            logger.warning("add_managed_role failed - this is fine on bot reconnect")
        ```

        ### Arguments

        * `role_name`: The role to manage.
        * `join_name`: The join command name. If `group` is passed, this command is a subcommand of
            that group.
        * `leave_name`: The leave command name. If `group` is passed, this command is a subcommand
            of that group.
        * `join_aliases`: Optional. A sequence of join command aliases.
        * `leave_aliases`: Optional. An sequence of leave command aliases.
        * `join_msg`: Message to send when the user successfully joins the role.
        * `leave_msg`: Message to send when the user successfully leaves the role.
        * `join_err`: Message when the user tries to join but is already member of the role.
        * `leave_err`: Message when the user tries to leave but is not a role member.
        * `join_doc`: Help string for the join command.
        * `leave_doc`: Help string for the leave command.
        * `delete`: Optional. If True, delete the requesting command. Default: True.
        * `pm`: Optional. If True, PM the response to the user. Otherwise, respond in the same
            channel. Default: True.
        * `group`: The group to add this command to. Optional.
        * `cog_instance`: Optional. Cog to group this command under in the help. Default: the
            RoleManager cog.
        * `checks`: Check objects to apply to the command
        * Further keyword arguments can be passed. These will be passed transparently to the
            `discord.ext.commands.command` decorator. Do not include `name`, `aliases`, or
            `pass_context`, as these are handled internally.

        ## Configuration file

        It is also possible to do this in the `config.json` file. In this case, the commands will
        always appear in `.help` under RoleManager. Please see `config.example.json` for an example
        of the structure, and refer to section above for documentation on the parameters.
    """
    def __init__(self, bot):
        super().__init__(bot, 'rolemanager')
        self.cog_config.set_defaults(user_roles={}, mod_roles={})
        self.managed_roles = {}

    async def on_ready(self):
        await super().on_ready()
        # unload all managed roles to reconfigure them
        for mr in self.managed_roles.values():
            self.remove_managed_role(mr)
        self.managed_roles = {}

        self.setup_all_config_roles()

    def unload_kazcog(self):
        """ Unload managed roles. """
        logger.debug("Unloading managed roles...")
        for role_name, mr in self.managed_roles.items():
            self.remove_managed_role(mr)
        self.managed_roles = {}

    def add_managed_role(
            self,
            role_name: str,
            join_name: str,
            leave_name: str,
            join_msg: str=None,
            leave_msg: str=None,
            join_err: str=None,
            leave_err: str=None,
            join_doc: str=None,
            leave_doc: str=None,
            delete=True,
            pm=True,
            join_aliases: Iterable[str]=tuple(),
            leave_aliases: Iterable[str]=tuple(),
            group: commands.Group=None,
            cog_instance=None,
            checks=tuple(),
            **kwargs
            ):
        """
        Add managed roles from other cogs or code. This method should be called in or after on_ready
        to ensure that server roles are loaded.

        :param role_name: The role to manage.
        :param join_name: The join command name.
        :param leave_name: The leave command name.
        :param join_aliases: An iterable of join command aliases. Optional.
        :param leave_aliases: An iterable of leave command aliases. Optional.
        :param join_msg: Message to send when the user successfully joins the role.
        :param leave_msg: Message to send when the user successfully leaves the role.
        :param join_err: Message when the user tries to join but is already member of the role.
        :param leave_err: Message when the user tries to leave but is not a role member.
        :param join_doc: Help string for the join command.
        :param leave_doc: Help string for the leave command.
        :param delete: If True, delete the requesting command.
        :param pm: If True, PM the response to the user. Otherwise, respond in the same channel.
        :param group: The group to add this command to. Optional.
        :param cog_instance: Cog to group this command under in the help.
        :param checks: Check objects to apply to the command
        :param kwargs: Keyword args to pass the ``discord.ext.commands.command`` decorator. Do not
            include `name`, `aliases`, or `pass_context`. Can also include checks here, e.g., for
            if only certain users should be able to use these commands.

        :raise TypeError: Command already exists (elsewhere, not as a managed role)
        :raise ClientException: Command is already managed
        """

        if self.managed_roles.get(role_name, None):
            raise discord.errors.ClientException("Role {} already managed".format(role_name))

        logger.info("Adding managed role {}".format(role_name))

        mr = ManagedRole(
            bot=self.bot, server=self.server, name=role_name,
            join_msg=join_msg, leave_msg=leave_msg,
            join_err=join_err, leave_err=leave_err,
            join_doc=join_doc, leave_doc=leave_doc,
            delete=delete, pm=pm, checks=checks
        )
        mr_join, mr_leave = mr.get_command_functions()

        # Set up the commands
        kwargs['pass_context'] = True
        make_command = group.command if group else commands.command
        jc = make_command(name=join_name, aliases=join_aliases, **kwargs)(mr_join)
        lc = make_command(name=leave_name, aliases=leave_aliases, **kwargs)(mr_leave)
        mr.commands = (jc, lc)

        # set up the cog that the commands are associated to (in the bot help, etc.)
        if not cog_instance:
            cog_instance = self

        jc.instance = cog_instance
        lc.instance = cog_instance

        self.managed_roles[role_name] = mr

    def remove_managed_role(self, mr: ManagedRole):
        for cmd in mr.commands:  # type: commands.Command
            if cmd.parent is not None:
                parent = cmd.parent  # type: commands.GroupMixin
            else:
                parent = self.bot
            rmret = parent.remove_command(cmd.name)

            if rmret is not None:
                logger.debug("Unloaded command {} for role {}".format(cmd.name, mr.name))
            else:
                logger.warning("Failed to unload command {} for role {}".format(cmd.name, mr.name))

    def setup_all_config_roles(self):
        logger.info("Setting up managed roles from configuration")
        user_role_map = self.cog_config.user_roles
        for name, args in user_role_map.items():
            self.setup_config_role(name, args)

        mod_role_map = self.cog_config.mod_roles
        for name, args in mod_role_map.items():
            self.setup_config_role(name, args, [mod_only()])

    def setup_config_role(self, name, role_map, checks: Iterable=tuple()):
        logger.info("Setting up managed role from config: {}".format(name))
        logger.debug("With configuration: {!r}".format(role_map))

        group = role_map.get('group', tuple())
        kwargs = copy.deepcopy(role_map)

        # Recursively get the groups
        logger.debug("Finding command group.")
        current_group = self.bot  # type: commands.GroupMixin
        for command_name in group:
            try:
                current_group = current_group.commands[command_name]
            except KeyError:
                logger.warning("Group '{}' does not exist: making dummy group."
                    .format(command_name))
                current_group = self._make_dummy_group(current_group, command_name)
            except AttributeError:
                raise discord.ClientException(
                    ("Cannot group role management command: parent "
                     "command '{0.name}' is not a group").format(current_group)
                )
        else:
            kwargs['group'] = current_group

        kwargs['checks'] = checks

        try:
            self.add_managed_role(role_name=name, **kwargs)
        except TypeError as e:
            raise discord.ClientException("Configuration error for managed role '{}': {}"
                .format(name, e.args[0]))

    def _make_dummy_group(self, parent: commands.GroupMixin, name: str) -> commands.GroupMixin:
        async def anonymous_group(dummy_self, ctx: commands.Context):
            await self.bot.say(get_group_help(ctx))

        current_group = parent.group(
            name=name, invoke_without_command=True, pass_context=True)(anonymous_group)
        current_group.instance = self
        return current_group
