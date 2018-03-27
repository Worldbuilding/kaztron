# kaztron
from collections import OrderedDict
from .kazcog import KazCog

__version__ = "2.1a1dev1"

bot_info = {
    "version": __version__,
    "links": OrderedDict()
}
bot_info["links"]["Changelog"] = "https://github.com/Worldbuilding/KazTron/releases/tag/v" + __version__
bot_info["links"]["Manual"] = "http://worldbuilding.network/kaztron/"
bot_info["links"]["GitHub"] = "https://github.com/Worldbuilding/KazTron"
bot_info["links"]["Bugs/Issues"] = "https://github.com/Worldbuilding/KazTron/issues"

cfg_defaults = {
    "discord": {
        "mod_roles": []
    },
    "core": {
        "name": "UnnamedBot",
        "log_level": "INFO",
        "log_file": "kaztron.log"
    }
}
