"""Full-validator and bootstrap-gate consistency tests (AC-09).

The upgraded ``contracts check`` and the untouched dependency-free bootstrap
gate (``scripts/check_schemas.py``) must agree on the 14-Schema registry:
both pass on the committed registry and both reject a registry whose
identity set drifts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module
from hermes_pipeline.contracts.validate import run_contracts_check

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bootstrap_checker() -> Any:
    """Load the dependency-free bootstrap gate without leaking import state."""
    with isolated_script_module(
        "check_schemas", REPO_ROOT / "scripts" / "check_schemas.py"
    ) as module:
        yield cast(Any, module)


def test_both_validators_pass_on_the_committed_registry(
    bootstrap_checker: Any,
) -> None:
    ok, output = run_contracts_check(REPO_ROOT)
    assert ok, output
    report = bootstrap_checker.Reporter()
    bootstrap_checker.check_schemas(REPO_ROOT / "schemas", report, lock_identity=True)
    assert not report.has_issues, report.render()


def _drifted_registry(tmp_path: Path) -> Path:
    """A registry copy with one $id renamed (identity lock must fail)."""
    destination = tmp_path / "schemas"
    shutil.copytree(REPO_ROOT / "schemas", destination)
    target = destination / "engineering" / "closeout.schema.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["$id"] = document["$id"].replace("/v1", "/v2")
    target.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def test_both_validators_reject_an_identity_drift(
    tmp_path: Path, bootstrap_checker: Any
) -> None:
    drifted = _drifted_registry(tmp_path)
    report = bootstrap_checker.Reporter()
    bootstrap_checker.check_schemas(drifted, report, lock_identity=True)
    assert report.has_issues
    assert "unexpected Schema $id" in report.render()

    # The full validator must also fail on the drifted registry.
    ok, output = run_contracts_check(tmp_path)
    assert not ok
    assert "unexpected Schema $id" in output or "expected Schema $id" in output
