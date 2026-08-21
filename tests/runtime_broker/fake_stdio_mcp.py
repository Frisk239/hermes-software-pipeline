from __future__ import annotations

import json
import sys
from typing import Any, cast


def _read() -> dict[str, object]:
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            raise SystemExit(0)
        stripped = line.strip()
        if not stripped:
            continue
        loaded = json.loads(stripped.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise SystemExit(1)
        return cast(dict[str, object], loaded)


def _write(payload: dict[str, object]) -> None:
    sys.stdout.buffer.write(json.dumps(payload).encode() + b"\n")
    sys.stdout.buffer.flush()


def main() -> None:
    seen: list[str] = []
    while True:
        msg = _read()
        method = str(msg.get("method", ""))
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "fake", "version": "0"},
                    },
                }
            )
        elif method == "tools/call":
            params: Any = msg.get("params", {})
            name = ""
            if isinstance(params, dict):
                typed = cast(dict[str, Any], params)
                name = str(typed.get("name", ""))
            seen.append(name)
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "content": [{"type": "text", "text": f"login-ok {name}"}]
                    },
                }
            )
            if len(seen) == 2:
                sys.stderr.write(",".join(seen))
                sys.stderr.flush()


if __name__ == "__main__":
    main()
