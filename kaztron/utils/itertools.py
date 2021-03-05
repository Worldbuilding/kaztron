from itertools import *
from typing import Iterable, Any


def pairwise(s: Iterable[Any]):
    """ s -> (s0,s1), (s1,s2), (s2, s3), ... """
    a, b = tee(s)
    next(b, None)
    return zip(a, b)


def windowed(s: Iterable[Any], n=2):
    """ s -> (s0, s1, ..., sn), (s1, s2, ..., s(n+1)), (s2, s3, ..., s(n+2), ... """
    iterators = []
    b = s
    for _ in range(n-1):
        a, b = tee(b)
        iterators.append(a)
        next(b, None)
    iterators.append(b)
    return zip(*iterators)
