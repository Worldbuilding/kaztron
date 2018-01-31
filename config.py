import sys
import json
import logging
import errno

logger = logging.getLogger("kaztron.config")

DEFAULTS = { 'LogLevel': logging.WARNING, 'LogFile': 'kaztron.log' }

token = ""
modteam = []
filterdelete = []
filterwarn = []
warnchannel = ""
deletechannel = ""
outputchannel = ""
welcomechannel = ""
dicechannel = ""
testchannel = ""
authorID = ""
showcase = ""
loglevel = DEFAULTS['LogLevel']
logfile = DEFAULTS['LogFile']

data = {}

# TODO: Seriously? Refactor this to be a data class with I/O methods...
def data_import():
    """
    :raise OSError: Failure to read config.json
    """
    # pls refactor me. end the pain.
    global token, modteam, filterdelete, filterwarn, warnchannel, \
           outputchannel, welcomechannel, dicechannel, testchannel, authorID, \
           showcase, loglevel, logfile

    log_level_map = {
        'CRITICAL' : logging.CRITICAL,
        'ERROR' : logging.ERROR,
        'WARNING' : logging.WARNING,
        'INFO' : logging.INFO,
        'DEBUG' : logging.DEBUG,
    }

    # read config file
    with open("config.json") as json_data:
        config_data = json.load(json_data)

    # prevalidate and store data
    token = config_data["token"]
    modteam = config_data["modteam"]
    warnchannel = config_data["WarnChannel"]
    outputchannel = config_data["OutputChannel"]
    welcomechannel = config_data["WelcomeChannel"]
    dicechannel = config_data["DiceChannel"]
    testchannel = config_data["TestChannel"]
    authorID = config_data["AuthorID"]
    showcase = config_data["ShowcaseChannel"]

    loglevel = log_level_map.get(config_data["LogLevel"].upper(), DEFAULTS['LogLevel'])
    logfile = config_data["LogFile"] if config_data["LogFile"] else DEFAULTS['LogFile']

    # for API compatibility w/rest of kaztron for now - until a proper refactor
    return token, modteam, filterdelete, filterwarn, warnchannel, \
           outputchannel, welcomechannel, dicechannel, testchannel, authorID, \
           showcase

def data_dump(data, path):
    with open(path,"w") as json_data:
        d = json.dump(data,json_data)

def dict_import() -> None:
    """
    Import message filter rules (warn/auto-delete) from `dict.json`. If
    file does not exist, assumes blank rules.

    :raise OSError: Failure to read `dict.json` (except file-not-found, which is
    handled internally)
    """
    global filterdelete, filterwarn
    try:
        with open("dict.json") as json_data:
            dict_data = json.load(json_data)
    except IOError as e: # file doesn't exist?
        if e.errno == errno.ENOENT:
            logger.warn("dict.json does not exist: assuming empty dict")
            dict_data = {}
        else:
            raise

    filterdelete = dict_data.get("delete", [])
    filterwarn = dict_data.get("warn", [])

def dict_dump(delete, warn):
    data_dump({"delete" : delete, "warn" : warn}, "dict.json")

def dict_write() -> (list, list):
    """ Write the message filter rules (warn/auto-delete) to `dict.json`. """
    global filterdelete, filterwarn
    dict_dump(filterdelete, filterwarn)
    dict_import() # reload as written
    return filterdelete, filterwarn
