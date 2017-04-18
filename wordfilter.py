# coding=utf8

## Thanks writing this for me, Laogeobunny! ##

import re
import typing


class WordFilter:
    """
    Implements a word filter, capable of loading a set of filter rules and then testing messages
    against those rules.

    Each input rule shall be a literal string to match, except for possible character '%'
    at the beginning or end of the string (or both), which indicates "match only on a word boundary
    at the beginning/end of this string". If no % is specified, then that end of the string can
    match in the middle of a word.

    For example:

    - 'test.match' will match 'test.match', 'greatest.match', 'test.matching', 'test.match, yo!'
        but NOT 'test!match' (the dot is matched literally)
    - '%test.match' will match 'test.match', 'test.matching' but NOT 'greatest.match'
    - 'test.match%' will match 'test.match', 'greatest.match', 'test.match, yo!' but NOT
        'test.matching'
    - '%test.match%' will match 'test.match', 'test.match, yo!', '...test.match?', but NOT
        'greatest.match' or 'test.matching'.

    """

    def __init__(self):
        _rules_raw = []  # :type [str]
        _rules_patterns = []  # :type [str]
        _rules_compiled = []  # :type [typing.Pattern]

    def load_rules(self, rules_list: [str]) -> None:
        """
        Load a list of rules. This list will override the previous rules, and is intended for a
        re-load of the full list from configuration.

        :param rules_list: A list of input rules See the class docstring.
        """
        self._rules_raw = list(rules_list)
        self._rules_patterns = [self._rule2pattern(rule) for rule in rules_list]
        self._rules_compiled = [re.compile('|'.join(self._rules_patterns), re.I)]

    def _rule2pattern(self, str_rule: str) -> str:
        """
        Convert an input rule to a regex pattern string.

        :param str_rule: A single input rule. See the class docstring.
        """
        pat_rule_parts = []

        # identify word and boundaries
        is_bound_start = (str_rule[0] == '%')
        is_bound_end = (str_rule[-1] == '%')
        if is_bound_start and is_bound_end:
            str_word = str_rule[1:-1]
        elif is_bound_start:
            str_word = str_rule[1:]
        elif is_bound_end:
            str_word = str_rule[:-1]
        else:
            str_word = str_rule
        esc_word = re.escape(str_word)

        # build regex
        if is_bound_start:
            pat_rule_parts.append(r'\b')
        pat_rule_parts.append(esc_word)
        if is_bound_end:
            pat_rule_parts.append(r'\b')
        return ''.join(pat_rule_parts)

    def check_message(self, test_string: str) -> str:
        """
        Check a message for a rule match.

        :param test_string: The text message to test for rules matches.
        :return: The first matched string, or `None` if no match
        """
        for pattern in self._rules_compiled:
            match_obj = pattern.search(test_string)
            if match_obj is not None:  # match found for this rule - stop early and return match
                return match_obj.group(0)
        return None

def filter_func(rules,message):
    if rules != []:
        wf = WordFilter()
        wf.load_rules(rules)
        match = wf.check_message(message)
        if match is not None:
            return True
        else:
            return False
    else:
        pass