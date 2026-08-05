#!/usr/bin/env python3
"""Shared plumbing for the dependency-free bootstrap checkers (slice-00-01).

Both checkers run on the Python standard library only and remain runnable
as standalone scripts; this module only removes duplicated helpers.
"""

from __future__ import annotations

from pathlib import Path
import unicodedata

# Maximum number of issue lines printed before truncation.
MAX_ISSUE_LINES = 100
# Maximum UTF-8 byte length of one sanitized issue message.
MAX_ISSUE_BYTES = 240
# Maximum total UTF-8 byte length of rendered output.
MAX_OUTPUT_BYTES = 8000


def _bounded_sanitize(value: str, max_bytes: int) -> str:
    """Escape control/format characters and truncate to a UTF-8 byte bound."""
    suffix = "..."
    suffix_bytes = len(suffix.encode("utf-8"))
    pieces: list[str] = []
    used = 0
    for char in value:
        category = unicodedata.category(char)
        piece = f"\\u{ord(char):04x}" if category.startswith("C") else char
        encoded_len = len(piece.encode("utf-8"))
        if used + encoded_len > max_bytes - suffix_bytes:
            pieces.append(suffix)
            return "".join(pieces)
        pieces.append(piece)
        used += encoded_len
    return "".join(pieces)


def _truncate_utf8(value: str, max_bytes: int) -> str:
    """Truncate text without splitting a UTF-8 code point."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    suffix = "\n... (output truncated)"
    budget = max_bytes - len(suffix.encode("utf-8"))
    pieces: list[str] = []
    used = 0
    for char in value:
        encoded_len = len(char.encode("utf-8"))
        if used + encoded_len > budget:
            break
        pieces.append(char)
        used += encoded_len
    return "".join(pieces) + suffix


class Reporter:
    """Collects bounded, actionable issue lines.

    Diagnostic fields come from untrusted repository content, so every
    message is sanitized (embedded newlines are escaped) and truncated to
    a fixed maximum length before being stored; rendering additionally
    limits total line count and total output size.
    """

    def __init__(self) -> None:
        self._issues: list[str] = []
        self.scanned = 0

    def issue(self, message: str) -> None:
        self._issues.append(_bounded_sanitize(message, MAX_ISSUE_BYTES))

    @property
    def has_issues(self) -> bool:
        return bool(self._issues)

    def render(self) -> str:
        lines = self._issues[:MAX_ISSUE_LINES]
        if len(self._issues) > MAX_ISSUE_LINES:
            lines.append(
                f"... {len(self._issues) - MAX_ISSUE_LINES} further issue(s) omitted"
            )
        return _truncate_utf8("\n".join(lines), MAX_OUTPUT_BYTES)


def repo_root() -> Path:
    """Repository root is the parent of the scripts/ directory."""
    return Path(__file__).resolve().parent.parent


def fixture_roots(
    root: Path,
    positive_rel: str,
    negative_rel: str,
    required_negative: frozenset[str],
) -> list[tuple[str, Path, bool]]:
    """(name, path, should_pass) pairs for the bootstrap self-test fixtures."""
    fixtures = root / "scripts" / "fixtures"
    expected: list[tuple[str, Path, bool]] = []
    positive = fixtures / positive_rel
    if not positive.is_dir():
        raise ValueError(f"required positive fixture missing: {positive_rel}")
    expected.append(("positive", positive, True))
    negative_root = fixtures / negative_rel
    present = {
        path.name for path in negative_root.glob("*") if path.is_dir()
    }
    missing = required_negative - present
    if missing:
        raise ValueError(
            "required negative fixture(s) missing: " + ", ".join(sorted(missing))
        )
    for negative in sorted(negative_root.glob("*")):
        if negative.is_dir():
            expected.append((negative.name, negative, False))
    return expected


def render_bounded_lines(lines: list[str]) -> str:
    """Render collected subprocess evidence through the same safety bounds."""
    report = Reporter()
    for line in lines:
        report.issue(line)
    return report.render()
