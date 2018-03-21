import copy
import traceback
import logging

import discord
from kaztron.utils.datetime import format_timestamp


def setup_logging(logger, config):
    from kaztron.config import log_level
    cfg_level = config.get("core", "log_level", converter=log_level)
    logger.setLevel(cfg_level)

    # Specific packages
    cfg_packages = {  # defaults
        "sqlalchemy.engine": "WARN",
        "websockets.protocol": "INFO",
        "discord": "INFO"
    }
    cfg_packages.update(config.get("core", "log_dependencies"))

    for name, s_value in cfg_packages.items():
        logging.getLogger(name).setLevel(max(log_level(s_value), cfg_level))

    # File handler
    fh = logging.FileHandler(config.get("core", "log_file"))
    fh_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s [in %(pathname)s:%(lineno)d]')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    # Console handler - fixed log level
    ch = logging.StreamHandler()
    ch_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s')
    ch.setLevel(max(cfg_level, logging.INFO))  # never below INFO - avoid cluttering console
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)


def message_log_str(message: discord.Message) -> str:
    """
    Convert a :cls:`discord.Message` object to a string suitable for logging or tracing the message.
    Format looks like:

    [2012-01-01 12:34:56] <#channel:username#1234> "Message here"
    """
    return "[{}] <#{!s}:{!s}> {!r}"\
        .format(format_timestamp(message),
                message.channel, message.author, message.content)


def exc_log_str(exception) -> str:
    """
    Format an exception as a "nice" one-liner string (does not include stack trace).
    """
    return "{}: {!s}".format(type(exception).__name__, exception)


def tb_log_str(exception) -> str:
    """
    Format an exception as a full traceback.
    """
    return "".join(traceback.format_exception(None, exception, exception.__traceback__))
