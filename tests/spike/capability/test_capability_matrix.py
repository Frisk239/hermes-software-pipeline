"""Four-state CapabilityProfile field matrix (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import pytest

from hermes_pipeline.runtime_broker._capability import (
    CAPABILITY_FIELDS,
    classify_filesystem,
    classify_network_deny,
    e2e_browser_composition,
    record_matrix,
)

pytestmark = pytest.mark.fake_only


def test_every_capability_field_has_a_dated_verdict() -> None:
    matrix = record_matrix()
    assert {row.field for row in matrix} == set(CAPABILITY_FIELDS)
    assert all(row.observed_at_utc.endswith("Z") for row in matrix)
    assert all(
        row.verdict
        in {
            "ENFORCED",
            "OBSERVED_ONLY",
            "UNSUPPORTED_RUNTIME",
            "NOT_APPLICABLE",
        }
        for row in matrix
    )


def test_hard_network_deny_is_unsupported_without_os_block() -> None:
    assert classify_network_deny(os_egress_block=False, privileged=False) == (
        "UNSUPPORTED_RUNTIME"
    )
    assert classify_network_deny(os_egress_block=True, privileged=True) == "ENFORCED"


def test_same_user_filesystem_acl_is_observed_only() -> None:
    assert classify_filesystem(lower_privilege_or_sandbox=False) == "OBSERVED_ONLY"
    assert classify_filesystem(lower_privilege_or_sandbox=True) == "ENFORCED"


def test_e2e_browser_composition_does_not_re_widen() -> None:
    matrix = record_matrix()
    assert e2e_browser_composition(matrix) is True
    egress = next(row for row in matrix if row.field == "network.egress")
    assert egress.verdict == "UNSUPPORTED_RUNTIME"
