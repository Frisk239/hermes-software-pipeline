"""External timeout, cancel, and zero-survivor fencing (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import sys
import threading

import pytest

from hermes_pipeline.runtime_broker._process import run_fenced

pytestmark = pytest.mark.fake_only


def test_timeout_kills_tree_and_reports_zero_survivors() -> None:
    result = run_fenced(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_s=0.3,
        output_bytes=1024,
    )
    assert result.timed_out is True
    assert result.cancelled is False
    assert result.survivors == ()


def test_cancel_is_distinct_from_timeout() -> None:
    cancel = threading.Event()
    cancel.set()
    result = run_fenced(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_s=5.0,
        output_bytes=1024,
        cancel_event=cancel,
    )
    assert result.cancelled is True
    assert result.timed_out is False
    assert result.survivors == ()


def test_orphan_grandchild_is_killed_with_zero_survivors() -> None:
    script = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "time.sleep(30)"
    )
    result = run_fenced(
        [sys.executable, "-c", script],
        timeout_s=0.4,
        output_bytes=1024,
    )
    assert result.timed_out is True
    assert result.survivors == ()


def test_fast_child_completes_without_timeout() -> None:
    result = run_fenced(
        [sys.executable, "-c", "print('ok')"],
        timeout_s=10.0,
        output_bytes=1024,
    )
    assert result.timed_out is False
    assert result.cancelled is False
    assert b"ok" in result.stdout
    assert result.survivors == ()
