"""Pydantic JSON-schema generator for the contract toolchain.

The committed Schemas reference the shared ``common/definitions`` $defs
library through standalone ``$ref`` values (absolute $id fragments, or local
``#/$defs/...`` fragments inside the definitions document itself). Pydantic
normally resolves every ``$ref`` against its own definitions registry and
fails on unregistered references; this generator keeps unregistered toolchain
references verbatim so the authoring types can emit the exact committed
``$ref`` documents. Registered references (nested Pydantic models) continue
to resolve and are later inlined by the projection layer.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from pydantic.json_schema import DefsRef, GenerateJsonSchema, JsonRef, JsonSchemaValue


def _collect_json_refs(schema: JsonSchemaValue) -> set[str]:
    """All ``$ref`` values anywhere in a schema tree (module-local walker)."""

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            mapping = cast(dict[str, Any], value)
            for key, item in mapping.items():
                if key == "$ref" and isinstance(item, str):
                    refs.add(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in cast(list[Any], value):
                walk(item)

    refs: set[str] = set()
    walk(schema)
    return refs


class NoResolveSchemaGenerator(GenerateJsonSchema):
    """``GenerateJsonSchema`` that passes unregistered toolchain refs through.

    Pydantic's own definitions registry only knows refs it created itself
    (``#/$defs/<Model>``). Absolute ``https://...`` refs and ``#/$defs/...``
    fragments declared by the authoring types are never registered; the base
    implementation converts them to ``None``/``KeyError`` and the wrapping
    handlers raise. Returning the reference itself keeps ``{"$ref": ...}``
    as the standalone schema the committed projection requires.
    """

    def get_schema_from_definitions(self, json_ref: JsonRef) -> JsonSchemaValue | None:
        if str(json_ref).startswith(("http://", "https://")):
            return {"$ref": str(json_ref)}
        try:
            return super().get_schema_from_definitions(json_ref)
        except KeyError:
            # A local fragment that pydantic never registered is a toolchain
            # $defs reference (for example "#/$defs/relativePath").
            return {"$ref": str(json_ref)}

    def get_json_ref_counts(self, json_schema: JsonSchemaValue) -> dict[JsonRef, int]:
        """Count ``$ref`` occurrences, skipping unregistered toolchain refs.

        The base implementation performs a direct registry lookup that
        raises ``KeyError`` for unregistered local fragments. Toolchain refs
        are standalone values that are never unpacked, so they contribute a
        count of one and need no recursion into definitions.
        """
        json_refs: Counter[str] = Counter()

        def _add_json_refs(schema: Any) -> None:
            if isinstance(schema, dict):
                mapping = cast(dict[str, Any], schema)
                if "$ref" in mapping:
                    ref_value = mapping["$ref"]
                    if not isinstance(ref_value, str):
                        # "$ref" is a property name here, not a reference.
                        return
                    json_ref = JsonRef(ref_value)
                    already_visited = json_ref in json_refs
                    json_refs[json_ref] += 1
                    if already_visited:
                        return
                    try:
                        defs_ref = self.json_to_defs_refs[json_ref]
                        if defs_ref in self._core_defs_invalid_for_json_schema:
                            raise self._core_defs_invalid_for_json_schema[defs_ref]
                        _add_json_refs(self.definitions[defs_ref])
                    except KeyError:
                        # Unregistered absolute and local toolchain refs are
                        # standalone; there is nothing to recurse into.
                        pass
                for key, value in mapping.items():
                    if key == "examples" and isinstance(value, list):
                        continue
                    _add_json_refs(value)
            elif isinstance(schema, list):
                for value in cast(list[Any], schema):
                    _add_json_refs(value)

        _add_json_refs(json_schema)
        return cast(dict[JsonRef, int], json_refs)

    def _garbage_collect_definitions(self, schema: JsonSchemaValue) -> None:
        """Keep registered definitions, tolerating unregistered toolchain refs.

        The base implementation raises ``KeyError`` when it meets a local
        ``#/$defs/...`` fragment that pydantic never registered; toolchain
        fragments are standalone references with no definition to visit.
        """
        visited_defs_refs: set[DefsRef] = set()
        unvisited_json_refs = _collect_json_refs(schema)
        while unvisited_json_refs:
            next_json_ref = unvisited_json_refs.pop()
            try:
                next_defs_ref = self.json_to_defs_refs[JsonRef(next_json_ref)]
                if next_defs_ref in visited_defs_refs:
                    continue
                visited_defs_refs.add(next_defs_ref)
                unvisited_json_refs.update(
                    _collect_json_refs(self.definitions[next_defs_ref])
                )
            except KeyError:
                # Unregistered absolute and local toolchain refs are
                # standalone; there is nothing to visit.
                pass
        self.definitions = {
            key: value
            for key, value in self.definitions.items()
            if key in visited_defs_refs
        }

    def sort(
        self, value: JsonSchemaValue, parent_key: str | None = None
    ) -> JsonSchemaValue:
        """Keep Pydantic's insertion order; ordering is owned by the projection.

        The base implementation alphabetically sorts every schema object,
        which would fight the committed projection key order and the
        definitions document's fixed ``$defs`` order. The projection layer
        (``serialize.render_json``) applies the single authoritative order.
        """
        return value
