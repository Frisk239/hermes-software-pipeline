"""The full ``contracts check`` validator (slice-00-03).

Read-only validation of the committed contract registry with bounded,
deterministic output and stable exit semantics (0 pass, 1 fail):

- the 14-Schema identity lock is unchanged from the bootstrap gate;
- every generated Schema meta-validates as Draft 2020-12;
- every ``$ref`` resolves against the registry (JSON Pointer fragments
  included);
- every corpus entry is validated by the immutable f36 snapshot, the strict
  authoring model, and the generated Schema with recorded expectations and
  three-way agreement (round-trip and canonical-hash checks for positives);
- the OpenAPI document matches the fixed AC-07 shape and embeds the exact
  generated Schemas;
- the compatibility registry matches the fixed key set and structure;
- secret canaries never appear in any reported output.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .corpus import (
    BASE_CATEGORIES,
    EXPECTED_PASS,
    CorpusEntry,
    EntryResult,
    load_corpus,
    validate_entry,
)
from .formats import register_rfc3339_checker
from .generate import generate_contract_document, load_json_document
from .jcs import canonical_json, raw_digest
from .registry import COMPONENT_KEYS, CONTRACTS, DRAFT_2020_12, EXPECTED_SCHEMA_IDS

# The frozen jsonschema lacks its optional RFC 3339 checker; registering the
# deterministic shared-rule checker is idempotent and required for every
# instance validation performed by this validator (AC-03, revision 6).
register_rfc3339_checker()

MAX_ISSUES = 60
MAX_LINE_BYTES = 240
MAX_OUTPUT_BYTES = 65536
CANARY_TOKEN_RE = re.compile(r"canary_[A-Za-z0-9_-]+")


def cap_utf8(text: str, limit: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate ``text`` to at most ``limit`` UTF-8 bytes (whole characters)."""
    # Error text can originate in malformed JSON/schema input. ``backslashreplace``
    # keeps even a lone surrogate printable rather than letting reporting raise.
    data = text.encode("utf-8", errors="backslashreplace")
    safe_text = data.decode("utf-8")
    if len(data) <= limit:
        return safe_text
    marker = "\n...(output truncated)"
    marker_bytes = len(marker.encode("utf-8"))
    keep = max(0, limit - marker_bytes)
    head = data[:keep].decode("utf-8", errors="ignore")
    if marker_bytes <= limit:
        return head + marker
    return head


def redact_canaries(text: str) -> str:
    """Replace every canary-shaped token with ``<redacted>`` (AC-10)."""
    return CANARY_TOKEN_RE.sub("<redacted>", text)


def sanitize_diagnostic(text: str) -> str:
    """Render one untrusted diagnostic as a single printable output line."""
    sanitized: list[str] = []
    for char in text:
        code = ord(char)
        if code < 32 or 127 <= code <= 159:
            sanitized.append(f"\\x{code:02x}")
        elif 0xD800 <= code <= 0xDFFF:
            sanitized.append(f"\\u{code:04x}")
        else:
            sanitized.append(char)
    return "".join(sanitized)


def cap_utf8_inline(text: str, limit: int) -> str:
    """Cap a single diagnostic line without introducing a line break."""
    data = text.encode("utf-8", errors="backslashreplace")
    safe_text = data.decode("utf-8")
    if len(data) <= limit:
        return safe_text
    marker = "..."
    keep = max(0, limit - len(marker.encode("utf-8")))
    return data[:keep].decode("utf-8", errors="ignore") + marker


def sanitize_output(text: str, canaries: frozenset[str]) -> str:
    """Bound, sanitize, and redact one reported-output block (AC-10).

    Control characters (other than ``\\n`` and ``\\t``) are replaced with
    their ``\\xNN`` escapes, every canary token collected from the fixtures
    is replaced with ``<redacted>``, and the total is capped at
    ``MAX_OUTPUT_BYTES`` UTF-8 bytes.
    """
    sanitized: list[str] = []
    for char in text:
        code = ord(char)
        if char in "\n\t":
            sanitized.append(char)
        elif code < 32 or 127 <= code <= 159:
            sanitized.append(f"\\x{code:02x}")
        elif 0xD800 <= code <= 0xDFFF:
            sanitized.append(f"\\u{code:04x}")
        else:
            sanitized.append(char)
    text = redact_canaries("".join(sanitized))
    for canary in sorted(canaries, key=len, reverse=True):
        text = text.replace(canary, "<redacted>")
    return cap_utf8(text)


def collect_canary_tokens(root: Path) -> frozenset[str]:
    """Every secret canary token committed under the fixture corpus."""
    corpus_dir = root / "tests" / "fixtures" / "contracts" / "corpus"
    canaries: set[str] = set()
    if corpus_dir.is_dir():
        for path in sorted(corpus_dir.glob("*.json")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                # This function is used by the exception-reporting path. A
                # damaged fixture must not make error reporting throw again.
                continue
            canaries.update(CANARY_TOKEN_RE.findall(text))
    return frozenset(canaries)


class Reporter:
    """Bounded, deterministic issue collector (mirrors bootstrap style)."""

    def __init__(self) -> None:
        self.issues: list[str] = []
        self.suppressed_issues = 0
        self.scanned = 0

    def issue(self, message: str) -> None:
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(
                cap_utf8_inline(sanitize_diagnostic(message), MAX_LINE_BYTES)
            )
        else:
            self.suppressed_issues += 1

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    def render(self) -> str:
        lines = list(self.issues)
        if self.suppressed_issues:
            lines.append(f"... {self.suppressed_issues} further issue(s)")
        return "\n".join(lines)


def _load_schema_documents(root: Path, report: Reporter) -> dict[Path, dict[str, Any]]:
    """Parse every committed Schema document under root/schemas."""
    documents: dict[Path, dict[str, Any]] = {}
    schema_dir = root / "schemas"
    if not schema_dir.is_dir():
        report.issue(f"{schema_dir}: Schema directory missing")
        return documents
    for path in sorted(schema_dir.rglob("*.json")):
        report.scanned += 1
        try:
            document = load_json_document(path)
        except (OSError, ValueError) as exc:
            report.issue(str(exc))
            continue
        documents[path] = document
    return documents


def _check_identity_lock(
    documents: dict[Path, dict[str, Any]], report: Reporter
) -> dict[str, Path]:
    """The declared $id set must exactly equal the locked bootstrap set."""
    declared: dict[str, Path] = {}
    for path, document in documents.items():
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            report.issue(f"{path}: missing string $id")
            continue
        if schema_id in declared:
            report.issue(f"{path}: duplicate $id {schema_id!r}")
            continue
        declared[schema_id] = path
    for schema_id in sorted(EXPECTED_SCHEMA_IDS - set(declared)):
        report.issue(f"expected Schema $id not declared: {schema_id}")
    for schema_id in sorted(set(declared) - EXPECTED_SCHEMA_IDS):
        report.issue(f"unexpected Schema $id: {schema_id} ({declared[schema_id]})")
    return declared


def _check_meta_validation(
    documents: dict[Path, dict[str, Any]], report: Reporter
) -> None:
    """Draft 2020-12 meta-validation of every generated Schema (AC-03)."""
    for path, document in sorted(documents.items()):
        if document.get("$schema") != DRAFT_2020_12:
            report.issue(f"{path}: $schema must be exactly Draft 2020-12")
        try:
            Draft202012Validator.check_schema(document)
        except Exception as exc:
            report.issue(f"{path}: meta-validation failed ({exc})")


def _decode_pointer_token(token: str) -> str | None:
    out: list[str] = []
    i = 0
    while i < len(token):
        char = token[i]
        if char == "~":
            if i + 1 >= len(token) or token[i + 1] not in ("0", "1"):
                return None
            out.append("~" if token[i + 1] == "0" else "/")
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _pointer_resolves(document: object, pointer: str) -> bool:
    """RFC 6901 JSON Pointer resolution inside one document."""
    if not pointer:
        return True
    if not pointer.startswith("/"):
        return False
    current: object = document
    for raw_token in pointer[1:].split("/"):
        token = _decode_pointer_token(raw_token)
        if token is None:
            return False
        if isinstance(current, dict):
            current = cast(dict[str, Any], current)
            if token not in current:
                return False
            current = current[token]
        elif isinstance(current, list):
            current = cast(list[Any], current)
            if token == "-":
                return False
            if not token.isdigit() or (len(token) > 1 and token[0] == "0"):
                return False
            index = int(token)
            if index > 2**31 - 1 or index >= len(current):
                return False
            current = current[index]
        else:
            return False
    return True


def _walk_refs(node: object, trail: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (trail, $ref value) for every $ref inside a schema tree."""
    if isinstance(node, dict):
        node = cast(dict[str, Any], node)
        for key, value in node.items():
            if key == "$ref":
                yield trail, value
            else:
                yield from _walk_refs(value, f"{trail}/{key}")
    elif isinstance(node, list):
        node = cast(list[Any], node)
        for index, item in enumerate(node):
            yield from _walk_refs(item, f"{trail}/{index}")


def _check_ref_closure(
    documents: dict[Path, dict[str, Any]],
    declared: dict[str, Path],
    report: Reporter,
) -> None:
    """Every ``$ref`` in every Schema must resolve (AC-03)."""
    for path, document in sorted(documents.items()):
        for trail, ref in _walk_refs(document):
            if not isinstance(ref, str):
                report.issue(f"{path}:{trail}: $ref is not a string")
                continue
            uri, separator, fragment = ref.partition("#")
            if not separator:
                fragment = ""
            target: dict[str, Any] | None = None
            if uri:
                target_path = declared.get(uri)
                if target_path is None:
                    report.issue(
                        f"{path}:{trail}: $ref does not resolve to a declared "
                        f"Schema: {ref}"
                    )
                    continue
                target = documents.get(target_path)
            else:
                target = document
            if fragment and not fragment.startswith("/"):
                report.issue(f"{path}:{trail}: unsupported non-pointer fragment: {ref}")
                continue
            if target is not None and not _pointer_resolves(target, fragment):
                report.issue(f"{path}:{trail}: JSON Pointer does not resolve: {ref}")


def _build_registry(documents: dict[Path, dict[str, Any]]) -> Registry[Any]:
    """A local referencing registry over the 14 committed Schemas.

    Every absolute ``$ref`` in the registry resolves against this table, so
    validation never performs a network lookup (AC-09 offline rule).
    """
    registry: Registry[Any] = Registry()
    for document in documents.values():
        schema_id = document.get("$id")
        if isinstance(schema_id, str):
            registry = registry.with_resource(
                schema_id, Resource.from_contents(document)
            )
    return registry


def _formatted_validator(
    document: dict[str, Any], registry: Registry
) -> Draft202012Validator:
    """Draft 2020-12 validator with the FORMAT_CHECKER enabled (AC-03)."""
    return Draft202012Validator(
        document, format_checker=Draft202012Validator.FORMAT_CHECKER, registry=registry
    )


def build_snapshot_registry(snapshot_dir: Path, report: Reporter) -> Registry[Any]:
    """A referencing registry built only from the 14 f36 snapshot files.

    The baseline authority must resolve every ``$ref`` against the immutable
    snapshots, never through the current generated Schemas (revision 6): the
    snapshot registry is assembled exclusively from
    ``tests/fixtures/contracts/snapshots/`` contents whose raw digests are
    bound by the committed manifest.
    """
    registry: Registry[Any] = Registry()
    for contract in CONTRACTS:
        snapshot_path = snapshot_dir / Path(contract.relative_path).relative_to(
            "schemas"
        )
        try:
            snapshot = load_json_document(snapshot_path)
        except (OSError, ValueError) as exc:
            report.issue(f"{snapshot_path}: snapshot unavailable ({exc})")
            continue
        schema_id = snapshot.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            report.issue(f"{snapshot_path}: snapshot has no string $id")
            continue
        if schema_id != contract.schema_id:
            report.issue(
                f"{snapshot_path}: snapshot $id does not match its locked identity"
            )
            continue
        registry = registry.with_resource(schema_id, Resource.from_contents(snapshot))
    return registry


def _check_corpus(
    root: Path,
    documents: dict[Path, dict[str, Any]],
    report: Reporter,
) -> list[EntryResult]:
    """Run the full corpus three-way gate (AC-04/AC-05)."""
    fixture_root = root / "tests" / "fixtures" / "contracts"
    results: list[EntryResult] = []
    entries_by_id: dict[str, list[CorpusEntry]] = {}
    try:
        entries = load_corpus(fixture_root)
    except (OSError, UnicodeError, ValueError) as exc:
        report.issue(f"{fixture_root}: corpus is invalid ({exc})")
        return results
    for entry in entries:
        entries_by_id.setdefault(entry.schema_id, []).append(entry)

    for contract in CONTRACTS:
        if contract.model is None:
            continue
        categories = {
            entry.category for entry in entries_by_id.get(contract.schema_id, [])
        }
        missing = sorted(set(BASE_CATEGORIES) - categories)
        if missing:
            report.issue(
                f"{contract.schema_id}: corpus missing required categories {missing}"
            )

    snapshot_dir = fixture_root / "snapshots"
    _check_snapshot_digests(fixture_root, report)
    snapshot_registry = build_snapshot_registry(snapshot_dir, report)
    generated_registry = _build_registry(documents)
    for contract in CONTRACTS:
        schema_path = root / contract.relative_path
        snapshot_path = snapshot_dir / Path(contract.relative_path).relative_to(
            "schemas"
        )
        generated = documents.get(schema_path)
        if generated is None:
            report.issue(f"{schema_path}: generated Schema missing")
            continue
        try:
            snapshot = load_json_document(snapshot_path)
        except (OSError, ValueError) as exc:
            report.issue(f"{snapshot_path}: snapshot unavailable ({exc})")
            continue
        baseline_validator = _formatted_validator(snapshot, snapshot_registry)
        generated_validator = _formatted_validator(generated, generated_registry)
        model = contract.model

        for entry in entries_by_id.get(contract.schema_id, []):
            if model is None:
                report.issue(
                    f"{entry.schema_id}:{entry.name}: corpus entry on a "
                    "non-instantiable contract"
                )
                continue
            result = validate_entry(
                entry, model, baseline_validator, generated_validator
            )
            results.append(result)
            _report_entry(entry, result, report)

    return results


def _report_entry(entry: CorpusEntry, result: EntryResult, report: Reporter) -> None:
    expected = entry.expected == EXPECTED_PASS
    verdicts = {
        "baseline": result.baseline_pass,
        "model": result.model_pass,
        "generated": result.generated_pass,
    }
    if (
        result.baseline_pass != result.model_pass
        or result.model_pass != result.generated_pass
    ):
        report.issue(
            f"{entry.schema_id}:{entry.name}: three-way disagreement {verdicts!r}"
        )
    for authority, passed in verdicts.items():
        if passed != expected:
            report.issue(
                f"{entry.schema_id}:{entry.name}: expected "
                f"{'pass' if expected else 'reject'} but {authority} returned "
                f"{'pass' if passed else 'reject'}"
            )
    if entry.expected == EXPECTED_PASS and not result.round_trip_ok:
        report.issue(f"{entry.schema_id}:{entry.name}: round-trip failed")
    if "content_hash" in entry.document and not result.hash_ok:
        report.issue(f"{entry.schema_id}:{entry.name}: content_hash mismatch")


def _check_snapshot_digests(fixture_root: Path, report: Reporter) -> None:
    """The committed snapshot raw-digest manifest must match the bytes."""
    manifest_path = fixture_root / "raw-digests.json"
    try:
        manifest = load_json_document(manifest_path)
    except (OSError, ValueError) as exc:
        report.issue(f"{manifest_path}: raw-digest manifest unavailable ({exc})")
        return
    digests = manifest.get("digests")
    if not isinstance(digests, dict):
        report.issue(f"{manifest_path}: digests must be a mapping")
        return
    digests = cast(dict[str, Any], digests)
    if manifest.get("kind") != "f36-schema-snapshot-raw-digests":
        report.issue(f"{manifest_path}: unexpected snapshot manifest kind")
    if manifest.get("base_sha") != "f36ba6a2930267e2d90682ff61930c82fd1237bb":
        report.issue(f"{manifest_path}: snapshot base_sha must be f36ba6a")
    expected_paths = {
        "snapshots/" + Path(contract.relative_path).relative_to("schemas").as_posix()
        for contract in CONTRACTS
    }
    if set(digests) != expected_paths:
        missing = sorted(expected_paths - set(digests))
        extra = sorted(set(digests) - expected_paths)
        if missing:
            report.issue(
                f"{manifest_path}: missing raw digest entries ({len(missing)})"
            )
        if extra:
            report.issue(
                f"{manifest_path}: unexpected raw digest entries ({len(extra)})"
            )
    for relative, expected in sorted(digests.items()):
        snapshot = (fixture_root / relative).resolve()
        if not snapshot.is_relative_to(fixture_root):
            report.issue(f"{manifest_path}: digest path escapes the fixture root")
            continue
        try:
            raw = snapshot.read_bytes()
        except OSError as exc:
            report.issue(f"{snapshot}: unreadable ({exc})")
            continue
        if raw_digest(raw) != expected:
            report.issue(f"{snapshot}: raw digest mismatch")


def _check_openapi(root: Path, report: Reporter) -> None:
    """OpenAPI document structure and embedded-schema equality (AC-07)."""
    path = root / "contracts" / "openapi.json"
    try:
        document = load_json_document(path)
    except (OSError, ValueError) as exc:
        report.issue(f"{path}: {exc}")
        return
    if document.get("openapi") != "3.1.0":
        report.issue(f"{path}: openapi must be exactly 3.1.0")
    if (
        document.get("jsonSchemaDialect")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        report.issue(f"{path}: jsonSchemaDialect must be Draft 2020-12")
    info = document.get("info")
    if not isinstance(info, dict):
        report.issue(f"{path}: info must be non-empty")
    else:
        info = cast(dict[str, Any], info)
        if not info.get("title") or not info.get("version"):
            report.issue(f"{path}: info must be non-empty")
    if document.get("paths") != {}:
        report.issue(f"{path}: paths must be exactly an empty object")
    for banned in ("servers", "security", "operationId"):
        if banned in document:
            report.issue(f"{path}: must not contain {banned!r}")

    components = document.get("components")
    if not isinstance(components, dict):
        report.issue(f"{path}: components missing")
        return
    schemas = cast(dict[str, Any], components).get("schemas")
    if not isinstance(schemas, dict):
        report.issue(f"{path}: components.schemas missing")
        return
    schemas = cast(dict[str, Any], schemas)
    if set(schemas) != set(COMPONENT_KEYS):
        report.issue(
            f"{path}: component keys must be exactly the fixed 14 "
            f"(got {sorted(schemas)})"
        )
    for contract in CONTRACTS:
        component = schemas.get(contract.component_key)
        if component is None:
            continue
        expected = generate_contract_document(contract)
        try:
            if canonical_json(component) != canonical_json(expected):
                report.issue(
                    f"{path}: component {contract.component_key!r} is not "
                    "canonically equal to its generated Schema"
                )
        except (TypeError, ValueError) as exc:
            report.issue(f"{path}: component {contract.component_key!r}: {exc}")
        if component.get("$id") != contract.schema_id:
            report.issue(
                f"{path}: component {contract.component_key!r} must embed the "
                f"exact $id {contract.schema_id!r}"
            )


def _check_registry(root: Path, report: Reporter) -> None:
    """Compatibility registry structure and key set (AC-08)."""
    path = root / "contracts" / "compatibility-registry.json"
    try:
        document = load_json_document(path)
    except (OSError, ValueError) as exc:
        report.issue(f"{path}: {exc}")
        return
    if set(document) != set(EXPECTED_SCHEMA_IDS):
        report.issue(f"{path}: registry keys must equal the 14-Schema $id set exactly")
    for schema_id, entry in sorted(document.items()):
        if not isinstance(entry, dict):
            report.issue(f"{path}: entry {schema_id!r} must be an object")
            continue
        entry = cast(dict[str, Any], entry)
        current = entry.get("current_version")
        supported = entry.get("supported_versions")
        if not isinstance(current, int) or isinstance(current, bool) or current < 1:
            report.issue(
                f"{path}: {schema_id!r} current_version must be an integer >= 1"
            )
        if not isinstance(supported, list):
            report.issue(
                f"{path}: {schema_id!r} supported_versions must be non-empty "
                "and strictly increasing"
            )
            continue
        supported = cast(list[Any], supported)
        if (
            not supported
            or not all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in supported
            )
            or any(supported[i] >= supported[i + 1] for i in range(len(supported) - 1))
        ):
            report.issue(
                f"{path}: {schema_id!r} supported_versions must be non-empty "
                "and strictly increasing"
            )
            continue
        supported = cast(list[int], supported)
        if supported[-1] != current:
            report.issue(
                f"{path}: {schema_id!r} current_version must be the maximum "
                "of supported_versions"
            )


def _check_canaries(
    fixture_root: Path, report: Reporter, output: str
) -> frozenset[str]:
    """Secret canaries must never appear in any reported output (AC-04/10).

    Returns the collected canary tokens so the caller can redact them from
    the final rendered output; a leaked token adds a failure issue without
    ever repeating the token itself.
    """
    corpus_dir = fixture_root / "corpus"
    canaries: set[str] = set()
    if corpus_dir.is_dir():
        for path in sorted(corpus_dir.glob("*.json")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                report.issue(f"{path}: cannot safely read canary corpus")
                continue
            canaries.update(CANARY_TOKEN_RE.findall(text))
    for canary in sorted(canaries):
        if canary in output:
            report.issue("secret canary leaked into reported output")
    return frozenset(canaries)


def run_contracts_check(root: Path) -> tuple[bool, str]:
    """Run the full validator; returns (ok, rendered output)."""
    report = Reporter()
    documents = _load_schema_documents(root, report)
    declared = _check_identity_lock(documents, report)
    _check_meta_validation(documents, report)
    _check_ref_closure(documents, declared, report)
    results = _check_corpus(root, documents, report)
    _check_openapi(root, report)
    _check_registry(root, report)

    entry_count = len(results)
    positive = sum(1 for result in results if result.entry.expected == EXPECTED_PASS)
    output_lines = [
        (
            f"contracts check: OK ({len(documents)} Schema document(s), "
            f"{entry_count} corpus entries [{positive} positive], "
            "14 OpenAPI components, 14 registry keys)"
            if not report.has_issues
            else "contracts check: FAIL"
        )
    ]
    if report.has_issues:
        output_lines.append(report.render())

    fixture_root = root / "tests" / "fixtures" / "contracts"
    canaries = _check_canaries(fixture_root, report, "\n".join(output_lines))
    if report.has_issues:
        output_lines = ["contracts check: FAIL", report.render()]

    rendered = sanitize_output("\n".join(output_lines) + "\n", canaries)
    return not report.has_issues, rendered
