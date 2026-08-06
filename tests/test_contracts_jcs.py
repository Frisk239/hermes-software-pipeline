"""RFC 8785 golden vectors, rejection behavior, and single-implementation
guarantee (AC-06).

The committed vectors lock the canonical output of the pinned rfc8785
implementation; NaN, Infinity, and lone surrogates must be rejected, and no
``sort_keys``-style approximation may exist anywhere in the toolchain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_pipeline.contracts.jcs import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads(
    (
        REPO_ROOT / "tests" / "fixtures" / "contracts" / "vectors" / "jcs-golden.json"
    ).read_text(encoding="utf-8")
)


def test_golden_vectors_reproduce_exact_canonical_and_digests() -> None:
    import hashlib

    assert VECTORS["implementation"] == "rfc8785==0.1.4"
    assert VECTORS["vectors"]
    for vector in VECTORS["vectors"]:
        actual = canonical_json(vector["input"])
        assert actual == vector["canonical"], vector["name"]
        digest = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        assert f"sha256:{digest}" == vector["sha256"], vector["name"]


def test_rejections_cover_nan_infinity_and_lone_surrogates() -> None:
    names = {item["name"] for item in VECTORS["rejections"]}
    assert {"nan", "infinity", "negative-infinity", "lone-surrogate"} <= names
    for item in VECTORS["rejections"]:
        with pytest.raises(ValueError):
            canonical_json(item["input"])


def test_no_sort_keys_approximation_in_the_toolchain() -> None:
    package = REPO_ROOT / "src" / "hermes_pipeline" / "contracts"
    for path in sorted(package.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "sort_keys" not in text, path
        if path.name != "serialize.py":
            assert "json.dumps" not in text, (
                f"{path} must not serialize JSON directly (use serialize.render_json)"
            )
