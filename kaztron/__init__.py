# kaztron
from collections import OrderedDict

__version__ = "2.0.1"

bot_info = {
    "version": __version__,
    "links": OrderedDict()
}
bot_info["links"]["Changelog"] = "https://github.com/Worldbuilding/KazTron/releases/tag/v" + __version__
bot_info["links"]["Manual"] = "https://worldbuilding.github.io/kaztron/"
bot_info["links"]["GitHub"] = "https://github.com/Worldbuilding/KazTron"
bot_info["links"]["Bugs/Issues"] = "https://github.com/Worldbuilding/KazTron/issues"
bot_info["links"]["Spotlight Apps"] = "https://docs.google.com/spreadsheets/d/1YSwx6AJFfOEzIwTAeb71YXEeM0l34mUt6OvyhxTwQis/edit?usp=sharing"

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
