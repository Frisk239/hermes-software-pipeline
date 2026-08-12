"""Golden descriptor/protocol fixtures (slice-00-05, versioning).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Descriptor and protocol versioning is fixed as spike versioned constants
plus committed golden JSON fixtures with accept/reject vectors; the
contract-toolchain path is out of scope. The shim side and the runtime
side must agree on one descriptor shape (the fixtures bind both).
"""

from __future__ import annotations

import json
from pathlib import Path

from hermes_shim._descriptor import validate_descriptor as shim_validate

from hermes_pipeline.transport._descriptor import (
    validate_descriptor as runtime_validate,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "transport"


def test_golden_descriptor_accepted_by_both_sides() -> None:
    document = json.loads((FIXTURES / "descriptor-golden.json").read_text("utf-8"))
    assert shim_validate(document) == []
    assert runtime_validate(document) == []


def test_golden_version_response_shape() -> None:
    response = json.loads(
        (FIXTURES / "version-response-golden.json").read_text("utf-8")
    )
    assert set(response) == {
        "runtime_version",
        "protocol_version",
        "contract_schema_range",
        "release",
        "state_root_identity",
    }
    assert response["protocol_version"] == 1
    assert response["runtime_version"] == "0.1.0"


def test_shim_and_runtime_descriptor_field_sets_identical() -> None:
    import hermes_shim._descriptor as shim_mod

    import hermes_pipeline.transport._descriptor as runtime_mod

    assert set(shim_mod.REQUIRED_FIELDS) == set(runtime_mod.REQUIRED_FIELDS)


def test_shim_and_runtime_protocol_constants_identical() -> None:
    from hermes_shim import _constants as shim_constants

    from hermes_pipeline.transport import _constants as runtime_constants

    for name in (
        "PROTOCOL_VERSION",
        "DESCRIPTOR_VERSION",
        "RUNTIME_VERSION",
        "RELEASE",
        "BODY_LIMIT_BYTES",
        "RATE_WINDOW_SECONDS",
        "RATE_MAX_REQUESTS",
        "CLIENT_CONNECT_TIMEOUT_SECONDS",
        "CLIENT_READ_TIMEOUT_SECONDS",
        "REQUEST_BUDGET_SECONDS",
        "MAX_PORT_ATTEMPTS",
        "TOKEN_HEX_CHARS",
        "START_IDENTITY_HEX_CHARS",
    ):
        assert getattr(shim_constants, name) == getattr(runtime_constants, name), name
