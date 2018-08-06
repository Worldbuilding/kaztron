import copy
import html
from datetime import datetime
import inspect
import logging
import re
from textwrap import shorten, indent, wrap
from typing import Union, Callable, Dict

import discord
from discord.ext.commands import HelpFormatter
from ruamel.yaml import YAML, YAMLError

from discord.ext import commands

from kaztron.utils.checks import CheckId
from kaztron.utils.discord import get_named_role, get_command_prefix
from .kazcog import KazCog

logger = logging.getLogger(__name__)

CommandOrGroup = Union[commands.Command, commands.GroupMixin]


class NotKazhelpError(ValueError):
    pass


class CoreHelpParser:
    """ Core help formatter for KazCogs. This formatter will make use of
    structured help data and compatible KazTron-defined check functions to construct the help data.
    If this data is not available for a given command, then the normal discord.py help formatting is
    used.

    Structured data is contained in the docstring of the cog class and its commands, or the
    description field of the commands. It must begin by the string '!kazhelp', followed by YAML-
    formatted data containing the following fields:

    description: String describing what the command does. Should start with an imperative verb.
        This is shown in the full help output for the command, BEFORE the usage/arguments.
        Should be kept reasonable brief (one sentence to one paragraph).
    brief: Optional. Brief help, shown in command listings. If not specified, the first line of
        description is used.
    details: Optional. Additional information on the command. This is shown after the usage, but
        before the parameters and other command information.
    parameters:
        - name: parameter name (same as the parameter in code!)
          default: optional. Default value, for optional parameters.
          type: optional. Type.
          optional: optional. 'true' or 'false'. Default is 'false'.
          description: Longform description. Required.
        - name: ...
          default: etc.
    examples:
        - command: .command string here
          description: A short description.
        - command: ...
          description: etc.
    users: Optional. String describing users who can use this command. If compatible KazTron check
        functions are used, will also be listed in this section.
    channels: Optional. Channels in which this command can be used. If compatible KazTron check
        functions are used, will also be listed in this section.

    The description and details can also contain the following tags at the beginning of a paragraph,
    which may be specially interpreted by various KazTron help formatters.
        - IMPORTANT:
        - WARNING:
        - NOTE:
        - TIP:

    You can also include the following inline tags in any field:
        - {{name}} - Bot's name.
        - {{!command name}} - A link to another command (or subcommand).
        - {{%CogName}} - A link to a cog.

    Cogs may override KazCog's :meth:`~KazCog.export_kazhelp_vars` in order to define custom
    variables. Predefined variables cannot be overridden. Variable names must start with
    [A-Za-z0-9_] and must not contain curly braces.

    In addition, the cog docstring may specify the order of commands and subcommands as part of its
    structured data. This data may or may not be used: e.g. for the Discord output format, this data
    is not considered, but for the Jekyll formatter it is. For example:

    contents:
        - command1
        - command2:
            - subcommand1
            - subcommand2
        - command3:
            - subcommand1
            - subcommand2

    Note the colon in cases that a command has subcommands.

    Any commands or subcommands which do not appear in this list will be listed alphabetically
    after the specified commands. A warning will be issued by the formatter(s).

    Convenient template for the lazy:

    !kazhelp

    brief:
    description: |
        Blah. Blah. Blah.
    details: |
        Blah. Blah. Blah.
    parameters:
        - name:
          default:
          type:
          optional: true|false
          description:
    examples:
        - command:
          description:
    """
    cog_fields = {'description', 'jekyll_description', 'brief', 'details',
                  'parameters', 'examples', 'users', 'channels', 'contents'}
    cmd_fields = {'description', 'jekyll_description', 'brief', 'details',
                  'parameters', 'examples', 'users', 'channels'}
    blocks = ('IMPORTANT', 'WARNING', 'NOTE', 'TIP')
    var_re = re.compile('{{\s*([A-Za-z0-9_-]+)\s*}}')
    tags_re = re.compile(r'^\s*(' + '|'.join(blocks) + r'): (.*)$', re.S)
    links_re = re.compile(r'{{\s*([!%])\s*(.*?)\s*}}')

    def __init__(self, variables=None):
        self.variables = variables or {}
        self.cog_vars = {}  # type: Dict[str, Dict[str, str]]
        self.yaml = YAML(typ='safe')

    def parse(self, command: Union[commands.Command, KazCog], bot: commands.Bot):
        """
        Parse KazTron structured help documentation. This method stores the parsed documentation and
        some live information (e.g. annotated command checks) in the command object's
        ``kaz_structured_help`` attribute.

        This method is expected to be called by other help formatter routines that will then use
        this structured data to generate the final format (e.g. in-bot help, or generating HTML or
        Markdown for online documentation).

        Further helper methods :meth:`parse_tags` and :meth:`parse_links` are provided, in order to
        allow formatting of tags (IMPORTANT, WARNING, etc.) and inter-command links when needed.

        :param command: Command whose help to parse.
        :param bot: Bot instance the command is tied to
        :return: final parsed data
        :raise ValueError: command does not contain kazhelp-formatted data.
        """
        try:
            doc_data = copy.deepcopy(command.kaz_structured_help)
        except AttributeError:  # kaz_structured_help doesn't exist yet
            try:
                doc_data = self._parse_yaml(command)
            except YAMLError as e:
                if isinstance(command, commands.Command):
                    name = "command {} (cog {})".format(
                        command.qualified_name, type(command.instance).__name__
                    )
                else:
                    name = "cog {}".format(type(command).__name__)
                raise ValueError("Error parsing !kazhelp YAML for {}".format(name)) from e
            if isinstance(command, commands.Command):
                self._process_checks(doc_data, command, bot)
            command.kaz_structured_help = copy.deepcopy(doc_data)
        self._parse_vars(command, doc_data)
        return doc_data

    def parse_tags(self, text: str, callback: Callable[[str, str], str]):
        """
        Helper method for concrete help formatter routines needing to transform tags.

        Parse tags (IMPORTANT, WARNING, etc.) in a given string (usually one of the structured
        data fields). This method parses out the tags and passes them to the callback, replacing
        the tag with the returned text.

        :param text: Text to parse for tags. Usually should be some structured text field.
        :param callback: function(tag_name: str, tag_contents: str) -> str, returning the new text
            for the tag.
        :return: String with tags substituted according to the callback.
        """
        par_split = text.split('\n\n')
        par_proc = []
        for p in par_split:
            m = self.tags_re.fullmatch(p)
            if m is None:
                par_proc.append(p)
            else:
                par_proc.append(callback(m.group(1).strip(), m.group(2).strip()))
        return '\n\n'.join(par_proc)

    def parse_links(self, text: str, callback: Callable[[str, str], str]):
        """
        Helper method for concrete help formatter routines needing to transform links.

        This method parses out the links. It passes as first argument either 'command' or 'cog',
        and as second argument the target (command or cog name).

        This is provided for single text fields, as this transformation will often need to occur
        after escaping of the original text.

        :param text: Text to parse. Usually should be some structured text field.
        :param callback: function(link_type: str, link_target: str) -> str, returning the new text
            for the link.
        :return: String with link substituted according to the callback.
        """
        def callback_wrapper(match):
            link_type = 'command' if match.group(1) == '!' else 'cog'
            content = match.group(2)
            return callback(link_type, content)
        return self.links_re.sub(callback_wrapper, text)

    def _parse_yaml(self, command: commands.Command):
        START_STRING = '!kazhelp'

        # defaults
        parsed_data = {
            'description': '',
            'jekyll_description': None,
            'brief': None,
            'details': None,
            'parameters': [],
            'examples': [],
            'users': '',
            'channels': ''
        }

        # set up expected fields (cogs vs. commands)
        if isinstance(command, commands.Command):
            fields = self.cmd_fields
        else:  # cog
            parsed_data['contents'] = []
            fields = self.cog_fields

        # parse the help YAML
        raw_help = self.get_raw_help(command)
        if not raw_help or not raw_help.startswith(START_STRING):
            raise NotKazhelpError()
        raw_data = self.yaml.load(raw_help[len(START_STRING):])

        # update parsed_data's default values, but don't overwrite defaults with a None value
        for key, value in raw_data.items():
            if value is not None or key not in parsed_data:
                parsed_data[key] = value

        # validation: check for unknown fields
        unknown_fields = set(parsed_data.keys()) - fields
        if unknown_fields:
            raise ValueError('Unknown YAML fields {!r} for command "{!s}"'
                .format(unknown_fields, command))

        # validation: validate & set defaults for all structures
        self._validate_brief(parsed_data)
        self._validate_params(parsed_data)
        self._validate_examples(parsed_data)

        return parsed_data

    @staticmethod
    def _validate_brief(data: dict):
        if data['brief'] is None:
            data['brief'] = data['description'].split('\n')[0]

    @staticmethod
    def _validate_params(data: dict):
        validated = []
        for p in data['parameters']:
            p_v = {
                # name, description are required: no defaults
                'optional': False,
                'default': '',
                'type': ''
            }
            p_v.update(p)
            if 'description' not in p or 'name' not in p:
                raise KeyError("Parameters must have name and description")
            validated.append(p_v)
        data['parameters'] = validated

    @staticmethod
    def _validate_examples(data: dict):
        validated = []
        for e in data['examples']:
            e_v = {'description': None}  # command is required - don't default it
            e_v.update(e)
            validated.append(e_v)
        data['examples'] = validated

    @staticmethod
    def get_raw_help(command: commands.Command):
        if isinstance(command, commands.Command):
            return command.help.strip() if command.help else None
        else:  # cog
            return inspect.getdoc(command)

    @staticmethod
    def _process_checks(data: dict, command: commands.Command, bot: commands.Bot):
        roles = []
        channels = []
        new_brief = ''
        for check in command.checks:
            # get check data
            try:
                check_type = check.kaz_check_id
            except AttributeError:
                continue
            try:
                check_data = check.kaz_check_data
            except AttributeError:
                check_data = []

            # process check_type
            if check_type is CheckId.U_ROLE or check_type is CheckId.U_ROLE_OR_MODS:
                for role_name in check_data:
                    for server in bot.servers:
                        try:
                            role = get_named_role(server, role_name)
                            roles.append(role.name)
                            break
                        except ValueError:
                            continue
                    else:
                        roles.append(role_name + ' (not found)')
                if check_type is CheckId.U_ROLE_OR_MODS:
                    roles.append('Moderators')
                    roles.append('Administrators')
            elif check_type is CheckId.U_MOD:
                roles = ['Moderators', 'Administrators']
                new_brief = '[MOD ONLY] ' + data['brief']
            elif check_type is CheckId.U_ADMIN:
                roles = ['Administrators']
                new_brief = '[ADMIN ONLY] ' + data['brief']
            elif check_type is CheckId.C_LIST:
                for ch_id in check_data:
                    ch = bot.get_channel(ch_id)  # type: discord.Channel
                    if ch is not None:
                        channels.append('#' + ch.name)
                        break
                    else:
                        channels.append(ch_id + ' (not found)')
            elif check_type is CheckId.C_MOD:
                channels = ['Mod channels']
                new_brief = '[MOD ONLY] ' + data['brief']
            elif check_type is CheckId.C_ADMIN:
                channels = ['Admin channels']
                new_brief = '[ADMIN ONLY] ' + data['brief']

        if roles:
            data['users'] = ', '.join(roles) + '. ' + data['users']
        if channels:
            data['channels'] = ', '.join(channels) + '. ' + data['channels']
        if new_brief:
            data['brief'] = new_brief

    def _parse_vars(self, command: Union[commands.Command, KazCog], data: dict):
        if isinstance(command, commands.Command):
            cog = command.instance
        else:
            cog = command
        cog_name = type(cog).__name__

        # get any cog-specific variables
        if cog_name not in self.cog_vars:
            self.cog_vars[cog_name] = cog.export_kazhelp_vars().copy()

        # generate variables - order is important, self.variables should have priority
        try:
            variables = self.cog_vars[cog_name].copy()
            variables.update(self.variables)
        except KeyError:
            variables = self.variables

        for k in ('description', 'jekyll_description', 'brief', 'details', 'users', 'channels'):
            if data[k]:
                data[k] = self._subst_vars(str(data[k]), variables)
        for p in data['parameters']:
            for k in ('default', 'type', 'description'):
                if p[k]:
                    p[k] = self._subst_vars(str(p[k]), variables)
        for e in data['examples']:
            for k in ('command', 'description'):
                if e[k]:
                    e[k] = self._subst_vars(str(e[k]), variables)

    def _subst_vars(self, s: str, variables: Dict[str, str]):
        def subst_var_inner(m):
            varname = m.group(1)
            if not re.match('[A-Za-z0-9_]', varname[0]):
                return m.group(0)  # ignore invalid variable name
            try:
                return variables[varname]
            except KeyError:
                return m.group(0)
        return self.var_re.sub(subst_var_inner, s)


class DiscordHelpFormatter(commands.HelpFormatter):
    """
    Handles formatting of the help command for KazTron cogs. Format is as defined in the
    CoreHelpParser.
    """
    def __init__(self, parser: CoreHelpParser, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = parser

    def format(self):
        """
        Format command help using kaztron structured help data.

        This method will replace the description, help and brief attributes of the command, if
        structured help data is available. If only text help data is detected, these attributes are
        not modified, and discord.py's built-in help formatter is used instead.

        :return: Formatted help
        """
        self.kaz_preprocess(self.command, self.context.bot)
        return super().format()

    def get_command_signature(self):
        return self._make_title('USAGE') + '\n' + super().get_command_signature()

    def kaz_preprocess(self, command: commands.Command, bot: commands.Bot):
        if command is not bot:  # command or cog - not the bot itself
            try:
                data = self.parser.parse(command, bot)
            except NotKazhelpError:
                logger.debug("Non-!kazhelp for command '{!s}'".format(command))
            else:
                logger.debug("Parsed !kazhelp for command '{!s}'".format(command))
                if isinstance(command, commands.Command):
                    command.description = self._format_links(data['description'])
                    command.brief = self._format_links(data['brief'] or data['description'])
                    command.help = self._format_links(self._build_detailed_info(data))
                    if isinstance(command, commands.GroupMixin):
                        command.help += '\n\n' + self._make_title("SUB-COMMANDS")
                else:  # cog
                    command.__doc__ = self._format_links(
                        data['description'] + '\n\n' + self._build_detailed_info(data)
                    )

    def _build_detailed_info(self, data: dict):
        sections = []
        if data['parameters']:
            sections.append(self._make_title("ARGUMENTS"))
            sections.append(self._build_parameters(data))
        if data['details'] or data['users'] or data['channels']:
            sections.append(self._make_title("DETAILS"))
            if data['details']:
                sections.append(self._format_links(data['details']))
            if data['users']:
                sections.append('MEMBERS: {users}'.format(**data))
            if data['channels']:
                sections.append('CHANNELS: {channels}'.format(**data))
        if data['examples']:
            sections.append(
                self._make_title("EXAMPLES" if len(data['examples']) > 1 else "EXAMPLE")
            )
            sections.append(self._build_examples(data))
        return '\n\n'.join(sections)

    @staticmethod
    def _build_parameters(data: dict):
        strings = []
        for p in data['parameters']:
            p_strings = []
            is_optional = p['optional']

            # name/type
            if is_optional:
                p_strings.append('* [{name}]'.format(**p))
            else:
                p_strings.append('* <{name}>'.format(**p))
            if p['type']:
                p_strings.append('({type})'.format(type=p['type'].strip()))
            p_strings.append(':')

            # description
            if is_optional:
                p_strings.append('Optional.')
                p_strings.append(p['description'].strip())
                if p['default']:
                    p_strings.append('Default: {}'.format(p['default'].strip()))
            else:
                p_strings.append(p['description'].strip())
            strings.append(' '.join(p_strings))
        return '\n\n'.join(strings)

    @staticmethod
    def _build_examples(data: dict):
        strings = []
        for e in data['examples']:
            if 'description' in e and e['description']:
                strings.append('{command}\n    {description}'.format(
                    command=e['command'].strip(),
                    description=e['description'].strip()
                ))
            else:
                strings.append(e['command'].strip())
        return '\n\n'.join(strings)

    @staticmethod
    def _make_title(s: str):
        return '{}\n{}'.format(s, '-'*len(s))

    def _format_links(self, s: str):
        try:
            prefix = get_command_prefix(self.context)
        except AttributeError:  # probably in pre-parse - this will get regen'd on help call
            prefix = '.'
        return self.parser.parse_links(
            s,
            lambda t, target: '`{}{}`'.format(prefix if t == 'command' else '', target)
        )


class JekyllHelpFormatter:
    """
    Handles formatting of the help documentation in a markdown format compatible with Jekyll.
    This class is meant to be used "on-line" (i.e. with the bot connected to Discord) in order to
    be able to resolve live information such as allowed channels.
    """
    slugify_re = re.compile('[^A-Za-z0-9\-]')

    def __init__(self, parser: CoreHelpParser, bot: commands.Bot):
        self.parser = parser
        self.bot = bot
        self.output = None  # type: list
        self.commands = None  # type: list
        self.cog = None  # type: KazCog
        self.section = []
        self.context = None  # type: commands.Context

    def format(self, cog: KazCog, context: commands.Context) -> str:
        self.cog = cog
        self.output = []
        self.commands = []
        self.section = [0]
        self.context = context

        try:
            data = self.parser.parse(cog, self.bot)
        except NotKazhelpError as e:
            data = {
                'brief': None,
                'description': cog.__doc__ or '',
                'jekyll_description': None,
                'contents': []
            }
        self._format_front_matter(data)
        self._format_all_commands(data)

        ret_val = '\n\n'.join(self.output)

        # no need to hold onto these - allow memory to be gc'd
        self.output = None
        self.commands = None

        return ret_val

    def _format_front_matter(self, data: dict):
        parts = []
        parts.append('---')
        parts.append('title: "{title}"'.format(title=type(self.cog).__name__))
        parts.append('last_updated: {date}'.format(date=datetime.now().strftime('%d %B %Y')))
        if data['brief']:
            parts.append('summary: "{brief}"'.format(brief=shorten(data['brief'], 200)))
        parts.append('---\n')
        if data['jekyll_description']:
            parts.append(self._format_md_field(data['jekyll_description']))
        elif data['description']:
            parts.append(self._format_md_field(data['description']))
        self.output.append('\n'.join(parts))

    def _format_all_commands(self, data: dict):
        # explicitly ordered commands
        if data['contents']:
            self._format_iterate_names(data['contents'], self.bot)

        # all other commands
        for command in self.bot.walk_commands():
            if command.instance is self.cog and command not in self.commands:
                self._format_iterate_commands(self.bot)

    def _format_iterate_names(self, name_list: list, parent: CommandOrGroup):
        for name in name_list:
            if isinstance(name, str):
                command = parent.get_command(name)
                if command:
                    self.section[-1] += 1
                    self.commands.append(command)
                    self._format_command(command)
                else:
                    logger.warning("Command {!r} not found".format(name))
            else:  # if 'name' is a dict with subcommands
                command_name, subcommand_struct = next(iter(name.items()))
                command = parent.get_command(command_name)
                if command:
                    self.section[-1] += 1
                    self.commands.append(command)
                    self._format_command(command)

                    self.section.append(0)
                    self._format_iterate_names(subcommand_struct, command)
                    self.section.pop()
                else:
                    logger.warning("Command {!r} not found".format(name))

    def _format_iterate_commands(self, command: CommandOrGroup):
        for c in command.walk_commands():
            if c.instance is self.cog and c not in self.commands:
                self.section[-1] += 1
                self.commands.append(c)
                self._format_command(c)

                warn_msg = "Command not in cog 'contents' list: {} in cog {}" \
                    .format(c.name, type(self.cog).__name__)
                logger.warning(warn_msg)
                self.bot.loop.create_task(
                    self.bot.send_message(self.context.message.channel, warn_msg))

                try:
                    self.section.append(0)
                    self._format_iterate_commands(c)
                except AttributeError:  # not a group - can't walk through subcommands
                    pass
                finally:
                    self.section.pop()

    def _format_command(self, command: commands.Command):
        try:
            data = self.parser.parse(command, self.bot)
            logger.debug("Parsed KazCog YAML help info for command '{!s}'".format(command))
        except NotKazhelpError as e:
            data = None
            logger.debug("Non-!kazhelp docs for command '{!s}'".format(command))

        self.output.append(self._make_cmd_header(command.qualified_name, command.aliases))

        if data:
            if data['jekyll_description']:
                self.output.append(self._format_md_field(data['jekyll_description']))
            else:
                self.output.append(self._format_md_field(data['description']))
            self.output.append('**Usage**: `' + self.get_command_signature(command) + '`')
            self.output.append(self._build_detailed_info(data))
        else:
            if command.description:
                self.output.append('<pre>' + html.escape(command.description) + '</pre>')
            self.output.append('**Usage**: `' + self.get_command_signature(command) + '`')
            if command.help:
                self.output.append('<pre>' + html.escape(command.help.strip()) + '</pre>')

    def get_command_signature(self, command: commands.Command):
        # this is hacky... eh.
        disc_formatter = HelpFormatter(show_check_failure=True)
        disc_formatter.command = command
        disc_formatter.context = self.context
        return disc_formatter.get_command_signature()

    def _build_detailed_info(self, data: dict):
        sections = []
        if data['parameters']:
            sections.append(self._make_header("Arguments"))
            sections.append(self._build_parameters(data))
        if data['details'] or data['users'] or data['channels']:
            sections.append(self._make_header("Details"))
            if data['details']:
                sections.append(self._format_md_field(data['details']))
            if data['users']:
                sections.append(self._make_definition("Members",
                                self._format_md_field(data['users'], tags=False)))
            if data['channels']:
                sections.append(self._make_definition("Channels",
                                self._format_md_field(data['channels'], tags=False)))
        if data['examples']:
            sections.append(
                self._make_header("Examples" if len(data['examples']) > 1 else "Example")
            )
            sections.append(self._build_examples(data))
        return '\n\n'.join(sections)

    def _build_parameters(self, data: dict):
        strings = []
        for p in data['parameters']:
            type_str = ' {type}.'.format(type=p['type'].strip()) if p['type'] else ''

            is_optional = p['optional']
            if is_optional:
                if p['default']:
                    desc = '{type} Optional. {description} Default: {default}'.format(
                        type=type_str,
                        description=self._format_md_field(p['description'], tags=False),
                        default=self._format_md_field(p['default'], tags=False)
                    )
                else:
                    desc = '{type} Optional. {description}'.format(
                        type=type_str,
                        description=self._format_md_field(p['description'], tags=False)
                    )
                strings.append(self._make_definition('[{}]'.format(p['name']), desc))
            else:
                desc = type_str + ' ' + self._format_md_field(p['description'], tags=False)
                strings.append(self._make_definition('&lt;{}&gt;'.format(p['name']), desc))
            strings.append('\n\n')
        return ''.join(strings)

    @staticmethod
    def _build_examples(data: dict):
        strings = []
        for e in data['examples']:
            command = e['command'].strip()
            multiline = '\n' in command
            has_desc = 'description' in e and e['description']

            if multiline and has_desc:
                strings.append('* ```\n{}'.format(
                    indent(command + '\n```\n' + e['description'], '  ')
                ))
            elif multiline and not has_desc:
                strings.append('* ```\n{}'.format(
                    indent(command + '\n```', '  ')
                ))
            elif not multiline and has_desc:
                strings.append('* `{command}` - {description}'.format(**e))
            else:  # not multiline and not has_desc
                strings.append('* `{command}`'.format(**e))
        return '\n'.join(strings)

    def _make_cmd_header(self, title: str, aliases: str):
        return '{} {}. {}\n{{: #{} }}'.format(
            '#' * (len(self.section) + 1),
            '.'.join(str(i) for i in self.section),
            title + ((' (' + ', '.join(aliases) + ')') if aliases else ''),
            self._slugify(title)
        )

    def _slugify(self, text):
        return self.slugify_re.sub('-', text)

    @staticmethod
    def _make_header(title: str):
        return '**{}**'.format(title)

    @staticmethod
    def _make_definition(term: str, definition: str):
        definition_lines = definition.splitlines()
        return "{}\n: {}\n{}".format(
            term.strip(),
            definition_lines[0].strip(),
            '\n'.join(('  ' + l.strip()) for l in definition_lines[1:])
        )

    def _format_md_field(self, text: str, tags=True, links=True):
        text_f = text.strip()
        if tags:
            text_f = self._format_tags(text_f)
        if links:
            text_f = self._format_links(text_f)
        return text_f

    def _format_tags(self, text: str) -> str:
        return self.parser.parse_tags(text, lambda name, contents:
            "{{% include {tag}.html content='{content}' %}}".format(
                tag=name.lower(),
                content=html.escape(contents)
            ))

    def _format_links(self, text: str):
        def callback(link_type: str, link_target: str):
            if link_type == 'command':
                # find the command to get the cog
                for command in self.bot.walk_commands():
                    if command.qualified_name == link_target:
                        return '<a href="./{}.html#{}">{}</a>'.format(
                            type(command.instance).__name__.lower(),
                            self._slugify(link_target),
                            link_target
                        )
                else:
                    # communicate the warning
                    msg = "Link target not found: \"{}\" in cog {}".format(
                        link_target, type(self.cog).__name__
                    )
                    logger.warning(msg)
                    self.bot.loop.create_task(
                        self.bot.send_message(self.context.message.channel, msg))

                    return '<a href="#">{}</a> (error: link target not found)'.format(link_target)
            else:
                return '<a href="./{}.html">{}</a>'.format(link_target.lower(), link_target)
        return self.parser.parse_links(text, callback)
