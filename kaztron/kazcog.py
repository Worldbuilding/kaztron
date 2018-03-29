import functools
import logging

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config, get_runtime_config, KaztronConfig
from kaztron.errors import BotNotReady

logger = logging.getLogger(__name__)


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
    _custom_states = []

    _core_cache = None

    def __init__(self, bot: commands.Bot):
        self._bot = bot
        self.disconnect_task = None
        setattr(self, '_{0.__class__.__name__}__unload'.format(self), self.unload)

    async def on_ready(self):
        """
        If overridden, the super().on_ready() call should occur at the *end* of the method, as it
        marks the cog as fully ready to receive commands.
        """
        self.core.set_cog_ready(self)

    def unload(self):
        try:
            if self.is_ready:
                self.unload_kazcog()
        except:
            logger.exception("Exception occurred during disconnect event in cog {}"
                .format(type(self).__name__))
            # suppress exception - we're shutting down
        finally:
            try:
                self.core.set_cog_shutdown(self)
            except:
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
        # cached since we need this when handling disconnect, after cog potentially unloaded...
        if not self._core_cache:
            self._core_cache = self.bot.get_cog('CoreCog')
        return self._core_cache

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
