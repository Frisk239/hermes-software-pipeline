#!/usr/bin/env python3
"""Shared plumbing for the dependency-free bootstrap checkers (slice-00-01).

Both checkers run on the Python standard library only and remain runnable
as standalone scripts; this module only removes duplicated helpers.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

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
    present = {path.name for path in negative_root.glob("*") if path.is_dir()}
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


# --------------------------------------------------------------------------
# .gitignore pattern matching (slice-00-02)
# --------------------------------------------------------------------------
# Governed-file discovery must never scan content that Git itself ignores
# (reference clones, virtual environments, tool caches) while still
# scanning every governed unignored file. Git's check-ignore is not usable
# here: the checkers are dependency-free, offline, and must behave the same
# on fixture roots that are not Git repositories. This module implements
# the .gitignore subset the repository actually uses: comments, trailing
# '!' negation, '/' anchoring, a trailing '/' directory marker, and the
# '*', '?', and '**' wildcards. Escapes and character classes are not part
# of the subset; a pattern using them is treated literally.


@dataclass(frozen=True)
class IgnoreRule:
    """One parsed .gitignore rule."""

    negated: bool
    anchored: bool
    dir_only: bool
    segments: tuple[str, ...]


def parse_gitignore(text: str) -> list[IgnoreRule]:
    """Parse the supported .gitignore subset into ordered rules."""
    rules: list[IgnoreRule] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]
        anchored = line.startswith("/")
        if anchored:
            line = line[1:]
        segments = tuple(segment for segment in line.split("/") if segment)
        if segments:
            rules.append(IgnoreRule(negated, anchored, dir_only, segments))
    return rules


def load_ignore_rules(root: Path) -> list[IgnoreRule]:
    """Read <root>/.gitignore; an absent or unreadable file means no rules.

    Only the root-level ignore file is consulted; nested .gitignore files
    are not part of the supported subset.
    """
    ignore_file = root / ".gitignore"
    try:
        return parse_gitignore(ignore_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


def _segment_regex(pattern: str) -> re.Pattern[str]:
    """Compile one path segment (no '/') into an anchored regex."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _segments_match(pattern: tuple[str, ...], target: tuple[str, ...]) -> bool:
    """Match a pattern segment tuple against a target path tuple, honoring
    '**' as an arbitrary (including empty) run of segments."""

    def match(pi: int, ti: int) -> bool:
        if pi == len(pattern):
            return ti == len(target)
        if pattern[pi] == "**":
            for skip in range(len(target) - ti + 1):
                if match(pi + 1, ti + skip):
                    return True
            return False
        if ti == len(target):
            return False
        return _segment_regex(pattern[pi]).fullmatch(target[ti]) is not None and match(
            pi + 1, ti + 1
        )

    return match(0, 0)


def _rule_matches(rule: IgnoreRule, rel_parts: tuple[str, ...]) -> bool:
    """True when one rule matches rel_parts or any directory prefix of it.

    Anchored patterns match a prefix starting at the root; unanchored
    patterns slide across every position, so ``.venv/`` ignores a virtual
    environment at any depth. A trailing '/' (dir_only) is handled by
    prefix matching, so a directory rule also ignores everything beneath
    it.
    """
    if "**" in rule.segments:
        return _segments_match(rule.segments, rel_parts)
    if rule.anchored:
        if len(rule.segments) > len(rel_parts):
            return False
        return _segments_match(rule.segments, rel_parts[: len(rule.segments)])
    if len(rule.segments) > len(rel_parts):
        return False
    window = len(rule.segments)
    for start in range(len(rel_parts) - window + 1):
        if _segments_match(rule.segments, rel_parts[start : start + window]):
            return True
    return False


def is_path_ignored(rel_path: str, rules: list[IgnoreRule]) -> bool:
    """True when rel_path (POSIX, root-relative) is ignored by the rules.

    Git semantics: the last matching rule wins, and a rule matching a
    directory prefix ignores the whole subtree. Directory-only rules are
    applied to every prefix of the path, so the final path component is
    matched as if it were a directory as well; Git treats a trailing '/'
    pattern as matching both the directory and its contents, which is the
    behavior the checker needs for pruning.
    """
    rel_parts = tuple(part for part in rel_path.split("/") if part)
    if not rel_parts:
        return False
    last_match: IgnoreRule | None = None
    for rule in rules:
        if _rule_matches(rule, rel_parts):
            last_match = rule
    return last_match is not None and not last_match.negated
