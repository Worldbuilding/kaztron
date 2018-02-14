#!/usr/bin/env python
# coding=utf8

import sys
import asyncio
import logging

import time

import kaztron
from kaztron import runner
from kaztron.config import get_kaztron_config
from kaztron.utils.logging import setup_logging

# In the loving memory of my time as a moderator of r/worldbuilding network
# To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience.
# (Assuming this is from Kazandaki -- Laogeodritt)


# load configuration
try:
    config = get_kaztron_config(kaztron.cfg_defaults)
except OSError as e:
    print(str(e), file=sys.stderr)
    sys.exit(runner.ErrorCodes.CFG_FILE)

# setup logging
setup_logging(logging.getLogger(), config)  # setup the root logger
logger = logging.getLogger("kaztron.bootstrap")


def reset_backoff(backoff: runner.Backoff, sequence):
    if sequence == backoff.n:  # don't do it if we had a retry in the meantime
        backoff.reset()


if __name__ == '__main__':
    logger.info("Welcome to KazTron v{}, booting up...".format(kaztron.__version__))

    loop = asyncio.get_event_loop()
    try:
        bo_timer = runner.Backoff(initial_time=3.0, base=1.58, max_attempts=12)
        wait_time = 0
        while True:
            reset_task = loop.call_later(wait_time, reset_backoff, bo_timer, bo_timer.n)
            runner.run(loop)
            logger.error("Bot halted unexpectedly.")
            reset_task.cancel()
            wait_time = bo_timer.next()
            logger.info("Restarting bot in {:.1f} seconds...".format(wait_time))
            time.sleep(wait_time)
            logger.info("Restarting bot...")
    except StopIteration:
        logger.error("Too many failed attempts. Exiting.")
        sys.exit(runner.ErrorCodes.RETRY_MAX_ATTEMPTS)
    except KeyboardInterrupt:  # outside of runner.run
        logger.info("Interrupted by user. Exiting.")
    finally:
        logger.info("Exiting.")
        loop.close()
