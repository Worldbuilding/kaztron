# kaztron
from collections import OrderedDict

__version__ = "1.3b1"

bot_info = {
    "version": __version__,
    "changelog":
        "+ Modnotes\n"
        "+ Spotlight queue management feature\n"
        "+ Refactor of all command UI and usability improvements\n"
        "+ Improved logging facilities\n"
        "+ Internal rewrite for maintainability & reliability\n"
        "x Various bugfixes - see git history",
    "links": OrderedDict()
}
bot_info["links"]["Manual"] = "https://github.com/Kazandaki/KazTron/wiki"
bot_info["links"]["GitHub"] = "https://github.com/Kazandaki/KazTron"
bot_info["links"]["Bugs/Issues"] = "https://github.com/Kazandaki/KazTron/issues"
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
