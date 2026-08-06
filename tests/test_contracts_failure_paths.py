"""``contracts`` failure-path tests (AC-10, revision 6).

Every failure path — including malformed Schema-registry input — returns
exit 1 with a UTF-8-byte-limited, control-character-sanitized,
canary-redacted message and never a traceback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.cli._main import main
from hermes_pipeline.contracts import toolchain
from hermes_pipeline.contracts.validate import (
    MAX_OUTPUT_BYTES,
    Reporter,
    cap_utf8,
    sanitize_output,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _malformed_root(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    schema_dir = root / "schemas"
    schema_dir.mkdir(parents=True)
    (schema_dir / "broken.schema.json").write_text(
        "{not valid json\x07", encoding="utf-8"
    )
    return root


def test_malformed_schema_registry_exits_1_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _malformed_root(tmp_path)
    monkeypatch.setattr(toolchain, "_repo_root", lambda: root)
    assert main(["contracts", "check"]) == 1
    output = capsys.readouterr().out
    assert "contracts check: FAIL" in output
    assert "Traceback" not in output
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES


def test_bad_utf8_schema_registry_exits_1_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "checkout"
    schema_dir = root / "schemas"
    schema_dir.mkdir(parents=True)
    (schema_dir / "bad.schema.json").write_bytes(
        bytes([0x7B, 0x22, 0x24, 0x69, 0x64, 0x22, 0x3A, 0x20, 0x22])
        + bytes([0xFF, 0xFE, 0x07])
        + bytes([0x22, 0x7D])
    )
    monkeypatch.setattr(toolchain, "_repo_root", lambda: root)
    assert main(["contracts", "check"]) == 1
    output = capsys.readouterr().out
    assert "contracts check: FAIL" in output
    assert "Traceback" not in output
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert "not valid UTF-8" in output


def test_toolchain_first_import_failure_output_is_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The standard-library import-failure branch must never echo untrusted
    exception payload: fixed safe text, no traceback, no canary, no injected
    control characters, and a bounded byte count (AC-10, REWORK #2)."""
    import builtins

    payload = ("boom" + chr(10) + "canary_closeout_7f3e9a2c4b1d" + chr(7)) * 5000
    real_import = builtins.__import__

    def poisoned(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "hermes_pipeline.contracts.toolchain":
            raise ImportError(payload)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", poisoned)
    assert main(["contracts", "check"]) == 1
    err = capsys.readouterr().err
    assert "contract toolchain unavailable" in err
    assert "Traceback" not in err
    assert "canary_closeout_7f3e9a2c4b1d" not in err
    assert chr(7) not in err
    assert "boom" not in err
    assert len(err.encode("utf-8")) <= MAX_OUTPUT_BYTES


def test_toolchain_inner_import_failure_output_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A post-dispatch ImportError must not echo its untrusted payload."""
    payload = ("boom" + chr(10) + "canary_closeout_7f3e9a2c4b1d" + chr(7)) * 5000
    monkeypatch.setattr(toolchain, "_repo_root", lambda: tmp_path)

    def _poisoned(_: Path) -> tuple[bool, str]:
        raise ImportError(payload)

    monkeypatch.setattr(toolchain, "run_contracts_check", _poisoned)
    assert main(["contracts", "check"]) == 1
    err = capsys.readouterr().err
    assert "contract toolchain unavailable" in err
    assert "Traceback" not in err
    assert "canary_closeout_7f3e9a2c4b1d" not in err
    assert chr(7) not in err
    assert "boom" not in err
    assert chr(10) not in err.removesuffix(chr(10))
    assert len(err.encode("utf-8")) <= MAX_OUTPUT_BYTES


def test_unexpected_validator_error_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(toolchain, "_repo_root", lambda: tmp_path)

    def _boom(root: Path) -> tuple[bool, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(toolchain, "run_contracts_check", _boom)
    assert main(["contracts", "check"]) == 1
    err = capsys.readouterr().err
    assert "contracts check: FAIL (RuntimeError: boom)" in err
    assert "Traceback" not in err


def test_output_is_utf8_byte_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(toolchain, "_repo_root", lambda: tmp_path)

    def _huge(root: Path) -> tuple[bool, str]:
        return False, "x" * 200_000 + "\n"

    monkeypatch.setattr(toolchain, "run_contracts_check", _huge)
    assert main(["contracts", "check"]) == 1
    output = capsys.readouterr().out
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert "(output truncated)" in output


def test_canaries_are_redacted_from_error_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(toolchain, "_repo_root", lambda: REPO_ROOT)

    def _leaky(root: Path) -> tuple[bool, str]:
        return False, "leaked canary_closeout_7f3e9a2c4b1d token\n"

    monkeypatch.setattr(toolchain, "run_contracts_check", _leaky)
    assert main(["contracts", "check"]) == 1
    output = capsys.readouterr().out
    assert "canary_closeout_7f3e9a2c4b1d" not in output
    assert "<redacted>" in output


def test_sanitize_output_replaces_control_characters() -> None:
    assert sanitize_output("a\x07b\x00c\nd\te", frozenset()) == "a\\x07b\\x00c\nd\te"
    assert sanitize_output("tab\tand\nnewline", frozenset()) == "tab\tand\nnewline"
    assert sanitize_output("del\x7f", frozenset()) == "del\\x7f"


def test_reporter_escapes_untrusted_line_breaks_before_rendering() -> None:
    report = Reporter()
    report.issue("schema-id=bad\nforged: diagnostic\tcolumn\x07")
    assert report.render() == "schema-id=bad\\x0aforged: diagnostic\\x09column\\x07"


def test_unreadable_canary_corpus_never_breaks_the_error_reporter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "tests" / "fixtures" / "contracts" / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "broken.json").write_bytes(b"\xff\xfe")
    monkeypatch.setattr(toolchain, "_repo_root", lambda: tmp_path)

    assert main(["contracts", "check"]) == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "contracts check: FAIL" in output
    assert "Traceback" not in output
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES


def test_sanitize_output_redacts_canaries_and_caps_bytes() -> None:
    canaries = frozenset({"canary_closeout_7f3e9a2c4b1d"})
    sanitized = sanitize_output("secret canary_closeout_7f3e9a2c4b1d here", canaries)
    assert "canary_closeout_7f3e9a2c4b1d" not in sanitized
    assert "<redacted>" in sanitized

    big = sanitize_output("é" * 100_000, frozenset())
    assert len(big.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert big.endswith("(output truncated)")


def test_cap_utf8_never_splits_a_multi_byte_character() -> None:
    text = "é" * 50_000
    capped = cap_utf8(text, 1024)
    assert len(capped.encode("utf-8")) <= 1024
    assert "\ufffd" not in capped
    assert capped.endswith("(output truncated)")
