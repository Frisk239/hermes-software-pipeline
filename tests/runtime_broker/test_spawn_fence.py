from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker.opencode_adapter import OpenCodeAdapter
from hermes_pipeline.runtime_broker.ports import RuntimeLaunchRequest
from hermes_pipeline.runtime_broker.process_adapter import ProcessAdapter

_SLEEP_CHILD = """\
import time
from pathlib import Path
marker = Path("beat.txt")
deadline = time.time() + 30
while time.time() < deadline:
    marker.write_text(str(time.time()), encoding="utf-8")
    time.sleep(0.05)
"""

_SPAWNER = """\
import subprocess
import sys
import time
subprocess.Popen([sys.executable, "beat.py"])
time.sleep(30)
"""


def test_opencode_timeout_stops_grandchild_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hermes_pipeline.runtime_broker.opencode_adapter as module

    monkeypatch.setattr(module, "_PROMPT_TIMEOUT_S", 0.5)
    marker = tmp_path / "beat.txt"
    child = tmp_path / "beat.py"
    child.write_text(_SLEEP_CHILD, encoding="utf-8")
    script = tmp_path / "fake_opencode.py"
    script.write_text(_SPAWNER, encoding="utf-8")
    adapter = OpenCodeAdapter(str(script), cwd=str(tmp_path))
    handle = adapter.launch(
        RuntimeLaunchRequest(
            runtime_id="rt-tree",
            prompt="go",
            model="x",
        )
    )
    assert handle.status == "FAILED"
    assert adapter.collect("rt-tree").detail == "timeout"
    time.sleep(0.3)
    first = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    time.sleep(0.4)
    second = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    assert first == second


def test_cleaned_env_drops_github_token() -> None:
    from hermes_pipeline.runtime_broker.fence import cleaned_child_env

    env = cleaned_child_env({"PATH": "/bin", "GITHUB_TOKEN": "secret", "GH_TOKEN": "x"})
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert env["PATH"] == "/bin"


def test_signal_cancels_live_process_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hermes_pipeline.runtime_broker.process_adapter as module

    monkeypatch.setattr(module, "_PROMPT_TIMEOUT_S", 5.0)
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    adapter = ProcessAdapter(str(script), cwd=str(tmp_path))

    def _cancel() -> None:
        time.sleep(0.2)
        adapter.signal("rt-cancel")

    worker = threading.Thread(target=_cancel, daemon=True)
    worker.start()
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-cancel", prompt="go"))
    worker.join(timeout=2)
    assert handle.status == "CANCELLED"
