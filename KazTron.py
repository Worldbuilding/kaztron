#!/usr/bin/env python
# coding=utf8

import sys
import asyncio
import logging

from discord.ext import commands

from kaztron import cfg_defaults
from kaztron.config import get_kaztron_config
from kaztron.utils.logging import setup_logging

# In the loving memory of my time as a moderator of r/worldbuilding network
# To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience.
# (Assuming this is from Kazandaki -- Laogeodritt)


# load configuration
try:
    config = get_kaztron_config(cfg_defaults)
except OSError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)

# setup logging
setup_logging(logging.getLogger(), config)  # setup the root logger
logger = logging.getLogger("kaztron.bootstrap")


if __name__ == '__main__':
    client = commands.Bot(command_prefix='.',
        description='This an automated bot for the /r/worldbuilding discord server',
        pm_help=True)

    # Load extensions
    startup_extensions = config.get("core", "extensions")
    client.load_extension("kaztron.cog.core")
    for extension in startup_extensions:
        # noinspection PyBroadException
        try:
            client.load_extension("kaztron.cog." + extension)
        except Exception as e:
            logger.exception('Failed to load extension {}'.format(extension))
            sys.exit(1)

    # Run the main loop
    loop = asyncio.get_event_loop()
    # noinspection PyBroadException
    try:
        loop.run_until_complete(client.login(config.get("discord", "token")))
        loop.run_until_complete(client.connect())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        logger.info("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.info("Client closed.")
    except:
        logger.exception("Uncaught exception during bot execution")
        logger.error("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.error("Client closed.")
    finally:
        logger.info("Closing event loop...")
        loop.close()
        logger.info("Exiting.")
