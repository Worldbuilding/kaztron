#!/usr/bin/env python
# coding=utf8

import asyncio
import logging

logger = logging.getLogger("kaztron.bootstrap")

if __name__ == '__main__':
    # Kinda hacky from the original code, on import this will set up the config + discord bot + logging
    from kaztron.KazTron import client, config

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
