"""Fresh-process recovery probe for AC-05/AC-09 (slice-00-04 spike,
SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Opens a database in a *fresh process* (same database and WAL) and prints a
bounded JSON audit to stdout:

- inbox/event/outbox/receipt counts;
- projection value/revision;
- whether the Event hash chain verifies;
- a hash-chain integrity verdict for the whole file.

Usage: python _recovery_probe.py <database>
Exit code 0 when the audit is readable and the chain verifies.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from hermes_pipeline.persistence.event_chain import verify_chain


def audit(database: str) -> dict[str, object]:
    conn = sqlite3.connect(database)
    try:
        inbox = int(conn.execute("SELECT COUNT(*) FROM spike_inbox").fetchone()[0])
        events = int(conn.execute("SELECT COUNT(*) FROM spike_events").fetchone()[0])
        outbox = int(conn.execute("SELECT COUNT(*) FROM spike_outbox").fetchone()[0])
        receipts = int(
            conn.execute("SELECT COUNT(*) FROM spike_receipts").fetchone()[0]
        )
        projection = conn.execute(
            "SELECT value, revision FROM spike_projection WHERE id = 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT sequence, previous_event_hash, event_hash, payload_json "
            "FROM spike_events ORDER BY sequence"
        ).fetchall()
    finally:
        conn.close()
    chain_rows = [
        (int(r[0]), str(r[1]) if r[1] is not None else None, str(r[2]), str(r[3]))
        for r in rows
    ]
    try:
        verify_chain(chain_rows)
        chain_ok = True
        chain_detail = ""
    except ValueError:
        chain_ok = False
        chain_detail = "chain verification failed"
    size = Path(database).stat().st_size
    return {
        "inbox": inbox,
        "events": events,
        "outbox": outbox,
        "receipts": receipts,
        "projection_value": int(projection[0]) if projection else None,
        "projection_revision": int(projection[1]) if projection else None,
        "chain_ok": chain_ok,
        "chain_detail": chain_detail,
        "bytes": size,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: _recovery_probe.py <database>")
        return 2
    try:
        result = audit(argv[0])
    except Exception:
        print(json.dumps({"error": "probe failed"}))
        return 1
    print(json.dumps(result))
    return 0 if result["chain_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
