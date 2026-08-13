"""Real-runner guards reject before any child process (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = (
    REPO_ROOT / "src" / "hermes_pipeline" / "runtime_broker" / "tools_bootstrap.py"
)
CONTROLLED = (
    REPO_ROOT / "src" / "hermes_pipeline" / "runtime_broker" / "controlled_e2e.py"
)

pytestmark = pytest.mark.fake_only


def _invoke(script: Path, extra: list[str]) -> tuple[int, str]:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW
    child = subprocess.Popen(
        [sys.executable, str(script), *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        creationflags=flags,
    )
    stdout, _stderr = child.communicate()
    return int(child.returncode or 0), stdout


@pytest.mark.parametrize(
    ("script", "extra"),
    [
        (BOOTSTRAP, []),
        (BOOTSTRAP, ["verify"]),
        (BOOTSTRAP, ["selfcheck"]),
        (BOOTSTRAP, ["probe-codex"]),
        (BOOTSTRAP, ["probe-opencode"]),
        (CONTROLLED, []),
    ],
)
def test_missing_authorization_rejects_before_process_creation(
    script: Path, extra: list[str]
) -> None:
    code, stdout = _invoke(script, extra)
    assert code == 1
    payload = json.loads(stdout.strip())
    assert payload == {"ok": False, "code": "DEPENDENCY_UNAVAILABLE"}
