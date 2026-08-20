from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlparse

from hermes_pipeline.contracts.definitions import FixedV1Integer, Sha256Ref
from hermes_pipeline.contracts.jcs import content_hash
from hermes_pipeline.contracts.runtime import (
    CapabilityProfile,
    Filesystem,
    Network,
    Resources,
)

_SCHEMA_ID = "https://schemas.hermes-pipeline.dev/runtime/capability-profile/v1"
_PLACEHOLDER_HASH = Sha256Ref("sha256:" + "0" * 64)
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC = re.compile(r"^\\\\[^\\]+\\[^\\]")
_KNOWN_KINDS = frozenset(
    {
        "READ_PATH",
        "WRITE_PATH",
        "EXECUTABLE",
        "NETWORK",
        "BROWSER",
        "SECRET",
        "SIDE_EFFECT",
    }
)
_DEFAULT_RESOURCES = Resources(
    wall_time_ms=600000,
    output_bytes=1048576,
    processes=4,
)
StageType = Literal["PRD", "ARCHITECTURE", "DEVELOPMENT", "E2E", "ACCEPTANCE"]
BrowserType = Literal["NONE", "CHROME_DEVTOOLS_MCP"]
NetworkMode = Literal["DENY_ALL", "ALLOW_LIST"]
SideEffect = Literal["NONE", "LOCAL_BUILD", "LOCAL_TEST", "BROWSER_TEST"]
PathStyle = Literal["windows", "posix"]


@dataclass(frozen=True)
class CapabilityRequest:
    kind: str
    target: str


@dataclass(frozen=True)
class CapabilityVerdict:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class _NormPath:
    style: PathStyle
    parts: tuple[str, ...]


def compile_profile(
    *,
    write_roots: Sequence[str],
    read_roots: Sequence[str] | None = None,
    executables: Sequence[str] = (),
    network_mode: NetworkMode = "DENY_ALL",
    network_allow: Sequence[str] = (),
    secrets: Sequence[str] = (),
    browser: BrowserType = "NONE",
    side_effects: Sequence[SideEffect] = (),
    stage_type: StageType = "DEVELOPMENT",
    profile_id: str = "cap_development",
    profile_revision: int = 1,
    resources: Resources | None = None,
) -> CapabilityProfile:
    roots_write = list(write_roots)
    roots_read = list(read_roots) if read_roots is not None else list(roots_write)
    profile = CapabilityProfile(
        schema_id=_SCHEMA_ID,
        schema_version=FixedV1Integer(1),
        profile_id=profile_id,
        profile_revision=profile_revision,
        stage_type=stage_type,
        filesystem=Filesystem(read_roots=roots_read, write_roots=roots_write),
        executables=list(executables),
        network=Network(mode=network_mode, allow=list(network_allow)),
        secrets=list(secrets),
        browser=browser,
        resources=resources if resources is not None else _DEFAULT_RESOURCES,
        side_effects=list(side_effects),
        content_hash=_PLACEHOLDER_HASH,
    )
    document = profile.model_dump(mode="json")
    return profile.model_copy(
        update={"content_hash": Sha256Ref(content_hash(document))}
    )


def evaluate(
    profile: CapabilityProfile, request: CapabilityRequest
) -> CapabilityVerdict:
    kind = request.kind
    if kind not in _KNOWN_KINDS:
        return CapabilityVerdict(False, "unknown capability kind")
    if kind == "READ_PATH":
        return _evaluate_path(request.target, profile.filesystem.read_roots)
    if kind == "WRITE_PATH":
        return _evaluate_path(request.target, profile.filesystem.write_roots)
    if kind == "EXECUTABLE":
        if request.target in profile.executables:
            return CapabilityVerdict(True, "allowed")
        return CapabilityVerdict(False, "executable not allowed")
    if kind == "NETWORK":
        return _evaluate_network(profile, request.target)
    if kind == "BROWSER":
        if request.target == profile.browser:
            return CapabilityVerdict(True, "allowed")
        return CapabilityVerdict(False, "browser not allowed")
    if kind == "SECRET":
        if request.target in profile.secrets:
            return CapabilityVerdict(True, "allowed")
        return CapabilityVerdict(False, "secret not allowed")
    if request.target in profile.side_effects:
        return CapabilityVerdict(True, "allowed")
    return CapabilityVerdict(False, "side effect not allowed")


def _evaluate_path(target: str, roots: Sequence[str]) -> CapabilityVerdict:
    path = _normalize(target)
    if path is None:
        return CapabilityVerdict(False, "invalid path")
    for root in roots:
        bound = _normalize(root)
        if bound is None:
            continue
        if _contains(bound, path):
            return CapabilityVerdict(True, "allowed")
    return CapabilityVerdict(False, "path not in roots")


def _evaluate_network(profile: CapabilityProfile, target: str) -> CapabilityVerdict:
    if profile.network.mode == "DENY_ALL":
        return CapabilityVerdict(False, "network denied")
    host = _network_host(target)
    if host is None:
        return CapabilityVerdict(False, "invalid host")
    allowed = {
        item
        for item in (_network_host(entry) for entry in profile.network.allow)
        if item
    }
    if host in allowed:
        return CapabilityVerdict(True, "allowed")
    return CapabilityVerdict(False, "host not in allow list")


def _normalize(raw: str) -> _NormPath | None:
    text = raw.strip()
    style = _style(text)
    if style is None:
        return None
    parsed = PureWindowsPath(text) if style == "windows" else PurePosixPath(text)
    if not parsed.is_absolute():
        return None
    parts = list(parsed.parts)
    if not parts:
        return None
    collapsed: list[str] = [parts[0]]
    for part in parts[1:]:
        if part in ("", "."):
            continue
        if part == "..":
            if len(collapsed) == 1:
                return None
            collapsed.pop()
            continue
        collapsed.append(part)
    return _NormPath(style, tuple(collapsed))


def _style(path: str) -> PathStyle | None:
    if not path or "\x00" in path:
        return None
    if _WINDOWS_DRIVE.match(path) or _WINDOWS_UNC.match(path):
        return "windows"
    if path.startswith("/") and not path.startswith("//"):
        return "posix"
    return None


def path_inside(root: Path, target: Path) -> bool:
    left = _normalize(str(root.resolve()))
    right = _normalize(str(target.resolve()))
    if left is None or right is None:
        return False
    return _contains(left, right)


def _contains(root: _NormPath, path: _NormPath) -> bool:
    if root.style != path.style:
        return False
    root_parts = root.parts
    path_parts = path.parts
    if root.style == "windows":
        root_parts = tuple(part.casefold() for part in root_parts)
        path_parts = tuple(part.casefold() for part in path_parts)
    return path_parts[: len(root_parts)] == root_parts


def _network_host(target: str) -> str | None:
    text = target.strip()
    if not text or "\x00" in text:
        return None
    if "://" in text:
        host = urlparse(text).hostname
        return host.casefold() if host else None
    if "/" in text:
        text = text.split("/", 1)[0]
    if text.startswith("["):
        end = text.find("]")
        if end < 1:
            return None
        return text[1:end].casefold()
    if ":" in text:
        host, _, port = text.rpartition(":")
        if host and port.isdigit():
            text = host
    return text.casefold() if text else None


__all__ = [
    "CapabilityRequest",
    "CapabilityVerdict",
    "compile_profile",
    "evaluate",
    "path_inside",
]
