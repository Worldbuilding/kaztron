# kaztron
from collections import OrderedDict
from .kazcog import KazCog
from .scheduler import Scheduler, TaskInstance, task

__release__ = "2.3"  # release stream, usually major.minor only
__version__ = "2.3.4"

bot_info = {
    "version": __version__,
    "links": OrderedDict()
}
bot_info["links"]["Changelog"] = "https://github.com/Worldbuilding/KazTron/releases/tag/v" \
                                 + __version__
bot_info["links"]["Manual"] = "http://worldbuilding.network/kaztron/"
bot_info["links"]["GitHub"] = "https://github.com/Worldbuilding/KazTron"
bot_info["links"]["Bugs/Issues"] = "https://github.com/Worldbuilding/KazTron/issues"

cfg_defaults = {
    "discord": {
        "mod_roles": [],
        "admin_roles": [],
        "mod_channels": [],
        "admin_channels": [],
        "playing": ""
    },
    "core": {
        "name": "UnnamedBot",
        "daemon": False,
        "daemon_pidfile": "kaztron.pid",
        "daemon_username": "",
        "daemon_group": "",
        "daemon_log": "daemon.log",
        "date_format": "%Y-%m-%d",
        "datetime_format": "%Y-%m-%d %H:%M",
        "datetime_seconds_format": "%Y-%m-%d %H:%M:%S"
    },
    "help": {
        "jekyll_manual_title_field": "kaz-manual-title",
        "jekyll_manual_id_field": "kaz-manual-id",
        "jekyll_version_field": "kaz-version",
        "jekyll_category_field": "kaz-cog-category"
    },
    "logging": {
        "level": "INFO",
        "file": "kaztron.log",
        "max_size_kb": 0,
        "max_backups": 0,
        "gzip_backups": True,
        "sub_loggers": {
            "sqlalchemy.engine": "WARN",
            "websockets.protocol": "INFO",
            "discord": "INFO"
        }
    }
}
