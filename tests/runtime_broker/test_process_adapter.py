from __future__ import annotations

import json
from pathlib import Path

from hermes_pipeline.runtime_broker.ports import RuntimeLaunchRequest
from hermes_pipeline.runtime_broker.process_adapter import ProcessAdapter

_SCRIPT = """\
import json
import sys
from pathlib import Path

Path("argv.json").write_text(json.dumps(sys.argv), encoding="utf-8")
"""


def test_missing_executable_is_unsupported(tmp_path: Path) -> None:
    adapter = ProcessAdapter(executable=str(tmp_path / "missing-cli"))
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-missing"))
    assert handle.status == "UNSUPPORTED"
    assert adapter.last_argv == []


def test_prompt_is_passed_as_print_flag(tmp_path: Path) -> None:
    script = tmp_path / "fake_cli.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    adapter = ProcessAdapter(executable=str(script), cwd=str(work))
    handle = adapter.launch(
        RuntimeLaunchRequest(
            runtime_id="rt-p",
            model="grok-4",
            prompt="Implement a login page",
        )
    )
    assert handle.status == "COMPLETED"
    recorded = json.loads((work / "argv.json").read_text(encoding="utf-8"))
    assert "--model" in recorded
    assert "grok-4" in recorded
    assert recorded[recorded.index("-p") + 1] == "Implement a login page"
    assert "-p" in adapter.last_argv
    assert "Implement a login page" in adapter.last_argv
