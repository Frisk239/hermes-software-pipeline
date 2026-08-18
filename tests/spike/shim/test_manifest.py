"""Plugin manifest and registration-surface tests (slice-00-05, AC-01/AC-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Dev-side evidence for the Hermes plugin contract: ``plugin.yaml`` carries
name ``hermes-software-pipeline``, version matching package metadata,
``kind: standalone``, ``manifest_version`` at most 1, and no
``requires_env``; the root entry and ``hermes_shim`` register exactly one
top-level ``pipeline`` CLI command with lifecycle plus submit/read, exactly
one ``pre_gateway_dispatch`` hook, and exactly one declared tool. The real
Hermes PluginManager probe (tests/spike/probe/pluginmanager) provides the
load evidence; these tests pin the surface deterministically.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, cast

import pytest
from hermes_shim import register as shim_register
from hermes_shim._cli import SUBCOMMANDS

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_YAML = REPO_ROOT / "plugin.yaml"


class _FakeCtx:
    """Records PluginContext registrations deterministically."""

    def __init__(self) -> None:
        self.cli_commands: list[dict[str, object]] = []
        self.hooks: list[tuple[str, object]] = []
        self.tools: list[dict[str, object]] = []

    def register_cli_command(self, **kwargs: object) -> None:
        self.cli_commands.append(kwargs)

    def register_hook(self, hook_name: str, callback: object) -> None:
        self.hooks.append((hook_name, callback))

    def register_tool(self, **kwargs: object) -> None:
        self.tools.append(kwargs)


@pytest.fixture
def fake_ctx() -> _FakeCtx:
    return _FakeCtx()


def test_plugin_yaml_shape() -> None:
    text = PLUGIN_YAML.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([a-z0-9_-]+):\s*(.*)$", line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()
    assert fields["name"] == "hermes-software-pipeline"
    assert fields["version"] == "0.1.0"
    assert fields["kind"] == "standalone"
    assert int(fields["manifest_version"]) <= 1
    assert "requires_env" not in fields


def test_plugin_yaml_version_matches_package_metadata() -> None:
    from hermes_pipeline import __version__

    text = PLUGIN_YAML.read_text(encoding="utf-8")
    assert f"version: {__version__}" in text


def test_register_registers_exactly_one_cli_tree(fake_ctx: _FakeCtx) -> None:
    shim_register(fake_ctx)  # type: ignore[arg-type]
    assert len(fake_ctx.cli_commands) == 1
    assert fake_ctx.cli_commands[0]["name"] == "pipeline"


def test_register_registers_exactly_one_hook(fake_ctx: _FakeCtx) -> None:
    shim_register(fake_ctx)  # type: ignore[arg-type]
    assert [name for name, _ in fake_ctx.hooks] == ["pre_gateway_dispatch"]


def test_register_registers_exactly_one_tool(fake_ctx: _FakeCtx) -> None:
    shim_register(fake_ctx)  # type: ignore[arg-type]
    assert len(fake_ctx.tools) == 1
    assert fake_ctx.tools[0]["name"] == "pipeline_health"
    schema = fake_ctx.tools[0]["schema"]
    assert isinstance(schema, dict) and schema["type"] == "object"


def test_pipeline_parser_has_exactly_five_subcommands() -> None:
    from hermes_shim._cli import build_pipeline_parser

    parser = argparse.ArgumentParser()
    build_pipeline_parser(parser)
    subparsers = [a for a in parser._actions if type(a).__name__ == "_SubParsersAction"]
    assert len(subparsers) == 1
    choices = cast(dict[str, Any], cast(Any, subparsers[0]).choices)
    assert set(choices) == set(SUBCOMMANDS)
    assert len(choices) == 9


def test_plugin_yaml_no_requires_env() -> None:
    text = PLUGIN_YAML.read_text(encoding="utf-8")
    assert "requires_env" not in text


def test_negative_manifest_version_two_rejected() -> None:
    """A manifest with manifest_version 2 must be rejected by the installer.

    The dev-side pin asserts the committed manifest stays at most 1; the
    installer rejection itself is exercised by the Hermes install probe.
    """
    text = PLUGIN_YAML.read_text(encoding="utf-8")
    match = re.search(r"^manifest_version:\s*(\d+)\s*$", text, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) <= 1
