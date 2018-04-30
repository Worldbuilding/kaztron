import re
from typing import List, Dict, Iterable


def format_list(list_) -> str:
    """
    Format a list as a string for display over Discord, with indices starting from 1.
    """
    digits = len(str(len(list_)))
    fmt = "{0: >" + str(digits) + "d}. {1!s:s}"
    text_bits = []
    text_bits.extend(fmt.format(i+1, item) for i, item in enumerate(list_))
    return '\n'.join(text_bits)


def split_chunks_on(str_: str, maxlen: int, split_char='\n') -> List[str]:
    """
    Split a long string along `split_char` such that all strings are smaller than but as close as
    possible to `maxlen` size.

    Lines that exceed `maxlen` size will not be split.
    """
    len_split = len(split_char)
    lines = str_.split(split_char)
    parts = []
    this_part = []
    running_len = 0
    for line in lines:
        len_line = len(line) + len_split  # can't forget the newline/split_char!
        if len_line + running_len <= maxlen:
            this_part.append(line)
            running_len += len_line
        else:
            parts.append(this_part)
            this_part = [line]
            running_len = len_line
    parts.append(this_part)  # last one, not committed in loop
    return [split_char.join(part) for part in parts]


def split_code_chunks_on(str_: str, maxlen: int, split_char='\n', lang: str=None) -> List[str]:
    """
    Same as :func:`split_chunks_on`, but returns string parts that are all formatted as Markdown
    code blocks, optionally with a language string (the original string must not already be a code
    block!).

    Lines that exceed `maxlen` size will not be split.
    """
    head = '```{}\n'.format(lang if lang else '')
    tail = '\n```'
    len_pad = len(head) + len(tail)
    raw_parts = split_chunks_on(str_, maxlen - len_pad, split_char=split_char)
    return ["{}{}{}".format(head, part, tail) for part in raw_parts]


def natural_truncate(str_: str, maxlen: int, ellipsis_='[…]') -> str:
    """
    If the string is too long, truncate to up to maxlen along word boundaries, with ellipsis_
    appended to the end.
    """
    maxlen_net = maxlen - len(ellipsis_)
    if len(str_) > maxlen:
            trunc_str = str_[:maxlen_net]
            match = re.search(r'\W.*?$', trunc_str)
            if match:
                return str_[:match.start() + 1] + ellipsis_
            else:
                return trunc_str
    else:
        return str_


def none_wrapper(value, default=""):
    """
    Pure laziness! Sometimes this ends up being nice syntactic sugar for code readability.
    """
    return value if value is not None else default


_KWARG_RE = re.compile('\s*([A-Za-z0-9_-]+)=("[^"]+"|[^ ]+)(\s*.*)')


def parse_keyword_args(keywords: Iterable[str], args: str) -> (Dict[str, str], str):
    """
    :param keywords: Valid keywords
    :param args: String argument to parse
    :return: (Dict of kwargs, remaining part of args)
    """
    kwargs = {}
    matches = _KWARG_RE.match(args)
    while matches is not None:
        key, value, args = matches.group(1, 2, 3)
        if key in kwargs:
            raise ValueError("Argument '{}' passed multiple times".format(key))
        elif key in keywords:
            kwargs[key] = value
        else:
            raise ValueError('Unknown keyword `{}`'.format(key))
        matches = _KWARG_RE.match(args)
    return kwargs, args.strip()


