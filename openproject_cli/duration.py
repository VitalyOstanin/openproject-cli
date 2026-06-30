"""Conversion between decimal hours and ISO 8601 durations.

OpenProject stores time-entry durations as ISO 8601 strings (``PT5H``,
``PT1H30M``). The CLI accepts and displays plain decimal hours, so these two
helpers translate between the two representations.
"""

from __future__ import annotations

import re

_ISO_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def hours_to_iso8601(hours: float) -> str:
    """Convert decimal hours to an ISO 8601 duration, e.g. 1.5 -> ``PT1H30M``."""
    if hours < 0:
        raise ValueError("hours must be non-negative")
    total_minutes = round(hours * 60)
    whole_hours, minutes = divmod(total_minutes, 60)
    parts = "PT"
    if whole_hours:
        parts += f"{whole_hours}H"
    if minutes or not whole_hours:
        parts += f"{minutes}M"
    return parts


def iso8601_to_hours(value: str | None) -> float | None:
    """Convert an ISO 8601 duration to decimal hours; None passes through."""
    if not value:
        return None
    match = _ISO_RE.match(value)
    if not match:
        return None
    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return days * 24 + hours + minutes / 60 + seconds / 3600
