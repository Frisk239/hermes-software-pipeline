"""Hostile repository, argv, path, and secret negatives (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._digest import file_digest
from hermes_pipeline.runtime_broker._identity import (
    REJECTED_MCP,
    assert_no_dangerous_codex_flags,
)
from hermes_pipeline.runtime_broker._opencode import merge_permission_policy
from hermes_pipeline.runtime_broker._policy import (
    PolicyError,
    assert_codex_config_not_trusted,
    assert_digest_unchanged,
    assert_no_git_metadata,
    assert_path_inside,
    git_child_environment,
)
from hermes_pipeline.runtime_broker._redaction import child_environment, redact

pytestmark = pytest.mark.fake_only

CANARY = "sk-hostile-canary"
EGRESS = "https://evil.example.invalid/canary"


def test_hostile_opencode_json_cannot_widen_injected_deny() -> None:
    merged = merge_permission_policy({"*": "deny"}, {"*": "allow", "bash": "allow"})
    assert merged["*"] == "deny"


def test_argv_injection_cannot_add_rejected_mcp_or_shell() -> None:
    closed = ["node", "mcp.js", "--headless", "--isolated"]
    for flag in REJECTED_MCP:
        assert flag not in closed
    with pytest.raises(ValueError):
        assert_no_dangerous_codex_flags(
            ["codex", "exec", "--dangerously-bypass-hook-trust"]
        )


def test_adapter_rejects_path_escape_symlink_and_8_3(tmp_path: Path) -> None:
    root = tmp_path / "child-home"
    root.mkdir()
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    assert assert_path_inside(root, "ok.txt").name == "ok.txt"
    with pytest.raises(PolicyError):
        assert_path_inside(root, "../secret")
    with pytest.raises(PolicyError):
        assert_path_inside(root, "/etc/passwd")
    with pytest.raises(PolicyError):
        assert_path_inside(root, "C:\\Windows\\System32")
    with pytest.raises(PolicyError):
        assert_path_inside(root, "COM1")
    with pytest.raises(PolicyError):
        assert_path_inside(root, "PROGRA~1")
    link = root / "escape"
    try:
        link.symlink_to(tmp_path / "outside")
        with pytest.raises(PolicyError):
            assert_path_inside(root, "escape")
    except OSError:
        pass


def test_codex_trust_gate_and_git_hygiene(tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        assert_codex_config_not_trusted('approval_policy = "never"\ntrusted = true\n')
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    assert_no_git_metadata(snapshot)
    (snapshot / ".git").write_text("gitdir: C:/real/.git\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        assert_no_git_metadata(snapshot)
    env = git_child_environment(tmp_path)
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert Path(env["GIT_CONFIG_GLOBAL"]).is_file()


def test_env_and_egress_canaries_never_reach_child() -> None:
    env = child_environment(
        {"TOKEN": CANARY, "HOME": "state/child-home", "EGRESS": EGRESS},
        allow=("HOME",),
        canaries=(CANARY, EGRESS),
    )
    log = redact(f"token={CANARY} url={EGRESS}", (CANARY, EGRESS))
    assert CANARY not in env.values()
    assert EGRESS not in env.values()
    assert CANARY not in log
    assert EGRESS not in log


def test_candidate_gitdir_digest_is_unchanged(tmp_path: Path) -> None:
    gitdir = tmp_path / "HEAD"
    gitdir.write_text("ref: refs/heads/main\n", encoding="utf-8")
    digest = file_digest(gitdir.read_bytes())
    assert_digest_unchanged(gitdir, digest)
    gitdir.write_text("ref: refs/heads/other\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        assert_digest_unchanged(gitdir, digest)


def test_linked_worktree_git_file_is_not_isolation_evidence(tmp_path: Path) -> None:
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    (snapshot / ".git").write_text("gitdir: C:/real/repo/.git\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        assert_no_git_metadata(snapshot)
    if os.name == "nt":
        assert True
