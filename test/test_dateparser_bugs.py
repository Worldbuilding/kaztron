"""
Test suite for dateparser bugs/regression tests on implemented workarounds.
"""
from datetime import datetime
from kaztron.utils.datetime import parse

import pytest

base1 = datetime(2018, 3, 27, 17, 15, 52, 695093)


@pytest.mark.parametrize('now,datestring,expected', [
    (base1, "6PM UTC", datetime(2018, 3, 27, 18, 0)),    # in the future
    (base1, "6PM UTC-4", datetime(2018, 3, 27, 22, 0)),  # in the future
    (base1, "2PM UTC", datetime(2018, 3, 27, 14, 0)),    # in the future
    (base1, "2PM UTC-4", datetime(2018, 3, 27, 18, 0)),  # in the past
    # across day boundary
    (datetime(2018, 8, 18, 3, 55, 1, 0), "9:57 PM MDT", datetime(2018, 8, 18, 3, 57, 0)),
])
def test_dateparser_default(now: datetime, datestring: str, expected: datetime):
    result = parse(datestring, RELATIVE_BASE=now)
    assert result == expected


@pytest.mark.parametrize('now,datestring,expected', [
    (base1, "6PM UTC", datetime(2018, 3, 27, 18, 0)),      # same day: 6PM today is in the future
    (base1, "6PM UTC-4", datetime(2018, 3, 27, 22, 0)),    # same day: 6PM today is in the future
    (base1, "2PM UTC", datetime(2018, 3, 28, 14, 0)),      # next day: 2PM is in the past today
    (base1, "2PM UTC-4", datetime(2018, 3, 27, 18, 0)),    # same day: 2PM is in the future so OK
    # across day boundary
    (datetime(2018, 8, 18, 3, 55, 1, 0), "9:57 PM MDT", datetime(2018, 8, 18, 3, 57, 0)),
])
def test_dateparser_future(now: datetime, datestring: str, expected: datetime):
    result = parse(datestring, future=True, RELATIVE_BASE=now)
    assert result == expected
