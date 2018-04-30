import copy
import logging
from typing import Iterable

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import get_named_role, get_group_help
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class ManagedRole:
    def __init__(self, bot: discord.Client, *,
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
        logger.debug("join({}): {}".format(self.name, message_log_str(ctx.message)[:256]))
        role = get_named_role(ctx.message.server, self.name)

        if role not in ctx.message.author.roles:
            await self.bot.add_roles(ctx.message.author, role)
            logger.info("join: Gave role {} to user {}".format(self.name, ctx.message.author))
            await self.bot.send_message(self.reply_dest(ctx), self.join_message(ctx))
        else:
            await self.bot.send_message(self.reply_dest(ctx), self.join_error(ctx))
        await self.delete_message(ctx)

    async def do_leave(self, ctx: commands.Context):
        logger.debug("leave({}): {}".format(self.name, message_log_str(ctx.message)[:256]))
        role = get_named_role(ctx.message.server, self.name)

        if role in ctx.message.author.roles:
            await self.bot.remove_roles(ctx.message.author, role)
            logger.info("leave: Removed role {} from user {}".format(self.name, ctx.message.author))
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
    def __init__(self, bot):
        super().__init__(bot)
        self.managed_roles = {}

    async def on_ready(self):
        if not self.is_ready:  # first time this is called - not a reconnect
            self.setup_all_config_roles()
        await super().on_ready()

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
            bot=self.bot, name=role_name, join_msg=join_msg, leave_msg=leave_msg,
            join_err=join_err, leave_err=leave_err, join_doc=join_doc, leave_doc=leave_doc,
            delete=delete, pm=pm, checks=checks
        )
        mr_join, mr_leave = mr.get_command_functions()

        # Set up the commands
        kwargs['pass_context'] = True
        make_command = group.command if group else commands.command
        jc = make_command(name=join_name, aliases=join_aliases, **kwargs)(mr_join)
        lc = make_command(name=leave_name, aliases=leave_aliases, **kwargs)(mr_leave)

        # set up the cog that the commands are associated to (in the bot help, etc.)
        if not cog_instance:
            cog_instance = self

        jc.instance = cog_instance
        lc.instance = cog_instance

        self.managed_roles[role_name] = mr

    def setup_all_config_roles(self):
        logger.info("Setting up managed roles from configuration")
        user_role_map = self.config.get('role_man', 'user_roles', {})
        for name, args in user_role_map.items():
            self.setup_config_role(name, args)

        mod_role_map = self.config.get('role_man', 'mod_roles', {})
        for name, args in mod_role_map.items():
            self.setup_config_role(name, args, [mod_only()])

    def setup_config_role(self, name, role_map, checks: Iterable=tuple()):
        logger.info("Setting up managed role from config: {}".format(name))
        logger.debug("With configuration: {!r}".format(role_map))

        group = role_map.get('group', tuple())
        kwargs = copy.deepcopy(role_map)

        # Recursively get the groups
        logger.debug("Finding group.")
        current_group = self.bot  # type: commands.GroupMixin
        for command_name in group:
            try:
                current_group = current_group.commands[command_name]
            except KeyError:
                logger.warning("Group '{}' does not exist: making dummy group."
                    .format(command_name))
                self._make_dummy_group(current_group, command_name)
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

    def _make_dummy_group(self, parent: commands.GroupMixin, name: str):
        async def anonymous_group(dummy_self, ctx: commands.Context):
            await self.bot.say(get_group_help(ctx))

        current_group = parent.group(
            name=name, invoke_without_command=True, pass_context=True)(anonymous_group)
        current_group.instance = self


def setup(bot):
    bot.add_cog(RoleManager(bot))
