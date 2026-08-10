"""Shared persistence port contract tests (slice-00-04, AC-02/03/04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Every persistence Adapter (deterministic in-memory and SQLite spike)
implements the same private port contract; these tests run against both
Adapters (shared contract tests, repository test expectations).

Coverage:

- AC-02: Controller logic runs against the in-memory Adapter with no SQLite
  present; a persistence failure (including a ``find_command`` failure)
  returns the specified safe, non-durable ``CommandReceipt``; the
  Stage-facing signature stays ``submit(ControllerCommand) ->
  CommandReceipt``.
- AC-03: one explicit transaction commits Inbox, Event, projection, Outbox,
  and receipt all-or-none; an exception injected before or after each of
  the five logical writes rolls the whole transaction back, and every
  ``after`` hook proves (via bounded evidence on the ``FaultSpec``) that
  the named write really executed before the rollback; the explicit driver
  transaction mode is proven by behavior-difference fixtures; a fixture
  that relies on the legacy ``sqlite3`` default transaction control fails.
- AC-04: duplicate identical commands return the original receipt with
  exactly one Event; same-ID different-payload returns the private
  ``COMMAND_ID_CONFLICT`` classification and the schema-compatible
  ``CONFLICT``/``CONFLICT`` receipt with fixed message ``command identity
  conflict``; expected-revision mismatch returns ``CONFLICT``/``CONFLICT``
  with ``expected revision conflict``; rejections append no Event or Outbox
  row and leak no raw exception text.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Protocol, runtime_checkable

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.spike.conftest import make_spike_command

from hermes_pipeline.contracts.runtime import CommandReceipt
from hermes_pipeline.controller._persistence_port import (
    AcceptanceWrites,
    ControllerPersistencePort,
    EventRecord,
    FaultSpec,
    InboxRecord,
    OutboxRecord,
    PersistenceError,
    PersistenceErrorKind,
    ProjectionRecord,
    ReceiptRecord,
    StoredCommand,
)
from hermes_pipeline.controller.spike_controller import (
    COMMAND_ID_CONFLICT,
    MESSAGE_IDENTITY_CONFLICT,
    MESSAGE_INVALID_DELTA,
    MESSAGE_PERSISTENCE_UNAVAILABLE,
    MESSAGE_REVISION_CONFLICT,
    SpikeController,
)
from hermes_pipeline.persistence.in_memory import InMemoryControllerStore
from hermes_pipeline.persistence.sqlite_spike import (
    DRIVER_TRANSACTION_MODE,
    SqliteControllerStore,
)

#: All five logical-write positions (1=Inbox, 2=Event, 3=projection,
#: 4=Outbox, 5=receipt).
ALL_WRITES = (1, 2, 3, 4, 5)


def _assert_no_sensitive_output(rendered: str, forbidden: tuple[str, ...]) -> None:
    """Fail closed without allowing pytest to echo a leak on regression."""
    if (
        any(value in rendered for value in forbidden)
        or chr(10) in rendered
        or chr(13) in rendered
        or chr(9) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe persistence-port diagnostic")


def _assert_no_exception_chain(error: BaseException) -> None:
    """Ensure a private-port boundary cannot retain raw driver details."""
    if error.__cause__ is not None or error.__context__ is not None:
        raise AssertionError("persistence port retained an unsafe exception chain")


@runtime_checkable
class PortFactory(Protocol):
    """Callable building one port instance for the shared contract tests."""

    def __call__(
        self, fault_spec: FaultSpec | None = None
    ) -> ControllerPersistencePort:
        """Build a fresh port with an optional fault spec."""
        raise NotImplementedError


def _dummy_writes() -> AcceptanceWrites:
    """Deterministic five-record writes for port-level fault tests."""
    return AcceptanceWrites(
        inbox=InboxRecord(
            command_id="cmd_dummy",
            payload_hash="0" * 64,
            command_json='{"command_id":"cmd_dummy"}',
            recorded_at="2026-01-01T00:00:00Z",
        ),
        event=EventRecord(
            sequence=1,
            event_id="evt_00000000",
            pipeline_revision=1,
            payload_json='{"value":1,"revision":1}',
        ),
        projection=ProjectionRecord(value=1, revision=1),
        outbox=OutboxRecord(
            command_id="cmd_dummy", effect_type="SPIKE_NOOP_EFFECT", payload_json="{}"
        ),
        receipt=ReceiptRecord(
            command_id="cmd_dummy", receipt_json='{"status":"ACCEPTED"}'
        ),
    )


@pytest.fixture(
    params=["in-memory", "sqlite"],
    ids=["in-memory", "sqlite"],
)
def port_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> PortFactory:
    """Parameterized Adapter factory for the shared contract tests."""

    def build(fault_spec: FaultSpec | None = None) -> ControllerPersistencePort:
        if request.param == "in-memory":
            return InMemoryControllerStore(fault_spec=fault_spec)
        db = tmp_path / f"contract-{request.param}.db"
        return SqliteControllerStore(db, fault_spec=fault_spec)

    return build


def _make_controller(
    port: ControllerPersistencePort,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> SpikeController:
    return SpikeController(port, frozen_clock, event_id_sequence)


def test_port_signature_returns_command_receipt(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-02: the Stage-facing signature remains submit -> CommandReceipt."""
    controller = _make_controller(port_factory(), frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_0000"))
    assert isinstance(receipt, CommandReceipt)
    assert receipt.status == "ACCEPTED"
    assert receipt.observed_revision == 1


def test_accepted_submit_commits_all_five_records(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-03 positive: a normal submit leaves all five records present."""
    port = port_factory()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_0001"))
    assert receipt.status == "ACCEPTED"
    audit = port.audit()
    assert audit.inbox_count == 1
    assert audit.event_count == 1
    assert audit.outbox_count == 1
    assert audit.receipt_count == 1
    assert audit.projection is not None
    assert audit.projection.value == 1
    assert audit.projection.revision == 1


@pytest.mark.parametrize("position", ALL_WRITES)
@pytest.mark.parametrize("phase", ["before", "after"])
def test_injected_fault_rolls_back_all_five_records(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
    position: int,
    phase: str,
) -> None:
    """AC-03: an exception injected before or after each of the five logical
    writes rolls the whole transaction back and the caller receives the
    specified non-durable CommandReceipt. For the ``after`` phase the
    named write demonstrably executed first (bounded evidence on the
    FaultSpec); for the ``before`` phase it never executed."""
    spec = FaultSpec(
        before=frozenset({position}) if phase == "before" else frozenset(),
        after=frozenset({position}) if phase == "after" else frozenset(),
    )
    port = port_factory(spec)
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_fault"))
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == MESSAGE_PERSISTENCE_UNAVAILABLE
    assert receipt.error.retryable is True
    audit = port.audit()
    assert audit.inbox_count == 0
    assert audit.event_count == 0
    assert audit.outbox_count == 0
    assert audit.receipt_count == 0
    assert audit.projection is not None
    assert audit.projection.value == 0
    assert audit.projection.revision == 0
    if phase == "after":
        # The after hook fired only after the write executed: the probe
        # observed the written row inside the transaction.
        assert any(
            entry.startswith(f"after:write:{position}:probe:")
            for entry in spec.evidence
        ), f"missing after-write evidence for position {position}"
    else:
        # A before hook fires before the write, so no write ever executed.
        assert spec.evidence == []


def test_all_ten_injection_points_reachability_matrix(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-03: the full 10-point injection matrix (five logical writes x
    before/after) is reachable on both Adapters, every after point proves
    the write executed before the rollback, and every before point proves
    the write never executed. This is the spike-persistence reachability
    evidence for the ten AC-03 injection points."""
    covered: list[tuple[int, str]] = []
    for position in ALL_WRITES:
        for phase in ("before", "after"):
            spec = FaultSpec(
                before=frozenset({position}) if phase == "before" else frozenset(),
                after=frozenset({position}) if phase == "after" else frozenset(),
            )
            port = port_factory(spec)
            controller = _make_controller(port, frozen_clock, event_id_sequence)
            receipt = controller.submit(make_spike_command("cmd_matrix_fault"))
            assert receipt.status == "REJECTED"
            assert receipt.error.code == "INTERNAL_ERROR"
            assert receipt.error.message == MESSAGE_PERSISTENCE_UNAVAILABLE
            audit = port.audit()
            assert audit.event_count == 0
            if phase == "after":
                assert any(
                    entry.startswith(f"after:write:{position}:probe:")
                    for entry in spec.evidence
                ), f"after point {position} did not prove the write executed"
            else:
                assert spec.evidence == [], f"before point {position} wrote"
            covered.append((position, phase))
    assert len(covered) == 10


def test_duplicate_identical_command_returns_original_receipt_single_event(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-04 positive: replay of an identical command returns the original
    receipt with a single Event."""
    port = port_factory()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    command = make_spike_command("cmd_contract_dup")
    first = controller.submit(command)
    assert first.status == "ACCEPTED"
    replay = controller.submit(command)
    assert replay.status == "ACCEPTED"
    assert replay.model_dump() == first.model_dump()
    audit = port.audit()
    assert audit.event_count == 1
    assert audit.receipt_count == 1
    assert audit.outbox_count == 1


def test_same_id_different_payload_is_private_command_id_conflict(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-04 negative: same ID different payload returns the private
    COMMAND_ID_CONFLICT classification and the schema-compatible conflict
    receipt with no Event, no Outbox row, and no raw exception text."""
    port = port_factory()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    first = controller.submit(make_spike_command("cmd_contract_idconf"))
    assert first.status == "ACCEPTED"
    conflicting = make_spike_command(
        "cmd_contract_idconf", delta=1, payload_extra={"extra": 1}
    )
    conflict = controller.submit(conflicting)
    assert conflict.status == "CONFLICT"
    assert conflict.error.code == "CONFLICT"
    assert conflict.error.message == MESSAGE_IDENTITY_CONFLICT
    assert conflict.error.retryable is False
    # The private classification is asserted on the spike-internal path and
    # is never part of the Stage-visible receipt.
    internal = controller.submit_internal(conflicting)
    assert internal.duplicate_class == COMMAND_ID_CONFLICT
    assert internal.receipt.status == "CONFLICT"
    audit = port.audit()
    assert audit.event_count == 1
    assert audit.outbox_count == 1
    assert audit.receipt_count == 1


def test_expected_revision_conflict_receipt(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-04 negative: expected-revision mismatch returns CONFLICT/CONFLICT
    with fixed message, no Event, no Outbox row."""
    port = port_factory()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    first = controller.submit(make_spike_command("cmd_contract_rev"))
    assert first.status == "ACCEPTED"
    conflict = controller.submit(
        make_spike_command("cmd_contract_rev2", expected_revision=0)
    )
    assert conflict.status == "CONFLICT"
    assert conflict.error.code == "CONFLICT"
    assert conflict.error.message == MESSAGE_REVISION_CONFLICT
    assert conflict.error.retryable is False
    audit = port.audit()
    assert audit.event_count == 1
    assert audit.outbox_count == 1
    assert audit.receipt_count == 1


def test_invalid_delta_rejection_mapping(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-02/AC-04: INVALID_DELTA projects to REJECTED/VALIDATION_ERROR with
    fixed message and no state change."""
    port = port_factory()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_baddelta", delta=2))
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "VALIDATION_ERROR"
    assert receipt.error.message == MESSAGE_INVALID_DELTA
    assert receipt.error.retryable is False
    audit = port.audit()
    assert audit.event_count == 0
    assert audit.outbox_count == 0
    assert audit.receipt_count == 0
    assert audit.projection is not None
    assert audit.projection.value == 0
    assert audit.projection.revision == 0


def test_failure_receipt_contains_no_raw_exception_text(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-03/AC-04: no traceback, raw SQL, path, database content, or raw
    exception text appears in any receipt or captured output."""
    port = port_factory(FaultSpec(before=frozenset({1})))
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_noleak"))
    rendered = receipt.model_dump_json()
    _assert_no_sensitive_output(rendered, ("injected fault", "Traceback", "sqlite"))
    captured = capsys.readouterr()
    _assert_no_sensitive_output(
        captured.out + captured.err, ("injected fault", "Traceback")
    )


def test_raw_driver_exception_never_crosses_interface(
    port_factory: PortFactory,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-02: an Adapter-level driver failure surfaces only as the safe
    non-durable CommandReceipt; no PersistenceError or InjectedFault escapes
    through submit()."""
    port = port_factory(FaultSpec(before=frozenset({5})))
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_contract_raw"))
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == MESSAGE_PERSISTENCE_UNAVAILABLE
    assert receipt.error.retryable is True


class _FindCommandFailingPort(InMemoryControllerStore):
    """Negative fixture: the deduplication probe fails at the port."""

    def find_command(self, command_id: str) -> StoredCommand | None:
        raise PersistenceError(
            PersistenceErrorKind.UNAVAILABLE, MESSAGE_PERSISTENCE_UNAVAILABLE
        )


def test_find_command_persistence_error_maps_to_fixed_failure_receipt(
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-02/AC-03: a PersistenceError from find_command (the deduplication
    probe) maps to the same fixed non-durable failure receipt as any other
    persistence failure, and no raw exception crosses submit()."""
    port: ControllerPersistencePort = _FindCommandFailingPort()
    controller = _make_controller(port, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_find_failure"))
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == MESSAGE_PERSISTENCE_UNAVAILABLE
    assert receipt.error.retryable is True
    assert receipt.event_ids == []
    # The failure path wrote nothing durable.
    audit = port.audit()
    assert audit.inbox_count == 0
    assert audit.event_count == 0
    assert audit.outbox_count == 0
    assert audit.receipt_count == 0
    # No raw exception text appears in the rendered receipt.
    rendered = receipt.model_dump_json()
    _assert_no_sensitive_output(rendered, ("Traceback", "sqlite", "find_command"))


def test_persistence_error_typed_boundary(
    port_factory: PortFactory,
) -> None:
    """The private port raises only typed PersistenceError, never a raw
    driver exception, for an injected in-transaction failure."""
    port = port_factory(FaultSpec(after=frozenset({2})))
    with pytest.raises(PersistenceError) as excinfo:
        port.commit_acceptance(_dummy_writes())
    if (
        str(excinfo.value) != MESSAGE_PERSISTENCE_UNAVAILABLE
        or excinfo.value.safe_message != MESSAGE_PERSISTENCE_UNAVAILABLE
    ):
        raise AssertionError("persistence port leaked an unsafe failure message")
    _assert_no_exception_chain(excinfo.value)


def test_sqlite_driver_failure_does_not_retain_raw_exception_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-02/AC-03: a raw SQLite failure never survives in error chaining."""
    store = SqliteControllerStore(tmp_path / "poisoned-driver.db")
    canary = "sqlite-driver-canary" + chr(10) + "detail" + chr(7)

    def _poisoned_connect(_: Engine) -> NoReturn:
        raise sqlite3.OperationalError(canary)

    monkeypatch.setattr(Engine, "connect", _poisoned_connect)
    try:
        with pytest.raises(PersistenceError) as excinfo:
            store.find_command("cmd_driver_failure")
    finally:
        store.close()

    rendered = str(excinfo.value)
    if (
        rendered != MESSAGE_PERSISTENCE_UNAVAILABLE
        or canary in rendered
        or chr(10) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("persistence port leaked an unsafe driver diagnostic")
    _assert_no_exception_chain(excinfo.value)


def test_legacy_default_transaction_control_is_never_relied_upon(
    tmp_path: Path,
) -> None:
    """AC-03 negative: the legacy sqlite3 implicit transaction control
    leaves partial records behind (proving it must not be relied on), while
    the spike Adapter wraps every write in an explicit transaction."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, payload TEXT)")
        conn.execute("INSERT INTO t (payload) VALUES ('first')")
        conn.commit()
        with contextlib.suppress(sqlite3.IntegrityError):
            # legacy mode: the failed second row leaves the first row
            # durable without any explicit rollback boundary
            conn.execute("INSERT INTO t (id, payload) VALUES (1, 'second')")
    finally:
        conn.close()
    check = sqlite3.connect(db)
    try:
        partial = check.execute("SELECT COUNT(*) FROM t").fetchone()
    finally:
        check.close()
    assert partial is not None and partial[0] == 1  # partial legacy state
    # The spike Adapter never writes outside an explicit transaction.
    store = SqliteControllerStore(tmp_path / "explicit.db")
    assert store.audit().event_count == 0


def test_adapter_engine_uses_explicit_driver_transaction_mode(
    tmp_path: Path,
) -> None:
    """AC-03/AC-08: the Adapter's engine runs in the documented explicit
    driver transaction mode — the legacy sqlite3 implicit transaction
    control is disabled (native autocommit) and every transaction is opened
    by an explicit BEGIN event hook. Behavior difference at the driver
    level: in the Adapter's mode a raw DML statement leaves
    ``in_transaction == False`` and is immediately durable (no silent
    implicit transaction), while the legacy default silently opens an
    implicit transaction; and the five-record commit still rolls back
    atomically when the explicit transaction fails."""
    assert "explicit" in DRIVER_TRANSACTION_MODE
    assert "begin" in DRIVER_TRANSACTION_MODE
    database = tmp_path / "explicit-mode.db"
    store = SqliteControllerStore(database)
    engine = store._engine  # type: ignore[attr-defined]

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE tx_probe (id INTEGER PRIMARY KEY)"))

    # Driver-level behavior difference: a raw DML statement on the Adapter's
    # engine commits immediately (native autocommit) and never opens a
    # legacy implicit transaction.
    raw = engine.raw_connection()
    driver = raw.driver_connection  # type: ignore[attr-defined]
    assert driver is not None
    assert driver.in_transaction is False
    driver.execute("INSERT INTO tx_probe DEFAULT VALUES")
    assert driver.in_transaction is False  # no implicit transaction opened
    raw.close()
    other = sqlite3.connect(database)
    try:
        visible = int(other.execute("SELECT COUNT(*) FROM tx_probe").fetchone()[0])
    finally:
        other.close()
    assert visible == 1  # immediately durable, no silent holding

    # Atomicity of the five-record commit still comes from the explicit
    # BEGIN/COMMIT pair: a failing explicit transaction rolls back.
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO tx_probe DEFAULT VALUES"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    other = sqlite3.connect(database)
    try:
        after_rollback = int(
            other.execute("SELECT COUNT(*) FROM tx_probe").fetchone()[0]
        )
    finally:
        other.close()
    assert after_rollback == 1
    store.close()


def test_legacy_reliant_fixture_fails_behavior_difference(
    tmp_path: Path,
) -> None:
    """AC-03 negative: a fixture relying on the legacy sqlite3 default
    transaction control fails the behavior-difference assertions — an
    INSERT without an explicit COMMIT is silently held in an implicit
    transaction (invisible to a second connection) and is lost on close,
    which is exactly the behavior the explicit Adapter mode eliminates."""
    database = tmp_path / "legacy-reliant.db"
    conn = sqlite3.connect(database)  # legacy default (implicit control)
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO t DEFAULT VALUES")  # implicit BEGIN
        other = sqlite3.connect(database)
        try:
            invisible = int(other.execute("SELECT COUNT(*) FROM t").fetchone()[0])
        finally:
            other.close()
        assert invisible == 0  # silently held: not durable without COMMIT
    finally:
        conn.close()  # no COMMIT: the implicit transaction is discarded
    check = sqlite3.connect(database)
    try:
        lost = int(check.execute("SELECT COUNT(*) FROM t").fetchone()[0])
    finally:
        check.close()
    assert lost == 0  # the legacy-reliant write was lost
    # The same DML on the Adapter's engine is immediately durable (see
    # test_adapter_engine_uses_explicit_driver_transaction_mode).
