import copy
import inspect
import logging
import re

from ruamel.yaml import YAML

from discord.ext import commands

from .kazcog import KazCog

logger = logging.getLogger(__name__)


class CoreHelpFormatter:
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
    """
    cog_fields = {'description', 'brief', 'details',
                  'parameters', 'examples', 'users', 'channels', 'contents'}
    cmd_fields = {'description', 'brief', 'details',
                  'parameters', 'examples', 'users', 'channels'}
    blocks = ('IMPORTANT', 'WARNING', 'NOTE', 'TIP')
    var_re = re.compile('{{\s*([A-Za-z0-9_-]+)\s*}}')

    def __init__(self, variables=None):
        self.variables = variables or {}
        self.yaml = YAML(typ='safe')

    def parse(self, command: commands.Command, bot: commands.Bot):
        """
        Parse KazTron structured help documentation. This method will replace the description,
        help and brief attributes of the command.
        :param command: Command whose help to parse.
        :return: final parsed data
        :raise ValueError: command does not contain kazhelp-formatted data.
        """
        try:
            doc_data = copy.deepcopy(command.kaz_structured_help)
        except AttributeError:
            doc_data = self._parse_yaml(command)
            # TODO: user/channel checking
            # TODO: contents ordering
            command.kaz_structured_help = copy.deepcopy(doc_data)
        self._parse_vars(doc_data)
        return doc_data

    def _parse_yaml(self, command: commands.Command):
        START_STRING = '!kazhelp'

        # defaults
        parsed_data = {
            'description': '',
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
            raise ValueError('KazCog structured help must start with !kazhelp')
        parsed_data.update(self.yaml.load(raw_help[len(START_STRING):]))

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
            # TODO: mod only mark
            data['brief'] = data['description'].split('\n')[0]

    @staticmethod
    def _validate_params(data: dict):
        validated = []
        for p in data['parameters']:
            p_v = {
                # name, description are required: no defaults
                'optional': 'false',
                'default': None,
                'type': None
            }
            p_v.update(p)
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

    def _parse_vars(self, data: dict):
        for k in ('description', 'brief', 'details', 'users', 'channels'):
            if data[k]:
                data[k] = self._subst_vars(data[k])
        for p in data['parameters']:
            for k in ('default', 'type', 'optional', 'description'):
                if p[k]:
                    p[k] = self._subst_vars(p[k])
        for e in data['examples']:
            for k in ('command', 'description'):
                if e[k]:
                    e[k] = self._subst_vars(e[k])

    def _subst_vars(self, s: str):
        def subst_var_inner(m):
            try:
                return self.variables[m.group(1)]
            except KeyError:
                return m.group(0)
        return self.var_re.sub(subst_var_inner, s)


class DiscordHelpFormatter(commands.HelpFormatter):
    """
    Handles formatting of the help command for KazTron cogs. Format is as defined in the
    KazHelpFormatter.
    """
    def __init__(self, parser: CoreHelpFormatter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = parser

    def format(self):
        self.kaz_preprocess(self.command, self.context.bot)
        return super().format()

    def get_command_signature(self):
        return self._make_title('USAGE') + '\n' + super().get_command_signature()

    def kaz_preprocess(self, command: commands.Command, bot: commands.Bot):
        if command is not bot:  # command or cog - not the bot itself
            try:
                data = self.parser.parse(command, bot)
            except ValueError as e:
                if '!kaz' in e.args[0]:
                    logger.debug("Non-KazCog help for command '{!s}'".format(command))
                else:
                    raise
            else:
                logger.debug("Parsed KazCog YAML help info for command '{!s}'".format(command))
                command.description = data['description']
                command.brief = data['brief'] or data['description']
                command.help = self._build_detailed_info(data)

    def _build_detailed_info(self, data: dict):
        sections = []
        if data['details']:
            sections.append(self._make_title("DETAILS"))
            sections.append(data['details'])
        if data['parameters']:
            sections.append(self._make_title("ARGUMENTS"))
            sections.append(self._build_parameters(data))
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
            strings.append('* {name}'.format(**p))
            if p['type']:
                strings.append(' ({type})'.format(**p))
            strings.append(':')
            if p['optional'] and p['optional'].lower() != 'false':
                strings.append(' Optional. {description} Default: {default}'.format(**p))
            else:
                strings.append(p['description'])
            strings.append('\n')
        return ''.join(strings)

    @staticmethod
    def _build_examples(data: dict):
        strings = []
        for e in data['examples']:
            if 'description' in e and e['description']:
                strings.append('{command}\n    {description}'.format(**e))
            else:
                strings.append(e['command'])
        return '\n\n'.join(strings)

    @staticmethod
    def _make_title(s: str):
        return '{}\n{}'.format(s, '-'*len(s))


class JekyllHelpFormatter:
    """
    Handles formatting of the help documentation in a markdown format compatible with Jekyll.
    This class is meant to be used "on-line" (i.e. with the bot connected to Discord) in order to
    be able to resolve live information such as allowed channels.
    """
    def __init__(self, parser: CoreHelpFormatter):
        self.parser = parser

    def format(self, cog: KazCog) -> str:
        pass
