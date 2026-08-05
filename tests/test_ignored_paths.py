"""Ignored-path governed-file discovery regression tests (AC-07).

Content under paths ignored by the checked root's ``.gitignore`` must
never be scanned; equivalent unignored invalid content must still fail.
The bootstrap checkers are loaded by file path through the CLI's isolated
loader (they live outside the managed package), and the matcher plus
end-to-end behavior are both covered without hardcoding any machine-specific
absolute path.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "scripts" / "fixtures"


@pytest.fixture
def documentation_modules() -> Iterator[tuple[Any, Any]]:
    """Yield checker modules while preserving the process import state."""
    script = _REPO_ROOT / "scripts" / "check_documentation.py"
    with isolated_script_module("check_documentation", script) as module:
        common = sys.modules.get("_check_common")
        assert common is not None
        yield cast(Any, module), cast(Any, common)


def test_anchored_directory_rule_matches_only_root(
    documentation_modules: tuple[Any, Any],
) -> None:
    _checker, common = documentation_modules
    rules = common.parse_gitignore("/reference/\n")
    assert common.is_path_ignored("reference/notes.md", rules)
    assert common.is_path_ignored("reference/sub/deep.md", rules)
    assert not common.is_path_ignored("docs/guide.md", rules)
    assert not common.is_path_ignored("referencex/notes.md", rules)


def test_unanchored_rule_matches_any_depth(
    documentation_modules: tuple[Any, Any],
) -> None:
    _checker, common = documentation_modules
    rules = common.parse_gitignore(".venv/\n")
    assert common.is_path_ignored(".venv/lib/x.py", rules)
    assert common.is_path_ignored("a/b/.venv/x.py", rules)
    assert not common.is_path_ignored("venv/lib/x.py", rules)


def test_negation_reincludes_matching_path(
    documentation_modules: tuple[Any, Any],
) -> None:
    _checker, common = documentation_modules
    rules = common.parse_gitignore(".venv/\n!.venv/keep.md\n")
    assert common.is_path_ignored(".venv/lib/x.py", rules)
    assert not common.is_path_ignored(".venv/keep.md", rules)


def test_comments_and_blank_lines_are_ignored(
    documentation_modules: tuple[Any, Any],
) -> None:
    _checker, common = documentation_modules
    rules = common.parse_gitignore("# a comment\n\n.venv/\n")
    assert common.is_path_ignored(".venv/x", rules)


def test_wildcard_segment_matches(documentation_modules: tuple[Any, Any]) -> None:
    _checker, common = documentation_modules
    rules = common.parse_gitignore("*.pyc\n")
    assert common.is_path_ignored("a/b/mod.pyc", rules)
    assert not common.is_path_ignored("a/b/mod.py", rules)


def test_empty_gitignore_yields_no_rules(
    documentation_modules: tuple[Any, Any],
) -> None:
    _checker, common = documentation_modules
    assert common.parse_gitignore("") == []
    assert common.parse_gitignore("# only comments\n") == []


def test_ignored_fixture_content_does_not_fail_positive_fixture(
    documentation_modules: tuple[Any, Any],
) -> None:
    check_documentation, _common = documentation_modules
    root = _FIXTURES / "ignored-paths"
    assert check_documentation.main(["--root", str(root)]) == 0


def test_unignored_invalid_content_still_fails(
    documentation_modules: tuple[Any, Any],
) -> None:
    check_documentation, _common = documentation_modules
    root = _FIXTURES / "negative" / "docs" / "unignored-invalid"
    assert check_documentation.main(["--root", str(root)]) == 1


def test_tmp_tree_prunes_ignored_invalid_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    documentation_modules: tuple[Any, Any],
) -> None:
    check_documentation, _common = documentation_modules
    # The checker confines a --root scan to the repository; make the temp
    # area look like the repository so the tree can be checked out-of-repo.
    monkeypatch.setattr(check_documentation, "repo_root", lambda: tmp_path.parent)
    root = tmp_path / "tree"
    (root / "reference").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".gitignore").write_text("/reference/\n", encoding="utf-8")
    (root / "reference" / "bad.md").write_text("```\n", encoding="utf-8")
    (root / "docs" / "good.md").write_text("ok\n", encoding="utf-8")
    assert check_documentation.main(["--root", str(root)]) == 0
    (root / ".gitignore").unlink()
    assert check_documentation.main(["--root", str(root)]) == 1


def test_unignored_new_governed_file_is_still_scanned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    documentation_modules: tuple[Any, Any],
) -> None:
    check_documentation, _common = documentation_modules
    monkeypatch.setattr(check_documentation, "repo_root", lambda: tmp_path.parent)
    root = tmp_path / "tree"
    (root / "docs").mkdir(parents=True)
    (root / ".gitignore").write_text("/reference/\n", encoding="utf-8")
    (root / "docs" / "ok.md").write_text("ok\n", encoding="utf-8")
    (root / "new-governed.md").write_text("ok\n", encoding="utf-8")
    assert check_documentation.main(["--root", str(root)]) == 0
