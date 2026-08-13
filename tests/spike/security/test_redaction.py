"""Hermes-side redaction and child-env canary denial (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import pytest

from hermes_pipeline.runtime_broker._redaction import (
    MAX_BOUNDED_BYTES,
    REDACTED,
    bound_text,
    child_environment,
    redact,
)

pytestmark = pytest.mark.fake_only

CANARIES = (
    "sk-canary-secret",
    "HOSTCANARY",
    "usercanary",
    "C:\\\\secret\\\\path",
    "ENVCANARY",
    "tok_canary",
)


def test_canaries_never_survive_redaction() -> None:
    raw = (
        "user=usercanary host=HOSTCANARY token=sk-canary-secret "
        "path=C:\\secret\\path env=ENVCANARY tok=tok_canary"
    )
    cleaned = redact(raw, CANARIES)
    for canary in CANARIES:
        assert canary not in cleaned
    assert REDACTED in cleaned


def test_output_is_byte_capped() -> None:
    assert (
        len(bound_text("x" * (MAX_BOUNDED_BYTES + 50)).encode("utf-8"))
        <= MAX_BOUNDED_BYTES
    )


def test_child_environment_drops_secret_canaries() -> None:
    env = child_environment(
        {
            "PATH": "/bin",
            "TOKEN": "sk-canary-secret",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
        },
        allow=("PATH", "OPENCODE_DISABLE_AUTOUPDATE"),
        canaries=CANARIES,
    )
    assert "TOKEN" not in env
    assert env["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
    assert "sk-canary-secret" not in env.values()
