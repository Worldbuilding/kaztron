import functools
import logging
from asyncio import iscoroutinefunction
from typing import Type, Dict, Union

import discord
from discord.ext import commands

from kaztron.utils.embeds import EmbedSplitter
from kaztron.config import KaztronConfig, SectionView
from kaztron.errors import BotNotReady
from kaztron.utils.discord import Limits
from kaztron.utils.strings import natural_split, split_chunks_on

logger = logging.getLogger(__name__)


class KazCog:
    """
    Base class for KazTron. Provides convenience access to various core structures like
    configuration, as well as some bot state control.

    CoreCog installs a global check that only allows commands once on_ready has been called for that
    cog. However, in event handlers like on_message(), this check is not automatically handled:
    you must manually call :meth:`~.is_ready()` to check readiness state.

    :param bot: The discord bot instance that this cog is attached to.
    :param config_section_name: The name of this cog's config section. Should be a valid Python
        identifier. Optional but recommended for new code: if this is not specified, the
        `self.cog_config` and `self.cog_state` convenience properties will not be available.
    :param config_section_view: A custom SectionView for this cog's config section. This is
        provided so you can specify a subclass that has type hinting, converters, defaults, etc.
        configured, which simplifies using the configuration and helps IDE autocompletion.
    :param state_section_view: Same as ``config_section_view``, but for `self.cog_state`.

    :var commands.Bot bot: The bot instance this Cog is loaded into. Available after __init__.
    :var CoreCog core: The CoreCog instance loaded in the bot. Convenience attribute available after
        on_ready is called.
    :var SectionView cog_config: Read-only user configuration for this cog.
    :var SectionView cog_state: Read/write bot state for this cog. You should use this if you are
        using the global state.json state (i.e. you did not call :meth:`~.setup_custom_state` in
        this cog), but use ``self.state`` if you are using a custom state.
    :var KaztronConfig config: Ready-only user configuration for the entire bot.
        Class variable available always. You should normally use ``self.cog_config`` to access your
        cog's specific section, instead of the global config.
    :var KaztronConfig state: Read/write bot state. Class variable available always. This will
        normally point to the global state.json file, but can point to a custom, cog-specific file
        :meth:`~.setup_custom_state` is called.
    ;
    """
    config = None  # type: KaztronConfig
    state = None  # type: KaztronConfig
    _custom_states = []

    _core_cache = None
    _roleman_cache = None

    _ch_out_id = None
    _ch_test_id = None

    def __init__(self,
                 bot: commands.Bot,
                 config_section_name: str=None,
                 config_section_view: Type[SectionView]=None,
                 state_section_view: Type[SectionView]=None):
        self._bot = bot
        self._section = None  # type: str
        self.cog_config = None  # type: SectionView
        self.cog_state = None  # type: SectionView
        self._setup_config(config_section_name, config_section_view, state_section_view)

        setattr(self, '_{0.__class__.__name__}__unload'.format(self), self.unload)
        self._ch_out = discord.Object(self._ch_out_id)  # type: discord.Channel
        self._ch_test = discord.Object(self._ch_test_id)  # type: discord.Channel

        # Detect success/error in cog's on_ready w/o boilerplate from the child class
        def on_ready_wrapper(f):
            @functools.wraps(f)
            async def wrapper(cog):
                try:
                    await f()
                except Exception:
                    cog.core.set_cog_error(cog)
                    # noinspection PyProtectedMember
                    await cog.bot.send_message(
                        discord.Object(id=cog._ch_out_id),
                        "[ERROR] Failed to load cog: {}".format(type(cog).__name__)
                    )
                    raise
                else:
                    cog.core.set_cog_ready(cog)
            return wrapper
        if not iscoroutinefunction(self.on_ready):
            raise discord.ClientException("on_ready must be a coroutine function")
        self.on_ready = on_ready_wrapper(self.on_ready).__get__(self, type(self))

    def _setup_config(self,
                      section: str,
                      config_view: Type[SectionView]=None,
                      state_view: Type[SectionView]=None
                      ):
        self._section = section
        if not self._section:
            return
        if config_view:
            self.config.set_section_view(self._section, config_view)
        if state_view:
            self.state.set_section_view(self._section, state_view)
        self.cog_config = self.config.get_section(self._section)
        self.cog_state = self.state.get_section(self._section)

    @classmethod
    def static_init(cls, config: KaztronConfig, state: KaztronConfig):
        """ Executes one-time class setup. """
        # _config and _state are deprecated, available for backwards compatibility
        cls.config = cls._config = config
        cls._ch_out_id = cls.config.discord.channel_output
        cls._ch_test_id = cls.config.discord.channel_test
        cls.state = cls._state = state

    async def on_ready(self):
        """
        Can be overridden. `super().on_ready()` should be called at the beginning of the method.
        """
        self._ch_out = self.validate_channel(self._ch_out_id)
        self._ch_test = self.validate_channel(self._ch_test_id)

    # noinspection PyBroadException
    def unload(self):
        try:
            if self.is_ready:
                self.unload_kazcog()
        except Exception:
            logger.exception("Exception occurred during disconnect event in cog {}"
                .format(type(self).__name__))
            # suppress exception - we're shutting down
        finally:
            try:
                self.core.set_cog_shutdown(self)
            except Exception:
                logger.exception("Exception occurred during cog shutdown in cog {}"
                    .format(type(self).__name__))
                # suppress exception - we're shutting down

    def unload_kazcog(self):
        """
        Can be overridden to perform some actions at disconnect time. All state files will
        automatically be written and need not be written here (but any updates to the self.state
        should be done to persist it).

        MUST NOT BE A COROUTINE.

        Only executed if cog was in ready state.
        """
        pass

    def export_kazhelp_vars(self) -> Dict[str, str]:
        """
        Can be overridden to make dynamic help variables available for structured help ("!kazhelp").
        Returns a dict mapping variable name to values.

        Variable names must start with a character in the set [A-Za-z0-9_].

        :return: variable name -> value
        """
        return {}

    def setup_custom_state(self, name, defaults=None):
        """
        Set up a custom state file for this cog instance. To be called by the child class.

        The name specified MUST BE UNIQUE BOT-WIDE. Otherwise, concurrency issues will occur as
        multiple KaztronConfig instances cannot handle a single file.

        If you call this method, you should use ``self.state`` instead of ``self.cog_state``.
        Furthermore, the ``state_section_view`` passed at construction has no effect on a custom
        state file, as this cog has the whole file to itself; in this case, you can set up your
        own SectionView objects for each section by calling ``self.state.set_section_view``.

        :param name: A simple alphanumeric name, to be used as part of the filename.
        :param defaults: Defaults for this state file, as taken by the :cls:`KaztronConfig`
            constructor.
        """
        self.state = KaztronConfig('state-' + name + '.json', defaults)
        self.cog_state = None

    def validate_channel(self, id_: str) -> discord.Channel:
        """
        Validate and return the :class:`discord.Channel`, or raise an exception if not found.
        Normally called in :meth:`~.on_ready`.
        :raise ValueError: channel not found
        """
        channel = self.bot.get_channel(id_)
        if channel is None:
            raise ValueError("Channel {} not found".format(id_))
        return channel

    async def send_message(self, destination, contents, *, tts=False,
                           embed: Union[discord.Embed, EmbedSplitter]=None,
                           auto_split=True, split='word'):
        """
        Send a message. This method wraps the :meth:`discord.Client.send_message` method and adds
        automatic message splitting if a message is too long for one line.

        No parsing of Markdown is done for message splitting; this behaviour may break intended
        formatting. For messages which may contain formatting, it is suggested you parse and split
        the message instead of relying on auto-splitting.

        See also :meth:`kaztron.utils.split_chunks_on` and :meth:`kaztron.utils.natural_split` for
        manual control of splitting behaviour. See also :meth:`kaztron.utils.split_code_chunks_on`
        for splitting Markdown code blocks manually.

        See also :cls:`kaztron.utils.embeds.EmbedSplitter` for similar functionality in splitting
        embeds.

        :param destination: he location to send the message (Channel, PrivateChannel, User, etc.)
        :param contents: The content of the message to send. If this is missing, then the ``embed``
            parameter must be present.
        :param tts: Indicates if the message should be sent using text-to-speech.
        :param embed: The rich embed for the content. Also accepts EmbedSplitter instances, for
            automatic splitting - in this case, the EmbedSplitter will be finalized by this method.
        :param auto_split: Whether to auto-split messages that exceed the maximum message length.
        :param split: What to split on: 'word' or 'line'. 'Line' should only be used for messages
            known to contain many line breaks, as otherwise auto-splitting is likely to fail.
        """

        # prepare text contents
        if not contents or not auto_split:
            content_chunks = (contents,)
        else:
            if split == 'word':
                content_chunks = natural_split(contents, Limits.MESSAGE)
            elif split == 'line':
                content_chunks = split_chunks_on(contents, Limits.MESSAGE, split_char='\n')
            else:
                raise ValueError('`split` argument must be \'word\' or \'line\'')

        # prepare embed
        try:
            embed_list = embed.finalize()
        except AttributeError:
            embed_list = (embed,)

        # strategy: output all text chunks before starting to output embed chunks
        # so the last text chunk will have the first embed chunk attached
        # this is because non-split messages usually have the embed appear after the msg -
        # should be fairly rare for both msg and embed to be split
        for content_chunk in content_chunks[:-1]:
            await self.bot.send_message(destination, content_chunk, tts=tts)

        await self.bot.send_message(destination, content_chunks[-1], tts=tts, embed=embed_list[0])

        for embed_chunk in embed_list[1:]:
            await self.bot.send_message(destination, tts=tts, embed=embed_chunk)

    async def send_output(self, contents, *,
                          tts=False, embed: Union[discord.Embed, EmbedSplitter]=None,
                          auto_split=True, split='word'):
        """
        Send a message to the bot output channel.

        Convenience function equivalent to ``self.send_message(self.channel_out, ...)``. See also
        :meth:`.send_message`.
        """
        await self.send_message(self.channel_out, contents, tts=tts, embed=embed,
            auto_split=auto_split, split=split)

    @property
    def core(self):
        # cached since we need this when handling disconnect, after cog potentially unloaded...
        from kaztron.core import CoreCog
        if not self._core_cache:
            self._core_cache = self.bot.get_cog('CoreCog')
        return self._core_cache  # type: CoreCog

    @property
    def rolemanager(self):
        from kaztron.rolemanager import RoleManager
        if not self._roleman_cache:
            self._roleman_cache = self.bot.get_cog('RoleManager')
        return self._roleman_cache  # type: RoleManager

    @property
    def is_ready(self):
        """ Check if the cog is ready. """
        return self.core and self in self.core.ready_cogs

    @property
    def bot(self):
        return self._bot

    @property
    def scheduler(self):
        return self._bot.scheduler

    @property
    def channel_out(self) -> discord.Channel:
        """
        Configured output channel. Before on_ready, returns a discord Object only usable in
        :meth:`discord.Client.send_message` and similar.
        """
        return self._ch_out

    @property
    def channel_test(self) -> discord.Channel:
        """
        Configured test channel. Before on_ready, returns a discord Object only usable in
        :meth:`discord.Client.send_message` and similar.
        """
        return self._ch_test

    @property
    def server(self) -> discord.Server:
        return self._ch_out.server


def ready_only(func):
    """
    Decorator for event handlers (like :meth:`on_member_join`).

    Checks if the cog is ready, and if not, raises a :cls:`~kaztron.errors.BotNotReady` error.

    There is no need to call this for commands, as the global check from the CoreCog will handle
    this automatically.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if args[0].is_ready:
            await func(*args, **kwargs)
        else:
            raise BotNotReady(type(args[0]).__name__)
    return wrapper
