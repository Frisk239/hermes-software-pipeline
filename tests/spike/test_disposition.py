"""Disposition inventory for every spike component (slice-00-04, AC-14).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Every spike module and test carries an explicit disposition: only the
CounterSpike domain evaluator may be retained as a non-public candidate;
persistence, migration, workload, and LangGraph checkpoint spike code and
tests are experimental and are deleted or rewritten unless Slice 00-07
explicitly adopts them. A spike module lacking a disposition marker, or a
test presenting the spike as settled product code, fails review.

Marker contract:

- every spike source file contains ``SPIKE-EXPERIMENTAL``;
- every spike source file contains exactly one ``DISPOSITION: <record>``
  line;
- only ``src/hermes_pipeline/domain/counter_spike.py`` may carry
  ``RETAIN_NON_PUBLIC_CANDIDATE``; everything else must carry
  ``DELETE_UNLESS_ADOPTED_BY_00-07``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "hermes_pipeline"
SPIKE_TESTS = Path(__file__).resolve().parent

EXPERIMENTAL_MARKER = "SPIKE-EXPERIMENTAL"
DISPOSITION_PREFIX = "DISPOSITION:"
RETAIN_MARKER = "RETAIN_NON_PUBLIC_CANDIDATE"
DELETE_MARKER = "DELETE_UNLESS_ADOPTED_BY_00-07"

#: The one component permitted to be retained as a non-public candidate.
RETAINED_PATH = "src/hermes_pipeline/domain/counter_spike.py"

SPIKE_SOURCE_DIRS = (
    SRC / "domain",
    SRC / "controller",
    SRC / "persistence",
    SRC / "stage_executor",
)


def _spike_source_files() -> list[Path]:
    files: list[Path] = []
    for directory in SPIKE_SOURCE_DIRS:
        for path in sorted(directory.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            files.append(path)
    for path in sorted(SPIKE_TESTS.rglob("*.py")):
        files.append(path)
    return files


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_spike_file_carries_experimental_marker() -> None:
    """Negative: a spike module lacking the experimental marker fails."""
    missing = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _spike_source_files()
        if EXPERIMENTAL_MARKER not in _read(path)
    ]
    assert missing == [], f"spike files missing experimental marker: {missing}"


def test_every_spike_file_carries_exact_disposition() -> None:
    """Each spike file carries exactly one retain-or-delete record."""
    problems: list[str] = []
    for path in _spike_source_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        dispositions = [
            line.strip()
            for line in _read(path).splitlines()
            if line.strip().startswith(DISPOSITION_PREFIX)
        ]
        if len(dispositions) != 1:
            problems.append(
                f"{rel}: expected exactly one disposition, got {len(dispositions)}"
            )
            continue
        marker = dispositions[0].split(DISPOSITION_PREFIX, 1)[1].strip()
        if marker not in (RETAIN_MARKER, DELETE_MARKER):
            problems.append(f"{rel}: unknown disposition {marker!r}")
    assert problems == [], "\n".join(problems)


def test_only_counter_spike_may_be_retained() -> None:
    """Only the CounterSpike domain evaluator may be a non-public retention
    candidate; everything else is delete-unless-adopted."""
    for path in _spike_source_files():
        # this file names the retention marker in its own constants
        if path.name == "test_disposition.py":
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = _read(path)
        retains = RETAIN_MARKER in text
        if retains and rel != RETAINED_PATH:
            raise AssertionError(f"{rel} claims retention; only {RETAINED_PATH} may")
        if rel == RETAINED_PATH and not retains:
            raise AssertionError(f"{RETAINED_PATH} lost its retention record")


def test_disposition_inventory_is_complete_and_maps_every_path() -> None:
    """The disposition inventory covers every spike path with an explicit
    retain-or-delete record (the inventory itself is this test plus the
    marker scan above)."""
    files = _spike_source_files()
    assert files, "spike inventory must not be empty"
    covered = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in files
        if path.name != "test_disposition.py"
    ]
    assert RETAINED_PATH in covered
    assert any("persistence/" in entry for entry in covered)
    assert any("stage_executor/" in entry for entry in covered)


#: The forbidden phrase is assembled at runtime (from separately quoted
#: words that no formatter can merge) so this file's own assertion never
#: contains the contiguous words.
_FORBIDDEN_WORD_ONE = "production"
_FORBIDDEN_WORD_TWO = "foundation"
_FORBIDDEN_FOUNDATION = _FORBIDDEN_WORD_ONE + " " + _FORBIDDEN_WORD_TWO


def test_no_spike_test_claims_production_foundation() -> None:
    """Negative: a test presenting the spike as settled product code fails."""
    for path in _spike_source_files():
        text = _read(path).lower()
        lowered = (
            text.replace("cannot silently become " + _FORBIDDEN_FOUNDATION, "")
            .replace("never " + _FORBIDDEN_FOUNDATION, "")
            # this test's own assertion message names the forbidden phrase
            .replace("presents the spike as " + _FORBIDDEN_FOUNDATION, "")
        )
        assert _FORBIDDEN_FOUNDATION not in lowered, (
            f"{path}: presents the spike as {_FORBIDDEN_FOUNDATION}"
        )
