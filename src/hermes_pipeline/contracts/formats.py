"""Deterministic format rules shared by the authoring types and jsonschema.

The frozen ``jsonschema`` installation lacks its optional RFC 3339 checker
(``rfc3339_validator`` is not a dependency), so the toolchain constructs a
fresh deterministic checker for each Schema validator. The single shared rule
below is used by the authoring type (``definitions.UtcTimestamp``) and by the
Schema-side format checker, so both authorities cannot diverge on
``format: date-time`` instances (AC-03, revision 7).

The rule is pure standard library: no timezone database, no third-party
library, and no wall-clock input, so the verdict is byte-identical on every
platform.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from jsonschema import FormatChecker

# RFC 3339 full-date "T" full-time with a mandatory time offset. Both "T"/"t"
# and "Z"/"z" are accepted (the ABNF is case-insensitive); the time offset
# must itself be a valid hour/minute pair.
_RFC3339_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?"
    r"([Zz]|[+-]\d{2}:\d{2})$"
)


def is_rfc3339_datetime(value: object) -> bool:
    """True when ``value`` is an RFC 3339 date-time with a time offset.

    Accepts leap seconds (second ``60``) as RFC 3339 permits and rejects
    impossible calendar dates, hours outside 00-23, minutes outside 00-59,
    and offsets outside ``±23:59``.
    """
    if not isinstance(value, str):
        return False
    match = _RFC3339_RE.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    if second == 60:  # leap second; RFC 3339 permits it
        second = 59
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False
    offset = match.group(8)
    if offset in ("Z", "z"):
        return True
    offset_hour = int(offset[1:3])
    offset_minute = int(offset[4:6])
    return offset_hour <= 23 and offset_minute <= 59


def validate_rfc3339_datetime(value: str) -> str:
    """Raise ``ValueError`` unless ``value`` satisfies the shared rule."""
    if not is_rfc3339_datetime(value):
        raise ValueError("must be an RFC 3339 date-time with a time offset")
    return value


def build_format_checker() -> FormatChecker:
    """Build a fresh deterministic date-time checker (AC-03).

    The checker and the authoring type share ``is_rfc3339_datetime``, so a
    format-violating instance is rejected by both Schema validation and the
    Pydantic model. It is deliberately local to one validator: never mutate
    jsonschema's process-wide default ``FORMAT_CHECKER``.
    """
    checker = FormatChecker()
    checker.checks("date-time", raises=ValueError)(_check_date_time)
    return checker


def _check_date_time(value: Any) -> bool:
    return is_rfc3339_datetime(value)
