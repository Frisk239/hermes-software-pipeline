"""Real source-install probe with Candidate-identity binding (slice-00-05,
AC-03).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Installs this repository from a temporary local Git fixture whose default
HEAD is pinned to the Candidate SHA (``HERMES_PIPELINE_CANDIDATE_SHA`` in
CI, derived from the workflow event; locally the fixture's own commit),
then proves repository/fixture/installed HEAD plus ``HEAD^{tree}``
equality. A fixture whose ``main`` points at a non-Candidate SHA fails the
post-install assertion. ``hermes plugins list`` is secondary manifest/
enable evidence only; load evidence comes from the PluginManager probe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.spike.probe._hermes import (
    assert_installed_checkout_is_candidate,
    build_install_fixture,
    git_value,
    hermes_checkout,
    hermes_python,
    probe_env,
    resolve_install_fixture,
    run_hermes_cli,
)


def _candidate_sha() -> str | None:
    return os.environ.get("HERMES_PIPELINE_CANDIDATE_SHA")


def test_source_install_binds_to_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = hermes_python()
    checkout = hermes_checkout(python)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    env = probe_env(hermes_home)

    fixture, fixture_sha = resolve_install_fixture(tmp_path, env)
    candidate = _candidate_sha() or fixture_sha

    # Pre-install assertions: fixture SHA/ref.
    assert git_value(env, "rev-parse", "HEAD", cwd=fixture) == candidate
    assert git_value(env, "symbolic-ref", "HEAD", cwd=fixture) == "refs/heads/main"

    # Non-interactive source install (no requires_env prompt).
    proc = run_hermes_cli(
        python,
        checkout,
        hermes_home,
        ["plugins", "install", f"file://{fixture}", "--enable"],
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    installed = hermes_home / "plugins" / "hermes-software-pipeline"
    # Post-install assertions: this isolated home also installs exactly the
    # event-derived Candidate and its tested tree.
    assert_installed_checkout_is_candidate(installed, fixture, candidate, env)

    # `hermes pipeline --help` resolves with the five subcommands.
    proc = run_hermes_cli(
        python, checkout, hermes_home, ["pipeline", "--help"], timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    for subcommand in ("setup", "doctor", "start", "status", "stop"):
        assert subcommand in proc.stdout

    # plugins list is secondary manifest/enable evidence only.
    proc = run_hermes_cli(
        python, checkout, hermes_home, ["plugins", "list"], timeout=300
    )
    assert proc.returncode == 0
    assert "hermes-software" in proc.stdout
    config = (hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert "hermes-software-pipeline" in config


def test_non_candidate_fixture_fails_post_install_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fixture whose main points at a non-Candidate SHA fails the
    post-install HEAD assertion (the install binds the fixture default
    HEAD, never any other repository state)."""
    python = hermes_python()
    checkout = hermes_checkout(python)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    env = probe_env(hermes_home)

    fixture, candidate = build_install_fixture(tmp_path / "fixture")
    # Move main to a second commit so the default HEAD differs from the
    # Candidate (which is the first commit).
    git = shutil.which("git")
    assert git is not None
    marker = fixture / "non-candidate-marker.txt"
    marker.write_text("not the candidate", encoding="utf-8")
    for argv in (
        [git, "-C", str(fixture), "add", "-A"],
        [
            git,
            "-C",
            str(fixture),
            "commit",
            "-m",
            "non-candidate move",
            "--author=Fixture <fixture@hermes-pipeline.dev>",
        ],
    ):
        proc = subprocess.run(
            argv, env=env, capture_output=True, text=True, timeout=120
        )
        assert proc.returncode == 0, proc.stderr
    assert git_value(env, "rev-parse", "HEAD", cwd=fixture) != candidate

    proc = run_hermes_cli(
        python,
        checkout,
        hermes_home,
        ["plugins", "install", f"file://{fixture}", "--enable"],
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    installed = hermes_home / "plugins" / "hermes-software-pipeline"
    installed_head = git_value(env, "rev-parse", "HEAD", cwd=installed)
    # The post-install assertion must detect the mismatch.
    assert installed_head != candidate
    with pytest.raises(AssertionError):
        assert installed_head == candidate


def test_manifest_version_two_rejected_by_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plugin declaring manifest_version 2 is rejected by the installer."""
    python = hermes_python()
    checkout = hermes_checkout(python)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    fixture = tmp_path / "bad-manifest-plugin"
    fixture.mkdir()
    (fixture / "plugin.yaml").write_text(
        "name: bad-manifest-plugin\nversion: 0.1.0\nmanifest_version: 2\n",
        encoding="utf-8",
    )
    (fixture / "__init__.py").write_text("", encoding="utf-8")
    # The fixture must be a local Git repository for the installer clone.
    git = shutil.which("git")
    assert git is not None
    for argv in (
        [git, "-C", str(fixture), "init", "-b", "main"],
        [git, "-C", str(fixture), "config", "user.name", "fixture"],
        [git, "-C", str(fixture), "config", "user.email", "f@x.dev"],
        [git, "-C", str(fixture), "add", "-A"],
        [git, "-C", str(fixture), "commit", "-m", "bad manifest"],
    ):
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
    proc = run_hermes_cli(
        python,
        checkout,
        hermes_home,
        ["plugins", "install", f"file://{fixture}", "--enable"],
        timeout=600,
    )
    assert proc.returncode != 0
    assert "manifest_version" in (proc.stdout + proc.stderr)
