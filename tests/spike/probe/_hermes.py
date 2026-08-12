"""Hermes probe fixtures for slice-00-05 (AC-01/AC-03/AC-09).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Probe suites locate the Hermes environment through the explicit
``HERMES_PIPELINE_PROBE_HERMES`` variable; they skip with a clear reason
when the variable is absent and fail (not skip) when it is set but broken.
``uv run --offline pytest`` never assumes Hermes exists in the project dev
environment; in required CI the variable is always set. All child
processes use controlled argv arrays and fixture-built allow-list
environments.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from hermes_shim._provision import build_child_env

REPO_ROOT = Path(__file__).resolve().parents[3]

# The probe child environment carries only the isolated HERMES_HOME, the
# resolved probe path, the optional candidate SHA, and bytecode-off.
PROBE_ENV_KEYS = (
    "HERMES_HOME",
    "HERMES_PIPELINE_PROBE_HERMES",
    "HERMES_PIPELINE_CANDIDATE_SHA",
    "PATH",
    "SystemRoot",
    "ComSpec",
    "USERPROFILE",
    "HOME",
    "TEMP",
    "TMP",
)


def hermes_python() -> Path:
    """Resolve the Hermes environment Python; skip/fail per contract."""
    value = os.environ.get("HERMES_PIPELINE_PROBE_HERMES")
    if not value:
        pytest.skip("HERMES_PIPELINE_PROBE_HERMES not set (probe runs only in CI)")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"HERMES_PIPELINE_PROBE_HERMES set but not a file: {value}")
    return path


def hermes_checkout(python: Path) -> Path:
    """The Hermes checkout root.

    The interpreter lives at ``<checkout>/venv/Scripts/python.exe``
    (Windows) or ``<checkout>/venv/bin/python`` (POSIX); probe both the
    venv depth and the base-python depth to tolerate layout variants.
    """
    candidates = (
        python.parent.parent.parent,
        python.parent.parent,
    )
    for candidate in candidates:
        if (candidate / "hermes_cli").is_dir():
            return candidate
    pytest.fail("HERMES_PIPELINE_PROBE_HERMES does not point inside a Hermes checkout")


def probe_env(hermes_home: Path) -> dict[str, str]:
    """Fixture-built allow-list environment for a Hermes probe child."""
    extra: dict[str, str] = {"HERMES_HOME": str(hermes_home)}
    candidate = os.environ.get("HERMES_PIPELINE_CANDIDATE_SHA")
    if candidate:
        extra["HERMES_PIPELINE_CANDIDATE_SHA"] = candidate
    env = build_child_env(extra)
    # The probe child also needs the Hermes checkout on the module path via
    # its working directory; PATH carries the resolved executables.
    return env


def run_hermes_cli(
    python: Path,
    checkout: Path,
    hermes_home: Path,
    argv: list[str],
    *,
    timeout: float = 300,
) -> subprocess.CompletedProcess[str]:
    """Run one Hermes CLI command with a controlled argv array.

    The ``hermes`` executable (``venv/Scripts/hermes.exe`` on Windows,
    ``venv/bin/hermes`` on POSIX) is invoked directly: the ``cli.py``
    ``fire.Fire(main)`` entry re-routes positional arguments and is not
    suitable for controlled argv calls.
    """
    exe = python.parent / ("hermes.exe" if os.name == "nt" else "hermes")
    if not exe.is_file():
        pytest.fail(f"Hermes executable not found: {exe}")
    return subprocess.run(
        [str(exe), *argv],
        cwd=str(checkout),
        env=probe_env(hermes_home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def run_probe_script(
    python: Path,
    checkout: Path,
    hermes_home: Path,
    script: str,
    *,
    timeout: float = 300,
) -> subprocess.CompletedProcess[str]:
    """Run one probe script inside the Hermes environment Python."""
    return subprocess.run(
        [str(python), "-c", script],
        cwd=str(checkout),
        env=probe_env(hermes_home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def resolve_install_fixture(tmp_path: Path, env: dict[str, str]) -> tuple[Path, str]:
    """The shared Candidate-pinned install fixture for every Hermes probe.

    In CI the workflow builds one fixture with ``git clone --no-checkout``
    plus ``checkout -B main <HERMES_PIPELINE_CANDIDATE_SHA>`` and exposes
    it via ``HERMES_PIPELINE_INSTALL_FIXTURE``; locally the fixture is
    built by the test. Either way the returned fixture's default HEAD is
    pinned to the event-derived Candidate, its ref is ``main``, and its
    tree equals the repository tree — so install, PluginManager, and
    Gateway evidence all bind to the same Candidate.
    """
    provided = os.environ.get("HERMES_PIPELINE_INSTALL_FIXTURE")
    if provided:
        fixture = Path(provided)
        candidate = os.environ.get("HERMES_PIPELINE_CANDIDATE_SHA")
        assert candidate is not None, "fixture requires the candidate SHA"
        git = shutil.which("git")
        assert git is not None
        head = subprocess.run(
            [git, "-C", str(fixture), "rev-parse", "HEAD"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert head.returncode == 0 and head.stdout.strip() == candidate
        ref = subprocess.run(
            [git, "-C", str(fixture), "symbolic-ref", "HEAD"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert ref.returncode == 0 and ref.stdout.strip() == "refs/heads/main"
        fixture_tree = subprocess.run(
            [git, "-C", str(fixture), "rev-parse", "HEAD^{tree}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        repo_tree = subprocess.run(
            [git, "-C", str(REPO_ROOT), "rev-parse", "HEAD^{tree}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            fixture_tree.returncode == 0
            and repo_tree.returncode == 0
            and fixture_tree.stdout.strip() == repo_tree.stdout.strip()
        )
        return fixture, candidate
    return build_install_fixture(tmp_path / "fixture", candidate_sha=None)


def assert_installed_checkout_is_candidate(
    installed: Path,
    fixture: Path,
    candidate: str,
    env: dict[str, str],
) -> None:
    """Prove one probe's installed checkout is the tested Candidate.

    Each Hermes probe installs into its own isolated ``HERMES_HOME``.  The
    assertion therefore belongs beside every install, rather than being
    inferred from the source-install probe's separate home directory.
    ``resolve_install_fixture`` already proves the fixture tree equals the
    checked-out repository tree, so equality below closes the Candidate ->
    fixture -> installed-chain for this individual probe.
    """
    assert installed.is_dir()
    assert git_value(env, "rev-parse", "HEAD", cwd=installed) == candidate
    assert git_value(env, "rev-parse", "HEAD^{tree}", cwd=installed) == git_value(
        env, "rev-parse", "HEAD^{tree}", cwd=fixture
    )


def git_value(env: dict[str, str], *argv: str, cwd: Path) -> str:
    """Run a controlled local Git read and return its trimmed stdout."""
    git = shutil.which("git")
    assert git is not None
    proc = subprocess.run(
        [git, "-C", str(cwd), *argv],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def build_install_fixture(
    target: Path, candidate_sha: str | None = None
) -> tuple[Path, str]:
    """Build a temporary local Git fixture whose default HEAD is pinned to
    the Candidate SHA (or to the current working tree when none given).

    Copies the repository content (excluding Git state and local caches)
    into ``target``, then creates a local Git repository with ``main``
    pinned to the returned SHA. All Git argv is controlled and confined to
    the temporary fixture directory; the repository's own Git state is
    untouched. Returns (fixture_path, fixture_head_sha).
    """
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree(REPO_ROOT, target)
    env = build_child_env({})
    git = shutil.which("git")
    assert git is not None
    for argv in (
        [git, "-C", str(target), "init", "-b", "main"],
        [git, "-C", str(target), "config", "user.name", "slice-00-05-fixture"],
        [git, "-C", str(target), "config", "user.email", "fixture@hermes-pipeline.dev"],
        [git, "-C", str(target), "add", "-A"],
    ):
        proc = subprocess.run(
            argv, env=env, capture_output=True, text=True, timeout=120
        )
        assert proc.returncode == 0, proc.stderr
    if candidate_sha is None:
        # Commit the fixture content and pin main to it.
        proc = subprocess.run(
            [git, "-C", str(target), "commit", "-m", "slice-00-05 fixture"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        proc = subprocess.run(
            [git, "-C", str(target), "rev-parse", "HEAD"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
        candidate_sha = proc.stdout.strip()
    else:
        # Pin the fixture's main to an existing repository commit: import
        # the exact commit from the source repository (read-only source).
        proc = subprocess.run(
            [git, "-C", str(target), "fetch", str(REPO_ROOT), candidate_sha],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        proc = subprocess.run(
            [git, "-C", str(target), "checkout", "-B", "main", candidate_sha],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
    return target, candidate_sha


def _copy_tree(source: Path, target: Path) -> None:
    """Copy governed repository content into the fixture (no .git)."""
    ignore = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        "reference",
    }
    for item in source.iterdir():
        if item.name in ignore:
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                dest,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".venv",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".hypothesis",
                ),
            )
        else:
            shutil.copy2(item, dest)
