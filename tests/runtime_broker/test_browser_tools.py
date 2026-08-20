from __future__ import annotations

import ast
import hashlib
import io
import sys
import zipfile
from pathlib import Path

from hermes_pipeline.runtime_broker.browser_tools import (
    LOCK_DIR,
    BrowserPins,
    BrowserToolsError,
    materialize_browser_tools,
)
from hermes_pipeline.runtime_broker.chrome_mcp import closed_mcp_argv

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_SPIKES = frozenset(
    {
        "hermes_pipeline.runtime_broker._e2e",
        "hermes_pipeline.runtime_broker._host",
        "hermes_pipeline.runtime_broker.controlled_e2e",
        "hermes_pipeline.runtime_broker.tools_bootstrap",
        "hermes_pipeline.runtime_broker._identity",
        "hermes_pipeline.runtime_broker._provision",
    }
)
_SPIKE_FILE = _SRC / "runtime_broker" / "browser_tools.py"
_DOCS_LOCK = (
    Path(__file__).resolve().parents[2]
    / "docs/roadmap/phase-00-foundation/slices/"
    / "00-06-agent-runtime-security-spikes"
)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, payload in entries.items():
            zipped.writestr(name, payload)
    return buffer.getvalue()


def _node_archive() -> bytes:
    if sys.platform == "win32":
        return _zip_bytes(
            {
                "node-v22.23.2-win-x64/node.exe": b"node",
                "node-v22.23.2-win-x64/npm.cmd": b"npm",
            }
        )
    return _zip_bytes(
        {
            "node-v22.23.2-linux-x64/bin/node": b"node",
            "node-v22.23.2-linux-x64/bin/npm": b"npm",
        }
    )


def _cft_archive() -> bytes:
    if sys.platform == "win32":
        return _zip_bytes({"chrome-win64/chrome.exe": b"chrome"})
    return _zip_bytes({"chrome-linux64/chrome": b"chrome"})


def _pins(node_archive: bytes) -> BrowserPins:
    base = BrowserPins(
        node_url="https://nodejs.org/dist/test/node.zip",
        node_sha256=hashlib.sha256(node_archive).hexdigest(),
        cft_url="https://storage.googleapis.com/chrome-for-testing-public/test.zip",
    )
    return base


def _npm(argv: list[str], cwd: Path, env: dict[str, str]) -> int:
    del env
    assert "npm" in Path(argv[0]).name.lower()
    assert "--ignore-scripts" in argv
    mcp = cwd / "node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"
    mcp.parent.mkdir(parents=True, exist_ok=True)
    mcp.write_text("mcp", encoding="utf-8")
    return 0


def test_lock_files_match_00_06_bytes() -> None:
    for name in ("package.json", "package-lock.json", ".npmrc"):
        assert (LOCK_DIR / name).read_bytes() == (_DOCS_LOCK / name).read_bytes()


def test_materialize_writes_closed_argv_paths(tmp_path: Path) -> None:
    node = _node_archive()
    cft = _cft_archive()
    urls = {
        "https://nodejs.org/dist/test/node.zip": node,
        "https://storage.googleapis.com/chrome-for-testing-public/test.zip": cft,
    }

    def fetch(url: str) -> bytes:
        return urls[url]

    materialize_browser_tools(
        tmp_path,
        fetch=fetch,
        npm=_npm,
        pins=_pins(node),
    )
    argv = closed_mcp_argv(tmp_path, 4317)
    assert argv is not None
    assert argv[1].endswith("chrome-devtools-mcp.js")

    def refuse_fetch(url: str) -> bytes:
        raise AssertionError(url)

    def refuse_npm(argv: list[str], cwd: Path, env: dict[str, str]) -> int:
        del argv, cwd, env
        raise AssertionError("npm")

    materialize_browser_tools(
        tmp_path,
        fetch=refuse_fetch,
        npm=refuse_npm,
        pins=_pins(node),
    )


def test_bad_node_digest_fails_closed(tmp_path: Path) -> None:
    node = _node_archive()
    pins = BrowserPins(
        node_url="https://nodejs.org/dist/test/node.zip",
        node_sha256="0" * 64,
        cft_url="https://storage.googleapis.com/chrome-for-testing-public/test.zip",
    )

    def fetch(url: str) -> bytes:
        del url
        return node

    try:
        materialize_browser_tools(tmp_path, fetch=fetch, npm=_npm, pins=pins)
    except BrowserToolsError as exc:
        assert exc.code == "node_sha"
    else:
        raise AssertionError("expected fail")
    assert closed_mcp_argv(tmp_path, 80) is None


def test_zip_slip_fails_closed(tmp_path: Path) -> None:
    node = _zip_bytes({"../escape.exe": b"x"})
    pins = _pins(node)

    def fetch(url: str) -> bytes:
        return node if "node" in url else _cft_archive()

    try:
        materialize_browser_tools(tmp_path, fetch=fetch, npm=_npm, pins=pins)
    except BrowserToolsError as exc:
        assert exc.code == "path_escape"
    else:
        raise AssertionError("expected fail")


def test_does_not_import_keep_marked_probes() -> None:
    imported = _imported_names(_SPIKE_FILE)
    assert imported.isdisjoint(_SPIKES)
