import sys
from os import path
import json
import logging
import errno
import copy

logger = logging.getLogger("kaztron.config")

class KaztronConfig:
    """
    Simple interface for KazTron configuration files. This class uses JSON as
    the file backend, but this API could easily be adapted to other languages.

    Expected structure is similar to:

    .. code-block:: json
        {
            "section1": {
                "key1": "any data type",
                "key2": ["a", "list", "is", "fine"]
            },
            "section2": {
                "key1": "flamingo",
                "key2": 3
            }
        }

    :param filename: Filename or filepath of the config file.
    :param defaults: A dict of the same structure as the JSON file above,
        containing default values. Optional. Note that this structure will be
        deep copied.

    .. attribute:: filename

    ``str`` - Filename or filepath for the config file. Read/write.
    """
    def __init__(self, filename="config.json", defaults=None):
        self.filename = filename
        self._data = {}
        self._defaults = copy.deepcopy(defaults) if defaults else {}
        self.read()

    def read(self):
        """
        Read the config file and update all values stored in the object.
        :raises OSError: Error opening file.
        """
        logger.info("config({}) Reading file...".format(self.filename))
        self._data = copy.deepcopy(self._defaults)
        with open(self.filename) as cfg_file:
            read_data = json.load(cfg_file)
        self._data.update(read_data)

    def write(self):
        """
        Write the current config data to the configured file.
        :raises OSError: Error opening file.
        """
        logger.info("config({}) Writing file...".format(self.filename))
        with open(self.filename, "w") as cfg_file:
            d = json.dump(self._data, cfg_file)

    def get_section(self, section: str):
        """
        Retrieve a configuration section as a dict. Modifications to this dict
        will be reflected in this object's loaded config.

        :raises KeyError: section doesn't exist
        """
        logger.debug("config:get_section: file={!r} section={!r} "
            .format(self.filename, section))

        try:
            section = self._data[section]
        except KeyError as e:
            raise KeyError("Can't find section {!r}".format(section)) from e

        return section

    def get(self, section: str, key: str, default=None, converter=None):
        """
        Retrieve a configuration value. The returned value, if it is a
        collection, the returned collection is **not a copy**: modifications to
        the collection may be reflected in the config loaded into memory. If you
        need to modify it without changing the loaded config, make a copy.

        If the value is not found in the config data, then ``default`` is
        returned if it is not None.

        Note that if ``defaults`` were provided at construction time, they take
        precedence over the ``default`` parameter.

        :param section: Section of the config file to retrieve from.
        :param key: Key to obtain.
        :param default: Value to return if the section/key is not found. If this
            is None or not specified, a KeyError is raised instead.
        :param converter: Type or converter function for the value. Called with
            the retrieved value as its single argument. Must not modify the
            original value (e.g. if that value is a collection).

        :raises KeyError: Section/key not found and ``default`` param is ``None``
        """
        logger.debug("config:get: file={!r} section={!r} key={!r}"
            .format(self.filename, section, key))

        try:
            section_data = self._data[section]
        except KeyError as e:
            if default is not None:
                logger.debug("config({}) Section {!r} not found: using default {!r}"
                    .format(self.filename, section, default))
                return default
            else:
                raise KeyError("Can't find section {!r}".format(section)) from e

        try:
            value = section_data[key]
        except KeyError as e:
            if default is not None:
                value = default
            else:
                raise KeyError("config({0}) No key {2!r} in section {1!r}"
                    .format(self.filename, section, key)) from e
        except TypeError as e:
            raise TypeError("config({}) Unexpected configuration file structure"
                .format(self.filename)) from e

        if converter is not None and callable(converter):
            value = converter(value)
        return value

    def set(self, section: str, key: str, value):
        """
        Write a configuration value. Values should always be primitive types
        (int, str, etc.) or JSON-serialisable objects. A deep copy is made of
        the object for storing in the configuration.

        :param section: Section of the config file
        :param key: Key name to store
        :param value: Value to store at the given section and key
        """
        logger.debug("config:set: file={!r} section={!r} key={!r} value={!r}"
            .format(self.filename, section, key, value))

        try:
            section_data = self._data[section]
        except KeyError as e:
            logger.debug("Section {!r} not found: creating new section".format(section))
            section_data = self._data[section] = {}

        section_data[key] = copy.deepcopy(value)


def log_level(value: str):
    """
    Converter for KaztronConfig.get() for the core.log_level config
    """
    log_level_map = {
        'CRITICAL' : logging.CRITICAL,
        'ERROR' : logging.ERROR,
        'WARNING' : logging.WARNING,
        'INFO' : logging.INFO,
        'DEBUG' : logging.DEBUG,
    }
    return log_level_map.get(value.upper(), DEFAULTS['LogLevel'])


def make_kaztron_config(defaults=None):
    return KaztronConfig(defaults=defaults)

def make_filter_config():
    return KaztronConfig("dict.json", defaults={"filter": {"warn": [], "delete": []}})


DEFAULTS = { 'LogLevel': logging.WARNING, 'LogFile': 'kaztron.log' }

token = ""
modteam = []
filterdelete = []
filterwarn = []
warnchannel = ""
deletechannel = ""
outputchannel = ""
welcomechannel = ""
ruleschannel = ""
dicechannel = ""
testchannel = ""
authorID = ""
showcase = ""
showcase_spreadsheet_id = ""
showcase_spreadsheet_range = ""
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
           outputchannel, welcomechannel, ruleschannel, dicechannel, \
           testchannel, authorID, showcase, \
           showcase_spreadsheet_id, showcase_spreadsheet_range, \
           loglevel, logfile

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
    ruleschannel = config_data["RulesChannel"]
    dicechannel = config_data["DiceChannel"]
    testchannel = config_data["TestChannel"]
    authorID = config_data["AuthorID"]
    showcase = config_data["ShowcaseChannel"]
    showcase_spreadsheet_id = config_data["ShowcaseSpreadsheetId"]
    showcase_spreadsheet_range = config_data["ShowcaseSpreadsheetRange"]

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
