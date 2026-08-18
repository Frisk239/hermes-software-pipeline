"""Host gh publish helpers (slice 05-14).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

from hermes_shim._github import gh_available, publish_with_gh, worktree_files


def test_worktree_files_reads_relative_paths(tmp_path: Path) -> None:
    target = tmp_path / "worktrees" / "pl_a" / "src"
    target.mkdir(parents=True)
    (target / "app.py").write_text("print(1)\n", encoding="utf-8")
    files = worktree_files(tmp_path, "pl_a")
    assert files == {"src/app.py": "print(1)\n"}


def test_publish_without_gh_is_empty() -> None:
    def _runner(argv: list[str], stdin: str = "") -> tuple[int, str, str]:
        del argv, stdin
        return 1, "", ""

    result = publish_with_gh(
        repo="Frisk239/test-repository",
        project_id="prj_a",
        pipeline_id="pl_a",
        sha="abc",
        files={"src/app.py": "print(1)\n"},
        runner=_runner,
    )
    assert result == {}


def test_publish_with_fake_gh_opens_pr() -> None:
    calls: list[str] = []

    def _runner(argv: list[str], stdin: str = "") -> tuple[int, str, str]:
        del stdin
        joined = " ".join(argv)
        calls.append(joined)
        if argv[:2] == ["gh", "auth"]:
            return 0, "logged in", ""
        if "git/ref/heads/main" in joined:
            return 0, '{"object":{"sha":"aa"}}', ""
        if "git/commits/" in joined:
            return 0, '{"tree":{"sha":"tt"}}', ""
        if "git/blobs" in joined:
            return 0, '{"sha":"bb"}', ""
        if "git/trees" in joined:
            return 0, '{"sha":"tr"}', ""
        if "git/commits" in joined:
            return 0, '{"sha":"cc"}', ""
        if "git/refs" in joined:
            return 0, '{"ref":"refs/heads/hermes/prj_a/pl_a"}', ""
        if "pulls" in joined:
            return 0, '{"number":3,"html_url":"https://github.com/o/r/pull/3"}', ""
        return 1, "", ""

    result = publish_with_gh(
        repo="Frisk239/test-repository",
        project_id="prj_a",
        pipeline_id="pl_a",
        sha="abc",
        files={"src/app.py": "print(1)\n"},
        runner=_runner,
    )
    assert result["pr_number"] == "3"
    assert result["branch"] == "hermes/prj_a/pl_a"
    assert any("gh auth status" in item for item in calls)


def test_gh_available_false_when_auth_fails() -> None:
    def _runner(argv: list[str], stdin: str = "") -> tuple[int, str, str]:
        del argv, stdin
        return 1, "", "not logged in"

    assert gh_available(_runner) is False
