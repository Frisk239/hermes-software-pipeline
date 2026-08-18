from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hermes_pipeline.contracts.jcs import content_hash
from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.capability import (
    CapabilityRequest,
    compile_profile,
    evaluate,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_CAPABILITY = _SRC / "runtime_broker" / "capability.py"


def _development(root: str) -> CapabilityProfile:
    return compile_profile(write_roots=[root])


def test_compile_is_deterministic_and_uses_jcs_content_hash() -> None:
    first = compile_profile(write_roots=["/work"], executables=["uv"])
    second = compile_profile(write_roots=["/work"], executables=["uv"])
    assert first.content_hash == second.content_hash
    assert first.content_hash == content_hash(first.model_dump(mode="json"))
    assert first.stage_type == "DEVELOPMENT"
    assert first.filesystem.write_roots == ["/work"]


@pytest.mark.parametrize(
    ("root", "inside", "escaped", "foreign"),
    [
        (r"C:\work", r"C:\work\src\a.py", r"C:\work\..\escape.py", r"D:\escape.py"),
        ("/work", "/work/src/a.py", "/work/../escape.py", "/other/escape.py"),
    ],
)
def test_write_path_allow_inside_and_deny_escape(
    root: str, inside: str, escaped: str, foreign: str
) -> None:
    profile = _development(root)
    assert evaluate(profile, CapabilityRequest("WRITE_PATH", inside)).allowed is True
    assert evaluate(profile, CapabilityRequest("WRITE_PATH", escaped)).allowed is False
    assert evaluate(profile, CapabilityRequest("WRITE_PATH", foreign)).allowed is False


def test_windows_paths_are_case_insensitive_posix_are_not() -> None:
    windows = _development(r"C:\work")
    posix = _development("/work")
    assert (
        evaluate(windows, CapabilityRequest("WRITE_PATH", r"C:\WORK\src\a.py")).allowed
        is True
    )
    assert (
        evaluate(posix, CapabilityRequest("WRITE_PATH", "/WORK/src/a.py")).allowed
        is False
    )


def test_mixed_windows_separators_and_prefix_are_not_roots() -> None:
    profile = _development(r"C:\work")
    assert (
        evaluate(profile, CapabilityRequest("WRITE_PATH", r"C:/work/src/a.py")).allowed
        is True
    )
    assert (
        evaluate(profile, CapabilityRequest("WRITE_PATH", r"C:\workshop\a.py")).allowed
        is False
    )
    assert (
        evaluate(
            _development("/work"), CapabilityRequest("WRITE_PATH", "/workshop/a.py")
        ).allowed
        is False
    )


def test_network_deny_all_and_allow_list() -> None:
    denied = compile_profile(write_roots=["/work"], network_mode="DENY_ALL")
    allowed = compile_profile(
        write_roots=["/work"],
        network_mode="ALLOW_LIST",
        network_allow=["example.com"],
    )
    assert (
        evaluate(denied, CapabilityRequest("NETWORK", "example.com")).allowed is False
    )
    assert (
        evaluate(denied, CapabilityRequest("NETWORK", "https://other.test")).allowed
        is False
    )
    assert (
        evaluate(allowed, CapabilityRequest("NETWORK", "example.com")).allowed is True
    )
    assert (
        evaluate(allowed, CapabilityRequest("NETWORK", "https://example.com/x")).allowed
        is True
    )
    assert (
        evaluate(allowed, CapabilityRequest("NETWORK", "other.test")).allowed is False
    )


def test_executable_browser_secret_and_side_effect_are_fail_closed() -> None:
    profile = compile_profile(
        write_roots=["/work"],
        executables=["uv"],
        browser="NONE",
        secrets=["API_TOKEN"],
        side_effects=["NONE"],
    )
    assert evaluate(profile, CapabilityRequest("EXECUTABLE", "uv")).allowed is True
    assert evaluate(profile, CapabilityRequest("EXECUTABLE", "python")).allowed is False
    assert (
        evaluate(profile, CapabilityRequest("BROWSER", "CHROME_DEVTOOLS_MCP")).allowed
        is False
    )
    assert evaluate(profile, CapabilityRequest("SECRET", "API_TOKEN")).allowed is True
    assert evaluate(profile, CapabilityRequest("SECRET", "OTHER")).allowed is False
    assert evaluate(profile, CapabilityRequest("SIDE_EFFECT", "NONE")).allowed is True
    assert (
        evaluate(profile, CapabilityRequest("SIDE_EFFECT", "LOCAL_BUILD")).allowed
        is False
    )


def test_unknown_kind_is_denied() -> None:
    profile = _development("/work")
    verdict = evaluate(profile, CapabilityRequest("TELEPORT", "/work/src/a.py"))
    assert verdict.allowed is False
    assert verdict.reason == "unknown capability kind"


def test_capability_module_does_not_import_keep_marked_probes() -> None:
    tree = ast.parse(_CAPABILITY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        assert all("runtime_broker._" not in name for name in names)


def test_controller_and_domain_do_not_import_capability() -> None:
    for folder in ("controller", "domain"):
        for path in (_SRC / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                assert all("capability" not in name for name in names)
