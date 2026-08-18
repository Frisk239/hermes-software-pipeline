from __future__ import annotations

from pathlib import Path

from hermes_pipeline.transport.kernel_bridge import KernelBridge

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TOML = ROOT / "runtime-env" / "pyproject.toml"


def test_runtime_env_declares_kernel_contract_deps() -> None:
    text = RUNTIME_TOML.read_text(encoding="utf-8")
    assert "pydantic>=2,<3" in text
    assert "jsonschema>=4,<5" in text
    assert "rfc8785==0.1.4" in text
    assert 'name = "hermes-pipeline-runtime-env"' in text


def test_kernel_bridge_imports() -> None:
    assert KernelBridge is not None
