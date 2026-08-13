"""Authorization golden shapes and Host validation (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.runtime_broker._acl import protect_owner_only
from hermes_pipeline.runtime_broker._auth import (
    AuthorizationError,
    HostInputs,
    parse_host_argv,
    snapshot_path,
    validate_authorization,
)
from hermes_pipeline.runtime_broker._digest import file_digest, object_digest
from hermes_pipeline.runtime_broker._snapshot import snapshot_tree_digest

pytestmark = pytest.mark.fake_only

REPO = Path(__file__).resolve().parents[3]
SLICE_FIXTURES = (
    REPO
    / "docs"
    / "roadmap"
    / "phase-00-foundation"
    / "slices"
    / "00-06-agent-runtime-security-spikes"
    / "fixtures"
)
TEST_FIXTURES = REPO / "tests" / "fixtures" / "security"
TOOL_LOCK = (
    REPO
    / "docs"
    / "roadmap"
    / "phase-00-foundation"
    / "slices"
    / "00-06-agent-runtime-security-spikes"
    / "tool-lock.json"
)


def _load(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def test_copied_goldens_match_committed_slice_fixtures() -> None:
    for name in (
        "host-gate.accept.json",
        "host-gate.reject-extra-field.json",
        "pre-execution-tool-record.accept.json",
        "pre-execution-tool-record.reject-runtime-field.json",
        "run-binding.accept.json",
        "tool-observations.accept.json",
    ):
        assert (
            TEST_FIXTURES.joinpath(name).read_bytes()
            == SLICE_FIXTURES.joinpath(name).read_bytes()
        )


def test_reject_extra_host_gate_field() -> None:
    payload = _load(TEST_FIXTURES / "host-gate.reject-extra-field.json")
    assert "extra" in payload


def test_reject_runtime_field_on_pre_execution_record() -> None:
    payload = _load(
        TEST_FIXTURES / "pre-execution-tool-record.reject-runtime-field.json"
    )
    assert "version_output" in payload


def test_validate_authorization_rejects_runtime_and_extra_fields(
    tmp_path: Path,
) -> None:
    lock = TOOL_LOCK
    record_path = tmp_path / "pre-execution-tool-record.json"
    binding_path = tmp_path / "run-binding.json"
    gate_path = tmp_path / "host-gate.json"
    shutil.copyfile(
        TEST_FIXTURES / "pre-execution-tool-record.reject-runtime-field.json",
        record_path,
    )
    shutil.copyfile(TEST_FIXTURES / "run-binding.accept.json", binding_path)
    shutil.copyfile(TEST_FIXTURES / "host-gate.reject-extra-field.json", gate_path)
    snapshot = snapshot_path(record_path)
    snapshot.mkdir()
    inputs = HostInputs(
        state_root=tmp_path / "state",
        candidate_sha="9cf24b876cc7422386ed54c277900ff1e3c2c2bf",
        source_tree_digest="0123456789abcdef0123456789abcdef01234567",
        tool_lock=lock,
        tool_record=record_path,
        host_gate=gate_path,
        run_binding=binding_path,
    )
    with pytest.raises(AuthorizationError):
        validate_authorization(inputs)


def test_valid_chain_then_replay_is_rejected(tmp_path: Path) -> None:
    record = _load(TEST_FIXTURES / "pre-execution-tool-record.accept.json")
    lock_digest = file_digest(TOOL_LOCK.read_bytes())
    record["tool_lock_digest"] = lock_digest
    now = datetime.now(tz=UTC)
    record_path = tmp_path / "pre-execution-tool-record.json"
    snapshot = snapshot_path(record_path)
    snapshot.mkdir()
    (snapshot / "README").write_text("snapshot\n", encoding="utf-8")
    tree = snapshot_tree_digest(snapshot)
    record["source_tree_digest"] = tree
    record["integration_candidate_tree_digest"] = tree
    record["candidate_tree_digest"] = tree
    binding = {
        "schema_version": 1,
        "planning_base_sha": record["planning_base_sha"],
        "candidate_sha": record["candidate_sha"],
        "candidate_tree_digest": tree,
        "integration_base_sha": record["integration_base_sha"],
        "integration_candidate_sha": record["integration_candidate_sha"],
        "integration_candidate_tree_digest": tree,
        "source_tree_digest": tree,
        "tool_lock_digest": lock_digest,
        "tool_record_digest": object_digest(record),
        "custodian_origin": "git-custodian",
        "run_id": "run_example_0001",
        "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "expires_at_utc": (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "single_use_nonce": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    gate = {
        "schema_version": 1,
        "run_binding_digest": object_digest(binding),
    }
    binding_path = tmp_path / "run-binding.json"
    gate_path = tmp_path / "host-gate.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    protect_owner_only(gate_path)
    state = tmp_path / "state"
    inputs = HostInputs(
        state_root=state,
        candidate_sha=str(record["candidate_sha"]),
        source_tree_digest=str(record["source_tree_digest"]),
        tool_lock=TOOL_LOCK,
        tool_record=record_path,
        host_gate=gate_path,
        run_binding=binding_path,
    )
    first = validate_authorization(inputs, clock=lambda: now)
    assert first["run_binding_digest"] == gate["run_binding_digest"]
    with pytest.raises(AuthorizationError):
        validate_authorization(inputs, clock=lambda: now)


def test_git_metadata_in_snapshot_is_rejected(tmp_path: Path) -> None:
    record = _load(TEST_FIXTURES / "pre-execution-tool-record.accept.json")
    record["tool_lock_digest"] = file_digest(TOOL_LOCK.read_bytes())
    record_path = tmp_path / "pre-execution-tool-record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    snapshot = snapshot_path(record_path)
    snapshot.mkdir()
    (snapshot / ".git").write_text("gitdir: /real/repo/.git\n", encoding="utf-8")
    binding = {
        "schema_version": 1,
        "planning_base_sha": record["planning_base_sha"],
        "candidate_sha": record["candidate_sha"],
        "candidate_tree_digest": record["candidate_tree_digest"],
        "integration_base_sha": record["integration_base_sha"],
        "integration_candidate_sha": record["integration_candidate_sha"],
        "integration_candidate_tree_digest": record[
            "integration_candidate_tree_digest"
        ],
        "source_tree_digest": record["source_tree_digest"],
        "tool_lock_digest": record["tool_lock_digest"],
        "tool_record_digest": object_digest(record),
        "custodian_origin": "git-custodian",
        "run_id": "run_example_0001",
        "issued_at_utc": "2026-08-13T00:00:00.000Z",
        "expires_at_utc": "2099-08-13T00:00:00.000Z",
        "single_use_nonce": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    gate = {"schema_version": 1, "run_binding_digest": object_digest(binding)}
    binding_path = tmp_path / "run-binding.json"
    gate_path = tmp_path / "host-gate.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    inputs = HostInputs(
        state_root=tmp_path / "state",
        candidate_sha=str(record["candidate_sha"]),
        source_tree_digest=str(record["source_tree_digest"]),
        tool_lock=TOOL_LOCK,
        tool_record=record_path,
        host_gate=gate_path,
        run_binding=binding_path,
    )
    with pytest.raises(AuthorizationError):
        validate_authorization(inputs)


def test_unknown_argv_token_is_rejected() -> None:
    with pytest.raises(AuthorizationError):
        parse_host_argv(
            [
                "--state-root",
                "s",
                "--candidate-sha",
                "c",
                "--source-tree-digest",
                "d",
                "--tool-lock",
                "l",
                "--tool-record",
                "r",
                "--host-gate",
                "g",
                "--run-binding",
                "b",
                "--extra",
                "nope",
            ]
        )


def test_snapshot_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    record = _load(TEST_FIXTURES / "pre-execution-tool-record.accept.json")
    record["tool_lock_digest"] = file_digest(TOOL_LOCK.read_bytes())
    record_path = tmp_path / "pre-execution-tool-record.json"
    snapshot = snapshot_path(record_path)
    snapshot.mkdir()
    (snapshot / "a.txt").write_text("one\n", encoding="utf-8")
    record["source_tree_digest"] = "sha256:" + ("ab" * 32)
    record["integration_candidate_tree_digest"] = record["source_tree_digest"]
    record_path.write_text(json.dumps(record), encoding="utf-8")
    binding = {
        "schema_version": 1,
        "planning_base_sha": record["planning_base_sha"],
        "candidate_sha": record["candidate_sha"],
        "candidate_tree_digest": record["source_tree_digest"],
        "integration_base_sha": record["integration_base_sha"],
        "integration_candidate_sha": record["integration_candidate_sha"],
        "integration_candidate_tree_digest": record["source_tree_digest"],
        "source_tree_digest": record["source_tree_digest"],
        "tool_lock_digest": record["tool_lock_digest"],
        "tool_record_digest": object_digest(record),
        "custodian_origin": "git-custodian",
        "run_id": "run_example_0001",
        "issued_at_utc": "2026-08-13T00:00:00.000Z",
        "expires_at_utc": "2099-08-13T00:00:00.000Z",
        "single_use_nonce": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    gate_path = tmp_path / "host-gate.json"
    bind_path = tmp_path / "run-binding.json"
    bind_path.write_text(json.dumps(binding), encoding="utf-8")
    gate_path.write_text(
        json.dumps({"schema_version": 1, "run_binding_digest": object_digest(binding)}),
        encoding="utf-8",
    )
    protect_owner_only(gate_path)
    inputs = HostInputs(
        state_root=tmp_path / "state",
        candidate_sha=str(record["candidate_sha"]),
        source_tree_digest=str(record["source_tree_digest"]),
        tool_lock=TOOL_LOCK,
        tool_record=record_path,
        host_gate=gate_path,
        run_binding=bind_path,
    )
    with pytest.raises(AuthorizationError):
        validate_authorization(inputs)
