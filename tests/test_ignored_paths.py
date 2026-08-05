"""Ignored-path governed-file discovery regression tests (AC-07).

Content under paths ignored by the checked root's ``.gitignore`` must
never be scanned; equivalent unignored invalid content must still fail.
The bootstrap checkers are loaded by file path (they live outside the
managed package and are deliberately type-unannotated), and the matcher
plus end-to-end behavior are both covered without hardcoding any
machine-specific absolute path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "scripts" / "fixtures"


def _load_scripts_module(name: str) -> Any:
    """Load one bootstrap checker from scripts/ by absolute file path.

    The scripts are validated by their own self-tests; tests here only
    need their callable surface, so the module is loaded at runtime
    instead of being part of the managed package import graph.
    """
    spec = importlib.util.spec_from_file_location(
        name, _REPO_ROOT / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_check_common = _load_scripts_module("_check_common")
check_documentation = _load_scripts_module("check_documentation")
is_path_ignored = _check_common.is_path_ignored
parse_gitignore = _check_common.parse_gitignore


def test_anchored_directory_rule_matches_only_root() -> None:
    rules = parse_gitignore("/reference/\n")
    assert is_path_ignored("reference/notes.md", rules)
    assert is_path_ignored("reference/sub/deep.md", rules)
    assert not is_path_ignored("docs/guide.md", rules)
    assert not is_path_ignored("referencex/notes.md", rules)


def test_unanchored_rule_matches_any_depth() -> None:
    rules = parse_gitignore(".venv/\n")
    assert is_path_ignored(".venv/lib/x.py", rules)
    assert is_path_ignored("a/b/.venv/x.py", rules)
    assert not is_path_ignored("venv/lib/x.py", rules)


def test_negation_reincludes_matching_path() -> None:
    rules = parse_gitignore(".venv/\n!.venv/keep.md\n")
    assert is_path_ignored(".venv/lib/x.py", rules)
    assert not is_path_ignored(".venv/keep.md", rules)


def test_comments_and_blank_lines_are_ignored() -> None:
    rules = parse_gitignore("# a comment\n\n.venv/\n")
    assert is_path_ignored(".venv/x", rules)


def test_wildcard_segment_matches() -> None:
    rules = parse_gitignore("*.pyc\n")
    assert is_path_ignored("a/b/mod.pyc", rules)
    assert not is_path_ignored("a/b/mod.py", rules)


def test_empty_gitignore_yields_no_rules() -> None:
    assert parse_gitignore("") == []
    assert parse_gitignore("# only comments\n") == []


def test_ignored_fixture_content_does_not_fail_positive_fixture() -> None:
    root = _FIXTURES / "ignored-paths"
    assert check_documentation.main(["--root", str(root)]) == 0


def test_unignored_invalid_content_still_fails() -> None:
    root = _FIXTURES / "negative" / "docs" / "unignored-invalid"
    assert check_documentation.main(["--root", str(root)]) == 1


def test_tmp_tree_prunes_ignored_invalid_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
) -> None:
    monkeypatch.setattr(check_documentation, "repo_root", lambda: tmp_path.parent)
    root = tmp_path / "tree"
    (root / "docs").mkdir(parents=True)
    (root / ".gitignore").write_text("/reference/\n", encoding="utf-8")
    (root / "docs" / "ok.md").write_text("ok\n", encoding="utf-8")
    (root / "new-governed.md").write_text("ok\n", encoding="utf-8")
    assert check_documentation.main(["--root", str(root)]) == 0
