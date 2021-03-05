import json
import logging
import errno
import copy
from collections import OrderedDict
from typing import Type, Dict, Tuple, Sequence, Callable, Any

from kaztron.driver.atomic_write import atomic_write

logger = logging.getLogger("kaztron.config")


class ConfigError(Exception):
    def __init__(self, file, section, key, *args):
        super().__init__(file, section, key, *args)
        self.file = file
        self.section = section
        self.key = key

    def __str__(self):
        return "Error in configuration {}".format(self._get_config_info())

    def _get_config_info(self):
        s = [self.file]
        if self.section:
            s.append(self.section)
        if self.key:
            s.append(self.key)
        return ':'.join(s)


class ReadOnlyError(ConfigError):
    def __init__(self, file, *args):
        super().__init__(file, None, None, *args)

    def __str__(self):
        return "Configuration file {} is open read-only".format(self.file)


class ConfigNameError(ConfigError):
    def __str__(self):
        return "Config sections cannot start with '_' in {}".format(self._get_config_info())


class ConfigKeyError(ConfigError, AttributeError, KeyError):
    def __str__(self):
        return "Configuration key not found: {}".format(self._get_config_info())


class ConfigConverterError(ConfigError):
    def __str__(self):
        return "Error in converter for configuration: {}".format(self._get_config_info())


class KaztronConfig:
    """
    Simple interface for KazTron configuration files. This class uses JSON as
    the file backend, but this API could easily be adapted to other languages.

    Sections can be accessed as attributes (as long as the name is a valid attribute name). If a
    section doesn't exist,

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
        containing default values to set to the config file. Optional.

    .. attribute:: filename

        ``str`` - Filename or filepath for the config file. Read/write.

    .. attribute:: read_only

        ``bool`` - Whether the config file is read-only. If true, disables :meth:`~.write()` and
        :meth:`~.set`. Read-only property.
    """
    def __init__(self, filename="config.json", defaults=None, read_only=False):
        if defaults is None:
            defaults = {}
        self.filename = filename
        self._data = {}
        self._defaults = {}
        self._read_only = read_only
        self._section_view_map = {}
        self.is_dirty = False
        self.read()
        for section, s_data in defaults.items():
            self.set_defaults(section, **s_data)

    @property
    def read_only(self):
        return self._read_only

    def read(self):
        """
        Read the config file and update all values stored in the object.
        :raises OSError: Error opening file.
        :raises JSONDecodeError:
        :raises ConfigNameError: Invalid key name in file
        """
        logger.info("config({}) Reading file...".format(self.filename))
        self._data = {}
        try:
            with open(self.filename) as cfg_file:
                read_data = json.load(cfg_file, object_pairs_hook=OrderedDict)
        except OSError as e:
            if e.errno == errno.ENOENT:  # file not found, just create it
                if not self._read_only:
                    self.is_dirty = True  # force the write
                    self.write()
                else:
                    raise
            else:  # other failures should bubble up
                raise
        else:
            self._data.update(read_data)
            self.is_dirty = False

        for section, sdata in self._data.items():
            if section.startswith('_'):
                raise ConfigNameError(self.filename, section, None)
            for key in sdata.keys():
                if key.startswith('_'):
                    raise ConfigNameError(self.filename, section, key)

    def write(self, log=True):
        """
        Write the current config data to the configured file.
        :raises OSError: Error opening or writing file.
        :raise ReadOnlyError: configuration is set as read-only
        """
        if self._read_only:
            raise ReadOnlyError(self.filename)

        if self.is_dirty:
            if log:
                logger.info("config({}) Writing file...".format(self.filename))
            with atomic_write(self.filename) as cfg_file:
                json.dump(self._data, cfg_file)
            self.is_dirty = False

    def set_section_view(self, section: str, cls: Type['SectionView']):
        """
        Set the SectionView sub-class to use for a particular section.

        This option is made available to allow for sub-classes of SectionView, which can contain
        attribute type annotations for IDE autocompletion as well as specify conversion functions.
        """
        self._section_view_map[section] = cls

    def __getattr__(self, item):
        return self.get_section(item)

    def get_section(self, section: str) -> 'SectionView':
        """
        Retrieve a configuration section view. Modifications to this view
        will be reflected in this object's loaded config.

        If section doesn't exist, a SectionView will be returned that can be used to write to a new
        section (unless the configuration is read-only).

        :param section: Section name to retrieve
        :raises ConfigKeyError: section doesn't exist in a read-only config
        """
        logger.debug("config:get_section: file={!r} section={!r} ".format(self.filename, section))

        if self.read_only and section not in self._data:
            raise ConfigKeyError(self.filename, section, None)

        cls = self._section_view_map.get(section, SectionView)
        return cls(self, section)

    def get_section_data(self, section: str) -> dict:
        """
        Retrieve the raw section data. THIS IS A LIVE DICT - you should not
        make direct changes to this dict.

        This is a low-level method and should generally not be called by cogs.
        :param section: Section name to retrieve
        :raises ConfigKeyError: section doesn't exist
        """
        try:
            return self._data[section]
        except KeyError as e:
            raise ConfigKeyError(self.filename, section, None) from e

    def get(self, section: str, key: str, default=None, converter=None):
        """
        Retrieve a configuration value. The returned value, if it is a
        collection, the returned collection is **not a copy**: modifications to
        the collection may be reflected in the config loaded into memory. If you
        need to modify it without changing the loaded config, make a copy.

        If the value is not found in the config data, then ``default`` is
        returned if it is not None.

        Note that if ``defaults`` were provided at construction time or via :meth:`~.set_defaults`,
        they take precedence over the ``default`` parameter.

        .. deprecated:: v2.2a1
            Use attribute access (e.g. `config.section_name.key_name`) instead.

        :param section: Section of the config file to retrieve from.
        :param key: Key to obtain.
        :param default: Value to return if the section/key is not found. If this
            is None or not specified, a KeyError is raised instead.
        :param converter: Type or converter function for the value. Called with
            the retrieved value as its single argument. Must not modify the
            original value (e.g. if that value is a collection).

        :raises ConfigKeyError: Section/key not found and ``default`` param is ``None``
        :raises TypeError: Section is not a dict
        """
        logger.debug("config:get: file={!r} section={!r} key={!r}"
            .format(self.filename, section, key))

        try:
            value = self._data[section][key]
        except KeyError as e:
            default = self._get_default(section, key, default)
            if default is not None:
                logger.debug("config({}) {!r} -> {!r} not found: using default {!r}"
                    .format(self.filename, section, key, default))
                value = default
            else:
                raise ConfigKeyError(self.filename, section, key) from e
        except TypeError:
            raise TypeError("config({}) Unexpected configuration file structure"
                .format(self.filename))

        if converter is not None and callable(converter):
            try:
                value = converter(value)
            except Exception as e:
                raise ConfigConverterError(self.filename, section, key) from e
        return value

    def _get_default(self, section: str, key: str, default):
        try:
            return self._defaults[section][key]
        except KeyError:
            return default

    def set(self, section: str, key: str, value):
        """
        Write a configuration value. Values should always be primitive types
        (int, str, etc.) or JSON-serialisable objects. A deep copy is made of
        the object for storing in the configuration.

        .. deprecated:: v2.2a1
            Use attribute access (e.g. ``config.section_name.key_name``) instead.

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
        self.is_dirty = True

    def set_defaults(self, section: str, **kwargs):
        """
        Set configuration values for any keys that are not already defined in the config file.
        If the configuration file is not read-only, this will set the configuration and write the
        file; if it is read-only, this will only retain these defaults in-memory.

        .. deprecated:: v2.2a1
            Use attribute access for the section and :meth:`SectionView.set_defaults`, e.g.,
            ``config.section_name.set_defaults(...)``.

        :param section: The section to set. This method can only set one section at a time.
        :param kwargs: key=value pairs to set, if the key is not already in the config.
        :raises OSError: Error opening or writing file.
        :raise ReadOnlyError: configuration is set as read-only
        """
        if not self.read_only:
            for key, value in kwargs.items():
                try:
                    self.get(section, key)
                except KeyError:
                    self.set(section, key, value)
            self.write()
        else:
            if section not in self._defaults:
                self._defaults[section] = {}
            self._defaults[section].update(kwargs)

    def __str__(self):
        return '{!s}{}'.format(self.filename, '[ro]' if self.read_only else '')

    def __repr__(self):
        return 'KaztronConfig<{!s}>'.format(self)


class SectionView:
    """
    Dynamic view for a configuration section. Configuration keys can be retrieved as attributes
    (``view.config_key``) or via the :meth:`get` method; similarly, they can be written by setting
    attributes or via the :meth:`set` method.

    :meth:`set_defaults` allows default values to be set for specific keys. Note that these defaults
    may end up being written to file.

    :meth:`set_converters` allows setting converter functions for getting and setting values. This
    happens implicitly on any converter access, allowing transparent conversion between the JSON
    file data and Python objects.

    Any changes to configuration values in the view will be reflected in the KaztronConfig parent
    object (and thus can be written to file, etc.).

    Changes to configuration can be written in a few ways:

    * Attribute assignment. Note that you have to access the attribute DIRECTLY: if you make deeper
      modifications to the attribute's value (e.g. if it's a dict or list you modify), then it will
      not be detected and the 'dirty' flag will not be set. This will cause the change not to be
      written to file on the next :meth:`write()` call (or automatic write in a KazTron command).
    * Calling :meth:`set`.
    * Using `with section_view_instance:`. A write will be forced at the end of the `with` block,
      allowing you to get around the attribute assignment problem mentioned above. This may be
      less efficient if you are heavily using converters, as it will re-convert every key in the
      configuration.

    Get/set provide additional functionality like defining a default value, if the config key is
    not present, and specifying a converting function/callable.

    Attempting to get a non-existent value, if no default is set, will raise a ConfigKeyError. If
    a converter raises an error (either get or set), a ConfigConverterError is raised.
    """
    def __init__(self, config: KaztronConfig, section: str):
        self.__config = config
        self.__section = section
        self.__converters = {}  # type: Dict[str, Tuple[Callable[[Any], Any], Callable[[Any], Any]]]
        self.__cache = {}  # type: Dict[str, Any]

    def __enter__(self):
        if self.__config.read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.__config.filename))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:  # exception happened - revert any changes
            self.__config.read()
            self.clear_cache()
            return

        # force detecting and converting data, in case changes were to converted data or structures
        for key in self.keys():
            self.set(key, self.get(key))  # forces dirty flag + conversion to happen
        self.write()

    def set_converters(self, key: str, get_converter, set_converter):
        """
        Set a converter to use with specific configuration values. This converter will only be
        applied to this SectionView.

        This method should generally be called in SectionView subclasses' __init__ method, or in
        the __init__ of a cog.

        Converters must have the signatures:

        * ``def get_converter(json_value) -> output_value``
        * ``def set_converter(any_value) -> json_serializable_value``

        :param key: The key to apply the converter to
        :param get_converter: The converter to be used when retrieving data.
        :param set_converter: The converter to be used when setting data.
        """
        if get_converter is not None and not callable(get_converter):
            raise ValueError("Get converter must be callable")
        if set_converter is not None and not callable(set_converter):
            raise ValueError("Set converter must be callable")
        if key in self.__cache:  # clear converted cache
            del self.__cache[key]
        self.__converters[key] = (get_converter, set_converter)

    def set_defaults(self, **kwargs):
        """
        Set configuration values for any keys that are not already defined in the config file.
        This method will write to file, if the config is not read-only.

        This method should generally be called in SectionView subclasses' __init__ method, or in
        the __init__ of a cog.

        Similar in usage to :meth:`KaztronConfig.set_defaults`.
        """
        return self.__config.set_defaults(self.__section, **kwargs)

    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key: str, value):
        if not key.startswith('_'):  # for private and protected values
            self.set(key, value)
        else:
            self.__dict__[key] = value

    def get(self, key: str, default=None):
        """
        Read a configuration value. Usage is similar to :meth:`KaztronConfig.get`.
        :raises ConfigKeyError: Key doesn't exist
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        converter = self.__converters.get(key, (None, None))[0]
        if key in self.__cache:
            logger.debug("{!s}: Read key '{}' from converter cache.".format(self, key))
            return self.__cache[key]
        else:
            value = self.__config.get(self.__section, key, default=default, converter=converter)
            if converter is not None:  # cache converted value
                self.__cache[key] = value
            return value

    def set(self, key: str, value):
        """
        Write a configuration value. Usage is similar to :meth:`KaztronConfig.set`.
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        converter = self.__converters.get(key, (None, lambda x: x))[1]
        if key in self.__cache:  # clear cached converted value
            del self.__cache[key]
        try:
            value = converter(value)
        except Exception as e:
            raise ConfigConverterError(self.__config.filename, self.__section, key) from e
        self.__config.set(self.__section, key, value)

    def keys(self):
        return self.__config.get_section_data(self.__section).keys()

    def clear_cache(self):
        """ Clear the converted value cache. """
        logger.debug("{!s}: Clearing converted value cache.".format(self))
        self.__cache.clear()

    def write(self):
        """ If the in-memory cache of the config file is dirty, write to file. """
        self.__config.write()

    def __str__(self):
        return "{!s}:{}".format(self.__config, self.__section)

    def __repr__(self):
        return "Config<{!s}, data={!r}>"\
            .format(self, self.__config.get_section_data(self.__section))

    def __eq__(self, other):
        return self.__section == other.__section and self.__config is other.__config


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


def get_kaztron_config(defaults=None) -> KaztronConfig:
    """
    Get the static configuration object for the bot. Constructs the object if needed.
    """
    global _kaztron_config
    if not _kaztron_config:
        _kaztron_config = KaztronConfig(defaults=defaults, read_only=True)
    return _kaztron_config


def get_runtime_config() -> KaztronConfig:
    """
    Get the dynamic (state-persisting) configuration object for the bot. Constructs the object if
    needed.
    """
    global _runtime_config
    if not _runtime_config:
        _runtime_config = KaztronConfig("state.json")
    return _runtime_config
