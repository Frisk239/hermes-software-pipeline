"""Real-tool runners are never pytest-collected (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.fake_only


def test_real_runners_are_not_pytest_collected(pytestconfig: pytest.Config) -> None:
    session = pytestconfig.pluginmanager.get_plugin("session")
    collected = getattr(session, "items", [])
    paths = [str(getattr(item, "path", "")) for item in collected]
    joined = "\n".join(paths)
    assert "tools_bootstrap.py" not in joined
    assert "controlled_e2e.py" not in joined
