"""Deterministic offline SBOM preview over uv.lock."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module


@pytest.fixture
def previewer() -> Iterator[Any]:
    path = Path(__file__).resolve().parents[1] / "scripts" / "sbom_preview.py"
    with isolated_script_module("sbom_preview", path) as module:
        yield cast(Any, module)


def test_sbom_preview_is_deterministic_over_uv_lock(previewer: Any) -> None:
    root = Path(__file__).resolve().parents[1]
    first = json.dumps(previewer.build_preview(root), sort_keys=True)
    second = json.dumps(previewer.build_preview(root), sort_keys=True)
    assert first == second
    document = json.loads(first)
    assert document["schema"] == "hermes-sbom-preview/v1"
    assert document["lock_file"] == "uv.lock"
    names = [(row["name"], row["version"]) for row in document["packages"]]
    assert names == sorted(names)
    assert all(
        {"name", "version", "source"} == set(row) for row in document["packages"]
    )
