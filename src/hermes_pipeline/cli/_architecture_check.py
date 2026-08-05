"""Standard-library AST architecture checker (slice-00-02).

Validates package import boundaries from ``docs/architecture/
system-and-module-design.md`` using only ``ast`` and friends, so it runs on
any Python 3.12 without dependencies:

- ``ARCH-01`` forbidden absolute import: a bare top-level import resolves
  to a package submodule and must use the ``hermes_pipeline.`` prefix;
- ``ARCH-02`` forbidden relative import: a relative import of level >= 2
  crosses a Module boundary; only same-package ``from . import`` is allowed;
- ``ARCH-03`` forbidden dynamic import: ``__import__`` and
  ``importlib.import_module`` (including aliases) are rejected;
- ``ARCH-04`` core-to-Adapter reverse dependency;
- ``ARCH-05`` ``domain`` imports only the standard library and contract
  value types;
- ``ARCH-06`` ``controller`` must not import frameworks, provider SDKs,
  process/filesystem modules, or a concrete Adapter;
- ``ARCH-08`` no package imports the root Hermes plugin Shim;
- ``ARCH-99`` unparsable source or missing package root.

Output is stable (sorted, bounded, sanitized) and identifies file, line,
and rule for every diagnostic.
"""

from __future__ import annotations

import ast
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Core Modules that own business authority (system-and-module-design.md).
CORE_MODULES = frozenset({"domain", "contracts", "controller"})

# Dependency families and stdlib modules forbidden inside controller.
CONTROLLER_FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "anthropic",
        "boto3",
        "fastapi",
        "github",
        "google",
        "httpx",
        "langgraph",
        "lark_oapi",
        "openai",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "sqlalchemy",
        "subprocess",
        "tempfile",
    }
)

# Path segments identifying concrete Adapter code.
ADAPTER_SEGMENTS = frozenset({"adapter", "adapters"})

# Import names reserved for the future root Hermes plugin Shim. No package
# in this distribution may reference them.
SHIM_TOP_LEVEL_NAMES = frozenset({"hermes_shim", "hermes_plugin", "plugin", "shim"})

# Output bounds: maximum diagnostics, per-line bytes, and total bytes.
MAX_DIAGNOSTICS = 100
MAX_LINE_BYTES = 240
MAX_OUTPUT_BYTES = 8000


@dataclass(frozen=True)
class Diagnostic:
    """One architecture finding: file (repo-relative), line, rule, message."""

    path: str
    line: int
    rule: str
    message: str


@dataclass(frozen=True)
class _ImportEdge:
    line: int
    level: int
    module: str


class _ImportAnalyzer(ast.NodeVisitor):
    """Collects import edges and module-level alias bindings."""

    def __init__(self) -> None:
        self.edges: list[_ImportEdge] = []
        self.aliases: dict[str, str] = {}
        self.dynamic_import_lines: list[int] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(_ImportEdge(node.lineno, 0, alias.name))
            self.aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.edges.append(_ImportEdge(node.lineno, node.level, module))
        if node.level == 0:
            for alias in node.names:
                if alias.name != "*":
                    self.aliases[alias.asname or alias.name] = (
                        f"{module}.{alias.name}" if module else alias.name
                    )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_dynamic = False
        if isinstance(func, ast.Name):
            name = func.id
            is_dynamic = (
                name == "__import__"
                or self.aliases.get(name) == "importlib.import_module"
            )
        elif isinstance(func, ast.Attribute) and func.attr == "import_module":
            value = func.value
            is_dynamic = isinstance(value, ast.Name) and (
                value.id == "importlib" or self.aliases.get(value.id) == "importlib"
            )
        if is_dynamic:
            self.dynamic_import_lines.append(node.lineno)
        self.generic_visit(node)


def _package_parts(root_name: str, file: Path, root: Path) -> tuple[str, ...]:
    """Package name parts of a module file (root name + directory chain)."""
    rel_dir = file.relative_to(root).parent
    return (root_name, *rel_dir.parts)


def _resolve_edge(
    edge: _ImportEdge, package: tuple[str, ...], root_name: str
) -> tuple[str | None, tuple[str, ...] | None]:
    """Resolve one import edge to (top-level name, in-package inner parts).

    ``inner`` is ``None`` when the target is outside the checked package
    root. A pure-relative edge that escapes the root reports a sentinel.
    """
    if edge.level == 0:
        parts = tuple(p for p in edge.module.split(".") if p)
        if not parts:
            return None, ()
        if parts[0] == root_name:
            return root_name, parts[1:]
        return parts[0], None
    if edge.level > len(package):
        return None, ("<escape>",)
    base = package[: len(package) - (edge.level - 1)]
    parts = tuple(p for p in edge.module.split(".") if p)
    return root_name, base[1:] + parts


def _domain_target_allowed(
    inside: bool, in_package_target: str | None, top_level: str | None
) -> bool:
    """True when a domain import target satisfies the domain whitelist.

    In-package targets must be ``contracts`` or ``domain`` itself; external
    targets must be standard-library top-level names. A relative import
    that escapes the package root is not re-reported here (ARCH-02 already
    owns it).
    """
    if inside:
        return in_package_target in ("contracts", "domain")
    if top_level is None:
        return True
    return top_level in STDLIB_TOP_LEVEL_NAMES


def _check_edge(
    edge: _ImportEdge,
    package: tuple[str, ...],
    root_name: str,
    submodules: frozenset[str],
    rel: str,
    diagnostics: list[Diagnostic],
) -> None:
    top_level, inner = _resolve_edge(edge, package, root_name)
    inside = inner is not None and inner != ("<escape>",)
    in_package_target = inner[0] if (inside and inner) else None

    if edge.level == 0 and top_level in submodules:
        diagnostics.append(
            Diagnostic(
                rel,
                edge.line,
                "ARCH-01",
                f"bare absolute import {edge.module!r} resolves to a package "
                f"submodule; use the '{root_name}.{edge.module}' prefix",
            )
        )

    if edge.level >= 2 or (edge.level > 0 and inner == ("<escape>",)):
        diagnostics.append(
            Diagnostic(
                rel,
                edge.line,
                "ARCH-02",
                f"relative import at level {edge.level} crosses a Module "
                "boundary; use a full 'hermes_pipeline.' absolute import",
            )
        )

    if (
        package[1:]
        and package[1] in CORE_MODULES
        and inside
        and inner is not None
        and any(part in ADAPTER_SEGMENTS for part in inner)
    ):
        diagnostics.append(
            Diagnostic(
                rel,
                edge.line,
                "ARCH-04",
                f"core Module imports an Adapter ({'.'.join(inner)}); "
                "Adapters depend inward on Interfaces, never the reverse",
            )
        )

    if (
        package[1:]
        and package[1] == "domain"
        and not _domain_target_allowed(inside, in_package_target, top_level)
    ):
        diagnostics.append(
            Diagnostic(
                rel,
                edge.line,
                "ARCH-05",
                "domain imports something outside the standard "
                "library and contract value types",
            )
        )

    if package[1:] and package[1] == "controller":
        if top_level in CONTROLLER_FORBIDDEN_TOP_LEVEL:
            diagnostics.append(
                Diagnostic(
                    rel,
                    edge.line,
                    "ARCH-06",
                    f"controller must not import {top_level}",
                )
            )
        if (
            inside
            and inner is not None
            and any(part in ADAPTER_SEGMENTS for part in inner)
        ):
            diagnostics.append(
                Diagnostic(
                    rel,
                    edge.line,
                    "ARCH-06",
                    "controller must not import a concrete Adapter",
                )
            )

    if top_level in SHIM_TOP_LEVEL_NAMES:
        diagnostics.append(
            Diagnostic(
                rel,
                edge.line,
                "ARCH-08",
                f"import {top_level!r} refers to the root Hermes plugin "
                "Shim, which no package may import",
            )
        )


def check_package_tree(root: Path) -> list[Diagnostic]:
    """Return all architecture diagnostics for the package tree at root."""
    if not root.is_dir():
        return [Diagnostic(str(root), 1, "ARCH-99", "package root is missing")]
    diagnostics: list[Diagnostic] = []
    submodules = frozenset(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )
    for file in sorted(root.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        rel = file.relative_to(root).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            diagnostics.append(
                Diagnostic(rel, 1, "ARCH-99", f"cannot parse source: {exc}")
            )
            continue
        package = _package_parts(root.name, file, root)
        analyzer = _ImportAnalyzer()
        analyzer.visit(tree)
        for edge in analyzer.edges:
            _check_edge(edge, package, root.name, submodules, rel, diagnostics)
        for lineno in analyzer.dynamic_import_lines:
            diagnostics.append(
                Diagnostic(
                    rel,
                    lineno,
                    "ARCH-03",
                    "dynamic import via __import__/importlib.import_module "
                    "is forbidden",
                )
            )
    return diagnostics


def _sanitize(value: str) -> str:
    """Escape control characters and truncate one message line."""
    pieces: list[str] = []
    used = 0
    for char in value:
        piece = (
            f"\\u{ord(char):04x}"
            if unicodedata.category(char).startswith("C")
            else char
        )
        encoded_len = len(piece.encode("utf-8"))
        if used + encoded_len > MAX_LINE_BYTES - 3:
            pieces.append("...")
            break
        pieces.append(piece)
        used += encoded_len
    return "".join(pieces)


def render_diagnostics(diagnostics: list[Diagnostic]) -> str:
    """Deterministic, bounded rendering of diagnostics (sorted, sanitized)."""
    ordered = sorted(diagnostics, key=lambda d: (d.path, d.line, d.rule))
    visible = ordered[:MAX_DIAGNOSTICS]
    lines = [f"{d.path}:{d.line}: {d.rule}: {_sanitize(d.message)}" for d in visible]
    if len(ordered) > MAX_DIAGNOSTICS:
        lines.append(
            f"... {len(ordered) - MAX_DIAGNOSTICS} further diagnostic(s) omitted"
        )
    text = "\n".join(lines)
    if len(text.encode("utf-8")) <= MAX_OUTPUT_BYTES:
        return text
    budget = MAX_OUTPUT_BYTES - len(b"\n... (output truncated)")
    kept: list[str] = []
    used = 0
    for line in lines:
        line_len = len(line.encode("utf-8"))
        if used + line_len > budget:
            break
        kept.append(line)
        used += line_len
    return "\n".join(kept) + "\n... (output truncated)"


# Public rule inventory used by tests and diagnostics.
RULES = (
    "ARCH-01",
    "ARCH-02",
    "ARCH-03",
    "ARCH-04",
    "ARCH-05",
    "ARCH-06",
    "ARCH-08",
    "ARCH-99",
)

# Standard-library top-level names are read from the running interpreter;
# expose the set so tests can build valid fixtures without hardcoding it.
STDLIB_TOP_LEVEL_NAMES = frozenset(sys.stdlib_module_names)
