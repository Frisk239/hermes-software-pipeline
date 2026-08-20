from __future__ import annotations

import json
import sys


def _read() -> dict[str, object]:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line in (b"", b"\r\n", b"\n"):
            if headers:
                break
            if line == b"":
                raise SystemExit(0)
            continue
        key, _, value = line.decode().partition(":")
        headers[key.strip().lower()] = value.strip()
    size = int(headers.get("content-length", "0"))
    loaded = json.loads(sys.stdin.buffer.read(size))
    if not isinstance(loaded, dict):
        raise SystemExit(1)
    return loaded


def _write(payload: dict[str, object]) -> None:
    raw = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
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
            params = msg.get("params", {})
            name = ""
            if isinstance(params, dict):
                name = str(params.get("name", ""))
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
