import functools

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config, get_runtime_config, KaztronConfig
from kaztron.errors import BotNotReady


class KazCog:
    """
    Base class for KazTron. Provides convenience access to various core structures like
    configuration, as well as some bot state control.

    CoreCog installs a global check that only allows commands once on_ready has been called for that
    cog. However, in event handlers like on_message(), this check is not automatically handled:
    you must manually call :meth:`~.is_ready()` to check readiness state.

    :var commands.Bot bot: The bot instance this Cog is loaded into. Available after __init__.
    :var CoreCog core: The CoreCog instance loaded in the bot. Convenience attribute available after
        on_ready is called.
    :var KaztronConfig config: Ready-only user configuration. Class variable available always.
    :var KaztronConfig state: Read/write bot state. Class variable available always.
    """
    _config = get_kaztron_config()
    _state = get_runtime_config()

    def __init__(self, bot: commands.Bot):
        self._bot = bot

    async def on_ready(self):
        """
        If overridden, the super().on_ready() call should occur at the *end* of the method, as it
        marks the cog as fully ready to receive commands.
        """
        self.core.set_cog_ready(self)

    def setup_custom_state(self, name, defaults=None):
        """
        Set up a custom state file for this cog instance. To be called by the child class.

        The name specified MUST BE UNIQUE BOT-WIDE. Otherwise, concurrency issues will occur as
        multiple KaztronConfig instances cannot handle a single file.

        :param name: A simple alphanumeric name, to be used as part of the filename.
        :param defaults: Defaults for this state file, as taken by the :cls:`KaztronConfig`
            constructor.
        """
        self._state = KaztronConfig('state-' + name + '.json', defaults)

    @property
    def core(self):
        return self.bot.get_cog('CoreCog')

    @property
    def is_ready(self):
        """ Check if the cog is ready. """
        return self.core and self in self.core.ready_cogs

    @property
    def bot(self):
        return self._bot

    @property
    def config(self):
        return self._config

    @property
    def state(self):
        return self._state


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
