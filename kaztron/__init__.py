# kaztron
from collections import OrderedDict
from .kazcog import KazCog

__version__ = "2.1"

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
