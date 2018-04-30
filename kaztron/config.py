import json
import logging
import errno
import copy
from collections import OrderedDict

from kaztron.driver.atomic_write import atomic_write

logger = logging.getLogger("kaztron.config")


class ReadOnlyError(Exception):
    pass


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

    .. attribute:: read_only

        ``bool`` - Whether the config file is read-only. If true, disables :meth:`~.write()` and
        :meth:`~.set`. Read-only property.
    """
    def __init__(self, filename="config.json", defaults=None, read_only=False):
        self.filename = filename
        self._data = {}
        self._defaults = copy.deepcopy(defaults) if defaults else {}
        self._read_only = read_only
        self.read()

    @property
    def read_only(self):
        return self._read_only

    def read(self):
        """
        Read the config file and update all values stored in the object.
        :raises OSError: Error opening file.
        """
        logger.info("config({}) Reading file...".format(self.filename))
        self._data = copy.deepcopy(self._defaults)
        try:
            with open(self.filename) as cfg_file:
                read_data = json.load(cfg_file, object_pairs_hook=OrderedDict)
        except OSError as e:
            if e.errno == errno.ENOENT:  # file not found, just create it
                if not self._read_only:
                    self.write()
                else:
                    raise
            else:  # other failures should bubble up
                raise
        else:
            self._data.update(read_data)

    def write(self, log=True):
        """
        Write the current config data to the configured file.
        :raises OSError: Error opening or writing file.
        :raise ReadOnlyError: configuration is set as read-only
        """
        if self._read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.filename))
        if log:
            logger.info("config({}) Writing file...".format(self.filename))
        with atomic_write(self.filename) as cfg_file:
            json.dump(self._data, cfg_file)

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
        :raise ReadOnlyError: configuration is set as read-only
        """
        if self._read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.filename))
        logger.debug("config:set: file={!r} section={!r} key={!r}"
            .format(self.filename, section, key,))

        try:
            section_data = self._data[section]
        except KeyError:
            logger.debug("Section {!r} not found: creating new section".format(section))
            section_data = self._data[section] = {}

        section_data[key] = copy.deepcopy(value)

    def set_defaults(self, section: str, **kwargs):
        """
        Set configuration values for any keys that are not already defined in the config file.
        The current instance must not be read-only. This method will write to file.

        :param section: The section to set. This method can only set one section at a time.
        :param kwargs: key=value pairs to set, if the key is not already in the config.
        :raises OSError: Error opening or writing file.
        :raise RuntimeError: configuration is set as read-only
        """
        is_changed = False
        for key, value in kwargs.items():
            try:
                self.get(section, key)
            except KeyError:
                self.set(section, key, value)
                is_changed = True

        if is_changed:
            self.write()


def log_level(value: str):
    """
    Converter for KaztronConfig.get() for the core.log_level config
    """
    log_level_map = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
    }
    return log_level_map[value.upper()]


_kaztron_config = None
_runtime_config = None


def get_kaztron_config(defaults=None):
    """
    Get the static configuration object for the bot. Constructs the object if needed.
    """
    global _kaztron_config
    if not _kaztron_config:
        _kaztron_config = KaztronConfig(defaults=defaults, read_only=True)
    return _kaztron_config


def get_runtime_config():
    """
    Get the dynamic (state-persisting) configuration object for the bot. Constructs the object if
    needed.
    """
    global _runtime_config
    if not _runtime_config:
        _runtime_config = KaztronConfig("state.json")
    return _runtime_config
