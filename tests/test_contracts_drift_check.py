"""``contracts drift-check`` temporary-directory and exact-set tests (AC-02).

The read-only gate must write the complete generated artifact set into a
``TemporaryDirectory`` and then compare the exact file set and bytes against
the committed files; a hand edit, an extra generated-path file, or a missing
file must fail the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.cli._main import main
from hermes_pipeline.contracts import toolchain
from hermes_pipeline.contracts.validate import MAX_OUTPUT_BYTES

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal checkout whose committed artifacts mirror ``generated``."""

    def _generated(version: str) -> dict[Path, str]:
        return {
            Path("schemas/test.schema.json"): '{"$id": "x"}\n',
            Path("contracts/openapi.json"): '{"openapi": "3.1.0"}\n',
        }

    monkeypatch.setattr(toolchain, "generated_artifacts", _generated)
    return tmp_path


class _RecordingTemporaryDirectory:
    """Records the created directory and its generated contents.

    The directory itself is cleaned up when the ``with`` block exits; the
    recorded relative-path -> bytes map proves the complete generated set
    was written to disk inside the temporary directory (AC-02).
    """

    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.files: dict[str, bytes] = {}

    class _Session:
        def __init__(self, owner: _RecordingTemporaryDirectory) -> None:
            self._owner = owner
            self._path: Path | None = None

        def __enter__(self) -> Path:
            import tempfile

            self._path = Path(tempfile.mkdtemp(prefix="hermes-contracts-drift-"))
            self._owner.paths.append(self._path)
            return self._path

        def __exit__(self, *exc_info: object) -> None:
            import shutil

            assert self._path is not None
            for committed in sorted(self._path.rglob("*")):
                if committed.is_file():
                    self._owner.files[committed.relative_to(self._path).as_posix()] = (
                        committed.read_bytes()
                    )
            shutil.rmtree(self._path, ignore_errors=True)

    def __call__(self, prefix: str = "") -> _Session:
        return self._Session(self)


def _write_committed(root: Path) -> None:
    (root / "schemas").mkdir(parents=True)
    (root / "schemas" / "test.schema.json").write_bytes(b'{"$id": "x"}\n')
    (root / "contracts").mkdir(parents=True)
    (root / "contracts" / "openapi.json").write_bytes(b'{"openapi": "3.1.0"}\n')


def test_drift_check_writes_the_full_set_into_a_temp_directory(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_committed(fake_root)
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)
    recorder = _RecordingTemporaryDirectory()
    monkeypatch.setattr(toolchain.tempfile, "TemporaryDirectory", recorder)

    assert main(["contracts", "drift-check"]) == 0
    out = capsys.readouterr().out
    assert "contracts drift-check: OK (2 generated file(s)" in out

    assert len(recorder.paths) == 1
    assert recorder.files == {
        "schemas/test.schema.json": b'{"$id": "x"}\n',
        "contracts/openapi.json": b'{"openapi": "3.1.0"}\n',
    }


def test_drift_check_fails_on_a_hand_edited_committed_file(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_committed(fake_root)
    (fake_root / "schemas" / "test.schema.json").write_bytes(
        b'{"$id": "x", "extra": true}\n'
    )
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)

    assert main(["contracts", "drift-check"]) == 1
    out = capsys.readouterr().out
    assert "contracts drift-check: FAIL" in out
    assert "schemas/test.schema.json: differs" in out


def test_drift_check_fails_on_an_extra_committed_file(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_committed(fake_root)
    (fake_root / "schemas" / "extra.schema.json").write_bytes(b'{"$id": "y"}\n')
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)

    assert main(["contracts", "drift-check"]) == 1
    out = capsys.readouterr().out
    assert "contracts drift-check: FAIL" in out
    assert "schemas/extra.schema.json: not generated" in out


def test_drift_check_fails_on_a_missing_committed_file(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_committed(fake_root)
    (fake_root / "contracts" / "openapi.json").unlink()
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)

    assert main(["contracts", "drift-check"]) == 1
    out = capsys.readouterr().out
    assert "contracts drift-check: FAIL" in out
    assert "contracts/openapi.json: missing from the checkout" in out


def test_drift_check_leaves_the_checkout_read_only(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_committed(fake_root)
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)
    before = {
        p: (fake_root / p).read_bytes()
        for p in (
            "schemas/test.schema.json",
            "contracts/openapi.json",
        )
    }
    assert main(["contracts", "drift-check"]) == 0
    after = {
        p: (fake_root / p).read_bytes()
        for p in (
            "schemas/test.schema.json",
            "contracts/openapi.json",
        )
    }
    assert before == after


def test_drift_check_failure_output_is_globally_bounded_and_sanitized(
    fake_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Many hostile path names still produce one bounded diagnostic block."""
    monkeypatch.setattr(toolchain, "_repo_root", lambda: fake_root)
    poisoned_paths = {
        "a" + f"{index:02d}" + "_evil-A\nforged-line\x07canary_drift_123☃" + "x" * 4_000
        for index in range(20)
    }

    def _poisoned_committed_paths(_: Path) -> set[str]:
        return poisoned_paths

    def _missing(_: Path) -> bool:
        return False

    monkeypatch.setattr(
        toolchain, "committed_generated_paths", _poisoned_committed_paths
    )
    monkeypatch.setattr(Path, "is_file", _missing)

    assert main(["contracts", "drift-check"]) == 1
    output = capsys.readouterr().out
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert "(output truncated)" in output
    assert "\nforged-line" not in output
    assert chr(7) not in output
    assert "canary_drift_123" not in output
    assert "\\x0a" in output


def test_committed_generated_paths_discovers_exactly_the_generated_set(
    fake_root: Path,
) -> None:
    _write_committed(fake_root)
    (fake_root / "schemas" / "README.md").write_text("docs\n", encoding="utf-8")
    committed = toolchain.committed_generated_paths(fake_root)
    assert committed == {
        "schemas/test.schema.json",
        "contracts/openapi.json",
    }
