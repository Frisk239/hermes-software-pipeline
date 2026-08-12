"""Stale-descriptor cleanup and token rotation (slice-00-05, AC-04/AC-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A stale descriptor from a killed runtime is cleaned via the start-identity
algorithm before a new runtime starts; a live runtime's descriptor is
never removed; the token rotates only when the runtime process starts.
"""

from __future__ import annotations

import time
from pathlib import Path

from hermes_shim._descriptor import is_stale
from tests.spike.runtime._harness import (
    provision,
    start_runtime,
    stop_runtime,
    wait_for_descriptor,
    wait_runtime_ready,
)


def test_stale_descriptor_removed_before_fresh_start(tmp_path: Path) -> None:
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    descriptor_path = tmp_path / "descriptor" / "runtime.json"
    assert descriptor_path.is_file()
    # Kill the runtime; its descriptor is now stale (process gone).
    stop_runtime(proc, tmp_path)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not is_stale(tmp_path):
        time.sleep(0.25)
    assert is_stale(tmp_path)
    # A fresh start cleans the stale descriptor and writes a new one.
    proc2, document2 = _start_and_wait(tmp_path)
    assert int(document2["pid"]) != int(document["pid"])
    assert document2["start_identity"] != document["start_identity"]
    stop_runtime(proc2, tmp_path)


def test_live_descriptor_never_removed(tmp_path: Path) -> None:
    provision(tmp_path, offline=False)
    proc, _document = _start_and_wait(tmp_path)
    descriptor_path = tmp_path / "descriptor" / "runtime.json"
    before = descriptor_path.read_text(encoding="utf-8")
    # The stale check must keep a live matching process's descriptor.
    assert not is_stale(tmp_path)
    time.sleep(0.5)
    assert descriptor_path.read_text(encoding="utf-8") == before
    stop_runtime(proc, tmp_path)


def test_token_rotates_on_runtime_restart_only(tmp_path: Path) -> None:
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    token_first = document["token"]
    stop_runtime(proc, tmp_path)
    proc2, document2 = _start_and_wait(tmp_path)
    token_second = document2["token"]
    assert token_first != token_second
    stop_runtime(proc2, tmp_path)


def _start_and_wait(state_root: Path):
    proc = start_runtime(state_root)
    document = wait_for_descriptor(state_root)
    wait_runtime_ready(state_root)
    return proc, document
