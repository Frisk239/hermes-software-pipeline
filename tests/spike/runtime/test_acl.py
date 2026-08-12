"""Windows descriptor DACL verification (slice-00-05, fixed decision D3).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The exact ACE set is exactly one grant ACE for the current user with ``(F)``
and nothing else. Verification parses ``icacls`` output and rejects any
other subject in the descriptor DACL — including ``Everyone``
(``*S-1-1-0``), ``BUILTIN\\Users`` (``*S-1-5-32-545``), ``SYSTEM``
(``*S-1-5-18``), and ``BUILTIN\\Administrators`` (``*S-1-5-32-544``).
Negative fixtures with an ``Everyone`` or ``SYSTEM`` ACE are rejected.
POSIX uses ``0o600`` plus a mode check.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hermes_pipeline.transport._acl import (
    parse_icacls_aces,
    verify_descriptor_acl_text,
)

CURRENT_SID = "S-1-5-21-2356470663-1900885338-1476189310-1001"
CURRENT_USER = "FRISK239\\a2691"

# Real icacls output shapes (locale-independent parse target).
ICACLS_OK = """\
C:\\state\\descriptor\\runtime.json FRISK239\\a2691:(F)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_EVERYONE_ACE = """\
C:\\state\\descriptor\\runtime.json Everyone:(R)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_SYSTEM_ACE = """\
C:\\state\\descriptor\\runtime.json NT AUTHORITY\\SYSTEM:(F)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_SID_EVERYONE_ACE = """\
C:\\state\\descriptor\\runtime.json *S-1-1-0:(R)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_SID_ADMIN_ACE = """\
C:\\state\\descriptor\\runtime.json *S-1-5-32-544:(F)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_MULTI_ACE = """\
C:\\state\\descriptor\\runtime.json FRISK239\\a2691:(F) NT AUTHORITY\\SYSTEM:(F)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_INHERITED_ACE = """\
C:\\state\\descriptor\\runtime.json FRISK239\\a2691:(I)(F)

已成功处理 1 个文件; 处理 0 个文件时失败
"""

ICACLS_READ_ONLY_ACE = """\
C:\\state\\descriptor\\runtime.json FRISK239\\a2691:(R)

已成功处理 1 个文件; 处理 0 个文件时失败
"""


def test_parse_icacls_ok_single_ace() -> None:
    aces = parse_icacls_aces(ICACLS_OK)
    assert aces == [("FRISK239\\a2691", "F")]


def test_parse_icacls_ignores_header_lines() -> None:
    text = (
        "file: C:\\state\\descriptor\\runtime.json\n"
        "所有者: FRISK239\\a2691\n"
        "用户: FRISK239\\a2691:(F)\n"
    )
    aces = parse_icacls_aces(text)
    assert aces == [("FRISK239\\a2691", "F")]


def test_verify_accepts_exactly_one_current_user_full_control() -> None:
    problems = verify_descriptor_acl_text(ICACLS_OK, CURRENT_SID, CURRENT_USER)
    assert problems == []


def test_verify_accepts_sid_display_form() -> None:
    text = f"C:\\x {CURRENT_SID}:(F)\n"
    assert verify_descriptor_acl_text(text, CURRENT_SID, CURRENT_USER) == []


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("everyone-name", ICACLS_EVERYONE_ACE),
        ("system-name", ICACLS_SYSTEM_ACE),
        ("everyone-sid", ICACLS_SID_EVERYONE_ACE),
        ("administrators-sid", ICACLS_SID_ADMIN_ACE),
        ("multi-ace", ICACLS_MULTI_ACE),
        ("inherited-ace", ICACLS_INHERITED_ACE),
        ("read-only-ace", ICACLS_READ_ONLY_ACE),
    ],
)
def test_verify_rejects_negative_fixtures(name: str, text: str) -> None:
    problems = verify_descriptor_acl_text(text, CURRENT_SID, CURRENT_USER)
    assert problems != [], f"negative fixture {name} must be rejected"


def test_verify_rejects_empty_output() -> None:
    assert verify_descriptor_acl_text("", CURRENT_SID, CURRENT_USER) != []


def test_verify_rejects_missing_full_control_with_other_subject() -> None:
    text = "C:\\x BUILTIN\\Users:(M)\n"
    assert verify_descriptor_acl_text(text, CURRENT_SID, CURRENT_USER) != []


def test_real_apply_and_verify_windows() -> None:
    """Apply and verify the DACL on a real file (Windows only)."""
    if os.name != "nt":
        pytest.skip("Windows-only icacls application")
    from hermes_pipeline.transport._acl import apply_windows_dacl, verify_windows_dacl

    path = Path(os.environ.get("TEMP", ".")) / "hermes-pipeline-acl-check.json"
    path.write_text("{}", encoding="utf-8")
    try:
        problems = apply_windows_dacl(path)
        assert problems == [], problems
        assert verify_windows_dacl(path) == []
    finally:
        import contextlib

        with contextlib.suppress(OSError):
            path.unlink()
