# kaztron
from collections import OrderedDict

__version__ = "2.1a1.dev3"

bot_info = {
    "version": __version__,
    "changelog":
        "++ Writing Sprints\n"
        "++ Role Management Commands\n"
        "+ Modnotes: `add` command now allows file and image attachments\n"
        "+ Modtools: Expanded whois to search by name, name+discriminator, or ID\n"
        "+ Spotlight: Added date tracking to queue",
    "links": OrderedDict()
}
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
