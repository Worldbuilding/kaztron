import pytest
from kaztron.utils.strings import *


list_data = [
    (['a', 'b', 'c'], "1. a\n2. b\n3. c"),  # basic test
    (['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'],  # test number alignment for multi-digit
    " 1. a\n 2. b\n 3. c\n 4. d\n 5. e\n 6. f\n 7. g\n 8. h\n 9. i\n10. j")
]


@pytest.mark.parametrize('x, expect', list_data)
def test_list(x: list, expect: str):
    assert format_list(x) == expect


@pytest.mark.parametrize('s, default, expect',
        ((None, '', ''), (None, 'None', 'None'), ('asdf', 'None', 'asdf')))
def test_none_wrapper(s, default, expect):
    assert none_wrapper(s, default) == expect


class TestSplitChunks:
    MAXLEN = 50

    def test_empty(self):
        s = ''
        assert split_chunks_on(s, self.MAXLEN) == [s]

    def test_short_line(self):
        s = 'This is a short line.'
        assert split_chunks_on(s, self.MAXLEN) == [s]

    def test_short_lines(self):
        s = 'This is a short line.\nThis is another one.\nYup.'  # 49 chars
        assert split_chunks_on(s, self.MAXLEN) == [s]

    def test_split_two(self):
        s = 'This is a short line.\nThis is another one.\nNow this line should go over the edge.'
        e = ['This is a short line.\nThis is another one.',
             'Now this line should go over the edge.']
        assert split_chunks_on(s, self.MAXLEN) == e

    def test_split_three(self):
        s = 'This is a short line.\nThis is another one.\n' \
            'Now this line should go over the edge.\nAnd this one should again push us to 3 msgs.'
        e = ['This is a short line.\nThis is another one.',
             'Now this line should go over the edge.',
             'And this one should again push us to 3 msgs.']
        assert split_chunks_on(s, self.MAXLEN) == e

    def test_split_just_over(self):
        # just over 50 characters
        s = 'This is a short line.\nThis is another one.\nA pearl.'
        e = ['This is a short line.\nThis is another one.', 'A pearl.']
        assert split_chunks_on(s, self.MAXLEN) == e

    def test_long_line(self):
        s = 'This is a single line that is far too long, but still should not get split.'
        e = [s]
        assert split_chunks_on(s, self.MAXLEN) == e


class TestSplitCodeChunks:
    MAXLEN = 50
    LANG = 'python'

    def test_empty(self):
        s = ''
        e = ['```python\n\n```']
        assert split_code_chunks_on(s, self.MAXLEN, lang=self.LANG) == e

    def test_short_line(self):
        s = 'This is a short line.'
        e = ['```python\nThis is a short line.\n```']
        assert split_code_chunks_on(s, self.MAXLEN, lang=self.LANG) == e

    def test_short_lines(self):
        s = 'This is a short line.\nAnd another.'
        e = ['```python\nThis is a short line.\nAnd another.\n```']
        assert split_code_chunks_on(s, self.MAXLEN, lang=self.LANG) == e

    def test_split_three(self):
        # the last two lines are 45 characters long: they would fit without the code block frame but
        # not fit with the frame. So this test is checking that the frame size is accounted for.
        s = 'Short line.\nAnother one.\n' \
            'Go over the edge.\nAnd this one should again.'
        e = ['```python\nShort line.\nAnother one.\n```',
             '```python\nGo over the edge.\n```',
             '```python\nAnd this one should again.\n```']
        assert split_code_chunks_on(s, self.MAXLEN, lang=self.LANG) == e

    def test_split_just_over(self):
        # just over 50 characters after the frame
        s = 'This is a short line.\nIs another one.'
        e = ['```python\nThis is a short line.\n```',
             '```python\nIs another one.\n```']
        assert split_code_chunks_on(s, self.MAXLEN, lang=self.LANG) == e


class TestNaturalSplit:
    MAXLEN = 50

    def test_empty(self):
        s = ''
        e1 = ''
        e2 = ['']
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_short(self):
        s = 'Lorem ipsum dolor sit amet.'
        e1 = s
        e2 = [s]
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_just_too_long_with_ellipsis(self):
        s = 'Lorem ipsum dolor sit amet, sed do eiusmod asdf.'
        e1 = 'Lorem ipsum dolor sit amet, sed do eiusmod asdf.'
        e2 = [e1]
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_split_two(self):
        s = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.'
        e1 = 'Lorem ipsum dolor sit amet, consectetur […]'
        e2 = [e1, "[…] adipiscing elit."]
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_split_three(self):
        s = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, ' \
            'sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        e1 = 'Lorem ipsum dolor sit amet, consectetur […]'
        e2 = [e1, "[…] adipiscing elit, sed do eiusmod tempor […]",
              "[…] incididunt ut labore et dolore magna aliqua."]
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_split_three_no_ellipsis(self):
        s = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, ' \
            'sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        e1 = 'Lorem ipsum dolor sit amet, consectetur adipiscing'
        e2 = [e1, "elit, sed do eiusmod tempor incididunt ut labore",
              "et dolore magna aliqua."]
        assert natural_truncate(s, self.MAXLEN, '') == e1
        assert natural_split(s, self.MAXLEN, '') == e2

    def test_split_two_multiple_paragraphs(self):
        s = 'Lorem ipsum dolor sit amet,\n\nconsectetur adipiscing elit.'
        e1 = 'Lorem ipsum dolor sit amet,\n\nconsectetur […]'
        e2 = [e1, "[…] adipiscing elit."]
        assert natural_truncate(s, self.MAXLEN) == e1
        assert natural_split(s, self.MAXLEN) == e2

    def test_split__corner__before_space(self):
        s = 'asdf asdf exclude'
        e1 = 'asdf asdf […]'
        e2 = [e1, '[…] exclude']
        assert natural_truncate(s, 13) == e1
        assert natural_split(s, 13) == e2

    def test_split__corner__after_space(self):
        s = 'asdf asdf exclude'
        e1 = 'asdf asdf […]'
        e2 = [e1, '[…] exclude']
        assert natural_truncate(s, 14) == e1
        assert natural_split(s, 14) == e2

    def test_split__corner__before_nonword(self):
        s = 'asdf asdf. exclude'
        e1 = 'asdf […]'
        e2 = [e1, '[…] asdf. […]', '[…] exclude']
        assert natural_truncate(s, 13) == e1
        assert natural_split(s, 13) == e2

    def test_split__corner__after_nonword(self):
        s = 'asdf asdf. exclude'
        e1 = 'asdf asdf. […]'
        e2 = [e1, '[…] exclude']
        assert natural_truncate(s, 14) == e1
        assert natural_split(s, 14) == e2

    def test_split__corner__after_nonword_nospace(self):
        s = 'asdf asdf.exclude'
        e1 = 'asdf asdf. […]'
        e2 = [e1, '[…] exclude']
        assert natural_truncate(s, 14) == e1
        assert natural_split(s, 14) == e2


class TestKeywordParser:
    keys = ('asdf', 'jkl', 'guu')

    def test_no_keywords(self):
        s = 'flamingo watermelon dragonfruit'
        e_k = {}
        e_a = s
        k, a = parse_keyword_args(self.keys, s)
        assert k == e_k
        assert a == e_a

    def test_no_keywords__keyword_in_string(self):
        s = 'asdf flamingo jkl watermelon dragonfruit'
        e_k = {}
        e_a = s
        k, a = parse_keyword_args(self.keys, s)
        assert k == e_k
        assert a == e_a

    def test_no_keywords__keyword_like_in_string(self):
        s = 'asdf flamingo jkl="bluh" watermelon dragonfruit'
        e_k = {}
        e_a = s
        k, a = parse_keyword_args(self.keys, s)
        assert k == e_k
        assert a == e_a

    def test_valid_keywords(self):
        s = 'asdf="ping pong" jkl=hing flamingo watermelon dragonfruit'
        e_k = {'asdf': '"ping pong"', 'jkl': "hing"}
        e_a = "flamingo watermelon dragonfruit"
        k, a = parse_keyword_args(self.keys, s)
        assert k == e_k
        assert a == e_a

    def test_invalid_keywords(self):
        s = 'asdf="hing" nup="should break" jkl=\'hong\' flamingo watermelon dragonfruit'
        with pytest.raises(ValueError):
            parse_keyword_args(self.keys, s)
        s = 'nup="should break" jkl=\'hong\' flamingo watermelon dragonfruit'
        with pytest.raises(ValueError):
            parse_keyword_args(self.keys, s)
        s = 'asdf="hing" nup="should break" flamingo watermelon dragonfruit'
        with pytest.raises(ValueError):
            parse_keyword_args(self.keys, s)

    def test_repeated_keywords(self):
        s = 'asdf="hing" jkl=\'hong\' asdf="this is bad" flamingo watermelon dragonfruit'
        with pytest.raises(ValueError):
            parse_keyword_args(self.keys, s)

    def test_regression__newlines(self):
        s = 'asdf="ping pong" jkl=blah flamingo watermelon\n\ndragonfruit kiwi'
        e_k = {'asdf': '"ping pong"', 'jkl': 'blah'}
        e_a = "flamingo watermelon\n\ndragonfruit kiwi"
        k, a = parse_keyword_args(self.keys, s)
        assert k == e_k
        assert a == e_a
