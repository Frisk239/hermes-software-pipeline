"""Safe source-checkout discovery and loading for bootstrap CLI commands."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import cast

# Stable exit codes: 0 success, 1 check failure, 2 usage error.
EXIT_OK = 0
EXIT_CHECK_FAIL = 1
EXIT_USAGE = 2

_MISSING = object()
_SCRIPT_LOCAL_MODULES = ("_check_common", "check_schemas")


def find_repository_root(start: Path) -> Path | None:
    """Return the enclosing source checkout, or ``None`` outside one.

    The repository checks intentionally delegate to the committed bootstrap
    scripts and Schema registry. They therefore require a source checkout;
    the installed console entry point remains usable for ``--version`` in a
    standalone wheel environment.
    """
    anchor = start.resolve()
    if anchor.is_file():
        anchor = anchor.parent
    for candidate in (anchor, *anchor.parents):
        if (candidate / "scripts" / "check_schemas.py").is_file() and (
            candidate / "src" / "hermes_pipeline"
        ).is_dir():
            return candidate
    return None


def repo_root() -> Path | None:
    """Find the source checkout enclosing this editable installation, if any."""
    return find_repository_root(Path(__file__))


@contextmanager
def isolated_script_module(
    module_name: str, script: Path
) -> Generator[ModuleType, None, None]:
    """Load one bootstrap script and restore interpreter import state on exit.

    Bootstrap scripts use a bare ``_check_common`` import so that they stay
    dependency-free command-line files. Snapshotting their two local module
    names and the full import path prevents that implementation detail from
    leaking across CLI invocations or tests.
    """
    original_path = list(sys.path)
    module_names = set(_SCRIPT_LOCAL_MODULES) | {module_name}
    previous_modules: dict[str, object] = {
        name: sys.modules.get(name, _MISSING) for name in module_names
    }
    try:
        sys.path.insert(0, str(script.parent))
        for name in module_names:
            sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(module_name, script)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load bootstrap script: {script}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path[:] = original_path
        for name, previous in previous_modules.items():
            if previous is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = cast(ModuleType, previous)
