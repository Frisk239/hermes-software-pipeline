"""Materialize locked browser tools into a disposable verify sandbox."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import urlopen

from hermes_pipeline.runtime_broker.chrome_mcp import closed_mcp_argv
from hermes_pipeline.runtime_broker.fence import cleaned_child_env

LOCK_DIR = Path(__file__).resolve().parent / "browser_lock"
PACKAGE_DIGEST = "753a18ae9548e51fa57ae7f8e80b2a2208028ad015cb91ceadfe1625bb034a31"
LOCKFILE_DIGEST = "f691d5dae8a9a8129cdbe6fcd603e562d60360b843703140b9ff9fbb466d8bb9"
NPMRC_DIGEST = "d61adb1098d59a10d2ec140829cad10d4613c8ba1ddcab0cbd8d56b06a5fa543"
MCP_SRI = (
    "sha512-6xFW7oiUxTxZuHcfyYBkKQtmttjCbfifKZMSEk5CV8H2"
    "FucvKweYiJr8CblddYHtYjA4C14K9VAs1r49906RBA=="
)
NODE_WIN_URL = "https://nodejs.org/dist/v22.23.2/node-v22.23.2-win-x64.zip"
NODE_WIN_SHA = "1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97"
NODE_LINUX_URL = "https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz"
NODE_LINUX_SHA = "d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307"
CFT_WIN_URL = (
    "https://storage.googleapis.com/chrome-for-testing-public/"
    "151.0.7922.77/win64/chrome-win64.zip"
)
CFT_LINUX_URL = (
    "https://storage.googleapis.com/chrome-for-testing-public/"
    "151.0.7922.77/linux64/chrome-linux64.zip"
)
_ALLOWED_HOSTS = frozenset(
    {"nodejs.org", "storage.googleapis.com", "registry.npmjs.org"}
)
Fetcher = Callable[[str], bytes]
NpmRunner = Callable[[list[str], Path, dict[str, str]], int]


class BrowserToolsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ArchiveFetcher(Protocol):
    def get(self, url: str) -> bytes: ...


@dataclass(frozen=True)
class BrowserPins:
    node_url: str
    node_sha256: str
    cft_url: str
    package_digest: str = PACKAGE_DIGEST
    lockfile_digest: str = LOCKFILE_DIGEST
    npmrc_digest: str = NPMRC_DIGEST


def default_pins() -> BrowserPins:
    if sys.platform == "win32":
        return BrowserPins(NODE_WIN_URL, NODE_WIN_SHA, CFT_WIN_URL)
    return BrowserPins(NODE_LINUX_URL, NODE_LINUX_SHA, CFT_LINUX_URL)


def https_fetch(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise BrowserToolsError("url")
    with urlopen(url, timeout=120) as response:
        return response.read()


def subprocess_npm(argv: list[str], cwd: Path, env: dict[str, str]) -> int:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    return int(completed.returncode)


def materialize_browser_tools(
    state_root: Path,
    *,
    fetch: Fetcher | None = None,
    npm: NpmRunner | None = None,
    lock_dir: Path | None = None,
    pins: BrowserPins | None = None,
) -> None:
    root = state_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if closed_mcp_argv(root, 80) is not None:
        return
    chosen = pins if pins is not None else default_pins()
    inputs = lock_dir if lock_dir is not None else LOCK_DIR
    _verify_lock_inputs(inputs, chosen)
    _place_npm_project(root, inputs)
    getter = fetch if fetch is not None else https_fetch
    _place_node(root, getter(chosen.node_url), chosen.node_sha256)
    _place_cft(root, getter(chosen.cft_url))
    runner = npm if npm is not None else subprocess_npm
    _run_npm_ci(root, runner)
    if closed_mcp_argv(root, 80) is None:
        raise BrowserToolsError("incomplete")


def _verify_lock_inputs(lock_dir: Path, pins: BrowserPins) -> None:
    package = lock_dir / "package.json"
    lockfile = lock_dir / "package-lock.json"
    npmrc = lock_dir / ".npmrc"
    _require_digest(package, pins.package_digest)
    _require_digest(lockfile, pins.lockfile_digest)
    _require_digest(npmrc, pins.npmrc_digest)
    manifest = json.loads(package.read_text(encoding="utf-8"))
    if manifest.get("name") != "hermes-browser-runtime":
        raise BrowserToolsError("name")
    deps = manifest.get("dependencies", {})
    if deps.get("chrome-devtools-mcp") != "1.7.0":
        raise BrowserToolsError("pin")
    document = json.loads(lockfile.read_text(encoding="utf-8"))
    packages = document.get("packages", {})
    mcp = packages.get("node_modules/chrome-devtools-mcp", {})
    if mcp.get("integrity") != MCP_SRI:
        raise BrowserToolsError("sri")


def _place_npm_project(root: Path, lock_dir: Path) -> None:
    project = root / "tools" / "browser-runtime" / "project"
    project.mkdir(parents=True, exist_ok=True)
    _copy_file(lock_dir / "package.json", project / "package.json")
    _copy_file(lock_dir / "package-lock.json", project / "package-lock.json")
    runtime = root / "tools" / "browser-runtime"
    _copy_file(lock_dir / ".npmrc", runtime / "npmrc")
    (runtime / "empty-global-npmrc").write_text("", encoding="utf-8")


def _place_node(root: Path, archive: bytes, expected_sha256: str) -> None:
    digest = hashlib.sha256(archive).hexdigest()
    if digest != expected_sha256:
        raise BrowserToolsError("node_sha")
    dest = (
        root / "tools" / "node" / "windows-x64"
        if sys.platform == "win32"
        else root / "tools" / "node" / "linux-x64"
    )
    dest.mkdir(parents=True, exist_ok=True)
    _extract_archive(archive, dest, root)


def _place_cft(root: Path, archive: bytes) -> None:
    dest = (
        root / "tools" / "browser-runtime" / "chrome-for-testing" / "win64"
        if sys.platform == "win32"
        else root / "tools" / "browser-runtime" / "chrome-for-testing" / "linux64"
    )
    dest.mkdir(parents=True, exist_ok=True)
    _extract_archive(archive, dest, root)


def _run_npm_ci(root: Path, npm: NpmRunner) -> None:
    npm_exe = _npm_executable(root)
    if npm_exe is None:
        raise BrowserToolsError("npm")
    argv = [
        str(npm_exe),
        "ci",
        "--ignore-scripts",
        "--audit=false",
        "--fund=false",
        "--update-notifier=false",
        "--cache",
        str(root / "tools" / "npm-cache"),
        "--userconfig",
        str(root / "tools" / "browser-runtime" / "npmrc"),
        "--globalconfig",
        str(root / "tools" / "browser-runtime" / "empty-global-npmrc"),
    ]
    npm_path = Path(argv[0]).resolve()
    if not _under(root, npm_path):
        raise BrowserToolsError("path_npm")
    env = cleaned_child_env()
    env["CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS"] = "1"
    code = npm(argv, root / "tools" / "browser-runtime" / "project", env)
    if code != 0:
        raise BrowserToolsError("npm_ci")


def _npm_executable(root: Path) -> Path | None:
    if sys.platform == "win32":
        path = root / "tools/node/windows-x64/node-v22.23.2-win-x64/npm.cmd"
    else:
        path = root / "tools/node/linux-x64/node-v22.23.2-linux-x64/bin/npm"
    if path.is_file() and _under(root, path.resolve()):
        return path
    return None


def _extract_archive(archive: bytes, dest: Path, root: Path) -> None:
    if archive[:2] == b"PK":
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            for name in zipped.namelist():
                _assert_member(dest, name, root)
            zipped.extractall(dest)
        return
    with tarfile.open(fileobj=BytesIO(archive), mode="r:*") as tarred:
        for member in tarred.getmembers():
            _assert_member(dest, member.name, root)
        tarred.extractall(dest, filter="data")


def _assert_member(dest: Path, name: str, root: Path) -> None:
    if name.startswith("/") or ".." in Path(name).parts:
        raise BrowserToolsError("path_escape")
    target = (dest / name).resolve()
    if not _under(root, target):
        raise BrowserToolsError("path_escape")


def _copy_file(source: Path, dest: Path) -> None:
    dest.write_bytes(source.read_bytes())


def _require_digest(path: Path, expected: str) -> None:
    if not path.is_file():
        raise BrowserToolsError("lock_missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise BrowserToolsError("digest")


def _under(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "LOCK_DIR",
    "BrowserPins",
    "BrowserToolsError",
    "default_pins",
    "https_fetch",
    "materialize_browser_tools",
]
