"""PluginManager load/registration probe (slice-00-05, AC-01).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A subprocess running the Hermes environment Python with an isolated
``HERMES_HOME`` installs and enables this plugin, then calls
``get_plugin_manager().discover_and_load()`` and asserts: ``loaded.enabled
is True``, ``loaded.error is None``, exactly one tool, exactly one
``pre_gateway_dispatch`` hook, exactly one top-level ``pipeline`` CLI
command, and the pipeline subcommands. A deliberately broken
plugin fixture asserts ``loaded.error`` is set and Hermes keeps running
(fail-safe load). ``hermes plugins list`` is never used as load evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.spike.probe._hermes import (
    assert_installed_checkout_is_candidate,
    hermes_checkout,
    hermes_python,
    probe_env,
    resolve_install_fixture,
    run_hermes_cli,
    run_probe_script,
)

PLUGINMANAGER_PROBE = r"""
import argparse
from hermes_cli.plugins import get_plugin_manager

pm = get_plugin_manager()
pm.discover_and_load()
loaded = pm._plugins["hermes-software-pipeline"]
assert loaded.enabled is True, loaded.error
assert loaded.error is None, loaded.error
assert loaded.tools_registered == ["pipeline_health"], loaded.tools_registered
assert loaded.hooks_registered == ["pre_gateway_dispatch"], loaded.hooks_registered
# CLI commands are tracked in _cli_commands (commands_registered covers
# in-session slash commands only).
assert "pipeline" in pm._cli_commands, list(pm._cli_commands)
cmd = pm._cli_commands["pipeline"]
parser = argparse.ArgumentParser()
cmd["setup_fn"](parser)
subparsers = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
assert len(subparsers) == 1
choices = set(subparsers[0].choices)
assert choices == {"setup", "doctor", "start", "status", "stop", "submit", "read"}, choices
print("PLUGINMANAGER_PROBE_OK tools=1 hooks=1 commands=1 subcommands=7")
"""

BROKEN_PLUGIN_PROBE = r"""
from hermes_cli.plugins import get_plugin_manager

pm = get_plugin_manager()
pm.discover_and_load()
loaded = pm._plugins["broken-plugin"]
assert loaded.error is not None, "broken plugin must record a load error"
assert loaded.enabled is False
print("BROKEN_PLUGIN_FAILSAFE_OK")
"""


@pytest.fixture
def installed_plugin(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    """Install the plugin from a candidate-bound fixture into an isolated
    HERMES_HOME; returns (python, checkout, hermes_home, installed_path)."""
    python = hermes_python()
    checkout = hermes_checkout(python)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    env = probe_env(hermes_home)
    # The same event-derived Candidate fixture used by every Hermes probe.
    fixture, candidate = resolve_install_fixture(tmp_path, env)
    proc = run_hermes_cli(
        python,
        checkout,
        hermes_home,
        ["plugins", "install", f"file://{fixture}", "--enable"],
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    installed = hermes_home / "plugins" / "hermes-software-pipeline"
    assert_installed_checkout_is_candidate(installed, fixture, candidate, env)
    return python, checkout, hermes_home, installed


def test_pluginmanager_probe_exact_registration_counts(
    installed_plugin: tuple[Path, Path, Path, Path],
) -> None:
    python, checkout, hermes_home, _ = installed_plugin
    proc = run_probe_script(python, checkout, hermes_home, PLUGINMANAGER_PROBE)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PLUGINMANAGER_PROBE_OK" in proc.stdout


def test_hermes_pipeline_help_resolves(
    installed_plugin: tuple[Path, Path, Path, Path],
) -> None:
    python, checkout, hermes_home, _ = installed_plugin
    proc = run_hermes_cli(python, checkout, hermes_home, ["pipeline", "--help"])
    assert proc.returncode == 0, proc.stderr
    for subcommand in ("setup", "doctor", "start", "status", "stop"):
        assert subcommand in proc.stdout


def test_broken_plugin_failsafe_load(
    installed_plugin: tuple[Path, Path, Path, Path],
) -> None:
    """A broken plugin sets loaded.error and Hermes keeps running."""
    python, checkout, hermes_home, _ = installed_plugin
    broken = hermes_home / "plugins" / "broken-plugin"
    broken.mkdir(parents=True)
    (broken / "plugin.yaml").write_text(
        "name: broken-plugin\nversion: 0.1.0\nmanifest_version: 1\n",
        encoding="utf-8",
    )
    # No register() function: load must fail safely.
    (broken / "__init__.py").write_text("", encoding="utf-8")
    proc = run_probe_script(python, checkout, hermes_home, BROKEN_PLUGIN_PROBE)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BROKEN_PLUGIN_FAILSAFE_OK" in proc.stdout
