"""Shared contract tests for the Repository Interface fake."""

from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.repository import (
    FakeRepository,
    RepositoryPort,
    RepositoryRequest,
)

FAKE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "hermes_pipeline"
    / "repository"
    / "fake.py"
)
GIT_NAMES = frozenset({"git", "subprocess", "os"})


def test_fake_is_a_repository_port() -> None:
    assert isinstance(FakeRepository(), RepositoryPort)


def test_fake_never_calls_git() -> None:
    tree = ast.parse(FAKE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(GIT_NAMES)


def test_prepare_create_verify_cleanup_record_calls() -> None:
    fake = FakeRepository()
    request = RepositoryRequest(name="slice-00-07")
    assert fake.prepare(request).ok is True
    assert fake.create_candidate(request).action == "create_candidate"
    assert fake.verify(request).ok is True
    assert fake.cleanup(request).action == "cleanup"
    assert fake.calls == [
        ("prepare", "slice-00-07"),
        ("create_candidate", "slice-00-07"),
        ("verify", "slice-00-07"),
        ("cleanup", "slice-00-07"),
    ]
