"""Static tool-lock and npm identity checks (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hermes_pipeline.runtime_broker._digest import file_digest

SLICE_DIR = (
    Path("docs")
    / "roadmap"
    / "phase-00-foundation"
    / "slices"
    / "00-06-agent-runtime-security-spikes"
)
PLATFORM: str = "windows-x64" if sys.platform == "win32" else "linux-x64"
DANGEROUS_CODEX_FLAGS = (
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-bypass-hook-trust",
)
REJECTED_MCP = (
    "--browser-url",
    "--ws-endpoint",
    "--auto-connect",
    "--channel",
    "--user-data-dir",
    "--allow-unrestricted-paths",
    "--allowUnrestrictedPaths",
)


def load_tool_lock(path: Path) -> dict[str, Any]:
    """Load the committed tool lock as JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def verify_browser_inputs(lock: dict[str, Any], repo_root: Path) -> None:
    """Verify package.json / lock / .npmrc raw digests, name, pin, and SRI."""
    inputs = lock["browser_runtime_inputs"]
    manifest = repo_root / inputs["package_manifest"]
    lockfile = repo_root / inputs["lockfile"]
    npmrc = repo_root / inputs["npmrc"]
    if file_digest(manifest.read_bytes()) != inputs["package_manifest_digest"]:
        raise ValueError("package.json digest mismatch")
    if file_digest(lockfile.read_bytes()) != inputs["lockfile_digest"]:
        raise ValueError("package-lock.json digest mismatch")
    if file_digest(npmrc.read_bytes()) != inputs["npmrc_digest"]:
        raise ValueError(".npmrc digest mismatch")
    package = json.loads(manifest.read_text(encoding="utf-8"))
    if package.get("name") != "hermes-browser-runtime":
        raise ValueError("browser runtime name mismatch")
    pin = package.get("dependencies", {}).get("chrome-devtools-mcp")
    if pin != "1.7.0":
        raise ValueError("chrome-devtools-mcp pin is not exact 1.7.0")
    locked = json.loads(lockfile.read_text(encoding="utf-8"))
    integrity = locked["packages"]["node_modules/chrome-devtools-mcp"]["integrity"]
    expected = None
    for tool in lock["tools"]:
        if tool.get("tool") == "chrome-devtools-mcp":
            expected = "sha512-" + tool["expected_integrity_sha512"]
            break
    if integrity != expected:
        raise ValueError("chrome-devtools-mcp SRI mismatch")


def npm_argv(lock: dict[str, Any], state_root: Path, *, offline: bool) -> list[str]:
    """Build the locked npm argv. Ambient PATH npm is never used."""
    controlled = lock["browser_runtime_inputs"]["controlled_npm"]
    template = controlled["offline_argv"] if offline else controlled["online_argv"]
    executable = controlled["npm_executable_by_platform"][PLATFORM]
    rendered: list[str] = []
    for item in template:
        rendered.append(
            item.replace("<selected-locked-npm-executable>", executable).replace(
                "<state-root>", str(state_root)
            )
        )
    executable_name = Path(rendered[0]).name.lower()
    normalized = rendered[0].replace("\\", "/")
    root = str(state_root).replace("\\", "/")
    if executable_name in {"npm", "npm.cmd"} and root not in normalized:
        raise ValueError("ambient PATH npm is forbidden")
    return rendered


def mcp_argv(lock: dict[str, Any], state_root: Path, fixture_port: int) -> list[str]:
    """Build the closed Chrome DevTools MCP argv."""
    policy = lock["browser_launch_policy"]
    node = policy["node_executable_by_platform"][PLATFORM].replace(
        "<state-root>", str(state_root)
    )
    chrome = policy["chrome_for_testing_executable_by_platform"][PLATFORM].replace(
        "<state-root>", str(state_root)
    )
    rendered: list[str] = []
    for item in policy["mcp_argv"]:
        rendered.append(
            item.replace("<selected-locked-node-executable>", node)
            .replace("<state-root>", str(state_root))
            .replace("<selected-locked-cft-executable>", chrome)
            .replace("<host-reserved-fixture-port>", str(fixture_port))
        )
    if any(flag in rendered for flag in REJECTED_MCP):
        raise ValueError("rejected MCP override present")
    return rendered


def chrome_is_sealed(lock: dict[str, Any]) -> bool:
    """CfT is never a sealed hard-gate identity."""
    for tool in lock["tools"]:
        if (
            tool.get("tool") == "chrome-for-testing"
            and tool.get("integrity_status") == "no_official_checksum"
        ):
            return False
    return False


def windows_codex_unsupported(lock: dict[str, Any]) -> bool:
    """Windows sealed Codex remains UNSUPPORTED_RUNTIME in this revision."""
    if PLATFORM != "windows-x64":
        return False
    for tool in lock["tools"]:
        if tool.get("tool") == "codex-cli" and tool.get("platform") == "windows-x64":
            return "publisher hard gate unavailable" in str(
                tool.get("integrity_status")
            )
    return True


def assert_no_dangerous_codex_flags(argv: list[str]) -> None:
    """Refuse any sanctioned Codex argv that contains bypass flags."""
    if any(flag in argv for flag in DANGEROUS_CODEX_FLAGS):
        raise ValueError("dangerous Codex bypass flag is forbidden")
