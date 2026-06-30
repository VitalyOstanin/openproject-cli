"""Tests for ISO 8601 <-> decimal hours conversion."""

import pytest

from openproject_cli.duration import hours_to_iso8601, iso8601_to_hours


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (5, "PT5H"),
        (1.5, "PT1H30M"),
        (0.25, "PT15M"),
        (0, "PT0M"),
        (8, "PT8H"),
        (2.75, "PT2H45M"),
    ],
)
def test_hours_to_iso8601(hours, expected):
    assert hours_to_iso8601(hours) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT5H", 5.0),
        ("PT1H30M", 1.5),
        ("PT15M", 0.25),
        ("P1D", 24.0),
        ("PT90M", 1.5),
        (None, None),
        ("", None),
        ("garbage", None),
    ],
)
def test_iso8601_to_hours(value, expected):
    assert iso8601_to_hours(value) == expected


def test_negative_hours_rejected():
    with pytest.raises(ValueError):
        hours_to_iso8601(-1)


def test_roundtrip():
    for hours in (0.5, 1.0, 3.25, 7.5):
        assert iso8601_to_hours(hours_to_iso8601(hours)) == hours
