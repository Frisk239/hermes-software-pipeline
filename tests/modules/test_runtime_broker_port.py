"""Shared contract tests for the Runtime Broker Interface fake."""

from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.runtime_broker import (
    FakeRuntimeBroker,
    RuntimeBrokerPort,
    RuntimeLaunchRequest,
)

FAKE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "hermes_pipeline"
    / "runtime_broker"
    / "fake.py"
)
VENDOR_NAMES = frozenset({"codex", "opencode", "chrome", "subprocess", "os"})


def test_fake_is_a_runtime_broker_port() -> None:
    assert isinstance(FakeRuntimeBroker(), RuntimeBrokerPort)


def test_fake_does_not_import_or_exec_vendor_clis() -> None:
    tree = ast.parse(FAKE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(VENDOR_NAMES)


def test_launch_inspect_collect_are_fake_and_signal_is_unsupported() -> None:
    fake = FakeRuntimeBroker()
    handle = fake.launch(RuntimeLaunchRequest(runtime_id="rt-1"))
    assert handle.status == "FAKE"
    assert fake.inspect("rt-1").status == "FAKE"
    assert fake.collect("rt-1").status == "FAKE"
    signal = fake.signal("rt-1")
    assert signal.ok is False
    assert signal.code == "UNSUPPORTED"
    assert fake.launched == ["rt-1"]
