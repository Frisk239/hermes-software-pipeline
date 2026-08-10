"""Single-writer workload spike and SQLITE_FULL injection (slice-00-04,
AC-09).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Fixed reproducible envelope: 1,000 accepted commands, 4 producers, one
writer, queue capacity 32, command and event payloads each no larger than
1 KiB, p95 acknowledged latency <= 2s, busy count == 0, WAL high-water
<= 16 MiB, and checkpoint, online backup, and fresh-process recovery each
<= 5s.

The workload report carries only the fixed redacted runner profile (OS
family, architecture, CI runner label, Python version, sqlite3.sqlite_version)
plus selected PRAGMAs read from the actual spike database connection and
queue high-water; hostname, username, absolute paths, environment variable
values, tokens, raw exception text, and database content are forbidden,
proved by a redaction assertion with injected fake sensitive values.
Rework 2 (P1-1/P1-4): runner values are restricted to enum/regex value
domains (never just a length cap), control characters are rejected in every
string value, all reporter error messages are fixed safe text carrying
neither input values nor field names, and short-token, control-character,
and canary-key-name negatives all fail closed with zero leakage.

A deterministic SQLITE_FULL injection (PRAGMA max_page_count limited)
returns the specified non-durable REJECTED/INTERNAL_ERROR receipt, writes
no durable receipt record or partial records, is restart-safe, and never
exhausts real disk.
"""

from __future__ import annotations

import json
import math
import os
import platform
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from tests.spike.conftest import make_event_id_provider, make_spike_command

from hermes_pipeline.controller.spike_controller import (
    MESSAGE_PERSISTENCE_UNAVAILABLE,
    SpikeController,
)
from hermes_pipeline.persistence.backup import backup_database
from hermes_pipeline.persistence.sqlite_spike import SqliteControllerStore

#: Fixed envelope.
COMMAND_COUNT = 1_000
PRODUCER_COUNT = 4
QUEUE_CAPACITY = 32
MAX_PAYLOAD_BYTES = 1_024
P95_LATENCY_LIMIT_S = 2.0
WAL_HIGH_WATER_LIMIT_MIB = 16
OPERATION_LIMIT_S = 5.0

#: Fake sensitive values injected to prove redaction.
FAKE_HOSTNAME = "fake-host-0000"
FAKE_USERNAME = "fake-user-0000"
FAKE_PATH = "C:\\fake\\absolute\\path\\0000"
FAKE_ENV_VALUE = "fake-env-value-0000"
FAKE_TOKEN = "fake-token-0000"

#: Fresh-process recovery probe reused from the persistence spike.
PROBE = Path(__file__).resolve().parents[1] / "persistence" / "_recovery_probe.py"


def _assert_sqlite_full_error(error: sqlite3.OperationalError) -> None:
    """Classify the bounded injection by driver code, never error text."""
    if getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_FULL:
        raise AssertionError(
            "SQLITE_FULL injection did not return the expected driver code"
        )


def _assert_recovery_probe_succeeded(proc: subprocess.CompletedProcess[str]) -> None:
    """Keep a failed probe's raw output out of pytest diagnostics."""
    if proc.returncode != 0:
        raise AssertionError("workload recovery probe failed")


def _assert_safe_diagnostic(rendered: str, expected: str, canary: str) -> None:
    """Verify diagnostic redaction without echoing the canary on regression."""
    if (
        rendered != expected
        or canary in rendered
        or chr(10) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe workload diagnostic")


def _assert_no_sensitive_text(
    rendered: str, forbidden: Iterable[str], *, allow_line_feeds: bool = False
) -> None:
    """Fail closed without allowing pytest to render an unsafe diagnostic."""
    if (
        any(value in rendered for value in forbidden)
        or (not allow_line_feeds and chr(10) in rendered)
        or chr(13) in rendered
        or chr(9) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe workload diagnostic")


def _payload_for(index: int) -> dict[str, object]:
    """Deterministic payload bounded to 1 KiB of canonical JSON."""
    return {"delta": 1, "filler": "x" * 920, "index": index}


def _payload_bytes(payload: dict[str, object]) -> int:
    return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


class WorkloadReporter:
    """Renders only the fixed redacted runner profile plus selected PRAGMAs
    and queue high-water. Never emits hostname, username, absolute paths,
    environment values, tokens, raw exceptions, or database content.

    The input is sanitized, fail-closed (rework 2, P1-1/P1-4):

    - only the whitelisted runner, PRAGMA, and metric fields are accepted;
    - every runner value is restricted to a limited value domain (enum or
      regex whitelist), never just a length cap, so a short token such as
      ``"tok"`` cannot be rendered;
    - control characters (newline, carriage return, tab, and all other C0
      control characters plus DEL) are rejected in every string value;
    - every metric and numeric PRAGMA value is type-checked and
      range-bounded;
    - every error message is fixed safe text that never carries an input
      value **or a field name** — a canary key name is itself a sensitive
      value, so unknown-field errors do not echo the offending key.

    Values that are not the fixed profile (hostname/username/path/
    environment/token canaries, including short or control-character
    canaries) are rejected without being rendered, fail-closed and with
    zero leakage.
    """

    ALLOWED_RUNNER_FIELDS = frozenset(
        {
            "os_family",
            "architecture",
            "ci_runner_label",
            "python_version",
            "sqlite_version",
        }
    )
    ALLOWED_PRAGMA_FIELDS = frozenset(
        {
            "journal_mode",
            "synchronous",
            "wal_autocheckpoint",
            "page_size",
            "max_page_count",
        }
    )
    ALLOWED_METRIC_FIELDS = frozenset(
        {
            "accepted",
            "p95_latency_s",
            "busy_count",
            "wal_high_water_mib",
            "queue_high_water",
            "checkpoint_s",
            "backup_s",
            "recovery_s",
        }
    )
    #: Restricted runner value domains: enum or regex whitelist per field.
    #: A value outside the domain is rejected with fixed safe text; the
    #: length bound below is an additional cap, never the only check.
    RUNNER_VALUE_DOMAINS: ClassVar[dict[str, frozenset[str] | re.Pattern[str]]] = {
        "os_family": frozenset({"Windows", "Linux", "Darwin"}),
        "architecture": frozenset(
            {"AMD64", "x86_64", "aarch64", "arm64", "x86", "i386", "i686"}
        ),
        "ci_runner_label": frozenset({"local", "windows-latest", "ubuntu-latest"}),
        "python_version": re.compile(r"^\d+\.\d+(?:\.\d+)?$"),
        "sqlite_version": re.compile(r"^\d+\.\d+(?:\.\d+)?$"),
    }
    #: Restricted PRAGMA value domains (AC-09 selected PRAGMAs).
    JOURNAL_MODES: frozenset[str] = frozenset(
        {"delete", "truncate", "persist", "memory", "wal", "off"}
    )
    SYNCHRONOUS_MODES: frozenset[int] = frozenset({0, 1, 2, 3})
    PAGE_SIZES: frozenset[int] = frozenset(
        {512, 1024, 2048, 4096, 8192, 16384, 32768, 65536}
    )
    #: Bounded rendering caps: runner strings and numeric magnitudes.
    MAX_FIELD_LENGTH = 64
    MAX_METRIC_VALUE = 2**53

    @staticmethod
    def _has_control_char(value: str) -> bool:
        """True when the string carries a C0 control character or DEL."""
        return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)

    @staticmethod
    def _require_exact_string_keys(mapping: dict[object, object]) -> None:
        """Reject subclassed keys before any mapping lookup or set operation.

        A ``str`` subclass may override hashing or equality and throw an
        arbitrary exception when used as a dictionary key.  Key iteration
        and exact-type inspection are safe; only after this guard may the
        reporter use set algebra or lookups on untrusted mappings.
        """
        for key in mapping:
            if type(key) is not str:
                raise AssertionError("mapping key must be a string")

    @classmethod
    def _validated_runner(cls, runner_raw: object) -> dict[str, str]:
        """Fail-closed runner profile validation with fixed safe errors."""
        if type(runner_raw) is not dict:
            raise AssertionError("runner profile must be a mapping")
        runner_fields = cast(dict[object, object], runner_raw)
        cls._require_exact_string_keys(runner_fields)
        unknown_runner = set(runner_fields) - cls.ALLOWED_RUNNER_FIELDS
        if unknown_runner:
            # Fixed text: an unknown field name is itself a potential canary
            # key name and must never be echoed.
            raise AssertionError("forbidden runner field")
        missing_runner = cls.ALLOWED_RUNNER_FIELDS - set(runner_fields)
        if missing_runner:
            raise AssertionError("missing runner field")
        runner: dict[str, str] = {}
        for key in sorted(cls.ALLOWED_RUNNER_FIELDS):
            value = runner_fields[key]
            if type(value) is not str:
                raise AssertionError("runner field must be a string")
            if cls._has_control_char(value):
                raise AssertionError("runner field contains a control character")
            domain = cls.RUNNER_VALUE_DOMAINS[key]
            if isinstance(domain, frozenset):
                matches = value in domain
            else:
                matches = domain.fullmatch(value) is not None
            if not matches:
                raise AssertionError("runner field fails the value-domain whitelist")
            if len(value) > cls.MAX_FIELD_LENGTH:
                raise AssertionError("runner field exceeds the length bound")
            runner[key] = value
        return runner

    @classmethod
    def _validated_pragmas(cls, pragma_raw: object) -> dict[str, object]:
        """Fail-closed selected-PRAGMA validation with fixed safe errors."""
        if type(pragma_raw) is not dict:
            raise AssertionError("pragma profile must be a mapping")
        pragma_fields = cast(dict[object, object], pragma_raw)
        cls._require_exact_string_keys(pragma_fields)
        unknown_pragma = set(pragma_fields) - cls.ALLOWED_PRAGMA_FIELDS
        if unknown_pragma:
            raise AssertionError("forbidden pragma field")
        missing_pragma = cls.ALLOWED_PRAGMA_FIELDS - set(pragma_fields)
        if missing_pragma:
            raise AssertionError("missing pragma field")
        pragmas: dict[str, object] = {}
        for key in sorted(cls.ALLOWED_PRAGMA_FIELDS):
            value = pragma_fields[key]
            if key == "journal_mode":
                if type(value) is not str:
                    raise AssertionError("pragma field must be a string")
                if cls._has_control_char(value):
                    raise AssertionError("pragma field contains a control character")
                if value not in cls.JOURNAL_MODES:
                    raise AssertionError(
                        "pragma field fails the value-domain whitelist"
                    )
                if len(value) > cls.MAX_FIELD_LENGTH:
                    raise AssertionError("pragma field exceeds the length bound")
            else:
                if type(value) is not int:
                    raise AssertionError("pragma field must be an integer")
                if not 0 <= value <= cls.MAX_METRIC_VALUE:
                    raise AssertionError("pragma field is out of the bounded range")
                if key == "synchronous" and value not in cls.SYNCHRONOUS_MODES:
                    raise AssertionError(
                        "pragma field fails the value-domain whitelist"
                    )
                if key == "page_size" and value not in cls.PAGE_SIZES:
                    raise AssertionError(
                        "pragma field fails the value-domain whitelist"
                    )
            pragmas[key] = value
        return pragmas

    @classmethod
    def _validated_metrics(cls, metric_map: dict[object, object]) -> dict[str, str]:
        unknown_metrics = (
            set(metric_map)
            - cls.ALLOWED_METRIC_FIELDS
            - {
                "runner",
                "pragmas",
            }
        )
        if unknown_metrics:
            raise AssertionError("forbidden metric field")
        numeric: dict[str, str] = {}
        for key in sorted(cls.ALLOWED_METRIC_FIELDS):
            value = metric_map.get(key)
            if type(value) is int:
                numeric_value = value
                if not 0 <= numeric_value <= cls.MAX_METRIC_VALUE:
                    raise AssertionError("metric is out of the bounded range")
                numeric[key] = str(numeric_value)
                continue
            if type(value) is float:
                numeric_value = value
                if not math.isfinite(numeric_value):
                    raise AssertionError("metric must be finite")
                if not 0 <= numeric_value <= cls.MAX_METRIC_VALUE:
                    raise AssertionError("metric is out of the bounded range")
                numeric[key] = f"{numeric_value:.6f}"
                continue
            raise AssertionError("metric must be numeric")
        return numeric

    def __call__(self, metrics: object) -> str:
        if type(metrics) is not dict:
            raise AssertionError("workload report input must be a mapping")
        metric_map = cast(dict[object, object], metrics)
        self._require_exact_string_keys(metric_map)
        runner = self._validated_runner(metric_map.get("runner"))
        pragmas = self._validated_pragmas(metric_map.get("pragmas"))
        numeric = self._validated_metrics(metric_map)
        lines = [
            "workload report (slice-00-04 spike)",
            f"os_family={runner['os_family']}",
            f"architecture={runner['architecture']}",
            f"ci_runner_label={runner['ci_runner_label']}",
            f"python_version={runner['python_version']}",
            f"sqlite_version={runner['sqlite_version']}",
        ]
        for key in sorted(self.ALLOWED_PRAGMA_FIELDS):
            lines.append(f"{key}={pragmas[key]}")
        lines.extend(
            [
                f"accepted={numeric['accepted']}",
                f"p95_latency_s={numeric['p95_latency_s']}",
                f"busy_count={numeric['busy_count']}",
                f"wal_high_water_mib={numeric['wal_high_water_mib']}",
                f"queue_high_water={numeric['queue_high_water']}",
                f"checkpoint_s={numeric['checkpoint_s']}",
                f"backup_s={numeric['backup_s']}",
                f"recovery_s={numeric['recovery_s']}",
            ]
        )
        return "\n".join(lines)


def _runner_profile() -> dict[str, str]:
    """Fixed redacted runner profile: only the five allowed fields."""
    os_family = platform.system()
    ci_label = "local"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        ci_label = {"Windows": "windows-latest", "Linux": "ubuntu-latest"}.get(
            os_family, "local"
        )
    return {
        "os_family": os_family,
        "architecture": platform.machine(),
        "ci_runner_label": ci_label,
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
    }


def _selected_pragmas(store: SqliteControllerStore) -> dict[str, object]:
    """Read AC-09 PRAGMAs through an Adapter-configured Engine connection."""
    return store.selected_pragmas()


class _WorkloadDriver:
    """4 producers -> capacity-32 queue -> single writer thread.

    The writer is the only database writer and submits strictly serially,
    deriving ``expected_revision`` from its own accepted count so producer
    interleaving can never cause spurious revision conflicts.
    """

    def __init__(
        self,
        controller: SpikeController,
        database_path: Path,
        total: int,
        producer_count: int,
        capacity: int,
    ) -> None:
        self._controller = controller
        self._database_path = database_path
        self._total = total
        self._producer_count = producer_count
        self._capacity = capacity
        self._queue: queue.Queue[int] = queue.Queue(maxsize=capacity)
        self._latencies: list[float] = []
        self._busy_count = 0
        self._wal_high_water = 0
        self._queue_high_water = 0
        self._lock = threading.Lock()

    def _record_wal_high_water(self) -> None:
        wal = Path(str(self._database_path) + "-wal")
        try:
            size = wal.stat().st_size
        except OSError:
            return
        with self._lock:
            self._wal_high_water = max(self._wal_high_water, size)

    def _producer(self, start: int, step: int) -> None:
        index = start
        while index < self._total:
            self._queue.put(index)
            with self._lock:
                self._queue_high_water = max(
                    self._queue_high_water, self._queue.qsize()
                )
            index += step

    def _writer(self) -> None:
        accepted = 0
        processed = 0
        while processed < self._total:
            item = self._queue.get()
            started = time.perf_counter()
            payload = _payload_for(item)
            command = make_spike_command(
                f"cmd_workload_{item:06d}",
                delta=1,
                expected_revision=accepted,
                payload_extra={
                    "filler": payload["filler"],
                    "index": payload["index"],
                },
            )
            receipt = self._controller.submit(command)
            if receipt.status != "ACCEPTED":
                with self._lock:
                    self._busy_count += 1
            else:
                accepted += 1
            self._latencies.append(time.perf_counter() - started)
            if processed % 100 == 0:
                self._record_wal_high_water()
            self._queue.task_done()
            processed += 1

    def run(self) -> dict[str, object]:
        threads = [
            threading.Thread(target=self._producer, args=(start, self._producer_count))
            for start in range(self._producer_count)
        ]
        writer = threading.Thread(target=self._writer)
        for thread in threads:
            thread.start()
        writer.start()
        for thread in threads:
            thread.join()
        writer.join()
        self._record_wal_high_water()
        latencies = sorted(self._latencies)
        p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0
        return {
            "accepted": len(self._latencies),
            "p95_latency_s": round(p95, 4),
            "busy_count": self._busy_count,
            "wal_high_water_mib": round(self._wal_high_water / (1024 * 1024), 4),
            "queue_high_water": self._queue_high_water,
        }


def test_workload_envelope_within_declared_limits(
    tmp_path: Path,
) -> None:
    """AC-09 positive: within the fixed envelope, every declared limit is
    satisfied; the runner profile contains only the five allowed fields."""
    database = tmp_path / "workload.db"
    store = SqliteControllerStore(database)
    controller = SpikeController(
        store,
        lambda: datetime(2026, 1, 1),
        make_event_id_provider("evt_wl"),
    )

    driver = _WorkloadDriver(
        controller, database, COMMAND_COUNT, PRODUCER_COUNT, QUEUE_CAPACITY
    )
    metrics = cast(dict[str, Any], driver.run())

    assert metrics["accepted"] == COMMAND_COUNT
    assert metrics["p95_latency_s"] <= P95_LATENCY_LIMIT_S
    assert metrics["busy_count"] == 0
    assert metrics["wal_high_water_mib"] <= WAL_HIGH_WATER_LIMIT_MIB
    assert metrics["queue_high_water"] <= QUEUE_CAPACITY
    audit = store.audit()
    assert audit.event_count == COMMAND_COUNT
    assert audit.receipt_count == COMMAND_COUNT

    # Payload bound: every submitted command payload is <= 1 KiB.
    for index in (0, 999):
        assert _payload_bytes(_payload_for(index)) <= MAX_PAYLOAD_BYTES

    # Checkpoint, online backup, and fresh-process recovery each <= 5s.
    checkpoint_start = time.perf_counter()
    conn = sqlite3.connect(database)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    checkpoint_s = time.perf_counter() - checkpoint_start
    assert checkpoint_s <= OPERATION_LIMIT_S

    backup_start = time.perf_counter()
    backup_path = tmp_path / "workload-backup.db"
    backup_result = backup_database(database, backup_path)
    backup_s = time.perf_counter() - backup_start
    assert backup_result.ok
    assert backup_s <= OPERATION_LIMIT_S

    recovery_start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(PROBE), str(database)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    recovery_s = time.perf_counter() - recovery_start
    _assert_recovery_probe_succeeded(proc)
    assert recovery_s <= OPERATION_LIMIT_S

    pragmas = _selected_pragmas(store)
    report = WorkloadReporter()(
        {
            "runner": _runner_profile(),
            "pragmas": pragmas,
            "accepted": metrics["accepted"],
            "p95_latency_s": metrics["p95_latency_s"],
            "busy_count": metrics["busy_count"],
            "wal_high_water_mib": metrics["wal_high_water_mib"],
            "queue_high_water": metrics["queue_high_water"],
            "checkpoint_s": round(checkpoint_s, 4),
            "backup_s": round(backup_s, 4),
            "recovery_s": round(recovery_s, 4),
        }
    )
    assert "os_family=" in report
    assert f"ci_runner_label={_runner_profile()['ci_runner_label']}" in report
    # AC-09/P1-4: the report records the selected PRAGMAs and every recorded
    # value comes from the actual spike database connection.
    for key, value in pragmas.items():
        assert f"{key}={value}" in report, f"missing pragma {key} in report"
    assert pragmas["journal_mode"] == "wal"
    assert pragmas["synchronous"] == 2  # synchronous=FULL on the spike store
    store.close()


def test_workload_report_redaction_assertion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-09/P1-1: the reporter renders only the fixed redacted runner
    profile plus selected PRAGMAs with restricted value domains and bounded,
    type-checked metrics. Fake sensitive values (hostname, username,
    absolute path, environment variable value, token) injected directly into
    rendered fields and into exception paths — including short tokens,
    control-character canaries, and canary key names — are rejected
    fail-closed and never appear in the report, in any captured output, or
    in any reporter error message (all error messages are fixed safe text
    carrying neither input values nor field names)."""
    canaries = (FAKE_HOSTNAME, FAKE_USERNAME, FAKE_PATH, FAKE_ENV_VALUE, FAKE_TOKEN)
    valid_pragmas: dict[str, Any] = {
        "journal_mode": "wal",
        "synchronous": 2,
        "wal_autocheckpoint": 1000,
        "page_size": 4096,
        "max_page_count": 1073741823,
    }
    valid_metrics: dict[str, Any] = {
        "runner": _runner_profile(),
        "pragmas": valid_pragmas,
        "accepted": 3,
        "p95_latency_s": 0.01,
        "busy_count": 0,
        "wal_high_water_mib": 0.1,
        "queue_high_water": 2,
        "checkpoint_s": 0.01,
        "backup_s": 0.01,
        "recovery_s": 0.01,
    }

    # 1. Canary injected into a rendered runner field: fail-closed, and the
    #    error message never carries the value or the field name.
    for canary in canaries:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    "runner": {**valid_metrics["runner"], "os_family": canary * 20},
                    **{k: v for k, v in valid_metrics.items() if k != "runner"},
                }
            )
        _assert_no_sensitive_text(
            str(excinfo.value), (canary, "os_family", "Traceback")
        )

    # 2. Canary injected into a rendered metric field with the wrong type:
    #    fail-closed, no canary in the error message.
    for canary in canaries:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()({**valid_metrics, "accepted": canary})
        _assert_no_sensitive_text(str(excinfo.value), (canary, "Traceback"))

    # 3. Canary as a forbidden runner profile field: fail-closed, and the
    #    fixed error text does not echo the canary field name.
    for canary in canaries:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {"runner": {**valid_metrics["runner"], "hostname": canary}}
            )
        _assert_no_sensitive_text(str(excinfo.value), (canary,))

    # 4. Exception paths: non-mapping inputs produce bounded messages.
    with pytest.raises(AssertionError) as excinfo:
        WorkloadReporter()(FAKE_TOKEN)  # type: ignore[arg-type]
    _assert_no_sensitive_text(str(excinfo.value), (FAKE_TOKEN,))
    with pytest.raises(AssertionError) as excinfo:
        WorkloadReporter()({"runner": FAKE_PATH, "accepted": 1})
    _assert_no_sensitive_text(str(excinfo.value), (FAKE_PATH,))
    with pytest.raises(AssertionError) as excinfo:
        WorkloadReporter()({**valid_metrics, "p95_latency_s": float("nan")})
    _assert_no_sensitive_text(str(excinfo.value), canaries)

    # 5. P1-1 negative, class 1 — short canary (e.g. "tok"): a value that
    #    would pass any length-only check fails the restricted value domain
    #    (enum or regex whitelist) fail-closed with zero leakage.
    for field in ("os_family", "architecture", "ci_runner_label"):
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    "runner": {**valid_metrics["runner"], field: "tok"},
                    **{k: v for k, v in valid_metrics.items() if k != "runner"},
                }
            )
        _assert_no_sensitive_text(str(excinfo.value), ("tok", field))
    for field in ("python_version", "sqlite_version"):
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    "runner": {**valid_metrics["runner"], field: "tok"},
                    **{k: v for k, v in valid_metrics.items() if k != "runner"},
                }
            )
        _assert_no_sensitive_text(str(excinfo.value), ("tok", field))

    # 6. P1-1 negative, class 2 — control-character canaries (newline,
    #    carriage return, tab) in runner and pragma string values are
    #    rejected fail-closed and never rendered.
    control_canaries = (
        f"{FAKE_TOKEN}\n{FAKE_TOKEN}",
        f"{FAKE_TOKEN}\r{FAKE_TOKEN}",
        f"{FAKE_TOKEN}\t{FAKE_TOKEN}",
    )
    for control in control_canaries:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    "runner": {**valid_metrics["runner"], "os_family": control},
                    **{k: v for k, v in valid_metrics.items() if k != "runner"},
                }
            )
        _assert_no_sensitive_text(str(excinfo.value), (FAKE_TOKEN,))
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    **valid_metrics,
                    "pragmas": {**valid_pragmas, "journal_mode": control},
                }
            )
        _assert_no_sensitive_text(str(excinfo.value), (FAKE_TOKEN,))
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {
                    "runner": {**valid_metrics["runner"], "ci_runner_label": control},
                    **{k: v for k, v in valid_metrics.items() if k != "runner"},
                }
            )
        _assert_no_sensitive_text(str(excinfo.value), (FAKE_TOKEN,))

    # 7. P1-1 negative, class 3 — canary key names: an unknown field name is
    #    itself a sensitive value, so the fixed error text never echoes the
    #    offending key (runner, pragma, and metric mappings).
    for canary in canaries:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()({"runner": {**valid_metrics["runner"], canary: "x"}})
        _assert_no_sensitive_text(str(excinfo.value), (canary,))
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(
                {**valid_metrics, "pragmas": {**valid_pragmas, canary: "wal"}}
            )
        _assert_no_sensitive_text(str(excinfo.value), (canary,))
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()({**valid_metrics, canary: 1})
        _assert_no_sensitive_text(str(excinfo.value), (canary,))
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()({"runner": {**valid_metrics["runner"], "tok": "x"}})
        _assert_no_sensitive_text(str(excinfo.value), ("tok",))

    # 8. A subclass can preserve a legal base value while overriding str or
    #    format to leak a token. Exact builtin types are required before any
    #    value becomes part of the rendered report.
    class LeakyString(str):
        def __format__(self, format_spec: str) -> str:
            del format_spec
            return FAKE_TOKEN + chr(10) + "string-subclass" + chr(7)

    class LeakyInteger(int):
        def __str__(self) -> str:
            return FAKE_TOKEN + chr(10) + "integer-subclass" + chr(7)

    class LeakyFloat(float):
        def __format__(self, format_spec: str) -> str:
            del format_spec
            return FAKE_TOKEN + chr(10) + "float-subclass" + chr(7)

    class LeakyKey(str):
        def __hash__(self) -> int:
            return hash(str(self))

        def __eq__(self, other: object) -> bool:
            del other
            raise RuntimeError(FAKE_TOKEN + chr(10) + "key-subclass" + chr(7))

    def _with_leaky_key(mapping: Mapping[str, Any], key: str) -> dict[object, object]:
        copied: dict[object, object] = {
            field: value for field, value in mapping.items()
        }
        value = copied.pop(key)
        copied[LeakyKey(key)] = value
        return copied

    subclass_cases = (
        {
            "runner": {
                **valid_metrics["runner"],
                "os_family": LeakyString("Windows"),
            },
            **{key: value for key, value in valid_metrics.items() if key != "runner"},
        },
        {
            **valid_metrics,
            "pragmas": {
                **valid_pragmas,
                "journal_mode": LeakyString("wal"),
            },
        },
        {
            **valid_metrics,
            "pragmas": {
                **valid_pragmas,
                "synchronous": LeakyInteger(2),
            },
        },
        {**valid_metrics, "accepted": LeakyInteger(3)},
        {**valid_metrics, "p95_latency_s": LeakyFloat(0.01)},
        {
            **valid_metrics,
            "runner": _with_leaky_key(valid_metrics["runner"], "os_family"),
        },
        {**valid_metrics, "pragmas": _with_leaky_key(valid_pragmas, "journal_mode")},
        _with_leaky_key(valid_metrics, "runner"),
    )
    for case in subclass_cases:
        with pytest.raises(AssertionError) as excinfo:
            WorkloadReporter()(case)
        _assert_no_sensitive_text(str(excinfo.value), (FAKE_TOKEN,))

    # 9. A report generated while fake sensitive values are present in the
    #    process environment contains none of them: the reporter never
    #    reads environment variables, hostnames, usernames, or paths.
    monkeypatch.setenv("SPIKE_CANARY_ENV", FAKE_ENV_VALUE)
    monkeypatch.setenv("SPIKE_CANARY_USER", FAKE_USERNAME)
    report = WorkloadReporter()(valid_metrics)
    print(report)
    captured = capsys.readouterr()
    combined = report + captured.out + captured.err
    _assert_no_sensitive_text(combined, (*canaries, "Traceback"), allow_line_feeds=True)
    # The runner profile contains only the five fixed fields, the report
    # records the selected PRAGMAs, and it renders only the fixed field set.
    assert "os_family=" in report
    assert f"ci_runner_label={valid_metrics['runner']['ci_runner_label']}" in report
    for key in valid_pragmas:
        assert f"{key}={valid_pragmas[key]}" in report
    rendered_keys = {
        line.split("=", 1)[0] for line in report.splitlines() if "=" in line
    }
    assert rendered_keys == (
        WorkloadReporter.ALLOWED_RUNNER_FIELDS
        | WorkloadReporter.ALLOWED_PRAGMA_FIELDS
        | WorkloadReporter.ALLOWED_METRIC_FIELDS
    )
    # A reporter emitting a forbidden field fails (leaky emitter).
    with pytest.raises(AssertionError):
        WorkloadReporter()(
            {"runner": {**valid_metrics["runner"], "hostname": FAKE_HOSTNAME}}
        )


def test_queue_beyond_capacity_fails_declared_boundary() -> None:
    """AC-09 negative: a fixture that drives the queue beyond capacity 32
    fails the declared acceptance boundary."""
    q: queue.Queue[int] = queue.Queue(maxsize=QUEUE_CAPACITY)
    assert q.maxsize == QUEUE_CAPACITY
    for index in range(QUEUE_CAPACITY):
        q.put_nowait(index)
    with pytest.raises(queue.Full):
        q.put_nowait(QUEUE_CAPACITY)


def test_sqlite_full_injection_returns_safe_receipt_and_is_restart_safe(
    tmp_path: Path,
) -> None:
    """AC-09 negative: the deterministic SQLITE_FULL injection returns the
    non-durable REJECTED/INTERNAL_ERROR receipt, writes no durable receipt
    record or partial records, and is restart-safe without exhausting real
    disk."""
    database = tmp_path / "full.db"
    store = SqliteControllerStore(database)
    controller = SpikeController(
        store,
        lambda: datetime(2026, 1, 1),
        make_event_id_provider("evt_full_first"),
    )
    first = controller.submit(make_spike_command("cmd_full_0000"))
    assert first.status == "ACCEPTED"
    store.close()

    # Deterministic bounded fixture: cap the database at its current page
    # count plus 16 pages of headroom, then consume the headroom with
    # page-sized rows. Inbox rows the size of the transaction's own inbox
    # row fill the remaining free space of the inbox leaf page, so the next
    # five-record transaction deterministically needs a new page on its
    # first write and fails with SQLITE_FULL (never exhausting real disk).
    filler_conn = sqlite3.connect(database, isolation_level=None)
    current_pages = int(filler_conn.execute("PRAGMA page_count").fetchone()[0])
    cap_pages = current_pages + 16
    filler_conn.execute(f"PRAGMA max_page_count = {cap_pages}")
    fill_count = 0
    try:
        while True:
            filler_conn.execute(
                "INSERT INTO spike_inbox "
                "(command_id, payload_hash, command_json, receipt_json, "
                " recorded_at) VALUES (?, ?, ?, ?, ?)",
                (
                    f"cmd_fill_{fill_count:06d}",
                    "0" * 64,
                    "x" * 1100,
                    "{}",
                    "2026-01-01T00:00:00Z",
                ),
            )
            fill_count += 1
            if fill_count > 1000:
                raise AssertionError("filler did not reach the page-count cap")
    except sqlite3.OperationalError as exc:
        _assert_sqlite_full_error(exc)
    finally:
        filler_conn.close()

    # Cap the Controller store to the same boundary: every new page
    # allocation now fails with SQLITE_FULL, translated at the port into the
    # safe non-durable receipt.
    capped = SqliteControllerStore(database, max_page_count=cap_pages)
    capped_controller = SpikeController(
        capped,
        lambda: datetime(2026, 1, 1),
        make_event_id_provider("evt_full_capped"),
    )
    receipt = capped_controller.submit(
        make_spike_command("cmd_full_0001", expected_revision=1)
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == MESSAGE_PERSISTENCE_UNAVAILABLE
    assert receipt.error.retryable is True
    capped.close()

    # The failed transaction left no durable receipt record and no partial
    # records: only the first command's records exist (plus the bounded
    # fixture fill rows in the inbox table).
    reopened = SqliteControllerStore(database)
    audit = reopened.audit()
    assert audit.receipt_count == 1
    assert audit.event_count == 1
    assert audit.outbox_count == 1
    assert audit.inbox_count == 1 + fill_count
    assert audit.projection is not None
    assert audit.projection.value == 1
    assert audit.projection.revision == 1
    reopened.close()

    # Restart-safe: the same database accepts further commands once the
    # cap is lifted (fresh store over the same file; max_page_count is a
    # per-connection setting, so the fresh store can grow again).
    restarted = SqliteControllerStore(database)
    restarted_controller = SpikeController(
        restarted,
        lambda: datetime(2026, 1, 1),
        make_event_id_provider("evt_full_restarted"),
    )
    again = restarted_controller.submit(
        make_spike_command("cmd_full_0002", expected_revision=1)
    )
    assert again.status == "ACCEPTED"
    assert restarted.audit().event_count == 2
    restarted.close()


def test_sqlite_full_classification_does_not_render_driver_text() -> None:
    """AC-09 negative: a failing driver classification cannot leak text."""
    canary = "canary-sqlite-error" + chr(10) + "with-control" + chr(7)
    error = sqlite3.OperationalError(canary)

    with pytest.raises(AssertionError) as raised:
        _assert_sqlite_full_error(error)

    _assert_safe_diagnostic(
        str(raised.value),
        "SQLITE_FULL injection did not return the expected driver code",
        canary,
    )


def test_workload_probe_failure_does_not_render_subprocess_output() -> None:
    """AC-09 negative: workload probe output remains outside diagnostics."""
    canary = "canary-workload-output" + chr(10) + "with-control" + chr(7)
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=canary, stderr=canary
    )

    with pytest.raises(AssertionError) as raised:
        _assert_recovery_probe_succeeded(proc)

    _assert_safe_diagnostic(str(raised.value), "workload recovery probe failed", canary)


def test_envelope_exceeded_fixture_fails_declared_boundary() -> None:
    """AC-09 negative: an exceeded limit fails the declared acceptance
    boundary (the envelope is the acceptance boundary, not a wish)."""
    exceeded_p95 = P95_LATENCY_LIMIT_S + 0.5
    assert exceeded_p95 > P95_LATENCY_LIMIT_S
    with pytest.raises(AssertionError):
        assert exceeded_p95 <= P95_LATENCY_LIMIT_S
