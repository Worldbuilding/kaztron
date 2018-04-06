import gzip
import logging
import logging.handlers
import os


class LoggingInfo:
    is_setup = False
    cfg_level = logging.INFO
    cfg_packages = {}
    file_handler = None  # type: logging.FileHandler
    console_handler = None  # type: logging.StreamHandler


_logging_info = LoggingInfo()


def setup_logging(logger, config, *, debug=False, console=True):
    from kaztron.config import log_level
    global _logging_info

    if not debug:
        cfg_level = config.get("logging", "level", converter=log_level)
        console_level = max(cfg_level, logging.INFO)  # console never above INFO - avoid clutter
    else:
        cfg_level = console_level = logging.DEBUG

    logger.setLevel(cfg_level)
    _logging_info.cfg_level = cfg_level

    # Specific packages
    cfg_packages = {  # defaults
        "sqlalchemy.engine": "WARN",
        "websockets.protocol": "INFO",
        "discord": "INFO"
    }
    cfg_packages.update(config.get("logging", "tags"))
    _logging_info.cfg_packages = cfg_packages

    for name, s_value in cfg_packages.items():
        logging.getLogger(name).setLevel(max(log_level(s_value), cfg_level))

    # File handler
    fh = logging.handlers.RotatingFileHandler(
        config.get("logging", "file"),
        maxBytes=config.get("logging", "max_size_kb")*1024,
        backupCount=config.get("logging", "max_backups")
    )
    if config.get("logging", "gzip_backups"):
        fh.namer = gzip_namer
        fh.rotator = gzip_rotator
    fh_formatter = logging.Formatter(
        '[%(asctime)s] (%(levelname)s) %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    _logging_info.file_handler = fh

    # Console handler - fixed log level
    if console or debug:
        ch = logging.StreamHandler()
        ch_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s')
        ch.setLevel(console_level)
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)
        _logging_info.console_handler = ch


def get_logging_info() -> LoggingInfo:
    return _logging_info


def gzip_rotator(source, dest):
    with open(source, "rb") as sf:
        with gzip.open(dest, 'wb') as df:
            df.writelines(sf)
    os.remove(source)


def gzip_namer(name):
    return name + '.gz'
