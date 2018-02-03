#!/usr/bin/env python
# coding=utf8

import sys
import asyncio
import logging

logger = logging.getLogger("kaztron.bootstrap")

if __name__ == '__main__':
    # Kinda hacky from the original code, on import this will set up the config + bot + logging
    from kaztron.KazTron import client, config

    # Load extensions
    startup_extensions = config.get("core", "extensions")
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
        logger.info("Loop closed.")
