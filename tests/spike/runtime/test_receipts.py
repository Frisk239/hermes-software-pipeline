"""Fake receipt store exactly-once semantics (slice-00-05, fixed D4).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Stdlib ``sqlite3`` receipt store in the disposable state root: a duplicate
``command_id`` returns the original receipt; the receipt row and the
single effect commit atomically; a forged receipt (not matching the
persisted row) is rejected; the store survives a reopen (restart
evidence), and its data is disposable spike state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_pipeline.transport._receipts import ReceiptStore


@pytest.fixture
def store(tmp_path: Path) -> ReceiptStore:
    instance = ReceiptStore(tmp_path)
    instance.open()
    return instance


def test_happy_path_returns_receipt(store: ReceiptStore) -> None:
    receipt = store.process("cmd_0001", {"op": "fake"})
    assert receipt["command_id"] == "cmd_0001"
    assert receipt["deduplicated"] is False
    assert receipt["effect_count"] == 1
    assert store.effect_count("cmd_0001") == 1


def test_duplicate_command_id_returns_original_receipt(store: ReceiptStore) -> None:
    first = store.process("cmd_0002", {"op": "fake"})
    second = store.process("cmd_0002", {"op": "fake"})
    # The persisted receipt is returned unchanged: deduplicated stays at the
    # original value and no field is rewritten by the retry.
    assert second == first
    assert second["deduplicated"] is False
    assert second["effect_count"] == 1
    assert store.effect_count("cmd_0002") == 1
    assert first["payload_hash"] == second["payload_hash"]


def test_distinct_command_ids_have_distinct_effects(store: ReceiptStore) -> None:
    store.process("cmd_a", {"op": "fake"})
    store.process("cmd_b", {"op": "fake"})
    assert store.effect_count("cmd_a") == 1
    assert store.effect_count("cmd_b") == 1


def test_store_survives_reopen(tmp_path: Path) -> None:
    first = ReceiptStore(tmp_path)
    first.open()
    first.process("cmd_0003", {"op": "fake"})
    reopened = ReceiptStore(tmp_path)
    reopened.open()
    assert reopened.get("cmd_0003") is not None
    retry = reopened.process("cmd_0003", {"op": "fake"})
    assert retry == reopened.get("cmd_0003")
    assert retry["deduplicated"] is False
    assert reopened.effect_count("cmd_0003") == 1


def test_forged_receipt_rejected(store: ReceiptStore) -> None:
    store.process("cmd_0004", {"op": "fake"})
    forged = {
        "command_id": "cmd_0004",
        "payload_hash": "0" * 64,
        "effect_count": 1,
        "deduplicated": False,
        "processed_at": "2026-01-01T00:00:00Z",
    }
    assert store.is_forged("cmd_0004", forged)


def test_matching_receipt_not_forged(store: ReceiptStore) -> None:
    receipt = store.process("cmd_0005", {"op": "fake"})
    assert not store.is_forged("cmd_0005", receipt)


def test_unknown_command_id_is_forged(store: ReceiptStore) -> None:
    assert store.is_forged("never-seen", {"command_id": "never-seen"})


def test_effect_count_unknown_is_zero(store: ReceiptStore) -> None:
    assert store.effect_count("never-seen") == 0


def test_receipt_json_is_bounded_and_stable(store: ReceiptStore) -> None:
    receipt = store.process("cmd_0006", {"op": "fake"})
    text = json.dumps(receipt, sort_keys=True)
    assert len(text) < 2048
    assert "sql" not in text.lower()
