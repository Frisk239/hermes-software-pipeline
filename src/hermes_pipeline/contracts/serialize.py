"""Deterministic projection of authoring-model schemas.

Pydantic's ``model_json_schema`` output carries implementation details the
committed projections do not (field titles, redundant ``type`` siblings next
to ``const``/``enum``, local ``$defs`` for nested models, the implicit
``additionalProperties: true``). This module normalizes a generated schema
dict into the committed projection shape and renders it with the canonical
representation: sorted keys, two-space indentation, LF/UTF-8, and a trailing
newline. Rendering is pure and byte-identical across platforms; no part of
the representation is derived from the historical f36 file layout.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast


def render_json(value: Any) -> str:
    """Render a JSON value in the canonical projection representation.

    Keys sort alphabetically, objects and arrays render with two-space
    indentation, output is LF/UTF-8 with a trailing newline, and nothing
    outside ``value`` (timestamps, paths, environment) enters the bytes.
    """
    return _render(value, 0) + "\n"


def _render(value: Any, level: int) -> str:
    if isinstance(value, dict):
        value = cast(dict[str, Any], value)
        items = sorted(value.items(), key=lambda pair: pair[0])
        if not items:
            return "{}"
        pad = "  " * (level + 1)
        close = "  " * level
        lines = [
            f"{pad}{json.dumps(key, ensure_ascii=False)}: {_render(item, level + 1)}"
            for key, item in items
        ]
        return "{\n" + ",\n".join(lines) + "\n" + close + "}"
    if isinstance(value, list):
        value = cast(list[Any], value)
        if not value:
            return "[]"
        pad = "  " * (level + 1)
        close = "  " * level
        lines = [f"{pad}{_render(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(lines) + "\n" + close + "]"
    return json.dumps(value, ensure_ascii=False)


def normalize_schema(node: Any, *, root: bool = False) -> Any:
    """Normalize one schema node into the committed projection shape.

    Rules (all equivalence-preserving representations of the model output):

    - ``const``/``enum`` projections drop their redundant ``type`` sibling;
    - ``title`` survives only at the document root (pydantic field titles are
      an implementation detail of the authoring types);
    - ``additionalProperties: true`` (the JSON Schema default) is dropped;
    - ``anyOf`` whose members are all single-``type`` schemas collapses to
      the equivalent ``type`` array (``["string", "integer", "boolean"]``);
    - ``$ref`` projections stand alone.
    """
    if isinstance(node, list):
        return [normalize_schema(item) for item in cast(list[Any], node)]
    if not isinstance(node, dict):
        return node
    node = cast(dict[str, Any], node)

    normalized: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            properties = cast(dict[str, Any], value)
            normalized[key] = {
                name: normalize_schema(sub) for name, sub in properties.items()
            }
        elif key in ("items", "if", "then", "not"):
            normalized[key] = normalize_schema(value)
        elif key in ("anyOf", "allOf", "oneOf") and isinstance(value, list):
            normalized[key] = [
                normalize_schema(item) for item in cast(list[Any], value)
            ]
        elif key == "$defs" and isinstance(value, dict):
            defs = cast(dict[str, Any], value)
            normalized[key] = {
                name: normalize_schema(sub) for name, sub in defs.items()
            }
        else:
            normalized[key] = value

    if "const" in normalized:
        normalized = {key: normalized[key] for key in ("const",) if key in normalized}
    elif "enum" in normalized:
        normalized = {key: normalized[key] for key in ("enum",) if key in normalized}
    elif "$ref" in normalized:
        normalized = {key: normalized[key] for key in ("$ref",) if key in normalized}

    # Pydantic emits numeric constraints as ``ge``/``le``/``gt``/``lt`` for
    # annotated integer types; the Draft 2020-12 projection spells them
    # ``minimum``/``maximum``/``exclusiveMinimum``/``exclusiveMaximum``.
    for source, target in (
        ("ge", "minimum"),
        ("le", "maximum"),
        ("gt", "exclusiveMinimum"),
        ("lt", "exclusiveMaximum"),
    ):
        if source in normalized:
            normalized[target] = normalized.pop(source)

    if normalized.get("additionalProperties") is True:
        del normalized["additionalProperties"]
    normalized.pop("description", None)  # model docstrings are not projected
    if not root:
        normalized.pop("title", None)

    if isinstance(normalized.get("anyOf"), list):
        members = cast(list[Any], normalized["anyOf"])
        if members and all(
            isinstance(member, dict) and set(cast(dict[str, Any], member)) == {"type"}
            for member in members
        ):
            normalized["type"] = [member["type"] for member in members]
            del normalized["anyOf"]

    return normalized


def inline_local_defs(node: Any, defs: Mapping[str, Any]) -> Any:
    """Inline every local ``#/$defs/<name>`` reference with its definition.

    Nested authoring models are emitted by Pydantic as local references with
    a root ``$defs`` table; the committed projections inline them. Sibling
    keywords next to a ``$ref`` (Draft 2020-12 allows them) are merged into
    the inlined content. The root ``$defs`` table is removed afterwards.
    """

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in cast(list[Any], value)]
        if not isinstance(value, dict):
            return value
        value = cast(dict[str, Any], value)
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref[len("#/$defs/") :]
            definition = defs.get(name)
            if definition is None:
                raise KeyError(f"unresolved local $defs reference: {ref}")
            merged: dict[str, Any] = {}
            merged.update(cast(Mapping[str, Any], definition))
            for key, item in value.items():
                if key != "$ref":
                    merged[key] = item
            return walk(merged)
        return {key: walk(item) for key, item in value.items()}

    result = walk(node)
    if isinstance(result, dict):
        dict_result = cast(dict[str, Any], result)
        dict_result.pop("$defs", None)
        return dict_result
    return result
