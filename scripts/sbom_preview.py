#!/usr/bin/env python3
"""Print a deterministic offline SBOM preview from uv.lock."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True

EXIT_OK = 0
EXIT_FAIL = 1


def _source_label(source: object) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        for key in ("registry", "path", "editable", "virtual", "git", "url"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(source, sort_keys=True, separators=(",", ":"))
    return ""


def preview_packages(lock_text: bytes) -> list[dict[str, str]]:
    document = tomllib.loads(lock_text.decode("utf-8"))
    packages: list[dict[str, str]] = []
    for item in document.get("package", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        version = item.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "source": _source_label(item.get("source", "")),
            }
        )
    packages.sort(key=lambda row: (row["name"], row["version"]))
    return packages


def build_preview(root: Path) -> dict[str, object]:
    lock_path = root / "uv.lock"
    packages = preview_packages(lock_path.read_bytes())
    return {
        "schema": "hermes-sbom-preview/v1",
        "lock_file": "uv.lock",
        "packages": packages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    lock_path = root / "uv.lock"
    if not lock_path.is_file():
        print("sbom_preview: FAIL missing uv.lock", file=sys.stderr)
        return EXIT_FAIL
    document = build_preview(root)
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
