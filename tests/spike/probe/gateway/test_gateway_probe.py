"""Synthetic /card interception probe through the real gateway dispatch
path (slice-00-05, AC-09).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

With the shim loaded in a real Hermes process, construct the Feishu-style
synthetic event exactly as the installed Feishu adapter does
(``/card <tag> <json>``, ``MessageType.COMMAND``, resolved source) and
drive the real gateway dispatch path (``GatewayRunner._handle_message``)
with the real ``pre_gateway_dispatch`` hook. The probe event is skipped
with one authenticated loopback fake command submitted and a Prod Main
invocation counter at zero; non-probe events reach the dispatch stub; the
hook never raises. Real Feishu connections are never used (fixed decision
D7; Hermes' own in-tree test seam is the reference).
"""

from __future__ import annotations

from pathlib import Path

from tests.spike.probe._hermes import (
    assert_installed_checkout_is_candidate,
    hermes_checkout,
    hermes_python,
    probe_env,
    resolve_install_fixture,
    run_hermes_cli,
    run_probe_script,
)
from tests.spike.runtime._harness import (
    provision,
    start_runtime,
    stop_runtime,
    wait_for_descriptor,
    wait_runtime_ready,
)

GATEWAY_PROBE = r"""
import asyncio
from types import SimpleNamespace

from hermes_cli.plugins import get_plugin_manager
import hermes_cli.plugins as plugins_mod

pm = get_plugin_manager()
pm.discover_and_load()
hook = pm._hooks["pre_gateway_dispatch"][0]

from gateway.config import GatewayConfig, Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource

def make_event(text, message_id, message_type=MessageType.COMMAND):
    return MessageEvent(
        text=text,
        message_id=message_id,
        message_type=message_type,
        source=SessionSource(
            # Mirrors the pinned Feishu adapter's build_source() values for
            # a card-action synthetic event: FEISHU platform, open-chat ID,
            # operator open ID, and resolved union-id alternate identity.
            platform=Platform.FEISHU,
            chat_id="oc_probe_card_chat",
            chat_name="Feishu Probe Chat",
            chat_type="group",
            user_id="ou_probe_operator",
            user_name="tester",
            user_id_alt="on_probe_operator",
        ),
    )

runner = object.__new__(GatewayRunner)
runner.config = GatewayConfig(platforms={})
runner.adapters = {}
runner.pairing_store = SimpleNamespace(
    is_approved=lambda *a, **k: True,
    _is_rate_limited=lambda *a, **k: False,
)
runner.session_store = SimpleNamespace()
runner._running_agents = {}
runner._update_prompt_pending = {}

prod_main = {"count": 0}

async def capture(event, source, quick_key, run_generation):
    prod_main["count"] += 1
    return "prod-main-stub"

runner._handle_message_with_agent = capture

def fake_invoke(name, **kwargs):
    if name == "pre_gateway_dispatch":
        return [hook(**kwargs)]
    return []

plugins_mod.invoke_hook = fake_invoke

async def scenario():
    # Probe event: /card hermes_pipeline_fake_probe <json>, explicitly
    # MessageType.COMMAND (the Feishu command path) — is_command() must
    # resolve so the dispatch branch is the commanded one.
    probe_event = make_event(
        "/card hermes_pipeline_fake_probe "
        '{"command_id":"gw_probe_1","payload":{"op":"fake-probe"}}',
        "probe-message-0001",
        message_type=MessageType.COMMAND,
    )
    assert probe_event.is_command()
    result = await runner._handle_message(probe_event)
    assert result is None, result
    assert prod_main["count"] == 0, prod_main
    # Non-probe event reaches the normal dispatch stub (plain text path).
    plain_event = make_event(
        "hello", "plain-message-0002", message_type=MessageType.TEXT
    )
    await runner._handle_message(plain_event)
    assert prod_main["count"] == 1, prod_main
    print("GATEWAY_PROBE_OK prod_main=1")

asyncio.run(scenario())
"""


def test_gateway_interception_probe(tmp_path: Path) -> None:
    python = hermes_python()
    checkout = hermes_checkout(python)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()

    # The runtime's state root lives beneath the isolated HERMES_HOME so
    # the real hook resolves the descriptor and submits the loopback fake
    # command exactly as the production shim would.
    state_root = hermes_home / "software-pipeline"
    provision(state_root, offline=False)
    runtime = start_runtime(state_root)
    try:
        wait_for_descriptor(state_root)
        wait_runtime_ready(state_root)

        # The same event-derived Candidate fixture used by every Hermes
        # probe (install, PluginManager, Gateway).
        env = probe_env(hermes_home)
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

        proc = run_probe_script(python, checkout, hermes_home, GATEWAY_PROBE)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "GATEWAY_PROBE_OK" in proc.stdout

        # The probe event submitted exactly one authenticated loopback fake
        # command: one receipt with one effect in the disposable store.
        import sqlite3

        with sqlite3.connect(
            str(state_root / "descriptor" / "receipts.sqlite3")
        ) as conn:
            rows = conn.execute(
                "SELECT command_id, effect_count FROM receipts "
                "WHERE command_id LIKE 'probe_%'"
            ).fetchall()
        assert len(rows) == 1, rows
        command_id, effect_count = rows[0]
        assert command_id.startswith("probe_")
        assert effect_count == 1
    finally:
        stop_runtime(runtime, state_root)
