import functools
from collections import OrderedDict
from unittest.mock import mock_open, Mock, MagicMock

import pytest

from kaztron.config import KaztronConfig, SectionView, \
    ReadOnlyError, ConfigKeyError, ConfigConverterError, ConfigNameError

config_defaults = {
    'core': {
        'name': 'KazTron',
        'extensions': [],
        'channel_request': '',
        'daemon': False,
        'daemon_pidfile': 'hippo'
    },
    'default': {
        'key': 'value'
    }
}

config_data = {
    'core': {
        'name': 'ConfigTest',
        'extensions': ['a', 'b', 'c', 'd', 'e'],
        'channel_request': '123456789012345678'
    },
    'discord': {
        'playing': 'status',
        'limit': 5,
        'structure': OrderedDict([('a', 1), ('b', 2), ('c', 3)])
    }
}


class ConfigFixture:
    mock_load = None  # type: Mock
    mock_dump = None  # type: Mock
    mock_open = None  # type: MagicMock
    mock_atomic_write = None  # type: MagicMock
    config = None  # type: KaztronConfig


class SectionFixture:
    mock_config = None  # type: Mock
    section = None  # type: SectionView


def write_test(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        for cc in list(args) + list(kwargs.values()):
            if isinstance(cc, ConfigFixture):
                break
        else:
            raise Exception("Can't find ConfigFixture for write_test decorator")

        if cc.config.read_only:
            with pytest.raises(ReadOnlyError):
                return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return decorator


@pytest.fixture(params=[True, False])
def config(request, mocker) -> ConfigFixture:
    f = ConfigFixture()
    f.mock_load = mocker.patch('json.load', return_value=OrderedDict(config_data))
    f.mock_dump = mocker.patch('json.dump')
    f.mock_open = mocker.patch('builtins.open', mock_open())
    f.mock_atomic_write = mocker.patch('kaztron.driver.atomic_write', mock_open())
    f.config = KaztronConfig(filename='test.json',
                             defaults=config_defaults,
                             read_only=request.param)
    return f


@pytest.fixture
def section_view() -> SectionFixture:
    f = SectionFixture()
    f.mock_config = Mock(spec=KaztronConfig)
    f.mock_config.get.return_value = 'value'
    # noinspection PyTypeChecker
    f.section = SectionView(f.mock_config, 'section')
    return f

@pytest.fixture
def section_view_with_config(config) -> SectionFixture:
    f = SectionFixture()
    f.mock_config = config.config
    f.section = SectionView(f.mock_config, 'core')
    return f


# noinspection PyShadowingNames
class TestConfig:
    # Untested:
    # - Create non-existent files
    # - Write

    def test_init(self, config: ConfigFixture):
        config.mock_load.assert_called_once()
        config.mock_open.assert_called_once_with('test.json')

    def test_underscore_section_protection(self, mocker):
        mocker.patch('json.load', return_value=OrderedDict({
            'core': {'a': 1, 'b': 2, 'c': 3},
            '_illegal': {'d': 4, 'e': 5}
        }))
        mocker.patch('builtins.open', mock_open())
        with pytest.raises(ConfigNameError):
            KaztronConfig(filename='test.json', defaults=config_defaults, read_only=False)

    def test_underscore_key_protection(self, mocker):
        mocker.patch('json.load', return_value=OrderedDict({
            'core': {'a': 1, 'b': 2, '_illegal': 1024, 'c': 3}
        }))
        mocker.patch('builtins.open', mock_open())
        with pytest.raises(ConfigNameError):
            KaztronConfig(filename='test.json', defaults=config_defaults, read_only=False)

    def test_get_section_data(self, config: ConfigFixture):
        d = config.config.get_section_data('discord')
        assert list(d.keys()) == ['playing', 'limit', 'structure']

    def test_get_real_values(self, config: ConfigFixture):
        assert config.config.get('discord', 'playing') == 'status'
        assert config.config.get('discord', 'limit') == 5
        assert config.config.get('discord', 'structure') == \
            OrderedDict([('a', 1), ('b', 2), ('c', 3)])

    def test_get_real_values_with_defaults(self, config: ConfigFixture):
        assert config.config.get('core', 'name') == 'ConfigTest'
        assert config.config.get('core', 'extensions') == ['a', 'b', 'c', 'd', 'e']

    def test_get_default_values(self, config: ConfigFixture):
        assert config.config.get('core', 'daemon') is False
        assert config.config.get('core', 'daemon_pidfile') == 'hippo'

    def test_get_default_passed_in_get(self, config: ConfigFixture):
        assert config.config.get('core', 'asdf', 111) == 111

    def test_get_default_passed_in_get_when_default_exists(self, config: ConfigFixture):
        assert config.config.get('core', 'daemon', 111) is False
        assert config.config.get('core', 'daemon_pidfile', 'giraffe') == 'hippo'

    def test_get_nonexistent_section(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            assert config.config.get('asdf', 'jklx')
        with pytest.raises(KeyError):  # backwards compatibility <2.5.0
            assert config.config.get('asdf', 'jklx')

    def test_get_nonexistent_key(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):  # backwards compatibility <2.5.0
            assert config.config.get('core', 'jklx')
        with pytest.raises(KeyError):  # backwards compatibility <2.5.0
            assert config.config.get('core', 'jklx')

    @write_test
    def test_set_existing_key(self, config: ConfigFixture):
        assert config.config.get('core', 'name') == 'ConfigTest'
        config.config.set('core', 'name', 'Chloe')
        assert config.config.get('core', 'name') == 'Chloe'

    @write_test
    def test_set_and_write(self, config: ConfigFixture):
        config.mock_dump.reset_mock()
        config.config.set('core', 'name', 'Chloe')
        assert config.config.get('core', 'name') == 'Chloe'
        config.config.write()
        assert config.mock_dump.call_count == 1

    @write_test
    def test_set_new_key(self, config: ConfigFixture):
        with pytest.raises(KeyError):
            config.config.get('core', 'flamingo')
        config.config.set('core', 'flamingo', 'pink')
        assert config.config.get('core', 'flamingo') == 'pink'

    @write_test
    def test_set_new_section(self, config: ConfigFixture):
        with pytest.raises(KeyError):
            config.config.get('animals', 'flamingo')
        config.config.set('animals', 'flamingo', 'pink')
        assert config.config.get('animals', 'flamingo') == 'pink'

    def test_set_defaults_existing_section(self, config: ConfigFixture):
        with pytest.raises(KeyError):
            assert config.config.get('core', 'jklx')
            assert config.config.get('core', 'hhhh')
        config.config.set_defaults('core', jklx=77, hhhh=31)
        assert config.config.get('core', 'jklx') == 77
        assert config.config.get('core', 'hhhh') == 31

    def test_set_defaults_new_section(self, config: ConfigFixture):
        with pytest.raises(KeyError):
            assert config.config.get('qwer', 'jklx')
        config.config.set_defaults('qwer', jklx=13, hhhh=88)
        assert config.config.get('qwer', 'jklx') == 13
        assert config.config.get('qwer', 'hhhh') == 88

    def test_strings(self, config: ConfigFixture):
        # just to make sure these don't raise errors - no string checking, can be checked manually
        print(str(config.config))
        print(repr(config.config))


# noinspection PyShadowingNames
class TestConfigObjectApi:
    def test_get_section(self, config: ConfigFixture):
        core1 = config.config.get_section('core')
        core2 = config.config.core
        assert isinstance(core1, SectionView)
        assert core1 == core2  # check both access methods equivalent

    def test_get_section_not_exist(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            config.config.get_section('asdf_jkl')
        with pytest.raises(ConfigKeyError):
            _ = config.config.asdf_jkl

    def test_set_section_view(self, config: ConfigFixture):
        class X(SectionView):
            pass
        config.config.set_section_view('core', X)
        assert isinstance(config.config.core, X)

    def test_get_attribute(self, section_view: SectionFixture):
        assert section_view.section.name == 'value'
        section_view.mock_config.get.assert_called_once_with('section', 'name',
            converter=None, default=None)
        assert section_view.section.flamingo == 'value'
        section_view.mock_config.get.assert_called_with('section', 'flamingo',
            converter=None, default=None)

    def test_get_attribute_not_exist(self, section_view_with_config: SectionFixture):
        with pytest.raises(ConfigKeyError):
            _ = section_view_with_config.section.asdf_jkl
        with pytest.raises(AttributeError):  # backwards compatibility
            _ = section_view_with_config.section.asdf_jkl

    def test_get(self, section_view: SectionFixture):
        assert section_view.section.get('name') == 'value'
        section_view.mock_config.get.assert_called_once_with('section', 'name',
            converter=None, default=None)
        assert section_view.section.get('flamingo') == 'value'
        section_view.mock_config.get.assert_called_with('section', 'flamingo',
            converter=None, default=None)

    def test_get_not_exist(self, section_view_with_config: SectionFixture):
        with pytest.raises(ConfigKeyError):
            section_view_with_config.section.get('asdf_jkl')
        with pytest.raises(AttributeError):  # backwards compatibility
            section_view_with_config.section.get('asdf_jkl')

    def test_set_defaults(self, section_view: SectionFixture):
        defaults = {'a': 1, 'b': 2, 'c': 3}
        section_view.section.set_defaults(a=1, b=2, c=3)
        section_view.mock_config.set_defaults.assert_called_once_with('section', **defaults)

    def test_set_attribute(self, section_view: SectionFixture):
        section_view.section.therapy = 5
        section_view.mock_config.set.assert_called_once_with('section', 'therapy', 5)

    def test_set(self, section_view: SectionFixture):
        section_view.section.set('therapy', 5)
        section_view.mock_config.set.assert_called_once_with('section', 'therapy', 5)

    def test_converters(self, section_view: SectionFixture):
        section_view.section.set_converters('name', lambda x: '_' + x, lambda x: x[1:])
        section_view.section.set_converters('flamingo', lambda x: x + '0', lambda x: x[:-1])

        def get(section, key, default=None, converter=None):
            if converter is None:
                def identity_converter(x):
                    return x
                converter = identity_converter
            return converter('value')
        section_view.mock_config.get.side_effect = get

        # test get by attribute
        assert section_view.section.name == '_value'
        assert section_view.section.flamingo == 'value0'
        assert section_view.section.grapefruit == 'value'

        # test get by method also calls the converters correctly
        for key in ('name', 'flamingo', 'grapefruit'):
            assert section_view.section.get(key) == getattr(section_view.section, key)

        # set attribute
        section_view.section.name = '_dragon0'
        section_view.mock_config.set.assert_called_with('section', 'name', 'dragon0')
        section_view.section.flamingo = '_dragon0'
        section_view.mock_config.set.assert_called_with('section', 'flamingo', '_dragon')
        section_view.section.pumpernickel = '_dragon0'
        section_view.mock_config.set.assert_called_with('section', 'pumpernickel', '_dragon0')

        # set method
        section_view.section.set('flamingo', 'asdf')
        section_view.mock_config.set.assert_called_with('section', 'flamingo', 'asd')

    def test_converter_caching(self, section_view: SectionFixture):
        class Dummy:  # just for identity checking
            pass

        def get_converter(x):
            return Dummy()

        def get_converter2(x):
            return Dummy()

        def set_converter(x):
            return 0

        section_view.section.set_converters('test', get_converter, set_converter)

        def get(section, key, default=None, converter=None):
            if converter is None:
                def identity_converter(x):
                    return x
                converter = identity_converter
            return converter('value')
        section_view.mock_config.get.side_effect = get

        assert get_converter('') is not get_converter('')  # check test fixture gives diff objects
        val1 = section_view.section.test
        assert val1 is section_view.section.test  # same cached value
        assert val1 is section_view.section.get('test')  # same cached value (via get call)

        # not cached if we write
        section_view.section.test = ''
        val2 = section_view.section.test
        assert val1 is not val2  # cache cleared after a write
        assert val2 is section_view.section.test  # but cached on subsequent access

        # not cached if we switch converter
        section_view.section.set_converters('test', get_converter2, set_converter)
        val3 = section_view.section.test
        assert val2 is not val3
        assert val3 is section_view.section.test

    def _raise_error(self, *args):
        raise ValueError(*args)

    def test_converter_get_attribute_error(self, section_view_with_config: SectionFixture):
        section_view_with_config.section.set_converters('name', self._raise_error, None)
        with pytest.raises(ConfigConverterError):
            _ = section_view_with_config.section.name

    def test_converter_get_error(self, section_view_with_config: SectionFixture):
        section_view_with_config.section.set_converters('name', self._raise_error, None)
        with pytest.raises(ConfigConverterError):
            section_view_with_config.section.get('name')

    def test_converter_set_attribute_error(self, section_view_with_config: SectionFixture):
        section_view_with_config.section.set_converters('name', lambda x: '_' + x, self._raise_error)
        with pytest.raises(ConfigConverterError):
            section_view_with_config.section.name = 'abcd'

    def test_converter_set_error(self, section_view_with_config: SectionFixture):
        section_view_with_config.section.set_converters('name', lambda x: '_' + x, self._raise_error)
        with pytest.raises(ConfigConverterError):
            section_view_with_config.section.set('name', 'abcd')
