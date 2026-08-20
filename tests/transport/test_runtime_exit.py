from __future__ import annotations

from pathlib import Path

from hermes_pipeline.transport._exitlog import record_runtime_exit


def test_record_runtime_exit_is_bounded(tmp_path: Path) -> None:
    record_runtime_exit(tmp_path, "ValueError / secret=abc")
    text = (tmp_path / "logs" / "last-exit.txt").read_text(encoding="utf-8")
    assert text.strip() == "ValueError"
    assert "secret" not in text
